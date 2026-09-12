# Advisory Focus and Artifact Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep agent tool use and module movement free while preventing artifacts from being persisted to the wrong module.

**Architecture:** A pure resolver derives an optional canonical write target from current and recent dialogue. The target rides in a private prompt marker; agent middleware validates matching `commit_slice` calls and leaves every other tool untouched.

**Tech Stack:** Python 3.13, FastAPI, LangChain middleware, deepagents, pytest

**Spec:** `docs/superpowers/specs/2026-09-12-advisory-focus-artifact-routing-design.md`

## Global Constraints

- `commit_slice` remains the only state write path.
- Tool selection and tool ordering remain model-directed.
- `focus` is advisory and never overrides explicit artifact intent.
- Ambiguous turns receive no routing target.
- Headless behavior remains unchanged.

---

### Task 1: Pure artifact target resolver

**Files:**
- Create: `agent/artifact_routing.py`
- Create: `agent/tests/test_artifact_routing.py`

**Interfaces:**
- Produces: `WriteTarget(module: str, key: str, artifact: str)`
- Produces: `resolve_write_target(text: str, recent_messages: Sequence[str]) -> WriteTarget | None`
- Produces: `write_target_marker(target: WriteTarget) -> str`

- [x] Write failing tests for explicit questionnaire routing, terse follow-up inheritance, explicit override, and ambiguity.
- [x] Run `python3 -m pytest agent/tests/test_artifact_routing.py -q` and verify failure.
- [x] Implement conservative bilingual artifact patterns and marker serialization.
- [x] Run the tests and verify they pass.

### Task 2: Commit routing middleware

**Files:**
- Modify: `agent/artifact_routing.py`
- Modify: `agent/runtime.py`
- Test: `agent/tests/test_artifact_routing.py`

**Interfaces:**
- Produces: `ArtifactRoutingMiddleware`, which inspects `[WRITE TARGET]` in the latest human message.
- Consumes: `commit_slice` calls shaped as `{module, writes, reason, ...}`.

- [x] Add failing tests proving non-state tools pass through, a mismatched commit is rejected, and a matching commit executes.
- [x] Run the focused tests and verify failure.
- [x] Implement middleware using `wrap_tool_call`; return a `ToolMessage` error on mismatch.
- [x] Register middleware in `create_deep_agent`.
- [x] Run focused tests and verify success.

### Task 3: API routing and truthful completion

**Files:**
- Modify: `api/app/routers/chat_v3.py`
- Modify: `api/tests/test_chat_v3_intent.py`

**Interfaces:**
- Consumes: recent user and assistant message text.
- Produces: private write-target marker in `_runtime_text`.
- Produces: artifact-aware saved-claim verification.

- [x] Add failing tests for questionnaire inheritance from the previous assistant turn and target-specific success checks.
- [x] Run `python3 -m pytest api/tests/test_chat_v3_intent.py -q` and verify failure.
- [x] Resolve the target before inserting the current message and include the marker in the runtime input.
- [x] Require successful `commit_slice` output for the matching module/key before preserving a “saved” claim.
- [x] Run focused tests and verify success.

### Task 4: Make focus explicitly advisory

**Files:**
- Modify: `skills/dothesis/SKILL.md`
- Modify: `agent/runtime.py`

**Interfaces:**
- Changes instructions only; state storage and focus updates remain compatible.

- [x] Update the root skill first: route by artifact intent, use focus only for context-free continuation, and allow bounded cross-module work.
- [x] Update the system prompt to permit free tool choice and cross-module reads/writes.
- [x] Verify skill body remains below 500 lines.

### Task 5: Regression verification

**Files:**
- Test: `agent/tests/test_artifact_routing.py`
- Test: `api/tests/test_chat_v3_intent.py`
- Test: `agent/tests/test_m3_contract.py`
- Test: relevant state-tool tests

- [x] Run the focused test files.
- [x] Run the broader agent/API routing test subset.
- [x] Confirm a simulated questionnaire save to M5 is rejected and the same save to M3 succeeds.
- [x] Review the final diff for unrelated changes and report any pre-existing failures separately.
