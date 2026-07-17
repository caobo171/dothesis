# M1 Topic Feasibility — Sample-Size Reality Check + Operationalizability (Design)

**Date:** 2026-07-18
**Status:** Design — approved for implementation (companion plan: `2026-07-18-m1-feasibility-plan.md`)
**Delivers:** Vision §3.1 (`2026-07-17-dothesis-vertical-agent-vision.md:96-104`)
**Builds on:** shipped power-analysis ops (`libs/thesis-stats/src/thesis_stats/power.py`), M3 sampling_plan (`agent/tools/instrument.py:158-259`), method advisor (`agent/method_advisor.py`)

---

## 1. What this is and the bar it serves

Vision §3.1 sets the M1 bar (`2026-07-17-dothesis-vertical-agent-vision.md:97-99`):
a title + RQs that are *quantifiable* — every RQ maps to a testable relationship
between measurable constructs, in a population the student can actually sample.
The end-state (`:100-104`): the agent **refuses-softly** (advises, never blocks)
when an RQ cannot be operationalized as a survey construct, and the feasibility
check includes an early sample-size reality check ("this model will need n≈200;
can you get that?") — *powered by the same power-analysis op used later in M4*.

Two deterministic, advisory checks, delivered at M1 (topic lock), months before
the student has a conceptual model:

1. **Sample-size reality check** — from a coarse topic-level signal (rough
   construct/predictor count + method family if known), compute an early
   required-N estimate via the shipped `thesis_stats.run_power` engine, and ask
   the one question that kills more theses than any statistic: *"a model like
   this typically needs n ≈ N — can you realistically sample that from
   {target_population}?"*
2. **Operationalizability check** — flag RQs that are describable but not
   testable (definitional / normative / no measurable relationship), with a
   concrete reframe suggestion. Advise, never block.

Binding principles (vision §5): advisory-not-blocking (`:240-244`),
deterministic-before-generative (`:237-239`), fail-open everywhere, whitelist
is the compute boundary (`:226-232`), skills-first (`:253-255`), two-register
explanations (`:256-259`).

---

## 2. Grounded inventory (what exists; exact shapes)

### 2.1 The M1 persisted slice

`agent/state.py:35-37` — M1 owns:
`research_title, research_questions, decisions, language, field, research_type,
objectives, target_population, scope, user_context`. The slice map is mirrored
in `skills/dothesis/SKILL.md:178` (sync note at `agent/state.py:22-23`).

- `research_questions: string[]` — committed by the M1 wizard at
  `skills/dothesis-m1-topic/SKILL.md:87-88`.
- `research_type` is already normalized to a bounded literal —
  `quantitative | qualitative | mixed | Other` — via the M1 card options
  (`orchestrator/agents/m1_topic.py:71-84`, card fields at `:45`).
- `target_population` and `scope` are free-text card fields
  (`orchestrator/agents/m1_topic.py:45-51`) also seeded by partner intake
  (`orchestrator/intake.py:72-73`).

**At M1 there is no `conceptual_model`, no `methodology`, no `instrument`** —
those are M3-owned (`agent/state.py:43-44`). The feasibility estimate must work
from coarser signals (§4).

### 2.2 The shipped power engine (reuse, do NOT rebuild)

`libs/thesis-stats/src/thesis_stats/power.py` — pure, deterministic, "no LLM /
network / I/O / RNG" (`:1`). Public dispatcher (`:270-274`):

```python
run_power(analysis, mode="apriori", effect_size=None, alpha=0.05, power=0.80,
          predictors=None, n=None, n1=None, n2=None, ratio=1.0,
          alternative="two-sided") -> dict
```

- `analysis ∈ {regression, correlation, ttest, pls_sem}` (`:27-32`); no CB-SEM.
- Named effect-size conventions (`:27-31`): regression medium f²=0.15;
  pls_sem medium β=0.20; default when `effect_size=None` is `"medium"` (`:59-60`).
- **A-priori regression** (`:110-114`): requires `predictors ≥ 1`; returns
  `{"required_n": int}`. Golden: medium f², k=3 → **N=77**
  (`libs/thesis-stats/tests/test_power.py:12-18`).
- **A-priori PLS-SEM** (`:196-208`): inverse-square-root (Kock & Hadaya 2018),
  one-tailed, constant 2.486 at α=.05/power=.80 (`:197-199`);
  `required_n = ceil((2.486/β)²)` — **medium β=0.20 → N=155**, independent of
  k. When `predictors` given, adds the 10-times-rule `cross_checks` (Hair et
  al. 2017) and `recommended_n = max(required_n, 10*k)` (`:203-207`).
- **Payload** (`:299-315`): `{analysis, mode, inputs{effect_size,
  effect_size_label, effect_metric, alpha, power, predictors?}, required_n
  (/recommended_n/cross_checks), assumptions[], justification, citations[],
  method, caveats[]?}`.
- **The committee-ready justification sentence** is composed at `:237-258`;
  the PLS one (`:253-258`): *"Using the inverse square root method (Kock &
  Hadaya, 2018) with a minimum path coefficient β = …, α = … and power = …,
  the minimum sample is N = …; cross-checked against the 10-times rule, the
  recommended target is N = …"*. Regression (`:242-245`) cites Cohen (1988) and
  Faul et al. (2009).

