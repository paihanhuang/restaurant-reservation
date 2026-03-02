"""Unit tests for notifier."""

import pytest
from unittest.mock import AsyncMock

from src.notifications.notifier import Notifier, NotificationType, TEMPLATES


@pytest.fixture
def sms_sender():
    return AsyncMock()


@pytest.fixture
def email_sender():
    return AsyncMock()


@pytest.fixture
def notifier(sms_sender, email_sender):
    return Notifier(sms_sender=sms_sender, email_sender=email_sender)


def _make_reservation(**overrides):
    base = {
        "restaurant_name": "Test Bistro",
        "date": "2026-04-15",
        "preferred_time": "19:30",
        "confirmed_time": "19:30",
        "party_size": 4,
        "user_phone": "+14155559999",
        "user_email": "test@example.com",
    }
    base.update(overrides)
    return base


class TestNotifier:
    @pytest.mark.asyncio
    async def test_confirmed_sends_sms_and_email(self, notifier, sms_sender, email_sender):
        res = _make_reservation()
        result = await notifier.notify(NotificationType.CONFIRMED, res)
        assert result["sms_sent"] is True
        assert result["email_sent"] is True
        sms_sender.assert_called_once()
        email_sender.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_notification(self, notifier, sms_sender):
        res = _make_reservation()
        result = await notifier.notify(NotificationType.FAILED, res, extra={"reason": "fully booked"})
        assert result["sms_sent"] is True
        body = sms_sender.call_args[1]["body"]
        assert "fully booked" in body

    @pytest.mark.asyncio
    async def test_alt_proposed_notification(self, notifier, sms_sender):
        res = _make_reservation()
        result = await notifier.notify(
            NotificationType.ALTERNATIVE_PROPOSED, res,
            extra={"proposed_time": "20:30"},
        )
        assert result["sms_sent"] is True
        body = sms_sender.call_args[1]["body"]
        assert "20:30" in body

    @pytest.mark.asyncio
    async def test_no_phone_skips_sms(self, email_sender):
        notifier = Notifier(sms_sender=None, email_sender=email_sender)
        res = _make_reservation(user_phone=None)
        result = await notifier.notify(NotificationType.CONFIRMED, res)
        assert result["sms_sent"] is False
        assert result["email_sent"] is True

    @pytest.mark.asyncio
    async def test_no_email_skips_email(self, sms_sender):
        notifier = Notifier(sms_sender=sms_sender, email_sender=None)
        res = _make_reservation(user_email=None)
        result = await notifier.notify(NotificationType.CONFIRMED, res)
        assert result["sms_sent"] is True
        assert result["email_sent"] is False

    @pytest.mark.asyncio
    async def test_sms_error_handled(self, email_sender):
        sms_sender = AsyncMock(side_effect=Exception("SMS failed"))
        notifier = Notifier(sms_sender=sms_sender, email_sender=email_sender)
        res = _make_reservation()
        result = await notifier.notify(NotificationType.CONFIRMED, res)
        assert result["sms_sent"] is False
        assert result["email_sent"] is True

    @pytest.mark.asyncio
    async def test_timeout_notification(self, notifier, sms_sender):
        res = _make_reservation()
        result = await notifier.notify(
            NotificationType.TIMEOUT, res,
            extra={"proposed_time": "20:30"},
        )
        assert result["sms_sent"] is True


class TestTemplates:
    def test_all_types_have_templates(self):
        for t in NotificationType:
            assert t in TEMPLATES

    def test_templates_have_subject_and_body(self):
        for t, template in TEMPLATES.items():
            assert "subject" in template
            assert "body" in template
