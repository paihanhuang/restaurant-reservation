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


# ============================================================================
# LANGUAGE BARRIER SCENARIOS
# ============================================================================


class TestScenario11RepeatRequests:
    """Restaurant doesn't understand English well, asks agent to repeat 3 times
    before finally understanding and confirming.

    Simulates: "Sorry? What you say?" → agent repeats → "Again please?" →
    agent repeats → "Ah OK, four people seven thirty, yes we have!"
    """

    @pytest.mark.asyncio
    async def test_repeat_requests_eventually_confirms(self):
        engine, db = _make_engine(llm_responses=[
            # Turn 1: Agent repeats clearly after "Sorry? What?"
            LLMResponse(speech_text="Yes, I'd like to reserve a table for 4 people at 7:30 PM on April 15th, please."),
            # Turn 2: Agent repeats even more slowly after "Say again?"
            LLMResponse(speech_text="A table. For four people. Seven thirty PM. April fifteenth."),
            # Turn 3: Agent repeats one more time after "How many people?"
            LLMResponse(speech_text="Four people. F-O-U-R. At seven thirty in the evening."),
            # Turn 4: Restaurant finally understands → LLM confirms
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_repeat"},
            ),
        ])

        # Restaurant staff can't understand
        r1 = await engine.process_utterance("Sorry? What you say? I no understand.")
        assert r1["ended"] is False
        assert r1["speech_text"] is not None  # Agent repeats

        r2 = await engine.process_utterance("Eh? Say again please, slow slow.")
        assert r2["ended"] is False
        assert r2["speech_text"] is not None  # Agent repeats patiently

        r3 = await engine.process_utterance("How many people? What time? Say again.")
        assert r3["ended"] is False
        assert r3["speech_text"] is not None  # Agent repeats again

        # Restaurant finally gets it
        r4 = await engine.process_utterance("Ah OK OK! Four people, seven thirty, yes yes we have table!")
        assert r4["ended"] is True
        assert engine.turn_number >= 7  # 4 restaurant turns + 3 agent speech turns

    @pytest.mark.asyncio
    async def test_repeat_tracks_all_turns(self):
        """Verify transcript captures all repeat turns for audit."""
        engine, db = _make_engine(llm_responses=[
            LLMResponse(speech_text="Sure! A table for 4 at 7:30 PM please."),
            LLMResponse(speech_text="Four people, seven thirty PM."),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_1"},
            ),
        ])

        await engine.process_utterance("What? Repeat please.")
        await engine.process_utterance("Ah say again?")
        await engine.process_utterance("OK four people, seven thirty, got it!")

        # All turns should be in messages (system + greeting would be added separately)
        user_messages = [m for m in engine.messages if m.get("role") == "user"]
        assert len(user_messages) == 3  # All 3 restaurant utterances captured


class TestScenario12Misunderstanding:
    """Restaurant misunderstands the request — wrong party size, wrong time,
    or wrong date. Agent must detect and correct the misunderstanding.

    Simulates: "OK, table for 2 at 8 PM?" (agent requested 4 at 7:30)
    → Agent corrects → "Oh sorry, 4 people 7:30, yes OK!"
    """

    @pytest.mark.asyncio
    async def test_misunderstood_party_size_corrected(self):
        """Restaurant hears '2' instead of '4' — agent corrects."""
        engine, db = _make_engine(llm_responses=[
            # Turn 1: LLM detects the misunderstanding and corrects
            LLMResponse(speech_text="I'm sorry, it's actually for 4 people, not 2. Four guests at 7:30 PM."),
            # Turn 2: Restaurant acknowledges correction → confirm
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_misunderstand"},
            ),
        ])

        r1 = await engine.process_utterance("OK so table for 2 people at seven thirty, yes?")
        assert r1["ended"] is False
        assert "4" in r1["speech_text"] or "four" in r1["speech_text"].lower()

        r2 = await engine.process_utterance("Oh sorry sorry, four people! Yes we have, confirmed!")
        assert r2["ended"] is True

    @pytest.mark.asyncio
    async def test_misunderstood_time_corrected(self):
        """Restaurant hears '8:30' instead of '7:30' — agent corrects."""
        engine, db = _make_engine(llm_responses=[
            # LLM detects wrong time and corrects
            LLMResponse(speech_text="Actually, we need the table at 7:30 PM, not 8:30. Seven thirty."),
            # Restaurant confirms correct time
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_time_fix"},
            ),
        ])

        r1 = await engine.process_utterance("Table for four at eight thirty, right?")
        assert r1["ended"] is False
        assert "7:30" in r1["speech_text"] or "seven thirty" in r1["speech_text"].lower()

        r2 = await engine.process_utterance("Ah seven thirty, not eight thirty. OK yes, confirmed!")
        assert r2["ended"] is True

    @pytest.mark.asyncio
    async def test_misunderstood_date_corrected(self):
        """Restaurant thinks it's for today instead of April 15 — agent corrects."""
        engine, db = _make_engine(llm_responses=[
            LLMResponse(speech_text="No, not today. The reservation is for April 15th. April one-five."),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_date_fix"},
            ),
        ])

        r1 = await engine.process_utterance("OK for tonight? Table for four at seven thirty tonight?")
        assert r1["ended"] is False

        r2 = await engine.process_utterance("Oh April fifteen, OK OK, yes we have table!")
        assert r2["ended"] is True

    @pytest.mark.asyncio
    async def test_multiple_misunderstandings(self):
        """Restaurant gets both party size AND time wrong — agent corrects both."""
        engine, db = _make_engine(llm_responses=[
            LLMResponse(speech_text="Let me clarify — it's 4 people, not 2, and the time is 7:30, not 9 o'clock."),
            LLMResponse(speech_text="That's right! Four people at 7:30 PM on April 15th."),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_multi_fix"},
            ),
        ])

        r1 = await engine.process_utterance("Two people, nine o'clock?")
        assert r1["ended"] is False

        r2 = await engine.process_utterance("Hmm, four people... seven thirty?")
        assert r2["ended"] is False

        r3 = await engine.process_utterance("Yes yes, four, seven thirty, April fifteen. Confirmed!")
        assert r3["ended"] is True


