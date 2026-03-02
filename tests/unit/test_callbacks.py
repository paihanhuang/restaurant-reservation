"""Unit tests for Twilio status callbacks and AMD detection."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.telephony.callbacks import handle_status_callback, handle_amd_callback, validate_twilio_signature


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


class TestHandleAmdCallback:
    """Tests for Twilio AMD (Answering Machine Detection) callback."""

    @pytest.mark.asyncio
    async def test_machine_detected(self):
        """Machine answer should return machine_detected=True and log it."""
        db = AsyncMock()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallSid": "CA_vm",
            "AnsweredBy": "machine_end_beep",
        })

        result = await handle_amd_callback(request, db)
        assert result["machine_detected"] is True
        assert result["answered_by"] == "machine_end_beep"
        db.log_call.assert_called_once()

        logged = db.log_call.call_args[0][0]
        assert logged["status"] == "voicemail_detected"

    @pytest.mark.asyncio
    async def test_human_detected(self):
        """Human answer should return machine_detected=False and not log."""
        db = AsyncMock()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallSid": "CA_human",
            "AnsweredBy": "human",
        })

        result = await handle_amd_callback(request, db)
        assert result["machine_detected"] is False
        assert result["answered_by"] == "human"
        db.log_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_answered_by_defaults_human(self):
        """Missing AnsweredBy should default to 'unknown' → treated as human."""
        db = AsyncMock()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallSid": "CA_noval",
        })

        result = await handle_amd_callback(request, db)
        assert result["machine_detected"] is False
        assert result["answered_by"] == "unknown"

    @pytest.mark.asyncio
    async def test_fax_detected(self):
        """Fax detection should be treated as machine."""
        db = AsyncMock()
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "CallSid": "CA_fax",
            "AnsweredBy": "fax",
        })

        result = await handle_amd_callback(request, db)
        assert result["machine_detected"] is True
