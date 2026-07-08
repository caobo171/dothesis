# F0 — Foundation Fixes & Plan Remediation (P0, do FIRST)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Why this exists:** an independent Fable-5 audit (2026-07-08) found that the coaching/memory features (F2/F4/F7/F11) are designed against the FILE-backed `ProjectStateStore` but production uses `DbProjectStateStore`, which round-trips **only `SLICE_OWNERSHIP` keys** — so `roadmap_tasks`, `advisor_feedback`, `institution_profile`, `thesis_timeline`, field-it results would be **written, dropped, and never read back in prod**, while file-store unit tests stay green. Plus a set of contract/auth/packaging/test defects. This plan makes the program buildable. **Nothing in F2/F4/F7/F11 should start before Part A lands.**

**Goal:** persist new context_store keys in the DB, give consumers a real read API, fix the cross-cutting contract/auth/packaging defects, and record per-plan errata.

**Tech Stack:** SQLAlchemy + Alembic (`api/migrations/versions`), pytest via `./run.sh` (arm64). See `project_db_store_persistence_gap` memory.

## Global Constraints

- **Every new context_store key needs a DB round-trip test**, not just a file-store test.
- Keep `agent/state.py` (file store) semantics intact — the fix is in `DbProjectStateStore` + a shared key registry.
- POST-only; new routes get auth + ownership.
- Comment the decision behind each change.

---

## Part A — Persistence (the prerequisite, real code)

### Task A1: Migration — `coaching` column + `last_nudge_at`

**Files:**
- Create: an Alembic revision under `api/migrations/versions/`
- Modify: `api/app/models.py` (`ContextStore.coaching`, `Project.last_nudge_at`)

- [ ] **Step 1: Add the columns to the models**

`ContextStore`: `coaching: Mapped[dict | None] = mapped_column(JSONB)` — holds the non-module,
project-scoped coaching/memory keys as one blob. `Project`: `last_nudge_at: Mapped[datetime | None]
= mapped_column(DateTime(timezone=True))` (F11).

- [ ] **Step 2: Generate + edit the migration**

Run: `cd api && ./run.sh alembic revision -m "coaching blob + last_nudge_at"` and fill
`upgrade()`/`downgrade()` to add/drop `context_store.coaching` (JSONB, nullable) and
`projects.last_nudge_at` (timestamptz, nullable).

- [ ] **Step 3: Apply + verify**

Run: `cd api && ./run.sh alembic upgrade head` → no error; `alembic downgrade -1` then `upgrade head`
round-trips cleanly.

- [ ] **Step 4: Commit**

```bash
git add api/app/models.py api/migrations/versions
git commit -m "feat(store): coaching JSONB column + projects.last_nudge_at

Home for project-scoped coaching/memory keys the module columns can't hold.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task A2: Round-trip coaching keys in `DbProjectStateStore`

**Files:**
- Modify: `agent/state.py` (add `COACHING_KEYS`), `api/app/agent_state.py` (`load`/`_save`)
- Test: `api/tests/test_agent_state_coaching.py`

**Interfaces:**
- Produces: `COACHING_KEYS: set[str]` in `agent/state.py`; `DbProjectStateStore.load()` lifts the
  `coaching` column's keys into `contextStore`, `_save()` writes any `COACHING_KEYS` present in
  `contextStore` back into the `coaching` column.

- [ ] **Step 1: Write the failing test (DB round-trip, not file store)**

```python
# api/tests/test_agent_state_coaching.py
from app.agent_state import DbProjectStateStore
from app.db import get_engine


def test_coaching_keys_round_trip_in_db(project_id):   # reuse test_agent_state.py's project_id fixture
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    st = store.load()
    st["contextStore"]["roadmap_tasks"] = [{"id": "b1", "status": "open", "title": "x"}]
    st["contextStore"]["institution_profile"] = {"citation_style": "apa7"}
    store._save(st)
    reloaded = store.load()   # fresh read from DB
    assert reloaded["contextStore"]["roadmap_tasks"][0]["id"] == "b1"
    assert reloaded["contextStore"]["institution_profile"]["citation_style"] == "apa7"
    # module ownership still works and is unaffected
    assert "m1_topic" not in reloaded["contextStore"]
```

> Use the repo's existing DB test fixtures. NOTE: the `project_id` fixture currently lives
> module-local in `api/tests/test_agent_state.py:18` — **move it to `api/tests/conftest.py`** so the
> new `test_agent_state_coaching.py` file can see it (else it's a fixture-not-found error).

- [ ] **Step 2: Run to verify it fails** → FAIL (coaching keys dropped).

- [ ] **Step 3: Implement**

In `agent/state.py`:
```python
# Project-scoped coaching/memory keys that live OUTSIDE the module slice map.
# Persisted by DbProjectStateStore in the `coaching` JSONB column (see
# project_db_store_persistence_gap memory). Written via dedicated store paths,
# never commit_slice.
# NOTE: field-it results are NOT here — F7 writes them into the m4_analysis
# module column (where F8 reads), so they persist via normal ownership.
COACHING_KEYS = {"roadmap_tasks", "advisor_feedback", "institution_profile",
                 "thesis_timeline"}
