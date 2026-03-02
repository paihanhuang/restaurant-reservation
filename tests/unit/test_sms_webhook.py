"""Tests for SMS reply webhook handler."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from src.notifications.sms_webhook import router
from src.models.enums import ReservationStatus


@pytest.fixture
def app():
    """Create test app with SMS webhook router and mocked DB."""
    app = FastAPI()
    app.include_router(router)
    app.state.providers = {"db": AsyncMock()}
    return app


@pytest.fixture
def db(app):
    return app.state.providers["db"]


@pytest.fixture
def sample_reservation():
    return {
        "reservation_id": "res-001",
        "restaurant_name": "Bella Italia",
        "status": "alternative_proposed",
        "user_phone": "+14155551234",
        "date": "2026-03-15",
        "preferred_time": "19:30",
        "party_size": 4,
        "updated_at": "2026-03-01T12:00:00",
    }


class TestSMSWebhookConfirm:
    """Tests for confirming alternatives via SMS reply."""

    @pytest.mark.asyncio
    async def test_yes_confirms_reservation(self, app, db, sample_reservation):
        db.list_reservations_by_status.return_value = [sample_reservation]
        db.get_reservation.return_value = sample_reservation

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/sms/reply",
                data={"Body": "YES", "From": "+14155551234"},
            )

        assert resp.status_code == 200
        assert "Confirmed" in resp.text
        db.update_reservation.assert_called_once_with(
            "res-001", status=ReservationStatus.CONFIRMED.value
        )

    @pytest.mark.asyncio
    async def test_confirm_keyword_variants(self, app, db, sample_reservation):
        """All confirm keywords should work."""
        for kw in ["yes", "y", "confirm", "accept", "ok", "sure", "yep", "yeah"]:
            db.reset_mock()
            db.list_reservations_by_status.return_value = [sample_reservation]
            db.get_reservation.return_value = sample_reservation

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/webhooks/sms/reply",
                    data={"Body": kw, "From": "+14155551234"},
                )

            assert resp.status_code == 200
            assert db.update_reservation.called, f"Keyword '{kw}' should confirm"

    @pytest.mark.asyncio
    async def test_idempotent_confirm(self, app, db, sample_reservation):
        """Confirming an already-confirmed reservation is idempotent."""
        confirmed = {**sample_reservation, "status": "confirmed"}
        db.list_reservations_by_status.return_value = [sample_reservation]
        db.get_reservation.return_value = confirmed

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/sms/reply",
                data={"Body": "yes", "From": "+14155551234"},
            )

        assert resp.status_code == 200
        assert "already confirmed" in resp.text
        db.update_reservation.assert_not_called()


class TestSMSWebhookReject:
    """Tests for rejecting alternatives via SMS reply."""

    @pytest.mark.asyncio
    async def test_no_rejects_reservation(self, app, db, sample_reservation):
        db.list_reservations_by_status.return_value = [sample_reservation]
        db.get_reservation.return_value = sample_reservation

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/sms/reply",
                data={"Body": "NO", "From": "+14155551234"},
            )

        assert resp.status_code == 200
        assert "declined" in resp.text
        db.update_reservation.assert_called_once_with(
            "res-001", status=ReservationStatus.FAILED.value
        )


class TestSMSWebhookEdgeCases:
    """Tests for edge cases in SMS webhook."""

    @pytest.mark.asyncio
    async def test_unknown_phone(self, app, db):
        """Phone with no pending reservations."""
        db.list_reservations_by_status.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/sms/reply",
                data={"Body": "yes", "From": "+19995551234"},
            )

        assert resp.status_code == 200
        assert "No pending" in resp.text

    @pytest.mark.asyncio
    async def test_unrecognized_text(self, app, db, sample_reservation):
        """Garbage text returns help message."""
        db.list_reservations_by_status.return_value = [sample_reservation]

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/sms/reply",
                data={"Body": "what time?", "From": "+14155551234"},
            )

        assert resp.status_code == 200
        assert "Reply YES" in resp.text

    @pytest.mark.asyncio
    async def test_phone_not_matching(self, app, db, sample_reservation):
        """Phone doesn't match any reservation."""
        db.list_reservations_by_status.return_value = [sample_reservation]

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/sms/reply",
                data={"Body": "yes", "From": "+19999999999"},
            )

        assert resp.status_code == 200
        assert "No pending" in resp.text

    @pytest.mark.asyncio
    async def test_twiml_response_format(self, app, db, sample_reservation):
        """Response is valid TwiML XML."""
        db.list_reservations_by_status.return_value = [sample_reservation]
        db.get_reservation.return_value = sample_reservation

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhooks/sms/reply",
                data={"Body": "yes", "From": "+14155551234"},
            )

        assert resp.headers["content-type"] == "application/xml"
        assert "<Response>" in resp.text
        assert "<Message>" in resp.text
