# Architecture Design — Agent Critiques

Each agent independently reviewed [architecture_design.md](file:///home/etem/reservation-agent/Implementation%20Plan/architecture_design.md) from their own perspective.

---

## 🎩 Architect Critique — Design Gaps & Structural Issues

The Architect evaluates the design for completeness, boundary clarity, long-term viability, and overlooked failure modes.

### 1. Missing: Audio Format Conversion Layer

The plan states Twilio sends 8-bit 8kHz µ-law audio. OpenAI Whisper API expects 16kHz PCM (WAV/FLAC/MP3). **There is no component designed to handle this conversion.**

This is not a minor detail — it's a required transformation in the hot path of every single call. The `STTProvider` interface should either:
- Accept raw µ-law and handle conversion internally (leaks Twilio knowledge into the provider), or
- An explicit audio conversion layer sits between the WebSocket handler and the STT provider (cleaner separation)

**Recommendation:** Add an `AudioCodec` utility in `src/telephony/` that converts between Twilio's µ-law format and PCM before passing to the STT provider. The reverse (PCM → µ-law) is needed for TTS output as well. This is a two-way codec requirement that is completely absent from the design.

**Severity: High** — Without this, the STT provider will receive unintelligible audio and produce garbage transcripts.

---

### 2. Missing: Greeting & Opening Turn Design

The design covers the conversation engine and function calling, but **who speaks first?** When the restaurant answers, the agent must deliver an opening line immediately — before any STT is needed. The design doesn't specify:

- How the first utterance is triggered (on WebSocket `connected` event? On `start` event? After detecting human voice vs voicemail?)
- What the first utterance says (the system prompt has a greeting template, but no mechanism triggers its delivery)
- How voicemail detection works (answering machine vs human)

**Recommendation:** Add an explicit `on_call_answered` handler that:
1. Waits for the WebSocket `start` event
2. Generates and sends the opening greeting via TTS
3. Begins listening for the restaurant's response

Voicemail detection should use Twilio's `AnsweredBy` parameter with `MachineDetection=Enable` on the `calls.create()` call.

---

### 3. Missing: Silence Detection & Hold Handling

The system prompt says "if asked to hold, wait patiently (up to 30 seconds of silence)." But **there is no mechanism to detect silence** or hold music in the design. The conversation engine processes final transcripts — if nobody speaks, no transcript is produced, and the engine does nothing.

Questions unanswered:
- After 30 seconds of silence, what happens? Does the agent ask "Are you still there?" or hang up?
- Hold music produces constant garbage STT. How does the agent distinguish hold music from speech?
- What if the hold exceeds 2 minutes? The 5-minute call cap means holdwn time is expensive.

**Recommendation:** Add a `SilenceDetector` component that monitors the audio stream for:
- Prolonged silence (>30s) → agent prompts "Hello, are you still there?"
- Continuous noise without intelligible speech (hold music pattern) → suppress STT processing, wait for clear speech to resume
- Timeout (>120s of hold) → end call gracefully, retry later

---

### 4. Weak: `alt_time_window` Semantics Are Ambiguous

The schema defines `alt_time_window: tuple[time, time] | None` as "Negotiation bounds." But:

- Is this a single contiguous range (e.g., 6pm-9pm)?
- Can the user specify multiple ranges (e.g., "6-7pm or after 8:30pm")?
- What if `alt_time_window` is `None`? Does that mean "no alternatives accepted" or "any time is fine"?
- Does the window apply to the same date only, or could the restaurant propose tomorrow?

**Recommendation:** Document explicitly that `None` means "preferred time only, no alternatives." Consider whether the user should be able to specify "any time that day" as a separate option. The LLM system prompt must match whatever semantics are chosen.

---

### 5. Missing: Graceful Shutdown & In-Flight Call Handling

What happens when the server restarts? There could be active WebSocket connections (live calls). The design doesn't address:

- How to drain in-flight calls before shutdown (graceful termination)
- How to resume/recover a call that was in progress when the server crashed
- Whether the Celery worker should pick up orphaned `calling` state reservations on startup

**Recommendation:** Add a startup reconciliation step that checks for reservations stuck in `calling` or `in_conversation` states and either marks them for retry or `failed`.

---

### 6. Questionable: Single `transcript` Column

The schema stores the full transcript in a single `TEXT` column on the `reservations` table. For a multi-turn conversation, this could be a large blob. Issues:

- No structured access to individual turns
- No ability to query "what did the restaurant say on turn 3?"
- Transcript grows unbounded during the call — when is it written to DB?

**Recommendation:** Consider a `transcript_turns` table with `(reservation_id, turn_number, role, text, timestamp)` for structured access. The full transcript can be a computed view.

---

## 🔨 Builder Critique — Implementation Feasibility & API Correctness

The Builder evaluates whether the design can actually be built as specified, and flags API mismatches, missing details, and implementation blockers.

### 1. API Mismatch: OpenAI Whisper API Is NOT a Streaming API

The design shows `STTProvider.create_stream()` returning an `STTStream` with `send_audio(chunk)`. But **OpenAI's Whisper API is a batch API**, not a streaming API. You upload a complete audio file and get a transcript back. There is no WebSocket or streaming endpoint.

This means the design's real-time streaming pattern (`send audio chunks → get partial transcripts`) **cannot be implemented with the Whisper API as written.**

**Options:**
1. **Buffer audio and batch-transcribe** — Collect audio until Voice Activity Detection (VAD) detects end-of-utterance, then send the complete utterance to Whisper. Adds latency (~1-2s after speaker stops).
2. **Use a different STT** — Deepgram and Google Cloud Speech-to-Text both support true streaming. This contradicts the "all-OpenAI" decision.
3. **Use `openai.audio.transcriptions.create()` with chunked VAD** — Closest to the current design, but the `STTStream` interface is misleading. It should be `STTBatchProvider` with `transcribe(audio: bytes)` instead.

**Severity: High** — The provider interface as designed implies true streaming, but the default provider can't deliver it. The interface must match what's actually possible.

---

### 2. Missing: WebSocket Authentication & Routing

The design shows `ws/media-stream/{call_sid}` but:
- **How does the server know which reservation maps to which `call_sid`?** The `calls.create()` TwiML uses `reservation_id` in the URL, but Twilio's `start` event sends the `call_sid`. There's a mapping gap.
- **How is the WebSocket secured?** Twilio connects to the WebSocket — but there's no authentication token. Anyone who guesses the URL could inject audio.
- **What happens if Twilio connects before the server has stored the `call_sid`?** Race condition between `calls.create()` returning the SID and the WebSocket connection arriving.

**Recommendation:**
- Use `reservation_id` in the WebSocket URL (as designed in `initiate_call`), then extract `call_sid` from the WebSocket `start` event
- Add a shared secret or HMAC token to the WebSocket URL for authentication
- Store the `reservation_id → call_sid` mapping in Redis on the `start` event

---

### 3. Missing: FastAPI WebSocket Lifecycle Details

The media stream handler is shown as a standalone function, but:
- How does FastAPI register this WebSocket route?
- How are providers injected (dependency injection? global? passed as args?)
- How is the WebSocket connection cleaned up on error (try/finally)?
- Does the handler need CORS or middleware for Twilio's WebSocket connection?

FastAPI WebSocket endpoints need explicit `@app.websocket()` decoration and manual accept/close handling. There's no TwiML generation for the WebSocket URL either — the `initiate_call` function hardcodes the URL in an f-string TwiML block, which is fragile.

**Recommendation:** Use Twilio's Python SDK `VoiceResponse()` to build TwiML programmatically instead of f-string interpolation. Add explicit WebSocket lifecycle management (accept, try/finally/close).

---

### 4. Missing: `requirements.txt` Contents

The file is referenced but never specified. For implementation, we need the exact package list:
- `openai` (which version? v1.x has a completely different API from v0.x)
- `fastapi` + `uvicorn[standard]` (for WebSocket support)
- `twilio`
- `celery[redis]`
- `redis`
- `pydantic` (v1 or v2? Significant API differences)
- `structlog`

**Recommendation:** Pin exact versions. The OpenAI v1.x migration broke many projects that assumed v0.x APIs. Specify `openai>=1.0.0` at minimum, and use the new `client.chat.completions.create()` API (not the deprecated `openai.ChatCompletion.create()`).

---

### 5. Unclear: Celery Worker in Same Process or Separate?

The design mentions Celery workers but doesn't clarify:
- Does the Celery worker run in the same process as FastAPI?
- If separate, how does the worker initiate calls? Does it have its own Twilio client?
- How does the worker report results back to the FastAPI server?
- `scripts/run_server.py` — does this start both FastAPI and Celery?

**Recommendation:** Explicitly document the process model. Likely: FastAPI runs in process A (handles API + WebSocket), Celery worker runs in process B (handles call tasks). Both connect to the same Redis and SQLite.

---

### 6. Missing: Conversation Engine Turn Management

The engine calls `providers["llm"].chat(messages, functions)` but:
- How is the messages list built? Who appends the restaurant's speech?
- Where is the 20-turn context window enforced?
- How is summarization of older turns implemented?
- What happens when the LLM returns a function call — does the engine execute it inline, or is it queued?

The `process()` method signature takes a string, but the LLM needs a full message history. The design needs a `ConversationContext` object that manages the rolling window.

---

## 🛡️ Shield Critique — Failure Modes, Security, & Testability

The Shield stress-tests for gaps that would cause bugs, data loss, security vulnerabilities, or untestable paths.

### 1. CRITICAL: No Twilio Signature Validation on WebSocket

The risk table mentions "credential leak" mitigation, but **there is no design for Twilio webhook signature validation** on the WebSocket endpoint. Twilio signs its HTTP webhooks with `X-Twilio-Signature`, but **WebSocket connections don't carry this header in the same way**.

This means the `/ws/media-stream/{call_sid}` endpoint is open to:
- Audio injection (attacker sends fake audio)
- Eavesdropping (if no TLS, though WSS should handle this)
- Denial of service (flood with fake WebSocket connections)

**Recommendation:** Use a unique, short-lived token generated at `calls.create()` time and passed in the WebSocket URL. Validate the token on WebSocket `connect`. Expire tokens after 60s.

---

### 2. CRITICAL: No Call Duration Timeout

The design mentions a "5-minute hard cap" in the architect constraints, but **there is no enforcement mechanism** in the implementation. No timer, no watchdog, no Twilio `timeout` parameter.

If the call gets stuck (hold music forever, LLM hangs, STT produces continuous partial results), it will run indefinitely, accumulating Twilio per-minute charges.

**Recommendation:**
- Set `timeout` parameter on `calls.create()`
- Add a server-side watchdog timer in the WebSocket handler (e.g., `asyncio.wait_for(handle_media_stream(...), timeout=300)`)
- Log and alert on calls exceeding 3 minutes (soft warning) and force-hang-up at 5 minutes

---

### 3. HIGH: No Input Sanitization on LLM-Extracted Data

The function calling schema trusts the LLM to return valid `HH:MM` format for `confirmed_time` and `YYYY-MM-DD` for `confirmed_date`. But:

- What if the LLM returns `"7:30 PM"` instead of `"19:30"`?
- What if it returns `"tomorrow"` instead of a date?
- What if it hallucinates a date that doesn't match the reservation?

The design says "server-side validation of `alt_time_window`" but doesn't show **where** this validation lives or **what** it validates.

**Recommendation:** Add explicit validation functions:
- `parse_time(raw: str) -> time` with strict `HH:MM` 24-hour format parsing
- `validate_proposed_time(proposed: time, window: tuple[time, time]) -> bool`
- `validate_confirmed_date(confirmed: date, expected: date) -> bool`
- All validation failures should trigger a re-prompt to the LLM, not a state transition

---

### 4. HIGH: Transcript Persistence Timing Is Undefined

The design says transcripts are stored in SQLite but doesn't specify **when**:
- After every turn? (safe but expensive — DB write per exchange)
- At the end of the call? (risky — if the server crashes mid-call, transcript is lost)
- Periodically? (complex — needs a flush interval)

The transcript lives in Redis during the call (`session:{call_sid}`). If Redis crashes or the session expires before the transcript is persisted to SQLite, the audit trail is permanently lost.

**Recommendation:**
- Write transcript to SQLite on every terminal state transition (`confirmed`, `failed`)
- Additionally, set up periodic Redis → SQLite flushes for long calls (every 60 seconds)
- The `stop` event handler MUST persist the transcript before cleanup

---

### 5. MEDIUM: State Machine Has No Timeout Transitions

The state machine handles happy paths and explicit failures, but **what about time-based transitions?**

- Reservation in `calling` state for >10 minutes (call never connected) → should auto-transition to `retry` or `failed`
- Reservation in `alternative_proposed` for >24 hours (user never responded) → should auto-transition to `failed`
- Reservation in `in_conversation` for >5 minutes (call duration exceeded) → should auto-transition based on outcome

Without timeout transitions, reservations can get stuck in non-terminal states indefinitely.

**Recommendation:** Add a periodic Celery beat task that scans for stale reservations and applies timeout transitions. Define TTLs for each non-terminal state.

---

### 6. MEDIUM: No Rate Limiting on User API

The REST API has no rate limiting. A user (or attacker) could:
- Submit 1000 reservations per second → overwhelm Twilio, exhaust call credits
- Poll `GET /reservations/{id}` in a tight loop → DOS the FastAPI server
- Repeatedly call-and-cancel → burn Twilio minutes

**Recommendation:** Add rate limiting middleware to FastAPI:
- `POST /reservations`: max 5 per user per minute
- `GET /reservations/{id}`: max 30 per user per minute
- Global: max 100 requests per minute across all users

---

### 7. LOW: No Health Check or Observability Endpoints

The API has no:
- `/health` endpoint (is the server up?)
- `/readiness` endpoint (is Redis connected? Can we reach Twilio?)
- Structured logging format specification
- Metrics endpoint for monitoring (call success rate, average duration, failure reasons)

These are essential for production operation but are missing from the M1-M6 roadmap entirely.

**Recommendation:** Add `/health` in M1, `/readiness` in M2 (once Redis and Twilio are connected), and metrics in M6.

---

### 8. LOW: E2E Testing Has No Defined Scenario List

The verification plan mentions "call simulation" and "full flow simulation" but **doesn't define what scenarios must pass**. At minimum:

1. Happy path: call → restaurant confirms → notification sent
2. Negotiation: call → restaurant proposes alt → user confirms alt → confirmed
3. Rejection: call → restaurant has no availability → failed
4. Retry: call → busy signal → retry → restaurant answers → confirmed
5. Voicemail: call → voicemail detected → hang up → retry
6. Hold: call → restaurant asks to hold → wait → resume → confirmed
7. Timeout: call → no answer after max retries → failed → notification
8. Concurrent: two reservations for the same restaurant simultaneously

Without defined scenarios, testing is ad-hoc and coverage is unknown.

---

## Summary of Issues by Severity

| Severity | Agent | Issue |
|----------|-------|-------|
| **Critical** | Shield | No WebSocket authentication mechanism |
| **Critical** | Shield | No call duration timeout enforcement |
| **High** | Builder | OpenAI Whisper is batch-only, not streaming — interface mismatch |
| **High** | Architect | Missing audio codec layer (µ-law ↔ PCM conversion) |
| **High** | Shield | No validation/sanitization of LLM function call output |
| **High** | Shield | Transcript persistence timing undefined |
| **Medium** | Architect | No silence detection or hold music handling |
| **Medium** | Architect | `alt_time_window` semantics ambiguous |
| **Medium** | Shield | No timeout transitions in state machine |
| **Medium** | Shield | No rate limiting on user API |
| **Medium** | Builder | WebSocket authentication and routing gaps |
| **Medium** | Builder | Unclear process model (Celery worker vs FastAPI) |
| **Low** | Architect | Opening turn / greeting trigger unspecified |
| **Low** | Architect | Single `transcript` column is unstructured |
| **Low** | Builder | Missing `requirements.txt` contents |
| **Low** | Shield | No health check or observability endpoints |
| **Low** | Shield | No defined E2E test scenarios |
