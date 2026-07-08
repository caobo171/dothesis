# Field-It Survey Pipeline Implementation Plan (F7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vet the instrument (Questionnaire Doctor), compute a defensible sampling plan, hand off collection to fillform/survify, and ingest structured responses + quality metadata back into M4.

**Architecture:** Two pure/deterministic tools (`audit_instrument`, `sampling_plan`) + a POST handoff route + a POST results-ingestion route, all built on the existing `make_google_form_script` + M3 `instrument` slice. Provider selection defaults by language/region; Google Form stays the free fallback.

**Tech Stack:** Python, LangChain `@tool`, FastAPI (POST-only), pytest via `./run.sh`.

## Global Constraints

- **POST-only routes** (project convention).
- **Advisory, never blocks fielding** — audit/sampling surface findings; the student can still field.
- **Best-effort handoff** — a provider failure returns the existing Google Form fallback so the student is never stuck.
- **Shares the power/sample helper with F8** — one definition of the 10×/inverse-sqrt rule.
- **Cross-sell fillform (VN) / survify (intl)** per `project_sibling_products` memory.
- **Comment the decision behind each change.**

---

### Task 1: Questionnaire Doctor — `audit_instrument` + content + rubric criterion

**Files:**
- Create: `agent/tools/instrument.py`, `skills/dothesis-m3-design/references/questionnaire-quality.md`
- Modify: `quality/rubric.py` (add `instrument_quality` criterion) — F3
- Test: `api/tests/test_audit_instrument.py`

**Interfaces:**
- Produces: `audit_instrument(instrument: dict, hypotheses: list, constructs: list) -> str` (json findings + scale-provenance skeleton).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_audit_instrument.py
import json
from agent.tools.instrument import audit_instrument


def test_double_barreled_item_flagged():
    inst = {"items": [{"id": "q1", "text": "The app is fast and reliable", "construct": "PE"}]}
    out = json.loads(audit_instrument.func(instrument=inst, hypotheses=[], constructs=["PE"]))
    assert any("double" in f["issue"].lower() for f in out["findings"])


