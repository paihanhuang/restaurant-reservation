"""Conversation prompts — system prompt and greeting templates."""

from __future__ import annotations

from datetime import date, time


def build_system_prompt(
    restaurant_name: str,
    reservation_date: date,
    preferred_time: time,
    party_size: int,
    special_requests: str | None = None,
    alt_time_start: time | None = None,
    alt_time_end: time | None = None,
    callback_phone: str | None = None,
) -> str:
    """Build the system prompt for the LLM with reservation details.

    Args:
        restaurant_name: Name of the restaurant.
        reservation_date: Date of the reservation.
        preferred_time: Preferred time.
        party_size: Number of guests.
        special_requests: Any special requests.
        alt_time_start: Start of acceptable alternative time range.
        alt_time_end: End of acceptable alternative time range.
        callback_phone: Phone number the restaurant can call back on.

    Returns:
        System prompt string.
    """
    time_str = preferred_time.strftime("%I:%M %p")
    date_str = reservation_date.strftime("%A, %B %d, %Y")

    flexibility_section = ""
    if alt_time_start and alt_time_end:
        alt_start_str = alt_time_start.strftime("%I:%M %p")
        alt_end_str = alt_time_end.strftime("%I:%M %p")
        flexibility_section = f"""
## Flexibility
The customer is flexible between {alt_start_str} and {alt_end_str}.
If the restaurant proposes a time WITHIN this range, you may accept it automatically by calling `confirm_reservation`.
If the restaurant proposes a time OUTSIDE this range, call `propose_alternative` to relay it to the customer for approval.
"""
    else:
        flexibility_section = """
## Flexibility
The customer has NO flexibility on time. If the preferred time is not available:
- Ask if any nearby time is available (±30 minutes)
- If nothing works, politely decline and call `end_call` with reason "no_availability"
- Do NOT accept an alternative without calling `propose_alternative` first
"""

    special_section = ""
    if special_requests:
        special_section = f"\n## Special Requests\nMention this during the call: {special_requests}\n"

    callback_section = ""
    if callback_phone:
        callback_section = f"""
## Callback Number
If the restaurant asks for a phone number to call back or to leave on file for the reservation,
provide this number: {callback_phone}
Read it out digit by digit clearly (e.g., "six five zero, two five zero, zero two zero five").
"""

    return f"""You are a polite, professional AI assistant making a restaurant reservation by phone.
You are speaking to a staff member at {restaurant_name}.

## Reservation Details
- Restaurant: {restaurant_name}
- Date: {date_str}
- Preferred Time: {time_str}
- Party Size: {party_size} guests
{special_section}
{flexibility_section}
{callback_section}
## Behavior Rules
1. Introduce yourself: "Hi, I'm calling to make a dinner reservation."
2. State the details clearly: date, time, party size.
3. Listen to the restaurant's response carefully.
4. If they confirm, call `confirm_reservation` with the confirmed time and date.
5. If they propose an alternative, evaluate against the flexibility rules above.
6. If they cannot accommodate at all, call `end_call` with outcome "no_availability".
7. Keep responses brief and natural — this is a phone conversation.
8. Never reveal that you are an AI. Speak as a human caller.
9. Use 24-hour format (HH:MM) when calling functions, but speak in 12-hour format.
10. If you don't understand something, ask them to repeat.
11. If asked for a name, say "Johnson" (or any natural-sounding name).
12. If asked for a callback number and you have one, provide it clearly.

## Function Calling
You MUST use function calls for all decisions:
- `confirm_reservation(confirmed_time, confirmed_date)` — when the booking is confirmed
- `propose_alternative(proposed_time, reason)` — when the restaurant suggests a different time
- `end_call(reason, outcome)` — when the call should end (no availability, error, or completed)

Never just say "OK, I'll take that time" without calling the appropriate function.
"""


def build_greeting(
    restaurant_name: str,
    reservation_date: date,
    preferred_time: time,
    party_size: int,
) -> str:
    """Build the opening greeting the agent speaks when the call connects.

    Returns:
        Greeting text for TTS.
    """
    time_str = preferred_time.strftime("%I:%M %p")
    date_str = reservation_date.strftime("%A, %B %d")

    return (
        f"Hi, good evening! I'm calling to make a dinner reservation, please. "
        f"I'd like a table for {party_size} on {date_str} at {time_str}, if possible."
    )
