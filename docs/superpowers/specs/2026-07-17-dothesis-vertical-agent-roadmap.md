# DoThesis — Vertical-Agent Roadmap (post-thesis-stats)

**Date:** 2026-07-17
**Status:** Prioritized roadmap — each initiative is scoped to become its own spec
**Owner:** cao.nv17@gmail.com
**Companion:** `2026-07-17-dothesis-vertical-agent-vision.md` (end-state + principles)
**Baseline:** `thesis-stats` shared library is SHIPPED (`libs/thesis-stats` submodule;
`agent/tools/stats.py` ops `pls_sem`/`efa`/`regression_full`/`mediation`/`moderation`/`rigor`;
`agent/tools/model_adapter.py`). Nothing below re-proposes it; initiatives marked
**[extends thesis-stats]** build directly on that compute layer.

---

## Prioritization model

Rank = impact on "committee-ready quantitative thesis" × feasibility given what
exists. Two structural facts drive the ordering:

1. **The compute layer exists.** Adding a statistical capability is now "add a
   pure function to `libs/thesis-stats`, whitelist an op in
   `agent/tools/stats.py`, teach the M4 skill" — days, not weeks. Initiatives
   that ride this rail are cheap and high-impact.
2. **Trust compounds.** The differentiators are the verified-numbers and
   verified-sources chains (vision §4). Initiatives that harden a chain
   (validation, coherence, provenance) outrank initiatives that widen surface
   area (new methods, new UX), because one published wrong number costs more
   trust than ten missing features.

| # | Initiative | Impact | Feasibility | Phase |
|---|---|---|---|---|
| 1 | Stats self-validation layer | Critical (trust) | High — pure functions at tool boundary | Near |
| 2 | Power-analysis ops | Critical (committee ritual) | High — closed-form + `statsmodels` | Near |
| 3 | Data screening & prep ops + auto cleaning section | High | High — rigor-family ops | Near |
| 4 | Provider-agnostic vision | Medium (unblocks routing) | High — small refactor | Near |
| 5 | DOI verification → rubric dimension | Medium | High — wiring, engine code exists | Near |
| 6 | Hypothesis registry + cross-chapter coherence gate | Critical (trust) | Medium — schema + deterministic checks + bounded LLM | Mid |
| 7 | Assumption-driven method advisor | High | Medium — deterministic matrix over rigor/power outputs | Mid |
| 8 | PLS-SEM completeness: Q², MGA/MICOM, IPMA | High | Medium — extends `pls_engine.py` | Mid |
| 9 | CB-SEM compute (semopy) | Medium-High | Medium — new engine module | Mid |
| 10 | Rubric-grounded viva simulation | High (retention/referral) | Medium — depends on 1+6 | Mid |
| 11 | Similarity & quote-hygiene self-check | Medium | Medium — n-gram/fingerprint, no external index | Mid |
| 12 | Committee-readiness certificate (evidence ledger) | High (B2B moat) | Lower — spans all layers | Long |
| 13 | Instrument intelligence (scale provenance + attention checks) | Medium | Medium | Long |
| 14 | Auto-mode method upgrade (full pipeline beyond plain regression) | High (B2B) | Lower — gated on 1,2,3,6 | Long |

---

## Phase 1 — Near term: harden the numbers chain (next ~6 weeks)

### 1. Stats self-validation layer — **THE #1 NEXT INITIATIVE** [extends thesis-stats]

**Problem.** `run_stats` now computes real numbers, but nothing *checks* them
before the agent narrates or persists them. A numerical edge case (degenerate
bootstrap, collinear indicators producing AVE inconsistent with loadings, an
R² outside [0,1] from a pathological fit) or a mis-parsed SmartPLS upload
(`orchestrator/tools/m4_parsers/`, vision OCR in `agent/tools/output_parse.py`)
flows straight into `analysis_results` and then into Chapter 4. The rubric's
`results_validity_dimension` (`quality/rubric.py`) is regex presence-matching —
it can't catch a wrong value.

