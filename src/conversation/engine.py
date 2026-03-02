"""Conversation engine — manages the STT→LLM→TTS loop for a single call.

Orchestrates the dialogue between the agent and the restaurant:
1. Receives transcribed utterances from the restaurant
2. Sends them to the LLM for processing
3. Handles function calls (confirm, propose_alternative, end_call)
4. Generates speech responses via TTS
5. Logs transcript turns to the database
"""

from __future__ import annotations

import structlog
from datetime import datetime, date, time

from src.providers.base import LLMProvider, TTSProvider, STTProvider, Database, SessionStore
from src.conversation.prompts import build_system_prompt, build_greeting
from src.conversation.state_machine import StateMachine
from src.conversation.validators import (
    parse_time_strict,
    parse_date_strict,
    validate_proposed_time,
    validate_confirmed_date,
)
from src.models.enums import ReservationStatus

logger = structlog.get_logger()


class ConversationEngine:
    """Manages a single reservation call conversation."""

    def __init__(
        self,
        reservation_id: str,
        reservation: dict,
        llm: LLMProvider,
        tts: TTSProvider,
        stt: STTProvider,
        db: Database,
        state_machine: StateMachine,
    ):
        self.reservation_id = reservation_id
        self.reservation = reservation
        self.llm = llm
        self.tts = tts
        self.stt = stt
        self.db = db
        self.state_machine = state_machine
        self.call_sid: str | None = None
        self.turn_number = 0
        self.ended = False

        # Build system prompt from reservation details
        alt_start = None
        alt_end = None
        if reservation.get("alt_time_start"):
            alt_start = time.fromisoformat(reservation["alt_time_start"])
        if reservation.get("alt_time_end"):
            alt_end = time.fromisoformat(reservation["alt_time_end"])

        self.system_prompt = build_system_prompt(
            restaurant_name=reservation["restaurant_name"],
            reservation_date=date.fromisoformat(reservation["date"]),
            preferred_time=time.fromisoformat(reservation["preferred_time"]),
            party_size=reservation["party_size"],
            special_requests=reservation.get("special_requests"),
            alt_time_start=alt_start,
            alt_time_end=alt_end,
            callback_phone=reservation.get("callback_phone"),
        )

        # Conversation messages (OpenAI format)
        self.messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
        ]

    async def generate_greeting(self) -> str:
        """Generate the opening greeting for the call.

        Returns:
            Greeting text for TTS synthesis.
        """
        greeting = build_greeting(
            restaurant_name=self.reservation["restaurant_name"],
            reservation_date=date.fromisoformat(self.reservation["date"]),
            preferred_time=time.fromisoformat(self.reservation["preferred_time"]),
            party_size=self.reservation["party_size"],
        )

        # Add to conversation history
        self.messages.append({"role": "assistant", "content": greeting})

        # Log the greeting turn
        await self._log_turn("assistant", greeting)

        return greeting

    async def process_utterance(self, text: str) -> dict:
        """Process a transcribed restaurant utterance and generate a response.

        Args:
            text: Transcribed text from the restaurant staff.

        Returns:
            Dict with:
              - speech_text: Text to synthesize and speak back (or None)
              - action: Function call name if any (confirm/propose/end)
              - ended: Whether the conversation has ended
        """
        if self.ended:
            return {"speech_text": None, "action": None, "ended": True}

        # Log restaurant's turn
        await self._log_turn("user", text)
        self.messages.append({"role": "user", "content": text})

        # Get LLM response
        response = await self.llm.chat(self.messages)

        result = {"speech_text": None, "action": None, "ended": False}

        if response.action:
            # Handle function call
            result = await self._handle_action(response.action, response.params or {})

            # Add function call + result to messages for context
            self.messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": response.raw_response.get("tool_call_id", "call_1") if response.raw_response else "call_1",
                    "type": "function",
                    "function": {
                        "name": response.action,
                        "arguments": str(response.params),
                    },
                }],
            })
            self.messages.append({
                "role": "tool",
                "tool_call_id": response.raw_response.get("tool_call_id", "call_1") if response.raw_response else "call_1",
                "content": f"Action {response.action} processed. Result: {result.get('action_result', 'ok')}",
            })

            # If action produced speech, get LLM to generate next words
            if not self.ended and result.get("needs_response"):
                follow_up = await self.llm.chat(self.messages)
                if follow_up.speech_text:
                    result["speech_text"] = follow_up.speech_text
                    self.messages.append({"role": "assistant", "content": follow_up.speech_text})
                    await self._log_turn("assistant", follow_up.speech_text)

        elif response.speech_text:
            # Regular speech response
            result["speech_text"] = response.speech_text
            self.messages.append({"role": "assistant", "content": response.speech_text})
            await self._log_turn("assistant", response.speech_text)

        result["ended"] = self.ended
        return result

    async def _handle_action(self, action: str, params: dict) -> dict:
        """Handle a function call from the LLM.

        Returns:
            Dict with action result and any speech to generate.
        """
        result = {"action": action, "action_result": "ok", "needs_response": False}

        if action == "confirm_reservation":
            result = await self._handle_confirm(params)
        elif action == "propose_alternative":
            result = await self._handle_propose_alternative(params)
        elif action == "end_call":
            result = await self._handle_end_call(params)
        else:
            logger.warning("engine.unknown_action", action=action, reservation_id=self.reservation_id)
            result["action_result"] = f"Unknown action: {action}"

        return result

    async def _handle_confirm(self, params: dict) -> dict:
        """Handle a confirm_reservation function call."""
        try:
            confirmed_time = parse_time_strict(params.get("confirmed_time", ""))
            confirmed_date_str = params.get("confirmed_date", self.reservation["date"])
            confirmed_date = parse_date_strict(confirmed_date_str)

            # Validate date matches
            expected_date = date.fromisoformat(self.reservation["date"])
            if not validate_confirmed_date(confirmed_date, expected_date):
                return {
                    "action": "confirm_reservation",
                    "action_result": f"Date mismatch: confirmed {confirmed_date} but reservation is for {expected_date}. Please verify.",
                    "needs_response": True,
                }

            # Transition state
            await self.state_machine.transition(
                self.reservation_id,
                from_state=ReservationStatus.CALLING,
                to_state=ReservationStatus.CONFIRMED,
                trigger="llm_confirm",
                metadata={"confirmed_time": str(confirmed_time), "confirmed_date": str(confirmed_date)},
            )

            # Update reservation with confirmed time
            await self.db.update_reservation(
                self.reservation_id,
                confirmed_time=str(confirmed_time),
                status=ReservationStatus.CONFIRMED,
            )

            self.ended = True
            logger.info("engine.confirmed", reservation_id=self.reservation_id, time=str(confirmed_time))

            return {
                "action": "confirm_reservation",
                "action_result": "Reservation confirmed",
                "speech_text": f"Thank you so much, we're all set for {confirmed_time.strftime('%I:%M %p')}. Have a great evening!",
                "needs_response": False,
            }

        except ValueError as e:
            logger.warning("engine.confirm_validation_error", error=str(e), reservation_id=self.reservation_id)
            return {
                "action": "confirm_reservation",
                "action_result": f"Validation error: {e}. Please use HH:MM format.",
                "needs_response": True,
            }

    async def _handle_propose_alternative(self, params: dict) -> dict:
        """Handle a propose_alternative function call."""
        try:
            proposed_time = parse_time_strict(params.get("proposed_time", ""))
            reason = params.get("reason", "")

            # Check if within user's flexibility window
            alt_start = None
            alt_end = None
            if self.reservation.get("alt_time_start"):
                alt_start = time.fromisoformat(self.reservation["alt_time_start"])
            if self.reservation.get("alt_time_end"):
                alt_end = time.fromisoformat(self.reservation["alt_time_end"])

            within_bounds = validate_proposed_time(proposed_time, alt_start, alt_end)

            if within_bounds:
                # Auto-accept: within flexibility range → confirm directly
                return await self._handle_confirm({
                    "confirmed_time": str(proposed_time),
                    "confirmed_date": params.get("proposed_date", self.reservation["date"]),
                })
            else:
                # Outside bounds: transition to alternative_proposed, await user decision
                await self.state_machine.transition(
                    self.reservation_id,
                    from_state=ReservationStatus.CALLING,
                    to_state=ReservationStatus.ALTERNATIVE_PROPOSED,
                    trigger="llm_propose_alt",
                    metadata={"proposed_time": str(proposed_time), "reason": reason},
                )

                self.ended = True
                logger.info(
                    "engine.alt_proposed",
                    reservation_id=self.reservation_id,
                    proposed_time=str(proposed_time),
                )

                return {
                    "action": "propose_alternative",
                    "action_result": "Alternative proposed, awaiting user confirmation",
                    "speech_text": "Thank you, let me check with the guest and get back to you. I'll call back shortly.",
                    "needs_response": False,
                }

        except ValueError as e:
            logger.warning("engine.alt_validation_error", error=str(e), reservation_id=self.reservation_id)
            return {
                "action": "propose_alternative",
                "action_result": f"Validation error: {e}. Please use HH:MM format.",
                "needs_response": True,
            }

    async def _handle_end_call(self, params: dict) -> dict:
        """Handle an end_call function call."""
        reason = params.get("reason", "unknown")
        outcome = params.get("outcome", "completed")

        # Transition to failed (unless we're already in a terminal state)
        if not self.state_machine.is_terminal(self.reservation.get("status", "calling")):
            await self.state_machine.transition(
                self.reservation_id,
                from_state=ReservationStatus.CALLING,
                to_state=ReservationStatus.FAILED,
                trigger="llm_end_call",
                metadata={"reason": reason, "outcome": outcome},
            )

        self.ended = True
        logger.info("engine.ended", reservation_id=self.reservation_id, reason=reason)

        goodbye = "Alright, thank you for your time. Have a good evening!"
        return {
            "action": "end_call",
            "action_result": f"Call ended: {reason}",
            "speech_text": goodbye,
            "needs_response": False,
        }

    async def finalize(self) -> None:
        """Called when the call ends — cleanup and persist state."""
        logger.info("engine.finalize", reservation_id=self.reservation_id, turns=self.turn_number)

    async def _log_turn(self, role: str, text: str) -> None:
        """Log a transcript turn to the database."""
        self.turn_number += 1
        if self.db and self.call_sid:
            try:
                await self.db.append_transcript_turn(
                    self.reservation_id,
                    self.call_sid,
                    {
                        "role": role,
                        "text": text,
                        "turn_number": self.turn_number,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            except Exception as e:
                logger.error("engine.log_turn_error", error=str(e))
