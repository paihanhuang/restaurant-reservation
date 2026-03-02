"""Shared SMS helper for scripts — sync-only, thread-safe."""

from __future__ import annotations

import os

from scripts.shared.colors import GREEN, RED, RESET, DIM


def send_sms(body: str, env: dict | None = None) -> bool:
    """Send an SMS via Twilio. Sync call — safe for background threads.

    Args:
        body: Message body.
        env: Optional dict with TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
             TWILIO_PHONE_NUMBER, USER_PHONE. Falls back to os.environ.

    Returns:
        True if sent, False otherwise.
    """
    env = env or {}
    sid = env.get("TWILIO_ACCOUNT_SID") or os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = env.get("TWILIO_AUTH_TOKEN") or os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_phone = env.get("TWILIO_PHONE_NUMBER") or os.environ.get("TWILIO_PHONE_NUMBER", "")
    to_phone = env.get("USER_PHONE") or os.environ.get("USER_PHONE", "")

    if not all([sid, token, from_phone, to_phone, to_phone != "+1XXXXXXXXXX"]):
        print(f"  {DIM}   [SMS] Skipped — missing credentials or placeholder phone{RESET}")
        return False

    print(f"  {DIM}   [SMS] Sending to {to_phone}...{RESET}")
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        msg = client.messages.create(body=body, from_=from_phone, to=to_phone)
        print(f"  {GREEN}📱 SMS sent! SID: {msg.sid}{RESET}")
        return True
    except Exception as e:
        print(f"  {RED}📱 SMS FAILED: {type(e).__name__}: {e}{RESET}")
        return False


def format_confirmation_sms(reservation: dict) -> str:
    """Format a reservation confirmation SMS body."""
    return (
        f"🎉 Reservation Confirmed!\n\n"
        f"📍 {reservation.get('restaurant_name', 'Restaurant')}\n"
        f"📅 {reservation.get('date', '')}\n"
        f"⏰ {reservation.get('preferred_time', '')}\n"
        f"👥 Party of {reservation.get('party_size', '')}\n\n"
        f"Enjoy your dinner!"
    )


def format_alternative_sms(reservation: dict, proposed_time: str = "TBD") -> str:
    """Format an alternative proposal SMS body."""
    return (
        f"⏰ Alternative Time Proposed\n\n"
        f"📍 {reservation.get('restaurant_name', 'Restaurant')}\n"
        f"📅 {reservation.get('date', '')}\n"
        f"⏰ Original: {reservation.get('preferred_time', '')}\n"
        f"⏰ Proposed: {proposed_time}\n"
        f"👥 Party of {reservation.get('party_size', '')}\n\n"
        f"Reply YES to confirm or NO to reject."
    )
