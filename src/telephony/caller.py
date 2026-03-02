"""Twilio caller — initiate outbound calls with WebSocket media streams.

Generates a single-use auth token for WebSocket authentication,
creates TwiML with <Connect><Stream>, and places the call via Twilio SDK.
"""

from __future__ import annotations

import secrets
from datetime import datetime

from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Connect

from configs.telephony import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    PUBLIC_HOST,
    USE_TLS,
    RING_TIMEOUT_SECONDS,
    CALL_TIME_LIMIT_SECONDS,
    WS_TOKEN_TTL_SECONDS,
)
from src.providers.base import SessionStore


async def generate_ws_token(
    session_store: SessionStore,
    reservation_id: str,
) -> str:
    """Generate a short-lived, single-use token for WebSocket authentication.

    Token is stored in Redis with TTL and consumed on first use.
    """
    token = secrets.token_urlsafe(32)
    key = f"ws_token:{token}"
    await session_store.set(
        key,
        {"reservation_id": reservation_id, "created_at": datetime.utcnow().isoformat()},
        ttl=WS_TOKEN_TTL_SECONDS,
    )
    return token


async def validate_ws_token(
    session_store: SessionStore,
    token: str,
) -> str | None:
    """Validate and consume a WebSocket auth token.

    Returns reservation_id if valid, None if invalid or already used.
    Token is deleted after validation (single-use).
    """
    key = f"ws_token:{token}"
    data = await session_store.get(key)
    if data is None:
        return None
    # Consume the token (single-use)
    await session_store.delete(key)
    return data.get("reservation_id")


def build_twiml(reservation_id: str, ws_token: str) -> str:
    """Build TwiML response for connecting to a WebSocket media stream.

    Args:
        reservation_id: ID of the reservation this call is for.
        ws_token: Single-use auth token for WebSocket.

    Returns:
        TwiML XML string.
    """
    response = VoiceResponse()
    connect = Connect()
    protocol = "wss" if USE_TLS else "ws"
    stream_url = f"{protocol}://{PUBLIC_HOST}/ws/media-stream/{reservation_id}?token={ws_token}"
    connect.stream(url=stream_url)
    response.append(connect)
    return str(response)


async def initiate_call(
    restaurant_phone: str,
    reservation_id: str,
    session_store: SessionStore,
) -> dict:
    """Place an outbound call to a restaurant.

    Args:
        restaurant_phone: E.164 phone number of the restaurant.
        reservation_id: ID of the reservation.
        session_store: Session store for token management.

    Returns:
        Dict with call_sid and ws_token.
    """
    # Generate WebSocket auth token
    ws_token = await generate_ws_token(session_store, reservation_id)

    # Build TwiML
    twiml = build_twiml(reservation_id, ws_token)

    # Build status callback URL
    protocol = "https" if USE_TLS else "http"
    status_callback_url = f"{protocol}://{PUBLIC_HOST}/webhooks/twilio/status"

    # Create Twilio client and place call
    client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    call = client.calls.create(
        to=restaurant_phone,
        from_=TWILIO_PHONE_NUMBER,
        twiml=twiml,
        timeout=RING_TIMEOUT_SECONDS,
        time_limit=CALL_TIME_LIMIT_SECONDS,
        machine_detection="DetectMessageEnd",
        async_amd_status_callback=f"{protocol}://{PUBLIC_HOST}/webhooks/twilio/amd-status",
        async_amd_status_callback_method="POST",
        status_callback=status_callback_url,
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )

    return {
        "call_sid": call.sid,
        "ws_token": ws_token,
    }
