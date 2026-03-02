"""Unit tests for voicemail detection and TwiML generation."""

from __future__ import annotations

import pytest

from src.telephony.voicemail import is_machine, build_voicemail_twiml, VOICEMAIL_TEMPLATE


# ── is_machine() ────────────────────────────────────────────────────────

class TestIsMachine:
    """Tests for answering machine classification."""

    @pytest.mark.parametrize("answered_by", [
        "machine_start",
        "machine_end_beep",
        "machine_end_silence",
        "machine_end_other",
        "fax",
    ])
    def test_machine_values_return_true(self, answered_by: str):
        assert is_machine(answered_by) is True

    @pytest.mark.parametrize("answered_by", [
        "human",
        "unknown",
    ])
    def test_non_machine_values_return_false(self, answered_by: str):
        assert is_machine(answered_by) is False

    def test_empty_string_returns_false(self):
        assert is_machine("") is False

    def test_case_insensitive(self):
        assert is_machine("Machine_End_Beep") is True
        assert is_machine("HUMAN") is False

    def test_whitespace_stripped(self):
        assert is_machine("  machine_start  ") is True
        assert is_machine("  human  ") is False

    def test_unexpected_value_returns_false(self):
        """Unknown AMD values should default to human (safe fallback)."""
        assert is_machine("something_unexpected") is False


# ── build_voicemail_twiml() ─────────────────────────────────────────────

class TestBuildVoicemailTwiml:
    """Tests for voicemail TwiML generation."""

    SAMPLE_RESERVATION = {
        "restaurant_name": "Bella Italia",
        "party_size": 4,
        "date": "2026-03-09",
        "preferred_time": "19:30",
    }

    def test_returns_valid_xml(self):
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert twiml.startswith("<?xml")
        assert "<Response>" in twiml

    def test_contains_say(self):
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert "<Say" in twiml

    def test_contains_hangup(self):
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert "<Hangup" in twiml

    def test_contains_pause(self):
        """Should pause before speaking to let the beep finish."""
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert "<Pause" in twiml

    def test_message_includes_restaurant_name(self):
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert "Bella Italia" in twiml

    def test_message_includes_party_size(self):
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert "4" in twiml

    def test_message_includes_date(self):
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert "2026-03-09" in twiml

    def test_message_includes_time(self):
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert "19:30" in twiml

    def test_handles_missing_fields(self):
        """Should not crash on incomplete reservation dicts."""
        twiml = build_voicemail_twiml({})
        assert "<Say" in twiml
        assert "<Hangup" in twiml

    def test_voice_is_polly_joanna(self):
        twiml = build_voicemail_twiml(self.SAMPLE_RESERVATION)
        assert "Polly.Joanna" in twiml
