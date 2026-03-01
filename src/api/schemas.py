"""Pydantic schemas for API request/response validation."""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.enums import ReservationStatus


class TimeWindow(BaseModel):
    """Single contiguous time range for alternative negotiation.
    None means 'preferred time only, no alternatives accepted.'
    """
    start: time
    end: time

    @model_validator(mode="after")
    def validate_range(self):
        if self.start >= self.end:
            raise ValueError("alt_time_window.start must be before end")
        return self


class UserContact(BaseModel):
    """User contact information for notifications."""
    phone: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$", description="E.164 phone number")
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")


class ReservationRequest(BaseModel):
    """Request payload for creating a new reservation."""
    restaurant_name: str = Field(..., min_length=1, max_length=200)
    restaurant_phone: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$", description="E.164 format")
    date: date
    preferred_time: time
    alt_time_window: TimeWindow | None = None
    party_size: int = Field(..., ge=1, le=20)
    special_requests: str | None = Field(None, max_length=500)
    user_contact: UserContact

    @field_validator("date")
    @classmethod
    def date_must_be_future(cls, v: date) -> date:
        from datetime import date as date_cls
        if v < date_cls.today():
            raise ValueError("Reservation date must be today or in the future")
        return v


class TranscriptTurnResponse(BaseModel):
    """A single turn in the conversation."""
    turn_number: int
    role: str
    text: str
    timestamp: str


class ReservationResponse(BaseModel):
    """Response payload for reservation status."""
    reservation_id: str
    status: ReservationStatus
    restaurant_name: str
    date: date
    preferred_time: time
    party_size: int
    confirmed_time: time | None = None
    call_attempts: int = 0
    transcript: list[TranscriptTurnResponse] | None = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
