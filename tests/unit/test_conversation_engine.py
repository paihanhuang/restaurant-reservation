"""Unit tests for conversation engine — mock LLM, verify state transitions."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, time

from src.providers.base import LLMResponse
from src.conversation.engine import ConversationEngine
from src.conversation.state_machine import StateMachine
from src.models.enums import ReservationStatus


def _make_reservation(**overrides):
    """Build a test reservation dict."""
    base = {
        "reservation_id": "res-test-001",
        "restaurant_name": "Test Bistro",
        "restaurant_phone": "+14155551234",
        "date": "2026-04-15",
        "preferred_time": "19:30",
        "party_size": 4,
        "status": ReservationStatus.CALLING,
        "special_requests": None,
        "alt_time_start": None,
        "alt_time_end": None,
    }
    base.update(overrides)
    return base


def _make_engine(reservation=None, llm_responses=None):
    """Create a ConversationEngine with mocked dependencies."""
    res = reservation or _make_reservation()
    llm = AsyncMock()
    if llm_responses:
        llm.chat.side_effect = llm_responses
    tts = AsyncMock()
    stt = AsyncMock()
    db = AsyncMock()
    sm = StateMachine(db)

    engine = ConversationEngine(
        reservation_id=res["reservation_id"],
        reservation=res,
        llm=llm,
        tts=tts,
        stt=stt,
        db=db,
        state_machine=sm,
    )
    return engine, llm, db


class TestGreeting:
    @pytest.mark.asyncio
    async def test_generates_greeting(self):
        engine, _, _ = _make_engine()
        greeting = await engine.generate_greeting()
        assert "reservation" in greeting.lower() or "table" in greeting.lower()
        assert "4" in greeting  # party size
        assert len(engine.messages) == 2  # system + assistant

    @pytest.mark.asyncio
    async def test_greeting_in_messages(self):
        engine, _, _ = _make_engine()
        greeting = await engine.generate_greeting()
        assert engine.messages[-1]["role"] == "assistant"
        assert engine.messages[-1]["content"] == greeting


class TestConfirmation:
    @pytest.mark.asyncio
    async def test_confirm_updates_state(self):
        engine, llm, db = _make_engine()
        llm.chat.return_value = LLMResponse(
            action="confirm_reservation",
            params={"confirmed_time": "19:30", "confirmed_date": "2026-04-15"},
            raw_response={"tool_call_id": "call_1"},
        )

        result = await engine.process_utterance("Yes, we have a table at 7:30")
        assert result["action"] == "confirm_reservation"
        assert result["ended"] is True
        db.update_reservation.assert_called()

    @pytest.mark.asyncio
    async def test_confirm_bad_time_reprompts(self):
        engine, llm, db = _make_engine()
        # First call: bad format, second call: follow-up speech
        llm.chat.side_effect = [
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "7:30 PM", "confirmed_date": "2026-04-15"},
                raw_response={"tool_call_id": "call_1"},
            ),
            LLMResponse(speech_text="I'm sorry, could you confirm the time?"),
        ]

        result = await engine.process_utterance("We have 7:30")
        # Should not have ended — validation error triggers re-prompt
        assert result["ended"] is False

    @pytest.mark.asyncio
    async def test_confirm_wrong_date_reprompts(self):
        engine, llm, db = _make_engine()
        llm.chat.side_effect = [
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": "2026-04-16"},
                raw_response={"tool_call_id": "call_1"},
            ),
            LLMResponse(speech_text="Let me verify the date..."),
        ]

        result = await engine.process_utterance("Confirmed for tomorrow")
        assert result["ended"] is False  # Date mismatch


class TestAlternativeProposal:
    @pytest.mark.asyncio
    async def test_alt_within_bounds_auto_confirms(self):
        """If proposed time is within flexibility window, auto-confirm."""
        res = _make_reservation(alt_time_start="18:00", alt_time_end="21:00")
        engine, llm, db = _make_engine(reservation=res)

        llm.chat.return_value = LLMResponse(
            action="propose_alternative",
            params={"proposed_time": "20:00", "reason": "19:30 is taken"},
            raw_response={"tool_call_id": "call_1"},
        )

        result = await engine.process_utterance("Sorry, 7:30 is full. How about 8?")
        assert result["ended"] is True
        # Should have confirmed (auto-accept within bounds)
        assert result["action"] == "confirm_reservation"

    @pytest.mark.asyncio
    async def test_alt_outside_bounds_proposes(self):
        """If proposed time is outside window, transition to alternative_proposed."""
        res = _make_reservation(alt_time_start="18:00", alt_time_end="20:00")
        engine, llm, db = _make_engine(reservation=res)

        llm.chat.return_value = LLMResponse(
            action="propose_alternative",
            params={"proposed_time": "21:30", "reason": "only late slots"},
            raw_response={"tool_call_id": "call_1"},
        )

        result = await engine.process_utterance("We only have 9:30 PM")
        assert result["ended"] is True
        assert result["action"] == "propose_alternative"

    @pytest.mark.asyncio
    async def test_alt_no_flexibility_proposes(self):
        """If no flexibility window, always transition to alternative_proposed."""
        engine, llm, db = _make_engine()  # no alt_time_start/end

        llm.chat.return_value = LLMResponse(
            action="propose_alternative",
            params={"proposed_time": "20:00", "reason": "19:30 unavailable"},
            raw_response={"tool_call_id": "call_1"},
        )

        result = await engine.process_utterance("How about 8 PM?")
        assert result["ended"] is True
        assert result["action"] == "propose_alternative"


class TestEndCall:
    @pytest.mark.asyncio
    async def test_end_call_transitions_to_failed(self):
        engine, llm, db = _make_engine()
        llm.chat.return_value = LLMResponse(
            action="end_call",
            params={"reason": "fully booked", "outcome": "no_availability"},
            raw_response={"tool_call_id": "call_1"},
        )

        result = await engine.process_utterance("Sorry, we're fully booked")
        assert result["action"] == "end_call"
        assert result["ended"] is True

    @pytest.mark.asyncio
    async def test_end_call_produces_goodbye(self):
        engine, llm, db = _make_engine()
        llm.chat.return_value = LLMResponse(
            action="end_call",
            params={"reason": "no availability", "outcome": "no_availability"},
            raw_response={"tool_call_id": "call_1"},
        )

        result = await engine.process_utterance("We can't help you")
        assert result.get("speech_text") is not None
        assert "thank" in result["speech_text"].lower()


class TestSpeechResponse:
    @pytest.mark.asyncio
    async def test_regular_speech(self):
        engine, llm, db = _make_engine()
        llm.chat.return_value = LLMResponse(speech_text="Could you check again?")

        result = await engine.process_utterance("Let me check...")
        assert result["speech_text"] == "Could you check again?"
        assert result["ended"] is False

    @pytest.mark.asyncio
    async def test_no_processing_after_ended(self):
        engine, _, _ = _make_engine()
        engine.ended = True

        result = await engine.process_utterance("Hello?")
        assert result["ended"] is True
        assert result["speech_text"] is None
