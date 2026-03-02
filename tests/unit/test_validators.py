"""Unit tests for conversation validators."""

import pytest
from datetime import time, date

from src.conversation.validators import (
    parse_time_strict,
    parse_date_strict,
    validate_proposed_time,
    validate_confirmed_date,
)


class TestParseTimeStrict:
    def test_valid_24h(self):
        assert parse_time_strict("19:30") == time(19, 30)

    def test_valid_midnight(self):
        assert parse_time_strict("00:00") == time(0, 0)

    def test_valid_with_seconds(self):
        assert parse_time_strict("14:30:00") == time(14, 30, 0)

    def test_valid_single_digit_hour(self):
        assert parse_time_strict("9:00") == time(9, 0)

    def test_rejects_am_pm(self):
        with pytest.raises(ValueError, match="Ambiguous"):
            parse_time_strict("7:30 PM")

    def test_rejects_am(self):
        with pytest.raises(ValueError, match="Ambiguous"):
            parse_time_strict("11:00 AM")

    def test_rejects_lowercase_pm(self):
        with pytest.raises(ValueError, match="Ambiguous"):
            parse_time_strict("7pm")

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            parse_time_strict("dinnertime")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            parse_time_strict("")

    def test_rejects_out_of_range_hour(self):
        with pytest.raises(ValueError):
            parse_time_strict("25:00")

    def test_whitespace_stripped(self):
        assert parse_time_strict("  19:30  ") == time(19, 30)


class TestParseDateStrict:
    def test_valid_date(self):
        assert parse_date_strict("2026-04-15") == date(2026, 4, 15)

    def test_rejects_us_format(self):
        with pytest.raises(ValueError):
            parse_date_strict("04/15/2026")

    def test_rejects_text(self):
        with pytest.raises(ValueError):
            parse_date_strict("April 15, 2026")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            parse_date_strict("")


class TestValidateProposedTime:
    def test_within_bounds(self):
        assert validate_proposed_time(
            time(19, 0), time(18, 0), time(21, 0)
        ) is True

    def test_at_start_boundary(self):
        assert validate_proposed_time(
            time(18, 0), time(18, 0), time(21, 0)
        ) is True

    def test_at_end_boundary(self):
        assert validate_proposed_time(
            time(21, 0), time(18, 0), time(21, 0)
        ) is True

    def test_outside_bounds(self):
        assert validate_proposed_time(
            time(22, 0), time(18, 0), time(21, 0)
        ) is False

    def test_no_flexibility(self):
        assert validate_proposed_time(time(19, 0), None, None) is False


class TestValidateConfirmedDate:
    def test_match(self):
        d = date(2026, 4, 15)
        assert validate_confirmed_date(d, d) is True

    def test_mismatch(self):
        assert validate_confirmed_date(date(2026, 4, 16), date(2026, 4, 15)) is False
