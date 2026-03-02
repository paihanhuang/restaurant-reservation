"""Shared reservation config prompts for scripts."""

from __future__ import annotations

import os
from datetime import date, timedelta

from scripts.shared.colors import BOLD, DIM, RESET


def prompt_reservation(
    reservation_id: str = "interactive-001",
    include_extras: bool = True,
) -> dict:
    """Prompt user for reservation details with sensible defaults.

    Args:
        reservation_id: ID to assign to the reservation.
        include_extras: If True, also prompt for special requests,
            time flexibility, callback phone, and TTS voice.

    Returns:
        Reservation dict ready for ConversationEngine.
    """
    print(f"{BOLD}📋 Reservation Details{RESET}")
    print(f"{DIM}   (Press Enter to use defaults){RESET}\n")

    default_date = (date.today() + timedelta(days=7)).isoformat()

    restaurant = input(f"   Restaurant name {DIM}[Bella Italia]{RESET}: ").strip() or "Bella Italia"
    date_str = input(f"   Date {DIM}[{default_date}]{RESET}: ").strip() or default_date
    time_str = input(f"   Preferred time {DIM}[19:30]{RESET}: ").strip() or "19:30"
    party_str = input(f"   Party size {DIM}[4]{RESET}: ").strip() or "4"

    reservation = {
        "reservation_id": reservation_id,
        "restaurant_name": restaurant,
        "date": date_str,
        "preferred_time": time_str,
        "party_size": int(party_str),
        "status": "calling",
    }

    if include_extras:
        special = input(f"   Special requests {DIM}[none]{RESET}: ").strip() or None
        flex = input(f"   Flexible time window? {DIM}(e.g. 18:00-21:00 or Enter for none){RESET}: ").strip()
        alt_start = alt_end = None
        if flex and "-" in flex:
            parts = flex.split("-")
            alt_start = parts[0].strip()
            alt_end = parts[1].strip()

        twilio_phone = os.environ.get("TWILIO_PHONE_NUMBER", "")
        default_phone = twilio_phone or "+14155551234"
        phone = input(f"   Callback phone {DIM}[{default_phone}]{RESET}: ").strip() or default_phone

        print(f"\n{BOLD}🔊 TTS Voice{RESET}")
        print(f"   {DIM}Available: alloy, echo, fable, onyx, nova, shimmer{RESET}")
        voice = input(f"   Voice {DIM}[nova]{RESET}: ").strip() or "nova"

        reservation.update({
            "restaurant_phone": "+14155551234",
            "special_requests": special,
            "alt_time_start": alt_start,
            "alt_time_end": alt_end,
            "callback_phone": phone,
            "_voice": voice,
        })

    return reservation
