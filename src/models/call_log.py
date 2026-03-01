"""Call log data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.models.enums import CallStatus


@dataclass
class CallLog:
    """Represents a single call attempt."""

    reservation_id: str
    call_sid: str
    attempt_number: int
    status: CallStatus

    duration_seconds: int | None = None
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_at: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "reservation_id": self.reservation_id,
            "call_sid": self.call_sid,
            "attempt_number": self.attempt_number,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error_message": self.error_message,
        }
