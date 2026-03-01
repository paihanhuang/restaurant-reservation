"""Transcript turn data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TranscriptTurn:
    """A single turn in a conversation transcript."""

    reservation_id: str
    call_sid: str
    turn_number: int
    role: str  # "restaurant" or "agent"
    text: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "reservation_id": self.reservation_id,
            "call_sid": self.call_sid,
            "turn_number": self.turn_number,
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp,
        }
