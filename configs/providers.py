"""Provider registration — single place to swap providers."""

from __future__ import annotations

from configs.app import REDIS_URL, SQLITE_DB_PATH
from src.providers.sqlite_db import SQLiteDatabase
from src.providers.redis_session import RedisSessionStore


def create_providers() -> dict:
    """Instantiate and return all provider implementations.

    Swap providers here to change implementations without touching business logic.
    """
    return {
        # STT, TTS, LLM providers will be added in M3
        "stt": None,
        "tts": None,
        "llm": None,
        "session": RedisSessionStore(redis_url=REDIS_URL),
        "db": SQLiteDatabase(db_path=SQLITE_DB_PATH),
    }
