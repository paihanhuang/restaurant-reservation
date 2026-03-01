"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from configs.providers import create_providers
from src.api.middleware import setup_rate_limiting
from src.api.routes import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Restaurant Reservation Agent",
        description="AI-powered restaurant reservation booking via phone calls",
        version="0.1.0",
    )

    # Attach providers to app state
    app.state.providers = create_providers()

    # Setup middleware
    setup_rate_limiting(app)

    # Register routes
    app.include_router(router)

    @app.on_event("startup")
    async def startup():
        db = app.state.providers["db"]
        await db.initialize()

    return app
