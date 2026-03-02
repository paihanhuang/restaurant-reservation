"""State machine — enforces valid reservation status transitions.

All transitions must go through this module. Invalid transitions raise
InvalidStateTransition. Every transition is logged to the database.
"""

from __future__ import annotations

from datetime import datetime

import structlog

from src.models.enums import ReservationStatus
from src.providers.base import Database

logger = structlog.get_logger()


class InvalidStateTransition(Exception):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, from_state: str, to_state: str, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        msg = f"Invalid transition: {from_state} → {to_state}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


# Valid state transitions: from → set of valid destinations
VALID_TRANSITIONS: dict[str, set[str]] = {
    ReservationStatus.PENDING: {
        ReservationStatus.CALLING,
        ReservationStatus.FAILED,      # cancelled before calling
    },
    ReservationStatus.CALLING: {
        ReservationStatus.CONFIRMED,
        ReservationStatus.ALTERNATIVE_PROPOSED,
        ReservationStatus.FAILED,
        ReservationStatus.PENDING,     # retry: back to pending for re-scheduling
    },
    ReservationStatus.ALTERNATIVE_PROPOSED: {
        ReservationStatus.CONFIRMED,   # user accepts alternative
        ReservationStatus.FAILED,      # user rejects or timeout
    },
    ReservationStatus.CONFIRMED: set(),    # terminal
    ReservationStatus.FAILED: set(),       # terminal
}


class StateMachine:
    """Enforces valid status transitions and logs every transition."""

    def __init__(self, db: Database):
        self.db = db

    async def transition(
        self,
        reservation_id: str,
        from_state: str,
        to_state: str,
        trigger: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Attempt a state transition. Validates, logs, and updates the DB.

        Args:
            reservation_id: The reservation being transitioned.
            from_state: Current state (verified against DB).
            to_state: Desired new state.
            trigger: What caused this transition (e.g., "llm_confirm", "user_cancel").
            metadata: Optional data to log with the transition.

        Raises:
            InvalidStateTransition: If the transition is not allowed.
        """
        # Validate transition
        valid_destinations = VALID_TRANSITIONS.get(from_state, set())
        if to_state not in valid_destinations:
            raise InvalidStateTransition(from_state, to_state)

        # Log the transition
        await self.db.log_state_transition({
            "reservation_id": reservation_id,
            "from_state": from_state,
            "to_state": to_state,
            "trigger": trigger,
            "metadata": str(metadata) if metadata else None,
            "created_at": datetime.utcnow().isoformat(),
        })

        # Update reservation status
        await self.db.update_reservation(reservation_id, status=to_state)

        logger.info(
            "state_machine.transitioned",
            reservation_id=reservation_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
        )

    def is_terminal(self, state: str) -> bool:
        """Check if a state is terminal (no outgoing transitions)."""
        return len(VALID_TRANSITIONS.get(state, set())) == 0

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a transition is valid without performing it."""
        return to_state in VALID_TRANSITIONS.get(from_state, set())
