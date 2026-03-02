"""Local call simulator — runs full pipeline without Twilio.

Simulates a WebSocket call with pre-scripted restaurant responses.
Tests the full pipeline: greeting → STT → LLM → TTS → state transitions.
"""

from __future__ import annotations

import asyncio
import sys
import os
from datetime import date, time, timedelta
from unittest.mock import AsyncMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.providers.base import LLMResponse
from src.conversation.engine import ConversationEngine
from src.conversation.state_machine import StateMachine
from src.models.enums import ReservationStatus


# Pre-scripted restaurant responses for different scenarios
SCENARIOS = {
    "happy_path": [
        "Hello, thank you for calling Bella Italia, how can I help you?",
        "Let me check... Yes, we have a table for 4 at 7:30 PM on April 15th.",
        "Perfect, you're all set. The reservation is confirmed under what name?",
    ],
    "negotiation": [
        "Hello, Chez Michel speaking.",
        "I'm sorry, 7:30 is fully booked. We do have availability at 8:30 PM though.",
    ],
    "rejection": [
        "Good evening, Golden Dragon.",
        "I'm sorry, we're completely booked for that entire evening. No availability at all.",
    ],
    "hold": [
        "Thank you for calling. Please hold while I check.",
        "...",  # silence/hold
        "Sorry about the wait. Yes, we can do 7:30 for 4 people.",
    ],
}


def create_mock_llm(scenario: str):
    """Create a mock LLM that responds appropriately to each scenario."""
    llm = AsyncMock()

    if scenario == "happy_path":
        llm.chat.side_effect = [
            LLMResponse(speech_text="Yes, that would be wonderful, thank you!"),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": "2026-04-15"},
                raw_response={"tool_call_id": "call_1"},
            ),
            LLMResponse(speech_text="The name is Johnson. Thank you so much!"),
        ]
    elif scenario == "negotiation":
        llm.chat.side_effect = [
            LLMResponse(speech_text="I see. Let me check on that alternative time."),
            LLMResponse(
                action="propose_alternative",
                params={"proposed_time": "20:30", "reason": "7:30 fully booked"},
                raw_response={"tool_call_id": "call_2"},
            ),
        ]
    elif scenario == "rejection":
        llm.chat.side_effect = [
            LLMResponse(speech_text="I understand."),
            LLMResponse(
                action="end_call",
                params={"reason": "fully booked", "outcome": "no_availability"},
                raw_response={"tool_call_id": "call_3"},
            ),
        ]
    elif scenario == "hold":
        llm.chat.side_effect = [
            LLMResponse(speech_text="Of course, take your time."),
            LLMResponse(speech_text="No problem at all."),
            LLMResponse(
                action="confirm_reservation",
                params={"confirmed_time": "19:30", "confirmed_date": "2026-04-15"},
                raw_response={"tool_call_id": "call_4"},
            ),
        ]

    return llm


async def run_scenario(name: str, responses: list[str]):
    """Run a single simulation scenario."""
    print(f"\n{'='*60}")
    print(f"📞 SCENARIO: {name.upper().replace('_', ' ')}")
    print(f"{'='*60}")

    # Set up engine with mocks
    reservation = {
        "reservation_id": f"sim-{name}-001",
        "restaurant_name": "Test Restaurant",
        "restaurant_phone": "+14155551234",
        "date": "2026-04-15",
        "preferred_time": "19:30",
        "party_size": 4,
        "status": ReservationStatus.CALLING,
        "special_requests": None,
        "alt_time_start": "18:00" if name == "negotiation" else None,
        "alt_time_end": "20:00" if name == "negotiation" else None,
    }

    db = AsyncMock()
    llm = create_mock_llm(name)
    tts = AsyncMock()
    stt = AsyncMock()
    sm = StateMachine(db)

    engine = ConversationEngine(
        reservation_id=reservation["reservation_id"],
        reservation=reservation,
        llm=llm,
        tts=tts,
        stt=stt,
        db=db,
        state_machine=sm,
    )

    # Generate greeting
    greeting = await engine.generate_greeting()
    print(f"\n  🤖 Agent: {greeting}")

    # Process each restaurant response
    for i, response in enumerate(responses):
        print(f"\n  🏪 Restaurant: {response}")

        if response == "...":
            print(f"  ⏳ (hold/silence)")
            continue

        result = await engine.process_utterance(response)

        if result.get("speech_text"):
            print(f"  🤖 Agent: {result['speech_text']}")

        if result.get("action"):
            print(f"  ⚡ Action: {result['action']}")

        if result.get("ended"):
            print(f"\n  ✅ Call ended")
            break

    # Log final state
    final_status = "unknown"
    if db.update_reservation.call_args_list:
        for call in db.update_reservation.call_args_list:
            if "status" in (call[1] if call[1] else {}):
                final_status = call[1]["status"]
    print(f"  📊 Final status: {final_status}")
    print(f"  📝 Total turns: {engine.turn_number}")

    return final_status


async def main():
    """Run all simulation scenarios."""
    print("🚀" * 30)
    print("  RESERVATION AGENT — CALL SIMULATOR")
    print("🚀" * 30)

    results = {}
    for name, responses in SCENARIOS.items():
        try:
            status = await run_scenario(name, responses)
            results[name] = status
        except Exception as e:
            print(f"\n  ❌ ERROR: {e}")
            results[name] = "error"

    print(f"\n{'='*60}")
    print(f"📊 SIMULATION RESULTS")
    print(f"{'='*60}")
    for name, status in results.items():
        icon = "✅" if status in ("confirmed", "alternative_proposed", "failed") else "❌"
        print(f"  {icon} {name.replace('_', ' ').title()}: {status}")

    print(f"\n{'='*60}")
    print(f"🎉 ALL {len(results)} SCENARIOS COMPLETED")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