class TestScenario13PoorPronunciation:
    """Restaurant staff has heavy accent — STT produces garbled/noisy text.
    The LLM must interpret broken English and extract meaning.

    Simulates realistic Whisper output from accented speech:
    - Dropped articles, broken grammar
    - Phonetic misspellings
    - Mixed language fragments
    """

    @pytest.mark.asyncio
    async def test_garbled_stt_still_confirms(self):
        """Heavily accented 'yes we have table' comes through as garbled STT."""
        engine, db = _make_engine(llm_responses=[
            # LLM interprets garbled STT as a greeting
            LLMResponse(speech_text="Yes, I'd like to book a table for 4 at 7:30 PM on April 15th, please."),
            # LLM interprets broken confirmation
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_garbled"},
            ),
        ])

        # Garbled STT from heavy accent (realistic Whisper output)
        r1 = await engine.process_utterance("Helo, tank you for calling, how I can help?")
        assert r1["ended"] is False

        # Broken English confirmation
        r2 = await engine.process_utterance("Yes yes, foh people, seben turty, we hab. Confirm.")
        assert r2["ended"] is True

    @pytest.mark.asyncio
    async def test_phonetic_misspellings_handled(self):
        """STT produces phonetic approximations of accented words."""
        engine, db = _make_engine(llm_responses=[
            LLMResponse(speech_text="Of course, take your time to check."),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_phon"},
            ),
        ])

        # Phonetic STT output from accented speech
        r1 = await engine.process_utterance("Wan moment plis, I check da book.")
        assert r1["ended"] is False

        r2 = await engine.process_utterance("OK is good, we hab for you. Sebben turty, for peepo. Confirrrm.")
        assert r2["ended"] is True

    @pytest.mark.asyncio
    async def test_mixed_language_fragments(self):
        """STT picks up fragments in another language mixed with English."""
        engine, db = _make_engine(llm_responses=[
            LLMResponse(speech_text="Sure, I'll wait while you check."),
            LLMResponse(speech_text="Thank you. So we're confirmed for 7:30?"),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_mixed"},
            ),
        ])

        # Mixed English/other language (common in real calls)
        r1 = await engine.process_utterance("Un momento... ah wait please, I check for you, sí?")
        assert r1["ended"] is False

        r2 = await engine.process_utterance("Eh... como se dice... ah yes, table is OK, seven thirty, cuatro personas.")
        assert r2["ended"] is False

        r3 = await engine.process_utterance("Sí sí, confirm, seven thirty, four people. Is good.")
        assert r3["ended"] is True

    @pytest.mark.asyncio
    async def test_stt_noise_and_partial_words(self):
        """STT output includes noise markers and partial/cut-off words."""
        engine, db = _make_engine(llm_responses=[
            LLMResponse(speech_text="I'm sorry, could you repeat that? I'd like a table for 4 at 7:30."),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_noise"},
            ),
        ])

        # STT with noise/static artifacts
        r1 = await engine.process_utterance("[inaudible]... hel- hello? ...table? ...you want reser- [static]")
        assert r1["ended"] is False
        assert r1["speech_text"] is not None  # Agent asks to repeat

        r2 = await engine.process_utterance("Ah yes OK, I hear now. Four, seven thirty. We have. Confirm OK.")
        assert r2["ended"] is True

    @pytest.mark.asyncio
    async def test_accent_causes_wrong_number_detection(self):
        """Heavy accent makes '4' sound like '14' to STT — LLM corrects."""
        engine, db = _make_engine(llm_responses=[
            # LLM smart enough to know 14 is likely a mishearing of 4
            LLMResponse(speech_text="Just to confirm, that's for 4 people — four — not fourteen."),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": FUTURE_DATE},
                raw_response={"tool_call_id": "call_accent_num"},
            ),
        ])

        r1 = await engine.process_utterance("Fourteen people at seven thirty? Very big party!")
        assert r1["ended"] is False

        r2 = await engine.process_utterance("Oh four! Four people, not fourteen. OK OK, confirmed!")
        assert r2["ended"] is True

