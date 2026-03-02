"""Twilio inbound SMS webhook — handles user replies to reservation notifications.

Parses 'yes'/'no' replies to confirm or reject alternative time proposals.
"""

from __future__ import annotations

import structlog
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response

from src.models.enums import ReservationStatus
from src.providers.base import Database

logger = structlog.get_logger()

router = APIRouter()

# Recognized confirmation keywords (case-insensitive)
CONFIRM_KEYWORDS = {"yes", "y", "confirm", "accept", "ok", "sure", "yep", "yeah"}
REJECT_KEYWORDS = {"no", "n", "reject", "decline", "nope", "nah", "cancel"}


def _twiml_response(message: str) -> Response:
    """Return a TwiML XML response with a message."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{message}</Message></Response>"
    )
    return Response(content=xml, media_type="application/xml")


@router.post("/webhooks/sms/reply")
async def handle_sms_reply(request: Request) -> Response:
    """Handle incoming SMS replies from users.

    Twilio POSTs form data with Body, From, To, etc.
    Parses the body and confirms/rejects the most recent alternative_proposed reservation.
    """
    db: Database = request.app.state.providers["db"]

    form = await request.form()
    body = str(form.get("Body", "")).strip().lower()
    from_phone = str(form.get("From", ""))

    logger.info("sms_webhook.received", from_phone=from_phone, body=body)

    if not from_phone:
        return _twiml_response("Could not identify your phone number.")

    # Find the most recent alternative_proposed reservation for this phone
    reservations = await db.list_reservations_by_status(
        ReservationStatus.ALTERNATIVE_PROPOSED.value
    )

    # Filter by user phone and sort by most recent
    matching = [
        r for r in reservations
        if r.get("user_phone") == from_phone
    ]

    if not matching:
        logger.info("sms_webhook.no_pending", from_phone=from_phone)
        return _twiml_response(
            "No pending reservation offers found for your number. "
            "If you believe this is an error, please contact us directly."
        )

    # Use the most recent one (by updated_at or created_at)
    reservation = sorted(
        matching,
        key=lambda r: r.get("updated_at", r.get("created_at", "")),
        reverse=True,
    )[0]

    reservation_id = reservation["reservation_id"]
    restaurant_name = reservation.get("restaurant_name", "the restaurant")

    # Parse the reply
    if body in CONFIRM_KEYWORDS:
        # Check idempotency — already confirmed?
        current = await db.get_reservation(reservation_id)
        if current and ReservationStatus(current["status"]) == ReservationStatus.CONFIRMED:
            return _twiml_response(
                f"Your reservation at {restaurant_name} is already confirmed!"
            )

        await db.update_reservation(
            reservation_id, status=ReservationStatus.CONFIRMED.value
        )
        await db.log_state_transition({
            "reservation_id": reservation_id,
            "from_state": ReservationStatus.ALTERNATIVE_PROPOSED.value,
            "to_state": ReservationStatus.CONFIRMED.value,
            "trigger": "sms_reply_confirm",
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.info("sms_webhook.confirmed", reservation_id=reservation_id)
        return _twiml_response(
            f"Confirmed! Your reservation at {restaurant_name} has been booked. Enjoy your dinner!"
        )

    elif body in REJECT_KEYWORDS:
        # Check idempotency
        current = await db.get_reservation(reservation_id)
        if current and ReservationStatus(current["status"]) == ReservationStatus.FAILED:
            return _twiml_response(
                f"The offer from {restaurant_name} has already been declined."
            )

        await db.update_reservation(
            reservation_id, status=ReservationStatus.FAILED.value
        )
        await db.log_state_transition({
            "reservation_id": reservation_id,
            "from_state": ReservationStatus.ALTERNATIVE_PROPOSED.value,
            "to_state": ReservationStatus.FAILED.value,
            "trigger": "sms_reply_reject",
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.info("sms_webhook.rejected", reservation_id=reservation_id)
        return _twiml_response(
            f"Got it — the offer from {restaurant_name} has been declined. "
            "Would you like us to try a different restaurant?"
        )

    else:
        # Unrecognized reply
        logger.info("sms_webhook.unrecognized", body=body, from_phone=from_phone)
        return _twiml_response(
            "Reply YES to confirm or NO to reject the proposed time. "
            "For other requests, please visit your dashboard."
        )
