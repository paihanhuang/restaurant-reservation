"""Telephony configuration — Twilio credentials, timeouts."""

import os

# --- Twilio Credentials (from env) ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# --- Server Host (for callback URLs) ---
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "localhost:8000")
USE_TLS = os.getenv("USE_TLS", "true").lower() == "true"

# --- Call Parameters ---
RING_TIMEOUT_SECONDS = int(os.getenv("RING_TIMEOUT_SECONDS", "30"))
CALL_TIME_LIMIT_SECONDS = int(os.getenv("CALL_TIME_LIMIT_SECONDS", "300"))

# --- WebSocket Auth ---
WS_TOKEN_TTL_SECONDS = int(os.getenv("WS_TOKEN_TTL_SECONDS", "60"))

# --- Silence Detection ---
SILENCE_THRESHOLD_MS = int(os.getenv("SILENCE_THRESHOLD_MS", "700"))
HOLD_TIMEOUT_SECONDS = int(os.getenv("HOLD_TIMEOUT_SECONDS", "30"))
MAX_SILENCE_SECONDS = int(os.getenv("MAX_SILENCE_SECONDS", "120"))
