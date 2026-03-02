"""User notification dispatcher — SMS and email notifications.

Sends notifications to users about reservation status changes:
- confirmed: booking is confirmed
- failed: booking could not be completed
- alternative_proposed: restaurant offered a different time
- timeout: alternative offer expired
"""

from __future__ import annotations

import structlog
from datetime import datetime
from enum import StrEnum

logger = structlog.get_logger()


class NotificationType(StrEnum):
    CONFIRMED = "confirmed"
    FAILED = "failed"
    ALTERNATIVE_PROPOSED = "alternative_proposed"
    TIMEOUT = "timeout"


# Message templates per notification type
TEMPLATES = {
    NotificationType.CONFIRMED: {
        "subject": "Reservation Confirmed! 🎉",
        "body": (
            "Great news! Your reservation at {restaurant_name} has been confirmed.\n\n"
            "📅 Date: {date}\n"
            "⏰ Time: {confirmed_time}\n"
            "👥 Party size: {party_size}\n\n"
            "Enjoy your dinner!"
        ),
    },
    NotificationType.FAILED: {
        "subject": "Reservation Could Not Be Completed",
        "body": (
            "Unfortunately, we were unable to book a table at {restaurant_name}.\n\n"
            "📅 Requested: {date} at {preferred_time}\n"
            "Reason: {reason}\n\n"
            "Would you like to try a different restaurant or time?"
        ),
    },
    NotificationType.ALTERNATIVE_PROPOSED: {
        "subject": "Alternative Time Available at {restaurant_name}",
        "body": (
            "{restaurant_name} offered an alternative time for your reservation.\n\n"
            "📅 Date: {date}\n"
            "⏰ Original time: {preferred_time}\n"
            "⏰ Proposed time: {proposed_time}\n"
            "👥 Party size: {party_size}\n\n"
            "Reply to confirm or reject this alternative."
        ),
    },
    NotificationType.TIMEOUT: {
        "subject": "Reservation Offer Expired",
        "body": (
            "The alternative time offer from {restaurant_name} has expired.\n\n"
            "📅 Date: {date}\n"
            "⏰ Proposed time: {proposed_time}\n\n"
            "The offer was not confirmed within 24 hours."
        ),
    },
}


class Notifier:
    """Dispatches notifications via SMS and email."""

    def __init__(self, sms_sender=None, email_sender=None):
        """Initialize with optional SMS and email sender implementations.

        In production, sms_sender would use Twilio, email_sender would use SMTP.
        Both are injectable for testing.
        """
        self.sms_sender = sms_sender
        self.email_sender = email_sender

    async def notify(
        self,
        notification_type: NotificationType,
        reservation: dict,
        extra: dict | None = None,
    ) -> dict:
        """Dispatch a notification based on type and reservation data.

        Args:
            notification_type: Type of notification to send.
            reservation: Reservation data dict.
            extra: Additional context (reason, proposed_time, etc.).

        Returns:
            Dict with sms_sent and email_sent status.
        """
        template = TEMPLATES.get(notification_type)
        if not template:
            logger.warning("notifier.unknown_type", type=notification_type)
            return {"sms_sent": False, "email_sent": False}

        # Merge reservation data with extra context for formatting
        context = {**reservation}
        if extra:
            context.update(extra)

        subject = template["subject"].format(**{k: context.get(k, "") for k in _extract_keys(template["subject"])})
        body = template["body"].format(**{k: context.get(k, "") for k in _extract_keys(template["body"])})

        result = {"sms_sent": False, "email_sent": False}

        # Send SMS if phone available
        user_phone = reservation.get("user_phone")
        if user_phone and self.sms_sender:
            try:
                await self.sms_sender(to=user_phone, body=body)
                result["sms_sent"] = True
                logger.info("notifier.sms_sent", phone=user_phone, type=notification_type)
            except Exception as e:
                logger.error("notifier.sms_error", error=str(e))

        # Send email if available
        user_email = reservation.get("user_email")
        if user_email and self.email_sender:
            try:
                await self.email_sender(to=user_email, subject=subject, body=body)
                result["email_sent"] = True
                logger.info("notifier.email_sent", email=user_email, type=notification_type)
            except Exception as e:
                logger.error("notifier.email_error", error=str(e))

        return result


def _extract_keys(template_str: str) -> list[str]:
    """Extract format keys from a template string."""
    import re
    return re.findall(r'\{(\w+)\}', template_str)
