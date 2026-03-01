"""Unit tests for data models and enums."""

import pytest
from datetime import date, time

from src.models.enums import ReservationStatus, CallStatus
from src.models.reservation import Reservation
from src.models.call_log import CallLog
from src.models.transcript import TranscriptTurn


class TestReservationStatus:
    def test_all_values(self):
        assert ReservationStatus.PENDING == "pending"
        assert ReservationStatus.CALLING == "calling"
        assert ReservationStatus.IN_CONVERSATION == "in_conversation"
        assert ReservationStatus.ALTERNATIVE_PROPOSED == "alternative_proposed"
        assert ReservationStatus.CONFIRMED == "confirmed"
        assert ReservationStatus.RETRY == "retry"
        assert ReservationStatus.FAILED == "failed"

    def test_from_string(self):
        assert ReservationStatus("pending") == ReservationStatus.PENDING
        assert ReservationStatus("confirmed") == ReservationStatus.CONFIRMED

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            ReservationStatus("invalid_status")


class TestCallStatus:
    def test_all_values(self):
        assert CallStatus.INITIATED == "initiated"
        assert CallStatus.ANSWERED == "answered"
        assert CallStatus.VOICEMAIL == "voicemail"


class TestReservation:
    def test_construction(self):
        r = Reservation(
            restaurant_name="Test Restaurant",
            restaurant_phone="+14155551234",
            date=date(2026, 3, 15),
            preferred_time=time(19, 30),
            party_size=4,
            user_id="user@test.com",
            user_phone="+14155555678",
            user_email="user@test.com",
        )
        assert r.status == ReservationStatus.PENDING
        assert r.call_attempts == 0
        assert r.reservation_id  # UUID generated
        assert r.alt_time_start is None

    def test_with_alt_time(self):
        r = Reservation(
            restaurant_name="Test",
            restaurant_phone="+14155551234",
            date=date(2026, 3, 15),
            preferred_time=time(19, 0),
            party_size=2,
            user_id="user@test.com",
            user_phone="+14155555678",
            user_email="user@test.com",
            alt_time_start=time(18, 0),
            alt_time_end=time(21, 0),
        )
        assert r.alt_time_start == time(18, 0)
        assert r.alt_time_end == time(21, 0)

    def test_to_dict_and_back(self):
        r = Reservation(
            restaurant_name="Chez Test",
            restaurant_phone="+14155551234",
            date=date(2026, 4, 1),
            preferred_time=time(20, 0),
            party_size=6,
            user_id="user@test.com",
            user_phone="+14155555678",
            user_email="user@test.com",
            special_requests="Window seat",
        )
        d = r.to_dict()
        assert d["restaurant_name"] == "Chez Test"
        assert d["date"] == "2026-04-01"
        assert d["preferred_time"] == "20:00:00"
        assert d["status"] == "pending"

        r2 = Reservation.from_dict(d)
        assert r2.reservation_id == r.reservation_id
        assert r2.restaurant_name == r.restaurant_name
        assert r2.date == r.date
        assert r2.special_requests == "Window seat"


class TestCallLog:
    def test_construction(self):
        cl = CallLog(
            reservation_id="test-id",
            call_sid="CA1234",
            attempt_number=1,
            status=CallStatus.INITIATED,
        )
        assert cl.duration_seconds is None
        d = cl.to_dict()
        assert d["status"] == "initiated"
        assert d["attempt_number"] == 1


class TestTranscriptTurn:
    def test_construction(self):
        tt = TranscriptTurn(
            reservation_id="test-id",
            call_sid="CA1234",
            turn_number=1,
            role="agent",
            text="Hello, I'd like to make a reservation.",
        )
        d = tt.to_dict()
        assert d["role"] == "agent"
        assert d["turn_number"] == 1
        assert "timestamp" in d
