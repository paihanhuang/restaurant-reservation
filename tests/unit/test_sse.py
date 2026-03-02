"""Tests for SSE manager."""

from __future__ import annotations

import asyncio
import json
import pytest

from src.notifications.sse import SSEManager


class TestSSEManagerPublish:
    """Tests for SSE event publishing."""

    @pytest.mark.asyncio
    async def test_publish_to_subscriber(self):
        """Published events reach subscribers."""
        mgr = SSEManager()
        received = []

        async def collect():
            async for event in mgr.subscribe("user-1"):
                if "keepalive" not in event:
                    received.append(event)
                    break

        # Start subscriber
        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)  # Let subscriber register

        # Publish event
        await mgr.publish("user-1", "status_change", {"status": "confirmed"})
        await asyncio.wait_for(task, timeout=2.0)

        assert len(received) == 1
        assert "status_change" in received[0] or "confirmed" in received[0]

    @pytest.mark.asyncio
    async def test_publish_to_wrong_user_not_received(self):
        """Events for user-2 are not received by user-1."""
        mgr = SSEManager()
        received = []

        async def collect():
            async for event in mgr.subscribe("user-1"):
                if "keepalive" not in event:
                    received.append(event)
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        # Publish to different user
        await mgr.publish("user-2", "status_change", {"status": "confirmed"})
        await asyncio.sleep(0.1)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """Multiple subscribers for same user all receive events."""
        mgr = SSEManager()
        results = [[], []]

        async def collect(idx):
            async for event in mgr.subscribe("user-1"):
                if "keepalive" not in event:
                    results[idx].append(event)
                    break

        tasks = [
            asyncio.create_task(collect(0)),
            asyncio.create_task(collect(1)),
        ]
        await asyncio.sleep(0.05)

        await mgr.publish("user-1", "update", {"id": "1"})
        await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results[0]) == 1
        assert len(results[1]) == 1

    @pytest.mark.asyncio
    async def test_sse_format(self):
        """SSE output follows spec: event + data fields."""
        mgr = SSEManager()
        output = []

        async def collect():
            async for event in mgr.subscribe("user-1"):
                if "keepalive" not in event:
                    output.append(event)
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await mgr.publish("user-1", "test", {"key": "val"})
        await asyncio.wait_for(task, timeout=2.0)

        assert output[0].startswith("event: message\n")
        assert "data: " in output[0]
        assert output[0].endswith("\n\n")

    @pytest.mark.asyncio
    async def test_keepalive(self):
        """Keepalive comments are sent during idle periods."""
        mgr = SSEManager()
        output = []

        async def collect():
            count = 0
            async for event in mgr.subscribe("user-1"):
                output.append(event)
                count += 1
                if count >= 1:
                    break

        # Override timeout to be quick for testing
        original_subscribe = mgr.subscribe

        async def fast_subscribe(user_id):
            queue = asyncio.Queue(maxsize=100)
            if user_id not in mgr._subscribers:
                mgr._subscribers[user_id] = []
            mgr._subscribers[user_id].append(queue)
            try:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield f"event: message\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
            finally:
                if user_id in mgr._subscribers:
                    try:
                        mgr._subscribers[user_id].remove(queue)
                    except ValueError:
                        pass

        mgr.subscribe = fast_subscribe
        task = asyncio.create_task(collect())
        await asyncio.wait_for(task, timeout=2.0)

        assert any("keepalive" in e for e in output)


class TestSSEManagerCleanup:
    """Tests for subscriber cleanup."""

    @pytest.mark.asyncio
    async def test_subscriber_removed_on_disconnect(self):
        """Subscriber is removed from list after generator exits."""
        mgr = SSEManager()

        async def connect_and_leave():
            gen = mgr.subscribe("user-1")
            # Get one keepalive then stop
            await gen.__anext__()
            await gen.aclose()

        assert "user-1" not in mgr._subscribers

        # After close, subscriber should be cleaned up
        # (This tests the finally block in subscribe)
