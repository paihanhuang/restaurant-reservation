"""Voicemail detection and message handling.

Provides utilities to detect answering machines from Twilio's AMD
(Answering Machine Detection) and generate TwiML for leaving a
voicemail message.
"""

from __future__ import annotations

from twilio.twiml.voice_response import VoiceResponse


# Twilio AnsweredBy values that indicate a machine
_MACHINE_VALUES = frozenset({
    "machine_start",
    "machine_end_beep",
    "machine_end_silence",
    "machine_end_other",
    "fax",
})

# Template for the voicemail message
VOICEMAIL_TEMPLATE = (
    "Hi, this is an automated call regarding a reservation at {restaurant_name} "
    "for {party_size} guests on {date} at {preferred_time}. "
    "We'll try calling again shortly. Thank you!"
)


def is_machine(answered_by: str) -> bool:
    """Check if a Twilio AnsweredBy value indicates an answering machine.

    Args:
        answered_by: The AnsweredBy value from Twilio AMD callback.
            Expected values: human, machine_start, machine_end_beep,
            machine_end_silence, machine_end_other, fax, unknown.

    Returns:
        True if the call was answered by a machine, False otherwise.
        Defaults to False for unknown/missing values (safe fallback).
    """
    return answered_by.lower().strip() in _MACHINE_VALUES


def build_voicemail_twiml(reservation: dict) -> str:
    """Build TwiML that leaves a voicemail message and hangs up.

    Waits a beat for the voicemail beep, then speaks the message.

    Args:
        reservation: Dict with restaurant_name, party_size, date,
            preferred_time.

    Returns:
        TwiML XML string.
    """
    message = VOICEMAIL_TEMPLATE.format(
        restaurant_name=reservation.get("restaurant_name", "your restaurant"),
        party_size=reservation.get("party_size", ""),
        date=reservation.get("date", ""),
        preferred_time=reservation.get("preferred_time", ""),
    )

    response = VoiceResponse()
    response.pause(length=1)  # Wait for beep to finish
    response.say(message, voice="Polly.Joanna")
    response.hangup()
    return str(response)
