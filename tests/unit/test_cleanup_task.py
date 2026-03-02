"""Unit tests for cleanup tasks — stale state remediation."""

import pytest
from unittest.mock import AsyncMock

from src.tasks.cleanup_task import cleanup_stale_reservations


@pytest.fixture
def db():
    return AsyncMock()


class TestCleanupStaleReservations:
    @pytest.mark.asyncio
    async def test_cleans_stale_calling(self, db):
        db.list_reservations_by_status.side_effect = [
            [{"reservation_id": "res-1"}, {"reservation_id": "res-2"}],  # stale calling
            [],  # stale alt proposed
        ]

        result = await cleanup_stale_reservations(db)
        assert result["stale_calling"] == 2
        assert db.update_reservation.call_count == 2

    @pytest.mark.asyncio
    async def test_cleans_stale_alt_proposed(self, db):
        db.list_reservations_by_status.side_effect = [
            [],     # stale calling
            [{"reservation_id": "res-3", "confirmed_time": "20:30"}],  # stale alt
        ]

        result = await cleanup_stale_reservations(db)
        assert result["stale_alt_proposed"] == 1

    @pytest.mark.asyncio
    async def test_no_stale_returns_zeros(self, db):
        db.list_reservations_by_status.return_value = []
        result = await cleanup_stale_reservations(db)
        assert result["stale_calling"] == 0
        assert result["stale_alt_proposed"] == 0

    @pytest.mark.asyncio
    async def test_transitions_calling_to_failed(self, db):
        db.list_reservations_by_status.side_effect = [
            [{"reservation_id": "res-1"}],
            [],
        ]

        await cleanup_stale_reservations(db)
        db.update_reservation.assert_called_with("res-1", status="failed")

    @pytest.mark.asyncio
    async def test_transitions_alt_to_failed(self, db):
        db.list_reservations_by_status.side_effect = [
            [],
            [{"reservation_id": "res-2", "confirmed_time": "20:30"}],
        ]

        await cleanup_stale_reservations(db)
        db.update_reservation.assert_called_with("res-2", status="failed")

    @pytest.mark.asyncio
    async def test_logs_all_transitions(self, db):
        db.list_reservations_by_status.side_effect = [
            [{"reservation_id": "res-1"}],
            [{"reservation_id": "res-2", "confirmed_time": "20:30"}],
        ]

        await cleanup_stale_reservations(db)
        assert db.log_state_transition.call_count == 2

    @pytest.mark.asyncio
    async def test_notifier_called_on_failure(self, db):
        db.list_reservations_by_status.side_effect = [
            [{"reservation_id": "res-1"}],
            [],
        ]
        notifier = AsyncMock()
        notifier.notify = AsyncMock()

        await cleanup_stale_reservations(db, notifier=notifier)
        notifier.notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self, db):
        db.list_reservations_by_status.side_effect = [
            [{"reservation_id": "res-1"}],
            [],
        ]
        db.update_reservation.side_effect = Exception("DB error")

        # Should not raise — errors are logged
        result = await cleanup_stale_reservations(db)
        assert result["stale_calling"] == 0  # Failed to process
