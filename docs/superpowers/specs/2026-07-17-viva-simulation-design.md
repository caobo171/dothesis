# Rubric-Grounded Viva Simulation — Design Spec

**Date:** 2026-07-17
**Initiative:** Roadmap #10 (`docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:298-322`; table row at `:40`)
**Vision anchors:** §3.7 Defense (`2026-07-17-dothesis-vertical-agent-vision.md:175-184`), checklist item 10 (`:285-286`), and the F6 origin doc (`2026-07-08-mock-committee-design.md` — goals: 20–30 weakness-targeted questions, interactive drill, cheat-sheet, "preempt in the thesis").
**Status:** Design ready — implementation plan in `2026-07-17-viva-simulation-plan.md`.
**All paths repo-relative to the dothesis root.**

---

## 1. Problem and outcome

The shipped mock committee (`agent/tools/defense.py`) is heuristic. Its entire
weakness model is:

- `n < 200` → one power/generalizability question (`agent/tools/defense.py:33-39`);
- the substring `"not support" | "reject" | "p=0.2"` in a *stringified*
  `analysis_results` → one rejected-hypothesis question (`:42-49`);
- three always-on staples (contribution / method choice / limitations, `:52-62`);
- when a rubric result is passed, every finding becomes the same flat template
  — `"A weakness was flagged: {issue}. How do you respond?"`, always
  `difficulty: "hard"`, hint = the finding's `fix` verbatim (`:76-83`).

