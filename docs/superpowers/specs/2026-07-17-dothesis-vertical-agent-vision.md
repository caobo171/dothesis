# DoThesis — Vertical-Agent Vision: The Best Quantitative-Thesis Agent in the World

**Date:** 2026-07-17
**Status:** Strategic vision — north-star for all post-thesis-stats initiatives
**Owner:** cao.nv17@gmail.com
**Companion:** `2026-07-17-dothesis-vertical-agent-roadmap.md` (phased initiatives)
**Builds on:** `2026-07-17-thesis-stats-shared-lib-design.md` (shipped — real computation)

---

## 1. The claim we are making

DoThesis will be the single best AI agent in the world for one narrow, deep job:
**taking a social-science student from a blank topic to a committee-ready,
survey-based quantitative thesis** — PLS-SEM, CB-SEM, SPSS regression,
mediation/moderation — **and getting them through the defense**.

Not "an AI writing assistant that also does theses." Not "a stats tool with a
chatbot." A vertical agent whose every layer — skills, tools, state model,
quality gate, export — encodes what a real thesis committee actually checks.

The wedge that makes this defensible is already built and shipped:

1. **No fabricated sources** — every paper flows through
   `research_scout`/`parse_reference` and is verified against CrossRef, OpenAlex,
   Semantic Scholar, and arXiv (`engine/utils/api_citations/`,
   `AGENTS.md` invariants table).
