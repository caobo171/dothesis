# Quality Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One rubric scorer that grades a quantitative thesis (method-aware + institution-configurable + advisor-directive-aware), powering both a student readiness grader and a CI regression harness.

**Architecture:** `quality/rubric.py` orchestrates deterministic dimensions (reusing existing validators) + bounded LLM-judge dimensions into a `RubricResult`. A student tool + M5 `review` roadmap step render it; a CI harness runs the same scorer over fixtures. It reads `institution_profile` and `advisor_feedback` (owned by the cross-session-memory spec) with safe empty defaults.

**Tech Stack:** Python 3, LangChain `@tool`, engine LLM (`orchestrator.tools.m5_writing._get_llm`), pytest via `./run.sh` (arm64).

## Global Constraints

- **Read-only.** `score_thesis` never writes project state — it can't corrupt a thesis.
- **Best-effort judges.** Any LLM-judge failure ⇒ neutral dimension score + a "could not evaluate" finding; the overall score still returns. Never crash.
- **Safe defaults for cross-spec reads.** `institution_profile=None` ⇒ generic; `advisor_feedback=None` ⇒ `[]`.
- **Advisory, not blocking.** Existing hard gates (`validate_citations*`, M4 data gate) stay the hard stops.
- **Depends on Spec 1** (chapter-scoped `assess_export_readiness`) and **Spec 2** (roadmap spine, `flag_blocker`). Do those first.
- **Comment the decision behind each change** (project convention).
- Context-store slice keys (from `agent/state.py`): `m1_topic`, `m2_literature`, `m3_design`, `m4_analysis`, `m5_writing`; nested owned keys per `SLICE_OWNERSHIP`.

---

### Task 1: `quality/rubric.py` — result shape + deterministic dimensions

**Files:**
- Create: `quality/__init__.py`, `quality/rubric.py`
- Test: `api/tests/test_quality_rubric.py`

**Interfaces:**
- Consumes: `assess_export_readiness` (Spec 1), `validate_citations_plain` + `_is_stub_prose` (`orchestrator/tools/m5_writing.py:131,1090`).
- Produces:
  - `Finding = {"issue","fix","chapter","severity"}`, `Dimension = {"name","score","weight","findings"}`.
  - `deterministic_dimensions(context_store: dict) -> list[Dimension]` — structure, citation-integrity, stub dimensions.
  - `score_thesis(context_store, *, institution_profile=None, advisor_feedback=None) -> dict` (full `RubricResult`; in this task only deterministic dims + weighted overall).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_quality_rubric.py
from quality.rubric import score_thesis, deterministic_dimensions

_GOOD = {
    "m1_topic": {"research_title": "T", "research_questions": ["Q"]},
    "m2_literature": {"literature_sources": [{"title": "P", "authors": ["Smith"], "year": 2020}]},
    "m3_design": {"methodology": "PLS-SEM", "conceptual_model": {"nodes": []}, "hypotheses": ["H1"]},
    "m4_analysis": {"analysis_results": "AVE=0.62, HTMT ok, R2=.41, p<.05"},
    "m5_writing": {"final_sections": [{"title": "Results", "prose": "Real interpreted results. " * 20}]},
}


def test_structure_dimension_flags_missing_module():
    dims = {d["name"]: d for d in deterministic_dimensions({"m1_topic": {}})}
    assert dims["structure"]["score"] < 1.0
    assert any("M1" in f["issue"] for f in dims["structure"]["findings"])


def test_citation_integrity_flags_uncited():
    cs = {**_GOOD, "m5_writing": {"final_sections": [
        {"title": "Intro", "prose": "As shown (Ghost, 2099) this matters."}]}}
    dims = {d["name"]: d for d in deterministic_dimensions(cs)}
    assert any("Ghost" in f["issue"] for f in dims["citations"]["findings"])


