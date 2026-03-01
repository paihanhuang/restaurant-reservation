"""Audio codec — µ-law ↔ PCM conversion and resampling.

Twilio sends audio as µ-law 8kHz mono (base64-encoded in Media Stream messages).
Whisper STT expects 16kHz PCM (signed 16-bit little-endian).
This module handles the bidirectional conversion.

Flow:
  Inbound (Twilio → STT):  µ-law 8kHz → PCM 8kHz → PCM 16kHz
  Outbound (TTS → Twilio): PCM 16kHz → PCM 8kHz → µ-law 8kHz
"""

from __future__ import annotations

import audioop
import struct


class AudioCodec:
    """Bidirectional audio format converter for the telephony pipeline."""

    # Twilio Media Stream: µ-law, 8kHz, mono
    TWILIO_SAMPLE_RATE = 8000
    TWILIO_SAMPLE_WIDTH = 2  # 16-bit after decoding from µ-law

    # Whisper STT: PCM, 16kHz, mono, 16-bit signed LE
    STT_SAMPLE_RATE = 16000
    STT_SAMPLE_WIDTH = 2

    @staticmethod
    def ulaw_to_pcm(ulaw_bytes: bytes) -> bytes:
        """Decode µ-law to 16-bit PCM at original sample rate (8kHz).

        Args:
            ulaw_bytes: Raw µ-law encoded audio bytes.

        Returns:
            PCM audio bytes (signed 16-bit LE, 8kHz mono).
        """
        return audioop.ulaw2lin(ulaw_bytes, 2)

    @staticmethod
    def pcm_to_ulaw(pcm_bytes: bytes) -> bytes:
        """Encode 16-bit PCM to µ-law.

        Args:
            pcm_bytes: PCM audio (signed 16-bit LE).

        Returns:
            µ-law encoded audio bytes.
        """
        return audioop.lin2ulaw(pcm_bytes, 2)

    @staticmethod
    def resample(pcm_bytes: bytes, from_rate: int, to_rate: int) -> bytes:
        """Resample PCM audio between sample rates.

        Args:
            pcm_bytes: PCM audio (signed 16-bit LE).
            from_rate: Source sample rate in Hz.
            to_rate: Target sample rate in Hz.

        Returns:
            Resampled PCM audio bytes.
        """
        if from_rate == to_rate:
            return pcm_bytes
        # audioop.ratecv: (fragment, width, nchannels, inrate, outrate, state)
        converted, _ = audioop.ratecv(pcm_bytes, 2, 1, from_rate, to_rate, None)
        return converted

    @classmethod
    def twilio_to_stt(cls, ulaw_bytes: bytes) -> bytes:
        """Full inbound conversion: µ-law 8kHz → PCM 16kHz.

        This is the pipeline for preparing Twilio audio for STT (Whisper).
        """
        pcm_8k = cls.ulaw_to_pcm(ulaw_bytes)
        pcm_16k = cls.resample(pcm_8k, cls.TWILIO_SAMPLE_RATE, cls.STT_SAMPLE_RATE)
        return pcm_16k

    @classmethod
    def stt_to_twilio(cls, pcm_16k_bytes: bytes) -> bytes:
        """Full outbound conversion: PCM 16kHz → µ-law 8kHz.

        This is the pipeline for sending TTS audio back to Twilio.
        """
        pcm_8k = cls.resample(pcm_16k_bytes, cls.STT_SAMPLE_RATE, cls.TWILIO_SAMPLE_RATE)
        ulaw = cls.pcm_to_ulaw(pcm_8k)
        return ulaw
