"""Redis session store provider implementation."""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from src.providers.base import SessionStore


class RedisSessionStore(SessionStore):
    """Redis implementation of the SessionStore interface."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> dict | None:
        data = await self._redis.get(key)
        if data is None:
            return None
        return json.loads(data)

    async def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        data = json.dumps(value)
        if ttl is not None:
            await self._redis.setex(key, ttl, data)
        else:
            await self._redis.set(key, data)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
