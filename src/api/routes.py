"""FastAPI routes for the reservation agent API."""

from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, HTTPException, Request, status

from src.api.schemas import (
    ErrorResponse,
    HealthResponse,
    ReservationRequest,
    ReservationResponse,
    TranscriptTurnResponse,
)
from src.models.enums import ReservationStatus
from src.models.reservation import Reservation
from src.providers.base import Database

router = APIRouter()


def _get_db(request: Request) -> Database:
    """Extract DB provider from app state."""
    return request.app.state.providers["db"]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Liveness check — server is up."""
    return HealthResponse(status="ok")


@router.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(payload: ReservationRequest, request: Request):
    """Submit a new reservation request."""
    db = _get_db(request)

    reservation = Reservation(
        restaurant_name=payload.restaurant_name,
        restaurant_phone=payload.restaurant_phone,
        date=payload.date,
        preferred_time=payload.preferred_time,
        party_size=payload.party_size,
        user_id=payload.user_contact.email or payload.user_contact.phone,
        user_phone=payload.user_contact.phone,
        user_email=payload.user_contact.email,
        alt_time_start=payload.alt_time_window.start if payload.alt_time_window else None,
        alt_time_end=payload.alt_time_window.end if payload.alt_time_window else None,
        special_requests=payload.special_requests,
    )

    await db.create_reservation(reservation.to_dict())

    return ReservationResponse(
        reservation_id=reservation.reservation_id,
        status=reservation.status,
        restaurant_name=reservation.restaurant_name,
        date=reservation.date,
        preferred_time=reservation.preferred_time,
        party_size=reservation.party_size,
        call_attempts=0,
    )


@router.get(
    "/reservations/{reservation_id}",
    response_model=ReservationResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_reservation(reservation_id: str, request: Request):
    """Check reservation status."""
    db = _get_db(request)
    data = await db.get_reservation(reservation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Reservation not found")

    return ReservationResponse(
        reservation_id=data["reservation_id"],
        status=ReservationStatus(data["status"]),
        restaurant_name=data["restaurant_name"],
        date=data["date"],
        preferred_time=data["preferred_time"],
        party_size=data["party_size"],
        confirmed_time=data.get("confirmed_time"),
        call_attempts=data.get("call_attempts", 0),
    )


@router.get(
    "/reservations/{reservation_id}/transcript",
    response_model=list[TranscriptTurnResponse],
    responses={404: {"model": ErrorResponse}},
)
async def get_transcript(reservation_id: str, request: Request):
    """Retrieve call transcript."""
    db = _get_db(request)
    data = await db.get_reservation(reservation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Reservation not found")

    turns = await db.get_transcript(reservation_id)
    return [
        TranscriptTurnResponse(
            turn_number=t["turn_number"],
            role=t["role"],
            text=t["text"],
            timestamp=t["timestamp"],
        )
        for t in turns
    ]


@router.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def cancel_reservation(reservation_id: str, request: Request):
    """Cancel a pending reservation."""
    db = _get_db(request)
    data = await db.get_reservation(reservation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Reservation not found")

    current_status = ReservationStatus(data["status"])
    # Can only cancel from non-terminal, non-active states
    if current_status in (ReservationStatus.CONFIRMED, ReservationStatus.FAILED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel reservation in '{current_status}' state",
        )

    await db.update_reservation(reservation_id, status=ReservationStatus.FAILED.value)
    await db.log_state_transition({
        "reservation_id": reservation_id,
        "from_state": current_status.value,
        "to_state": ReservationStatus.FAILED.value,
        "trigger": "user_cancel",
        "call_sid": data.get("call_sid"),
        "timestamp": datetime.utcnow().isoformat(),
    })

    data["status"] = ReservationStatus.FAILED.value
    return ReservationResponse(
        reservation_id=data["reservation_id"],
        status=ReservationStatus.FAILED,
        restaurant_name=data["restaurant_name"],
        date=data["date"],
        preferred_time=data["preferred_time"],
        party_size=data["party_size"],
        confirmed_time=data.get("confirmed_time"),
        call_attempts=data.get("call_attempts", 0),
    )


@router.post(
    "/reservations/{reservation_id}/confirm-alternative",
    response_model=ReservationResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def confirm_alternative(reservation_id: str, request: Request):
    """Confirm an alternative time proposed by the restaurant."""
    db = _get_db(request)
    data = await db.get_reservation(reservation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Reservation not found")

    current_status = ReservationStatus(data["status"])
    if current_status != ReservationStatus.ALTERNATIVE_PROPOSED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot confirm alternative in '{current_status}' state (must be 'alternative_proposed')",
        )

    await db.update_reservation(reservation_id, status=ReservationStatus.CONFIRMED.value)
    await db.log_state_transition({
        "reservation_id": reservation_id,
        "from_state": current_status.value,
        "to_state": ReservationStatus.CONFIRMED.value,
        "trigger": "user_confirm_alt",
        "timestamp": datetime.utcnow().isoformat(),
    })

    data["status"] = ReservationStatus.CONFIRMED.value
    return ReservationResponse(
        reservation_id=data["reservation_id"],
        status=ReservationStatus.CONFIRMED,
        restaurant_name=data["restaurant_name"],
        date=data["date"],
        preferred_time=data["preferred_time"],
        party_size=data["party_size"],
        confirmed_time=data.get("confirmed_time"),
        call_attempts=data.get("call_attempts", 0),
    )


@router.post(
    "/reservations/{reservation_id}/reject-alternative",
    response_model=ReservationResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def reject_alternative(reservation_id: str, request: Request):
    """Reject an alternative time proposed by the restaurant."""
    db = _get_db(request)
    data = await db.get_reservation(reservation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Reservation not found")

    current_status = ReservationStatus(data["status"])
    if current_status != ReservationStatus.ALTERNATIVE_PROPOSED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reject alternative in '{current_status}' state",
        )

    await db.update_reservation(reservation_id, status=ReservationStatus.FAILED.value)
    await db.log_state_transition({
        "reservation_id": reservation_id,
        "from_state": current_status.value,
        "to_state": ReservationStatus.FAILED.value,
        "trigger": "user_reject_alt",
        "timestamp": datetime.utcnow().isoformat(),
    })

    data["status"] = ReservationStatus.FAILED.value
    return ReservationResponse(
        reservation_id=data["reservation_id"],
        status=ReservationStatus.FAILED,
        restaurant_name=data["restaurant_name"],
        date=data["date"],
        preferred_time=data["preferred_time"],
        party_size=data["party_size"],
        confirmed_time=data.get("confirmed_time"),
        call_attempts=data.get("call_attempts", 0),
    )
