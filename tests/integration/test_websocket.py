"""Integration tests for WebSocket media stream handler."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, WebSocket

from src.telephony.caller import generate_ws_token
from src.telephony.media_stream import handle_media_stream


@pytest.fixture
def session_store():
    """In-memory session store for testing."""
    store = {}

    class InMemorySession:
        async def get(self, key):
            return store.get(key)
        async def set(self, key, value, ttl=None):
            store[key] = value
        async def delete(self, key):
            store.pop(key, None)

    return InMemorySession()


class TestWebSocketAuth:
    @pytest.mark.asyncio
    async def test_valid_token_accepted(self, session_store):
        """WebSocket with valid token should be accepted."""
        token = await generate_ws_token(session_store, "res-123")
        # Verify token exists in store
        data = await session_store.get(f"ws_token:{token}")
        assert data is not None
        assert data["reservation_id"] == "res-123"

    @pytest.mark.asyncio
    async def test_token_consumed_after_use(self, session_store):
        """Token should be deleted from session store after validation."""
        from src.telephony.caller import validate_ws_token
        token = await generate_ws_token(session_store, "res-456")

        result = await validate_ws_token(session_store, token)
        assert result == "res-456"

        # Token should be consumed
        result2 = await validate_ws_token(session_store, token)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self, session_store):
        """Invalid token should return None."""
        from src.telephony.caller import validate_ws_token
        result = await validate_ws_token(session_store, "bad-token-xyz")
        assert result is None
