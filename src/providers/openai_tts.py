"""OpenAI TTS provider — streaming speech synthesis."""

from __future__ import annotations

from typing import AsyncIterator
from openai import AsyncOpenAI

from src.providers.base import TTSProvider


class OpenAITTS(TTSProvider):
    """Synthesizes speech using OpenAI TTS API with streaming."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "tts-1",
        voice: str = "alloy",
    ):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.voice = voice

    async def synthesize(self, text: str, output_format: str = "pcm") -> AsyncIterator[bytes]:
        """Convert text to speech, yielding PCM audio chunks.

        Args:
            text: Text to synthesize.
            output_format: Output format (default: pcm for 24kHz 16-bit mono).

        Yields:
            Audio bytes chunks for streaming playback.
        """
        response = await self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text,
            response_format=output_format,
        )

        # Stream the response content
        async for chunk in response.iter_bytes(chunk_size=4096):
            yield chunk
