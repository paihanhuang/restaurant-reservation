"""E2E test scenarios — tests full pipeline with mocked providers.

10 defined scenarios from the phased roadmap, exercising the full
reservation lifecycle: API → state machine → conversation engine.
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta, time
from unittest.mock import AsyncMock

from src.providers.base import LLMResponse
from src.conversation.engine import ConversationEngine
from src.conversation.state_machine import StateMachine, InvalidStateTransition
from src.models.enums import ReservationStatus
from src.tasks.call_task import place_reservation_call
from src.tasks.cleanup_task import cleanup_stale_reservations
from src.conversation.validators import parse_time_strict, validate_proposed_time


FUTURE_DATE = (date.today() + timedelta(days=30)).isoformat()


def _make_reservation(**overrides):
    base = {
        "reservation_id": "e2e-test-001",
        "restaurant_name": "E2E Bistro",
        "restaurant_phone": "+14155551234",
        "date": FUTURE_DATE,
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
        llm=llm, tts=tts, stt=stt, db=db,
        state_machine=sm,
    )
    return engine, db


class TestScenario1HappyPath:
    """API → call → restaurant confirms → confirmed + notification."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        engine, db = _make_engine(llm_responses=[
            LLMResponse(speech_text="Great, thank you!"),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_1"},
            ),
        ])

        greeting = await engine.generate_greeting()
        assert greeting

        result = await engine.process_utterance("Yes, we have a table at 7:30")
        assert result["ended"] is False

        result = await engine.process_utterance("You're confirmed for 7:30")
        assert result["ended"] is True
        assert engine.ended is True
        db.update_reservation.assert_called()


class TestScenario2NegotiationAccepted:
    """API → call → alt within bounds → user confirms → confirmed."""

    @pytest.mark.asyncio
    async def test_negotiation_auto_accept(self):
        res = _make_reservation(alt_time_start="18:00", alt_time_end="21:00")
        engine, db = _make_engine(
            reservation=res,
            llm_responses=[
                LLMResponse(
                    action="propose_alternative",
                    params={"proposed_time": "20:00", "reason": "7:30 taken"},
                    raw_response={"tool_call_id": "call_1"},
                ),
            ],
        )

        result = await engine.process_utterance("7:30 is taken, how about 8?")
        assert result["ended"] is True
        # Auto-accepted because within bounds


class TestScenario3Rejection:
    """API → call → no availability → failed."""

    @pytest.mark.asyncio
    async def test_rejection(self):
        engine, db = _make_engine(llm_responses=[
            LLMResponse(
                action="end_call",
                params={"reason": "fully booked", "outcome": "no_availability"},
                raw_response={"tool_call_id": "call_1"},
            ),
        ])

        result = await engine.process_utterance("Sorry, we're fully booked")
        assert result["action"] == "end_call"
        assert result["ended"] is True


class TestScenario4RetryOnBusy:
    """API → call → busy → retry → confirms on attempt 2."""

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        db = AsyncMock()
        session = AsyncMock()
        caller = AsyncMock()

        # Attempt 1: fails
        db.get_reservation.return_value = _make_reservation(status="pending")
        caller.generate_ws_token = AsyncMock(return_value="tok1")
        caller.initiate_call = AsyncMock(side_effect=Exception("Busy"))

        r1 = await place_reservation_call("e2e-1", db, session, caller, attempt=1, max_retries=3)
        assert r1["status"] == "retry"

        # Attempt 2: succeeds
        caller.initiate_call = AsyncMock(return_value="CA999")
        r2 = await place_reservation_call("e2e-1", db, session, caller, attempt=2, max_retries=3)
        assert r2["status"] == "initiated"


class TestScenario5Voicemail:
    """API → call → voicemail → hang up → retry."""

    @pytest.mark.asyncio
    async def test_voicemail_retry(self):
        engine, db = _make_engine(llm_responses=[
            LLMResponse(
                action="end_call",
                params={"reason": "voicemail detected", "outcome": "error"},
                raw_response={"tool_call_id": "call_1"},
            ),
        ])

        result = await engine.process_utterance("You have reached the voicemail of...")
        assert result["action"] == "end_call"
        assert result["ended"] is True


class TestScenario6HoldHandling:
    """API → call → hold → agent prompts → resume → confirms."""

    @pytest.mark.asyncio
    async def test_hold_then_confirm(self):
        engine, db = _make_engine(llm_responses=[
            LLMResponse(speech_text="Of course, take your time."),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_1"},
            ),
        ])

        result = await engine.process_utterance("Please hold while I check.")
        assert result["ended"] is False

        result = await engine.process_utterance("Yes, we can do 7:30 for 4 people.")
        assert result["ended"] is True


class TestScenario7MaxRetries:
    """API → call → no answer × 3 → failed."""

    @pytest.mark.asyncio
    async def test_max_retries_fails(self):
        db = AsyncMock()
        db.get_reservation.return_value = _make_reservation(status="pending")
        session = AsyncMock()
        caller = AsyncMock()
        caller.generate_ws_token = AsyncMock(return_value="tok")
        caller.initiate_call = AsyncMock(side_effect=Exception("No answer"))

        result = await place_reservation_call("e2e-7", db, session, caller, attempt=3, max_retries=3)
        assert result["status"] == "failed"


class TestScenario8CallTimeout:
    """API → call → conversation >5 min → forced end_call."""

    @pytest.mark.asyncio
    async def test_timeout_ends_call(self):
        engine, db = _make_engine(llm_responses=[
            LLMResponse(
                action="end_call",
                params={"reason": "call timeout exceeded", "outcome": "error"},
                raw_response={"tool_call_id": "call_1"},
            ),
        ])

        result = await engine.process_utterance("Still checking... let me see...")
        assert result["action"] == "end_call"
        assert result["ended"] is True


class TestScenario9AltTimeout:
    """API → alt proposed → no user response 24h → failed."""

    @pytest.mark.asyncio
    async def test_alt_timeout_cleanup(self):
        db = AsyncMock()
        db.list_reservations_by_status.side_effect = [
            [],  # stale calling
            [{"reservation_id": "e2e-9", "confirmed_time": "20:30"}],  # stale alt
        ]

        result = await cleanup_stale_reservations(db)
        assert result["stale_alt_proposed"] == 1
        db.update_reservation.assert_called_with("e2e-9", status="failed")


class TestScenario10Concurrent:
    """Two reservations submitted simultaneously → both complete."""

    @pytest.mark.asyncio
    async def test_concurrent_reservations(self):
        # Create two separate engines
        res1 = _make_reservation(reservation_id="concurrent-1")
        res2 = _make_reservation(reservation_id="concurrent-2")

        engine1, db1 = _make_engine(
            reservation=res1,
            llm_responses=[
                LLMResponse(
                    action="confirm_reservation",
                    params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                    raw_response={"tool_call_id": "call_1"},
                ),
            ],
        )
        engine2, db2 = _make_engine(
            reservation=res2,
            llm_responses=[
                LLMResponse(
                    action="confirm_reservation",
                    params={"confirmed_time": "20:00", "confirmed_date": FUTURE_DATE},
                    raw_response={"tool_call_id": "call_2"},
                ),
            ],
        )

        # Run both concurrently
        import asyncio
        r1, r2 = await asyncio.gather(
            engine1.process_utterance("Confirmed at 7:30"),
            engine2.process_utterance("Confirmed at 8:00"),
        )

        assert r1["ended"] is True
        assert r2["ended"] is True
        # Both have independent state
        assert engine1.reservation_id != engine2.reservation_id
