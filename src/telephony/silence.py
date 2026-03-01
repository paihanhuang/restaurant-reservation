"""Silence detector — monitors for prolonged silence during calls.

Tracks continuous silence duration and emits events:
  - prompt_check: 30s silence → "Are you still there?"
  - timeout: 120s silence → hang up

Speech resets the silence timer.
"""

from __future__ import annotations

import time as time_module
from enum import StrEnum
from dataclasses import dataclass


class SilenceEvent(StrEnum):
    """Events emitted by the silence detector."""
    NONE = "none"
    PROMPT_CHECK = "prompt_check"     # 30s — ask "are you still there?"
    TIMEOUT = "timeout"               # 120s — hang up


@dataclass
class SilenceConfig:
    """Configuration for silence detection."""
    prompt_threshold_seconds: float = 30.0
    timeout_threshold_seconds: float = 120.0


class SilenceDetector:
    """Monitors silence duration and emits events at configured thresholds."""

    def __init__(self, config: SilenceConfig | None = None):
        self.config = config or SilenceConfig()
        self._silence_start: float | None = None
        self._prompted = False

    def on_speech(self) -> None:
        """Called when speech is detected — resets silence timer."""
        self._silence_start = None
        self._prompted = False

    def on_silence(self) -> SilenceEvent:
        """Called when silence is detected — checks thresholds.

        Returns:
            SilenceEvent indicating what action to take.
        """
        now = time_module.monotonic()

        if self._silence_start is None:
            self._silence_start = now
            return SilenceEvent.NONE

        elapsed = now - self._silence_start

        if elapsed >= self.config.timeout_threshold_seconds:
            return SilenceEvent.TIMEOUT

        if not self._prompted and elapsed >= self.config.prompt_threshold_seconds:
            self._prompted = True
            return SilenceEvent.PROMPT_CHECK

        return SilenceEvent.NONE

    def reset(self) -> None:
        """Reset detector state."""
        self._silence_start = None
        self._prompted = False