def test_score_thesis_returns_overall_and_shape():
    r = score_thesis(_GOOD)
    assert 0.0 <= r["overall"] <= 1.0
    assert r["method"] and isinstance(r["dimensions"], list)
    assert r["advisor"] == {"total": 0, "addressed": 0, "open": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_quality_rubric.py -q`
Expected: FAIL — `ModuleNotFoundError: quality.rubric`.

- [ ] **Step 3: Implement the deterministic core**

```python
# quality/__init__.py
"""Thesis quality evaluation — one rubric scorer for a student grader + CI harness."""
```

```python
# quality/rubric.py
"""Rubric scorer: deterministic dimensions (reusing existing validators) + bounded
LLM-judge dimensions → a RubricResult. Read-only over a nested context_store, so it
can never corrupt a thesis. institution_profile + advisor_feedback are read with safe
defaults (owned by the cross-session-memory spec)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ALL_CHAPTERS = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


def _sections(context_store: dict) -> list[dict]:
    m5 = context_store.get("m5_writing") or {}
    return m5.get("final_sections") or list((m5.get("chapters") or {}).values()) or []


def _all_prose(context_store: dict) -> str:
    return "\n\n".join((s.get("prose") or "") for s in _sections(context_store))


def deterministic_dimensions(context_store: dict) -> list[dict]:
    from orchestrator.tools.m5_writing import (  # noqa: PLC0415
        assess_export_readiness, validate_citations_plain, _is_stub_prose,
    )

    # 1) Structure — reuse the single completeness gate (Spec 1).
    missing = assess_export_readiness(context_store)
    structure = {
        "name": "structure", "weight": 0.20,
        "score": max(0.0, 1.0 - 0.2 * len(missing)),
        "findings": [{"issue": m, "fix": f"Provide {m}.", "chapter": "-", "severity": "hard"}
                     for m in missing],
    }

    # 2) Citation integrity — uncited (Author, Year) = a source not in the pool.
    pool = (context_store.get("m2_literature") or {}).get("literature_sources") or []
    cite = validate_citations_plain(_all_prose(context_store), pool)
    uncited = cite["uncited_warnings"]
    citations = {
        "name": "citations", "weight": 0.20,
        "score": 1.0 if not uncited else max(0.0, 1.0 - 0.1 * len(uncited)),
        "findings": [{"issue": f"Citation {u} has no matching reference (possible fabrication).",
                      "fix": "Add the source to your references or remove the citation.",
                      "chapter": "-", "severity": "hard"} for u in uncited],
    }

    # 3) Stub prose — placeholder/failure text masquerading as a chapter.
    stub_findings = [
        {"issue": f"Section '{s.get('title')}' is a stub/placeholder, not real content.",
         "fix": "Compose or rewrite this section with real content.",
         "chapter": s.get("title", "-"), "severity": "hard"}
        for s in _sections(context_store) if _is_stub_prose(s.get("prose") or "")
    ]
    stubs = {"name": "no_stubs", "weight": 0.10,
             "score": 1.0 if not stub_findings else 0.0, "findings": stub_findings}

    return [structure, citations, stubs]


def _weighted(dims: list[dict]) -> float:
    total_w = sum(d["weight"] for d in dims) or 1.0
    return round(sum(d["score"] * d["weight"] for d in dims) / total_w, 3)


def score_thesis(context_store: dict, *, institution_profile: dict | None = None,
                 advisor_feedback: list[dict] | None = None) -> dict:
    """Full RubricResult. This task: deterministic dims only (judge + advisor + method
    overlay land in later tasks)."""
    method = _detect_method(context_store)
    dims = deterministic_dimensions(context_store)
    blocking = [f["issue"] for d in dims for f in d["findings"] if f["severity"] == "hard"]
    return {
        "overall": _weighted(dims), "method": method, "dimensions": dims,
        "advisor": {"total": 0, "addressed": 0, "open": []},
        "blocking": blocking,
    }


def _detect_method(context_store: dict) -> str:
    m = ((context_store.get("m3_design") or {}).get("methodology") or "").lower()
    if "pls" in m:
        return "pls-sem"
    if "cb-sem" in m or "amos" in m or "covariance" in m:
        return "cb-sem"
    if "regression" in m or "spss" in m or "anova" in m:
        return "spss"
    return "generic"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_quality_rubric.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add quality/__init__.py quality/rubric.py api/tests/test_quality_rubric.py
git commit -m "feat(quality): rubric scorer deterministic core

Structure/citations/stubs dimensions reuse existing validators; score_thesis
returns the RubricResult shape with a weighted overall. Read-only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Method-keyed criteria + institution overlay

**Files:**
- Modify: `quality/rubric.py`
- Test: `api/tests/test_quality_rubric.py`

**Interfaces:**
- Produces:
  - `METHOD_CRITERIA: dict[str, list[str]]` — the results-reporting checklist per method.
  - `results_validity_dimension(context_store, method) -> dict` — deterministic presence check of the method's required statistics in `analysis_results` text.
  - `apply_institution_overlay(dims, profile) -> list[dict]` — override weights + add hard requirement findings (min_references, citation_style, required_sections). `score_thesis` now folds these in.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_quality_rubric.py
from quality.rubric import results_validity_dimension, apply_institution_overlay, METHOD_CRITERIA


def test_pls_results_dimension_flags_missing_htmt():
    cs = {"m4_analysis": {"analysis_results": "AVE=0.6 CR=0.8 R2=0.4 p<.05"}}  # no HTMT
    d = results_validity_dimension(cs, "pls-sem")
    assert any("htmt" in f["issue"].lower() for f in d["findings"])


def test_spss_uses_different_criteria():
    assert set(METHOD_CRITERIA["spss"]) != set(METHOD_CRITERIA["pls-sem"])


def test_institution_min_references_adds_hard_finding():
    dims = [{"name": "citations", "weight": 0.2, "score": 1.0, "findings": []}]
    cs = {"m2_literature": {"literature_sources": [{"title": "a"}] * 12}}
    out = apply_institution_overlay(dims, {"min_references": 30}, cs)
    assert any("30" in f["issue"] for d in out for f in d["findings"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_quality_rubric.py -k "pls or spss or institution" -q`
Expected: FAIL — no `results_validity_dimension`.

- [ ] **Step 3: Implement method criteria + overlay**

```python
# add to quality/rubric.py
METHOD_CRITERIA: dict[str, list[str]] = {
    "pls-sem": ["cronbach", "composite reliability|cr", "ave", "htmt",
                "path coefficient|β|beta", "r2|r-square|r²", "p value|p-value|p<"],
    "cb-sem":  ["cronbach", "cfa|factor loading", "cfi", "rmsea", "tli|nfi",
                "chi-square|χ2", "path coefficient|β"],
    "spss":    ["cronbach", "kmo|bartlett", "regression|beta|β", "r2|r-square",
                "vif|tolerance", "f statistic|f=", "p value|p<"],
    "generic": ["reliability", "validity", "coefficient", "p value|p<"],
}


def results_validity_dimension(context_store: dict, method: str) -> dict:
    import re  # noqa: PLC0415
    text = ((context_store.get("m4_analysis") or {}).get("analysis_results") or "").lower()
    crits = METHOD_CRITERIA.get(method, METHOD_CRITERIA["generic"])
    findings = []
    for pattern in crits:
        if not re.search(pattern, text):
            label = pattern.split("|")[0]
            findings.append({"issue": f"Results don't report {label} (expected for {method}).",
                             "fix": f"Report and interpret {label} in your Results chapter.",
                             "chapter": "results", "severity": "soft"})
    score = 1.0 - (len(findings) / max(1, len(crits)))
    return {"name": "results_validity", "weight": 0.20, "score": round(score, 3),
            "findings": findings}


def apply_institution_overlay(dims: list[dict], profile: dict | None,
                              context_store: dict) -> list[dict]:
    """Override dimension weights and add hard requirement findings. Pure over dims."""
    if not profile:
        return dims
    out = [dict(d) for d in dims]
    for d in out:
        w = (profile.get("weight_overrides") or {}).get(d["name"])
        if w is not None:
            d["weight"] = w

    min_refs = profile.get("min_references")
    if min_refs:
        n = len((context_store.get("m2_literature") or {}).get("literature_sources") or [])
        if n < min_refs:
            for d in out:
                if d["name"] == "citations":
                    d["findings"] = d["findings"] + [{
                        "issue": f"Only {n} references; your institution requires ≥ {min_refs}.",
                        "fix": f"Add at least {min_refs - n} more sources.",
                        "chapter": "lit_review", "severity": "hard"}]
                    d["score"] = min(d["score"], 0.5)
    return out
```

Wire both into `score_thesis`: append `results_validity_dimension(context_store, method)` to
`dims`, then `dims = apply_institution_overlay(dims, institution_profile, context_store)`
before computing `overall`/`blocking`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_quality_rubric.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add quality/rubric.py api/tests/test_quality_rubric.py
git commit -m "feat(quality): method-aware results criteria + institution overlay

Results dimension checks the method's reporting checklist (PLS/CB-SEM/SPSS);
institution_profile overrides weights and adds hard requirements (min refs).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: LLM-judge dimensions (robust)

**Files:**
- Modify: `quality/rubric.py`
- Test: `api/tests/test_quality_rubric.py`

**Interfaces:**
- Consumes: `orchestrator.tools.m5_writing._get_llm`.
- Produces: `judge_dimension(name, weight, prompt, context_store) -> dict` — one bounded judge call returning `{score, findings}`; best-effort. `score_thesis` appends methodology + writing judge dims.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_quality_rubric.py
import orchestrator.tools.m5_writing as m5
from quality.rubric import judge_dimension


def test_judge_dimension_parses_llm_json(monkeypatch):
    class _Resp:
        content = '{"score": 0.4, "findings": [{"issue": "H1 has no gap", ' \
                  '"fix": "Trace H1 to a gap", "chapter": "methodology", "severity": "soft"}]}'
    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())
    d = judge_dimension("methodology", 0.15, "prompt", {})
    assert d["score"] == 0.4 and d["findings"][0]["issue"].startswith("H1")


def test_judge_dimension_survives_bad_json(monkeypatch):
    class _Resp: content = "not json at all"
    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())
    d = judge_dimension("writing", 0.10, "prompt", {})
    assert 0.0 <= d["score"] <= 1.0
    assert any("could not evaluate" in f["issue"].lower() for f in d["findings"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_quality_rubric.py -k judge -q`
Expected: FAIL — no `judge_dimension`.

- [ ] **Step 3: Implement the judge**

```python
# add to quality/rubric.py
import json as _json


def judge_dimension(name: str, weight: float, prompt: str, context_store: dict) -> dict:
    """One bounded LLM-judge call. Best-effort: any failure ⇒ neutral score + note."""
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415
    try:
        resp = _get_llm().invoke(prompt)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in content)
        content = str(content)
        s, e = content.find("{"), content.rfind("}")
        data = _json.loads(content[s:e + 1]) if s != -1 and e != -1 else {}
        score = float(data.get("score", 0.6))
        findings = [f for f in (data.get("findings") or []) if isinstance(f, dict)]
        return {"name": name, "weight": weight, "score": max(0.0, min(1.0, score)),
                "findings": findings}
    except Exception:
        logger.exception("quality: judge '%s' failed", name)
        return {"name": name, "weight": weight, "score": 0.6,
                "findings": [{"issue": f"Could not evaluate {name} automatically.",
                              "fix": "Review this dimension manually.", "chapter": "-",
                              "severity": "soft"}]}


def _judge_prompt(name: str, context_store: dict) -> str:
    m1 = context_store.get("m1_topic") or {}
    m3 = context_store.get("m3_design") or {}
    body = _all_prose(context_store)[:8000]
    rubric = {
        "methodology": "Do the hypotheses trace to stated research gaps, and does the chosen "
                       "method match the research design? Score 0..1.",
        "writing": "Is the prose coherent, academic in tone, and free of placeholder stubs? "
                   "Score 0..1.",
    }[name]
    return (f"You are a thesis examiner. {rubric}\nReturn STRICT JSON: "
            '{"score": <0..1>, "findings": [{"issue","fix","chapter","severity"}]}\n\n'
            f"Title: {m1.get('research_title')}\nHypotheses: {m3.get('hypotheses')}\n"
            f"Gaps: {(context_store.get('m2_literature') or {}).get('research_gaps')}\n\n"
            f"DRAFT:\n{body}")
```

Wire into `score_thesis`: after the deterministic + results dims, append
`judge_dimension("methodology", 0.15, _judge_prompt("methodology", cs), cs)` and
`judge_dimension("writing", 0.10, _judge_prompt("writing", cs), cs)`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_quality_rubric.py -k judge -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quality/rubric.py api/tests/test_quality_rubric.py
git commit -m "feat(quality): LLM-judge dimensions (methodology, writing)

Bounded judge calls returning score + fixes; robust to malformed JSON (neutral
score + a could-not-evaluate note, overall still computed).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Advisor-directive dimension

**Files:**
- Modify: `quality/rubric.py`
- Test: `api/tests/test_quality_rubric.py`

**Interfaces:**
- Produces: `advisor_dimension(advisor_feedback) -> tuple[dict, dict]` — the dimension + the `advisor` summary. `score_thesis` reads `advisor_feedback` (default `[]`).

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_quality_rubric.py
def test_open_advisor_directive_is_hard_finding():
    fb = [{"id": "1", "chapter": "results", "issue": "Report effect sizes",
           "required_change": "add Cohen's f2", "status": "open"},
          {"id": "2", "chapter": "intro", "issue": "narrow the scope",
           "required_change": "...", "status": "addressed"}]
    r = score_thesis(_GOOD, advisor_feedback=fb)
    assert r["advisor"] == {"total": 2, "addressed": 1, "open": [fb[0]]}
    adv = next(d for d in r["dimensions"] if d["name"] == "advisor")
    assert any(f["severity"] == "hard" and "effect sizes" in f["issue"] for f in adv["findings"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_quality_rubric.py -k advisor -q`
Expected: FAIL — no advisor dimension.

- [ ] **Step 3: Implement the advisor dimension**

```python
# add to quality/rubric.py
def advisor_dimension(advisor_feedback: list[dict]) -> tuple[dict, dict]:
    fb = advisor_feedback or []
    open_items = [f for f in fb if f.get("status") == "open"]
    summary = {"total": len(fb), "addressed": sum(1 for f in fb if f.get("status") == "addressed"),
               "open": open_items}
    findings = [{"issue": f"Advisor required (not yet addressed): {o.get('issue')}",
                 "fix": o.get("required_change", "Address this advisor comment."),
                 "chapter": o.get("chapter", "-"), "severity": "hard"} for o in open_items]
    score = 1.0 if not fb else summary["addressed"] / len(fb)
    return {"name": "advisor", "weight": 0.20, "score": round(score, 3),
            "findings": findings}, summary
```

Wire into `score_thesis`: `adv_dim, adv_summary = advisor_dimension(advisor_feedback or [])`;
append `adv_dim` to `dims`; set `result["advisor"] = adv_summary`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_quality_rubric.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add quality/rubric.py api/tests/test_quality_rubric.py
git commit -m "feat(quality): advisor-directive dimension

Open professor directives become hard findings on their chapter; the advisor
summary reports N-of-M addressed. Reads advisor_feedback (default []).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `review_thesis` tool + M5 `review` roadmap sub-step

**Files:**
- Modify: `agent/tools/writing.py` (add `review_thesis` tool; register in `make_writing_tools`)
- Modify: `agent/roadmap.py` (add `review` before `export` in `ROADMAP["M5"]`; extend `derive_substep` M5)
- Test: `api/tests/test_review_tool.py`, `agent/tests/test_roadmap.py`

**Interfaces:**
- Consumes: `quality.rubric.score_thesis`; the writing tools' `store` closure.
- Produces: `review_thesis() -> str` (json RubricResult) using the store's full context; `ROADMAP["M5"] = ["synthesize_sections", "assemble", "review", "export"]`.

- [ ] **Step 1: Write the failing tests**

```python
# api/tests/test_review_tool.py
import json
from agent.tools.writing import make_writing_tools


class _Store:
    def load_full_context_store(self):
        return {"m1_topic": {"research_title": "T", "research_questions": ["Q"]},
                "m3_design": {"methodology": "PLS-SEM"}, "m4_analysis": {"analysis_results": "AVE=0.6"}}


def test_review_thesis_returns_rubric(monkeypatch):
    tools = {t.name: t for t in make_writing_tools(_Store())}
    assert "review_thesis" in tools
    out = json.loads(tools["review_thesis"].func())
    assert "overall" in out and "dimensions" in out
```

```python
# add to agent/tests/test_roadmap.py
def test_m5_has_review_before_export():
    from agent.roadmap import ROADMAP
    assert ROADMAP["M5"].index("review") < ROADMAP["M5"].index("export")
```

> **Note for implementer:** confirm the store method that returns the FULL nested
> context_store (the rubric needs all modules, not one slice). `agent/state.py:132` references
> `load_full_context_store`; use that (DbProjectStateStore provides it). If the plain
> ProjectStateStore lacks it, add a `load_full_context_store` that returns `load()["contextStore"]`
> nested by module — match how `export_docx` already reads the full store in `writing.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd api && ./run.sh pytest tests/test_review_tool.py ../agent/tests/test_roadmap.py -k "review or M5" -q`
Expected: FAIL — no `review_thesis`, no `review` step.

- [ ] **Step 3: Implement the tool + roadmap step**

In `agent/roadmap.py`, change `ROADMAP["M5"]` to
`["synthesize_sections", "assemble", "review", "export"]` and add to `SUBSTEP_LABELS`
`"review": "Committee-readiness review"`. (M5 `derive_substep` stays: `final_sections`
present ⇒ `None`; the finer display steps render around it.)

In `agent/tools/writing.py`, inside `make_writing_tools(store)`:

```python
    @tool
    def review_thesis() -> str:
        """Grade the current thesis against a committee-readiness rubric (structure,
        citations, method-specific results, methodology, writing, and any open advisor
        comments). Returns per-dimension scores plus specific fixes. Advisory — it does
        not block export."""
        from quality.rubric import score_thesis  # noqa: PLC0415
        cs = store.load_full_context_store()
        profile = getattr(store, "institution_profile", None)
        feedback = (cs.get("advisor_feedback") if isinstance(cs, dict) else None) or []
        return json.dumps(score_thesis(cs, institution_profile=profile,
                                       advisor_feedback=feedback), ensure_ascii=False)
```

Add `review_thesis` to the list `make_writing_tools` returns.

- [ ] **Step 4: Run to verify they pass**

Run: `cd api && ./run.sh pytest tests/test_review_tool.py ../agent/tests/test_roadmap.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/writing.py agent/roadmap.py api/tests/test_review_tool.py agent/tests/test_roadmap.py
git commit -m "feat(quality): review_thesis tool + M5 review roadmap step

Students get a committee-readiness score + fixes before export; the coaching
roadmap gains a review sub-step. Advisory, not blocking.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: CI regression harness

**Files:**
- Create: `quality/eval_harness.py`, `quality/fixtures/` (2+ `context_store` JSON fixtures + a `baselines.json`)
- Test: `api/tests/test_eval_harness.py`

**Interfaces:**
- Consumes: `quality.rubric.score_thesis`.
- Produces: `run_harness(fixtures_dir, baselines) -> tuple[int, list[dict]]` — `(exit_code, rows)`; exit 1 if any fixture's `overall` drops below its baseline minus tolerance.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_eval_harness.py
import json
from quality.eval_harness import run_harness


def test_harness_flags_regression(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text(json.dumps({"m1_topic": {}}))
    baselines = {"a.json": 0.90}
    import quality.eval_harness as h
    monkeypatch.setattr(h, "score_thesis", lambda cs, **k: {"overall": 0.50, "dimensions": []})
    code, rows = run_harness(str(tmp_path), baselines, tolerance=0.03)
    assert code == 1 and rows[0]["regressed"] is True


def test_harness_passes_when_at_baseline(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text(json.dumps({"m1_topic": {}}))
    import quality.eval_harness as h
    monkeypatch.setattr(h, "score_thesis", lambda cs, **k: {"overall": 0.91, "dimensions": []})
    code, _ = run_harness(str(tmp_path), {"a.json": 0.90}, tolerance=0.03)
    assert code == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_eval_harness.py -q`
Expected: FAIL — no `quality.eval_harness`.

- [ ] **Step 3: Implement the harness**

```python
# quality/eval_harness.py
"""CI regression gate: score every fixture context_store and fail if any overall
drops below its recorded baseline. Run on prompt/model changes to catch quality
regressions (e.g. a Gemini↔Claude swap)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from quality.rubric import score_thesis


def run_harness(fixtures_dir: str, baselines: dict[str, float],
                tolerance: float = 0.03) -> tuple[int, list[dict]]:
    rows: list[dict] = []
    regressed_any = False
    for fp in sorted(Path(fixtures_dir).glob("*.json")):
        cs = json.loads(fp.read_text(encoding="utf-8"))
        overall = score_thesis(cs)["overall"]
        base = baselines.get(fp.name)
        regressed = base is not None and overall < base - tolerance
        regressed_any = regressed_any or regressed
        rows.append({"fixture": fp.name, "overall": overall, "baseline": base,
                     "regressed": regressed})
    return (1 if regressed_any else 0), rows


if __name__ == "__main__":  # pragma: no cover
    here = Path(__file__).parent / "fixtures"
    base = json.loads((here / "baselines.json").read_text()) if (here / "baselines.json").exists() else {}
    code, rows = run_harness(str(here), base)
    for r in rows:
        print(f"{r['fixture']:<30} {r['overall']:.3f} (base {r['baseline']})"
              f"{'  ⚠ REGRESSED' if r['regressed'] else ''}")
    sys.exit(code)
```

Create `quality/fixtures/good_pls_thesis.json` and `weak_thesis.json` (each a nested
`context_store`) and `baselines.json` mapping each filename to a recorded `overall` (run the
harness once, paste the numbers).

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_eval_harness.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quality/eval_harness.py quality/fixtures api/tests/test_eval_harness.py
git commit -m "feat(quality): CI regression harness over fixture theses

Same scorer, run over fixtures with recorded baselines; non-zero exit on a
quality drop so prompt/model swaps can't silently degrade output.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_quality_rubric.py tests/test_review_tool.py tests/test_eval_harness.py ../agent/tests/test_roadmap.py -q` → all PASS.
- [ ] `cd api && ./run.sh python -m quality.eval_harness` (from repo root on PYTHONPATH) prints the fixture table and exits 0 at baseline.
- [ ] Read-only confirmed: grep `quality/` for `commit_slice`/`_save`/writes → none.

## Notes / spec deviations

- **Advisor directives + institution profile are READ here, owned by the cross-session-memory
  spec.** This plan defines their read shapes and defaults so quality-evals ships standalone;
  the memory spec adds ingestion/persistence (`project_advisor_feedback_loop` memory).
- **Weights are illustrative** (structure .20, citations .20, stubs .10, results .20,
  methodology .15, writing .10, advisor .20 — they don't sum to 1; `_weighted` normalizes by
  total weight). Tune against the fixture set in Task 6.