```

In `api/app/agent_state.py` `load()`, after building `flat`, lift the coaching blob:
```python
        if cs and getattr(cs, "coaching", None):
            for k, v in cs.coaching.items():
                if k in COACHING_KEYS:
                    flat[k] = v
```
In `_save()`, MERGE coaching keys present in `flat` OVER the existing column (never rebuild —
a rebuild would wipe keys not in the current write, exactly like the per-module columns already
merge at `agent_state.py:121`):
```python
            existing_coaching = dict(getattr(existing, "coaching", None) or {}) if existing else {}
            for k in COACHING_KEYS:
                if k in flat:
                    existing_coaching[k] = flat[k]
            if existing_coaching:
                values["coaching"] = existing_coaching
```
`**values` already covers both the insert and update branches (`agent_state.py:135-142`).

**Also fix `exists()`** (`agent_state.py:46-50`): it must test MODULE keys only, else seeding an
`institution_default` (F4) makes every fresh project report `exists=True` and onboarding paths
treat it as "started":
```python
    def exists(self) -> bool:
        state = self.load()
        module_keys = set(state["contextStore"]) - COACHING_KEYS
        return bool(module_keys) or any(s != "locked" for s in state["status"].values())
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/state.py api/app/agent_state.py api/tests/test_agent_state_coaching.py
git commit -m "fix(store): round-trip coaching keys in DbProjectStateStore