**Outcome.** A deterministic verifier — `thesis_stats.validate_result(kind,
payload)` — runs at the tool boundary on **every** `run_stats` return and every
parsed upload before the agent may use the numbers. Checks (all pure
arithmetic/comparison, no LLM): bounds (R², loadings, α, AVE, VIF, HTMT within
mathematically possible ranges), internal consistency (AVE ≈ mean of squared
loadings per construct; CR consistent with loadings; |t| ↔ p agreement at the
stated df; bootstrap CI contains the point estimate; Fornell-Larcker diagonal
= √AVE), and cross-table consistency (n identical across tables from the same
run). Violations return typed findings (`hard` = impossible, `soft` =
suspicious) attached to the result; `hard` findings block the commit of that
result to `analysis_results` — the one justified exception to
advisory-not-blocking, because an impossible number is a fabrication with
extra steps. Upgrades the core guarantee from "no invented statistics" to
**"no incorrect statistics."**

**Rough scope.** New `validation.py` in `libs/thesis-stats` (pure, ~unit-tested
per check); call it in `agent/tools/stats.py:run_stats` on op results and in
the M4 parse path; a `stats_validity` rubric dimension in `quality/rubric.py`
that re-runs the verifier over persisted `analysis_results`; M4 skill section
on narrating a validation finding. No new tool — it rides existing surfaces.

**Dependencies.** None. **Advances:** vision §3.5(1), §4(1), checklist item 7.

**Why #1:** it is the highest trust-per-engineering-hour in the backlog — pure
functions, no new infra, direct extension of what just shipped, and it
converts the just-built compute layer from "we calculate" into "we certify,"
which is the claim no competitor can copy with prompting. Initiatives 6, 10,
and 12 all consume its findings.

### 2. Power-analysis ops (a-priori + post-hoc) [extends thesis-stats]

**Problem.** Every committee asks "why n=214?" — the G*Power ritual. DoThesis
has nothing: `agent/preflight.py` only checks that a `sample_plan.target_n`
exists, and `rigor.py` has effect sizes but no power (grep-verified). The
mock committee even asks the power question (`agent/tools/defense.py` small-n
heuristic) without being able to help answer it.

**Outcome.** `run_stats(op="power")`: a-priori mode (given effect size f²,
α, power, #predictors → required n; regression/SEM 10×-rule and
inverse-square-root cross-checks) and post-hoc mode (given achieved n and
observed f² from a `pls_sem`/`regression_full` run → achieved power).
M3 uses a-priori during sample planning (upgrading the preflight item from
"plan exists?" to a computed plan); M4/M5 use post-hoc for the limitations
section; the coherence between planned and achieved lands in the rubric.

**Rough scope.** `power.py` in `libs/thesis-stats` (statsmodels
`FTestPowerAnalysis`/closed-form; keep it dependency-light), whitelist op,
M3 + M4 skill updates, preflight upgrade, one rubric criterion.

**Dependencies.** None (pairs naturally with 1). **Advances:** §3.3, §3.5(2),
checklist item 4.

### 3. Data screening & preparation ops + auto-generated cleaning section [extends thesis-stats]

**Problem.** Real survey data arrives dirty; committees expect a screening
narrative. Today the compute layer starts at the measurement model:
no Little's MCAR test, no imputation, no Mahalanobis outliers, no
straight-lining/careless-response detection, no reverse-coding application
(grep-verified absent from `rigor.py`). Preflight asks whether *plans* exist
(`agent/preflight.py`) but nothing executes them. `check_thresholds` can only
*suspect* straight-lining after the fact (all-loadings>0.9 heuristic in
`agent/tools/stats.py`).

