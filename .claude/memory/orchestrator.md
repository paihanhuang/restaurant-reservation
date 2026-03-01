# Orchestrator Memory Log

> **Purpose:** Every pipeline execution decision and its outcome is logged here. Before spawning agents or passing artifacts, the Orchestrator MUST read this file and ensure past mistakes are not repeated.

## Format

Each entry follows this structure:

```
### [YYYY-MM-DD] <short title>
- **Action:** What pipeline decision was made (spawn order, artifact passing, re-spawn, skip)
- **Consequence:** What happened as a result (positive or negative)
- **Lesson:** What to do (or avoid) next time
- **Severity:** low | medium | high | critical
```

---

## Entries

_No entries yet. This file will be populated as the project progresses._
