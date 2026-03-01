"""Unit tests for Pydantic API schemas."""

import pytest
from datetime import date, time, timedelta

from src.api.schemas import (
    ReservationRequest,
    TimeWindow,
    UserContact,
    ReservationResponse,
)
from src.models.enums import ReservationStatus


class TestTimeWindow:
    def test_valid_range(self):
        tw = TimeWindow(start=time(18, 0), end=time(21, 0))
        assert tw.start == time(18, 0)
        assert tw.end == time(21, 0)

    def test_invalid_range_start_after_end(self):
        with pytest.raises(ValueError, match="start must be before end"):
            TimeWindow(start=time(21, 0), end=time(18, 0))

    def test_invalid_range_equal(self):
        with pytest.raises(ValueError, match="start must be before end"):
            TimeWindow(start=time(19, 0), end=time(19, 0))


class TestUserContact:
    def test_valid_e164(self):
        uc = UserContact(phone="+14155551234", email="user@test.com")
        assert uc.phone == "+14155551234"

    def test_invalid_phone_no_plus(self):
        with pytest.raises(ValueError):
            UserContact(phone="4155551234", email="user@test.com")

    def test_invalid_phone_too_short(self):
        with pytest.raises(ValueError):
            UserContact(phone="+1", email="user@test.com")

    def test_invalid_email(self):
        with pytest.raises(ValueError):
            UserContact(phone="+14155551234", email="not-an-email")


class TestReservationRequest:
    def _valid_payload(self, **overrides) -> dict:
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

    def test_valid_request(self):
        r = ReservationRequest(**self._valid_payload())
        assert r.restaurant_name == "Test Restaurant"
        assert r.party_size == 4
        assert r.alt_time_window is None

    def test_valid_with_alt_time(self):
        r = ReservationRequest(**self._valid_payload(
            alt_time_window={"start": "18:00:00", "end": "21:00:00"}
        ))
        assert r.alt_time_window.start == time(18, 0)
        assert r.alt_time_window.end == time(21, 0)

    def test_past_date_rejected(self):
        with pytest.raises(ValueError, match="future"):
            ReservationRequest(**self._valid_payload(date="2020-01-01"))

    def test_party_size_zero_rejected(self):
        with pytest.raises(ValueError):
            ReservationRequest(**self._valid_payload(party_size=0))

    def test_party_size_over_20_rejected(self):
        with pytest.raises(ValueError):
            ReservationRequest(**self._valid_payload(party_size=21))

    def test_invalid_phone_rejected(self):
        with pytest.raises(ValueError):
            ReservationRequest(**self._valid_payload(restaurant_phone="555-1234"))

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError):
            ReservationRequest(**self._valid_payload(restaurant_name=""))

    def test_none_alt_time_accepted(self):
        r = ReservationRequest(**self._valid_payload(alt_time_window=None))
        assert r.alt_time_window is None

    def test_special_requests_optional(self):
        r = ReservationRequest(**self._valid_payload(special_requests="Window seat"))
        assert r.special_requests == "Window seat"
