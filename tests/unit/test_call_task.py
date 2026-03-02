"""Unit tests for call task — retry logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.tasks.call_task import place_reservation_call, CallTaskError


def _make_reservation(**overrides):
    base = {
        "reservation_id": "res-test-001",
        "restaurant_name": "Test Bistro",
        "restaurant_phone": "+14155551234",
        "status": "pending",
    }
    base.update(overrides)
    return base


@pytest.fixture
def db():
    mock = AsyncMock()
    mock.get_reservation.return_value = _make_reservation()
    return mock


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def caller():
    mock = MagicMock()
    mock.generate_ws_token = AsyncMock(return_value="test-token")
    mock.initiate_call = AsyncMock(return_value="CA123456")
    return mock


class TestCallTask:
    @pytest.mark.asyncio
    async def test_successful_call(self, db, session, caller):
        result = await place_reservation_call("res-test-001", db, session, caller)
        assert result["status"] == "initiated"
        assert result["call_sid"] == "CA123456"
        caller.initiate_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_status_to_calling(self, db, session, caller):
        await place_reservation_call("res-test-001", db, session, caller)
        db.update_reservation.assert_any_call("res-test-001", status="calling")

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, db, session, caller):
        caller.initiate_call.side_effect = Exception("Network error")
        result = await place_reservation_call("res-test-001", db, session, caller, attempt=1, max_retries=3)
        assert result["status"] == "retry"
        assert result["next_attempt"] == 2
        assert result["delay"] > 0

    @pytest.mark.asyncio
    async def test_fails_after_max_retries(self, db, session, caller):
        caller.initiate_call.side_effect = Exception("Network error")
        result = await place_reservation_call("res-test-001", db, session, caller, attempt=3, max_retries=3)
        assert result["status"] == "failed"
        db.update_reservation.assert_any_call("res-test-001", status="failed")

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, db, session, caller):
        caller.initiate_call.side_effect = Exception("err")
        r1 = await place_reservation_call("res-test-001", db, session, caller, attempt=1, max_retries=3)
        r2 = await place_reservation_call("res-test-001", db, session, caller, attempt=2, max_retries=3)
        assert r1["delay"] < r2["delay"]  # Increasing delay

    @pytest.mark.asyncio
    async def test_rejects_confirmed_reservation(self, db, session, caller):
        db.get_reservation.return_value = _make_reservation(status="confirmed")
        with pytest.raises(CallTaskError):
            await place_reservation_call("res-test-001", db, session, caller)

    @pytest.mark.asyncio
    async def test_not_found_raises(self, db, session, caller):
        db.get_reservation.return_value = None
        with pytest.raises(CallTaskError, match="not found"):
            await place_reservation_call("res-missing", db, session, caller)

    @pytest.mark.asyncio
    async def test_logs_call(self, db, session, caller):
        await place_reservation_call("res-test-001", db, session, caller)
        db.log_call.assert_called_once()
        call_log = db.log_call.call_args[0][0]
        assert call_log["call_sid"] == "CA123456"
        assert call_log["attempt"] == 1
