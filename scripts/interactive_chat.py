#!/usr/bin/env python3
"""Interactive chat — YOU play the restaurant, the AI agent calls you.

Usage:
    .venv/bin/python scripts/interactive_chat.py

You'll be prompted to type restaurant responses. The agent uses your real
OpenAI API key (from .env) to generate intelligent replies, handle
misunderstandings, and decide when to confirm/propose/end the call.

Type 'quit' or 'exit' at any prompt to hang up.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from datetime import date, time, timedelta
from unittest.mock import AsyncMock

from src.providers.openai_llm import OpenAILLM
from src.conversation.engine import ConversationEngine
from src.conversation.state_machine import StateMachine
from src.models.enums import ReservationStatus


# ── ANSI colors ──────────────────────────────────────────────────────────
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║          🍽️  RESERVATION AGENT — INTERACTIVE CHAT  🍽️          ║
║                                                              ║
║   You are the restaurant staff. The AI agent is calling you  ║
║   to book a table. Respond however you like!                 ║
║                                                              ║
║   • Speak broken English         • Misunderstand requests    ║
║   • Put the agent on hold        • Be fully booked           ║
║   • Confirm or propose times     • Type 'quit' to hang up   ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def get_reservation_config() -> dict:
    """Prompt user for reservation details or use defaults."""
    print(f"{BOLD}📋 Reservation Details{RESET}")
    print(f"{DIM}   (Press Enter to use defaults){RESET}\n")

    restaurant = input(f"   Restaurant name {DIM}[Bella Italia]{RESET}: ").strip()
    if not restaurant:
        restaurant = "Bella Italia"

    date_str = input(f"   Date {DIM}[{(date.today() + timedelta(days=7)).isoformat()}]{RESET}: ").strip()
    if not date_str:
        date_str = (date.today() + timedelta(days=7)).isoformat()

    time_str = input(f"   Preferred time {DIM}[19:30]{RESET}: ").strip()
    if not time_str:
        time_str = "19:30"

    party_str = input(f"   Party size {DIM}[4]{RESET}: ").strip()
    party_size = int(party_str) if party_str else 4

    special = input(f"   Special requests {DIM}[none]{RESET}: ").strip() or None

    flex = input(f"   Flexible time window? {DIM}(e.g. 18:00-21:00 or Enter for none){RESET}: ").strip()
    alt_start = alt_end = None
    if flex and "-" in flex:
        parts = flex.split("-")
        alt_start = parts[0].strip()
        alt_end = parts[1].strip()

    return {
        "reservation_id": "interactive-001",
        "restaurant_name": restaurant,
        "restaurant_phone": "+14155551234",
        "date": date_str,
        "preferred_time": time_str,
        "party_size": party_size,
        "status": ReservationStatus.CALLING,
        "special_requests": special,
        "alt_time_start": alt_start,
        "alt_time_end": alt_end,
    }


async def run_interactive():
    """Run the interactive chat loop."""
    print_banner()

    # Check for API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(f"{RED}❌ OPENAI_API_KEY not found in .env — cannot start.{RESET}")
        return

    # Get reservation config
    reservation = get_reservation_config()

    print(f"\n{DIM}{'─' * 60}{RESET}")
    print(f"{BOLD}{GREEN}☎️  Ring ring... The agent is calling {reservation['restaurant_name']}!{RESET}")
    print(f"{DIM}{'─' * 60}{RESET}\n")

    # Set up real LLM + mocked DB
    llm = OpenAILLM(api_key=api_key)
    db = AsyncMock()
    sm = StateMachine(db)
    tts = AsyncMock()
    stt = AsyncMock()

    engine = ConversationEngine(
        reservation_id=reservation["reservation_id"],
        reservation=reservation,
        llm=llm,
        tts=tts,
        stt=stt,
        db=db,
        state_machine=sm,
    )

    # Generate and display greeting
    greeting = await engine.generate_greeting()
    print(f"  {BLUE}{BOLD}🤖 Agent:{RESET} {greeting}\n")

    # Chat loop
    turn = 0
    while not engine.ended:
        turn += 1
        # Get restaurant response from user
        try:
            user_input = input(f"  {GREEN}{BOLD}🏪 You (restaurant):{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n  {YELLOW}📞 Call disconnected.{RESET}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "bye", "hang up"):
            print(f"\n  {YELLOW}📞 You hung up the phone.{RESET}")
            break

        # Process through real LLM
        try:
            print(f"  {DIM}   ⏳ Agent is thinking...{RESET}", end="\r")
            result = await engine.process_utterance(user_input)
            print(f"  {' ' * 30}", end="\r")  # Clear "thinking" line
        except Exception as e:
            print(f"\n  {RED}❌ Error: {e}{RESET}")
            continue

        # Display agent response
        if result.get("speech_text"):
            print(f"  {BLUE}{BOLD}🤖 Agent:{RESET} {result['speech_text']}\n")

        # Display action if any
        if result.get("action"):
            action = result["action"]
            if action == "confirm_reservation":
                print(f"  {CYAN}⚡ ACTION: {BOLD}CONFIRMED{RESET}")
                print(f"  {CYAN}   The reservation has been confirmed!{RESET}\n")
            elif action == "propose_alternative":
                print(f"  {MAGENTA}⚡ ACTION: {BOLD}ALTERNATIVE PROPOSED{RESET}")
                print(f"  {MAGENTA}   Agent will check with the guest and call back.{RESET}\n")
            elif action == "end_call":
                print(f"  {YELLOW}⚡ ACTION: {BOLD}CALL ENDED{RESET}")
                reason = result.get("action_result", "")
                print(f"  {YELLOW}   {reason}{RESET}\n")

        if result.get("ended"):
            break

    # Summary
    print(f"\n{DIM}{'─' * 60}{RESET}")
    print(f"{BOLD}📊 Call Summary{RESET}")
    print(f"   Turns: {engine.turn_number}")
    print(f"   Messages: {len(engine.messages)}")

    # Check final state from DB calls
    ended_status = "unknown"
    for call in db.update_reservation.call_args_list:
        kwargs = call[1] if call[1] else {}
        if "status" in kwargs:
            ended_status = kwargs["status"]
    print(f"   Final status: {ended_status}")
    print(f"{DIM}{'─' * 60}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(run_interactive())
