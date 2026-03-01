"""WebSocket media stream handler.

Handles bidirectional audio between Twilio and the conversation pipeline.
Authenticates WebSocket connections via single-use tokens.
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from configs.app import CALL_DURATION_LIMIT_SECONDS
from src.telephony.audio_codec import AudioCodec
from src.telephony.vad import VADProcessor, VADConfig
from src.telephony.silence import SilenceDetector, SilenceConfig, SilenceEvent
from src.telephony.caller import validate_ws_token
from src.providers.base import SessionStore

logger = structlog.get_logger()


async def handle_media_stream(
    websocket: WebSocket,
    reservation_id: str,
    token: str,
    session_store: SessionStore,
) -> None:
    """Handle a Twilio Media Stream WebSocket connection.

    Flow:
    1. Validate auth token
    2. Accept WebSocket
    3. On 'start' event: initialize pipeline, send greeting
    4. On 'media' event: decode → VAD → (on utterance) → callback
    5. On 'stop' event: cleanup

    This handler does NOT currently wire to STT/LLM/TTS — that happens in M3.
    It establishes the audio pipeline infrastructure (codec, VAD, silence).
    """
    # Validate WebSocket auth token
    validated_reservation_id = await validate_ws_token(session_store, token)
    if validated_reservation_id is None or validated_reservation_id != reservation_id:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await websocket.accept()
    logger.info("media_stream.connected", reservation_id=reservation_id)

    # Initialize audio pipeline components
    codec = AudioCodec()
    vad = VADProcessor(VADConfig())
    silence_detector = SilenceDetector(SilenceConfig())

    call_sid: str | None = None
    stream_sid: str | None = None

    try:
        async with asyncio.timeout(CALL_DURATION_LIMIT_SECONDS):
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                event = message.get("event")

                if event == "start":
                    call_sid = message.get("start", {}).get("callSid")
                    stream_sid = message.get("start", {}).get("streamSid")
                    logger.info(
                        "media_stream.start",
                        reservation_id=reservation_id,
                        call_sid=call_sid,
                        stream_sid=stream_sid,
                    )
                    # M3 will add greeting generation here

                elif event == "media":
                    # Decode incoming audio
                    payload = message.get("media", {}).get("payload", "")
                    ulaw_bytes = base64.b64decode(payload)

                    # Convert to PCM for VAD
                    pcm_8k = codec.ulaw_to_pcm(ulaw_bytes)

                    # Check for speech/silence
                    utterance = vad.process(pcm_8k)

                    if utterance is not None:
                        # Speech detected — reset silence detector
                        silence_detector.on_speech()
                        # M3 will add: STT → LLM → TTS pipeline here
                        logger.debug(
                            "media_stream.utterance_detected",
                            reservation_id=reservation_id,
                            utterance_bytes=len(utterance),
                        )
                    else:
                        # Check silence thresholds
                        silence_event = silence_detector.on_silence()
                        if silence_event == SilenceEvent.PROMPT_CHECK:
                            logger.info("media_stream.silence_prompt", reservation_id=reservation_id)
                            # M3 will add: TTS "Are you still there?" here
                        elif silence_event == SilenceEvent.TIMEOUT:
                            logger.warning("media_stream.silence_timeout", reservation_id=reservation_id)
                            break  # End call

                elif event == "stop":
                    logger.info("media_stream.stop", reservation_id=reservation_id)
                    break

    except asyncio.TimeoutError:
        logger.warning("media_stream.call_timeout", reservation_id=reservation_id)
    except WebSocketDisconnect:
        logger.info("media_stream.disconnected", reservation_id=reservation_id)
    except Exception as e:
        logger.error("media_stream.error", reservation_id=reservation_id, error=str(e))
    finally:
        # Flush any remaining VAD buffer
        remaining = vad.flush()
        if remaining:
            logger.debug("media_stream.flush_remaining", reservation_id=reservation_id)
        # M5 will add: conversation.finalize() here
        logger.info("media_stream.cleanup", reservation_id=reservation_id)