**Outcome.** `run_stats(op="screen")` returning a full screening report:
missingness by item + Little's MCAR + recommended treatment (listwise / mean /
EM) with the treatment *applied* to a derived working file; Mahalanobis D²
outliers (χ² p<.001); straight-lining (per-respondent SD/longest-run) and
speeding proxies; reverse-coded items re-scored per the M3 instrument flags.
Every downstream op runs on the cleaned derivative with the screening
provenance attached. M5 renders a **defensible data-cleaning section** from the
report — every number computed, none narrated from memory.

**Rough scope.** `screening.py` in `libs/thesis-stats`; op + derived-file
handling in `agent/tools/stats.py` (workspace-local, sandbox-safe); M4 skill
step "0.5 — screen before you model"; M5 renderer for the cleaning section;
rubric criterion (screening present when a dataset exists).

**Dependencies.** 1 (screening outputs go through the verifier). **Advances:**
§3.4, checklist item 5.

### 4. Provider-agnostic vision for results screenshots

**Problem.** Screenshot ingestion of SPSS/SmartPLS output is hardwired to
Gemini: `agent/tools/output_parse.py` builds the vision message with
`provider="gemini"` and routes to the Gemini factory, and `agent/multimodal.py`
treats a Gemini vision sidecar as the fallback for non-vision brains. With
Claude set (`ANTHROPIC_API_KEY` switches the brain — `docs/ARCHITECTURE.md`)
or any future routed model, the screenshot path either degrades or silently
depends on a second provider's key.

**Outcome.** Vision parsing goes through the same capability dispatch as chat
attachments: `build_user_message(..., provider=detect_provider(spec),
supports_vision=...)` with per-provider block shapes (already implemented for
gemini/openai/anthropic in `multimodal.py`) and an explicit, configurable
vision-model spec for the sidecar case. Same `{table_kind, rows,
needs_confirmation}` contract; low-confidence still requires student
confirmation (M4 skill F13 rule).

**Rough scope.** Refactor `output_parse.py` to take a ModelSpec; config for
the vision sidecar; provider-matrix tests with recorded fixtures. Small,
contained.

**Dependencies.** None. **Advances:** §3.5 ingestion robustness; unblocks the
provider-routing work (`2026-07-08-provider-routing-fallback-design.md`).

### 5. Wire DOI/metadata verification into the quality rubric

**Problem.** The engine verifies sources at ingestion
(`engine/utils/api_citations/` — CrossRef et al.), but the rubric's citation
dimension (`quality/rubric.py:deterministic_dimensions`) only checks that
in-text citations match the reference pool. A source that entered the pool
by student paste/import, or whose metadata drifted, is never re-verified;
the final gate attests less than the ingestion path guarantees.

