"""Voice Activity Detection — buffers audio and yields complete utterances.

Segments incoming audio into speech utterances based on energy thresholds.
When a period of silence is detected after speech, the accumulated speech
buffer is yielded as a complete utterance for STT processing.
"""

from __future__ import annotations

import audioop
import struct
from enum import StrEnum
from dataclasses import dataclass, field


class VADState(StrEnum):
    """Current state of the VAD processor."""
    WAITING = "waiting"      # No speech detected yet
    SPEECH = "speech"        # Currently in a speech segment
    TRAILING = "trailing"    # Speech ended, waiting for silence confirmation


@dataclass
class VADConfig:
    """Configuration for voice activity detection."""
    energy_threshold: int = 300         # RMS energy threshold for speech
    min_speech_ms: int = 250            # Minimum speech duration to emit (ms)
    silence_ms: int = 700               # Silence duration to end utterance (ms)
    sample_rate: int = 8000             # Audio sample rate (Hz)
    sample_width: int = 2               # Bytes per sample (16-bit = 2)
    chunk_ms: int = 20                  # Expected chunk duration (ms)


class VADProcessor:
    """Buffers audio chunks and detects end-of-speech boundaries.

    Usage:
        vad = VADProcessor()
        for chunk in audio_stream:
            utterance = vad.process(chunk)
            if utterance is not None:
                transcript = await stt.transcribe(utterance)
    """

    def __init__(self, config: VADConfig | None = None):
        self.config = config or VADConfig()
        self.state = VADState.WAITING
        self._speech_buffer = bytearray()
        self._silence_frames = 0
        self._speech_frames = 0

        # Pre-compute frame counts from ms
        frames_per_sec = self.config.sample_rate / (self.config.chunk_ms * self.config.sample_rate * self.config.sample_width / 1000 / (self.config.sample_width))
        self._min_speech_frames = max(1, self.config.min_speech_ms // self.config.chunk_ms)
        self._silence_frames_threshold = max(1, self.config.silence_ms // self.config.chunk_ms)

    def _is_speech(self, chunk: bytes) -> bool:
        """Check if an audio chunk contains speech based on RMS energy."""
        if len(chunk) < self.config.sample_width:
            return False
        try:
            rms = audioop.rms(chunk, self.config.sample_width)
            return rms >= self.config.energy_threshold
        except audioop.error:
            return False

    def process(self, chunk: bytes) -> bytes | None:
        """Process an audio chunk and return a complete utterance if detected.

        Args:
            chunk: Raw PCM audio data (one chunk, typically 20ms).

        Returns:
            Complete utterance bytes if end-of-speech detected, None otherwise.
        """
        is_speech = self._is_speech(chunk)

        if self.state == VADState.WAITING:
            if is_speech:
                self.state = VADState.SPEECH
                self._speech_buffer = bytearray(chunk)
                self._speech_frames = 1
                self._silence_frames = 0
            return None

        elif self.state == VADState.SPEECH:
            self._speech_buffer.extend(chunk)
            if is_speech:
                self._speech_frames += 1
                self._silence_frames = 0
            else:
                self._silence_frames += 1
                if self._silence_frames >= self._silence_frames_threshold:
                    self.state = VADState.WAITING
                    if self._speech_frames >= self._min_speech_frames:
                        utterance = bytes(self._speech_buffer)
                        self._speech_buffer = bytearray()
                        self._speech_frames = 0
                        self._silence_frames = 0
                        return utterance
                    else:
                        # Too short — discard
                        self._speech_buffer = bytearray()
                        self._speech_frames = 0
                        self._silence_frames = 0
                        return None
            return None

        return None

    def reset(self) -> None:
        """Reset VAD state, discarding any buffered audio."""
        self.state = VADState.WAITING
        self._speech_buffer = bytearray()
        self._speech_frames = 0
        self._silence_frames = 0

    def flush(self) -> bytes | None:
        """Force-emit any buffered speech (e.g., at end of call).

        Returns:
            Buffered speech bytes if any, None otherwise.
        """
        if self._speech_frames >= self._min_speech_frames and len(self._speech_buffer) > 0:
            utterance = bytes(self._speech_buffer)
            self.reset()
            return utterance
        self.reset()
        return None
