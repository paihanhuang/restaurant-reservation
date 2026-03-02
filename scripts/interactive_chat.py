#!/usr/bin/env python3
"""Interactive chat — YOU play the restaurant, the AI agent calls you.

Features:
  🔊 Agent speaks its responses aloud via OpenAI TTS
  📞 Agent can provide a callback phone number when asked
  📱 Sends real SMS to your cell on confirmation/alternative
  🧠 Real GPT-4o powers the conversation

Usage:
    .venv/bin/python scripts/interactive_chat.py
    .venv/bin/python scripts/interactive_chat.py --no-voice   # text only
    .venv/bin/python scripts/interactive_chat.py --no-sms     # skip SMS

Type 'quit' or 'exit' at any prompt to hang up.
"""

from __future__ import annotations

import asyncio
import os
import sys
import subprocess
import tempfile
import struct
import wave
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from datetime import date, time, timedelta
from unittest.mock import AsyncMock
from openai import AsyncOpenAI

from src.providers.openai_llm import OpenAILLM
from src.conversation.engine import ConversationEngine
from src.conversation.state_machine import StateMachine
from src.models.enums import ReservationStatus

from scripts.shared.colors import BLUE, GREEN, YELLOW, RED, CYAN, MAGENTA, BOLD, DIM, RESET
from scripts.shared.sms import send_sms, format_confirmation_sms, format_alternative_sms
from scripts.shared.config import prompt_reservation


class TTSPlayer:
    """Plays text as speech using OpenAI TTS + aplay."""

    def __init__(self, api_key: str, voice: str = "alloy"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.voice = voice

    async def speak(self, text: str) -> None:
        """Synthesize text to speech and play it through speakers."""
        if not text:
            return

        try:
            # Get audio from OpenAI TTS (PCM format: 24kHz 16-bit mono)
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice=self.voice,
                input=text,
                response_format="pcm",
            )

            # Read all PCM bytes
            pcm_data = response.read()

            # Write to temp WAV file for aplay
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name
                with wave.open(f, 'wb') as wav:
                    wav.setnchannels(1)        # mono
                    wav.setsampwidth(2)         # 16-bit
                    wav.setframerate(24000)     # 24kHz
                    wav.writeframes(pcm_data)

            # Play via aplay (blocking)
            subprocess.run(
                ["aplay", "-q", tmp_path],
                capture_output=True,
                timeout=30,
            )

        except Exception as e:
            print(f"  {DIM}   🔇 Audio playback error: {e}{RESET}")
        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def print_banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║          🍽️  RESERVATION AGENT — INTERACTIVE CHAT  🍽️          ║
║                                                              ║
║   You are the restaurant staff. The AI agent is calling you  ║
║   to book a table. Respond however you like!                 ║
║                                                              ║
║   • 🔊 Agent speaks its responses aloud                      ║
║   • 📱 Real SMS on confirmation!                             ║
║   • Ask for a callback number — the agent has one!           ║
║   • Type 'quit' to hang up                                   ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def get_reservation_config() -> dict:
    """Prompt user for reservation details or use defaults."""
    return prompt_reservation(
        reservation_id="interactive-001",
        include_extras=True,
    )


async def run_interactive(use_voice: bool = True, use_sms: bool = True):
    """Run the interactive chat loop."""
    print_banner()

    # Check for API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(f"{RED}❌ OPENAI_API_KEY not found in .env — cannot start.{RESET}")
        return

    # Get reservation config
    reservation = get_reservation_config()
    voice = reservation.pop("_voice", "nova")

    # Set up TTS player
    tts_player = None
    if use_voice:
        tts_player = TTSPlayer(api_key=api_key, voice=voice)
        print(f"\n{GREEN}   🔊 Voice enabled ({voice}){RESET}")
    else:
        print(f"\n{YELLOW}   🔇 Voice disabled (text only){RESET}")

    # Set up SMS
    sms_enabled = use_sms and os.environ.get("USER_PHONE", "") not in ("", "+1XXXXXXXXXX")
    if sms_enabled:
        print(f"{GREEN}   📱 SMS enabled → {os.environ.get('USER_PHONE')}{RESET}")
    elif use_sms:
        print(f"{YELLOW}   📱 SMS disabled — set USER_PHONE in .env{RESET}")
        sms_enabled = False

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

    # Speak the greeting
    if tts_player:
        await tts_player.speak(greeting)

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
        speech = result.get("speech_text")
        if speech:
            print(f"  {BLUE}{BOLD}🤖 Agent:{RESET} {speech}\n")

            # Speak it!
            if tts_player:
                await tts_player.speak(speech)

        # Display action and send SMS
        if result.get("action"):
            action = result["action"]
            if action == "confirm_reservation":
                print(f"  {CYAN}⚡ ACTION: {BOLD}CONFIRMED{RESET}")
                print(f"  {CYAN}   The reservation has been confirmed!{RESET}\n")
                if sms_enabled:
                    send_sms(format_confirmation_sms(reservation))

            elif action == "propose_alternative":
                proposed = result.get("params", {}).get("time", "TBD")
                print(f"  {MAGENTA}⚡ ACTION: {BOLD}ALTERNATIVE PROPOSED{RESET}")
                print(f"  {MAGENTA}   Proposed time: {proposed}{RESET}")
                print(f"  {MAGENTA}   Agent will check with the guest and call back.{RESET}\n")
                if sms_enabled:
                    send_sms(format_alternative_sms(reservation, proposed))

            elif action == "end_call":
                print(f"  {YELLOW}⚡ ACTION: {BOLD}CALL ENDED{RESET}")
                reason = result.get("action_result", "")
                print(f"  {YELLOW}   {reason}{RESET}\n")
                if sms_enabled:
                    send_sms(
                        f"😔 Reservation Not Available\n\n"
                        f"📍 {reservation['restaurant_name']}\n"
                        f"📅 {reservation['date']} at {reservation['preferred_time']}\n\n"
                        f"Reason: {reason or 'Could not complete booking'}"
                    )

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
    if sms_enabled:
        print(f"   SMS sent to: {os.environ.get('USER_PHONE')}")
    print(f"{DIM}{'─' * 60}{RESET}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interactive reservation agent chat")
    parser.add_argument("--no-voice", action="store_true", help="Disable TTS voice (text only)")
    parser.add_argument("--no-sms", action="store_true", help="Disable SMS notifications")
    args = parser.parse_args()

    asyncio.run(run_interactive(use_voice=not args.no_voice, use_sms=not args.no_sms))
