# Quantitative Correctness Content Pack Implementation Plan (F8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode an advisor's quantitative-correctness eye as content + two thin deterministic checks — decision matrix, methods pre-flight, two-register explanations, output sanity — no stats engine.

**Architecture:** Mostly skill-content assets (`references/*.md`) + a root-skill style rule + two pure/deterministic functions (`preflight_check`, `check_thresholds`). Feeds the F3 rubric a `preflight` criterion and the F2 coaching surface an advisory line.

**Tech Stack:** Markdown skill content; Python (pure functions + one whitelisted stats-tool op); pytest via `./run.sh`.

## Global Constraints

- **No computation of new statistics** — `check_thresholds` classifies values the student already pasted; never derives them.
- **Advisory, not blocking** — Methods Pre-Flight surfaces missing items, never refuses M4.
- **Keep skill content ↔ code in sync** (the slice map / gate rationale).
- **Depends on F2** (coaching surface) and **F3** (rubric) — reference them but don't reimplement.
- **Comment the decision behind each change.**

---

### Task 1: Design→Test Decision Matrix (content)

**Files:**
- Create: `skills/dothesis-m3-design/references/design-test-matrix.md`
- Modify: `skills/dothesis-m3-design/SKILL.md` (add a "consult the matrix" rule)
- Test: `api/tests/test_skill_content.py` (grep-style assertions)

- [ ] **Step 1: Write the content asset**

`design-test-matrix.md`: a decision tree mapping (model type · sample size · construct nature
[reflective/formative] · data normality) → recommended method (PLS-SEM / CB-SEM / multiple
regression / moderated regression) with the citable rule (Hair et al. thresholds) and 2–3
worked justifications (e.g. "n=120, formative constructs, prediction-focused ⇒ PLS-SEM because…").

- [ ] **Step 2: Add the M3 skill rule**

In `skills/dothesis-m3-design/SKILL.md`, add: "Before endorsing any analysis method, consult
`references/design-test-matrix.md` and state the rule that applies + its citation. Never approve
CB-SEM below its sample minimum or a reflective/formative mismatch."

- [ ] **Step 3: Write + run the content test**

```python
# api/tests/test_skill_content.py
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def test_design_test_matrix_exists_and_referenced():
    ref = ROOT / "skills/dothesis-m3-design/references/design-test-matrix.md"
    assert ref.exists() and "PLS-SEM" in ref.read_text() and "CB-SEM" in ref.read_text()
    skill = (ROOT / "skills/dothesis-m3-design/SKILL.md").read_text()
    assert "design-test-matrix" in skill
```

Run: `cd api && ./run.sh pytest tests/test_skill_content.py -k design_test -q` → PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/dothesis-m3-design/ api/tests/test_skill_content.py
git commit -m "feat(m3): design-test decision matrix content + consult rule

Encodes the method-choice logic (PLS/CB-SEM/regression) so the agent stops the
#1 novice error — wrong test for the design — with a citable justification.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Two-Register Explanations (root-skill rule)

**Files:**
- Modify: `skills/dothesis/SKILL.md`
- Test: `api/tests/test_skill_content.py`

- [ ] **Step 1: Add the style rule**

