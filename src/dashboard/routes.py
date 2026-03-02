"""Dashboard routes — serves HTML page and JSON API for reservation management."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from src.providers.base import Database
from src.notifications.sse import sse_manager

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the dashboard HTML page."""
    import os
    template_path = os.path.join(
        os.path.dirname(__file__), "templates", "index.html"
    )
    with open(template_path) as f:
        html = f.read()
    return HTMLResponse(content=html)


@router.get("/api/dashboard/reservations")
async def list_reservations(request: Request) -> list[dict]:
    """Return all reservations ordered by most recent first."""
    db: Database = request.app.state.providers["db"]
    reservations = await db.list_all_reservations()
    return reservations


@router.get("/events/{user_id}")
async def sse_endpoint(user_id: str):
    """SSE endpoint — streams real-time status updates to the browser.

    Client connects with EventSource('/events/{user_id}') and receives
    events whenever reservation statuses change.
    """
    return StreamingResponse(
        sse_manager.subscribe(user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
