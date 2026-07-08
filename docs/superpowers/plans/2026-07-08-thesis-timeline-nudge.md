# Thesis Timeline + Weekly Nudge Implementation Plan (F11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the thesis a realistic backwards timeline from the defense date and one opt-in weekly nudge, so DoThesis accompanies the student across months — earning "goes with your thesis journey."

**Architecture:** Two pure functions (`build_timeline`, `timeline_status`) + a dedicated store path + a `set_defense_date` tool + a standalone weekly-nudge module the deploy's cron runs (no in-app scheduler) + a ContextPanel timeline card. Reuses F2 roadmap position, F7 target-n, F4 memory patterns, existing `mail.py`.

**Tech Stack:** Python (pure logic + a cron-run module), LangChain `@tool`, `api/app/mail.py`, pytest via `./run.sh` (no real emails).

## Global Constraints

- **No gamification** — a calendar + one gentle weekly nudge, nothing more.
- **No in-app scheduler** — the nudge is `python -m app.jobs.weekly_nudge`, cron-invoked; idempotent (6-day window).
- **Opt-in respected at send time**; unsubscribe flips a user pref.
- **Advisory** — the timeline never blocks; infeasible plans are flagged, not refused.
- **Pure + null-safe** timeline functions (no date ⇒ `{}`).
- **Depends on F2** (roadmap position + UI), **F7** (`target_n`), **F4** (`USER_MEMORY_KEYS` + store path). **Comment the decision behind each change.**

---

### Task 1: `build_timeline` (pure)

**Files:**
- Create: `agent/timeline.py`
- Test: `api/tests/test_timeline.py`

**Interfaces:**
- Produces: `build_timeline(defense_date: date, method: str, target_n: int, today: date) -> dict` → `{milestones:[{module,label,start,end,weeks}], data_collection_weeks, total_weeks, feasible}`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_timeline.py
from datetime import date
from agent.timeline import build_timeline


def test_six_month_plan_is_feasible_and_ordered():
    tl = build_timeline(date(2026, 12, 31), "pls-sem", target_n=250, today=date(2026, 7, 1))
    assert tl["feasible"] is True
    ends = [m["end"] for m in tl["milestones"]]
    assert ends == sorted(ends)                       # chronological
    assert ends[-1] <= "2026-12-31"                   # finishes by defense
    assert tl["data_collection_weeks"] >= 3           # realistic buffer