**Outcome.** A `source_verification` rubric dimension: every
`literature_sources` entry re-checked (DOI resolves; title/author/year match
the registrar within tolerance; unverifiable entries flagged with a fix
suggestion). Cached + rate-limited so the gate stays cheap; findings feed the
defense drill ("two of your sources could not be verified — expect the
question").

**Rough scope.** Reuse engine verification clients from `quality/` (lazy
import per the rubric's existing pattern); verification-status field on
pool entries; rubric dimension + tests with recorded API fixtures.

**Dependencies.** None. **Advances:** §4(2), checklist item 2.

---

## Phase 2 — Mid term: the coherence gate and full method coverage (quarter horizon)

### 6. Hypothesis registry + cross-chapter coherence gate

**Problem.** The thesis's spine — hypotheses — has no first-class
representation that survives across modules. M3 commits `hypotheses`, M4
commits `analysis_results` with per-hypothesis entries (M4 skill mandates
`hypothesis_tests[].decision`), M5 writes prose — but nothing verifies they
agree. A discussion chapter can claim H2 was supported when M4 said otherwise,
or quote β=.34 where the table says .31, and today's gate
(`quality/rubric.py`) cannot see it: `results_validity_dimension` is keyword
regex over flattened text.

**Outcome.** (a) A **hypothesis registry** schema: each hypothesis carries id,
constructs, direction, source gap (M2), planned test (M3), result entry id +
decision (M4), and discussion anchor (M5) — enforced at `commit_slice`
validation for the owning slices. (b) A **coherence dimension** in the rubric:
deterministic checks first (every hypothesis has a decision; every statistic
quoted in prose string-matches a persisted `analysis_results` value; direction
words in the discussion agree with the sign of the persisted β; metric family
consistent with M3's tool), then a bounded LLM-judge pass for semantic
agreement (does the discussion paragraph actually discuss the found result?)
with findings quoting exact prose. Replaces pattern-matching with
state-vs-prose reconciliation.

**Rough scope.** Registry schema + `orchestrator/schemas` validation + skill
updates (M3/M4/M5 reference the registry ids they already informally use:
`H1`, `r-H1`); number-extraction + reconciliation module in `quality/`;
rubric dimension; needs_review propagation already exists
(`commit_slice` DAG) and lights up when a registry link breaks.

**Dependencies.** 1 (validated numbers are the reconciliation baseline).
**Advances:** §3.8(a), §4(1) end-to-end chain, checklist items 1, 7, 8.
This is the Phase-2 anchor: after it, the gate certifies the *thesis*, not
just its parts.

### 7. Assumption-driven method advisor

**Problem.** The design-test decision matrix is skill *content* (F8) — the
agent consults prose. Whether the chosen method actually fits the student's
data is never computed, and method mismatch is a thesis-killer a real advisor
catches early.

**Outcome.** A deterministic `recommend_method` check: inputs = conceptual
model shape (`agent/tools/model_adapter.py` already normalizes three shapes),
planned/actual n (power op #2), construct nature, and — once data exists —
`rigor`/`screen` outputs (normality, sample adequacy). Output = ranked
methods with citable justifications and explicit mismatch flags, surfaced in
M3 (planning), re-run automatically in M4 preflight when the data contradicts
the plan ("data is non-normal with n=95: PLS-SEM remains defensible; CB-SEM
is not — here's the sentence for your methodology chapter"). Advisory, per
principle 4.

**Rough scope.** Pure decision module (in `agent/` or `libs/thesis-stats`),
tool factory bound to the store (the `make_preflight_tool` pattern in
`agent/preflight.py`), M3/M4 skill integration, rubric criterion
(method-choice justified).

**Dependencies.** 2, 3. **Advances:** §3.3, checklist item 3.

### 8. PLS-SEM completeness: Q² (blindfolding), MGA + measurement invariance (MICOM), IPMA [extends thesis-stats]

**Problem.** The M4 skill already tells students PLS-SEM reporting includes
Q² (`skills/dothesis-m4-analysis/SKILL.md` metric-family rule and the sample
`structural_model.q2` block) — but the engine cannot compute it
(grep-verified: no blindfolding, no MGA/invariance, no IPMA in
`libs/thesis-stats`). Vietnamese/ASEAN business faculties routinely require
Q², and any thesis comparing groups (gender, region, cohort) needs
MGA with MICOM to be defensible. IPMA is the standard "practical
implications" figure.

**Outcome.** Three op extensions on the existing engine
(`libs/thesis-stats/src/thesis_stats/pls_engine.py` / `smartpls.py`):
`pls_sem` gains Q² via blindfolding/PLSpredict-style omission; new `mga` op
(permutation-based group comparison + MICOM invariance ladder, refusing
soft-ly to compare paths when invariance fails); new `ipma` op
(importance-performance matrix from total effects + rescaled scores, feeding
an M5 chart + implications section).

**Rough scope.** Engine work in the submodule (with golden-value tests
against SmartPLS reference outputs, the pattern
`orchestrator/tools/m4_parsers/golden` already uses); three whitelist entries
+ summarizers in `agent/tools/stats.py`; M4 skill sections; validator (#1)
rules for the new tables.

**Dependencies.** 1 (new outputs get validation rules). **Advances:** §3.5(3),
the "unbeatable on PLS-SEM" position.

### 9. CB-SEM compute (semopy): CFA + fit indices [extends thesis-stats]

**Problem.** CB-SEM students can only *paste* results
(`orchestrator/tools/m4_parsers/lavaan.py` parses; nothing computes) — the
compute-vs-parse gap survives for exactly the CFI/TLI/RMSEA/SRMR family the
skill's consistency rule names. Half the method market is parse-only.

**Outcome.** `run_stats(op="cb_sem")`: CFA measurement model + structural
model via `semopy` (pure-Python, sandbox-compatible — no R bridge), returning
loadings, χ²/df, CFI, TLI, RMSEA, SRMR, path estimates, modification-index
highlights, driven by the same `model_adapter` output. Family-consistency
enforcement stays: a project whose M3 tool is CB-SEM gets this op and never
mixes in PLS metrics.

**Rough scope.** `cbsem.py` module in the submodule wrapping semopy with the
AdvanceModel adapter; golden tests vs lavaan reference outputs; whitelist op +
skill; validator rules (fit-index bounds).

**Dependencies.** 1; independent of 8. **Advances:** §3.5(3), method breadth.

### 10. Rubric-grounded viva simulation

**Problem.** The mock committee is heuristic: `agent/tools/defense.py`
generates from two state signals (n<200, "not support" substring) plus
always-on staples, and folds in rubric findings only when passed. It cannot
yet attack what a real examiner attacks, because until 1/5/6 the gate itself
doesn't see threshold breaches, unverified sources, or incoherent chapters.

**Outcome.** The drill consumes the full enriched gate: every hard/soft
finding (validation breaches, power shortfall, screening anomalies, coherence
mismatches, unverifiable sources) becomes a targeted question with a
model-answer rubric; the interactive drill grades student answers against
those criteria and iterates until pass; output includes the per-weakness
citable cheat-sheet and an opt-in feed of disclosed weaknesses into M5
limitations (closing the `2026-07-08-mock-committee-design.md` "preempt in
the thesis" goal). Difficulty calibrated to the degree level from M1 state.

**Rough scope.** Extend `committee_questions` mapping (finding-type →
question template + answer rubric); drill-state in the defense skill
(`skills/dothesis-defense/SKILL.md`, currently 66 lines); grading via bounded
LLM-judge with the deterministic answer criteria; roadmap-card surfacing
after M5 (already the designed trigger).

**Dependencies.** 1, 5, 6 (question fuel). **Advances:** §3.7, checklist
item 10, and the referral loop.

### 11. Similarity & quote-hygiene self-check

**Problem.** No plagiarism/similarity capability exists anywhere
(grep-verified across `agent/`, `quality/`, `orchestrator/`, `skills/`).
Students get their first similarity signal from Turnitin — after submission.
LLM-drafted prose also risks verbatim overlap with the abstracts the agent
read in M2.

**Outcome.** A self-check dimension (not a Turnitin replacement — vision §7):
n-gram fingerprint overlap between draft chapters and (a) the project's own
source abstracts/quotes held in `literature_sources`, (b) intra-thesis
duplication (chapters copying each other); verbatim-span detection with
quote/citation hygiene fixes ("this 27-word span matches Nguyen 2023's
abstract — quote it or rewrite"). Runs locally, deterministic, findings in
the rubric + a pre-export report.

**Rough scope.** Fingerprinting module in `quality/` (shingling + winnowing;
no external service); rubric dimension; M5 skill guidance on paraphrase
hygiene; export-time report in the run drawer.

**Dependencies.** None hard; richer after 6 (shared prose-extraction).
**Advances:** §3.8(c), checklist item 9.

---

## Phase 3 — Long term: certification, instrument depth, B2B scale

### 12. Committee-readiness certificate (the evidence ledger)

**Problem.** Trust artifacts today are internal (rubric JSON, tool logs). A
student, advisor, or B2B partner cannot *see* the chain that makes a DoThesis
thesis different from ChatGPT output.

**Outcome.** Every export ships with a machine-checkable appendix + shareable
report: per-source verification status, per-number provenance (op, dataset
hash, timestamp, validation pass), power computation, screening summary,
coherence attestation, similarity result — the vision-§6 checklist rendered
with evidence. For B2B this *is* the product: a deterministic, auditable
guarantee per generated report. Doubles as the marketing surface ("verified
by DoThesis" page).

**Rough scope.** Provenance capture at the `run_stats`/`commit_slice`
boundary (append-only ledger rows per project); report renderer in the
export path (`engine/utils/export_professional.py` + a web view); gate
summary API for B2B callers.

**Dependencies.** 1, 2, 3, 5, 6, 11 — it is the capstone over the chains.
**Advances:** §4(1)(2), §5(2), B2B determinism principle.

### 13. Instrument intelligence: scale provenance, attention checks, translation hygiene

**Problem.** M3's instrument step builds questionnaires but doesn't encode
psychometric provenance: no adapted-from citation per construct scale, no
generated attention-check items, no back-translation guidance for the
Vietnamese-English scale round-trip most local theses need. Preflight flags
missing reverse-coding but can't propose it.

**Outcome.** Instrument items carry per-construct scale provenance (source
paper via the verified pool — reusing the citations chain); the builder
proposes reverse-coded variants and attention checks (wired to screening #3,
which then actually *uses* them); a content-validity pass checks item↔construct
alignment; M5's methodology chapter renders the instrument narrative
(adapted-from table) automatically.

**Rough scope.** Instrument schema extension (`agent/tools/instrument.py` +
M3 skill); scale-suggestion flow grounded in M2 sources; screening hook;
methodology renderer.

**Dependencies.** 3 (attention-check consumption), 5 (provenance
verification). **Advances:** §3.4, checklist items 3, 5.

### 14. Auto-mode method upgrade: full quantitative pipeline unattended

**Problem.** Auto-approve constrains M3 to plain multiple linear regression
for analysability (`AGENTS.md` invariant; `orchestrator/tools/m3_design.py`
auto_fill_directive) — correct when the pipeline couldn't verify richer
output, but it caps B2B value at the simplest design.

**Outcome.** With the verifier (1), screening (3), coherence gate (6), and
per-family compute (8/9) in place, the orchestrator graph runs the full
appropriate method for the uploaded data (PLS-SEM with Q²/MGA where the model
warrants) and *treats gate failures as blocking* — the B2B-mode exception the
vision's principle 4 reserves. Deterministic seeds for bootstrap/permutation
ops so a re-run reproduces the report byte-for-byte.

**Rough scope.** Relax `auto_fill_directive` behind a capability flag; graph
nodes for screen→analyze→validate→compose with hard gate semantics; seed
plumbing through `thesis_stats` entry points; eval-harness scenarios
(`quality/eval_harness.py`, `orchestrator/evals/sim_thesis.py`) covering the
richer pipelines.

**Dependencies.** 1, 2, 3, 6, 8 (and 9 for CB-SEM briefs). **Advances:**
B2B determinism principle; makes the certificate (12) sellable at scale.

---

## Sequencing summary

```
Near   : 1 self-validation ──► 2 power ──► 3 screening   (numbers chain hardened)
         4 provider-agnostic vision · 5 DOI→rubric        (independent, small)
Mid    : 6 coherence gate (anchor) · 7 method advisor
         8 PLS completeness · 9 CB-SEM · 10 viva · 11 similarity
Long   : 12 certificate · 13 instrument intelligence · 14 auto-mode upgrade
```

**The single highest-leverage next initiative is #1, the stats
self-validation layer.** It is small (pure functions at an existing tool
boundary), it directly compounds the thesis-stats investment that just
shipped, it upgrades the product's core promise from "no invented statistics"
to "no incorrect statistics," and it is a hard dependency of the coherence
gate (6), the deepened viva (10), and the certificate (12) — every later
trust initiative stands on it. Ship it first.
