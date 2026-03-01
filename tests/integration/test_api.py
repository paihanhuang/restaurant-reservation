"""Integration tests for the REST API."""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient, ASGITransport

from src.app import create_app


@pytest.fixture
def app():
    """Create a test app with in-memory SQLite."""
    application = create_app()
    # Override DB to use temp file
    import tempfile, os
    from src.providers.sqlite_db import SQLiteDatabase
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    application.state.providers["db"] = SQLiteDatabase(db_path=tmp.name)
    yield application
    os.unlink(tmp.name)


@pytest.fixture
async def client(app):
    """Async test client."""
    # Initialize DB
    await app.state.providers["db"].initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _valid_payload(**overrides) -> dict:
    base = {
        "restaurant_name": "Test Restaurant",
        "restaurant_phone": "+14155551234",
        "date": (date.today() + timedelta(days=1)).isoformat(),
        "preferred_time": "19:30:00",
        "party_size": 4,
        "user_contact": {"phone": "+14155555678", "email": "user@test.com"},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
class TestCreateReservation:
    async def test_create_valid(self, client):
        resp = await client.post("/reservations", json=_valid_payload())
        assert resp.status_code == 201
        data = resp.json()
        assert "reservation_id" in data
        assert data["status"] == "pending"
        assert data["restaurant_name"] == "Test Restaurant"

    async def test_create_with_alt_time(self, client):
        resp = await client.post("/reservations", json=_valid_payload(
            alt_time_window={"start": "18:00:00", "end": "21:00:00"}
        ))
        assert resp.status_code == 201

    async def test_create_past_date_rejected(self, client):
        resp = await client.post("/reservations", json=_valid_payload(date="2020-01-01"))
        assert resp.status_code == 422

    async def test_create_invalid_party_size(self, client):
        resp = await client.post("/reservations", json=_valid_payload(party_size=0))
        assert resp.status_code == 422

    async def test_create_invalid_phone(self, client):
        resp = await client.post("/reservations", json=_valid_payload(
            restaurant_phone="555-1234"
        ))
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestGetReservation:
    async def test_get_existing(self, client):
        # Create first
        create_resp = await client.post("/reservations", json=_valid_payload())
        reservation_id = create_resp.json()["reservation_id"]

        # Get
        resp = await client.get(f"/reservations/{reservation_id}")
        assert resp.status_code == 200
        assert resp.json()["reservation_id"] == reservation_id

    async def test_get_nonexistent(self, client):
        resp = await client.get("/reservations/nonexistent-id")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestCancelReservation:
    async def test_cancel_pending(self, client):
        # Create
        create_resp = await client.post("/reservations", json=_valid_payload())
        reservation_id = create_resp.json()["reservation_id"]

        # Cancel
        resp = await client.post(f"/reservations/{reservation_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

        # Verify persisted
        get_resp = await client.get(f"/reservations/{reservation_id}")
        assert get_resp.json()["status"] == "failed"

    async def test_cancel_nonexistent(self, client):
        resp = await client.post("/reservations/nonexistent-id/cancel")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestGetTranscript:
    async def test_empty_transcript(self, client):
        create_resp = await client.post("/reservations", json=_valid_payload())
        reservation_id = create_resp.json()["reservation_id"]
        resp = await client.get(f"/reservations/{reservation_id}/transcript")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_transcript_nonexistent(self, client):
        resp = await client.get("/reservations/nonexistent/transcript")
        assert resp.status_code == 404