def test_missing_reverse_coded_per_construct_flagged():
    inst = {"items": [{"id": "q1", "text": "I like it", "construct": "ATT", "reverse_coded": False}]}
    out = json.loads(audit_instrument.func(instrument=inst, hypotheses=[], constructs=["ATT"]))
    assert any("reverse" in f["issue"].lower() for f in out["findings"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_audit_instrument.py -q` → FAIL (no module).

- [ ] **Step 3: Implement `audit_instrument` + content**

`questionnaire-quality.md`: the item-level checklist (double-barreled, leading, back-translation
for adapted scales, anchor consistency, attention checks, reverse-coded coverage) + the
scale-provenance table template.

```python
# agent/tools/instrument.py
"""Questionnaire Doctor — deterministic instrument lint before fielding. Advisory: returns
findings + a scale-provenance skeleton; never blocks. Guidance, not psychometric computation."""
from __future__ import annotations
import json
from langchain_core.tools import tool

_CONJ = (" and ", " or ", " và ", " hoặc ")


@tool
def audit_instrument(instrument: dict, hypotheses: list, constructs: list) -> str:
    """Lint a questionnaire before fielding: double-barreled/leading items, reverse-coded
    coverage per construct, attention checks, and a scale-provenance skeleton to fill."""
    items = (instrument or {}).get("items") or []
    findings = []
    for it in items:
        text = (it.get("text") or "").lower()
        if any(c in text for c in _CONJ):
            findings.append({"issue": f"Item {it.get('id')} may be double-barreled "
                             f"(joins two ideas): '{it.get('text')}'",
                             "fix": "Split into two items.", "severity": "soft"})
    by_construct: dict = {}
    for it in items:
        by_construct.setdefault(it.get("construct"), []).append(it)
    for c in (constructs or []):
        group = by_construct.get(c, [])
        if group and not any(i.get("reverse_coded") for i in group):
            findings.append({"issue": f"Construct '{c}' has no reverse-coded item.",
                             "fix": "Add one reverse-coded item to catch careless responding.",
                             "severity": "soft"})
    if not any(it.get("attention_check") for it in items):
        findings.append({"issue": "No attention-check item.",
                         "fix": "Add at least one attention check.", "severity": "soft"})
    provenance = [{"construct": c, "source": "", "adapted_from": "", "back_translated": False}
                  for c in (constructs or [])]
    return json.dumps({"findings": findings, "scale_provenance": provenance}, ensure_ascii=False)
```

Register the tool (match the tool-list wiring); add an `instrument_quality` soft criterion to
`quality/rubric.py` reading `audit_instrument` findings.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_audit_instrument.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/instrument.py skills/dothesis-m3-design/references/questionnaire-quality.md quality/rubric.py api/tests/test_audit_instrument.py
git commit -m "feat(m3): Questionnaire Doctor — audit_instrument + provenance table

Deterministic instrument lint before fielding (double-barreled, reverse-coded
coverage, attention checks) + rubric criterion. Protects everything downstream.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `sampling_plan` (shared power helper)

**Files:**
- Create: `agent/sampling.py` (the shared power helper) + `sampling_plan` in `agent/tools/instrument.py`
- Modify: `agent/preflight.py` (F8) to import the shared helper (if F8 landed)
- Test: `api/tests/test_sampling_plan.py`

**Interfaces:**
- Produces: `target_sample_n(method: str, n_paths: int, n_indicators: int) -> tuple[int, str]` (pure), and `sampling_plan(context_store) -> str` (json plan).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sampling_plan.py
import json
from agent.sampling import target_sample_n
from agent.tools.instrument import sampling_plan


def test_pls_10x_rule():
    n, rule = target_sample_n("pls-sem", n_paths=5, n_indicators=6)
    assert n >= 60 and "10" in rule  # 10x the largest of paths-into-a-construct / arrows


def test_cb_sem_minimum_applied():
    n, _ = target_sample_n("cb-sem", n_paths=4, n_indicators=20)
    assert n >= 200


def test_sampling_plan_shape():
    cs = {"m3_design": {"methodology": "PLS-SEM", "conceptual_model": {"paths": [1, 2, 3]},
                        "instrument": {"items": [{}, {}, {}]}}}
    plan = json.loads(sampling_plan.func(context_store=cs))
    assert plan["target_n"] and plan["timeline_weeks"] and plan["method_rule"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_sampling_plan.py -q` → FAIL.

- [ ] **Step 3: Implement**

```python
# agent/sampling.py
"""Shared sample-size power logic (used by F7 sampling_plan + F8 preflight). Guidance rules,
not a power-analysis engine."""
from __future__ import annotations


def target_sample_n(method: str, n_paths: int, n_indicators: int) -> tuple[int, str]:
    m = (method or "").lower()
    if "cb-sem" in m or "amos" in m:
        return max(200, 10 * n_indicators), "CB-SEM: ≥200 and ≥10× indicators (Kline)."
    if "pls" in m:
        return max(60, 10 * max(1, n_paths)), "PLS-SEM: 10× the largest number of arrows into a construct (Hair et al.)."
    return max(50, 15 * max(1, n_paths)), "Regression: ≥15 cases per predictor."
```

```python
# in agent/tools/instrument.py
from agent.sampling import target_sample_n  # noqa: E402


@tool
def sampling_plan(context_store: dict) -> str:
    """Compute a defensible target sample size + collection timeline from the study's method
    and model size."""
    m3 = context_store.get("m3_design") or {}
    method = m3.get("methodology") or "regression"
    n_paths = len((m3.get("conceptual_model") or {}).get("paths") or [])
    n_ind = len((m3.get("instrument") or {}).get("items") or [])
    n, rule = target_sample_n(method, n_paths, n_ind)
    return json.dumps({"target_n": n, "method_rule": rule,
                       "screening": "Add a screening question to exclude ineligible respondents.",
                       "timeline_weeks": 3 if n <= 250 else 4,
                       "rationale": f"{rule} With {n_paths} structural paths and {n_ind} items."},
                      ensure_ascii=False)
```

If F8 has landed, refactor `agent/preflight.py`'s sample check to call `target_sample_n`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_sampling_plan.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/sampling.py agent/tools/instrument.py api/tests/test_sampling_plan.py
git commit -m "feat(m4): sampling_plan + shared power helper

Defensible target n (10x / inverse rules) + timeline; one helper shared with the
methods pre-flight so the sample-size rule is defined once.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Field-It handoff route (+ Google Form fallback)

**Files:**
- Create: `api/app/routers/field_it.py`
- Modify: `api/app/main.py` (mount)
- Modify: `api/app/settings.py` (fillform/survify API base + token)
- Test: `api/tests/test_field_it.py`

**Interfaces:**
- Produces: `POST /api/v1/projects/{id}/field-it` → `{provider, collection_id, survey_url}` or a `fallback_google_script`. Provider defaults from `language` (vi → fillform, else survify).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_field_it.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import field_it as fi


def _client(monkeypatch, handoff):
    monkeypatch.setattr(fi, "_provider_create_survey", handoff)
    app = FastAPI(); app.include_router(fi.router, prefix="/api/v1")
    return TestClient(app)


def test_vi_defaults_to_fillform(monkeypatch):
    seen = {}
    def ok(provider, payload):
        seen["provider"] = provider
        return {"collection_id": "c1", "survey_url": "https://fillform.info/s/c1"}
    c = _client(monkeypatch, ok)
    r = c.post("/api/v1/projects/abc/field-it",
               json={"instrument": {"items": []}, "sampling_plan": {"target_n": 200}, "language": "vi"})
    assert r.status_code == 200 and seen["provider"] == "fillform"
    assert r.json()["survey_url"].startswith("https://fillform.info")


def test_provider_failure_returns_google_fallback(monkeypatch):
    def boom(provider, payload): raise RuntimeError("provider down")
    c = _client(monkeypatch, boom)
    r = c.post("/api/v1/projects/abc/field-it",
               json={"instrument": {"items": [{"text": "Q1"}]}, "sampling_plan": {}, "language": "en"})
    assert r.status_code == 200 and r.json()["fallback_google_script"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_field_it.py -q` → FAIL.

- [ ] **Step 3: Implement the route**

```python
# api/app/routers/field_it.py
"""Field-It: hand a vetted instrument off to the team's own survey rails (fillform VN /
survify intl) with a sampling plan; returns a collection link. Best-effort — a provider
failure falls back to the existing Google Form script so the student is never stuck. POST-only."""
from __future__ import annotations
import logging
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["field-it"])


class FieldItIn(BaseModel):
    instrument: dict
    sampling_plan: dict = {}
    language: str = "en"


def _provider_for(language: str) -> str:
    return "fillform" if str(language).lower().startswith("vi") else "survify"


def _provider_create_survey(provider: str, payload: dict) -> dict:
    """Call the provider API; isolated so tests stub it. Wire to fillform/survify REST."""
    raise NotImplementedError  # implemented against the real provider API


@router.post("/projects/{project_id}/field-it")
async def create_field_it(project_id: str, body: FieldItIn):
    provider = _provider_for(body.language)
    payload = {"project_id": project_id, "items": body.instrument.get("items", []),
               "target_n": body.sampling_plan.get("target_n")}
    try:
        res = _provider_create_survey(provider, payload)
        return {"provider": provider, "collection_id": res["collection_id"],
                "survey_url": res["survey_url"]}
    except Exception:
        logger.exception("field-it: provider handoff failed; returning Google Form fallback")
        from ..._reserved import _  # placeholder; see note
        from agent.tools.forms import make_google_form_script  # noqa: PLC0415
        script = make_google_form_script.func(
            title="Thesis Survey",
            questions=[i.get("text", "") for i in body.instrument.get("items", [])])
        return {"provider": "google_form_fallback", "fallback_google_script": script}
```

> **Note for implementer:** delete the bogus `from ..._reserved import _` line — it's only there
> to mark that the real import block is `make_google_form_script`. Wire `_provider_create_survey`
> to the fillform/survify REST APIs using `settings.fillform_api_*` / `settings.survify_api_*`
> (add those to `settings.py`). Mount the router in `main.py` with the `/api/v1` prefix.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_field_it.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/field_it.py api/app/main.py api/app/settings.py api/tests/test_field_it.py
git commit -m "feat(field-it): survey handoff to fillform/survify (+ Google Form fallback)

The commercial flywheel — vetted instrument -> the team's own survey rails with a
sampling plan; best-effort with a Google Form fallback. POST-only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Results ingestion → M4 (with quality flags)

**Files:**
- Modify: `api/app/routers/field_it.py` (add `POST /field-it/results`)
- Test: `api/tests/test_field_it.py`

**Interfaces:**
- Produces: `POST /api/v1/projects/{id}/field-it/results` — ingests `{collection_id, responses[], quality[]}` into `m4_analysis` (raw dataset + quality flags for F8's Output Sanity Layer). Rejects malformed payloads (4xx).

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_field_it.py
def test_results_ingest_writes_m4(monkeypatch):
    written = {}
    monkeypatch.setattr(fi, "_store_for", lambda pid: type("S", (), {
        "set_field_it_results": lambda self, data: written.update(data)})())
    app = FastAPI(); app.include_router(fi.router, prefix="/api/v1")
    c = TestClient(app)
    r = c.post("/api/v1/projects/abc/field-it/results",
               json={"collection_id": "c1", "responses": [{"q1": 5}],
                     "quality": [{"straight_lined": False, "duration_s": 220}]})
    assert r.status_code == 200 and written["collection_id"] == "c1"


def test_results_bad_payload_is_4xx():
    app = FastAPI(); app.include_router(fi.router, prefix="/api/v1")
    c = TestClient(app)
    assert c.post("/api/v1/projects/abc/field-it/results", json={"nope": 1}).status_code == 422
```

- [ ] **Step 2: Run to verify it fails** → FAIL (no route).

- [ ] **Step 3: Implement the ingestion route**

Add a `FieldItResultsIn(BaseModel)` (`collection_id: str`, `responses: list[dict]`,
`quality: list[dict] = []`) and a `POST /projects/{project_id}/field-it/results` handler that
loads the project store (`_store_for`, wired like the roadmap endpoint's) and calls a
`set_field_it_results` store method that writes the raw responses + quality flags under
`m4_analysis` (via the dedicated per-project write path, mirroring `set_institution_profile`).
Pydantic validation makes a missing `collection_id`/`responses` a 422.

> **Note for implementer:** add `set_field_it_results(data)` to `ProjectStateStore` next to
> `set_institution_profile` (F4 pattern) — writes only the `m4_analysis` raw-dataset + quality
> keys, no focus/status change. Reuse the `_store_for` factory from the roadmap endpoint.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/field_it.py agent/state.py api/tests/test_field_it.py
git commit -m "feat(field-it): results ingestion into M4 with quality flags

Structured responses + quality metadata (straight-lining, duration) land in M4
for the Output Sanity Layer to screen. POST-only; validated.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_audit_instrument.py tests/test_sampling_plan.py tests/test_field_it.py -q` → all PASS.
- [ ] Fallback path confirmed: a stubbed provider failure returns a Google Form script, not a 500.
- [ ] Headless untouched: `cd api && ./run.sh pytest tests/test_partner_report.py -q` green.

## Notes

- **Shares `agent/sampling.py` with F8** — land whichever first; the second imports it.
- **F3** gains the `instrument_quality` criterion; **F8** Output Sanity consumes the returned
  quality flags.
- `_provider_create_survey` needs the real fillform/survify API contract; until then it's stubbed
  and the fallback path ships.
