"""Unit tests for state machine."""

import pytest
from unittest.mock import AsyncMock

from src.conversation.state_machine import StateMachine, InvalidStateTransition, VALID_TRANSITIONS
from src.models.enums import ReservationStatus


@pytest.fixture
def db():
    return AsyncMock()


@pytest.fixture
def sm(db):
    return StateMachine(db)


class TestValidTransitions:
    @pytest.mark.asyncio
    async def test_pending_to_calling(self, sm, db):
        await sm.transition("res-1", ReservationStatus.PENDING, ReservationStatus.CALLING, trigger="test")
        db.log_state_transition.assert_called_once()
        db.update_reservation.assert_called_once_with("res-1", status=ReservationStatus.CALLING)

    @pytest.mark.asyncio
    async def test_calling_to_confirmed(self, sm, db):
        await sm.transition("res-1", ReservationStatus.CALLING, ReservationStatus.CONFIRMED, trigger="llm_confirm")
        db.update_reservation.assert_called_once_with("res-1", status=ReservationStatus.CONFIRMED)

    @pytest.mark.asyncio
    async def test_calling_to_alt_proposed(self, sm, db):
        await sm.transition("res-1", ReservationStatus.CALLING, ReservationStatus.ALTERNATIVE_PROPOSED)
        db.update_reservation.assert_called_once()

    @pytest.mark.asyncio
    async def test_calling_to_failed(self, sm, db):
        await sm.transition("res-1", ReservationStatus.CALLING, ReservationStatus.FAILED)
        db.update_reservation.assert_called_once()

    @pytest.mark.asyncio
    async def test_alt_proposed_to_confirmed(self, sm, db):
        await sm.transition("res-1", ReservationStatus.ALTERNATIVE_PROPOSED, ReservationStatus.CONFIRMED)
        db.update_reservation.assert_called_once()

    @pytest.mark.asyncio
    async def test_alt_proposed_to_failed(self, sm, db):
        await sm.transition("res-1", ReservationStatus.ALTERNATIVE_PROPOSED, ReservationStatus.FAILED)
        db.update_reservation.assert_called_once()

    @pytest.mark.asyncio
    async def test_pending_to_failed(self, sm, db):
        """Pending can go to failed (user cancels before calling)."""
        await sm.transition("res-1", ReservationStatus.PENDING, ReservationStatus.FAILED)
        db.update_reservation.assert_called_once()


class TestInvalidTransitions:
    @pytest.mark.asyncio
    async def test_confirmed_to_calling_rejected(self, sm, db):
        with pytest.raises(InvalidStateTransition):
            await sm.transition("res-1", ReservationStatus.CONFIRMED, ReservationStatus.CALLING)
        db.update_reservation.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_to_pending_rejected(self, sm, db):
        with pytest.raises(InvalidStateTransition):
            await sm.transition("res-1", ReservationStatus.FAILED, ReservationStatus.PENDING)
        db.update_reservation.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_to_confirmed_rejected(self, sm, db):
        """Can't skip calling and go straight to confirmed."""
        with pytest.raises(InvalidStateTransition):
            await sm.transition("res-1", ReservationStatus.PENDING, ReservationStatus.CONFIRMED)

    @pytest.mark.asyncio
    async def test_confirmed_to_failed_rejected(self, sm, db):
        """Confirmed is terminal."""
        with pytest.raises(InvalidStateTransition):
            await sm.transition("res-1", ReservationStatus.CONFIRMED, ReservationStatus.FAILED)


class TestHelpers:
    def test_is_terminal_confirmed(self, sm):
        assert sm.is_terminal(ReservationStatus.CONFIRMED) is True

    def test_is_terminal_failed(self, sm):
        assert sm.is_terminal(ReservationStatus.FAILED) is True

    def test_is_not_terminal_pending(self, sm):
        assert sm.is_terminal(ReservationStatus.PENDING) is False

    def test_can_transition_valid(self, sm):
        assert sm.can_transition(ReservationStatus.PENDING, ReservationStatus.CALLING) is True

    def test_can_transition_invalid(self, sm):
        assert sm.can_transition(ReservationStatus.CONFIRMED, ReservationStatus.CALLING) is False


class TestTransitionLogging:
    @pytest.mark.asyncio
    async def test_transition_logged_to_db(self, sm, db):
        await sm.transition("res-1", ReservationStatus.PENDING, ReservationStatus.CALLING, trigger="start_call")
        logged = db.log_state_transition.call_args[0][0]
        assert logged["reservation_id"] == "res-1"
        assert logged["from_state"] == ReservationStatus.PENDING
        assert logged["to_state"] == ReservationStatus.CALLING
        assert logged["trigger"] == "start_call"
