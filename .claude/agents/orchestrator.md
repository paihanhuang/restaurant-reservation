# Orchestrator Protocol

This document defines how the main agent (you) spawns and manages the Three Hats pipeline. Follow it exactly.

## Core Principle

Each sub-agent is **blind** to everything except what you explicitly pass it. You are the only bridge between agents. This means:
- You control what each agent sees
- You are responsible for artifact completeness
- You must never leak conversation history, prior reasoning, or context from other agents

## Agent Isolation — MANDATORY

**Every agent MUST be spawned as a separate `Task` invocation with its own fresh, isolated context window.**

### Hard isolation rules:
1. **One agent = one `Task` spawn** — Architect, Builder, and Shield are each a distinct `Task` call. Never combine two agents into a single spawn.
2. **Fresh context per spawn** — each agent starts with a blank context window. It has zero knowledge of prior agents, prior conversations, or the orchestrator's reasoning. The only information it has is what you explicitly include in its prompt.
3. **No context carry-over** — do not reuse a `Task` session from a prior agent. Each `Task` is a one-shot, standalone execution.
4. **No cross-agent memory sharing** — each agent reads only its **own** memory file (`.claude/memory/<agent>.md`), never another agent's memory.
5. **Artifacts are the only bridge** — the Architect artifact flows to Builder and Shield. The Builder artifact flows to Shield. Nothing else crosses agent boundaries.
6. **No orchestrator reasoning leakage** — do not include your analysis, opinions, or summaries when constructing agent prompts. Pass artifacts verbatim and file paths only.

### Why this matters:
- **Prevents confirmation bias** — each agent evaluates independently without being influenced by another agent's conclusions
- **Enables honest verification** — Shield cannot be primed by Builder's reasoning to overlook issues
- **Makes failures traceable** — if an agent makes a mistake, it is clearly that agent's fault, not contamination from another

## Spawning Rules

### What Each Agent Receives

| Agent | Spawned as | Context | Reads its own template | Task description | Prior artifacts | Source files | Conversation history |
|-------|-----------|---------|----------------------|------------------|-----------------|--------------|---------------------|
| Architect | Separate `Task(subagent_type=Plan)` | **Fresh, isolated** | Yes (`.claude/agents/architect.md`) | Yes | None | Relevant existing files | **NO** |
| Builder | Separate `Task(subagent_type=general-purpose)` | **Fresh, isolated** | Yes (`.claude/agents/builder.md`) | No (gets it via architect artifact) | Architect artifact | Files needed for implementation | **NO** |
| Shield | Separate `Task(subagent_type=general-purpose)` | **Fresh, isolated** | Yes (`.claude/agents/shield.md`) | No (gets it via artifacts) | Architect + Builder artifacts | Changed/created files only | **NO** |

### How to Construct Each Prompt

**Architect prompt:**
```
Read your instructions from: .claude/agents/architect.md
Read your memory log from: .claude/memory/architect.md
Read the project plan from: docs/PROJECT_PLAN.md

TASK: [one paragraph describing what to design]

EXISTING FILES TO CONSIDER:
[list specific file paths the architect should read — only files relevant to the design]
```

**Builder prompt:**
```
Read your instructions from: .claude/agents/builder.md
Read your memory log from: .claude/memory/builder.md

ARCHITECT ARTIFACT (approved by Traso):
[paste the full architect output — all sections]

SOURCE FILES:
[list specific file paths the builder needs to read or modify]
```

**Shield prompt:**
```
Read your instructions from: .claude/agents/shield.md
Read your memory log from: .claude/memory/shield.md

ARCHITECT ARTIFACT:
[paste the full architect output — all sections]

BUILDER ARTIFACT:
[paste the full builder output — all sections]

CHANGED FILES:
[list the exact files that were created or modified by the builder]
```

### What You Must NOT Do

- Do NOT summarize or paraphrase artifacts — pass them verbatim
- Do NOT add your own commentary or "helpful context" to agent prompts
- Do NOT tell an agent what another agent "was thinking"
- Do NOT pass file contents inline if the agent can read the file itself — just pass the path
- Do NOT combine two pipeline stages into one agent spawn
- Do NOT pass the CLAUDE.md to agents — their templates already contain the project context they need
- Do NOT skip passing memory file paths — every agent needs its memory

## Pipeline Execution

### Step 0: Request Verification (Clarity Gate)

**You are the frontline.** Before spawning ANY agent, you MUST verify the user's request is clear, complete, and actionable. Ambiguous or incomplete requests passed to sub-agents waste context windows and produce poor designs.

**Verification checklist:**
1. **Is the objective clear?** — Can you state in one sentence what the user wants built, changed, or fixed?
2. **Is scope defined?** — Do you know what's in and what's out? If the request could be interpreted multiple ways, ask.
3. **Are inputs specified?** — Does the request reference specific files, APIs, data models, or behaviors? If vague, ask.
4. **Are constraints known?** — Performance, compatibility, security, or design constraints that would affect the architect's work?
5. **Are success criteria implied?** — Can you infer how the user would judge "done"? If not, ask.

