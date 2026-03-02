"""SSE (Server-Sent Events) manager for real-time push notifications.

Uses Redis pub/sub per user channel. Falls back to in-memory for testing.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

import structlog

logger = structlog.get_logger()


class SSEManager:
    """Manages SSE connections and event broadcasting."""

    def __init__(self, redis_client=None):
        """Initialize SSE manager.

        Args:
            redis_client: Optional Redis client for pub/sub.
                          If None, uses in-memory broadcasting (single-worker only).
        """
        self.redis = redis_client
        # In-memory fallback: dict of user_id -> list of asyncio.Queue
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def _channel_name(self, user_id: str) -> str:
        return f"sse:events:{user_id}"

    async def publish(self, user_id: str, event_type: str, data: dict) -> None:
        """Publish an event to all connected SSE clients for a user.

        Args:
            user_id: User identifier (phone or email).
            event_type: Event type (e.g., 'status_change').
            data: Event data dict.
        """
        payload = json.dumps({"type": event_type, **data})

        if self.redis:
            try:
                await self.redis.publish(self._channel_name(user_id), payload)
                logger.info("sse.published_redis", user_id=user_id, event=event_type)
            except Exception as e:
                logger.error("sse.redis_publish_error", error=str(e))
                # Fall through to in-memory
                await self._publish_in_memory(user_id, payload)
        else:
            await self._publish_in_memory(user_id, payload)

    async def _publish_in_memory(self, user_id: str, payload: str) -> None:
        """Push event to in-memory subscribers."""
        queues = self._subscribers.get(user_id, [])
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("sse.queue_full", user_id=user_id)

    async def subscribe(self, user_id: str) -> AsyncGenerator[str, None]:
        """Subscribe to SSE events for a user. Yields formatted SSE strings.

        This is an async generator that yields SSE-formatted events.
        It blocks until events are available, with periodic keepalive.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # Register subscriber
        if user_id not in self._subscribers:
            self._subscribers[user_id] = []
        self._subscribers[user_id].append(queue)

        try:
            while True:
                try:
                    # Wait for event with timeout (keepalive every 15s)
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        finally:
            # Unregister subscriber
            if user_id in self._subscribers:
                try:
                    self._subscribers[user_id].remove(queue)
                    if not self._subscribers[user_id]:
                        del self._subscribers[user_id]
                except ValueError:
                    pass


# Singleton instance — initialized by app startup
sse_manager = SSEManager()
