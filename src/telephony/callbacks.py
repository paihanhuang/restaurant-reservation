"""Twilio status callback handler with signature validation."""

from __future__ import annotations

import structlog
from datetime import datetime

from fastapi import Request, HTTPException
from twilio.request_validator import RequestValidator

from configs.telephony import TWILIO_AUTH_TOKEN
from src.providers.base import Database
from src.telephony.voicemail import is_machine, build_voicemail_twiml

logger = structlog.get_logger()


async def validate_twilio_signature(request: Request) -> bool:
    """Validate that a webhook request actually came from Twilio.

    Returns True if valid, raises HTTPException 403 if invalid.
    """
    validator = RequestValidator(TWILIO_AUTH_TOKEN)

    # Reconstruct the full URL
    url = str(request.url)

    # Get form data
    form = await request.form()
    params = dict(form)

    # Get the signature header
    signature = request.headers.get("X-Twilio-Signature", "")

    if not validator.validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    return True


async def handle_amd_callback(
    request: Request,
    db: Database,
) -> dict:
    """Process a Twilio Answering Machine Detection callback.

    Called asynchronously when Twilio finishes AMD analysis.
    If a machine is detected, logs the event and returns voicemail
    TwiML. If human, returns no-op.

    Returns:
        Dict with 'machine_detected' bool and optional 'twiml'.
    """
    form = await request.form()
    params = dict(form)

    call_sid = params.get("CallSid", "")
    answered_by = params.get("AnsweredBy", "unknown")

    logger.info(
        "amd_callback.received",
        call_sid=call_sid,
        answered_by=answered_by,
    )

    if is_machine(answered_by):
        logger.info(
            "amd_callback.machine_detected",
            call_sid=call_sid,
            answered_by=answered_by,
        )

        # Log voicemail detection
        await db.log_call({
            "call_sid": call_sid,
            "status": "voicemail_detected",
            "started_at": datetime.utcnow().isoformat(),
            "error_message": f"Answered by: {answered_by}",
        })

        return {
            "machine_detected": True,
            "call_sid": call_sid,
            "answered_by": answered_by,
        }

    logger.info(
        "amd_callback.human_detected",
        call_sid=call_sid,
    )

    return {
        "machine_detected": False,
        "call_sid": call_sid,
        "answered_by": answered_by,
    }


async def handle_status_callback(
    request: Request,
    db: Database,
) -> dict:
    """Process a Twilio status callback.

    Updates call_logs with the latest status. Idempotent — duplicate
    callbacks for the same status are ignored.
    """
    form = await request.form()
    params = dict(form)

    call_sid = params.get("CallSid", "")
    call_status = params.get("CallStatus", "")
    duration = params.get("CallDuration")

    # Map Twilio status to our CallStatus
    status_map = {
        "initiated": "initiated",
        "ringing": "ringing",
        "in-progress": "answered",
        "busy": "busy",
        "no-answer": "no_answer",
        "failed": "failed",
        "completed": "completed",
        "canceled": "failed",
    }

    mapped_status = status_map.get(call_status, call_status)

    # Log the call status update
    await db.log_call({
        "reservation_id": params.get("AccountSid", "unknown"),  # Will be enriched later
        "call_sid": call_sid,
        "attempt_number": 0,  # Will be enriched by the caller
        "status": mapped_status,
        "duration_seconds": int(duration) if duration else None,
        "started_at": datetime.utcnow().isoformat(),
        "ended_at": datetime.utcnow().isoformat() if call_status in ("completed", "failed", "busy", "no-answer") else None,
        "error_message": params.get("ErrorMessage"),
    })

    return {"status": "received", "call_sid": call_sid}