Tool boundary: `run_stats(op="power")` → `_op_power`
(`agent/tools/stats.py:298-313`) — "`file` is optional: a-priori is data-free"
(`:302-303`); op whitelisted at `:391`.

### 2.3 The M3 machinery this must stay consistent with

- `make_sampling_plan_tool(store)` (`agent/tools/instrument.py:158-259`):
  reads the live store (never model-supplied state — F0 rule, `:163-165`),
  computes the heuristic floor via `target_sample_n`
  (`agent/sampling.py:12-26`: PLS 10×max-in-degree floored at 60; regression
  15×k floored at 50; CB-SEM max(200, 10×indicators)), then makes power
  primary: `ts.run_power(analysis, "apriori", effect_size="medium",
  predictors=k)` with `k = _max_in_degree(cm)` (`:221-230`), takes
  `max(heuristic_n, power_n)`, embeds the justification sentence in the
  rationale (`:236-238`), and persists to M3 `sample_plan` via `commit_slice`
  (`:252-256`). Fail-open on power errors (`:231-233`).
- `_max_in_degree` (`agent/tools/instrument.py:141-155`): k = the largest
  number of arrows into any one construct — *the widest single regression*,
  which is what drives power. This k-semantics is the contract the M1 coarse
  estimate must share (§7).
- `agent/method_advisor.py`: `normalize_method` (`:29-41`) maps free-text
  method names → `regression | pls_sem | cb_sem | nonparametric`;
  `model_profile` (`:50-79`) needs a `conceptual_model`, which does not exist
  at M1 — so it is NOT reusable here (§3, D2 rationale).
- `agent/preflight.py:18-64`: the pure advisory-check pattern
  (`preflight_check(context_store) -> list[str]`, never blocks) +
  `make_preflight_tool(store)` factory (`:67-92`), registered in
  `agent/runtime.py:518`. `agent/coherence.py:1-12` is the "pure, offline,
  never raises" precedent for deterministic text heuristics.

### 2.4 The M1 skill surface