In the root `skills/dothesis/SKILL.md`, add a "Two-register explanations" rule: whenever
introducing a statistical concept, give (1) a plain-language Vietnamese analogy the student
understands, then (2) the formal academic sentence they can paste into the thesis. Include one
worked example (e.g. Cronbach's α).

- [ ] **Step 2: Test**

```python
# add to api/tests/test_skill_content.py
def test_two_register_rule_present():
    skill = (ROOT / "skills/dothesis/SKILL.md").read_text().lower()
    assert "two-register" in skill or "two register" in skill
```

Run: `cd api && ./run.sh pytest tests/test_skill_content.py -k two_register -q` → PASS.

- [ ] **Step 3: Commit**

```bash
git add skills/dothesis/SKILL.md api/tests/test_skill_content.py
git commit -m "feat(skill): two-register explanation rule

Every stat concept: plain-language VN analogy + the formal thesis sentence.
Differentiator for the stats-anxious student.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Methods Pre-Flight check + surfacing + rubric criterion

**Files:**
- Create: `agent/preflight.py`
- Modify: `skills/dothesis-m4-analysis/SKILL.md` (run pre-flight before analysis)
- Modify: `quality/rubric.py` (add `preflight` criterion) — F3 must exist
- Test: `api/tests/test_preflight.py`

**Interfaces:**
- Produces: `preflight_check(context_store: dict) -> list[str]` (pure; empty = ready).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_preflight.py
from agent.preflight import preflight_check


def test_flags_missing_sample_and_reverse_coded():
    cs = {"m3_design": {"methodology": "PLS-SEM", "instrument": {"items": []}}}
    missing = preflight_check(cs)
    assert any("sample" in m.lower() for m in missing)


def test_complete_m3_is_ready():
    cs = {"m3_design": {"methodology": "PLS-SEM",
                        "instrument": {"items": [{"reverse_coded": True}]},
                        "sample_plan": {"target_n": 200}, "cmb_plan": "Harman",
                        "missing_data_plan": "listwise"}}
    assert preflight_check(cs) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_preflight.py -q` → FAIL (no module).

- [ ] **Step 3: Implement `preflight_check`**

```python
# agent/preflight.py
"""Advisory M3->M4 readiness check — the 'before you run SmartPLS' audit. Pure, like
assess_export_readiness. Returns human-readable missing items (empty = ready). Never blocks."""
from __future__ import annotations


def preflight_check(context_store: dict) -> list[str]:
    m3 = context_store.get("m3_design") or {}
    inst = m3.get("instrument") or {}
    items = inst.get("items") or []
    missing: list[str] = []
    if not m3.get("methodology"):
        missing.append("M3 — analysis method not chosen (consult the design-test matrix).")
    if not items:
        missing.append("M3 — no questionnaire instrument yet.")
    if not (m3.get("sample_plan") or {}).get("target_n"):
        missing.append("Sample size not planned (10× rule / inverse-square-root).")
    if items and not any(i.get("reverse_coded") for i in items):
        missing.append("No reverse-coded items flagged — check for careless responding.")
    if not m3.get("cmb_plan"):
        missing.append("No common-method-bias plan (e.g. Harman / marker variable).")
    if not m3.get("missing_data_plan"):
        missing.append("No missing-data handling plan.")
    return missing
```

Add to `skills/dothesis-m4-analysis/SKILL.md`: "At the start of the analysis pipeline, run the
methods pre-flight; if items are missing, surface them and offer to fix before running." Add a
`preflight` soft criterion to `quality/rubric.py` (`score = 1 - 0.15*len(preflight_check(cs))`,
findings from each item, weight 0.10).

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_preflight.py tests/test_quality_rubric.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/preflight.py skills/dothesis-m4-analysis/SKILL.md quality/rubric.py api/tests/test_preflight.py
git commit -m "feat(m4): methods pre-flight check + rubric criterion

Advisory M3->M4 audit (sample size, reverse-coded, CMB/missing-data plans) so
fatal flaws are caught while cheap. Feeds the quality rubric.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Output Sanity Layer — content + `check_thresholds`

**Files:**
- Create: `skills/dothesis-m4-analysis/references/output-interpretation.md`
- Modify: `agent/tools/stats.py` (add `check_thresholds` op/tool)
- Test: `api/tests/test_check_thresholds.py`

**Interfaces:**
- Produces: `check_thresholds(table_kind: str, rows: list[dict]) -> str` (json findings). Classifies pasted values against thresholds + flags suspiciously-perfect patterns. No new computation.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_check_thresholds.py
import json
from agent.tools.stats import check_thresholds  # or via the stats tool factory — match stats.py


def test_htmt_above_085_flagged():
    out = json.loads(check_thresholds.func(table_kind="htmt",
                     rows=[{"pair": "BI-ATT", "value": 0.91}]))
    assert any("discriminant" in f["issue"].lower() for f in out["findings"])


def test_suspiciously_perfect_loadings_flagged():
    out = json.loads(check_thresholds.func(table_kind="loadings",
                     rows=[{"item": f"X{i}", "value": 0.96} for i in range(8)]))
    assert any("suspicious" in f["issue"].lower() or "straight" in f["issue"].lower()
               for f in out["findings"])


def test_good_loadings_no_flags():
    out = json.loads(check_thresholds.func(table_kind="loadings",
                     rows=[{"item": "X1", "value": 0.74}, {"item": "X2", "value": 0.81}]))
    assert out["findings"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_check_thresholds.py -q` → FAIL.

- [ ] **Step 3: Write the content ref + implement the tool**

`output-interpretation.md`: per-table threshold table (loadings ≥0.708, AVE ≥0.5, CR 0.7–0.95,
HTMT <0.85/0.90, VIF <3.3/5, p<.05, R²/f²/Q² bands, CB-SEM fit CFI≥.90 RMSEA≤.08) + the
"suspiciously perfect" heuristics + narration guidance.

Add `check_thresholds` following the whitelisted-op pattern in `agent/tools/stats.py`:

```python
_THRESHOLDS = {
    "loadings": lambda v: None if v >= 0.708 else "below 0.708 — consider removing this item",
    "ave": lambda v: None if v >= 0.5 else "AVE below 0.5 — convergent validity not met",
    "cr": lambda v: None if 0.7 <= v <= 0.95 else "CR outside 0.7–0.95",
    "htmt": lambda v: None if v < 0.85 else "HTMT ≥ 0.85 — discriminant validity may fail",
    "vif": lambda v: None if v < 3.3 else "VIF ≥ 3.3 — possible collinearity",
}


@tool
def check_thresholds(table_kind: str, rows: list[dict]) -> str:
    """Classify a pasted results table (loadings/ave/cr/htmt/vif) against standard
    thresholds and flag both violations AND suspiciously-perfect patterns (all
    loadings > 0.9 ⇒ possible straight-lined data). Does NOT compute new statistics."""
    check = _THRESHOLDS.get(table_kind)
    findings = []
    values = [r.get("value") for r in rows if isinstance(r.get("value"), (int, float))]
    if check:
        for r in rows:
            v = r.get("value")
            msg = check(v) if isinstance(v, (int, float)) else None
            if msg:
                findings.append({"issue": f"{r.get('item') or r.get('pair') or '?'}: {msg}",
                                 "severity": "hard"})
    # Suspiciously perfect: loadings/HTMT patterns that usually mean bad data.
    if table_kind == "loadings" and values and min(values) >= 0.9:
        findings.append({"issue": "All loadings > 0.9 — suspiciously perfect; check for "
                                  "straight-lined data or a wrong matrix.", "severity": "soft"})
    return json.dumps({"table_kind": table_kind, "findings": findings}, ensure_ascii=False)
```

Wire `check_thresholds` into the tool list (match how `run_stats` is registered) and reference
it from the M4 skill.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_check_thresholds.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/dothesis-m4-analysis/references/output-interpretation.md agent/tools/stats.py api/tests/test_check_thresholds.py
git commit -m "feat(m4): output sanity layer — check_thresholds + interpretation ref

Classifies pasted result tables against thresholds and flags suspiciously-
perfect patterns (straight-lined data). No new computation.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_skill_content.py tests/test_preflight.py tests/test_check_thresholds.py tests/test_quality_rubric.py -q` → all PASS.
- [ ] `check_thresholds` computes nothing new: grep the function for arithmetic on values → only comparisons.

## Notes

- **Depends on F3** (`quality/rubric.py`) for Task 3's criterion — do F3 first, or land Task 3's
  rubric edit when F3 lands.
- Content tasks (1, 2) are shippable immediately and highest-leverage; do them first.
