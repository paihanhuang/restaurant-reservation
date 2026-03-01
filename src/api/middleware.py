"""API middleware — rate limiting."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from configs.app import RATE_LIMIT_RESERVATIONS, RATE_LIMIT_QUERIES, RATE_LIMIT_GLOBAL

# Create limiter instance keyed by remote address
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT_GLOBAL])


def setup_rate_limiting(app: FastAPI) -> None:
    """Attach rate limiting middleware to a FastAPI app."""
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded: {exc.detail}"},
        )
