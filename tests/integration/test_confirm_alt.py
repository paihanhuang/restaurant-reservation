"""Integration test for confirm-alternative flow."""

import pytest
from httpx import AsyncClient, ASGITransport

from src.app import create_app
from src.models.enums import ReservationStatus


@pytest.fixture
async def app_and_client():
    """Create app with in-memory SQLite."""
    import os
    os.environ["SQLITE_DB_PATH"] = ":memory:"
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield app, client


class TestConfirmAlternativeFlow:
    @pytest.mark.asyncio
    async def test_full_alt_flow(self, app_and_client):
        """reservation → alt_proposed → confirm-alt → confirmed."""
        app, client = app_and_client

        # 1. Create reservation
        from datetime import date, timedelta
        future_date = (date.today() + timedelta(days=30)).isoformat()
        resp = await client.post("/reservations", json={
            "restaurant_name": "Test Bistro",
            "restaurant_phone": "+14155551234",
            "date": future_date,
            "preferred_time": "19:30:00",
            "party_size": 4,
            "user_contact": {"phone": "+14155559999"},
        })
        assert resp.status_code == 201
        res_id = resp.json()["reservation_id"]

        # 2. Manually transition to alternative_proposed (simulate call result)
        db = app.state.providers["db"]
        await db.update_reservation(res_id, status=ReservationStatus.ALTERNATIVE_PROPOSED.value)

        # 3. Confirm alternative
        resp = await client.post(f"/reservations/{res_id}/confirm-alternative")
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_confirm_alt_wrong_state(self, app_and_client):
        """Can't confirm alt from pending state."""
        app, client = app_and_client
        from datetime import date, timedelta
        future_date = (date.today() + timedelta(days=30)).isoformat()

        resp = await client.post("/reservations", json={
            "restaurant_name": "Test",
            "restaurant_phone": "+14155551234",
            "date": future_date,
            "preferred_time": "19:30:00",
            "party_size": 2,
            "user_contact": {"phone": "+14155559999"},
        })
        res_id = resp.json()["reservation_id"]

        resp = await client.post(f"/reservations/{res_id}/confirm-alternative")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_reject_alternative(self, app_and_client):
        """reservation → alt_proposed → reject → failed."""
        app, client = app_and_client
        from datetime import date, timedelta
        future_date = (date.today() + timedelta(days=30)).isoformat()

        resp = await client.post("/reservations", json={
            "restaurant_name": "Test",
            "restaurant_phone": "+14155551234",
            "date": future_date,
            "preferred_time": "19:30:00",
            "party_size": 3,
            "user_contact": {"phone": "+14155559999"},
        })
        res_id = resp.json()["reservation_id"]

        db = app.state.providers["db"]
        await db.update_reservation(res_id, status=ReservationStatus.ALTERNATIVE_PROPOSED.value)

        resp = await client.post(f"/reservations/{res_id}/reject-alternative")
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
