# Architect Memory Log

> **Purpose:** Every design decision and its outcome is logged here. Before producing any new design, the Architect MUST read this file and ensure past mistakes are not repeated.

## Format

Each entry follows this structure:

```
### [YYYY-MM-DD] <short title>
- **Action:** What was designed / decided
- **Consequence:** What happened as a result (positive or negative)
- **Lesson:** What to do (or avoid) next time
- **Severity:** low | medium | high | critical
```

---

## Entries

### [2026-03-02] Voicemail / Answering Machine Detection
- **Action:** Designed AMD handling across two paths: production (caller.py + callbacks.py) and live test (live_call.py). Chose `DetectMessageEnd` over `Enable` for higher accuracy. Centralized logic in new `voicemail.py` module.
- **Consequence:** Pending — to be updated after Shield review
- **Lesson:** `machine_detection="Enable"` was already set but never acted on — always follow through on feature flags with actual handling logic.
- **Severity:** medium
