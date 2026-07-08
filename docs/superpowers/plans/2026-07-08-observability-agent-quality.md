# Observability & Agent-Quality Evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit best-effort agent-quality events to PostHog from the moments that matter, and define a dashboard (funnel, gate rates, hallucination catches, quality trend, advisor loop).

**Architecture:** A thin `api/app/analytics.py` `emit()` wraps the PostHog SDK — fire-and-forget, no-op when unconfigured, swallows all errors. Instrument state transitions, quality reviews, the advisor loop, and exports. Dashboards are HogQL defined in a docs reference and created via the PostHog MCP/UI.

**Tech Stack:** Python 3, PostHog Python SDK, FastAPI/SQLAlchemy, pytest via `./run.sh`.

## Global Constraints

- **Analytics never blocks or breaks a turn.** Every `emit` is best-effort; a failure logs at debug and returns.
- **Inert when unconfigured.** No `POSTHOG_API_KEY` ⇒ `emit` no-ops. Safe to land before prod PostHog is provisioned.
- **No new PII.** Only ids already in the system (`user_id` as `distinct_id`, `project_id`).
- **No headless coupling.** Auto/partner may emit `export_completed` but gain no blocking logic (`project_headless_surfaces` memory).
- **Specs 2–4 produce most events** — this plan instruments them; order it last.
- **Comment the decision behind each change** (project convention).

---

### Task 1: `emit()` — best-effort PostHog capture

**Files:**
- Create: `api/app/analytics.py`
- Modify: `api/app/settings.py` (add `posthog_api_key`, `posthog_host`)
- Modify: `api/pyproject.toml` (add `posthog` dependency)
- Test: `api/tests/test_analytics.py`

**Interfaces:**
- Produces: `emit(event: str, distinct_id: str | None, properties: dict | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_analytics.py
from app import analytics


def test_emit_noop_without_key(monkeypatch):
    monkeypatch.setattr(analytics, "_client", lambda: None)  # unconfigured
    analytics.emit("x", "u", {"a": 1})   # must not raise


def test_emit_swallows_sdk_errors(monkeypatch):
    class _Boom:
        def capture(self, *a, **k): raise RuntimeError("posthog down")
    monkeypatch.setattr(analytics, "_client", lambda: _Boom())
    analytics.emit("x", "u", {"a": 1})   # must not raise


def test_emit_calls_capture_when_configured(monkeypatch):
    seen = {}
    class _Ok:
        def capture(self, distinct_id=None, event=None, properties=None, **k):
            seen.update(distinct_id=distinct_id, event=event, properties=properties)
    monkeypatch.setattr(analytics, "_client", lambda: _Ok())
    analytics.emit("module_status_changed", "user-1", {"module": "M1"})
    assert seen["event"] == "module_status_changed" and seen["distinct_id"] == "user-1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_analytics.py -q`
Expected: FAIL — `ModuleNotFoundError: app.analytics`.

- [ ] **Step 3: Implement `emit` + settings + dep**

Add to `api/app/settings.py` (next to other settings fields): `posthog_api_key: str = ""`,
`posthog_host: str = "https://us.i.posthog.com"`. Add `posthog` to `api/pyproject.toml`
dependencies and install into `.venv` (`cd api && ./run.sh python -m pip install posthog`).

```python
# api/app/analytics.py
"""Best-effort agent-quality event capture to PostHog. Fire-and-forget: no-ops when
unconfigured, swallows every error, never blocks or breaks a turn. Backend-only
(agent-quality signal), not product analytics."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CACHED = {"client": None, "init": False}


def _client():
    """Lazily build a PostHog client from settings, or None if unconfigured."""
    if _CACHED["init"]:
        return _CACHED["client"]
    _CACHED["init"] = True
    try:
        from .settings import get_settings  # noqa: PLC0415
        s = get_settings()
        if not getattr(s, "posthog_api_key", ""):
            _CACHED["client"] = None
        else:
            from posthog import Posthog  # noqa: PLC0415
            _CACHED["client"] = Posthog(project_api_key=s.posthog_api_key, host=s.posthog_host)
    except Exception:
        logger.debug("analytics: client init failed; disabling", exc_info=True)
        _CACHED["client"] = None
    return _CACHED["client"]


def emit(event: str, distinct_id: str | None, properties: dict | None = None) -> None:
    """Capture one agent-quality event. Best-effort — any failure is logged at debug."""
    try:
        client = _client()
        if client is None:
            return
        client.capture(distinct_id=distinct_id or "anonymous", event=event,
                       properties=properties or {})
    except Exception:
        logger.debug("analytics: emit(%s) failed", event, exc_info=True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_analytics.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add api/app/analytics.py api/app/settings.py api/pyproject.toml api/tests/test_analytics.py
git commit -m "feat(obs): best-effort PostHog emit layer

Fire-and-forget agent-quality capture; no-ops unconfigured, swallows errors,
never blocks a turn.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Instrument state transitions

Emit on the module-status moments in the DB-backed store, where user/project ids are known.

**Files:**
- Modify: `api/app/agent_state.py` (`DbProjectStateStore.commit_slice` override / hook)
- Test: `api/tests/test_agent_state_events.py`

**Interfaces:**
- Consumes: `analytics.emit`.
- Emits: `module_status_changed {module, from, to, project_id}`, `done_rejected_empty {module, project_id}`, `needs_review_propagated {module, downstream, project_id}`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_agent_state_events.py
import app.analytics as analytics
from app.agent_state import DbProjectStateStore


def test_commit_emits_status_change(monkeypatch, db_engine, project_id):  # fixtures per repo conventions
    events = []
    monkeypatch.setattr(analytics, "emit", lambda e, uid, props=None: events.append((e, props)))
    store = DbProjectStateStore(db_engine, project_id, "/tmp/ws")
    store.commit_slice("M1", {"research_title": "T"}, reason="x")
    assert any(e == "module_status_changed" for e, _ in events)


def test_empty_done_emits_rejected(monkeypatch, db_engine, project_id):
    events = []
    monkeypatch.setattr(analytics, "emit", lambda e, uid, props=None: events.append(e))
    store = DbProjectStateStore(db_engine, project_id, "/tmp/ws")
    try:
        store.commit_slice("M5", {}, reason="x", confirm_done=True)  # empty-done -> ValueError
    except ValueError:
        pass
    assert "done_rejected_empty" in events
```