Since that shipped, the quality gate grew the very signals a real examiner
attacks: stats self-validation (#1), power analysis (#2), screening (#3), DOI
verification (#5), coherence (#6), method-advisor conflict (#7), similarity
(#11) — all aggregated by `score_thesis` (`quality/rubric.py:472-514`) into
per-dimension `{issue, fix, chapter, severity}` findings plus a `blocking`
list (`:509`).

**Outcome of this initiative.** `generate_committee_questions` becomes a
deterministic viva generator that (a) turns each *material* rubric/state
finding into a targeted committee question with an escalated difficulty and a
`model_answer_hint` grounded in the student's own numbers, (b) classifies
every weakness as **must-fix-before-defense** vs **disclosable**, (c) returns
a `readiness` summary, and (d) keeps the drill/cheat-sheet flow in
`skills/dothesis-defense/SKILL.md` but hands it deterministic
`answer_criteria` to grade against. It stays advisory and read-only over
thesis state — a viva sim never blocks anything (skill boundary,
`skills/dothesis-defense/SKILL.md` "Read-only over thesis state").

## 2. Inputs — verified shapes

### 2.1 The nested context store

The tool reads `store.load_full_context_store()`
(`agent/tools/defense.py:101`), which returns the nested
`{m1_topic, m2_literature, m3_design, m4_analysis, m5_writing}` view
(`api/app/agent_state.py:157-171`). Keys the generator uses:

- **`m3_design.hypotheses`** — list (free shape; ids normalized via the
  `H\d` regexes in `agent/coherence.py:29-45`).
- **`m3_design.sample_plan`** — written by the `sampling_plan` tool
  (`agent/tools/instrument.py:173-256`): `{target_n, method_rule, rationale,
  timeline_weeks, power_analysis?}`. `power_analysis` is `thesis_stats.run_power`
  a-priori output (`libs/thesis-stats/src/thesis_stats/power.py:270-306`):
  carries `required_n` (and for PLS `recommended_n`, `:202-207`), `inputs`,
  and a citation-bearing `justification` ("inverse square root method
  (Kock & Hadaya, 2018)…", `:254-257`; Cohen 1988 for regression `:244-252`).
- **`m4_analysis.analysis_results`** — the structured M4 block
  (`skills/dothesis-m4-analysis/SKILL.md:154-174`):
  `descriptives.n`, `measurement_model[]`, `hypothesis_tests[]` with
  `{id, hypothesis, path, numbers: {beta, t, p, f2}, decision,
  interpretation}` where `decision` is "supported"/"not supported" prose
  (normalize with `str(decision).lower().startswith("support")` — parity with
  `agent/coherence.py:241`). Legacy projects may hold a plain string — the
  substring heuristic stays as fallback.
- **`m4_analysis.field_it_quality`** — list of quality flags from fielded
  collections (`agent/state.py:439-450`; M4-owned per `SLICE_OWNERSHIP`,
  `agent/state.py:49-51`). Only its *length* is used (shape of entries is
  producer-defined; never dereference fields from it).
- **`m1_topic.target_population` / `scope`** (`agent/state.py:36-37`) — to
  ground the generalizability staple.

### 2.2 The rubric result (`score_thesis`)

`score_thesis(context_store, institution_profile=…, advisor_feedback=…)`
(`quality/rubric.py:472-514`) returns
`{overall, method, dimensions: [{name, weight, score, findings}], advisor, blocking}`.
Every finding is `{issue, fix, chapter, severity}` with severity
`"hard" | "soft"`. Dimensions and their severity policy (all verified in
`quality/rubric.py`):

| dimension | severities | lines |
|---|---|---|
| `structure` | hard | :33-41 |
| `citations` (+ institution min-refs overlay) | hard | :43-63, :172-182 |
| `no_stubs` | hard | :65-73 |
| `results_validity` (presence checks) | soft | :89-108 |
| `methodology`, `writing` (LLM judges) | LLM-authored | :186-230 |
| `advisor` (open directives) | hard | :233-247 |
| `preflight` (incl. method-advisor conflict, power-justification gap) | soft | :111-128, `agent/preflight.py:36-57` |
| `instrument_quality` | soft | :131-155 |
| `stats_validity` (#1 self-validation) | hard + soft | :257-288 |
| `source_verification` (#5) | soft | :291-427 |
| `coherence` (#6, prose vs persisted numbers) | hard + soft | :430-452 |
| `similarity` (#11) | soft | :455-469 |

The rubric is the aggregation point: power-justification gaps and the
method-advisor conflict already surface through `preflight` findings
(`agent/preflight.py:36-39, :44-57`), screening-design gaps through the
reverse-coded check (`:41-43`), unverifiable DOIs through
`source_verification`. **Decision: the viva runs on `score_thesis` output; it
re-derives nothing the rubric already computes** (§10.1).

### 2.3 What the rubric does NOT carry (state-direct signals)

Three examiner attacks are visible only by joining state the rubric doesn't
join:

1. **Achieved-power shortfall** — `analysis_results.descriptives.n` (or
   `len(field_it_responses)`) vs `sample_plan.power_analysis.required_n /
   recommended_n`. The rubric's preflight only checks the *plan exists*
   (`agent/preflight.py:33-39`); the shortfall between plan and reality is the
   viva's classic question.
2. **Per-hypothesis "not supported"** — `hypothesis_tests[].decision`. The
   coherence dimension checks prose *agreement* with the decision, not the
   decision itself; an honest "H2 not supported" produces zero rubric findings
   but is the first thing a committee pulls.
3. **Fielded-data quality flags** — `field_it_quality` count.

These three are computed deterministically in the viva core from persisted
state. Everything else comes from the rubric.

## 3. Architecture and placement

```
agent/viva.py                 NEW — pure, offline, stdlib-only, never raises
  generate_viva(context_store, rubric_result=None) -> dict   (the envelope, §8)
  state_signal_questions(cs) -> list[dict]                   (§2.3 signals + staples)
  rubric_questions(rubric_result) -> list[dict]              (§4 mapping)
  readiness(questions) -> dict                               (§6)

agent/tools/defense.py        EXTENDED — stays the tool surface
  committee_questions(cs, rubric_result=None) -> list        kept as the pure
      question-list API (now delegates to agent.viva; other callers keep a list)
  make_defense_tools(store)   tool now returns the FULL envelope JSON
      (questions + readiness + meta); store-bound factory unchanged
      (agent/tools/defense.py:87-116, registered agent/runtime.py:162,:540)

skills/dothesis-defense/SKILL.md   EXTENDED — readiness-first drill flow (§9.3)
```

Precedent for the pure-module split: `agent/coherence.py`,
`agent/method_advisor.py`, `agent/preflight.py` — pure logic unit-tested
directly, tool wiring separate (the F0 pattern documented in
`agent/tools/defense.py:6-11`). `agent/viva.py` imports nothing heavier than
`agent.coherence.normalize_hypothesis_id` (module-scope stdlib only; no
LangChain, no quality import — the rubric result arrives as a plain dict).

## 4. Question-targeting model (normative)

A question is emitted from exactly three sources, in this order:

**A. Rubric findings → one question per material finding.**
For each dimension in `rubric_result["dimensions"]`, for each finding:

- **Skip** placeholder findings whose `issue` starts with
  `"Could not evaluate"` (the judge-failure note, `quality/rubric.py:211-213`)
  — a failed evaluation is not a weakness; turning it into a question would
  fabricate one.
- Build the question from the per-dimension template table (§7). Templates
  interpolate the finding's own `issue`/`chapter`; unknown dimension names
  fall back to the generic template (today's `:80` phrasing) so a future
  rubric dimension degrades gracefully instead of being dropped.
- **Per-dimension cap: 3 questions**, hard-severity findings first (a thesis
  with 30 uncited citations gets 3 citation questions + a count in the
  readiness summary, not 30 near-duplicates). **Overall cap: 30** (the F6
  "20–30 questions" goal). Dedup key: `(category, issue)`.

**B. State-direct signals (§2.3).**

- *Power shortfall:* if `power_analysis` exists and an achieved n is
  resolvable and `n_achieved < required_n` (use `recommended_n` when present
  — it is the max of the two rules, `power.py:207`) → one `methodology`
  question. If no `power_analysis` but `target_n < 200` → today's small-n
  question (`agent/tools/defense.py:33-39`) survives as the degraded form.
  Emit one or the other, never both.
- *Not-supported hypotheses:* one `results` question **per** hypothesis whose
  normalized decision is not-supported (cap 3), each naming the hypothesis id,
  path, and β/p from `numbers` — replacing the blind substring question. The
  substring heuristic (`:42-49`) remains only for string-typed legacy
  `analysis_results`.
- *Field-it quality flags:* `len(field_it_quality) > 0` → one `data_quality`
  question carrying the count.

**C. Staples — the classic per-thesis questions, always present** (empty-state
guarantee, `agent/tools/defense.py:51-62`): contribution, method
justification, limitations — plus a new **generalizability** staple that
interpolates `m1_topic.target_population`/`scope` when present ("Your study
covers {scope} — to whom do your findings generalize?").

**Never-fabricate rule (normative):** every non-staple question MUST carry a
`grounding` object (§8) whose `issue` is copied verbatim from a rubric finding
or whose `values` are read directly from state. There is no path that emits a
weakness question without a finding or a state value behind it. This is
enforced by test, not convention.

## 5. Difficulty escalation

Deterministic mapping from evidence strength — a hard finding is a hard
question:

| source | difficulty |
|---|---|
| rubric finding, `severity: "hard"` | `hard` |
| rubric finding, `severity: "soft"` | `medium` |
| power shortfall ≥ 20% below required n | `hard` |
| power shortfall < 20% / small-n heuristic | `medium` |
| not-supported hypothesis | `hard` (unchanged from `:47`) |
| field-it quality flags | `medium` |
| staples | `easy`–`medium` (unchanged from `:52-62`) |

Roadmap #10 mentions calibrating difficulty to the degree level from M1
(`roadmap.md:320-321`); **deferred** — no degree/level key exists anywhere in
state today (`SLICE_OWNERSHIP["M1"]`, `agent/state.py:36-37`, has no such
field; grep across `agent/ api/ skills/` confirms). When cross-session memory
grows one, it becomes a ±1 step on this table.

## 6. Defensibility and the readiness summary

Every question gets a `defensibility` class, derived from the same severity
policy the rubric already committed to (only provably-wrong blocks — the #1
bar, restated in `agent/coherence.py:4-9`):

- **`must_fix`** — rubric severity `hard` (exactly the findings feeding
  `blocking`, `quality/rubric.py:509`): a prose number contradicting the
  persisted result, an impossible statistic, a fabricated citation, a stub
  chapter, an open advisor directive. You do not talk your way past these; the
  hint says *fix, then re-drill* and routes to the owning module.
- **`disclosable`** — rubric severity `soft` + all state-direct signals
  (power shortfall, not-supported hypothesis, quality flags). Legitimate
  limitations: disclose, frame, move on.
- **`standard`** — the staples (not weaknesses).

Readiness verdict (advisory only — surfaced, never enforced):

```
must_fix > 0                  -> "not_ready"
must_fix == 0, disclosable>0  -> "ready_with_disclosures"
otherwise                     -> "ready"
```

`readiness` also carries `must_fix` / `disclosable` counts, counts by
dimension (including findings beyond the per-dimension question cap, so 30
uncited citations show as `citations: 30` even though only 3 questions
emitted), and a one-sentence deterministic summary. Optional tie-in: the
quality report may later display this verdict; the dependency stays one-way
(rubric → viva, never viva → rubric) to avoid an import cycle — out of scope
here beyond keeping the envelope JSON-stable.

## 7. Hint + criteria templating (normative)

Per-dimension template table `VIVA_TEMPLATES` in `agent/viva.py`, keyed by
rubric dimension name. Each entry defines: question phrasing, category,
`model_answer_hint` builder, and 2–4 deterministic `answer_criteria` strings.
The hint builder **reuses the finding's own `fix`** (the per-check fix
templates already written in the dimensions, e.g. `quality/rubric.py:60-62,
:279-281, :443-444`) and prefixes the defensibility framing. Representative
rows (full table is implementation, but these are normative in tone and
grounding):

| dimension / signal | question (template) | model_answer_hint (template) |
|---|---|---|
| `coherence` (hard) | "Your text says one number, your results table says another: {issue} Which is correct?" | "MUST FIX before the defense: {fix} A number mismatch cannot be defended — reconcile prose and results, then re-drill." |
| `stats_validity` (hard) | "{issue} Can you walk the committee through how this value was computed?" | "MUST FIX: {fix} An examiner recomputing this will find it — correct the source, never the narration." |
| `citations` (hard) | "{issue} Where can the committee find this source?" | "MUST FIX: {fix}" |
| `advisor` (hard) | "Your advisor required: {issue} — show the committee where you addressed it." | "MUST FIX: {fix} Committees include the advisor." |
| power shortfall (state) | "You collected n={n_achieved} but your own a-priori analysis requires N={required_n}. Justify your statistical power." | "Disclose and frame: acknowledge n={n_achieved} < N={required_n}; cite the a-priori method from your plan ({justification citation — e.g. Kock & Hadaya 2018}); frame as a boundary condition with a post-hoc achieved-power figure and a future-work note — not a fatal flaw, never an excuse." |
| not-supported H (state) | "{hid} ({path}) was not supported (β={beta}, p={p}). Why, and what does that mean theoretically?" | "Offer a theoretical/contextual explanation tied to your model — a null result is a finding, not a failure; never a data-quality excuse." (extends `:48-49`) |
| `similarity` (soft) | "{issue} How do you respond to a similarity query on this passage?" | "Disclose and fix hygiene: {fix}" |
| `source_verification` (soft) | "{issue} How did you verify this source?" | "Disclose: {fix} Verify before the defense if possible." |
| `preflight` / `instrument_quality` / `results_validity` (soft) | "{issue} — how do you justify this design choice to the committee?" | "Disclose and frame: {fix}" |
| unknown dimension | today's generic `:80` phrasing | "{fix}" (fallback `:83`) |

`answer_criteria` example (power): `["States the achieved n and required N
explicitly", "Cites the a-priori method used in the plan", "Frames the
shortfall as a boundary condition with future work", "Does not blame the data
or the committee's threshold"]`. The drill (skill) grades free-text answers
against these — the criteria are deterministic; the grading voice is the chat
LLM (§9).

Language note: templates are English; the skill already re-voices questions
and coaching in the student's language (`skills/dothesis-defense/SKILL.md`
"in their language (Vietnamese if they wrote in Vietnamese)"). Interpolated
`issue`/`fix` strings arrive in whatever language the rubric emitted — pass
through untouched.

## 8. Output envelope (normative)

The tool returns JSON (was: bare list — see §10.2 for the compat decision):

```json
{
  "questions": [
    {
      "id": "q-coherence-1",
      "category": "coherence",
      "question": "…",
      "targets": "H2 beta mismatch",
      "difficulty": "hard",
      "defensibility": "must_fix",
      "model_answer_hint": "MUST FIX before the defense: …",
      "answer_criteria": ["…", "…"],
      "grounding": {
        "source": "rubric:coherence",       // or "state:power" | "staple"
        "severity": "hard",                  // null for staples
        "issue": "<verbatim finding issue>", // null for staples
        "chapter": "results",
        "values": {"n_achieved": 95, "required_n": 160}  // state signals only
      }
    }
  ],
  "readiness": {
    "verdict": "not_ready",
    "must_fix": 2,
    "disclosable": 5,
    "by_dimension": {"coherence": 1, "citations": 30, "similarity": 2},
    "summary": "2 must-fix findings block a confident defense; 5 weaknesses are disclosable."
  },
  "meta": {
    "generator": "viva-v2-deterministic",
    "rubric_available": true,
    "method": "pls-sem"
  }
}
```

Ordering is deterministic: must_fix (hard→) first, then disclosable, then
staples; stable within groups by (dimension order as emitted by
`score_thesis`, finding index). Two runs over the same inputs are
byte-identical.

## 9. Determinism and the LLM boundary

**Decision: the generator itself contains zero LLM calls.** Findings,
targeting, difficulty, defensibility, hints, criteria, readiness — all
deterministic and offline. The LLM appears at exactly two pre-existing
boundaries:

1. **Inside `score_thesis`** — the two judge dimensions
   (`quality/rubric.py:482-485`). Already best-effort: failure yields a
   neutral dim whose placeholder finding the viva *skips* (§4.A). The tool's
   rubric pass keeps today's try/except fallback to state-only questions
   (`agent/tools/defense.py:105-113`).
2. **In the drill** — the skill's grading/coaching voice
   (`skills/dothesis-defense/SKILL.md` step 2). The chat agent already
   rephrases questions naturally and in the student's language; it now grades
   against the deterministic `answer_criteria` instead of a free-form hint.

Rationale for no phrasing pass inside the tool: the presenting agent IS an
LLM surface — natural phrasing is free at presentation time; an in-tool
phrasing call would add cost, nondeterminism, and an online dependency to a
generator whose tests must run offline, for zero user-visible gain. This
mirrors the rubric's own split (deterministic dims + bounded judge dims).

**Never-crash:** `generate_viva` follows the `validate_coherence` posture
(`agent/coherence.py:478+`, `quality/rubric.py` fail-open pattern): any
malformed slice degrades that question source, never the call; empty store →
staples + `verdict: "ready"` with `rubric_available: false` noted in meta.

## 10. Design decisions resolved

1. **Run on `score_thesis` output, don't re-derive.** The rubric already
   aggregates all eleven finding sources with a uniform
   `{issue, fix, chapter, severity}` shape and a severity policy this design
   reuses wholesale (§2.2). Re-deriving would duplicate eleven call sites and
   drift. The only state-direct computations are the three signals the rubric
   genuinely does not join (§2.3).
2. **Envelope replaces the bare list.** The tool's only consumers are the
   defense skill prompt and `api/tests/test_defense.py:66-70` (asserts a
   list) — both updated in this initiative. The pure
   `committee_questions()` keeps returning a list (delegating to
   `agent.viva`) so any other caller of the pure API is unaffected; plan
   includes a repo-wide grep gate.
3. **Difficulty from severity** (§5) — one table, no judgment calls; degree
   -level calibration deferred with grep-evidence (no such state key).
4. **Hints reuse finding `fix` strings** (§7) — the per-check fix templates
   in the dimensions are already the best per-finding remediation text; the
   viva adds only defensibility framing and grounded numbers.
5. **Advisory, never blocking.** No `commit_slice`, no status change, no
   gate: the readiness verdict is information. Consistent with the skill's
   read-only boundary and the F6 non-goals.
6. **Screening questions read `field_it_quality` only** — the single
   *persisted* screening artifact (`agent/state.py:439-450`); `run_stats
   op="screening"` output is not persisted as its own key and is therefore
   not a viva input (whatever the student committed into `analysis_results`
   reaches the viva via the rubric instead).
7. **Interactive answer-grading stays in the skill** — no new grading tool.
   The roadmap's "grades student answers … and iterates until pass"
   (`roadmap.md:309-310`) is realized as: deterministic `answer_criteria` in
   the envelope + skill instructions to grade each criterion explicitly.
   A dedicated grading tool (LLM-judge with the criteria) is a clean later
   increment behind the same boundary; not required for this initiative.

## 11. Testing strategy (all offline — see plan)

- **Unit (pure core):** hand-built rubric_result fixtures per dimension →
  correct question, category, difficulty, defensibility, hint interpolation;
  caps/dedup/ordering; judge-placeholder skipping; the never-fabricate
  property (every non-staple question's `grounding.issue` appears verbatim in
  the input rubric/state); byte-determinism across two calls.
- **State signals:** engineered nested stores for power shortfall (n=95 vs
  required 160 → hard + grounded hint), boundary (no power_analysis → small-n
  degraded form), structured hypothesis decisions, legacy string results,
  field_it_quality.
- **Clean thesis:** rubric with zero findings + healthy state → staples only,
  `verdict: "ready"`.
- **Never-crash:** empty store, `None` slices, junk-typed values.
- **Integration:** engineered store through the real `score_thesis` with the
  judge LLM stubbed (monkeypatch pattern from `api/tests/test_defense.py:47-53`)
  → envelope contains must_fix questions matching the rubric's `blocking`.
- **Regression:** existing `api/tests/test_defense.py` updated to the
  envelope; full suites stay green.

## 12. Out of scope

- Grading tool / iterate-until-pass automation (§10.7 — later increment).
- Feeding disclosed weaknesses into M5 limitations (F6 "preempt" goal — a
  separate M5-side initiative; the envelope's `disclosable` list is the
  designed input for it).
- Degree-level difficulty calibration (§5 — no state key yet).
- Rubric/report UI tie-in beyond a JSON-stable envelope (§6).
