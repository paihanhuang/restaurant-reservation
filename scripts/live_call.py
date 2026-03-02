#!/usr/bin/env python3
"""Live call — Agent calls YOUR phone via Twilio.

You pick up and play the restaurant. The agent speaks via Twilio TTS
and listens via Twilio's built-in speech recognition. When the
reservation is confirmed, an SMS is sent to your phone.

Architecture:
  1. pyngrok opens a public tunnel to localhost:8000
  2. FastAPI serves webhook routes for the conversation loop
  3. Twilio calls your cell with <Say> greeting + <Gather speech>
  4. Each time you speak, Twilio POSTs the transcript to our webhook
  5. ConversationEngine processes it → returns new <Say> + <Gather>
  6. On confirmation → sends SMS via Twilio

Usage:
    .venv/bin/python scripts/live_call.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import signal
import time
import threading

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from scripts.shared.colors import BLUE, GREEN, YELLOW, RED, CYAN, MAGENTA, BOLD, DIM, RESET
from scripts.shared.sms import send_sms, format_confirmation_sms, format_alternative_sms
from scripts.shared.config import prompt_reservation


def main():
    """Orchestrate the full live call flow."""
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║       📞  LIVE CALL — RESERVATION AGENT OVER THE PHONE  📞    ║
║                                                              ║
║   The agent will call your cell phone via Twilio.            ║
║   Pick up and pretend to be the restaurant staff!            ║
║                                                              ║
║   • Agent speaks via Twilio TTS                              ║
║   • Your speech is transcribed by Twilio STT                 ║
║   • GPT-4o powers the conversation                           ║
║   • SMS sent on confirmation                                 ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")

    # Validate env
    required = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "TWILIO_ACCOUNT_SID": os.environ.get("TWILIO_ACCOUNT_SID"),
        "TWILIO_AUTH_TOKEN": os.environ.get("TWILIO_AUTH_TOKEN"),
        "TWILIO_PHONE_NUMBER": os.environ.get("TWILIO_PHONE_NUMBER"),
        "USER_PHONE": os.environ.get("USER_PHONE"),
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"{RED}❌ Missing env vars: {', '.join(missing)}{RESET}")
        print(f"{DIM}   Set them in .env and try again.{RESET}")
        return

    user_phone = required["USER_PHONE"]
    twilio_phone = required["TWILIO_PHONE_NUMBER"]

    print(f"{GREEN}✓ ENV validated{RESET}")
    print(f"   Twilio from: {twilio_phone}")
    print(f"   Calling to:  {user_phone}")

    # Get reservation details
    reservation = prompt_reservation(
        reservation_id="live-call-001",
        include_extras=False,
    )
    reservation["callback_phone"] = twilio_phone
    reservation["user_phone"] = user_phone

    print(f"\n{DIM}{'─' * 60}{RESET}")
    print(f"{BOLD}🚀 Starting infrastructure...{RESET}\n")

    # 1. Start ngrok tunnel
    print(f"   {YELLOW}⏳ Starting ngrok tunnel...{RESET}", end="", flush=True)
    from pyngrok import ngrok, conf

    # Configure auth token from env
    ngrok_token = os.environ.get("NGROK_AUTHTOKEN", "")
    if ngrok_token:
        ngrok.set_auth_token(ngrok_token)
    else:
        print(f"\n{RED}❌ NGROK_AUTHTOKEN not set in .env{RESET}")
        print(f"{DIM}   1. Get a free token: https://dashboard.ngrok.com/get-started/your-authtoken{RESET}")
        print(f"{DIM}   2. Paste it as NGROK_AUTHTOKEN=... in your .env file{RESET}")
        return

    try:
        tunnel = ngrok.connect(8000, "http")
    except Exception as e:
        print(f"\n{RED}❌ ngrok failed: {e}{RESET}")
        print(f"{DIM}   You may need to run: ngrok config add-authtoken YOUR_TOKEN{RESET}")
        print(f"{DIM}   Get a free token at: https://dashboard.ngrok.com/get-started/your-authtoken{RESET}")
        return

    public_url = tunnel.public_url
    print(f"\r   {GREEN}✓ ngrok tunnel: {public_url}{RESET}")

    # 2. Build and start FastAPI app
    print(f"   {YELLOW}⏳ Starting FastAPI server...{RESET}", end="", flush=True)

    import uvicorn
    from fastapi import FastAPI, Form, Response
    from fastapi.responses import PlainTextResponse
    from unittest.mock import AsyncMock
    from twilio.twiml.voice_response import VoiceResponse, Gather
    from twilio.rest import Client as TwilioClient

    from src.providers.openai_llm import OpenAILLM
    from src.conversation.engine import ConversationEngine
    from src.conversation.state_machine import StateMachine
    from src.models.enums import ReservationStatus
    from src.telephony.voicemail import is_machine, build_voicemail_twiml, VOICEMAIL_TEMPLATE

    app = FastAPI(title="Live Call Server")

    # Shared state
    engine_holder = {
        "engine": None,
        "sms_sent": False,
        "confirmed": False,
        "voicemail_detected": False,
        "attempt": 1,
        "call_sid": None,
    }

    @app.on_event("startup")
    async def setup_engine():
        llm = OpenAILLM(api_key=required["OPENAI_API_KEY"])
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
        engine_holder["engine"] = engine

    @app.post("/voice/answer", response_class=PlainTextResponse)
    async def voice_answer():
        """Twilio hits this when the call is answered. Return greeting + gather."""
        engine = engine_holder["engine"]
        greeting = await engine.generate_greeting()
        print(f"\n  {BLUE}{BOLD}🤖 Agent:{RESET} {greeting}")

        response = VoiceResponse()
        gather = Gather(
            input="speech",
            action=f"{public_url}/voice/respond",
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        gather.say(greeting, voice="Google.en-US-Neural2-F")
        response.append(gather)
        # If no speech detected, prompt again
        response.say("I didn't catch that. Let me try again.", voice="Google.en-US-Neural2-F")
        response.redirect(f"{public_url}/voice/answer")

        return Response(content=str(response), media_type="application/xml")

    @app.post("/voice/respond", response_class=PlainTextResponse)
    async def voice_respond(SpeechResult: str = Form("")):
        """Process each utterance through conversation engine."""
        engine = engine_holder["engine"]
        text = SpeechResult.strip()

        if not text:
            # No speech detected — reprompt
            response = VoiceResponse()
            response.say("I'm sorry, I didn't catch that. Could you repeat?", voice="Google.en-US-Neural2-F")
            gather = Gather(
                input="speech",
                action=f"{public_url}/voice/respond",
                method="POST",
                speech_timeout="auto",
                language="en-US",
            )
            response.append(gather)
            return Response(content=str(response), media_type="application/xml")

        print(f"  {GREEN}{BOLD}🏪 Restaurant:{RESET} {text}")

        # Process through conversation engine
        try:
            result = await engine.process_utterance(text)
        except Exception as e:
            print(f"  {RED}❌ Engine error: {e}{RESET}")
            response = VoiceResponse()
            response.say("I'm having some trouble. Could you repeat that?", voice="Google.en-US-Neural2-F")
            gather = Gather(
                input="speech",
                action=f"{public_url}/voice/respond",
                method="POST",
                speech_timeout="auto",
                language="en-US",
            )
            response.append(gather)
            return Response(content=str(response), media_type="application/xml")

        speech = result.get("speech_text", "")
        action = result.get("action")
        ended = result.get("ended", False)

        print(f"  {DIM}   [DEBUG] action={action}, ended={ended}, speech={'yes' if speech else 'no'}{RESET}")

        if speech:
            print(f"  {BLUE}{BOLD}🤖 Agent:{RESET} {speech}")

        # Handle actions — send SMS in background thread so it doesn't
        # block the TwiML response back to Twilio
        if action:
            if action == "confirm_reservation":
                print(f"\n  {CYAN}⚡ ACTION: {BOLD}CONFIRMED!{RESET}")
                engine_holder["confirmed"] = True
                threading.Thread(
                    target=send_sms,
                    args=(format_confirmation_sms(reservation), required),
                    daemon=True,
                ).start()
            elif action == "propose_alternative":
                print(f"\n  {MAGENTA}⚡ ACTION: {BOLD}ALTERNATIVE PROPOSED{RESET}")
                params = result.get("params", {})
                proposed_time = params.get("proposed_time", "TBD")
                threading.Thread(
                    target=send_sms,
                    args=(format_alternative_sms(reservation, proposed_time), required),
                    daemon=True,
                ).start()
            elif action == "end_call":
                print(f"\n  {YELLOW}⚡ ACTION: {BOLD}CALL ENDED{RESET}")
        else:
            print(f"  {DIM}   [DEBUG] No action in this turn{RESET}")

        # Build TwiML response
        response = VoiceResponse()
        if speech:
            if result.get("ended"):
                # Final message, then hang up
                response.say(speech, voice="Google.en-US-Neural2-F")
                response.hangup()
            else:
                # Say response and gather next input
                gather = Gather(
                    input="speech",
                    action=f"{public_url}/voice/respond",
                    method="POST",
                    speech_timeout="auto",
                    language="en-US",
                )
                gather.say(speech, voice="Google.en-US-Neural2-F")
                response.append(gather)
                # Fallback
                response.say("Are you still there?", voice="Google.en-US-Neural2-F")
                response.redirect(f"{public_url}/voice/respond")
        else:
            response.hangup()

        return Response(content=str(response), media_type="application/xml")

    @app.post("/voice/status")
    async def voice_status():
        """Twilio call status callback."""
        return {"ok": True}

    @app.post("/voice/amd-status")
    async def voice_amd_status(AnsweredBy: str = Form("unknown"), CallSid: str = Form("")):
        """Twilio async AMD status callback."""
        print(f"\n  {DIM}   [AMD] AnsweredBy={AnsweredBy} CallSid={CallSid}{RESET}")

        if is_machine(AnsweredBy):
            engine_holder["voicemail_detected"] = True
            print(f"  {RED}{BOLD}📠 VOICEMAIL DETECTED!{RESET} ({AnsweredBy})")
            print(f"  {DIM}   Leaving voicemail message and hanging up...{RESET}")

            # Modify the in-progress call to play voicemail and hang up
            try:
                twilio_client_inner = TwilioClient(
                    required["TWILIO_ACCOUNT_SID"],
                    required["TWILIO_AUTH_TOKEN"],
                )
                vm_twiml = build_voicemail_twiml(reservation)
                twilio_client_inner.calls(CallSid).update(twiml=vm_twiml)
                print(f"  {GREEN}✓ Voicemail message injected{RESET}")
                print(f"  {YELLOW}   Would retry as attempt {engine_holder['attempt'] + 1}/3{RESET}")
            except Exception as e:
                print(f"  {RED}❌ Failed to inject voicemail: {e}{RESET}")
        else:
            print(f"  {GREEN}✓ Human detected — conversation continues{RESET}")

        return {"ok": True}

    # Start uvicorn in a thread
    import threading

    server_config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(server_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(2)
    print(f"\r   {GREEN}✓ FastAPI running on :8000{RESET}")

    # 3. Place the call
    print(f"\n{DIM}{'─' * 60}{RESET}")
    print(f"{BOLD}{GREEN}☎️  Placing call to {user_phone}...{RESET}")
    print(f"{DIM}   Pick up your phone and pretend to be the restaurant!{RESET}")
    print(f"{DIM}{'─' * 60}{RESET}\n")

    try:
        twilio_client = TwilioClient(
            required["TWILIO_ACCOUNT_SID"],
            required["TWILIO_AUTH_TOKEN"],
        )
        call = twilio_client.calls.create(
            to=user_phone,
            from_=twilio_phone,
            url=f"{public_url}/voice/answer",
            method="POST",
            machine_detection="DetectMessageEnd",
            async_amd_status_callback=f"{public_url}/voice/amd-status",
            async_amd_status_callback_method="POST",
            status_callback=f"{public_url}/voice/status",
            status_callback_event=["completed"],
        )
        engine_holder["call_sid"] = call.sid
        print(f"  {GREEN}✓ Call SID: {call.sid}{RESET}")
        print(f"  {DIM}  Waiting for you to pick up...{RESET}\n")
    except Exception as e:
        print(f"  {RED}❌ Call failed: {e}{RESET}")
        ngrok.disconnect(tunnel.public_url)
        return

    # Wait for call to complete
    try:
        print(f"  {DIM}Press Ctrl+C to end the session{RESET}\n")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}📞 Session ended.{RESET}")
    finally:
        # Give background SMS threads time to complete
        time.sleep(2)

        ngrok.disconnect(tunnel.public_url)
        server.should_exit = True
        print(f"{DIM}{'─' * 60}{RESET}")
        print(f"{BOLD}📊 Call Complete{RESET}")
        engine = engine_holder.get("engine")
        if engine:
            print(f"   Turns: {engine.turn_number}")
            print(f"   Ended: {engine.ended}")
            print(f"   Confirmed: {engine_holder.get('confirmed', False)}")
            print(f"   Voicemail: {engine_holder.get('voicemail_detected', False)}")

            # Fallback: if confirmation happened but SMS didn't send
            if engine_holder.get("confirmed") and not engine_holder.get("sms_sent"):
                print(f"\n  {YELLOW}📱 Sending fallback SMS...{RESET}")
                send_sms(format_confirmation_sms(reservation), required)

        print(f"{DIM}{'─' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