2. **No invented statistics** — M4 numbers come only from the whitelisted
   `run_stats` tool (`agent/tools/stats.py`; "the whitelist IS the security
   boundary"), and the M4 skill hard-forbids results without a real dataset
   (`skills/dothesis-m4-analysis/SKILL.md`).
3. **Real computation, not just parsing** — as of the `thesis-stats` shared
   library (`libs/thesis-stats`, git submodule), `run_stats` computes full
   PLS-SEM (paths + bootstrap t/CI, R², AVE/CR/α, HTMT, Fornell-Larcker, VIF,
   f², GoF), EFA (KMO/Bartlett), full OLS, mediation effects, moderation
   interactions, and a rigor pack (Shapiro-Wilk, Levene, Cohen's f²/d, Harman
   CMB) directly from the raw uploaded data (`agent/tools/stats.py` ops
   `pls_sem`/`efa`/`regression_full`/`mediation`/`moderation`/`rigor`;
   `agent/tools/model_adapter.py` maps all three conceptual_model shapes in
   the wild to the engine).

General-purpose LLMs will always be able to *write prose about* a thesis. They
will not, without years of vertical investment, (a) refuse to fabricate a β,
(b) compute that β from the student's own .sav file inside a sandboxed
whitelist, (c) check the β against the committee's thresholds, and (d) drill
the student on defending it. That whole chain is the product.

---

## 2. Where we stand (verified inventory)

What exists today, grounded in the code:

| Capability | Where | State |
|---|---|---|
| One deep agent + 8 skills, M1–M5 over a project `context_store` | `agent/runtime.py`, `skills/`, `AGENTS.md` | Shipped, production chat path (`DOTHESIS_AGENT_V3=1`) |
| Headless auto-draft (B2B / one-click) | `orchestrator/` LangGraph graph, `api/app/job_runner.py` | Shipped; M3 auto-fill constrained to plain regression for analysability |
| Source verification cascade | `engine/utils/api_citations/` (crossref, openalex, …) | Shipped |
| Real stats compute from raw data | `libs/thesis-stats` + `agent/tools/stats.py` | **Just shipped** |
| Parsed-output ingestion (SmartPLS/SPSS/lavaan exports, screenshots) | `orchestrator/tools/m4_parsers/`, `agent/tools/output_parse.py` | Shipped (vision path Gemini-only) |
| Threshold sanity on pasted tables | `check_thresholds` in `agent/tools/stats.py` + `references/output-interpretation.md` | Shipped (comparison-only, computes nothing) |
| Methods pre-flight (advisory M3→M4 audit) | `agent/preflight.py` | Shipped (method chosen, instrument, sample plan, reverse-coding, CMB plan, missing-data plan) |
| Quality rubric (structure, citation integrity, stub detection, results-validity, preflight) | `quality/rubric.py` | Shipped; results-validity is **regex presence-matching**, not semantic |
| Mock committee / defense drill | `agent/tools/defense.py`, `skills/dothesis-defense/` | Shipped but **heuristic** (state weakpoints + staple questions) |
| Prompt-injection guardrails on uploaded documents | `agent/guardrails.py` | Shipped |
| Multimodal attachment dispatch | `agent/multimodal.py` | Shipped; vision table-parsing hardwired to Gemini (`output_parse.py`) |

What verifiably does **not** exist (grep-confirmed 2026-07-17):

- No power analysis anywhere (`libs/thesis-stats/src/thesis_stats/rigor.py` has
  assumptions/effect-sizes/CMB only).
- No numeric self-validation of outputs (nothing checks R²≤1, AVE-vs-loadings
  consistency, t↔p agreement) — neither in `thesis_stats` nor `quality/`.
- No missing-data (MCAR/imputation), Mahalanobis outliers, or straight-lining
  detection in the compute layer (preflight only asks whether a *plan* exists).
- No plagiarism/similarity capability anywhere in `agent/`, `quality/`,
  `orchestrator/`, or `skills/`.
- No cross-chapter coherence check (M3 hypotheses ↔ M4 decisions ↔ M5
  discussion). `quality/rubric.py:results_validity_dimension` is keyword regex.
- No Q² (blindfolding), no MGA/measurement invariance, no IPMA, no computed
  CB-SEM fit (lavaan exists only as a *parser* of pasted output in
  `orchestrator/tools/m4_parsers/lavaan.py`).
- DOI verification lives in the engine but is not a rubric dimension
  (`quality/rubric.py` checks citation↔reference-pool matching only).

The vision below is the closure of exactly these gaps, ordered in the roadmap.

---

## 3. The end-state: what "best in the world" means at each stage

The full student journey is longer than M1–M5. The end-state product owns all
eight stages, with a concrete quality bar at each — the bar is always "what the
committee will check," not "what an LLM can generate."

### 3.1 Topic (M1)
**Bar:** a title + RQs that are *quantifiable* — every RQ maps to a testable
relationship between measurable constructs, in a population the student can
actually sample.
**End-state:** the agent refuses-softly (advises, never blocks) when an RQ
cannot be operationalized as a survey construct; it knows the difference
between a describable topic and a testable one. Feasibility check includes an
early sample-size reality check ("this model will need n≈200; can you get
that?") — powered by the same power-analysis op used later in M4.

### 3.2 Literature (M2)
**Bar:** every source real, every gap traceable to named papers, and the
citation graph dense enough to survive "which study supports this claim?"
**End-state:** unchanged guarantee (verified-only sources) plus: the gap →
hypothesis chain is machine-traceable, so the coherence gate (§3.8) can verify
that every M3 hypothesis cites an M2 gap and every M5 discussion paragraph
ties a result back to the literature it confirms/contradicts.

### 3.3 Design (M3)
**Bar:** the method fits the model, the sample, and the data — and the student
can say *why* in one sentence.
**End-state:** **assumption-driven method selection.** Today the design-test
matrix is skill content the agent consults; the end-state is a deterministic
advisor: given the conceptual model shape (from `model_adapter`), planned n,
construct nature (reflective/formative), and — once data exists — actual
distribution properties from `run_stats(op="rigor")`, it recommends
PLS-SEM vs CB-SEM vs regression with a citable justification, and flags
mismatches ("you chose CB-SEM with n=87 and non-normal data — here is why
PLS-SEM is the defensible choice"). Instrument design includes reverse-coded
items, attention checks, and a-priori power analysis baked into the sample
plan (`agent/preflight.py` items stop being "do you have a plan?" and become
"here is the computed plan").

### 3.4 Instrument & data collection
**Bar:** a questionnaire the committee recognizes as psychometrically literate;
a dataset that arrives already screened.
**End-state:** scale provenance (adapted-from citations per construct),
generated attention-check items, and — on upload — an automatic screening
report: careless-response/straight-lining detection, Mahalanobis outliers,
missingness pattern (Little's MCAR test) with a recommended and *defensible*
treatment (listwise vs imputation), all as new whitelisted `rigor`-family ops
in `libs/thesis-stats`. The output is a generated **data-cleaning section**
("of 260 responses, 14 removed for straight-lining, 6 multivariate outliers
(Mahalanobis p<.001), missingness MCAR (p=.42), mean imputation applied…") —
prose the student pastes into Chapter 3, every number computed.

### 3.5 Analysis (M4)
**Bar:** every number real, every number *checked*, every threshold breach
surfaced, every hypothesis decided with effect size — the chapter a methods
examiner cannot puncture.
**End-state:** three layers on top of the shipped compute:
1. **Self-validation:** every `run_stats` result (and every parsed upload)
   passes a deterministic verifier before the agent may narrate it —
   impossible values (R²∉[0,1], AVE inconsistent with its own loadings,
   |t|↔p mismatch at the stated df, CI not containing the estimate,
   HTMT>1 anomalies) are caught at the tool boundary, not by the LLM.
   This turns "no invented statistics" into the stronger guarantee:
   **"no incorrect statistics."** No competitor can claim either.
2. **Power analysis:** a-priori (design-time n planning) and post-hoc
   (achieved power for the observed effects) as whitelisted ops — the
   G*Power ritual every committee expects, computed in-line.
3. **Method breadth:** Q² via blindfolding, multi-group analysis with
   measurement invariance (MICOM), IPMA, and computed CB-SEM fit
   (χ²/df, CFI, TLI, RMSEA, SRMR via semopy) — so "quantitative
   social-science thesis" is covered wall-to-wall, not just the PLS-SEM
   happy path. Family-consistency stays enforced (no PLS+CB metric mixing,
   already an invariant in `AGENTS.md` and the M4 skill).

### 3.6 Writing (M5)
**Bar:** six chapters where Chapter 4's tables render from persisted
structured results (never retyped), Chapter 3 describes what was actually
done, and Chapter 5 discusses what Chapter 4 actually found.
**End-state:** the writing layer is a *renderer over verified state*, not a
generator. Tables 4.1–4.3 render from the structured `analysis_results`
blocks the M4 skill already mandates; the data-cleaning section renders from
the screening report; the limitations section is seeded from real flagged
weaknesses (small n, borderline HTMT, post-hoc power) so weaknesses are
disclosed, not discovered.

### 3.7 Defense
**Bar:** the student walks in having already answered the five hardest
questions their *specific* thesis invites.
**End-state:** the mock committee (`agent/tools/defense.py`) graduates from
heuristics + staples to a **rubric-grounded viva simulation**: questions are
generated from the full quality-gate output (every threshold breach, every
coherence finding, every power shortfall becomes an examiner attack), the
drill grades answers against model-answer criteria, and it produces the
per-weakness citable cheat-sheet. This is also the referral moment — the
emotional peak of the product (`2026-07-08-mock-committee-design.md`).

### 3.8 The quality gate (cross-cutting)
**Bar:** a single "committee-readiness" verdict a student (or a B2B partner)
can trust.
**End-state:** `quality/rubric.py` grows from five dimensions to a full
audit: (a) **cross-chapter coherence** — the hypothesis registry is the spine:
every M3 hypothesis has an M4 decision and an M5 discussion consistent with
that decision, every number quoted in prose matches `analysis_results`
verbatim; (b) **DOI/metadata verification wired in** — the engine's CrossRef
verification becomes a rubric dimension, not just an ingestion step;
(c) **similarity self-check** — n-gram/fingerprint overlap against the
project's own source pool and verbatim-quote detection, so the student is
warned before Turnitin is; (d) every dimension emits **traceable findings**
(file/chapter/value) rather than scores alone.

---

## 4. Durable differentiators (the moat, ranked)

1. **The verified-numbers chain.** Raw data → whitelisted compute →
   deterministic self-validation → structured persisted results → rendered
   tables → coherence-checked prose. Every number in the PDF is traceable to
   a `run_stats` invocation on the student's file. This chain is the moat;
   each roadmap initiative either extends or hardens it.
2. **The verified-sources chain.** Same shape, for citations: search →
   multi-API verification → reference pool → citation-integrity rubric →
   (end-state) DOI-verified bibliography in the export.
3. **Committee-shaped quality encoding.** Thresholds (loadings ≥.708, AVE ≥.5,
   HTMT <.85, VIF <3.3…), metric-family consistency, power norms, CMB
   rituals — encoded as deterministic checks, not prompt vibes. LLM epistemics
   improve for everyone; *encoded domain judgment* compounds only for us.
4. **Two runtimes, one state.** The same guarantees hold in guided chat and
   in the unattended B2B pipeline (`orchestrator/`), because both write the
   same `context_store` through the same `commit_slice` boundary and the
   quality gate reads state, not transcripts.
5. **Defense preparation grounded in the student's actual weaknesses** — a
   product surface no horizontal tool has a reason to build.

---

## 5. Principles (binding on every roadmap initiative)

1. **Never fabricate.** Sources via verified search only; statistics via
   whitelisted ops only. No initiative may weaken either boundary — new
   analyses become new whitelisted ops in `libs/thesis-stats`, never free-form
   code (`agent/tools/stats.py` docstring: the whitelist IS the security
   boundary; integration is a Python import, never HTTP — the thesis-stats
   design's hard constraint).
2. **Everything traceable.** Every number, citation, and quality finding
   carries provenance (which op, which file, which source, which check).
   "Trust me" is never an acceptable output; "here is the computation" is.
3. **Deterministic before generative.** If a check can be a pure function,
   it is a pure function (the `preflight_check` / `check_thresholds` /
   rubric-deterministic-dimensions pattern). LLM judgment is reserved for
   what genuinely needs language: interpretation, coaching, prose.
4. **Advisory, not blocking.** Soft locks, never walls (`AGENTS.md`).
   Pre-flight, rigor findings, and quality gates surface and coach; only the
   two fabrication boundaries are hard. The exception: B2B/auto-mode may
   *choose* to treat gate failures as blocking, because there is no student
   in the loop to advise.
5. **Determinism for B2B.** The orchestrator path stays simple and
   analysable (M3 auto-fill constrained by design), produces reproducible
   artifacts, and every auto-generated thesis passes the same quality gate a
   chat-built one does — the gate is the product for B2B.
6. **State is the interface.** New capabilities read and write the
   `context_store` through `commit_slice`/`read_slice` only; quality and
   defense read state, not chat history. This is what lets chat, auto-mode,
   and future surfaces share one quality bar.
7. **Skills first.** Module behavior changes land in `skills/*/SKILL.md`
   before code (`AGENTS.md` contract), keeping domain judgment inspectable
   and versionable.
8. **Two-register explanations.** Every statistical concept is explained
   twice — plain-language (Vietnamese-analogy register) and the formal
   sentence the student can paste (F8 content-pack rule). Stats-anxious
   students are the market; intimidation is churn.

---

## 6. What "committee-ready" concretely requires (the checklist the product certifies)

A thesis leaves DoThesis committee-ready when the quality gate can attest,
with evidence, all of:

- [ ] Every RQ maps to ≥1 hypothesis; every hypothesis cites an M2 gap.
- [ ] Every source in the bibliography is verification-passed (API match or
      DOI-resolved); every in-text citation resolves to the pool.
- [ ] Method choice is justified against model/sample/data (decision-matrix
      trace).
- [ ] Sample size is defended by an a-priori power computation (or post-hoc
      power is disclosed as a limitation).
- [ ] Data screening is documented with computed numbers (missingness +
      treatment, outliers, careless responses, reverse-coding applied).
- [ ] Measurement model complete per construct (α/CR/AVE/loadings), breaches
      surfaced not buried; discriminant validity (HTMT or Fornell-Larcker)
      reported; CMB addressed (Harman or better).
- [ ] Every hypothesis has a decision (supported/not) with effect size, from
      self-validated numbers; metric family consistent with the chosen tool.
- [ ] Chapter 4 tables match persisted results verbatim; Chapter 5 discusses
      what Chapter 4 found; limitations disclose the flagged weaknesses.
- [ ] Similarity self-check passed (no undisclosed verbatim overlap).
- [ ] The student has drilled the generated defense questions for their
      flagged weaknesses.

Every unchecked box is a roadmap initiative; the checklist *is* the product
spec for the quality gate's end-state.

---

## 7. Non-goals

- **Qualitative/mixed-methods depth** (interviews, coding, NVivo). M1 already
  normalizes `research_type`; qualitative stays supported as prose guidance,
  not as a compute vertical. Depth-first beats breadth-first here.
- **Becoming a general stats package.** Ops exist to serve thesis chapters,
  not to compete with R. If an analysis has no place in a survey-based
  thesis, it doesn't enter the whitelist.
- **Ghost-writing without guarantees.** Auto-mode without data still refuses
  to invent results — the M4 hard rule holds in every mode.
- **External plagiarism-database parity with Turnitin.** The similarity check
  is a *self-check* against the project's own sources and verbatim-quote
  hygiene, not a web-scale index.
