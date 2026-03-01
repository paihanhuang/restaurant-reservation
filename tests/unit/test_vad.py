"""Unit tests for Voice Activity Detection."""

import struct
import math
import pytest

from src.telephony.vad import VADProcessor, VADConfig, VADState


def _generate_sine_chunk(freq: int, duration_ms: int, sample_rate: int = 8000, amplitude: int = 8000) -> bytes:
    """Generate a PCM sine wave chunk."""
    n_samples = sample_rate * duration_ms // 1000
    samples = []
    for i in range(n_samples):
        sample = int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate))
        samples.append(sample)
    return struct.pack(f"<{n_samples}h", *samples)


def _generate_silence_chunk(duration_ms: int, sample_rate: int = 8000) -> bytes:
    """Generate a silent PCM chunk."""
    n_samples = sample_rate * duration_ms // 1000
    return b"\x00\x00" * n_samples


class TestVADProcessor:
    def _make_vad(self, **overrides) -> VADProcessor:
        """Create VAD with test-friendly defaults."""
        defaults = dict(
            energy_threshold=200,
            min_speech_ms=60,      # 3 chunks at 20ms
            silence_ms=60,         # 3 chunks of silence to end
            sample_rate=8000,
            chunk_ms=20,
        )
        defaults.update(overrides)
        cfg = VADConfig(**defaults)
        return VADProcessor(config=cfg)

    def test_initial_state_is_waiting(self):
        vad = self._make_vad()
        assert vad.state == VADState.WAITING

    def test_silence_only_produces_nothing(self):
        vad = self._make_vad()
        silence = _generate_silence_chunk(20)
        for _ in range(50):
            result = vad.process(silence)
            assert result is None
        assert vad.state == VADState.WAITING

    def test_speech_then_silence_produces_utterance(self):
        vad = self._make_vad()

        # Feed speech chunks (above energy threshold)
        speech = _generate_sine_chunk(440, 20, amplitude=8000)
        for _ in range(10):  # 200ms of speech
            result = vad.process(speech)
            # Should not emit yet (still speaking)

        # Feed silence chunks to trigger end-of-utterance
        silence = _generate_silence_chunk(20)
        utterance = None
        for _ in range(10):  # 200ms of silence (well above 60ms threshold)
            result = vad.process(silence)
            if result is not None:
                utterance = result
                break

        assert utterance is not None
        assert len(utterance) > 0

    def test_short_speech_discarded(self):
        """Speech shorter than min_speech_ms should be discarded."""
        vad = self._make_vad(min_speech_ms=100)  # Require 5 chunks (100ms)

        # Only 2 chunks of speech (40ms < 100ms min)
        speech = _generate_sine_chunk(440, 20, amplitude=8000)
        vad.process(speech)
        vad.process(speech)

        # Silence to trigger evaluation
        silence = _generate_silence_chunk(20)
        utterance = None
        for _ in range(10):
            result = vad.process(silence)
            if result is not None:
                utterance = result
                break

        assert utterance is None  # Too short, discarded

    def test_reset_clears_state(self):
        vad = self._make_vad()
        speech = _generate_sine_chunk(440, 20, amplitude=8000)
        vad.process(speech)
        assert vad.state == VADState.SPEECH

        vad.reset()
        assert vad.state == VADState.WAITING

    def test_flush_emits_buffered_speech(self):
        vad = self._make_vad()
        speech = _generate_sine_chunk(440, 20, amplitude=8000)

        # Buffer enough speech
        for _ in range(5):
            vad.process(speech)

        # Flush without waiting for silence
        utterance = vad.flush()
        assert utterance is not None
        assert len(utterance) > 0
        assert vad.state == VADState.WAITING

    def test_flush_with_no_speech_returns_none(self):
        vad = self._make_vad()
        assert vad.flush() is None