def test_two_week_deadline_is_infeasible():
    tl = build_timeline(date(2026, 7, 15), "pls-sem", target_n=250, today=date(2026, 7, 1))
    assert tl["feasible"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_timeline.py -q` → FAIL (no module).

- [ ] **Step 3: Implement `build_timeline`**

```python
# agent/timeline.py
"""Backwards thesis timeline + progress. Pure + null-safe. Buffers reflect reality (data
collection is weeks, not days). Sizes data collection from the target sample n (shared with F7)."""
from __future__ import annotations
from datetime import date, timedelta

# Weeks reserved per phase, allocated BACKWARDS from the defense date. Data collection is
# computed separately from target_n. Buffers are deliberately generous — students underestimate.
_PHASE_WEEKS = [
    ("M5", "Writing", 4), ("defense", "Defense prep", 1),   # note: defense sits AFTER writing
    ("M4", "Data analysis", 2), ("collect", "Data collection", None),  # None = from target_n
    ("M3", "Research design + questionnaire", 2),
    ("M2", "Literature review", 3), ("M1", "Topic", 1),
]


def _collection_weeks(target_n: int) -> int:
    # ~50 quality responses/week via a typical survey push; floor 3, cap 6.
    return max(3, min(6, -(-int(target_n or 150) // 50)))


def build_timeline(defense_date: date, method: str, target_n: int, today: date) -> dict:
    coll = _collection_weeks(target_n)
    # Order the plan forward: M1 → M2 → M3 → collect → M4 → M5 → defense.
    forward = [("M1", "Topic", 1), ("M2", "Literature review", 3),
               ("M3", "Research design + questionnaire", 2),
               ("collect", "Data collection", coll), ("M4", "Data analysis", 2),
               ("M5", "Writing", 4), ("defense", "Defense prep", 1)]
    total = sum(w for _, _, w in forward)
    start = defense_date - timedelta(weeks=total)
    milestones, cursor = [], start
    for module, label, weeks in forward:
        end = cursor + timedelta(weeks=weeks)
        milestones.append({"module": module, "label": label,
                           "start": cursor.isoformat(), "end": end.isoformat(), "weeks": weeks})
        cursor = end
    return {"milestones": milestones, "data_collection_weeks": coll,
            "total_weeks": total, "feasible": start >= today}
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/timeline.py api/tests/test_timeline.py
git commit -m "feat(timeline): backwards thesis plan with realistic buffers

build_timeline plans M1->defense from the defense date; data collection sized
from target_n; flags an infeasible (too-late) start.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `timeline_status` — progress vs plan

**Files:**
- Modify: `agent/timeline.py`
- Test: `api/tests/test_timeline.py`

**Interfaces:**
- Consumes: F2 `derive_substep` / module status for `actual_phase`.
- Produces: `timeline_status(context_store: dict, today: date) -> dict` → `{expected_phase, actual_phase, weeks_behind, this_week, next_milestone, on_track}` (`{}` if no timeline).

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_timeline.py
from datetime import date
from agent.timeline import timeline_status


def _cs_with_timeline(milestones, actual_focus, status):
    return {"contextStore": {"thesis_timeline": {"milestones": milestones}},
            "focus": actual_focus, "status": status}


def test_behind_schedule_detected():
    ms = [{"module": "M4", "label": "Data analysis", "start": "2026-07-01", "end": "2026-07-15"}]
    cs = _cs_with_timeline(ms, "M2", {"M1": "done", "M2": "in_progress", "M3": "locked",
                                      "M4": "locked", "M5": "locked"})
    st = timeline_status(cs, date(2026, 7, 10))
    assert st["expected_phase"] == "M4" and st["actual_phase"] == "M2"
    assert st["weeks_behind"] >= 1 and st["on_track"] is False


def test_no_timeline_is_empty():
    assert timeline_status({"contextStore": {}, "status": {}}, date(2026, 7, 1)) == {}
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement `timeline_status`**

```python
# add to agent/timeline.py
_ORDER = ["M1", "M2", "M3", "collect", "M4", "M5", "defense"]


def timeline_status(context_store_state: dict, today: date) -> dict:
    """context_store_state is the full state dict ({contextStore, status, focus})."""
    cs = context_store_state.get("contextStore") or {}
    tl = cs.get("thesis_timeline") or {}
    ms = tl.get("milestones") or []
    if not ms:
        return {}
    # expected phase = the milestone whose window contains today (or the last past one).
    iso = today.isoformat()
    expected = ms[0]
    for m in ms:
        if m["start"] <= iso <= m["end"] or m["end"] <= iso:
            expected = m
    # actual phase = the project's focus (F2). Map "collect" to M4's neighborhood.
    actual = context_store_state.get("focus") or "M1"
    exp_i = _ORDER.index(expected["module"]) if expected["module"] in _ORDER else 0
    act_i = _ORDER.index(actual) if actual in _ORDER else 0
    behind_phases = max(0, exp_i - act_i)
    # rough weeks-behind: sum planned weeks of the phases the student hasn't reached yet.
    weeks_behind = 0
    if behind_phases:
        for m in ms:
            if m["module"] in _ORDER and act_i <= _ORDER.index(m["module"]) < exp_i:
                weeks_behind += m.get("weeks", 1)
    return {"expected_phase": expected["module"], "actual_phase": actual,
            "weeks_behind": weeks_behind, "this_week": expected["label"],
            "next_milestone": expected, "on_track": weeks_behind == 0}
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/timeline.py api/tests/test_timeline.py
git commit -m "feat(timeline): timeline_status compares roadmap position vs plan

Reads the F2 focus against the planned milestone window -> weeks_behind +
this-week focus. Pure, null-safe.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Store path + `set_defense_date` tool + M1 capture

**Files:**
- Modify: `agent/state.py` (`set_thesis_timeline`)
- Modify: `agent/tools/state_tools.py` (`set_defense_date` inside `make_state_tools`)
- Modify: `skills/dothesis-m1-topic/SKILL.md` (ask for target defense date)
- Test: `agent/tests/test_state.py`, `agent/tests/test_state_tools.py`

**Interfaces:**
- Produces: `ProjectStateStore.set_thesis_timeline(timeline: dict) -> dict` (dedicated path, no status/focus change); `set_defense_date(defense_date: str) -> str` tool.

- [ ] **Step 1: Write the failing tests**

```python
# agent/tests/test_state.py (append)
def test_set_thesis_timeline(tmp_path):
    s = _store(tmp_path)
    before = s.load()
    s.set_thesis_timeline({"milestones": [{"module": "M1"}]})
    after = s.load()
    assert after["contextStore"]["thesis_timeline"]["milestones"][0]["module"] == "M1"
    assert after["status"] == before["status"] and after["focus"] == before["focus"]
```

```python
# agent/tests/test_state_tools.py (append)
def test_set_defense_date_builds_timeline(tmp_path):
    import uuid
    from agent.state import ProjectStateStore
    from agent.tools.state_tools import make_state_tools
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    store.commit_slice("M3", {"methodology": "PLS-SEM"}, reason="x")  # so target_n has a method
    tools = {t.name: t for t in make_state_tools(store)}
    import json
    out = json.loads(tools["set_defense_date"].func(defense_date="2026-12-31"))
    assert out["feasible"] in (True, False)
    assert store.load()["contextStore"]["thesis_timeline"]["milestones"]
```

- [ ] **Step 2: Run to verify they fail** → FAIL.

- [ ] **Step 3: Implement**

Add to `ProjectStateStore` (next to `set_institution_profile`, F4):

```python
    def set_thesis_timeline(self, timeline: dict[str, Any]) -> dict[str, Any]:
        state = self.load()
        state["contextStore"]["thesis_timeline"] = timeline
        self._save(state)
        return timeline
```

Inside `make_state_tools(store)`:

```python
    @tool
    def set_defense_date(defense_date: str) -> str:
        """Record the student's target defense/submission date (YYYY-MM-DD) and build a
        realistic backwards timeline (M1->defense) they can pace against."""
        from datetime import date  # noqa: PLC0415
        from agent.timeline import build_timeline  # noqa: PLC0415
        from agent.tools.instrument import sampling_plan  # noqa: PLC0415 (F7; or inline target_n)
        import json as _json
        state = store.load()
        m3 = state["contextStore"].get("m3_design") or {}
        target_n = (m3.get("sample_plan") or {}).get("target_n") or 200
        tl = build_timeline(date.fromisoformat(defense_date),
                            m3.get("methodology") or "regression", target_n, date.today())
        store.set_thesis_timeline(tl)
        return _json.dumps(tl, ensure_ascii=False)
```

Add `set_defense_date` to the factory's returned list. In `skills/dothesis-m1-topic/SKILL.md`,
add: "Early in M1, ask for the student's target defense/submission date and call
`set_defense_date` so the whole journey has a timeline."

> **Note for implementer:** if F7's `sampling_plan` isn't landed, read `target_n` directly from
> `m3_design.sample_plan.target_n` (as above) — the tool already does, so the F7 import is
> optional.

- [ ] **Step 4: Run to verify they pass** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/state.py agent/tools/state_tools.py skills/dothesis-m1-topic/SKILL.md agent/tests/test_state.py agent/tests/test_state_tools.py
git commit -m "feat(timeline): set_defense_date tool + store path + M1 capture

M1 asks for the defense date and builds the backwards timeline; stored via a
dedicated path that never touches module status/focus.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Weekly nudge runner + opt-in + idempotency

**Files:**
- Create: `api/app/jobs/__init__.py`, `api/app/jobs/weekly_nudge.py`
- Modify: `api/app/user_memory.py` (`nudge_opt_in` in `USER_MEMORY_KEYS`)
- Test: `api/tests/test_weekly_nudge.py`

**Interfaces:**
- Produces: `run_weekly_nudge(db, mail_send, now) -> dict` — `{sent, skipped}`; runnable via `python -m app.jobs.weekly_nudge`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_weekly_nudge.py
from datetime import datetime, timezone, timedelta
from app.jobs.weekly_nudge import run_weekly_nudge


class _Proj:
    def __init__(self, pid, state, owner, last=None, opt=True):
        self.id, self._state, self.owner_id = pid, state, owner
        self.last_nudge_at, self._opt = last, opt


def test_sends_to_due_optedin_only(monkeypatch):
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    due = _Proj("p1", {"contextStore": {"thesis_timeline": {"milestones":
        [{"module": "M4", "label": "Data analysis", "start": "2026-07-01", "end": "2026-07-15"}]}},
        "focus": "M2", "status": {}}, owner="u1", last=None)
    recent = _Proj("p2", due._state, owner="u2", last=now - timedelta(days=1))
    sent = []
    res = run_weekly_nudge(
        db=None, mail_send=lambda to, subject, html: sent.append(to) or True, now=now,
        _projects=lambda db: [due, recent],
        _email_for=lambda db, uid: f"{uid}@x.com",
        _opted_in=lambda db, uid: True,
        _mark=lambda db, p, ts: setattr(p, "last_nudge_at", ts))
    assert res["sent"] == 1 and sent == ["u1@x.com"]
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement the runner + opt-in key**

Add `"nudge_opt_in"` to `USER_MEMORY_KEYS` in `api/app/user_memory.py`.

```python
# api/app/jobs/weekly_nudge.py
"""Weekly thesis nudge — the between-session accompaniment. Runnable via
`python -m app.jobs.weekly_nudge` from the deploy's cron (no in-app scheduler). Idempotent
(6-day window). Best-effort per project; opt-in honored at send time."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
_NUDGE_WINDOW = timedelta(days=6)


def run_weekly_nudge(db, mail_send, now=None, *, _projects=None, _email_for=None,
                     _opted_in=None, _mark=None) -> dict:
    """Send one nudge per due, opted-in project. Injectable deps for tests."""
    from datetime import date  # noqa: PLC0415
    from agent.timeline import timeline_status  # noqa: PLC0415
    now = now or datetime.now(timezone.utc)
    projects = (_projects or _default_projects)(db)
    sent = skipped = 0
    for p in projects:
        try:
            if p.last_nudge_at and (now - p.last_nudge_at) < _NUDGE_WINDOW:
                skipped += 1; continue
            if not (_opted_in or _default_opted_in)(db, p.owner_id):
                skipped += 1; continue
            st = timeline_status(p._state if hasattr(p, "_state") else _load_state(db, p),
                                 now.date())
            if not st:
                skipped += 1; continue
            behind = (f"You're about {st['weeks_behind']} week(s) behind."
                      if not st["on_track"] else "You're on track — keep going.")
            html = (f"<p>This week: <b>{st['this_week']}</b>.</p><p>{behind}</p>"
                    f"<p><a href='https://dothesis.app'>Open your thesis</a></p>")
            to = (_email_for or _default_email_for)(db, p.owner_id)
            if mail_send(to, "Your thesis this week", html):
                (_mark or _default_mark)(db, p, now)
                sent += 1
        except Exception:
            logger.exception("weekly_nudge: project %s failed", getattr(p, "id", "?"))
            skipped += 1
    return {"sent": sent, "skipped": skipped}


# --- real DB-backed defaults (thin; tests inject stubs) ----------------------
def _default_projects(db): ...      # query projects with a thesis_timeline
def _default_opted_in(db, uid): ... # load_user_prefs(db, uid).get("nudge_opt_in", True)
def _default_email_for(db, uid): ...
def _default_mark(db, p, ts): ...
def _load_state(db, p): ...


if __name__ == "__main__":  # pragma: no cover
    from app.db import SessionLocal          # match the app's session factory
    from app.mail import send_html
    with SessionLocal() as db:
        print(run_weekly_nudge(db, send_html))
        db.commit()
```

> **Note for implementer:** fill the four `_default_*` helpers against the real models
> (`Project` with `owner_id` + `last_nudge_at` column — add a migration for `last_nudge_at`;
> `DbProjectStateStore` for `_load_state`; `load_user_prefs` for opt-in). The injected-deps
> signature is what the test drives, so the DB wiring stays swappable.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/jobs/ api/app/user_memory.py api/tests/test_weekly_nudge.py
git commit -m "feat(timeline): weekly nudge runner (cron-run, opt-in, idempotent)

Between-session accompaniment: one email/week with this-week focus + behind
status, honoring nudge_opt_in and a 6-day window. Runs via python -m.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Timeline card in the roadmap endpoint + ContextPanel

**Files:**
- Modify: `api/app/routers/roadmap.py` (add `timeline` to the response)
- Modify: `web/app/components/chat/RoadmapPanel.tsx` (F2) — render a timeline card
- Test: `api/tests/test_roadmap_router.py`, `web/app/components/chat/RoadmapPanel.test.tsx`

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_roadmap_router.py
def test_roadmap_includes_timeline_status(monkeypatch):
    state = {"focus": "M2", "status": {"M1": "done", "M2": "in_progress", "M3": "locked",
             "M4": "locked", "M5": "locked"},
             "contextStore": {"thesis_timeline": {"milestones": [
                 {"module": "M4", "label": "Data analysis", "start": "2026-07-01", "end": "2026-07-15"}]}}}
    c = _client(monkeypatch, state)   # helper from F2's roadmap test
    body = c.post("/api/v1/projects/abc/roadmap").json()
    assert "timeline" in body and body["timeline"].get("this_week")
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Add timeline to the endpoint + UI**

In `api/app/routers/roadmap.py`, after building the roadmap, add
`"timeline": timeline_status(state, date.today())` (import `timeline_status` + `date`; `{}` when
absent — null-safe).

In `RoadmapPanel.tsx` (F2), render a small timeline card at the top when `data.timeline?.this_week`
exists: "This week: {this_week}" + an on-track/behind badge (`weeks_behind`).

```tsx
{data.timeline?.this_week && (
  <div className="rounded-xl border border-ink-200 p-3 text-[12.5px]">
    <div className="font-semibold text-ink-800">This week: {data.timeline.this_week}</div>
    <div className={data.timeline.on_track ? "text-green-600" : "text-amber-600"}>
      {data.timeline.on_track ? "On track" : `~${data.timeline.weeks_behind} week(s) behind`}
    </div>
  </div>
)}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_roadmap_router.py -q` and `cd web && npm test -- RoadmapPanel` → PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/roadmap.py web/app/components/chat/RoadmapPanel.tsx api/tests/test_roadmap_router.py web/app/components/chat/RoadmapPanel.test.tsx
git commit -m "feat(timeline): you-are-here-vs-plan card in the roadmap

Roadmap endpoint returns timeline_status; ContextPanel shows this-week focus +
on-track/behind badge so the plan is visible every session.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_timeline.py ../agent/tests/test_state.py ../agent/tests/test_state_tools.py tests/test_weekly_nudge.py tests/test_roadmap_router.py -q` → all PASS.
- [ ] `cd web && npm test -- RoadmapPanel` → PASS.
- [ ] No real emails in tests (mail is injected/stubbed).
- [ ] Dry run: `./run.sh python -m app.jobs.weekly_nudge` sends to due, opted-in projects only.
- [ ] Deploy: register the weekly cron (e.g. `0 9 * * MON python -m app.jobs.weekly_nudge`).

## Notes

- **This is what makes the tagline literal** — steps 1–3 add the in-app timeline; step 4 is the
  between-session accompaniment; step 5 keeps it visible.
- **Migration:** add a `last_nudge_at` timestamp column to `projects` (Task 4).
- **Depends on F2** (roadmap position + UI), **F7** (`target_n`, optional — falls back to a stored
  value), **F4** (`USER_MEMORY_KEYS` + store-path pattern), **F6** (the defense block).
