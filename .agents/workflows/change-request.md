---
description: V-Model workflow for any non-trivial code change — propose first, then implement
---

# Change Request Workflow

// turbo-all

## Step 1: Read CLAUDE.md
Read the project operating contract:
```
cat /home/etem/reservation-agent/CLAUDE.md
```

## Step 2: Clarity Gate
- If the request is ambiguous, ask 1-3 clarifying questions and STOP.
- If underspecified, list explicit assumptions before proceeding.

## Step 3: Proposal
Present a structured plan to the user for approval:
1. **Problem Restatement** — what we're solving
2. **Assumptions & Constraints**
3. **Architectural Specs** — which files change, interfaces, data structures
4. **QA Strategy** — edge cases, verification plan
5. **Risk Check** — anything that could break

**STOP HERE. Wait for user approval before proceeding.**

## Step 4: Implementation
- Only after user explicitly approves the plan
- Generate code matching approved specs
- Minimal, focused diffs — no drive-by refactors

## Step 5: Verification
- Add/update tests immediately after implementation
- Run full regression: `PYTHONPATH="" .venv/bin/python -I -m pytest tests/ --tb=short`
- Validate against Step 3 QA strategy
- Commit with descriptive message