roadmap_tasks/advisor_feedback/institution_profile/thesis_timeline persist in
the coaching column instead of being silently dropped in prod. DB round-trip
test proves it (file-store tests couldn't).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task A3: Typed read API for consumers (fixes F3↔F4)

**Files:**
- Modify: `agent/state.py` (`ProjectStateStore` getters — inherited by Db store)
- Test: `api/tests/test_agent_state_coaching.py`

**Interfaces:**
- Produces on `ProjectStateStore`: `get_institution_profile() -> dict`, `get_advisor_feedback() -> list`,
  `get_roadmap_tasks() -> list`, `get_thesis_timeline() -> dict`. Each reads the (now round-tripped)
  `contextStore` key with a safe default. **F3's `review_thesis` MUST use these** instead of
  `getattr(store, "institution_profile", …)` / `load_full_context_store()`.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_agent_state_coaching.py
def test_read_api_returns_persisted_coaching(project_id):
    store = DbProjectStateStore(get_engine(), project_id, "/tmp/ws")
    st = store.load(); st["contextStore"]["advisor_feedback"] = [{"id": "1", "status": "open"}]
    store._save(st)
    assert store.get_advisor_feedback()[0]["id"] == "1"
    assert store.get_institution_profile() == {}
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement the getters**

```python
    # in ProjectStateStore (agent/state.py)
    def _cs(self) -> dict:
        return self.load().get("contextStore") or {}
    def get_institution_profile(self) -> dict:
        return self._cs().get("institution_profile") or {}
    def get_advisor_feedback(self) -> list:
        return self._cs().get("advisor_feedback") or []
    def get_roadmap_tasks(self) -> list:
        return self._cs().get("roadmap_tasks") or []
    def get_thesis_timeline(self) -> dict:
        return self._cs().get("thesis_timeline") or {}
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/state.py api/tests/test_agent_state_coaching.py
git commit -m "feat(store): typed read API for coaching keys (fixes F3<-F4)

get_institution_profile/get_advisor_feedback/... so F3's review_thesis reads
real persisted data instead of an unset attribute / module-only view.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Part B — Cross-cutting corrections to F1–F11 (apply when building each)

These amend the named plans. Apply the edit before/within the cited task.

- **[F3 Task 5] Use the read API.** `review_thesis` must call `store.get_institution_profile()` and
  `store.get_advisor_feedback()` (Part A3), NOT `getattr(store, "institution_profile", None)` /
  `load_full_context_store().get("advisor_feedback")`. Add an integration test: write a directive
  via F4's path → `review_thesis` returns a non-empty advisor dimension.
- **[F2 Task 6, F7 Tasks 3–4] Add auth + ownership.** `POST /projects/{id}/roadmap`, `/field-it`,
  `/field-it/results` must take `current_user` + a project-ownership check (match `credit.py`/`jobs.py`).
  `/field-it/results` especially — today it's an anonymous write into M4. Put the token/params in
  the body per CLAUDE.md; add a 401/403 test.
- **[F1 Task 6] Scope the partner gate.** The partner caller must NOT hard-fail on missing M1
  research-questions / M2 sources (F1's own budgeted scout can legitimately return `[]`). Pass
  `assess_export_readiness(store, chapters)` a partner-scoped subset (M4/M3 only) OR mark M1-RQ/M2
  soft for that caller. Regression test: M4-only store + empty scout ⇒ report still generated (no
  new headless gate — the program invariant).
- **[F3 Task 0 — NEW] Package `quality/`.** Add `quality/pyproject.toml` + editable install (or place
  the package where the existing `__editable__*.pth` finder maps it) so `from quality.rubric import …`
  resolves. Without this every F3/F9 test is fail→fail. Do this before F3 Task 1.
- **[F7/F8/F11 store shape] Canonicalize.** The agent `contextStore` is FLAT; the nested
  `m3_design.*` shape only exists in `load_full_context_store()`. Decide per consumer: (a) `preflight_check`
  / `build_timeline` read the flat keys (`methodology`, and a NEW owned key for the sample target), OR
  (b) read via `load_full_context_store()`. Add `sample_plan` (or `sample_target_n`), `cmb_plan`,
  `missing_data_plan` to `SLICE_OWNERSHIP["M3"]` so `commit_slice` can write them, AND persist F7's
  `sampling_plan` output (it currently returns JSON to the model and saves nothing). Strengthen F11's
  test so the method actually reaches `build_timeline` (not the default).
- **[F8 Task 3, F6 Task 1, F7 Task 1] Register tools + close over store.** `preflight_check` must be
  wrapped as a `@tool` (or invoked by a tool) and registered; every "register in the tool list" task
  must list `agent/runtime.py` in its Files. `generate_committee_questions` must close over `store`
  (`load_full_context_store()`), not take `context_store` as a model-supplied arg.
- **[F4 Task 4] Name the distill trigger.** Call `distill_advisor_themes` from `mark_feedback_addressed`
  when all directives are addressed; name the exact project-create site for `institution_default` seeding.
- **[F5] Emit-layer FIRST + fix event defs.** Land F5 Task 1 (`emit()`) before F2/F4 so they ship
  instrumented. Add the `citation_rejected` emit to F3's citation dimension (or cut the insight). Emit
  `next_action_surfaced` only on change, not every poll.

---

## Part C — Per-plan errata (test/signature bug fixes)

| Plan · Task | Defect | Fix |
|---|---|---|
| F11 Task 2 | `timeline_status` excludes the expected milestone ⇒ its own test can't pass | count `act_i..exp_i` **inclusive** (or derive weeks from dates); give the test a full milestone list |
| F1 Task 3 | test patches `m5.run_export` but `compose_export` bound it at import ⇒ real export runs | patch `ce.run_export`, or call `m5_writing.run_export` via the module |
| F10 Task 2 | `_openrouter` needs `OPENROUTER_API_KEY`; test omits it | `monkeypatch.setenv("OPENROUTER_API_KEY", "test")` |
| F2 Task 5 | new `[NEXT]` line breaks existing exact-match header test; sibling file name clash | update `test_runtime_state_header.py`; put new cases there, don't create `test_runtime_header.py` |
| F1 Task 4 / F3 Task 5 / F5 Task 3 | hidden live-LLM (`_infer_model`/`_get_llm`) + autouse Postgres in "unit" tests | stub the LLM; relocate pure-function tests to `agent/tests/`-style suites (no testcontainer) |
| F2 Task 7 | uses `jest`; repo is **vitest**; raw unauthed `fetch` | `vi.fn()`; shared authed POST helper |
| F7 Task 3 | Google-Form fallback passes `list[str]` to `make_google_form_script` (wants `list[dict]`) + bogus `_reserved` import | pass `[{"text":…,"type":"paragraph"}]`; delete the placeholder import |
| F6 Task 1 | `generate_committee_questions` takes model-supplied `context_store` | close over `store` (see Part B) |
| F9 Task 2 | canonical `score_probe` marker branch is deliberately broken | ship `return f"[{val}]" in text`; `{{cite}}` via a `regex` probe |
| F11 Task 4 | `from app.db import SessionLocal` (doesn't exist); dead `_PHASE_WEEKS`; migration only a note | use the real session factory (`get_session_factory()`); remove `_PHASE_WEEKS`; the migration is now A1 |
| F10 Task 1 | `_native` adds `temperature` to `ChatAnthropic` (current code doesn't) | match current construction; keep defaults byte-for-byte |
| Master vs F2/F3 | fictional deps: F2 "depends on F1"; F3 "calls the chapter-scoped gate" (it calls it unscoped) | delete F2's F1 dep; downgrade F3→F1 to "back-compat only" |

---

## Final verification (Part A)

- [ ] `cd api && ./run.sh alembic upgrade head` clean; `downgrade -1`/`upgrade head` round-trips.
- [ ] `cd api && ./run.sh pytest tests/test_agent_state_coaching.py -q` → PASS (DB round-trip proven).
- [ ] Grep confirms F2/F4/F11 coaching write paths target keys in `COACHING_KEYS` (roadmap_tasks,
  advisor_feedback, institution_profile, thesis_timeline); F7 field-it results go to the
  `m4_analysis` column (normal ownership), NOT the coaching blob.
- [ ] `exists()` returns False for a fresh project even after an `institution_default` seed.

## Notes

- Part A is the true prerequisite; Parts B/C are applied while building the respective features.
- After A2/A3, the F2/F4/F7/F11 store-path tasks should ADD a DB round-trip test (not only file-store).
- This closes the audit's two CRITICAL engineering findings + all HIGH/MED plan defects.
