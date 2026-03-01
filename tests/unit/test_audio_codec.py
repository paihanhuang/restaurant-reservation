"""Unit tests for audio codec — µ-law ↔ PCM conversion and resampling."""

import struct
import math
import pytest

from src.telephony.audio_codec import AudioCodec


class TestUlawPcmConversion:
    """Test µ-law ↔ PCM round-trip fidelity."""

    def test_ulaw_to_pcm_produces_output(self):
        """Basic smoke test: decoding µ-law should produce PCM bytes."""
        # 100 samples of µ-law silence (0xFF = zero crossing in µ-law)
        ulaw_data = b"\xff" * 100
        pcm = AudioCodec.ulaw_to_pcm(ulaw_data)
        # Each µ-law byte expands to 2 bytes (16-bit PCM)
        assert len(pcm) == 200

    def test_pcm_to_ulaw_produces_output(self):
        """Encoding PCM should produce µ-law bytes."""
        # 100 samples of PCM silence (16-bit LE zeros)
        pcm_data = b"\x00\x00" * 100
        ulaw = AudioCodec.pcm_to_ulaw(pcm_data)
        assert len(ulaw) == 100

    def test_round_trip_near_fidelity(self):
        """µ-law → PCM → µ-law should be lossy but close.

        µ-law is a lossy companding algorithm, so round-trip won't be
        bit-exact, but the decoded signal should be very close.
        """
        # Generate a simple sine wave in PCM
        sample_rate = 8000
        duration_ms = 50
        freq = 440  # Hz
        n_samples = sample_rate * duration_ms // 1000

        pcm_samples = []
        for i in range(n_samples):
            sample = int(16000 * math.sin(2 * math.pi * freq * i / sample_rate))
            pcm_samples.append(sample)

        pcm_original = struct.pack(f"<{n_samples}h", *pcm_samples)

        # Round trip: PCM → µ-law → PCM
        ulaw = AudioCodec.pcm_to_ulaw(pcm_original)
        pcm_recovered = AudioCodec.ulaw_to_pcm(ulaw)

        # Unpack and compare
        original = struct.unpack(f"<{n_samples}h", pcm_original)
        recovered = struct.unpack(f"<{n_samples}h", pcm_recovered)

        # Allow ±2% error per sample (µ-law is 8-bit companding)
        max_error = max(abs(o - r) for o, r in zip(original, recovered))
        # µ-law quantization error should be small for mid-range signals
        assert max_error < 1000, f"Max round-trip error too large: {max_error}"


class TestResampling:
    """Test sample rate conversion."""

    def test_upsample_8k_to_16k(self):
        """Upsampling 8kHz to 16kHz should roughly double the byte count."""
        n_samples = 800  # 100ms at 8kHz
        pcm_8k = b"\x00\x00" * n_samples
        pcm_16k = AudioCodec.resample(pcm_8k, 8000, 16000)
        # Should be approximately double
        expected_bytes = n_samples * 2 * 2  # 2x samples, 2 bytes each
        assert abs(len(pcm_16k) - expected_bytes) <= 4  # Allow ±2 samples tolerance

    def test_downsample_16k_to_8k(self):
        """Downsampling 16kHz to 8kHz should roughly halve the byte count."""
        n_samples = 1600  # 100ms at 16kHz
        pcm_16k = b"\x00\x00" * n_samples
        pcm_8k = AudioCodec.resample(pcm_16k, 16000, 8000)
        expected_bytes = n_samples // 2 * 2  # half samples, 2 bytes each
        assert abs(len(pcm_8k) - expected_bytes) <= 4

    def test_same_rate_is_identity(self):
        """Resampling at the same rate should return identical bytes."""
        pcm = b"\x01\x02" * 100
        result = AudioCodec.resample(pcm, 16000, 16000)
        assert result == pcm


class TestFullPipeline:
    """Test end-to-end twilio_to_stt and stt_to_twilio."""

    def test_twilio_to_stt_output_size(self):
        """µ-law 8kHz → PCM 16kHz: output should be ~4x input size."""
        # 100ms of µ-law at 8kHz = 800 bytes
        ulaw_data = b"\xff" * 800
        pcm_16k = AudioCodec.twilio_to_stt(ulaw_data)
        # 800 µ-law bytes → 800 PCM samples at 8kHz → 1600 samples at 16kHz → 3200 bytes
        assert abs(len(pcm_16k) - 3200) <= 8

    def test_stt_to_twilio_output_size(self):
        """PCM 16kHz → µ-law 8kHz: output should be ~1/4 input size."""
        # 100ms of PCM at 16kHz = 1600 samples = 3200 bytes
        pcm_16k = b"\x00\x00" * 1600
        ulaw = AudioCodec.stt_to_twilio(pcm_16k)
        # 3200 bytes → 1600 samples → 800 samples at 8kHz → 800 µ-law bytes
        assert abs(len(ulaw) - 800) <= 4

    def test_full_round_trip(self):
        """twilio_to_stt → stt_to_twilio should produce same-length output as input."""
        ulaw_input = b"\xff" * 800
        pcm_16k = AudioCodec.twilio_to_stt(ulaw_input)
        ulaw_output = AudioCodec.stt_to_twilio(pcm_16k)
        # Lengths should be approximately equal
        assert abs(len(ulaw_output) - len(ulaw_input)) <= 4
