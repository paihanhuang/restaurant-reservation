# Voicemail / Answering Machine Detection

## Problem Restatement

When a restaurant's number goes to voicemail, the agent currently talks into the void. It should detect the machine, leave a brief message after the beep, hang up, and retry.

## ASSUMPTIONS

- Twilio `machine_detection="Enable"` already exists in `caller.py` but is never acted on
- Twilio AMD reports `AnsweredBy`: `human`, `machine_start`, `machine_end_beep`, `machine_end_silence`, `machine_end_other`, `fax`, `unknown`
- Retry logic exists in `call_task.py` (max 3 attempts, exponential backoff)
- `live_call.py` has no machine detection

## IN_SCOPE

- Detect voicemail via Twilio AMD
- Leave a scripted voicemail message
- Schedule retry (reuse existing backoff)
- Integration in both production path and live test path

## OUT_OF_SCOPE

- Custom ML-based detection, voicemail transcription, per-type behavior differences

## DESIGN

### New: `src/telephony/voicemail.py`

```python
VOICEMAIL_MESSAGE = "Hi, this is an automated call regarding a reservation..."

def is_machine(answered_by: str) -> bool: ...
def build_voicemail_twiml(reservation: dict) -> str: ...
```

### Modified Files

| File | Change |
|------|--------|
| `caller.py` | `Enable` → `DetectMessageEnd`, add `async_amd_status_callback` URL |
| `callbacks.py` | Read `AnsweredBy`, delegate to voicemail logic on machine |
| `live_call.py` | Add AMD + `/voice/amd-status` webhook, voicemail + retry flow |

---

## Staged Implementation Plan (V-Model)

### Stage 1: Core Module — `voicemail.py` + Unit Tests

**Implement:**
- [voicemail.py](file:///home/etem/reservation-agent/src/telephony/voicemail.py) — `is_machine()`, `build_voicemail_twiml()`

**Test immediately:**
- [test_voicemail.py](file:///home/etem/reservation-agent/tests/unit/test_voicemail.py)
  - `is_machine("human")` → False
  - `is_machine("machine_end_beep")` → True
  - All 7 `AnsweredBy` values covered
  - `build_voicemail_twiml()` returns valid TwiML with `<Say>` + `<Hangup>`
  - Voicemail message contains reservation details

**Verify:** `PYTHONPATH="" .venv/bin/python -I -m pytest tests/unit/test_voicemail.py -v`

---

### Stage 2: Production Path — `caller.py` + `callbacks.py` + Integration Tests

**Implement:**
- [caller.py](file:///home/etem/reservation-agent/src/telephony/caller.py) — switch to `DetectMessageEnd`, add `async_amd_status_callback` URL
- [callbacks.py](file:///home/etem/reservation-agent/src/telephony/callbacks.py) — add `handle_amd_callback()` that reads `AnsweredBy` and acts

**Test immediately:**
- [test_callbacks.py](file:///home/etem/reservation-agent/tests/unit/test_callbacks.py) — add AMD callback tests:
  - `AnsweredBy=human` → no action
  - `AnsweredBy=machine_end_beep` → returns voicemail TwiML
  - Missing `AnsweredBy` → default to human (safe fallback)

**Verify:** `PYTHONPATH="" .venv/bin/python -I -m pytest tests/unit/test_callbacks.py tests/unit/test_voicemail.py -v`

---

### Stage 3: Live Test Path — `live_call.py` + Manual Verification

**Implement:**
- [live_call.py](file:///home/etem/reservation-agent/scripts/live_call.py) — add `machine_detection="DetectMessageEnd"`, `/voice/amd-status` webhook, voicemail message on detection, retry notice

**Test immediately:**
- Full regression: `PYTHONPATH="" .venv/bin/python -I -m pytest tests/ --tb=short`

**Manual verify:**
- Run `live_call.py` → let phone ring to voicemail → confirm:
  1. Terminal shows `⚡ VOICEMAIL DETECTED`
  2. Voicemail message is left
  3. Call disconnects
  4. Retry notice is printed

---

## RISKS

| Risk | Severity | Mitigation |
|------|----------|------------|
| AMD false positive (human → machine) | Medium | `DetectMessageEnd` is more accurate; log for audit |
| AMD adds 3-5s detection delay | Low | Acceptable tradeoff |
| Async AMD callback after conversation starts | Medium | Gracefully end with voicemail message |

## ACCEPTANCE_CRITERIA

1. ✅ `is_machine()` classifies all 7 `AnsweredBy` values correctly
2. ✅ Voicemail TwiML contains reservation details + `<Hangup>`
3. ✅ `caller.py` uses `DetectMessageEnd` with async callback
4. ✅ `callbacks.py` handles AMD status and triggers voicemail
5. ✅ `live_call.py` shows `VOICEMAIL DETECTED` and prints retry info
6. ✅ Existing human-answered calls are unaffected
7. ✅ All existing tests pass + new voicemail tests pass

## MEMORY_APPLIED

None applicable — architect memory log was empty.
