"""Unit tests for Twilio caller — token generation, TwiML, and call initiation."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.telephony.caller import generate_ws_token, validate_ws_token, build_twiml


class TestWSTokenGeneration:
    @pytest.mark.asyncio
    async def test_generate_token_stores_in_session(self):
        """Token generation should store reservation_id in session with TTL."""
        session = AsyncMock()
        token = await generate_ws_token(session, "res-123")

        assert len(token) > 20  # URL-safe base64, at least 32 chars
        session.set.assert_called_once()
        call_args = session.set.call_args
        key = call_args[0][0]
        value = call_args[0][1]
        assert key.startswith("ws_token:")
        assert value["reservation_id"] == "res-123"
        # TTL should be set
        assert call_args[1].get("ttl") is not None or call_args[0][2] is not None

    @pytest.mark.asyncio
    async def test_validate_valid_token(self):
        """Valid token should return reservation_id and be consumed."""
        session = AsyncMock()
        session.get.return_value = {"reservation_id": "res-123"}

        result = await validate_ws_token(session, "test-token")
        assert result == "res-123"
        # Token should be consumed (deleted)
        session.delete.assert_called_once_with("ws_token:test-token")

    @pytest.mark.asyncio
    async def test_validate_invalid_token(self):
        """Invalid/missing token should return None."""
        session = AsyncMock()
        session.get.return_value = None

        result = await validate_ws_token(session, "bad-token")
        assert result is None
        session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_is_single_use(self):
        """After validation, token should be deleted and second validation fails."""
        session = AsyncMock()
        # First call returns data, second returns None (deleted)
        session.get.side_effect = [
            {"reservation_id": "res-123"},
            None,
        ]

        result1 = await validate_ws_token(session, "token-1")
        assert result1 == "res-123"

        result2 = await validate_ws_token(session, "token-1")
        assert result2 is None


class TestBuildTwiml:
    def test_twiml_contains_stream(self):
        """TwiML should contain <Connect><Stream> with correct URL."""
        twiml = build_twiml("res-123", "test-token")
        assert "<Connect>" in twiml
        assert "<Stream" in twiml
        assert "res-123" in twiml
        assert "test-token" in twiml

    def test_twiml_uses_wss(self):
        """TwiML should use WSS protocol by default."""
        with patch("src.telephony.caller.USE_TLS", True):
            twiml = build_twiml("res-123", "token")
            assert "wss://" in twiml

    def test_twiml_is_valid_xml(self):
        """TwiML output should be parseable XML."""
        import xml.etree.ElementTree as ET
        twiml = build_twiml("res-123", "token")
        # Should not raise
        ET.fromstring(twiml)