> **Note for implementer:** reuse the repo's existing DB/project test fixtures (see
> `api/tests/test_agent_state*.py` or `conftest.py`) for `db_engine`/`project_id`; don't invent
> new fixtures.

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_agent_state_events.py -q`
Expected: FAIL — no events emitted.

- [ ] **Step 3: Instrument `DbProjectStateStore`**

In `api/app/agent_state.py`, wrap `commit_slice` (override that calls `super().commit_slice`)
so it emits around the state write. Read `before` status, call super, then emit — and catch
the empty-done `ValueError` to emit `done_rejected_empty` before re-raising:

```python
    def commit_slice(self, module, writes, reason, confirm_done=False, status_overrides=None):
        from .analytics import emit  # noqa: PLC0415 — local import keeps state layer clean
        uid = str(getattr(self, "user_id", "") or "") or None
        before = self.load()["status"].get(module)
        try:
            result = super().commit_slice(module, writes, reason,
                                          confirm_done=confirm_done, status_overrides=status_overrides)
        except ValueError as e:
            if "cannot mark" in str(e):  # the empty-done gate
                emit("done_rejected_empty", uid, {"module": module, "project_id": str(self.project_id)})
            raise
        after = self.load()["status"].get(module)
        if after != before:
            emit("module_status_changed", uid,
                 {"module": module, "from": before, "to": after, "project_id": str(self.project_id)})
        flagged = [d for d in result.get("flagged", [])] if isinstance(result, dict) else []
        if flagged:
            emit("needs_review_propagated", uid,
                 {"module": module, "downstream": flagged, "project_id": str(self.project_id)})
        return result
