"""Integration test for readiness endpoint."""

import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport

from src.app import create_app


@pytest.fixture
async def app():
    import os
    os.environ["SQLITE_DB_PATH"] = ":memory:"
    return create_app()


class TestReadiness:
    @pytest.mark.asyncio
    async def test_readiness_with_redis(self, app):
        """Returns 200 when Redis is available."""
        # Create a mock session store that works
        mock_session = AsyncMock()
        mock_session.get.return_value = {"ts": "check"}
        app.state.providers["session"] = mock_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/readiness")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ready"

    @pytest.mark.asyncio
    async def test_readiness_without_redis(self, app):
        """Returns 503 when Redis is unavailable."""
        # Remove session store
        app.state.providers.pop("session", None)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/readiness")
            assert resp.status_code == 503
            assert resp.json()["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_readiness_redis_error(self, app):
        """Returns 503 when Redis operation fails."""
        mock_session = AsyncMock()
        mock_session.set.side_effect = Exception("Connection refused")
        app.state.providers["session"] = mock_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/readiness")
            assert resp.status_code == 503
