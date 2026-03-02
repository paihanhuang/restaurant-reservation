"""Integration tests for dashboard routes."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from src.dashboard.routes import router


@pytest.fixture
def app():
    """Create test app with dashboard router and mocked DB."""
    app = FastAPI()
    app.include_router(router)
    app.state.providers = {"db": AsyncMock()}
    return app


@pytest.fixture
def db(app):
    return app.state.providers["db"]


class TestDashboardPage:
    """Tests for the dashboard HTML page."""

    @pytest.mark.asyncio
    async def test_dashboard_serves_html(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/dashboard")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Reservation Dashboard" in resp.text

    @pytest.mark.asyncio
    async def test_dashboard_has_sse_connection(self, app):
        """Dashboard HTML includes EventSource setup."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/dashboard")

        assert "EventSource" in resp.text
        assert "/events/" in resp.text


class TestDashboardAPI:
    """Tests for the dashboard JSON API."""

    @pytest.mark.asyncio
    async def test_list_reservations_empty(self, app, db):
        db.list_all_reservations.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/dashboard/reservations")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_reservations_returns_data(self, app, db):
        db.list_all_reservations.return_value = [
            {
                "reservation_id": "res-001",
                "restaurant_name": "Bella Italia",
                "date": "2026-03-15",
                "preferred_time": "19:30",
                "party_size": 4,
                "status": "confirmed",
            },
            {
                "reservation_id": "res-002",
                "restaurant_name": "Sushi Place",
                "date": "2026-03-16",
                "preferred_time": "20:00",
                "party_size": 2,
                "status": "pending",
            },
        ]

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/dashboard/reservations")

        data = resp.json()
        assert len(data) == 2
        assert data[0]["restaurant_name"] == "Bella Italia"
        assert data[1]["status"] == "pending"


class TestSSEEndpoint:
    """Tests for the SSE streaming endpoint."""

    @pytest.mark.asyncio
    async def test_sse_content_type(self, app):
        """SSE endpoint returns text/event-stream."""
        import asyncio

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            try:
                async with asyncio.timeout(1.0):
                    async with client.stream("GET", "/events/test-user") as resp:
                        assert resp.status_code == 200
                        assert "text/event-stream" in resp.headers["content-type"]
            except (asyncio.TimeoutError, TimeoutError):
                pass  # Expected — SSE streams indefinitely