```

> **Note for implementer:** confirm `DbProjectStateStore` has `user_id` available (thread it
> through `__init__` if the store knows the project's owner; else pass `None` — `emit` handles
> it). Confirm the `commit_slice` return dict key for flagged modules (`agent/state.py:212`
> returns `module`/`focus`; extend it to include `flagged` if not already, or recompute from
> `DOWNSTREAM`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_agent_state_events.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/agent_state.py api/tests/test_agent_state_events.py
git commit -m "feat(obs): emit module status + gate events from DbProjectStateStore

module_status_changed / done_rejected_empty / needs_review_propagated — the raw
signal for the completion funnel and gate-pass-rate insights.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Instrument quality, coaching, advisor, export

**Files:**
- Modify: `agent/tools/writing.py` (`review_thesis` → `quality_reviewed`)
- Modify: `agent/tools/state_tools.py` (`ingest_advisor_feedback` → `advisor_feedback_ingested`; `mark_feedback_addressed` → `advisor_feedback_addressed`)
- Modify: the roadmap endpoint (`api/app/routers/roadmap.py`) → `next_action_surfaced`
- Modify: export sites (`agent/tools/writing.py` export, `partner_report_service`, `job_runner`) → `export_completed`
- Test: `api/tests/test_quality_events.py`

**Interfaces:**
- Consumes: `analytics.emit`.

> **Cross-layer note:** `agent/tools/*` currently avoid importing `app.*` (agent is a lower
> layer). To keep that boundary, add a tiny indirection: `agent/analytics.py` with a settable
> `emit` hook that defaults to a no-op, and have `api` wire it to `app.analytics.emit` at
> startup (in `create_app`). Agent tools call `agent.analytics.emit`; tests stub it directly.
> (If the repo already lets `agent` import `app`, skip the indirection and import directly.)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_quality_events.py
import agent.analytics as aa
from agent.tools.writing import make_writing_tools


class _Store:
    def load_full_context_store(self):
        return {"m1_topic": {"research_title": "T"}, "m3_design": {"methodology": "PLS-SEM"}}


def test_review_thesis_emits_quality_reviewed(monkeypatch):
    events = []
    monkeypatch.setattr(aa, "emit", lambda e, uid, props=None: events.append((e, props)))
    tools = {t.name: t for t in make_writing_tools(_Store())}
    tools["review_thesis"].func()
    assert any(e == "quality_reviewed" for e, _ in events)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_quality_events.py -q`
Expected: FAIL — no `quality_reviewed` event.

- [ ] **Step 3: Implement the indirection + emits**

```python
# agent/analytics.py
"""Analytics hook for the agent layer — a no-op until the app wires it to PostHog,
so agent/ never imports app/. app.create_app() sets `emit` at startup."""
from __future__ import annotations
from typing import Callable

def _noop(event: str, distinct_id: str | None, properties: dict | None = None) -> None:
    return

emit: Callable[..., None] = _noop
```

In `create_app` (api startup), add: `import agent.analytics as aa; from .analytics import emit
as _e; aa.emit = _e`.

Then emit at each site (best-effort — wrap in try/except or rely on `emit` being safe):
- `review_thesis` (after computing the result):
  `aa.emit("quality_reviewed", None, {"overall": r["overall"], "method": r["method"], "blocking_count": len(r.get("blocking", []))})`
- `ingest_advisor_feedback` (after loop): `aa.emit("advisor_feedback_ingested", None, {"count": added})`
- `mark_feedback_addressed`: `aa.emit("advisor_feedback_addressed", None, {})`
- roadmap endpoint (after computing `next_action`):
  `emit("next_action_surfaced", None, {"module": na.get("module"), "substep": na.get("substep")})`
- export sites: `emit("export_completed", uid, {"scope": scope, "surface": "chat"|"auto"|"partner"})`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_quality_events.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/analytics.py agent/tools/writing.py agent/tools/state_tools.py api/app/routers/roadmap.py api/app/main.py api/tests/test_quality_events.py
git commit -m "feat(obs): emit quality/coaching/advisor/export events

quality_reviewed, next_action_surfaced, advisor_feedback_*, export_completed —
via an agent.analytics no-op hook the app wires to PostHog (keeps agent below app).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Dashboard definitions + create via MCP/UI

**Files:**
- Create: `docs/observability/agent-quality-events.md`

Dashboards aren't code — this task documents the event schema + the HogQL for each insight,
then creates them once in PostHog (via the MCP or UI). No automated test.

- [ ] **Step 1: Write the reference doc**

`docs/observability/agent-quality-events.md` — the event table (from the spec) + HogQL per
insight:
- **Completion funnel:** funnel over `module_status_changed` where `to = 'done'`, steps M1→M5.
- **Gate pass rate:** `countIf(event='done_rejected_empty') / countIf(event='module_status_changed' and properties.to='done')` grouped by `properties.module`.
- **Hallucination catches:** trend of `citation_rejected` count, breakdown by `properties.kind`.
- **Quality trend:** `avg(properties.overall)` of `quality_reviewed` over time, breakdown by
  `properties.method`.
- **Advisor loop:** `advisor_feedback_ingested` vs `advisor_feedback_addressed` over time.

- [ ] **Step 2: Create the dashboard**

Using the PostHog MCP (project token in the MCP context) or the UI, create one "DoThesis —
Agent Quality" dashboard with the five insights above. Record their URLs in the doc.

- [ ] **Step 3: Commit**

```bash
git add docs/observability/agent-quality-events.md
git commit -m "docs(obs): agent-quality event schema + dashboard HogQL

Source-of-truth for the emitted events and the five insights (funnel, gate rate,
hallucination catches, quality trend, advisor loop).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_analytics.py tests/test_agent_state_events.py tests/test_quality_events.py -q` → all PASS.
- [ ] Inert-when-unconfigured confirmed: with `POSTHOG_API_KEY` unset, run a turn locally → no errors, `emit` no-ops.
- [ ] Headless untouched: `cd api && ./run.sh pytest tests/test_partner_report.py -q` green; `export_completed` from partner is best-effort only.

## Notes / spec deviations

- **`agent.analytics` no-op hook** keeps the agent layer from importing `app` — the app wires
  the real `emit` at startup. If the codebase already permits `agent` → `app` imports, drop the
  indirection and import `app.analytics.emit` directly.
- **`citation_rejected` emit site** depends on where citation validation is centralized;
  emit it from the quality rubric's citation dimension (Spec 3) and/or `validate_citations`
  callers — pick the single chokepoint during implementation.
- Dashboards are created out-of-band (MCP/UI); only their definitions are version-controlled.
