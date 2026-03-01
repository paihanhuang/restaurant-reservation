"""Unit tests for SQLite database provider."""

import os
import tempfile
import pytest
from datetime import datetime

from src.providers.sqlite_db import SQLiteDatabase
from src.models.enums import ReservationStatus


@pytest.fixture
def db():
    """Create a temp SQLite DB for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    database = SQLiteDatabase(db_path=db_path)
    yield database
    os.unlink(db_path)


@pytest.fixture
def sample_reservation():
    return {
        "reservation_id": "test-res-001",
        "user_id": "user@test.com",
        "restaurant_name": "Chez Test",
        "restaurant_phone": "+14155551234",
        "date": "2026-04-01",
        "preferred_time": "19:30:00",
        "alt_time_start": "18:00:00",
        "alt_time_end": "21:00:00",
        "party_size": 4,
        "special_requests": "Window seat",
        "status": "pending",
        "call_attempts": 0,
        "call_sid": None,
        "confirmed_time": None,
        "user_phone": "+14155555678",
        "user_email": "user@test.com",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


@pytest.mark.asyncio
class TestSQLiteDatabase:
    async def test_initialize_creates_tables(self, db):
        await db.initialize()
        # Verify tables exist by querying them
        conn = db._get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        assert "reservations" in table_names
        assert "transcript_turns" in table_names
        assert "call_logs" in table_names
        assert "state_transitions" in table_names
        conn.close()

    async def test_create_and_get_reservation(self, db, sample_reservation):
        await db.initialize()
        await db.create_reservation(sample_reservation)
        result = await db.get_reservation("test-res-001")
        assert result is not None
        assert result["restaurant_name"] == "Chez Test"
        assert result["party_size"] == 4

    async def test_get_nonexistent_reservation(self, db):
        await db.initialize()
        result = await db.get_reservation("nonexistent-id")
        assert result is None

    async def test_update_reservation(self, db, sample_reservation):
        await db.initialize()
        await db.create_reservation(sample_reservation)
        await db.update_reservation(
            "test-res-001",
            status=ReservationStatus.CALLING.value,
            call_attempts=1,
        )
        result = await db.get_reservation("test-res-001")
        assert result["status"] == "calling"
        assert result["call_attempts"] == 1

    async def test_list_by_status(self, db, sample_reservation):
        await db.initialize()
        await db.create_reservation(sample_reservation)
        results = await db.list_reservations_by_status("pending")
        assert len(results) == 1
        assert results[0]["reservation_id"] == "test-res-001"

    async def test_list_by_status_empty(self, db):
        await db.initialize()
        results = await db.list_reservations_by_status("confirmed")
        assert len(results) == 0

    async def test_log_state_transition(self, db, sample_reservation):
        await db.initialize()
        await db.create_reservation(sample_reservation)
        await db.log_state_transition({
            "reservation_id": "test-res-001",
            "from_state": "pending",
            "to_state": "calling",
            "trigger": "call_task",
            "call_sid": "CA1234",
            "timestamp": datetime.utcnow().isoformat(),
        })
        conn = db._get_connection()
        rows = conn.execute(
            "SELECT * FROM state_transitions WHERE reservation_id = ?",
            ("test-res-001",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["to_state"] == "calling"
        conn.close()

    async def test_log_call(self, db, sample_reservation):
        await db.initialize()
        await db.create_reservation(sample_reservation)
        await db.log_call({
            "reservation_id": "test-res-001",
            "call_sid": "CA1234",
            "attempt_number": 1,
            "status": "initiated",
            "duration_seconds": None,
            "started_at": datetime.utcnow().isoformat(),
            "ended_at": None,
            "error_message": None,
        })
        conn = db._get_connection()
        rows = conn.execute(
            "SELECT * FROM call_logs WHERE reservation_id = ?",
            ("test-res-001",),
        ).fetchall()
        assert len(rows) == 1
        conn.close()

    async def test_append_and_get_transcript(self, db, sample_reservation):
        await db.initialize()
        await db.create_reservation(sample_reservation)

        await db.append_transcript_turn("test-res-001", "CA1234", {
            "turn_number": 1,
            "role": "agent",
            "text": "Hello, I'd like to make a reservation.",
            "timestamp": datetime.utcnow().isoformat(),
        })
        await db.append_transcript_turn("test-res-001", "CA1234", {
            "turn_number": 2,
            "role": "restaurant",
            "text": "Sure, for how many guests?",
            "timestamp": datetime.utcnow().isoformat(),
        })

        turns = await db.get_transcript("test-res-001")
        assert len(turns) == 2
        assert turns[0]["role"] == "agent"
        assert turns[1]["role"] == "restaurant"
        assert turns[0]["turn_number"] == 1
