"""Enums for reservation and call status."""

from enum import StrEnum


class ReservationStatus(StrEnum):
    """Lifecycle states for a reservation."""
    PENDING = "pending"
    CALLING = "calling"
    IN_CONVERSATION = "in_conversation"
    ALTERNATIVE_PROPOSED = "alternative_proposed"
    CONFIRMED = "confirmed"
    RETRY = "retry"
    FAILED = "failed"


class CallStatus(StrEnum):
    """Status of an individual call attempt."""
    INITIATED = "initiated"
    RINGING = "ringing"
    ANSWERED = "answered"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    COMPLETED = "completed"
    VOICEMAIL = "voicemail"
