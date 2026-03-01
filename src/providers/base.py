"""Provider interfaces — abstract base classes for all external dependencies.

Every external dependency (STT, TTS, LLM, session store, database) is
abstracted behind a provider interface. Default providers can be swapped
without touching business logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, time
from typing import AsyncIterator
from dataclasses import dataclass


# --- Data types returned by providers ---

@dataclass
class TranscriptResult:
    """Result from STT transcription."""
    text: str
    confidence: float | None = None


@dataclass
class LLMResponse:
    """Result from LLM chat completion."""
    speech_text: str | None = None
    action: str | None = None
    params: dict | None = None
    raw_response: dict | None = None


# --- Provider Interfaces ---

class STTProvider(ABC):
    """Transcribes a complete utterance (post-VAD). NOT a streaming interface."""

    @abstractmethod
    async def transcribe(self, audio: bytes, format: str = "wav") -> TranscriptResult:
        """Transcribe a complete audio utterance to text."""
        ...


class TTSProvider(ABC):
    """Synthesizes speech from text. Returns audio chunks for streaming playback."""

    @abstractmethod
    async def synthesize(self, text: str, output_format: str = "pcm") -> AsyncIterator[bytes]:
        """Convert text to speech audio, yielding chunks for streaming."""
        ...


class LLMProvider(ABC):
    """Chat completion with optional function calling."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        functions: list[dict] | None = None,
    ) -> LLMResponse:
        """Send messages to LLM and get a response, optionally with function calls."""
        ...


class SessionStore(ABC):
    """Key-value session store for ephemeral call state."""

    @abstractmethod
    async def get(self, key: str) -> dict | None:
        """Retrieve session data by key. Returns None if not found."""
        ...

    @abstractmethod
    async def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        """Store session data with optional TTL in seconds."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete session data by key."""
        ...


class Database(ABC):
    """Persistent database for reservations, call logs, transcripts."""

    @abstractmethod
    async def initialize(self) -> None:
        """Run migrations / create tables if needed."""
        ...

    @abstractmethod
    async def create_reservation(self, reservation: dict) -> None:
        """Insert a new reservation record."""
        ...

    @abstractmethod
    async def get_reservation(self, reservation_id: str) -> dict | None:
        """Retrieve a reservation by ID. Returns None if not found."""
        ...

    @abstractmethod
    async def update_reservation(self, reservation_id: str, **fields) -> None:
        """Update specific fields on a reservation."""
        ...

    @abstractmethod
    async def list_reservations_by_status(
        self, status: str, older_than_minutes: int | None = None
    ) -> list[dict]:
        """List reservations with a given status, optionally filtered by age."""
        ...

    @abstractmethod
    async def log_state_transition(self, transition: dict) -> None:
        """Log a state machine transition."""
        ...

    @abstractmethod
    async def log_call(self, call_log: dict) -> None:
        """Log a call attempt."""
        ...

    @abstractmethod
    async def append_transcript_turn(
        self, reservation_id: str, call_sid: str, turn: dict
    ) -> None:
        """Append a single conversation turn to the transcript."""
        ...

    @abstractmethod
    async def get_transcript(self, reservation_id: str) -> list[dict]:
        """Retrieve all transcript turns for a reservation, ordered by turn number."""
        ...
