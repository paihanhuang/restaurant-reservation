"""Unit tests for Twilio status callbacks."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.telephony.callbacks import handle_status_callback, validate_twilio_signature


class TestHandleStatusCallback:
    @pytest.mark.asyncio
    async def test_callback_logs_call(self):
        """Status callback should log call data to DB."""
        db = AsyncMock()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallSid": "CA1234",
            "CallStatus": "completed",
            "CallDuration": "45",
            "AccountSid": "AC_test",
        })

        result = await handle_status_callback(request, db)
        assert result["call_sid"] == "CA1234"
        db.log_call.assert_called_once()

        logged = db.log_call.call_args[0][0]
        assert logged["call_sid"] == "CA1234"
        assert logged["status"] == "completed"
        assert logged["duration_seconds"] == 45

    @pytest.mark.asyncio
    async def test_callback_maps_in_progress(self):
        """'in-progress' Twilio status should map to 'answered'."""
        db = AsyncMock()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallSid": "CA5678",
            "CallStatus": "in-progress",
        })

        await handle_status_callback(request, db)
        logged = db.log_call.call_args[0][0]
        assert logged["status"] == "answered"

    @pytest.mark.asyncio
    async def test_callback_maps_busy(self):
        """'busy' Twilio status should map to 'busy'."""
        db = AsyncMock()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallSid": "CA9999",
            "CallStatus": "busy",
        })

        await handle_status_callback(request, db)
        logged = db.log_call.call_args[0][0]
        assert logged["status"] == "busy"

    @pytest.mark.asyncio
    async def test_callback_is_idempotent(self):
        """Duplicate callbacks should not crash — each call produces a log entry."""
        db = AsyncMock()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallSid": "CA1111",
            "CallStatus": "ringing",
        })

        await handle_status_callback(request, db)
        await handle_status_callback(request, db)
        assert db.log_call.call_count == 2