`skills/dothesis-m1-topic/SKILL.md` — a guided wizard, one pass per invocation
(`:14-15`); Phase 3 drafts title + 2-4 RQs with per-RQ bars ("name the
construct(s) and the relationship", `:79-83`); Phase 4 confirms and commits
(`:84-88`). The defense-date capture (`:90-96`) is the existing model for an
*advisory, asked-once, early* feasibility signal ("if the plan comes back
`feasible: false` … flag it warmly … never refuse").

Vietnamese detection heuristic exists at `orchestrator/tools/m1_topic.py:23-25`
(`_is_vietnamese`).

---

## 3. Design decisions

### D1 — Where it lives: pure core in `agent/feasibility.py` + store-bound tool `make_feasibility_tool(store)`

New module `agent/feasibility.py` with two **pure** functions
(`estimate_sample_size`, `check_operationalizability`) and one thin store-bound
LangChain tool factory `make_feasibility_tool(store)` exposing a single tool
`topic_feasibility`, registered in the `agent/runtime.py` tool list next to
`make_preflight_tool(store)` (`agent/runtime.py:518`).

This is the established hybrid: pure check unit-tested offline
(`agent/preflight.py:18` pattern) + factory that closes over the store and
persists results (`agent/tools/instrument.py:158-171` pattern).

**Rejected — M1-skill-invoked raw `run_stats(op="power")`:** the skill (an
LLM) would have to pick `analysis`/`predictors`/`effect_size` itself — exactly
the judgment that must be deterministic (vision §5.3); it cannot interpolate
`target_population` from the store, cannot degrade to a range when the method
is unknown, and cannot persist the estimate for M3 reconciliation.

**Rejected — preflight-style pure check only (no tool):** `preflight_check`
runs at the M3→M4 boundary on state that already exists. The M1 wizard needs
an *invokable* mid-conversation tool during Phase 4, before `commit_slice`,
and needs to pass the two conversation-only hints (D2) that live nowhere in
the store yet.

**Rejected — new whitelisted op in `agent/tools/stats.py`:** `run_stats` ops
are data/compute ops; this is a state-reading advisory (like `sampling_plan`,
which also lives outside the OPS dict). No new computation is added — the tool
calls `thesis_stats.run_power` directly by Python import, the same way
`sampling_plan` does (`agent/tools/instrument.py:225-227`), which keeps
principle §5.1 intact (no new analysis outside the whitelist; the analysis IS
the whitelisted power engine).

### D2 — The coarse-input contract at M1

Store-read (authoritative, F0 rule — `agent/tools/instrument.py:163-165`):
`research_questions`, `research_title`, `research_type`, `target_population`,
`field` from the M1 slice.

Model-supplied hints (tool args, both optional):

```python
topic_feasibility(expected_constructs: int = 0, method_hint: str = "") -> str
```

- `expected_constructs` — the student's rough count of constructs/factors in
  the model they imagine ("I think satisfaction, trust, price, and loyalty" →
  4). The skill instructs the agent to pass what the *student said*, not to
  invent one.
- `method_hint` — free text if the student already mentioned a family
  ("PLS-SEM", "SPSS regression"); normalized via
  `agent.method_advisor.normalize_method` (`agent/method_advisor.py:29-41`).

Why model-supplied args are acceptable here when F0 forbids them for state:
these two hints exist only in conversation (no store key yet), and they are
*low-stakes* — they tune an advisory estimate; nothing hard depends on them.
They are persisted alongside the estimate with provenance
(`predictors_source`, D8) so M3 can see what was assumed.

**Predictor-count (k) derivation ladder** (first match wins; k is clamped to
[1, 12]):

1. `expected_constructs ≥ 2` → `k = expected_constructs - 1` (coarse
   worst-case: every other construct points at one DV — the widest possible
   regression, consistent with the `_max_in_degree` semantics of
   `agent/tools/instrument.py:141-143`). `predictors_source = "student_stated"`.
2. Else count RQs containing a relationship marker (the same lexicon as the
   operationalizability check, D7): `k = clamp(count, 2, 8)` when count ≥ 1.
   `predictors_source = "inferred_from_rqs"`. Rationale: each testable sub-RQ
   typically names one predictor→DV relationship (M1 skill bar,
   `skills/dothesis-m1-topic/SKILL.md:79-83`).
3. Else `k = 4`, `predictors_source = "default"` — a typical 5-construct
   survey model; the assumption is stated in the output verbatim.

This is deliberately the *smallest* input set that yields a useful N: for
PLS-SEM the a-priori N does not depend on k at all
(`libs/thesis-stats/src/thesis_stats/power.py:204`), so k only sharpens the
regression figure and the 10×-rule cross-check.

### D3 — Pre-M3 method-family default: compute BOTH regression and PLS-SEM, report a range

- `normalize_method(method_hint)` → `pls_sem` or `regression`: compute that
  single family. `status = "estimate"`.
- → `cb_sem`: the power engine has no CB-SEM analysis (`power.py:27-32`);
  fall back to the heuristic `target_sample_n("cb-sem", …)`
  (`agent/sampling.py:22`: max(200, 10×indicators) — with no indicator count
  at M1, report the Kline ≥200 floor) with an explicit "heuristic, not power"
  basis. `status = "estimate"`, `basis = "heuristic"`.
- → `None` (the normal M1 case): compute **both**
  `run_power("regression", "apriori", effect_size="medium", predictors=k)` and
  `run_power("pls_sem", "apriori", effect_size="medium", predictors=k)`, and
  report `range = [min, max]` of the resulting Ns (regression medium k=4 → 85;
  PLS medium → 155/recommended ≥ max(155, 10k)). Headline the **upper** bound
  ("plan for ~155–160") — under-recruiting is the unrecoverable failure.
  `status = "range"`, with the caveat sentence: *"assumes a medium effect and
  a survey model of about {k+1} constructs; M3 will compute the exact figure
  from your actual model."*
- `research_type == "qualitative"` (`orchestrator/agents/m1_topic.py:71-84`)
  → `status = "skipped"`, `skipped_reason` explains that a-priori power applies
  to quantitative designs (vision non-goal §7, `:294-298`). `mixed`, 
  `quantitative`, `Other`, and missing all compute.

Rationale for the both-families range over a single default: the product's
core market is PLS-SEM survey theses (vision §1), but the headless M3
auto-fill is constrained to plain regression (vision §2 table, `:57`), so
neither family is a safe universal assumption. A range with a stated
assumption is honest, fails gracefully, and cannot contradict whatever M3
later picks — the M3 figure will land inside or near the disclosed range for
the same medium-effect convention (D10).

### D4 — Effect-size assumption: the `"medium"` named convention, always

Identical to M3's `sampling_plan` call
(`agent/tools/instrument.py:226-227`: `effect_size="medium"`). Same constants
(`power.py:27-31`), same engine ⇒ the M1 estimate and the M3 computed plan
agree *by construction* whenever k agrees; when k differs the delta is
explainable ("your actual model has 5 arrows into Loyalty, not the 4 we
assumed"). The payload's own `assumptions[]` already discloses "medium effect
assumed (no pilot estimate supplied)" (`power.py:328-330`).

### D5 — Reuse the justification sentence verbatim

Each computed estimate carries `payload["justification"]`
(`power.py:302`, composed `:237-258`) **unchanged** — the spec-mandated
citable basis. The skill presents it as "the sentence you will later paste
into Chapter 3". Never re-word it in code; the LLM may translate it for a
Vietnamese student but the tool output keeps the canonical English sentence
(two-register rule, vision `:256-259`).

### D6 — Advisory + fail-open, three-step degradation ladder

The tool **never raises and never blocks** the Phase-4 commit
(vision `:240-244`; `agent/coherence.py:1` "never raises" precedent).

| Condition | Behavior |
|---|---|
| Power engine available, inputs derivable | Full estimate/range with justification + citations |
| `run_power` raises / `thesis_stats` unimportable | Fall back to `target_sample_n` heuristic (`agent/sampling.py:12-26`) with its rule string as the basis; `basis = "heuristic"` (mirrors `agent/tools/instrument.py:231-233`) |
| Even the heuristic fails (defensive) | Canned range `[100, 200]`, `basis = "canned"`, assumption sentence: "typical survey-model range; recompute in M3" |
| Empty M1 slice (no RQs, no population) | Ladder step 3 of D2 (k=4 default) + `{target_population}` placeholder replaced by "your intended population"; still returns, still advisory |
| `research_type == "qualitative"` | `status="skipped"` + one-line note; operationalizability still runs |

Store persistence (D8) is best-effort inside `try/except` exactly like
`agent/tools/instrument.py:252-256` — a write failure never loses the result.

### D7 — Operationalizability: deterministic lexicon heuristics, no LLM judge in v1

Pure function over `research_questions: list[str]` (plus the title for the
topic-level finding). stdlib `re`/`unicodedata` only (the
`agent/coherence.py:11` discipline). Per-RQ classification, first match wins:

| Kind | Trigger (EN lexicon) | Trigger (VI lexicon) | Advice template |
|---|---|---|---|
| `definitional` | `what is the meaning of`, `what does .* mean`, `^what is\b` (with no relationship marker), `how is .* defined` | `là gì`, `ý nghĩa của .* là`, `được định nghĩa` | "This asks what X *is* — describable, not testable. Reframe as a relationship: 'To what extent does X affect Y among {population}?'" |
| `normative` | `\bshould\b`, `\bought to\b`, `is it right/wrong` | `\bnên\b`, `cần phải` | "This asks what *should* be — a value judgment a survey can't test. Reframe around what people *do/report*." |
| `no_measurable_relationship` | RQ has **no** relationship marker AND no comparative marker | same, VI lexicon | "No measurable DV or relationship named. Which construct changes, and what moves it?" |
| (ok) | contains a relationship marker | — | not flagged |

Relationship-marker lexicon (shared with D2 step 2): EN
`affect|influence|impact|relationship|associat|predict|effect of|moderat|mediat|
correlat|difference between|to what extent|depend`, VI
`ảnh hưởng|tác động|mối quan hệ|dự đoán|mức độ|sự khác biệt|liên hệ|phụ thuộc`
(Vietnamese RQs are first-class — `orchestrator/tools/m1_topic.py:23-25`).
Exact regexes are an implementation detail; the classes and precedence above
are normative. Matching is case-insensitive on NFC-normalized text.

Topic-level finding: if **zero** RQs carry a relationship marker and
`research_type` is not `qualitative`, add one `topic_not_testable` finding
("all RQs are descriptive — a quantitative thesis needs at least one testable
relationship").

Finding shape:
`{"rq": str, "index": int|None, "kind": str, "why": str, "reframe_hint": str,
"severity": "advisory"}` — severity is always `"advisory"`.

**Why not the existing LLM-judge boundary** (`quality/rubric.py:186-202`):
deterministic-before-generative (vision `:237-239`) — these classes ARE
expressible as pure functions; the judge is best-effort/non-deterministic and
would break the offline test matrix (§8). The *semantic* layer already exists
for free: the M1 skill (an LLM mid-conversation) receives the deterministic
flags and phrases the coaching, in the student's language. A future rubric
judge dimension may deepen this (explicit non-goal, §9).

### D8 — Persistence: new M1-owned `feasibility` key

Add `"feasibility"` to `SLICE_OWNERSHIP["M1"]` (`agent/state.py:35-37`) and to
the advertised slice map in `skills/dothesis/SKILL.md:178` (sync note
`agent/state.py:22-23`; this key is agent-visible by design, like M3
`sample_plan` — unlike `decisions`/`user_context`, there is no
audit-integrity reason to hide it). The tool persists:

```json
{"sample_size": {…}, "operationalizability": {…},
 "inputs": {"k": 4, "predictors_source": "default", "method_family": null,
            "effect_size": "medium", "expected_constructs": 0, "method_hint": ""}}
```

via `store.commit_slice("M1", {"feasibility": …}, reason="topic_feasibility:
early sample-size reality check")`, best-effort (D6). Why persist: (a) M3's
`sampling_plan` can reference the early estimate (D10); (b) `read`-intent M1
queries answer from state, not recomputation
(`skills/dothesis-m1-topic/SKILL.md:22-23`); (c) the defense/limitations
surfaces read state, not transcripts (vision §5.6).

### D9 — Skill presentation: once, early, actionable, never nagging

`skills/dothesis-m1-topic/SKILL.md` changes (skills-first, vision `:253-255`):

- **Phase 4 (before "Lock this in?")**: call `topic_feasibility` exactly
  **once**, passing the construct count and method family *only if the student
  volunteered them*. Present at most two short items: (1) the reality-check
  question with `target_population` interpolated — *"A model like this
  typically needs n ≈ 155 (Kock & Hadaya, 2018). Can you realistically get
  ~160 responses from {target_population}?"* — plus one sentence noting M3
  will compute the exact figure; (2) at most the two most important
  operationalizability findings, each with its reframe hint. If the student
  acknowledges and wants to proceed anyway, **commit without further
  comment** — the estimate is already persisted for M3 to pick up.
- **Never repeat** the check in later passes unless the intent is `mutate`
  with a substantial pivot (same trigger as the existing downstream-impact
  warning, `SKILL.md:30-33`).
- One new quality-bar row: "Feasibility is advice, not a gate — never refuse
  to commit a topic over sample size or operationalizability."
- The presentation follows the defense-date model (`SKILL.md:90-96`): asked
  once, flagged warmly, never refuses.

### D10 — Consistency with the M3 computed plan (the front-loaded loop)

The vision requires M3 preflight items to "become 'here is the computed
plan'" (`2026-07-17-dothesis-vertical-agent-vision.md:126-127`); the M1
estimate is that plan's *forecast*, and the two must never contradict:

1. **Same engine, same convention**: both call `thesis_stats.run_power(…,
   "apriori", effect_size="medium", predictors=k)`
   (`agent/tools/instrument.py:226-227`). No second formula exists to drift.
2. **Same k semantics**: M1's k approximates `_max_in_degree`
   (`agent/tools/instrument.py:141-143`) from coarse signals (D2); the
   `predictors_source` provenance makes any M1↔M3 delta explainable.
3. **M3 is authoritative**: `sampling_plan` recomputes from the real
   `conceptual_model` and persists M3 `sample_plan`
   (`agent/tools/instrument.py:252-256`). Small additive change: when
   `cs.get("feasibility")` exists, `sampling_plan` appends one sentence to its
   `rationale` — *"Early M1 estimate was n ≈ {X} (assumed {k} predictors);
   this plan supersedes it."* — so the student sees continuity, not
   contradiction. The M1 message pre-commits to this: "M3 will refine this
   from your actual model."
4. **Preflight untouched**: `agent/preflight.py` still keys off M3
   `sample_plan.power_analysis` (`:32-39`); M1 feasibility never satisfies or
   suppresses a preflight item (it is a forecast, not a plan).

---

## 4. Component specification

### 4.1 `estimate_sample_size` (pure)

```python
def estimate_sample_size(m1: dict, expected_constructs: int = 0,
                         method_hint: str = "") -> dict
```

`m1` is the flat M1 slice view (`research_questions`, `research_type`,
`target_population`, `research_title`, `field` — all optional). Returns:

```json
{
  "status": "estimate" | "range" | "skipped",
  "basis": "power" | "heuristic" | "canned",
  "assumed": {
    "effect_size": "medium", "alpha": 0.05, "power": 0.80,
    "predictors": 4, "predictors_source": "student_stated|inferred_from_rqs|default",
    "method_family": "pls_sem|regression|cb_sem|null"
  },
  "estimates": [
    {"analysis": "pls_sem", "required_n": 155, "recommended_n": 155,
     "justification": "<verbatim from run_power>", "citations": ["Kock & Hadaya (2018)", "Hair, Hult, Ringle & Sarstedt (2017)"]}
  ],
  "headline_n": 155,
  "range": [85, 155],
  "message": "A model like this typically needs n ≈ 155. Can you realistically sample that from {population}? (M3 will compute the exact figure from your actual model.)",
  "skipped_reason": null
}
```

- `headline_n` = the single-family N when `status="estimate"`, else
  `max(range)`. `range` present only for `status="range"`.
- `message` interpolates `m1["target_population"]` when non-empty, else the
  literal phrase `your intended population`. English canonical; the skill
  translates (D5).
- Deterministic: same inputs → same dict (run_power is pure, `power.py:1`).
- Never raises (D6 ladder implemented inside).

### 4.2 `check_operationalizability` (pure)

```python
def check_operationalizability(research_questions: list, title: str = "",
                               research_type: str = "") -> dict
```

Returns `{"findings": [<finding>…], "testable_count": int,
"total": int}` with the finding shape of D7. Non-string list entries are
skipped defensively. Never raises.

### 4.3 `make_feasibility_tool(store)` → tool `topic_feasibility`

- Reads `cs = (store.load() or {}).get("contextStore") or {}` (flat store —
  `agent/preflight.py:88-89` precedent); builds the `m1` view from the M1-owned
  keys present at top level.
- Calls both pure functions; assembles
  `{"sample_size": …, "operationalizability": …, "advisory": true}`;
  persists per D8; returns `json.dumps(…, ensure_ascii=False)`.
- Docstring (the agent-facing contract): states it is advisory, run once
  before locking the topic, and that hint args are optional and must reflect
  what the student actually said.
- Registered in `agent/runtime.py` tools list (after
  `make_preflight_tool(store)`, `agent/runtime.py:516-518`).

---

## 5. Worked defaults (golden values, from the shipped engine)

| Scenario | Call | Result |
|---|---|---|
| 3 constructs + PLS hint | `run_power("pls_sem","apriori",effect_size="medium",predictors=2)` | required_n **155** (β=0.20, constant 2.486, `power.py:197-204`); 10×-rule cross-check 20 → recommended 155; Kock & Hadaya justification |
| Regression hint, k=3 | `run_power("regression","apriori",effect_size="medium",predictors=3)` | required_n **77** (shipped golden, `libs/thesis-stats/tests/test_power.py:12-18`) |
| No hints (default k=4) | both families | range **[reg-N(k=4), 155]**; headline 155 |
| CB-SEM hint | heuristic only | ≥200 (Kline floor, `agent/sampling.py:22`) |
| qualitative | — | skipped + note |

(The k=4 regression N is captured as a golden from the lib during Phase 1 of
the plan — do not hardcode from this doc.)

---

## 6. Degradation & failure matrix — see D6 table. Summary: power → heuristic → canned range; every row returns a well-formed payload; nothing blocks the M1 commit.

## 7. Determinism & security posture

- No LLM, no network, no RNG in `agent/feasibility.py` (imports: stdlib,
  `thesis_stats`, `agent.sampling`, `agent.method_advisor.normalize_method`).
- No new compute outside the whitelist boundary — the only statistics come
  from the already-shipped `thesis_stats.run_power` via Python import
  (vision `:226-232`; thesis-stats hard constraint "import, never HTTP").
- Tool reads state from the store, never from model-supplied state; the two
  hint args are advisory-only and persisted with provenance (D2).

## 8. Test matrix (all offline; `pytest.importorskip("thesis_stats")` where the engine is exercised, per `agent/tests/test_sampling_plan_power.py:7`)

1. 3-constructs + `method_hint="PLS-SEM"` → single estimate, `required_n=155`,
   justification contains "Kock & Hadaya".
2. `method_hint="SPSS regression"`, `expected_constructs=4` (k=3) →
   `required_n=77` (f²-based), justification cites Cohen/Faul.
3. No hints, 3 relationship-RQs → `status="range"`, k=3
   (`inferred_from_rqs`), range spans both families, headline = max.
4. `"What is the meaning of leadership?"` → one `definitional` finding,
   severity `advisory`; a relationship RQ in the same list is not flagged.
5. Normative RQ ("Should companies…") → `normative`; all-descriptive set →
   `topic_not_testable`.
6. Vietnamese RQ with `ảnh hưởng` → counted as testable (no flag);
   `… là gì?` → `definitional`.
7. `target_population="Gen Z bank customers in Hanoi"` → message contains the
   population string; missing population → "your intended population".
8. Determinism: two identical calls → identical payloads.
9. Fail-open: monkeypatched `run_power` raising → `basis="heuristic"`, valid
   payload, no exception; empty M1 slice → default-k range, no exception.
10. `research_type="qualitative"` → sample_size skipped, operationalizability
    still returned.
11. Tool test (fake `ProjectStateStore(tmp_path)`, pattern
    `agent/tests/test_sampling_plan_power.py:13-19`): persists M1
    `feasibility`; commit failure (broken store stub) still returns JSON.
12. M3 reconciliation: store with M1 `feasibility` + M3 model →
    `sampling_plan` rationale mentions the early estimate.

## 9. Non-goals (v1)

- **Headless/orchestrator M1 auto-path** — advisory checks need a student to
  advise (vision §5.4's B2B exception is about *gates*, not advice). The pure
  functions are import-ready if the orchestrator later wants them.
- **No new rubric dimension / LLM judge** for operationalizability (D7).
- **No CB-SEM power computation** — heuristic floor only, until roadmap #9
  lands CB-SEM compute.
- **No change to `agent/preflight.py` semantics** (D10.4), no change to
  `thesis_stats` (pure reuse).
- **No qualitative sample-size guidance** (saturation etc.) — vision §7.
