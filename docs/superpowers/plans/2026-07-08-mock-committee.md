# Mock Committee (Hội đồng ảo) Implementation Plan (F6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A post-M5 defense-prep flow that generates committee questions from THIS student's real weak points, drills the student, and produces a defensible cheat-sheet.

**Architecture:** A `generate_committee_questions` tool (weak points from earned state + F3 rubric findings) + a `skills/dothesis-defense/SKILL.md` that runs the drill and exports a cheat-sheet via the existing `run_export`. F2's `next_action` offers "Prep for your defense" once M5 is `done`. No new state-machine module (MODULES stays M1–M5).

**Tech Stack:** Python, LangChain `@tool`, engine LLM, `run_export`, pytest via `./run.sh`.

## Global Constraints

- **No new tracked module** — defense is an optional terminal step, not an M6 in the state machine.
- **Best-effort question generation** — LLM/rubric failure falls back to state-only heuristic questions so the drill always has material.
- **Read-only** over thesis state (except the optional limitations-preempt via M5's normal path).
- **Depends on F2** (post-M5 `next_action` offer) and **F3** (rubric findings as the question source); works state-only without F3.
- **Comment the decision behind each change.**

---

### Task 1: `generate_committee_questions` — state-only heuristics

**Files:**
- Create: `agent/tools/defense.py`
- Test: `api/tests/test_defense.py`

**Interfaces:**
- Produces: `generate_committee_questions(context_store: dict, rubric_result: dict | None = None) -> str` (json list of `{category, question, targets, difficulty, model_answer_hint}`). This task: heuristics from state only.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_defense.py
import json
from agent.tools.defense import generate_committee_questions


def test_small_n_and_rejected_hypothesis_targeted():
    cs = {"m3_design": {"methodology": "PLS-SEM", "sample_plan": {"target_n": 90},
                        "hypotheses": ["H1"]},
          "m4_analysis": {"analysis_results": "H1 not supported (p=0.21)"}}
    qs = json.loads(generate_committee_questions.func(context_store=cs))
    joined = " ".join(q["question"].lower() for q in qs)
    assert "sample" in joined and ("reject" in joined or "not support" in joined)


def test_always_returns_questions_even_on_empty_state():
    qs = json.loads(generate_committee_questions.func(context_store={}))
    assert len(qs) >= 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_defense.py -q` → FAIL (no module).

- [ ] **Step 3: Implement the heuristic generator**

```python
# agent/tools/defense.py
"""Mock Committee — generate defense questions from THIS thesis's weak points. Best-effort:
state-only heuristics guarantee material even if the LLM/rubric is unavailable."""
from __future__ import annotations
import json
from langchain_core.tools import tool


def _state_weakpoints(cs: dict) -> list[dict]:
    m3 = cs.get("m3_design") or {}
    m4 = cs.get("m4_analysis") or {}
    qs: list[dict] = []
    n = (m3.get("sample_plan") or {}).get("target_n")
    if n and n < 200:
        qs.append({"category": "methodology",
                   "question": f"Your sample size is {n}. How do you justify statistical power "
                               "and generalizability?", "targets": "sample size",
                   "difficulty": "medium", "model_answer_hint": "Cite the 10× / inverse-sqrt rule "
                   "and acknowledge it as a limitation with a future-work note."})
    results = str(m4.get("analysis_results") or "").lower()
    if "not support" in results or "reject" in results or "p=0.2" in results:
        qs.append({"category": "results",
                   "question": "One of your hypotheses was not supported. Why do you think that "
                               "is, and what does it mean theoretically?", "targets": "rejected hypothesis",
                   "difficulty": "hard", "model_answer_hint": "Offer a theoretical/contextual "
                   "explanation, not a data-quality excuse."})
    # Always-on staples so the drill is never empty.
    qs += [
        {"category": "contribution", "question": "What is the single most important contribution "
         "of your study?", "targets": "contribution", "difficulty": "medium",
         "model_answer_hint": "One theoretical + one practical contribution, in one sentence each."},
        {"category": "methodology", "question": "Why did you choose this analysis method over the "
         "alternatives?", "targets": "method choice", "difficulty": "medium",
         "model_answer_hint": "Tie to model type, sample size, and construct nature."},
        {"category": "limitations", "question": "What are the main limitations of your study?",
         "targets": "limitations", "difficulty": "easy",
         "model_answer_hint": "Name 2–3 honest limitations with mitigation/future work."},
    ]
    return qs


@tool
def generate_committee_questions(context_store: dict, rubric_result: dict | None = None) -> str:
    """Generate defense-committee questions targeted at THIS thesis's weak points (small n,
    rejected hypotheses, method choice, sampling, borderline validity). Returns categorized
    questions with model-answer hints for a drill."""
    return json.dumps(_state_weakpoints(context_store), ensure_ascii=False)
```

Register `generate_committee_questions` in the tool list.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_defense.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/defense.py api/tests/test_defense.py
git commit -m "feat(defense): generate_committee_questions from state weak points

State-only heuristics (small n, rejected H, method/sampling) so the drill always
has weakness-targeted material.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Rubric-informed questions

**Files:**
- Modify: `agent/tools/defense.py`
- Test: `api/tests/test_defense.py`

**Interfaces:**
- Consumes: F3 `RubricResult` (`dimensions[].findings`). When passed (or fetched), each hard finding becomes a targeted question; else fall back to heuristics.

- [ ] **Step 1: Write the failing test**

```python
# add to api/tests/test_defense.py
def test_rubric_findings_become_questions():
    rr = {"dimensions": [{"name": "citations", "findings": [
        {"issue": "Citation (Ghost, 2099) has no matching reference.", "chapter": "intro"}]}]}
    qs = json.loads(generate_committee_questions.func(context_store={}, rubric_result=rr))
    assert any("ghost" in q["question"].lower() or "reference" in q["question"].lower() for q in qs)
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Fold rubric findings in**

In `generate_committee_questions`, before returning, if `rubric_result` is provided, map each
hard finding to a question:

```python
    questions = _state_weakpoints(context_store)
    if rubric_result:
        for dim in rubric_result.get("dimensions", []):
            for f in dim.get("findings", []):
                questions.append({"category": dim.get("name", "general"),
                    "question": f"A weakness was flagged: {f.get('issue')}. How do you respond?",
                    "targets": dim.get("name"), "difficulty": "hard",
                    "model_answer_hint": f.get("fix", "Acknowledge and defend or disclose as a limitation.")})
    return json.dumps(questions, ensure_ascii=False)
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/defense.py api/tests/test_defense.py
git commit -m "feat(defense): turn rubric findings into targeted committee questions

Each hard quality finding becomes a defense question, so the drill hits exactly
the examiner's likely attack points.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Defense skill + cheat-sheet export

**Files:**
- Create: `skills/dothesis-defense/SKILL.md`
- Modify: `skills/dothesis/SKILL.md` (route "prep for defense" → the defense skill)
- Test: `api/tests/test_skill_content.py`

- [ ] **Step 1: Write the skill**

`skills/dothesis-defense/SKILL.md` — the flow: (1) call `generate_committee_questions` (pass the
`review_thesis` rubric result if available); (2) run an interactive drill — ask one question,
let the student answer, grade against `model_answer_hint`, coach a stronger answer; (3) compile
the drilled Q→improved-answer pairs into a `defense_cheatsheet` and export it via `export_docx`
(the existing writing tool) as a short standalone document.

- [ ] **Step 2: Route from the root skill**

In `skills/dothesis/SKILL.md`, add: when the user asks to prepare for their defense/viva (or M5
is done and they accept the offer), read the `dothesis-defense` skill.

- [ ] **Step 3: Test**

```python
# add to api/tests/test_skill_content.py
def test_defense_skill_exists_and_wired():
    ds = ROOT / "skills/dothesis-defense/SKILL.md"
    assert ds.exists() and "generate_committee_questions" in ds.read_text()
    assert "defense" in (ROOT / "skills/dothesis/SKILL.md").read_text().lower()
```

Run: `cd api && ./run.sh pytest tests/test_skill_content.py -k defense -q` → PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/dothesis-defense/ skills/dothesis/SKILL.md api/tests/test_skill_content.py
git commit -m "feat(defense): mock-committee drill skill + cheat-sheet export

Interactive weakness drill; compiles defensible one-paragraph answers into an
exportable cheat-sheet. Routed from the root skill.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: F2 post-M5 "defense" offer

**Files:**
- Modify: `agent/roadmap.py` (`next_action` step 5)
- Test: `agent/tests/test_roadmap.py`

**Interfaces:**
- Consumes: `next_action` (F2). When every module is `done`, the terminal action offers defense prep (alongside export).

- [ ] **Step 1: Write the failing test**

```python
# add to agent/tests/test_roadmap.py
def test_all_done_offers_defense_prep():
    from agent.roadmap import next_action
    s = {"contextStore": {"final_sections": [{"x": 1}]},
         "status": {m: "done" for m in ["M1", "M2", "M3", "M4", "M5"]}, "focus": "M5"}
    na = next_action(s)
    labels = " ".join(na.get("cta_options", [])).lower()
    assert "defense" in labels or "defence" in labels
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Add the offer**

In `agent/roadmap.py` `next_action` step 5 (everything done), extend `cta_options`:

```python
    return {"module": "M5", "substep": "export", "title": "Export your thesis & prep your defense",
            "why": "Every module is done — generate the final document and rehearse your defense.",
            "cta_options": ["Export my thesis", "Prep for my defense", "Review it first"]}
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/roadmap.py agent/tests/test_roadmap.py
git commit -m "feat(defense): offer defense prep as the post-completion next action

Once M5 is done, next_action leads the student into the mock committee, not just
export — the emotional peak of the journey.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_defense.py tests/test_skill_content.py ../agent/tests/test_roadmap.py -q` → all PASS.
- [ ] Robustness: `generate_committee_questions` on `{}` still returns ≥3 questions.

## Notes

- **Sequence right after F3** so questions are rubric-informed; ships state-only meanwhile.
- **No MODULES change** — defense is a terminal optional step surfaced via `next_action`, not a
  tracked module, so nothing that iterates M1–M5 is affected.
