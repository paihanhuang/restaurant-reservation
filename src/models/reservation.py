"""Reservation data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, datetime
from uuid import uuid4

from src.models.enums import ReservationStatus


@dataclass
class Reservation:
    """Represents a reservation request and its current state."""

    restaurant_name: str
    restaurant_phone: str
    date: date
    preferred_time: time
    party_size: int
    user_id: str
    user_phone: str
    user_email: str

    # Optional fields
    alt_time_start: time | None = None
    alt_time_end: time | None = None
    special_requests: str | None = None

    # System-managed fields
    reservation_id: str = field(default_factory=lambda: str(uuid4()))
    status: ReservationStatus = ReservationStatus.PENDING
    call_attempts: int = 0
    call_sid: str | None = None
    confirmed_time: time | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        """Serialize to dict for DB storage."""
        return {
            "reservation_id": self.reservation_id,
            "user_id": self.user_id,
            "restaurant_name": self.restaurant_name,
            "restaurant_phone": self.restaurant_phone,
            "date": self.date.isoformat(),
            "preferred_time": self.preferred_time.isoformat(),
            "alt_time_start": self.alt_time_start.isoformat() if self.alt_time_start else None,
            "alt_time_end": self.alt_time_end.isoformat() if self.alt_time_end else None,
            "party_size": self.party_size,
            "special_requests": self.special_requests,
            "status": self.status.value,
            "call_attempts": self.call_attempts,
            "call_sid": self.call_sid,
            "confirmed_time": self.confirmed_time.isoformat() if self.confirmed_time else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Reservation:
        """Deserialize from DB row dict."""
        return cls(
            reservation_id=data["reservation_id"],
            user_id=data["user_id"],
            restaurant_name=data["restaurant_name"],
            restaurant_phone=data["restaurant_phone"],
            date=date.fromisoformat(data["date"]),
            preferred_time=time.fromisoformat(data["preferred_time"]),
            alt_time_start=time.fromisoformat(data["alt_time_start"]) if data.get("alt_time_start") else None,
            alt_time_end=time.fromisoformat(data["alt_time_end"]) if data.get("alt_time_end") else None,
            party_size=data["party_size"],
            special_requests=data.get("special_requests"),
            status=ReservationStatus(data["status"]),
            call_attempts=data.get("call_attempts", 0),
            call_sid=data.get("call_sid"),
            confirmed_time=time.fromisoformat(data["confirmed_time"]) if data.get("confirmed_time") else None,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            user_phone=data.get("user_phone", ""),
            user_email=data.get("user_email", ""),
        )