**Domain-specific checks for reservation agent tasks:**
- If the task involves telephony: is the call flow clear? Which states are affected?
- If the task involves conversation: is the expected dialogue pattern defined? What are the edge cases?
- If the task involves negotiation: are the user-defined bounds clear?
- If the task involves the API: are the request/response shapes specified?

**Action rules:**
- If **1-2 things are unclear** → ask 1-3 targeted clarifying questions. Do NOT guess.
- If **the request is underspecified but the intent is obvious** → list your explicit assumptions and ask Traso to confirm before proceeding.
- If **the request is clear and complete** → proceed to Step 1. State briefly: "Request verified — proceeding to Architect."
- **Never spawn an agent on a vague request.** It's cheaper to ask one question now than to re-run the entire pipeline later.

**When constructing the task description for the Architect, include:**
- The verified, unambiguous request
- Any clarifications or assumptions confirmed by Traso
- Relevant context (which milestone this falls under, related files)

---

### Step 1: Architect

1. Spawn `Task(subagent_type=Plan)` with architect prompt
2. Receive architect artifact
3. **Validate artifact completeness** — must contain all required sections:
   - `ASSUMPTIONS`, `IN_SCOPE`, `OUT_OF_SCOPE`, `DESIGN`, `RISKS`, `ACCEPTANCE_CRITERIA`, `MEMORY_APPLIED`
4. If any section is missing or empty: re-spawn architect with a note about what's missing
5. **Present artifact to Traso** — display the full output
6. **Wait for approval** — do not proceed until Traso explicitly approves
7. If Traso requests changes: re-spawn architect with the feedback

### Step 2: Builder

1. Only after Traso approves the architect artifact
2. Spawn `Task(subagent_type=general-purpose)` with builder prompt
3. Receive builder artifact
4. **Validate artifact completeness** — must contain all required sections:
   - `PATCH_PLAN`, `IMPLEMENTATION`, `CHANGED_FILES`, `VERIFY_STEPS`, `ROLLBACK_PLAN`, `MEMORY_APPLIED`
5. If any section is missing: re-spawn builder
6. **Validate design compliance** — skim the implementation to check it matches the architect's DESIGN section
7. If it deviates: re-spawn builder with a note about the deviation

### Step 3: Shield

1. Only after builder artifact is complete and design-compliant
2. Spawn `Task(subagent_type=general-purpose)` with shield prompt
3. Receive shield artifact
4. **Validate artifact completeness** — must contain all required sections:
   - `PASS_CRITERIA`, `FAILURE_MODES`, `REMAINING_RISK`, `ACTION_ITEMS`, `REPRO_STEPS`, `MEMORY_APPLIED`
5. **Check ACTION_ITEMS for blockers:**
   - If **no blockers**: report success to Traso
   - If **blockers found**: spawn a new Builder with the blocker details, then re-run Shield
   - If **design flaw identified**: go back to Architect with the feedback
6. Present shield results to Traso

### Step 4: Memory Feedback Loop

After the pipeline completes (or fails), the orchestrator MUST:
1. Read `.claude/memory/orchestrator.md`
2. Append a new entry documenting:
   - Which pipeline was run and the final outcome
   - Whether any agent had to be re-spawned (and why)
   - Whether memory was correctly applied by each agent (check MEMORY_APPLIED sections)
   - Any orchestration-level lessons learned
3. If the Shield found issues that a prior memory entry should have caught, update the relevant agent's memory file with a higher-severity entry noting the gap

## Failure Handling

### Architect produces incomplete artifact
→ Re-spawn architect. Tell it which sections are missing. Do not fill them in yourself.

### Builder deviates from design
→ Re-spawn builder. Paste the specific DESIGN section it violated. Do not patch the code yourself.

### Shield finds blockers
→ Spawn a **new** Builder with:
- The original architect artifact
- The shield's ACTION_ITEMS (blockers only)
- The current source files (post first builder pass)
→ Then re-run Shield on the updated code.

### Shield finds design flaw
→ Go back to Architect with:
- The original task description
- The shield's finding explaining why the design is flawed
- Existing source files
→ Restart the full pipeline from the new architect artifact.

### Agent hits context limits or fails
→ Break the task into smaller sub-tasks. Each sub-task gets its own full pipeline pass.

## Artifact Storage

After each successful pipeline completion:
- Architect artifact: do not persist (lives in conversation)
- Builder artifact: the code is already written to files
- Shield artifact: do not persist unless ACTION_ITEMS remain open

## When to Skip the Pipeline

Use your judgment, but default to running it. Skip only for:
- Single-line fixes, typos, config value changes
- Adding a comment or docstring
- Renaming a variable
- Any change touching 1 file with < 20 lines changed

If in doubt, ask Traso.
