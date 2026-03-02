"""Celery call task — place reservation call with retry logic."""

from __future__ import annotations

import structlog
from datetime import datetime

logger = structlog.get_logger()


# Default config values (overridden from env in production)
MAX_RETRIES = 3
RETRY_DELAYS = [60, 120, 300]  # Exponential backoff: 1min, 2min, 5min


class CallTaskError(Exception):
    """Raised when a call task fails."""
    pass


async def place_reservation_call(
    reservation_id: str,
    db,
    session_store,
    caller_module,
    attempt: int = 1,
    max_retries: int = MAX_RETRIES,
) -> dict:
    """Place a reservation call with retry logic.

    Args:
        reservation_id: The reservation to call for.
        db: Database provider.
        session_store: Session store for tokens.
        caller_module: Module with initiate_call, generate_ws_token.
        attempt: Current attempt number (1-based).
        max_retries: Maximum number of attempts.

    Returns:
        Dict with status and call details.
    """
    from src.models.enums import ReservationStatus

    # Load reservation
    reservation = await db.get_reservation(reservation_id)
    if not reservation:
        raise CallTaskError(f"Reservation {reservation_id} not found")

    # Validate state
    status = reservation["status"]
    if status not in (ReservationStatus.PENDING, ReservationStatus.CALLING):
        raise CallTaskError(
            f"Cannot place call for reservation in '{status}' state"
        )

    logger.info(
        "call_task.starting",
        reservation_id=reservation_id,
        attempt=attempt,
        max_retries=max_retries,
    )

    try:
        # Update status to calling
        if status == ReservationStatus.PENDING:
            await db.update_reservation(reservation_id, status=ReservationStatus.CALLING)
            await db.log_state_transition({
                "reservation_id": reservation_id,
                "from_state": status,
                "to_state": ReservationStatus.CALLING,
                "trigger": "call_task",
                "metadata": f"attempt {attempt}",
                "created_at": datetime.utcnow().isoformat(),
            })

        # Update call attempts
        await db.update_reservation(reservation_id, call_attempts=attempt)

        # Generate token and initiate call
        token = await caller_module.generate_ws_token(
            reservation_id, session_store
        )
        call_sid = await caller_module.initiate_call(
            to_number=reservation["restaurant_phone"],
            reservation_id=reservation_id,
            token=token,
        )

        # Log the call
        await db.log_call({
            "reservation_id": reservation_id,
            "call_sid": call_sid,
            "attempt": attempt,
            "status": "initiated",
            "created_at": datetime.utcnow().isoformat(),
        })

        logger.info(
            "call_task.initiated",
            reservation_id=reservation_id,
            call_sid=call_sid,
            attempt=attempt,
        )

        return {"status": "initiated", "call_sid": call_sid, "attempt": attempt}

    except Exception as e:
        logger.error(
            "call_task.error",
            reservation_id=reservation_id,
            attempt=attempt,
            error=str(e),
        )

        if attempt >= max_retries:
            # Max retries exhausted → fail the reservation
            await db.update_reservation(
                reservation_id, status=ReservationStatus.FAILED
            )
            await db.log_state_transition({
                "reservation_id": reservation_id,
                "from_state": ReservationStatus.CALLING,
                "to_state": ReservationStatus.FAILED,
                "trigger": "call_task_max_retries",
                "metadata": f"Failed after {attempt} attempts: {e}",
                "created_at": datetime.utcnow().isoformat(),
            })

            logger.info("call_task.max_retries", reservation_id=reservation_id)
            return {"status": "failed", "reason": str(e), "attempt": attempt}

        # Calculate retry delay (exponential backoff)
        delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
        logger.info(
            "call_task.scheduling_retry",
            reservation_id=reservation_id,
            next_attempt=attempt + 1,
            delay=delay,
        )

        return {"status": "retry", "next_attempt": attempt + 1, "delay": delay}
