"""Cleanup tasks — stale state remediation.

Periodic tasks to handle:
- Stale 'calling' reservations (stuck >10 minutes → failed)
- Stale 'alternative_proposed' reservations (no response >24h → failed)
"""

from __future__ import annotations

import structlog
from datetime import datetime

from src.models.enums import ReservationStatus

logger = structlog.get_logger()

# Default timeouts
STALE_CALLING_TIMEOUT_MINUTES = 10
STALE_ALT_PROPOSED_TIMEOUT_HOURS = 24


async def cleanup_stale_reservations(
    db,
    calling_timeout_minutes: int = STALE_CALLING_TIMEOUT_MINUTES,
    alt_timeout_hours: int = STALE_ALT_PROPOSED_TIMEOUT_HOURS,
    notifier=None,
) -> dict:
    """Find and remediate stale reservations.

    Args:
        db: Database provider.
        calling_timeout_minutes: Minutes before a 'calling' reservation is stale.
        alt_timeout_hours: Hours before an 'alternative_proposed' reservation expires.
        notifier: Optional notifier for sending failure notifications.

    Returns:
        Dict with counts of remediated reservations.
    """
    results = {"stale_calling": 0, "stale_alt_proposed": 0}

    # 1. Stale 'calling' reservations
    stale_calling = await db.list_reservations_by_status(
        ReservationStatus.CALLING,
        older_than_minutes=calling_timeout_minutes,
    )

    for res in stale_calling:
        try:
            await db.update_reservation(
                res["reservation_id"],
                status=ReservationStatus.FAILED,
            )
            await db.log_state_transition({
                "reservation_id": res["reservation_id"],
                "from_state": ReservationStatus.CALLING,
                "to_state": ReservationStatus.FAILED,
                "trigger": "stale_cleanup",
                "metadata": f"stuck in calling for >{calling_timeout_minutes}min",
                "created_at": datetime.utcnow().isoformat(),
            })
            results["stale_calling"] += 1

            if notifier:
                from src.notifications.notifier import NotificationType
                await notifier.notify(
                    NotificationType.FAILED, res,
                    extra={"reason": "Call did not complete within expected time"},
                )

            logger.info(
                "cleanup.stale_calling",
                reservation_id=res["reservation_id"],
            )
        except Exception as e:
            logger.error(
                "cleanup.stale_calling_error",
                reservation_id=res["reservation_id"],
                error=str(e),
            )

    # 2. Stale 'alternative_proposed' reservations
    stale_alt = await db.list_reservations_by_status(
        ReservationStatus.ALTERNATIVE_PROPOSED,
        older_than_minutes=alt_timeout_hours * 60,
    )

    for res in stale_alt:
        try:
            await db.update_reservation(
                res["reservation_id"],
                status=ReservationStatus.FAILED,
            )
            await db.log_state_transition({
                "reservation_id": res["reservation_id"],
                "from_state": ReservationStatus.ALTERNATIVE_PROPOSED,
                "to_state": ReservationStatus.FAILED,
                "trigger": "alt_timeout_cleanup",
                "metadata": f"alternative not confirmed within {alt_timeout_hours}h",
                "created_at": datetime.utcnow().isoformat(),
            })
            results["stale_alt_proposed"] += 1

            if notifier:
                from src.notifications.notifier import NotificationType
                await notifier.notify(
                    NotificationType.TIMEOUT, res,
                    extra={"proposed_time": res.get("confirmed_time", "unknown")},
                )

            logger.info(
                "cleanup.stale_alt",
                reservation_id=res["reservation_id"],
            )
        except Exception as e:
            logger.error(
                "cleanup.stale_alt_error",
                reservation_id=res["reservation_id"],
                error=str(e),
            )

    logger.info("cleanup.completed", **results)
    return results
