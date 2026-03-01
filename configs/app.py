"""Application configuration — FastAPI, Redis, retry policy, rate limits."""

import os

# --- FastAPI ---
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# --- Redis ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# --- Retry Policy ---
MAX_CALL_RETRIES = int(os.getenv("MAX_CALL_RETRIES", "3"))
RETRY_DELAY_SECONDS = int(os.getenv("RETRY_DELAY_SECONDS", "60"))

# --- Rate Limits ---
RATE_LIMIT_RESERVATIONS = os.getenv("RATE_LIMIT_RESERVATIONS", "5/minute")
RATE_LIMIT_QUERIES = os.getenv("RATE_LIMIT_QUERIES", "30/minute")
RATE_LIMIT_GLOBAL = os.getenv("RATE_LIMIT_GLOBAL", "100/minute")

# --- Call Timeouts ---
CALL_DURATION_LIMIT_SECONDS = int(os.getenv("CALL_DURATION_LIMIT_SECONDS", "300"))
STALE_CALLING_TIMEOUT_MINUTES = int(os.getenv("STALE_CALLING_TIMEOUT_MINUTES", "10"))
STALE_ALT_PROPOSED_TIMEOUT_HOURS = int(os.getenv("STALE_ALT_PROPOSED_TIMEOUT_HOURS", "24"))

# --- Database ---
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "data/reservations.db")
