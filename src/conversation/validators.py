"""Validators for LLM output — strict parsing and bounds checking."""

from __future__ import annotations

import re
from datetime import time, date


def parse_time_strict(time_str: str) -> time:
    """Parse a time string in strict HH:MM 24-hour format.

    Rejects ambiguous formats like "7:30 PM", "7pm", etc.
    Only accepts: "HH:MM" or "HH:MM:SS" (24-hour).

    Args:
        time_str: Time string to parse.

    Returns:
        time object.

    Raises:
        ValueError: If the format is not strict 24-hour HH:MM.
    """
    time_str = time_str.strip()
    # Reject AM/PM formats
    if re.search(r'[aApP][mM]', time_str):
        raise ValueError(f"Ambiguous time format '{time_str}' — use 24-hour HH:MM")

    # Accept HH:MM or HH:MM:SS
    match = re.fullmatch(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', time_str)
    if not match:
        raise ValueError(f"Invalid time format '{time_str}' — expected HH:MM")

    hour, minute = int(match.group(1)), int(match.group(2))
    second = int(match.group(3)) if match.group(3) else 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError(f"Time out of range: {time_str}")

    return time(hour, minute, second)


def parse_date_strict(date_str: str) -> date:
    """Parse a date string in strict YYYY-MM-DD format.

    Args:
        date_str: Date string to parse.

    Returns:
        date object.

    Raises:
        ValueError: If the format is not YYYY-MM-DD.
    """
    date_str = date_str.strip()
    match = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', date_str)
    if not match:
        raise ValueError(f"Invalid date format '{date_str}' — expected YYYY-MM-DD")

    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def validate_proposed_time(proposed: time, alt_start: time | None, alt_end: time | None) -> bool:
    """Check if a proposed time falls within the user's flexibility window.

    Args:
        proposed: Proposed alternative time.
        alt_start: Start of acceptable range (None = no flexibility).
        alt_end: End of acceptable range (None = no flexibility).

    Returns:
        True if within bounds, False otherwise.
    """
    if alt_start is None or alt_end is None:
        return False  # No flexibility — reject all alternatives
    return alt_start <= proposed <= alt_end


def validate_confirmed_date(confirmed: date, expected: date) -> bool:
    """Validate that the confirmed date matches the reservation date.

    Args:
        confirmed: Date from the LLM's function call.
        expected: Expected reservation date.

    Returns:
        True if they match.
    """
    return confirmed == expected
