"""OpenAI STT provider — Whisper transcription."""

from __future__ import annotations

import io
import wave
from openai import AsyncOpenAI

from src.providers.base import STTProvider, TranscriptResult


class OpenAISTT(STTProvider):
    """Transcribes utterances using OpenAI Whisper API."""

    def __init__(self, api_key: str | None = None, model: str = "whisper-1"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def transcribe(self, audio: bytes, format: str = "wav") -> TranscriptResult:
        """Transcribe PCM audio to text using Whisper.

        Args:
            audio: Raw PCM audio (16-bit signed LE, 16kHz mono).
            format: Audio format hint (default: wav).

        Returns:
            TranscriptResult with transcribed text.
        """
        # Wrap raw PCM in a WAV container for the API
        wav_buffer = self._pcm_to_wav(audio)

        response = await self.client.audio.transcriptions.create(
            model=self.model,
            file=("audio.wav", wav_buffer, "audio/wav"),
            response_format="text",
        )

        return TranscriptResult(text=response.strip())

    @staticmethod
    def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
        """Wrap raw PCM bytes in a WAV container."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()
