# Assumption-Driven Method Advisor — Design Spec

**Date:** 2026-07-17
**Status:** Design — ready for implementation (companion plan: `2026-07-17-method-advisor-plan.md`)
**Owner:** cao.nv17@gmail.com
**Roadmap:** Initiative #7 in `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:226-248` (Phase 2, "Assumption-driven method advisor"; dependencies 2 and 3 are **shipped** — `run_power` at `libs/thesis-stats/src/thesis_stats/power.py:270`, `run_screening` at `libs/thesis-stats/src/thesis_stats/screening.py:385`)
**Vision anchors:** `2026-07-17-dothesis-vertical-agent-vision.md` §3.3 (assumption-driven method selection, :114-127), §4(3) (committee-shaped quality encoding, :212-215), §5 principle 3 (deterministic before generative, :236-239), principle 4 (advisory, not blocking, :240-244), principle 8 (two-register explanations, :256-259), checklist item 3 (:271-272)
**Builds on (all shipped — nothing here re-proposes them):** `2026-07-17-thesis-stats-shared-lib-design.md`, `2026-07-17-power-analysis-design.md` (#2), `2026-07-17-data-screening-design.md` (#3), `2026-07-17-stats-self-validation-design.md` (#1)

---

## 1. Motivation

Today the analysis method is *picked*, never *checked against the data*:

- The design-test decision matrix is **skill prose** the agent consults
  (`skills/dothesis-m3-design/SKILL.md:112-115` mandates reading
  `skills/dothesis-m3-design/references/design-test-matrix.md` and "state the
  rule that applies + its citation"). Whether the LLM applies the matrix
  correctly is unverifiable — the exact failure mode principle 3 of the vision
  exists to eliminate (`...-vision.md:236-239`).
- M3 persists `methodology` as a free string, and M4 just routes to it: the
  M4 skill's only method-awareness is the metric-family consistency rule
  (`skills/dothesis-m4-analysis/SKILL.md:36-39`, `:161-163`) and the headless
  schema records `design`/`tool` as unvalidated strings
  (`orchestrator/schemas/m3.py:25-27`).
- The methods preflight checks that a method **exists**, not that it **fits**:
  `agent/preflight.py:28-29` — `"M3 — analysis method not chosen (consult the
  design-test matrix)"` is the entire method check.
- Meanwhile every assumption input the matrix needs is now **computed** by
  shipped code and then thrown away for this purpose: normality
  (`rigor.py:48-67` Shapiro-Wilk; per-item skew/kurtosis exists only inside the
  SPSS descriptives path, `spss.py:193-194`), the power-based required N
  (`power.py:270-315`, persisted at `sample_plan.power_analysis` by
  `agent/tools/instrument.py:222-236`), missingness + Little's MCAR
  (`screening.py:91-143`), model shape (`agent/tools/model_adapter.py:9-16`
  normalizes all three `conceptual_model` shapes), and item/construct counts.

Method mismatch is a thesis-killer a real advisor catches early — "you chose
CB-SEM with n = 87 and non-normal data" is exactly the sentence a committee
opens with. This initiative turns the matrix from prose into a **deterministic
decision table** over already-computed evidence: given the model and (when
uploaded) the data, rank `pls_sem` / `cb_sem` / `regression` /
`nonparametric` with a per-criterion evidence row (which assumption
passed/failed, the observed number, the citation), a plain + formal
justification sentence, explicit caveats, and a **method-vs-choice conflict
check** when M3's chosen method disagrees with the evidence.

**Advisory only.** Per vision principle 4 (`...-vision.md:240-244`) the
advisor never blocks and never auto-switches the method. Every finding it
emits is `soft`. Rationale for *no hard findings at all* (unlike the
self-validation layer): a method choice is a defensible judgment call with
legitimate committee-to-committee variance, never an arithmetic impossibility
— the "provably contradictory" bar that justified validation's one hard
exception (`...-roadmap.md:69-74`) is not reachable here. The two fabrication
boundaries and the M4 stats-validation gate
(`agent/tools/state_tools.py:105-127`) remain the only hard walls.

## 2. Scope and non-scope

**In scope**

- One engine addition: a `distribution` check (per-item skewness/kurtosis +
  severe-non-normality flags) in `libs/thesis-stats/src/thesis_stats/rigor.py`,
  wired into `run_rigor` and therefore the existing `rigor` op (§4).
- A pure decision module `agent/method_advisor.py`: model profiler (all three
  conceptual_model shapes), data profiler, the decision table, the ranking
  algorithm, justification templates, and the conflict check (§5-§7).
- A store-bound tool `method_advice` via `make_method_advisor_tool(store)`
  (the `make_preflight_tool` pattern), registered in `agent/runtime.py`,
  persisting its advice to the M3 slice (§8).
- Preflight items + rubric ride-along + defense-hint upgrade + M3/M4 skill
  sections (§9).

**Out of scope (explicitly deferred)**

- **No auto-switching, no hard findings, no gate.** The advisor cannot change
  `methodology`, cannot block `commit_slice`, and emits no `hard` severity.
- Multivariate normality proper (Mardia's coefficients) and robust-ML advice —
  deferred to initiative #9 (CB-SEM compute, `...-roadmap.md:278-286`), which
  owns the CB-SEM estimator story. v1's normality evidence is the univariate
  screen (Shapiro + severe skew/kurtosis), clearly labeled as such.
- Formative measurement *modeling*. M3 carries no construct-nature field today
  (grep-verified: "formative" appears only in the matrix prose and the M3
  skill). v1 accepts an optional per-construct nature hint and reports
  `unknown` otherwise (§6 C2) — adding a first-class M3 schema field is its
  own change and not required for the advisor to be useful.
- The headless orchestrator path. M3 auto-fill is constrained to plain
  regression **by design** (vision §2 table :57, principle 5 :245-248); the
  advisor is a chat-runtime surface. The `orchestrator/schemas/m3.py` fields
  are unchanged.
- Any LLM involvement, any network, any RNG. Every verdict is a comparison
  over computed numbers (vision principle 3).
- Weighted scoring models. Ranking is lexicographic over verdict counts (§7)
  — no tunable weights to argue about in a defense.

## 3. Placement decision (engine vs product)

The guiding line: **numbers computed from data belong to the engine; decision
rules that encode committee pedagogy belong to dothesis.**

| Option | Verdict |
|---|---|
| (a) Everything in `libs/thesis-stats` (new `advisor.py`) | Rejected. The decision thresholds are product/pedagogy — they restate `references/design-test-matrix.md`, they will iterate with skill content (vision principle 7), and fillform (the only other thesis-stats consumer) generates data and has no student to advise. Putting committee pedagogy in the shared engine couples fillform releases to dothesis coaching changes. |
| (b) Everything in dothesis (`agent/method_advisor.py`), computing skew/kurtosis inline | Rejected for the one data-computed piece. The severe-non-normality statistics are exactly the kind of committee-citable computed numbers the engine owns (`rigor.py` module docstring :1-7); they also upgrade the existing `rigor` op for every consumer (a per-item skew/kurtosis table is a standard Chapter 4 preamble), and they must work where Shapiro-Wilk is invalid (`rigor.py:62-63` skips n > 5000 — precisely when a large-n CB-SEM question arises). Engine functions are unit-tested next to the other rigor checks. |
| **(c) Split: `check_distribution` in `thesis_stats.rigor` (engine); decision core + tool in `agent/method_advisor.py` (dothesis)** | **Chosen.** Mirrors the shipped precedent exactly: `agent/sampling.py` and `agent/preflight.py` are dothesis-side pure rule modules; `thesis_stats.power`/`screening` are engine math. The decision core needs **no** engine import to run (design-time advice works even where thesis_stats is missing — the `model_adapter.py:4-6` import-light posture), and the only submodule change is one small, generally-useful check. |

## 4. Engine addition: `check_distribution` in `rigor.py`

New pure function next to `check_normality` (`rigor.py:48-67`), same
`(result, warnings)` contract:

```python
check_distribution(df, columns=None) -> tuple[dict, list[str]]
# per column: {"skewness": float, "kurtosis": float (excess),
#              "severe": bool, "n": int}
# plus "_summary": {"n_items": int, "severe_n": int, "severe_pct": float,
#                   "thresholds": {"abs_skew": 2.0, "abs_kurtosis": 7.0},
#                   "citation": "West, Finch & Curran (1995); Curran (2016)"}
```

- `severe` = `|skew| > 2 or |kurtosis| > 7` — the standard severe-univariate-
  non-normality cutoffs for ML SEM (West, Finch & Curran 1995; Curran, West &
  Finch 1996; the Curran (2016) citation is already in the screening citation
  list, `screening.py:25-26`).
- pandas `skew()`/`kurtosis()` (Fisher, excess kurtosis) — the same estimator
  the SPSS descriptives path already uses (`spss.py:193-194`), so the two
  surfaces can never disagree about an item's skewness.
- Columns default to all numeric columns; when a model is supplied to
  `run_rigor` it scopes to measurement items via the existing
  `_measurement_items` (`rigor.py:158-168`) — identical scoping to
  `normality`.
- Wire-in: `"distribution"` joins the `run_rigor` `checks` set
  (`rigor.py:191`, default-selected list) with the same skip-into-`warnings`
  posture (:173-179). The `rigor` op (`agent/tools/stats.py:248-256`) and its
  docstring/skill entry pick it up with no op-layer change beyond copy.
- Validation ride-along: `claims_from_rigor` (`validation.py:718`) gains
  `skew`/`kurtosis` claims with **soft** plausibility bounds only (|skew| > 20
  or |kurtosis| > 200 indicates a mis-parsed column, not a distribution).
  No hard rules — a skewness has no impossible finite value.

Version: `thesis_stats.__version__` `"0.4.0"` → `"0.5.0"`
(`libs/thesis-stats/src/thesis_stats/__init__.py:38`). No new dependency —
pandas/numpy only.

## 5. The advisor's inputs (consume, never recompute)

The advisor is a pure function over three profiles. Every evidence row
records its `source` so provenance survives into the persisted advice
(vision principle 2).

### 5.1 Model profile — `profile_model(conceptual_model, instrument=None) -> dict`

Pure, no engine import, tolerant of all three shapes the adapter documents
(`agent/tools/model_adapter.py:9-16`): canonical nodes/edges, legacy
constructs/paths, decomposed DV/IVs/moderator. Unlike `to_advance_model` it
must **not** require a measurement mapping (`model_adapter.py:66-72` raises
without one — design-time M3 often has item texts, not columns).

Extracted: construct count; per-construct item count (node `questions`, else
`instrument.items` grouped by construct); `single_item_constructs`;
`latent_model` (any construct with ≥ 2 items); `has_mediation` (a node with
both an inbound and an outbound edge on a directed path to the outcome);
`has_moderation` (a node typed moderator / `moderate_effect`, an edge with
`effect: "moderates"`, or a decomposition `moderator`); `max_in_degree` —
**single-sourced**: the logic currently in
`agent/tools/instrument.py:141-156` (`_max_in_degree`) moves to
`method_advisor.py` and `instrument.py` delegates to it, so the power
cross-check and the advisor can never count arrows differently;
`construct_nature` — from an optional `nature: "reflective"|"formative"`
key on nodes (new, optional, taught to M3 by the skill update §9.4), else
`"unknown"` per construct.

### 5.2 Data profile — `build_data_profile(df, items) -> dict` (only when a file exists)

Thin composition over **engine** functions (lazy import, fail-open to
`None` fields with a warning): `n_rows`; `normality` via
`thesis_stats.rigor.check_normality` (`rigor.py:48-67`); `distribution` via
the new `check_distribution` (§4); `missing_overall_pct` (direct
`df.isna()` arithmetic — trivial, not a recompute of screening);
`likert_levels` (max distinct integer values across items — ≤ 7 distinct
integers ⇒ ordinal Likert, the same inference posture as screening's
inferred bounds, `screening.py:403-408`).

Two inputs are **consumed from prior work, never recomputed**:

- **#2's power N** — read from the store:
  `sample_plan.power_analysis.recommended_n` (falling back to `required_n`),
  exactly the keys `sampling_plan` persists (`instrument.py:228-236`,
  `:249-254`). The advisor never calls `run_power`; the a-priori N is a
  design decision with its own recorded assumptions
  (`power_analysis.inputs.effect_size_label`) and recomputing it here could
  silently disagree with the persisted, committee-quoted number.
- **#3's MCAR verdict** — Little's MCAR runs an EM loop
  (`screening.py:146-184`); the M4 skill already mandates running the
  `screening` op first (`skills/dothesis-m4-analysis/SKILL.md:66-71`). The
  tool accepts an optional `mcar_p` argument that the agent copies from the
  screening report it just received (`missing.mcar.p`,
  `screening.py:141-143`); the evidence row records
  `source: "screening op (agent-passed)"`. Absent ⇒ the missingness criterion
  runs on `missing_overall_pct` alone and the MCAR-dependent note is skipped.
  (Screening output is not persisted to the context store today; passing one
  scalar from the just-run op is the honest v1 bridge — see risk #4.)

### 5.3 Choice + plan (from the store, trusted)

`methodology` (the chosen method string, flat store key —
`instrument.py:182`, `state_tools.py:260`), `sample_plan.target_n`,
`sample_plan.power_analysis` (above), `conceptual_model`, `instrument`.
Read server-side by the store-bound tool, **never** accepted from the model —
the documented F0 lesson (`instrument.py:161-166`: "models can't be trusted
to pass real state"), and doubly load-bearing here: the conflict check
compares chosen-vs-advised, so a model-supplied "chosen method" would let a
sycophantic model erase the conflict it exists to surface.

Method-string normalization reuses the keyword mapping already in
`instrument.py:216-220` / `agent/sampling.py:20-26` ("pls" → `pls_sem`;
"cb-sem"/"cbsem"/"amos"/"lavaan"/"covariance" → `cb_sem`;
"regress"/"spss" → `regression`; else `None` = unmapped, advice still
produced, conflict check skipped with a caveat).

## 6. The decision table

Candidates: `pls_sem`, `cb_sem`, `regression`, `nonparametric`. Each
criterion yields, per method, a verdict in `{favors, neutral, against,
strongly_against, unknown}` plus an evidence row `{criterion, observed,
threshold, verdicts, citation, source}`. Missing inputs ⇒ `unknown` (listed,
never counted). All thresholds carry the citation the student will be asked
for; they deliberately match `references/design-test-matrix.md` (the skill
prose stays as the narrative companion; the table below is its executable
form).

| # | Criterion | Input (source) | Rule + threshold | Verdicts | Citation |
|---|---|---|---|---|---|
| C1 | Latent measurement model | model profile | No multi-item construct ⇒ nothing to estimate a measurement model on | no-latent: `favors` regression, `against` pls_sem/cb_sem; latent: `favors` both SEM, `against`-with-note regression ("collapses constructs to composite means") | design-test-matrix.md:27-39; Hair et al. (2022) |
| C2 | Formative constructs | model profile (`nature` hints) | Any formative construct | `strongly_against` cb_sem, `favors` pls_sem; all-`unknown` nature ⇒ `unknown` + caveat "decide reflective vs formative before the estimator" | design-test-matrix.md:35, :54-57; Hair et al. (2022) |
| C3 | CB-SEM sample floor | n (data rows, else `target_n`) | n < 150 ⇒ `against` cb_sem; n < 100 ⇒ `strongly_against` ("never below ~100") | cb_sem only | Kline (2016); Hair et al. (2019); design-test-matrix.md:53-55 |
| C4 | Power adequacy | n vs `power_analysis.recommended_n`/`required_n` (store, #2) | n < required a-priori N ⇒ `against` the analysis family the N was computed for + a mandatory caveat quoting the shortfall ("n = 95 < required N = 160 (Kock & Hadaya 2018)") | analysis-specific; caveat always | Kock & Hadaya (2018); Cohen (1988) — whichever `power_analysis.citations` carries (`power.py:223-228`) |
| C5 | 10×-rule adequacy | n vs `10 × max_in_degree` | n below even the liberal 10× rule ⇒ `against` pls_sem; meets it ⇒ `favors` pls_sem (small-n defensibility) | pls_sem | Hair, Hult, Ringle & Sarstedt (2017); `agent/sampling.py:23-25` |
| C6 | Normality | data profile (§4) | `severe_pct ≥ 25%` of items (\|skew\|>2 or \|kurt\|>7) ⇒ `strongly_against` cb_sem (ML assumes multivariate normality), `favors` pls_sem (distribution-free) and `favors` nonparametric; Shapiro-fail majority but no severe items ⇒ `against` cb_sem with the "significant-but-mild at this n" note | cb_sem / pls_sem / nonparametric | Kline (2016); West, Finch & Curran (1995); Hair et al. (2022) |
| C7 | Missingness / MCAR | `missing_overall_pct` (computed) + `mcar_p` (passed, #3) | `mcar_p < .05` ⇒ note-only row: FIML favors cb_sem in principle (Enders & Bandalos 2001) **but** carries the v1 caveat verbatim from screening ("this tool applies neither in v1", `screening.py:332-335`); `missing_overall_pct > 15` ⇒ caveat on all | note/caveat only, `neutral` verdicts | Enders & Bandalos (2001); Little (1988) |
| C8 | Mediation / moderation | model profile | Present ⇒ `favors` pls_sem (bootstrap indirect/interaction ops exist: `stats.py:223-245`), `neutral` regression ("PROCESS-style bootstrap acceptable", Hayes 2018), `neutral` cb_sem | pls_sem / regression | Hayes (2018); Preacher & Hayes (2008) |
| C9 | Single-item constructs | model profile | Any single-item latent construct ⇒ `against` cb_sem (identification/reliability), pls_sem `neutral`-with-caveat | cb_sem | Hair et al. (2022); Diamantopoulos et al. (2012) |
| C10 | Scale type | data profile `likert_levels` | ≥ 5 ordered categories ⇒ note "customarily treated as approximately continuous"; < 5 ⇒ `against` cb_sem (ML on coarse ordinal) + note that categorical estimators are out of scope | cb_sem | Rhemtulla, Brosseau-Liard & Savalei (2012) |
| C11 | Research goal | optional `goal` arg (`"confirmation"` \| `"prediction"`, else unknown) | confirmation + fit indices wanted ⇒ `favors` cb_sem; prediction/theory-building ⇒ `favors` pls_sem | cb_sem / pls_sem | Kline (2016); Hair et al. (2022); design-test-matrix.md:36-39 |
| C12 | Nonparametric niche | C1 + C6 + n | `favors` nonparametric only when there is no latent model AND (severe non-normality OR n below the regression floor `50 + 8k`, Green 1991); otherwise `against` ("rarely the thesis-grade primary analysis") | nonparametric | Green (1991); design-test-matrix.md:47 |

**Design-time mode** (no data file): C6, C7, C10 report `unknown` with the
explicit line "re-run after data upload"; n comes from `target_n`. This is
the M3 surface. **Data-time mode**: n = rows of the supplied file (the skill
directs the agent to pass the `_screened.csv` when screening was applied,
`stats.py:299-304`).

## 7. Ranking, output shape, conflict check

**Ranking is lexicographic, not weighted:** sort methods by
`(count strongly_against, count against, -count favors)` ascending; ties
break by the fixed parsimony order `regression → pls_sem → cb_sem →
nonparametric` — "prefer the simplest defensible method," the M3 skill's own
parsimony rule (`skills/dothesis-m3-design/SKILL.md:64-86`). Deterministic:
same inputs ⇒ byte-identical output (dict key order fixed, floats rounded
4 dp like `stats.py:130-137`).

```json
{
  "mode": "data",                       // or "design"
  "recommendation": [
    {"method": "pls_sem", "rank": 1,
     "tally": {"favors": 4, "against": 0, "strongly_against": 0}},
    {"method": "regression", "rank": 2, "tally": {...}},
    {"method": "cb_sem", "rank": 3, "tally": {"favors": 1, "against": 1, "strongly_against": 2}},
    {"method": "nonparametric", "rank": 4, "tally": {...}}
  ],
  "evidence": [
    {"criterion": "cb_sem_sample_floor", "observed": {"n": 95},
     "threshold": "CB-SEM defensible from n ≈ 150; never below ~100",
     "verdicts": {"cb_sem": "strongly_against"},
     "citation": "Kline (2016); Hair et al. (2019)",
     "source": "rows of survey_screened.csv"},
    {"criterion": "normality", "observed": {"severe_pct": 43.8, "severe_n": 7, "n_items": 16},
     "threshold": "|skew| > 2 or |kurtosis| > 7 on ≥ 25% of items",
     "verdicts": {"cb_sem": "strongly_against", "pls_sem": "favors", "nonparametric": "favors"},
     "citation": "Kline (2016); West, Finch & Curran (1995)",
     "source": "computed: thesis_stats.rigor.check_distribution"}
  ],
  "unknown": ["construct_nature", "research_goal"],
  "justification": {
    "plain": "Your data is strongly skewed and you have 95 answers — PLS-SEM stays defensible here; CB-SEM would need roughly 150+ and near-normal data.",
    "formal": "Given n = 95 (below the CB-SEM convention of n ≥ 150; Kline, 2016) and severe univariate non-normality on 7 of 16 items (|skew| > 2 or |kurtosis| > 7; West, Finch & Curran, 1995), PLS-SEM is the defensible estimator: it is distribution-free and its inverse-square-root sample requirement is met (Kock & Hadaya, 2018; Hair et al., 2022)."
  },
  "caveats": ["n = 95 is below the a-priori power-based N = 160 — disclose in limitations (source: sample_plan.power_analysis).",
              "Construct nature (reflective/formative) not declared — confirm before finalizing the estimator."],
  "conflict_with_choice": {
    "chosen": "cb_sem", "chosen_raw": "CB-SEM (AMOS)", "advised": "pls_sem",
    "reasons": ["cb_sem_sample_floor", "normality"],
    "sentence": "M3 chose CB-SEM, but n = 95 (< 100 floor) and severe non-normality on 7/16 items make it indefensible as specified; PLS-SEM is the evidence-backed alternative — or collect to n ≥ 150 and re-check."
  },                                     // null when chosen ∈ top rank or is un-mapped
  "inputs_fingerprint": "sha1:…",        // over (methodology, conceptual_model, target_n, mode, file row count)
  "citations": ["Hair et al. (2022)", "Kline (2016)", "Kock & Hadaya (2018)", "..."],
  "method": "deterministic decision table v1 (no LLM)"
}
```

- The **justification pair** is deterministic templating per
  (top method × firing criteria), exactly the `power.py:237-265` `_justify`
  pattern; the two registers implement vision principle 8. The formal
  sentence is the one the student pastes into the methodology chapter — the
  roadmap's promised deliverable (`...-roadmap.md:238-240`).
- **`conflict_with_choice`** is non-null iff the normalized chosen method is
  mapped (§5.3) and is not rank 1 **and** at least one `against`/
  `strongly_against` row targets it. Chosen method rank 1 or merely tied ⇒
  null (no noise when the choice is fine). This is the "soft finding for the
  preflight/rubric surface" — severity `soft` everywhere, matching the
  preflight finding shape (`quality/rubric.py:125-126`).
- **`inputs_fingerprint`** guards staleness: preflight (§9.2) only reports a
  persisted conflict whose fingerprint still matches the current store, so
  editing the model or the method after an advisory run silently retires the
  old finding instead of nagging about it.

## 8. Surface decision: store-bound tool, not a `run_stats` op

| Option | Verdict |
|---|---|
| (a) New `run_stats` op `method_advice` | Rejected. `run_stats` ops are store-blind by design (file + model-passed params, `stats.py:386-424`); the advisor's core inputs — the *chosen* method, the persisted power N — are store state, and the conflict check is only trustworthy if those are read server-side (§5.3). Passing them as params re-opens the exact hole the F0 correction closed (`instrument.py:161-166`). |
| (b) Fold into the `rigor` op | Rejected for the same reason `power` wasn't folded (`2026-07-17-power-analysis-design.md` §3 option b): `run_rigor` runs **on a data file** (`rigor.py:173`), but design-time advice is data-free and is the *primary* M3 consumer; and rigor cannot see the store either. The engine piece that *does* belong in rigor (distribution stats) goes there (§4). |
| **(c) Store-bound tool factory `make_method_advisor_tool(store)`** | **Chosen** — and prescribed by the roadmap itself ("tool factory bound to the store (the `make_preflight_tool` pattern in `agent/preflight.py`)", `...-roadmap.md:243-245`). One tool serves both moments: no `file` ⇒ design-time advice from the store; `file` given ⇒ data-time advice. |

Concretely, in `agent/method_advisor.py` (decision core + factory in one
module, mirroring `agent/preflight.py:18-70`):

```python
@tool
def method_advice(file: str = "", measurement: dict | None = None,
                  mcar_p: float | None = None, goal: str | None = None) -> str
```

- Reads the live flat contextStore (`store.load()["contextStore"]`, the
  `preflight.py:66-67` pattern; accepts the nested `m3_design` wrapper the
  same way `preflight_check` does, `preflight.py:20-24`).
- `file` optional; when given, loads via the same reader posture as
  `stats.py:21-32` and builds the data profile (§5.2) over the measurement
  items (`measurement` mapping, else instrument item columns present in the
  df, else numeric columns — the screening fallback, `screening.py:396-400`).
- Calls the pure `advise_method(...)`; **persists** the advice via
  `commit_slice("M3", {"method_advice": payload}, reason=...)` — best-effort,
  fail-open, exactly the `sampling_plan` persistence posture
  (`instrument.py:249-254`); a method-fit assessment *is* a design artifact,
  and persisting it is what lets preflight and the rubric see the conflict.
- Registered in the runtime tool list next to its siblings
  (`agent/runtime.py:518` preflight, `:527` sampling_plan).
- Fail-open everywhere: thesis_stats missing ⇒ data profile degrades to
  `None` + warning, design-mode advice still returns (the decision core has
  no engine dependency, §3c); store write failure ⇒ advice still returned
  (`instrument.py:249-254` comment).

**Sandbox note:** in production the run_stats ops are slated for the
network-less sandbox (`stats.py:1-8`); this tool computes its data profile
in-process via vetted engine functions (Shapiro + skew/kurtosis + isna — no
model-authored code, so the whitelist principle holds: the model still only
picks a tool and parameters). If/when the sandbox split lands, the data
profile is one isolated function (`build_data_profile`) whose numbers are
also obtainable from `run_stats(op="rigor", checks=["normality",
"distribution"])` — transport can move without touching the decision core.
Recorded as risk #3.

## 9. Product integration (advisory, never blocking)

### 9.1 M3 — the planning surface

`skills/dothesis-m3-design/SKILL.md` §3c (:99-127): after the
design × instrument × analysis pick, the skill now instructs: **call
`method_advice` (no file) and quote its formal justification sentence**; the
matrix consultation rule (:112-115) becomes "consult the tool first; use
`references/design-test-matrix.md` for the narrative and the worked
examples." When the tool returns a conflict or ranks the student's preference
below an alternative, present the trade-off (the skill's own rule: "Do not
pick the methodology for the user without showing tradeoffs", :155) — never
override.

### 9.2 Preflight — two new advisory items

`agent/preflight.py:18-42` (`preflight_check`) gains, mirroring the power
initiative's upgrade shape (`2026-07-17-power-analysis-design.md` §8.2):

- `methodology` present but no `method_advice` in the store →
  `"Method choice not advisor-checked — run method_advice for a citable
  method-fit justification."`
- `method_advice.conflict_with_choice` non-null **and**
  `inputs_fingerprint` matches the current store →
  `"Chosen method (CB-SEM) conflicts with the assumption advisor
  (recommends PLS-SEM): n = 95 < 100 floor; severe non-normality."`
  (first-reason summary; the full evidence stays in the store).

`preflight_check` stays pure and advisory (module docstring contract,
`preflight.py:1-14`); the fingerprint comparison is a pure hash of store
values — no data access from preflight.

### 9.3 Rubric — rides along for free

`quality/rubric.py:111-128` (`preflight_dimension`, weight 0.10, −0.15 per
item) reuses the same `preflight_check`, so an unadvised or
conflict-carrying design lowers the design-readiness score with **zero
rubric code changes** — the roadmap's "rubric criterion (method-choice
justified)" (`...-roadmap.md:245-246`) and checklist item 3
(`...-vision.md:271-272`, "decision-matrix trace") land through the existing
dimension. One test asserts the ride-along (plan Phase 4), the same proof
obligation the power spec set (its §8.3).

### 9.4 M4 — the data-contradicts-the-plan surface

`skills/dothesis-m4-analysis/SKILL.md` pipeline (:92-103): after step 0
(preflight) and the mandatory `screening` run (:66-71), insert **step 1.5 —
re-run `method_advice(file=<current file>, mcar_p=<from the screening
report>)`.** If `conflict_with_choice` is non-null: surface it in both
registers, offer the ready-made methodology sentence, and let the student
decide — loop back to M3 to change the method (an M3 commit, which
auto-flags M4) or proceed with the caveat recorded for the limitations
section. Never refuse to run the chosen analysis (the preflight section's
posture, :79-93). The metric-family rule (:36-39) is unchanged and
orthogonal.

### 9.5 Defense — a computed model answer

`agent/tools/defense.py` (`_state_weakpoints`): when `method_advice` exists,
the "why this method?" staple's `model_answer_hint` quotes the formal
justification sentence; when a current-fingerprint conflict exists, the drill
gains the examiner attack "your data violates your method's assumptions —
respond" with the evidence rows as the cheat-sheet. Pure change, heuristic
fallback unchanged — the `sample_plan.power_analysis` hint upgrade pattern
(`2026-07-17-power-analysis-design.md` §8.4).

## 10. Testing strategy

All offline, all deterministic (fixtures generated in-test with
`numpy.random.default_rng(42)`, written to `tmp_path` CSVs — no network, no
checked-in binaries).

### 10.1 Engine (`libs/thesis-stats/tests/test_rigor.py` extension)

- `check_distribution` known values: `rng.exponential` column ⇒ skew > 2,
  `severe: true`; `rng.normal` ⇒ |skew| < 1, `severe: false`; constant
  column ⇒ skipped into warnings; `_summary.severe_pct` arithmetic; scoping
  via model measurement items matches `check_normality`'s.
- `run_rigor(checks=["distribution"])` wiring; default `checks=None` now
  includes it; warnings posture on inapplicable input.
- Validation: skew/kurtosis claims are soft-bounded only; golden-clean rigor
  output ⇒ zero findings (extends the `test_validation_golden.py` pattern).

### 10.2 Decision core (`agent/tests/test_method_advisor.py`)

Seeded fixture recipes (each asserts the **full ranked order and the exact
evidence rows** — criterion ids, verdicts, observed numbers):

| Fixture | Recipe | Asserted outcome |
|---|---|---|
| `normal_adequate` | n = 300, 4 constructs × 4 items, MVN → Likert 1-7 | `cb_sem` carries zero `strongly_against`; with `goal="confirmation"` cb_sem rank 1; `conflict_with_choice` null when chosen = CB-SEM |
| `skewed_small` | n = 95, exponential → Likert 1-5, most items \|skew\| > 2 | `pls_sem` rank 1; cb_sem rows C3 (`strongly_against`, n < 100) + C6 (`strongly_against`, severe_pct) present with observed numbers; chosen = "CB-SEM (AMOS)" ⇒ conflict non-null, `reasons == ["cb_sem_sample_floor", "normality"]`, sentence mentions both |
| `mediation_shape` | nodes/edges with X→M→Y (+ the same as decomposition + legacy shapes) | C8 row present; all three conceptual_model shapes produce the **identical** profile and advice |
| `no_latent` | single-item constructs only, n = 200 | `regression` rank 1; C1 row `against` both SEM |
| `design_mode` | no file; store `target_n = 80`, `power_analysis.required_n = 160` | mode `"design"`; C6/C7/C10 in `unknown`; C4 caveat quotes 80 < 160 **verbatim from the store value** (proves no recompute — monkeypatch `thesis_stats.run_power` to raise, advice unaffected) |

Plus: determinism (two calls, byte-identical JSON); every payload
`json.dumps`-serializable; ranking tie-break order; fingerprint changes when
methodology/model/target_n change and only then; unmapped methodology string
⇒ no conflict + caveat; `mcar_p=0.01` ⇒ C7 note present with the v1
FIML caveat text.

### 10.3 Tool + integration (`agent/tests/`)

Store-bound tool with the temp-store pattern (`test_sampling_plan_power.py`
precedent): persistence shape under `method_advice`; fail-open on store
write failure and on missing thesis_stats (design mode still answers);
`file` given ⇒ data-mode advice + n from rows. Preflight: both new items,
both store shapes (flat + nested, `preflight.py:20-24`), stale-fingerprint
conflict suppressed. Rubric: an un-advised store scores lower on the
`preflight` dimension than an advised one; a conflicted store lower still —
zero rubric code changed. Defense: hint quotes the formal sentence.

## 11. Risks

1. **Threshold literature variance** — CB-SEM minimums are quoted anywhere
   from 100 to 200; a committee may hold a different line than C3. Mitigated:
   every evidence row carries its citation, the two-tier threshold (against
   at 150 / strongly_against at 100) matches the matrix the product already
   teaches (`design-test-matrix.md:53-55`), and everything is soft/advisory —
   the student can defend a different judgment with the same table.
2. **Advice read as verdict.** The output is a *ranking*, and rank 1 will be
   treated as gospel by anxious students. Mitigated: `conflict_with_choice`
   is null whenever the chosen method is defensible (top rank — §7), the
   skill language presents trade-offs (§9.1, M3 skill :155), and design-mode
   output explicitly lists what is `unknown` until data arrives.
3. **Sandbox divergence** — the tool computes the data profile in-process
   while run_stats ops may move to the sandbox service (§8 note). Mitigated:
   `build_data_profile` is one isolated function whose statistics are also
   exposed via the `rigor` op; migration moves transport, not rules.
4. **Agent-passed `mcar_p` is tamperable/mistypable.** Impact is bounded — it
   only shades the C7 *note* (neutral verdicts, no ranking effect §6), and
   the evidence row labels the source as agent-passed. Durable fix (persist
   the screening report to the store) belongs to the coherence/state
   initiative, not here.
5. **Stale persisted advice after M3 edits.** Mitigated by
   `inputs_fingerprint` (§7): preflight and defense only surface a conflict
   whose fingerprint matches the current store; the M4 skill re-runs the tool
   on the current file anyway.
6. **`nature` hint adoption** — C2 stays `unknown` for existing projects
   (no schema migration). Accepted: the caveat line keeps the
   reflective/formative question visible, which is strictly better than
   today's prose-only treatment; a first-class schema field can follow once
   #9 (CB-SEM compute) forces the issue.
