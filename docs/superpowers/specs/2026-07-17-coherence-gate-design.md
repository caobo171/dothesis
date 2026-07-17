# Hypothesis Registry + Cross-Chapter Coherence Gate — Design Spec

**Date:** 2026-07-17
**Status:** Design — ready for implementation (companion plan: `2026-07-17-coherence-gate-plan.md`)
**Owner:** cao.nv17@gmail.com
**Roadmap:** Initiative #6 in `2026-07-17-dothesis-vertical-agent-roadmap.md:192-224` (Phase 2 — "This is the Phase-2 anchor: after it, the gate certifies the *thesis*, not just its parts")
**Vision anchors:** `2026-07-17-dothesis-vertical-agent-vision.md:186-198` (§3.8(a) cross-chapter coherence), `:204-207` (§4.1 — the verified-numbers chain *ends* in "coherence-checked prose"), `:164-173` (§3.6 — Chapter 5 discusses what Chapter 4 actually found)
**Builds on:** Initiative #1, shipped — `2026-07-17-stats-self-validation-design.md`; `libs/thesis-stats/src/thesis_stats/validation.py`; `agent/stats_validation.py`

---

## 1. Motivation

The moat is the verified-numbers chain (vision §4.1, `:204-207`):

```
raw data → whitelisted compute → self-validation (#1, shipped) → structured
persisted results → rendered tables → [THIS INITIATIVE] coherence-checked prose
```

Initiative #1 closed the hole between "compute" and "persist": impossible or
self-contradictory numbers can no longer become `analysis_results` (the M4
commit gate, `agent/tools/state_tools.py:104-127`) and the rubric re-checks
persisted numbers (`quality/rubric.py:257-288`). But #1 deliberately stops at
the payload boundary. Its design spec §2 states the scope line this
initiative now crosses (`2026-07-17-stats-self-validation-design.md:60-67`):

> **Cross-chapter coherence (M3 ↔ M4 ↔ M5)** — hypothesis-registry
> reconciliation, prose-vs-state number matching, direction-word agreement.
> That is roadmap initiative #6; this layer only checks numbers against
> *other numbers in the same results payload*, never against prose. The one
> M3-adjacent check kept here (X2, hypothesis coverage) is a soft structural
> count, not semantic reconciliation.

So today, nothing verifies the thesis agrees with itself **across modules**:

- M3 commits `hypotheses` and a `conceptual_model` whose edges carry `id`
  ("H1"), `hypothesis` text, and `effect_type: "positive"|"negative"`
  (`orchestrator/schemas/m3.py:36-47`, `orchestrator/agents/m3_design.py:533-542`).
- M4 commits `analysis_results.hypothesis_tests[]` with
  `{id, hypothesis, path, numbers{beta,t,p,f2}, decision, interpretation}`
  (`skills/dothesis-m4-analysis/SKILL.md:143-149`).
- M5 writes prose into `final_sections` (chat path,
  `agent/state.py:52`) or `m5_writing.chapters` (auto-mode / editor path,
  `orchestrator/tools/m5_writing.py:1645-1678`).

A discussion chapter can claim H2 was supported when the persisted `decision`
says otherwise, or quote β=.34 where `numbers.beta` is .31, and no gate can
see it — the rubric's `results_validity_dimension` is presence regex over
flattened text (`quality/rubric.py:89-108`), and the only cross-module check
that exists is #1's X2, a soft structural count of hypothesis ids
(`agent/stats_validation.py:325-338`). The roadmap names exactly this failure
(`roadmap:194-201`).

This initiative closes it with a **hypothesis registry** (one derived record
per hypothesis, spanning M3 → M4 → M5) and a **deterministic coherence
checker** (pure, no LLM, offline) that reconciles the three module slices and
the prose against each other.

## 2. Scope and non-scope

**In scope**

- A pure module `agent/coherence.py` (§3) containing:
  - the hypothesis-registry builder (§4) — derived, never persisted;
  - deterministic prose-number/word extraction for M5 chapters (§6);
  - the coherence check catalogue (§5) with hard/soft severities and explicit
    tolerances;
  - never-raising composite entry points for the two wiring surfaces (§7).
- Wiring at: the **M5 `commit_slice` gate** (hard number-mismatch findings
  block, §7.2), the **M4 `commit_slice` gate** (advisory-only coherence
  warnings + X2 delegation, §7.3), and a **`coherence` rubric dimension**
  whose hard findings enter `blocking` (§7.4).
- Extension (not duplication) of #1's X2 hypothesis-coverage check: the
  matching logic moves into the registry builder and `agent/stats_validation.py`
  delegates to it, keeping the shipped finding id and severity (§5.1, §7.3).
- Finding-schema reuse from #1 (§5.4) — same dict shape, new `coherence.*`
  check ids.
- M5 + M4 skill guidance updates and an AGENTS.md invariant row (§7.6).

**Out of scope (explicitly deferred)**

- **Semantic / LLM-judge coherence** — "does the discussion paragraph
  actually discuss the found result?" (`roadmap:210-212` names a bounded
  LLM-judge pass as part of #6's outcome; it is deferred to a follow-up spec).
  This layer is deliberately designed so that pass can slot in later as a
  separate **soft-only** rubric sub-dimension consuming the same registry —
  nothing here needs rework to add it. Everything in this spec is pure and
  offline.
- **M5 rewriting / auto-correction.** The checker flags; it never edits
  prose. Fix paths are narrated by the agent (re-quote the persisted value,
  or re-run/recommit M4), mirroring #1's "fix the source, never retype"
  contract (`skills/dothesis-m4-analysis/SKILL.md:184-189`).
- Gap→hypothesis traceability (M2 ↔ M3 — vision §3.2 `:106-112`). The
  registry reserves a `gap_ids` field but no check consumes it yet.
- Qualitative results and mixed-method themes (`orchestrator/schemas/m3.py:52-56`).
- Blocking inside the M5 editor autosave PATCH endpoint
  (`api/app/routers/m5_editor.py:97-136`) — deliberate, see §7.5.
- Re-checking arithmetic possibility of persisted numbers — that is #1's job
  and already runs at the M4 gate and in `stats_validity_dimension`. This
  layer treats persisted M4 numbers as the validated baseline
  (`roadmap:221` — "Dependencies. 1 (validated numbers are the
  reconciliation baseline)").

## 3. Architecture and placement

### 3.1 Decision: one pure module in `agent/coherence.py`

The roadmap sketch says "number-extraction + reconciliation module in
`quality/`" (`roadmap:217`). We deviate, with rationale:

| Option | Verdict |
|---|---|
| (a) Module in `quality/` (roadmap literal) | Rejected — the M5/M4 commit gates live in `agent/tools/state_tools.py`, and the established layering direction is quality→agent, not agent→quality: `quality/rubric.py` already lazily imports `agent.stats_validation` (`quality/rubric.py:274`), `agent.preflight` (`:120`), and `agent.tools.instrument` (`:143`). Placing the checker in `quality/` would create the first agent→quality import edge just to feed the gate. |
| (b) Module in `libs/thesis-stats` | Rejected — the registry walks dothesis product schemas (`hypothesis_tests`, `conceptual_model` edges, `final_sections`/`chapters`) and bilingual prose conventions; #1's spec already ruled that product shapes must not leak into the shared engine (`2026-07-17-stats-self-validation-design.md:84`). No new arithmetic primitives are needed from the engine. |
| **(c) `agent/coherence.py` — pure, no LangChain, no I/O, mirroring `agent/stats_validation.py`** | **Chosen.** Same placement pattern as #1's dothesis adapter: the gates import it lazily from `state_tools.py`, the rubric imports it lazily from `quality/rubric.py` — both directions already exist for `agent.stats_validation`. |

Public surface of `agent/coherence.py`:

- `normalize_hypothesis_id(x) -> str | None` — "H1"/"h1"/"r-H1"/"Giả thuyết H1"
  → `"H1"` (shared with the X2 delegation, §7.3).
- `build_registry(hypotheses, conceptual_model, analysis_results, chapters)
  -> list[dict]` — the derived registry (§4). Pure; tolerant of every
  historical shape; unknown shapes yield thinner entries, never errors.
- `extract_prose_claims(prose, chapter_name) -> list[dict]` — deterministic
  stat/direction/decision extraction from one chapter's prose (§6).
- `check_coherence(registry) -> list[dict]` — the catalogue (§5) over a
  built registry; returns #1-shaped finding dicts.
- `coverage_findings(m3_hypotheses, analysis_results) -> list[dict]` — the
  extracted X2 logic + the new orphan-result check (§5.1); called by
  `agent/stats_validation.py` (delegation) and by `check_coherence`.
- `validate_m5_sections(final_sections, flat_context) -> dict` — gate entry
  point: builds the registry from the flat contextStore + the *incoming*
  sections, runs the catalogue, returns #1's aggregate wrapper
  (`{"passed", "hard", "soft", "findings", "findings_hard", "findings_soft",
  "crashed"}` — `agent/stats_validation.py:43-48`). **Never raises.**
- `validate_coherence(nested_context_store) -> dict` — rubric entry point
  over the nested store (`m3_design` / `m4_analysis` / `m5_writing` columns).
  **Never raises.**

### 3.2 Determinism, purity, dependency constraints

- Every function: same inputs → same findings, byte-identical, ordered by
  registry order (M3 hypothesis order) then check order. No LLM, no network,
  no filesystem, no clock, no randomness.
- Dependencies: stdlib `re`/`unicodedata` only. It does **not** import
  `thesis_stats` (no arithmetic beyond comparison; the finding shape is a
  plain dict copied from #1's contract, not the `Finding` dataclass — same
  choice `agent/stats_validation.py` already makes for its X2/unstructured
  findings at `:318-338`).
- Fast enough for every commit: regex over ≤ 6 chapters of prose + a few
  dozen registry entries — single-digit milliseconds.

## 4. The hypothesis registry

### 4.1 Decision: derived at check time, never persisted

The roadmap sketches the registry as a schema "enforced at `commit_slice`
validation for the owning slices" (`roadmap:203-206`). We keep the *schema*
and the *enforcement*, but the registry itself is a **pure derivation**, not
a stored key:

- **Slice ownership forbids a cross-module key.** Each contextStore key has
  exactly one owning module (`agent/state.py:24-53`); a registry spanning
  M3+M4+M5 facts would need either a new ownership carve-out or triple
  writes. Both re-create the "two maps of the same fact drift silently"
  failure the codebase explicitly guards against
  (`agent/tools/state_tools.py:29-31`).
- **Staleness is the enemy this initiative exists to kill.** A persisted
  registry would itself go stale on every upstream edit — the exact drift the
  checker must detect. Deriving at check time makes the registry always-true
  by construction; the existing `needs_review` propagation
  (`agent/state.py:78-84`, M3→M4,M5 and M4→M5) already covers the
  "upstream changed, downstream must re-look" workflow (`roadmap:218-219`).
- **No migration.** Historical projects get a registry for free the first
  time the rubric runs.

The registry MAY be echoed (bounded, ids + statuses only) in gate success
payloads for narration, but is never a source of truth.

### 4.2 Registry entry shape

One flat dict per hypothesis id found in **either** M3 or M4 (union — the
orphan check needs entries M3 doesn't know):

```json
{
  "id": "H1",
  "in_m3": true,
  "statement": "LS has a positive effect on PI",
  "direction": "positive",
  "direction_source": "edge_effect_type",
  "edge": {"source": "LS", "target": "PI"},
  "gap_ids": [],
  "m4": {
    "present": true,
    "result_id": "r-H1",
    "path": "LS -> PI",
    "decision": "supported",
    "decision_supported": true,
    "significant": true,
    "numbers": {"beta": 0.34, "t": 7.01, "p": 0.001, "p_is_threshold": true, "f2": 0.18}
  },
  "m5": {
    "mentioned_in": ["results", "discussion"],
    "claims": [
      {"chapter": "results", "kind": "number", "metric": "beta", "value": 0.34,
       "decimals": 2, "attribution": "strong", "sentence": "…(β=.34, p<.001)… H1…"},
      {"chapter": "discussion", "kind": "decision", "value": "supported",
       "attribution": "strong", "sentence": "…H1 was supported…"}
    ]
  }
}
```

Field derivations (all tolerant — a missing source just leaves the field
null/absent):

- **`id`** — via `normalize_hypothesis_id`. M3 `hypotheses` entries may be
  strings (`"H1: [A] has a positive effect on [B]"` —
  `skills/dothesis-m3-design/SKILL.md:12,93-96`) or dicts
  (`orchestrator/schemas/m3.py:47` is `list[dict] | None`); #1's X2 already
  tolerates both (`agent/stats_validation.py:330-331`). For strings, the id
  is the leading `H\d+` token; for dicts, `id` else `label` else leading
  token of `statement`/`text`. M4 side: `hypothesis_tests[].hypothesis`,
  falling back to the `id` field (same double-keying X2 uses at `:326-329`),
  with the `r-` result-prefix stripped for matching.
- **`statement`** — the M3 string (minus the id prefix) or dict
  `statement`/`text`/`hypothesis`; else the matching conceptual-model edge's
  `hypothesis` text (`orchestrator/agents/m3_design.py:537`).
- **`direction` + `direction_source`** — resolution order:
  1. `edge_effect_type`: the conceptual-model edge whose `id` matches
     ("H1" edges — `orchestrator/agents/m3_design.py:534,541`) →
     `effect_type` `"positive"`/`"negative"` (a `"moderates"`/other value →
     direction `None`; moderation hypotheses have no sign expectation here).
  2. `statement_wording`: the bilingual direction lexicon (§6.3) applied to
     the statement, only when exactly one polarity matches.
  3. `None` — no direction claim, direction checks skip.
  The `direction_source` field is recorded because `effect_type` defaults to
  `"positive"` on model generation without the user necessarily confirming it
  (`orchestrator/agents/m3_design.py:538-541`) — that is a load-bearing
  reason direction checks are soft (§5.5).
- **`edge`** — source/target **labels** resolved through the node list
  (edges reference node ids, nodes carry `label` —
  `orchestrator/schemas/m3.py:38-44`), so they are comparable with M4 `path`
  strings after #1's arrow normalization (`_norm_path`,
  `agent/stats_validation.py:25-28` — "→" → "->").
- **`m4`** — from the matching `hypothesis_tests` entry:
  `decision_supported = str(decision).lower().startswith("support")` (the
  shipped predicate, `agent/stats_validation.py:249`); `numbers.p` parsed
  through the shipped `_p_value` helper (`agent/stats_validation.py:31-40`,
  `"<0.001"` → `(0.001, threshold=True)`); `significant` = numeric `p < .05`
  or threshold ≤ .05. Only the **first** matching entry per id feeds
  agreement checks — the M4 skill's mutate rule appends new entries rather
  than overwriting (`skills/dothesis-m4-analysis/SKILL.md:221`), so we take
  the **last** matching entry (most recent) and record
  `superseded_count` when >1. (Coverage counts any match.)
- **`m5`** — chapters resolved to canonical names via
  `chapters_from_final_sections` (`orchestrator/tools/m5_writing.py:1645-1678`)
  when given `final_sections`, or directly when given the auto-mode/editor
  `chapters` dict (both shapes, same tolerance the rubric applies at
  `quality/rubric.py:15-19`). Only `results`, `discussion`, and `conclusion`
  chapters are scanned for claims (§6.1). Stub prose is skipped via
  `_is_stub_prose` (`orchestrator/tools/m5_writing.py:1722-1729`).

## 5. Check catalogue

All checks are pure functions over the registry. Category prefix
`coherence.*` except the shipped X2 id, which is kept verbatim for its
existing consumers.

### 5.1 Coverage (extends #1's X2 — does not duplicate it)

| ID | Check id | Rule | Severity | Surface |
|---|---|---|---|---|
| CO1 | `xtable.hypothesis_coverage` (shipped id, kept) | An M3 hypothesis id with no `hypothesis_tests` entry. Logic extracted from `agent/stats_validation.py:325-338` into `coverage_findings` and upgraded: id matching via `normalize_hypothesis_id` (the shipped version does exact-string matching, so "H1" vs "r-H1"/"h1" miscounts), and message/shape unchanged. | soft | M4 gate (existing), rubric |
| CO2 | `coherence.orphan_result` | A `hypothesis_tests` entry whose normalized id exists in neither M3 `hypotheses` nor the conceptual-model edge ids. Soft — an extra entry can be a legitimate robustness/control test, but usually signals a renamed or deleted hypothesis. | soft | M4 gate, rubric |
| CO3 | `coherence.undiscussed_hypothesis` | A hypothesis with an M4 result that is never mentioned (id token, §6.2) in the `results` **or** `discussion` chapter. Runs only when both chapters exist with non-stub prose — a half-written draft must not spray findings. | soft | M5 gate, rubric |

CO1 stays at the M4 commit gate exactly where it is today (it already rides
`stats_validation_warnings` — `agent/tools/state_tools.py:112-124`); the M4
skill's "do not mark M4 done while any M3 hypothesis lacks a result"
(`skills/dothesis-m4-analysis/SKILL.md:237`) remains guidance, with CO1 as
its deterministic witness.

### 5.2 Direction agreement

| ID | Check id | Rule | Severity |
|---|---|---|---|
| DI1 | `coherence.direction_m3_m4` | Registry `direction` is `positive`/`negative` and the persisted β has the opposite sign (beyond ε = half-ulp of the persisted display precision, #1 §4.4 defaults). Skipped when β is absent or direction is `None`. Soft — two wording-adjacent reasons: (a) `effect_type` is machine-defaulted to positive (`orchestrator/agents/m3_design.py:538-541`); (b) a sign opposite to the hypothesis is a *legitimate finding* (the hypothesis is then simply not supported) — it is only an inconsistency, not an impossibility. Message distinguishes the `decision_supported=true` case ("a negative β cannot support a positive-effect hypothesis — flip the hypothesis direction or the decision") from the plain case. | soft |
| DI2 | `coherence.direction_prose` | An M5 sentence attributed to the hypothesis (§6.2) contains exactly one polarity from the direction lexicon (§6.3), and it contradicts the sign of the persisted β. Sentences matching both polarities, or none, produce nothing. Soft — natural-language polarity is wording, not arithmetic (e.g. "the negative relationship was not found" defeats naive matching; the both-polarities guard catches most such sentences, and soft severity absorbs the rest). | soft |

### 5.3 Decision agreement

| ID | Check id | Rule | Severity |
|---|---|---|---|
| DE1 | *(already shipped — not re-implemented)* | M4-internal `decision` vs its own p: #1 already maps `decision` onto a `significant` flag per p-claim (`agent/stats_validation.py:248-260`) and C6 fires **hard** `consistency.flag_p` on contradiction (`libs/thesis-stats/src/thesis_stats/validation.py:446-463` — significant with p ≥ .05, or non-significant with p < .05). This spec adds nothing at the M4 boundary for decision-vs-p; the design merely documents the dependency. | hard (shipped) |
| DE2 | `coherence.decision_prose` | An M5 sentence attributed to the hypothesis contains exactly one decision form from the lexicon (§6.3 — supported / not-supported / significant / not-significant families, negated forms matched first), and it contradicts the registry: prose "supported"/"significant" with `decision_supported=false` or `significant=false`, or the inverse. Soft — see §5.5. | soft |

### 5.4 Number agreement — the hard core

| ID | Check id | Rule | Severity |
|---|---|---|---|
| NU1 | `coherence.number_mismatch` | A stat quoted in M5 prose with **strong attribution** (§6.2) to a hypothesis/construct disagrees with the persisted M4 value beyond tolerance (§6.4). Covers β, t, p (exact and threshold forms), f² per hypothesis; R² per endogenous construct. A prose `p < X` fails when the persisted p (numeric, or persisted threshold) does not satisfy `< X`. **Hard** — the persisted value passed #1's validation and is the single source of truth (vision `:191-193`: "every number quoted in prose matches `analysis_results` verbatim"); a differing quote is provably wrong against product state. | hard |
| NU2 | `coherence.number_mismatch_weak` | Same comparison but with **weak attribution** (construct-label sentence match rather than an explicit H-id, §6.2). | soft |

Prose numbers with no attributable persisted counterpart produce **no
finding** (never guess — #1's §6.1 principle). A β quoted in prose when M4
has *no* numbers at all is CO3/undiscussed territory, not NU1.

### 5.5 Severity policy — reconciling with "advisory, not blocking"

#1 resolved the tension with vision principle 4 by pinning **hard =
provably wrong** ("an impossible number is a fabrication with extra steps",
`2026-07-17-stats-self-validation-design.md:444-452`). This spec applies the
same bar with one refinement for prose:

- **Hard (blocks): NU1 only.** A number is a verbatim, machine-comparable
  claim; when the prose says β=.34 and the validated state says .31, one of
  them is wrong and we know which — the state, because it came from
  `run_stats` or a confirmed parse and survived #1's gate. There is no
  wording nuance in a digit string. (DE1 hard already ships inside #1.)
- **Soft (advises): everything word-shaped or structural.** CO1–CO3, DI1,
  DI2, DE2. Direction and decision words pass through natural language —
  negation scope, hedging ("partially supported"), Vietnamese/English
  register variation — and M3's `direction` may be a machine default. Under
  the #1 bar, none of these is *provable*; blocking a student on a wording
  judgment call violates the principle ("The student is never walled in by a
  judgment call — only by arithmetic"). The LLM-judge follow-up (out of
  scope) is the eventual arbiter for the semantic cases.

**Where hard blocks — both surfaces, mirroring #1 exactly:**

1. **The M5 commit gate** (§7.2) blocks the commit that would persist the
   contradicting prose — the chat path's enforcement point, symmetric with
   #1's M4 gate.
2. **The rubric `blocking` list** (§7.4) catches prose that entered state
   without passing the chat gate: the auto-draft path writes
   `m5_writing.chapters` outside `commit_slice`, the editor PATCH mutates
   prose directly (`api/app/routers/m5_editor.py:127-135`), and legacy
   projects predate the gate. Same safety-net split #1 established
   (`2026-07-17-stats-self-validation-design.md:462-470`).

Coherence never hard-blocks an **M4** commit: at M4 there is no prose yet,
and every M4-side coherence check (CO1, CO2, DI1) is advisory (§7.3).

### 5.6 Tolerances

- Prose numbers carry inferred `decimals` (digits displayed, §6.4);
  ε = 0.5 × 10⁻ᵈ — the half-ulp rule verbatim from #1 §4.4.
- Persisted numbers are compared at full stored precision; the tolerance is
  taken from the *prose* precision (the prose is the rounded rendering of the
  persisted value, so "β=.34" matches stored 0.3391 but not 0.31).
- β sign participates in the value (a sign mismatch is a value mismatch,
  never absorbed by ε).
- Every finding records `tolerance`, `observed` (the prose sentence excerpt +
  parsed value) and `expected` (the persisted value + its location) — the
  audit-trail contract from #1 §5.

## 6. Deterministic prose extraction

This is the riskiest surface; the design principle is **precision over
recall**: a missed match costs a warning; a false hard finding costs the
layer's credibility. Everything below is pure regex + string ops.

### 6.1 Which prose

Only the `results`, `discussion`, and `conclusion` canonical chapters.
Rationale: `intro`/`lit_review` cite other papers' statistics (a β from a
cited study must not be compared to ours — this is the dominant
false-positive source, so those chapters are excluded wholesale), and
`methodology` quotes *planned* figures (target n, thresholds). Chapter
resolution per §4.2; non-canonical sections (References etc.) are dropped by
`chapters_from_final_sections` already.

### 6.2 Attribution — tying a sentence to a hypothesis

- **Segmentation:** split prose into sentences on newline boundaries and on
  `[.!?]` followed by whitespace + a non-digit (so "p < .05. Next" splits but
  "0.34" never does). Deterministic and unit-tested; no NLP library.
- **Hypothesis anchor:** the token `\bH\d{1,2}\b` (plus normalized forms
  "Giả thuyết 1", "Hypothesis 1" → H1). **Strong attribution** = the sentence
  (or its parenthetical stat group, e.g. "(β = .34, p < .001)") contains
  exactly **one** hypothesis anchor. Sentences with ≥2 anchors contribute
  mention evidence for CO3 but no number/word claims (can't tell which stat
  belongs to which hypothesis).
- **Weak attribution** = no anchor, but the sentence contains exactly one
  registry path's source **and** target construct labels (≥3 chars, matched
  case-insensitively on word boundaries) and the parsed metric exists on
  exactly one registry entry. Produces NU2 (soft) only.
- **R²:** attributed to a construct, not a hypothesis — strong when the
  sentence names exactly one construct with a persisted
  `structural_model.r2` entry, or when the model has exactly one endogenous
  R² (then any R² mention is unambiguous).

### 6.3 Bilingual lexicons

The product's default language is Vietnamese (`language … or "vi"` —
`agent/tools/writing.py:112`, `api/app/routers/m5_editor.py:575`), so all
word checks ship with EN + VI forms as module constants (extensible, and the
precedent for VN/EN dual-register narration is already in the M4 skill
`:194-196`):

- **positive:** positive(ly), increases?, "tác động tích cực", "thuận chiều",
  "cùng chiều", "tăng".
- **negative:** negative(ly), decreases?, "tác động tiêu cực",
  "nghịch chiều", "ngược chiều", "giảm".
- **supported:** supported, accepted, "được ủng hộ", "được chấp nhận".
- **not supported:** "not supported", rejected, "không được ủng hộ",
  "bị bác bỏ", "không được chấp nhận".
- **significant / not significant:** significant, "có ý nghĩa thống kê" /
  "not significant", "no significant", "không có ý nghĩa thống kê",
  "không đáng kể".

Matching rules: lowercase + NFC normalization; **negated forms are matched
first** (ordered alternation), and a sentence matching both a form and its
negation — or both polarities — yields nothing (§5.2/§5.3). This is the
whole negation strategy; anything smarter is the LLM-judge's job.

### 6.4 Number patterns

- Metrics: `β|ß|\bbeta\b|hệ số (hồi quy|đường dẫn|tác động)` → beta;
  `\bp\b` with `[<=≤]` → p (threshold vs exact by operator); `R²|R\^?2` → r2;
  `\bt\b =` → t; `f²|f\^?2` → f2. Each followed by an optional operator and
  a signed decimal.
- Normalization before parse: unicode minus (−, –) → `-`; APA-style bare
  leading dot (`.34`) → `0.34`; Vietnamese decimal **comma** (`0,34`) →
  `0.34` (only when the comma sits between digits inside a matched stat
  expression — never applied to free text).
- `decimals` inferred from the matched string (digits after the separator);
  drives ε per §5.6.
- Unparseable/ambiguous matches produce no claim (never guess).

Known deferred-to-judge cases (documented in the module docstring, all
producing *no finding* here): stats quoted in tables rendered as markdown
(compared cell-wise by initiative #13's renderer work, not prose regex),
percentage renderings of R² ("56% of variance"), and comparative wording
without digits ("a stronger effect than H2").

### 6.5 Finding schema reuse

Findings are #1 §5 dicts verbatim — `check`, `severity`, `message`,
`location`, `observed`, `expected`, `tolerance`, `source` — with:

- `source: "prose"` for NU/DI2/DE2 findings (a third value alongside
  `computed`/`parsed`; consumers only branch on the existing two, and #1's
  `Finding.to_dict` location-merge already tolerates extra keys —
  `libs/thesis-stats/src/thesis_stats/validation.py:48-58`).
- `location` gains `hypothesis` and `chapter` keys (extra keys ride the same
  merge; `table` is null for prose findings).
- The aggregate wrapper is `_agg`'s shape (`agent/stats_validation.py:43-48`),
  reused by both entry points.
- Rubric mapping: `issue = message`, `chapter` = the finding's chapter (or
  `"results"`), `severity` passed through, `fix` templated per check id —
  the same mapping `stats_validity_dimension` applies (`quality/rubric.py:276-281`).

## 7. Integration points

### 7.1 Overview

```
M3 commit ──────────────► (unchanged)
M4 commit_slice wrapper ─► #1 gate (unchanged) + X2 delegated + CO2/DI1 advisory   §7.3
M5 commit_slice wrapper ─► NEW coherence gate: NU1 hard-blocks; soft rides payload §7.2
quality/rubric.py ───────► NEW coherence dimension; hard → blocking               §7.4
m5_editor PATCH ─────────► deliberately not gated (rubric is the net)             §7.5
```

### 7.2 The M5 commit gate — hard number mismatches block `final_sections`

**Attach point:** the model-facing `commit_slice` wrapper in
`agent/tools/state_tools.py`, immediately after the M4 stats block
(`:104-127`) and before `store.commit_slice` (`:128-133`) — the established
home for deterministic model-facing guards (NON_CONTENT_KEYS strip `:73-82`,
M3 model repair `:88-97`, M4 stats gate `:104-127`). Both runtimes (app chat
and headless) share these tools, so both are covered — the same coverage
argument #1 made (`2026-07-17-stats-self-validation-design.md:407-418`).

```python
_coherence_warnings = None
if module == "M5" and "final_sections" in writes:
    try:
        from agent.coherence import validate_m5_sections  # noqa: PLC0415
        _flat = (store.load() or {}).get("contextStore", {})
        _v = validate_m5_sections(writes["final_sections"], _flat)
        if _v.get("crashed"):
            _coherence_warnings = "unavailable"
        elif _v["hard"]:
            return json.dumps({
                "error": "coherence_failed — this prose quotes statistics that "
                         "contradict the persisted analysis_results and cannot be committed",
                "findings": _v["findings_hard"],
                "hint": "Quote the persisted value exactly (re-read the M4 slice), or — if "
                        "the analysis itself changed — recommit M4 first. Never adjust the "
                        "prose number to something in between. Explain in both registers.",
            }, ensure_ascii=False)
        elif _v["soft"]:
            _coherence_warnings = _v["findings_soft"]
    except Exception:
        logger.debug("commit_slice: M5 coherence gate skipped", exc_info=True)
        _coherence_warnings = "unavailable"
```

- Error return (not raise) — the `SliceOwnershipError` pattern
  (`state_tools.py:134-137`) so the turn continues and the agent coaches.
- Soft findings ride the success payload as `coherence_warnings`; a crash
  yields `coherence: "unavailable"` — key naming symmetric with
  `stats_validation_warnings` / `stats_validation` (`state_tools.py:140-142`).
- `validate_m5_sections` reads `hypotheses`, `conceptual_model`, and
  `analysis_results` from the **flat** contextStore (the store's `load()`
  shape — the documented footgun and its precedent at `state_tools.py:219-224`),
  and the incoming `writes["final_sections"]` as the M5 side. A read failure
  of any upstream slice skips the dependent checks (thin registry, fewer
  checks — never a block).
- If M4 has no `analysis_results` at all, every check skips except nothing —
  an M5 draft before analysis produces zero findings from this layer (the
  fabricated-statistics case is #1/M4-skill territory, and CO3 requires an
  M4 result to exist).

### 7.3 The M4 commit gate — delegation + advisory coherence

Two changes, both non-breaking:

1. **X2 delegation (extend, don't duplicate).** The X2 block in
   `agent/stats_validation.py:325-338` is replaced by
   `findings += coverage_findings(m3_hypotheses, block)` (lazy import of
   `agent.coherence`; both modules are pure so the edge is clean).
   `coverage_findings` emits CO1 with the **shipped** check id
   `xtable.hypothesis_coverage`, severity, and message shape — existing
   tests and consumers see the same finding, now with normalized id
   matching — plus the new CO2 `coherence.orphan_result`. The
   `validate_analysis_results(block, m3_hypotheses)` signature is unchanged.
2. **Advisory DI1 at commit time.** In the `state_tools.py` M4 block, after
   the existing validation call, a soft-only
   `coherence.m4_commit_findings(writes["analysis_results"], _flat)` (DI1
   direction check — it needs `conceptual_model`, which the stats validator
   never sees) is merged into the same warnings surface, under
   `coherence_warnings`. Never blocks; wrapped in the same try/except.

### 7.4 The rubric dimension — the safety net over persisted state

New `coherence_dimension(context_store)` in `quality/rubric.py`, appended in
`score_thesis` after `stats_validity_dimension` (`quality/rubric.py:457`):

- Decision: a **new dimension**, not a fold into `results_validity` (which
  stays presence-only) or `stats_validity` (payload-internal correctness) —
  three different questions: *mentioned*, *possible*, *consistent across
  chapters*. Weight 0.10 (total weight is normalized — `quality/rubric.py:250-254`
  — so this doesn't skew others).
- Reads the nested columns: `m3_design.{hypotheses, conceptual_model}`,
  `m4_analysis.analysis_results`, and prose via the rubric's own `_sections`
  tolerance (`quality/rubric.py:15-19`) mapped to canonical chapters; calls
  `validate_coherence`; maps findings per §6.5.
- Hard findings (NU1) flow into the existing `blocking` aggregation
  (`quality/rubric.py:463`) — this is what closes the auto-draft, editor-PATCH,
  and legacy paths (§5.5), the same role `stats_validity` plays for numbers
  (`quality/rubric.py:257-266` docstring).
- Score: `1.0` minus 0.5/hard and 0.1/soft, floored at 0 — the
  `stats_validity_dimension` formula (`quality/rubric.py:284-286`).
- Never crashes; tolerates every historical shape (string
  `analysis_results`, missing chapters, string hypotheses). No M5 prose →
  score 1.0, zero findings (nothing to reconcile — structure gaps are the
  `structure` dimension's job, `quality/rubric.py:33-41`).

### 7.5 The editor autosave PATCH — deliberately not gated inline

`PATCH /m5/chapters/{name}` writes prose directly
(`api/app/routers/m5_editor.py:127-135`) and revalidates citations inline
(`:122-125`). We do **not** block or check coherence there in this
initiative: autosave fires per keystroke-burst mid-edit — a hard block would
fight the user while a sentence is half-typed, and even advisory findings
computed per-save are noise until the edit settles. The rubric (§7.4) is the
enforcement net for this path; surfacing live per-chapter
`coherence_warnings` in the PATCH response (mirroring `uncited_warnings`) is
noted as a natural follow-up once the editor UI has a place to render them —
out of scope here.

### 7.6 Skill and docs surface

- `skills/dothesis-m5-writing/SKILL.md`: a "Numbers come from state" section —
  when writing results/discussion, read β/t/p/R² from the M4 slice and quote
  them verbatim at the displayed precision; the coherence gate blocks a
  commit whose quoted numbers contradict `analysis_results`; on a
  `coherence_failed` error, re-read the M4 slice and correct the prose (or
  recommit M4 if the analysis changed) — never split the difference; soft
  `coherence_warnings` (undiscussed hypotheses, direction/decision wording)
  must be acknowledged to the user before `confirm_done`.
- `skills/dothesis-m4-analysis/SKILL.md`: one-line update to the
  self-validation section (`:190-192`) noting coverage now checks both
  directions (a result entry for a nonexistent hypothesis is flagged too).
- `AGENTS.md` invariants: add the row "hard coherence findings (prose
  numbers contradicting persisted `analysis_results`) block M5
  `final_sections` commits — the prose end of the verified-numbers chain."

## 8. Error handling

Verbatim inheritance of #1 §8, applied to this layer:

- **Never raises out of an entry point.** `validate_m5_sections` /
  `validate_coherence` wrap everything; on exception: `logger.exception`,
  emit `coherence_check_crashed` via `agent.analytics.emit` (the established
  no-op-until-wired hook — `agent/tools/state_tools.py:181-182`), return
  `_agg([], crashed=True)`. The gate then commits with
  `coherence: "unavailable"` recorded on the payload — fail-open, because
  blocking a student on our own bug violates the advisory principle, and the
  rubric gives a second chance.
- **Unknown/legacy shapes produce thinner registries, never errors** —
  string `analysis_results` yields `m4.present=false` entries (no number
  checks possible; CO1 still counts); a string-only `hypotheses` list still
  yields ids; a missing `conceptual_model` just nulls directions.
- **Ambiguity produces silence, not findings** (§6) — the checker's
  false-positive budget for hard findings is zero.

## 9. Testing strategy — fully offline

All tests pure/deterministic, no LLM, no network. Layout follows the
existing suites (`agent/tests/test_stats_validation.py`,
`agent/tests/test_state_tools.py`, `tests/test_stats_validity_dimension.py`).

1. **Registry building.** From the M4 skill's canonical sample block
   (`SKILL.md:132-151`) + string and dict M3 hypotheses + both M5 shapes:
   correct ids, direction resolution order (edge beats wording; moderation →
   None), path label resolution, last-entry-wins for duplicate results,
   union entries for orphans.
2. **Prose extraction.** Parameterized EN + VI: "(β = .34, p < .001)" strong
   attribution; ".34"/"0,34"/"−0.34"/en-dash forms; decimals inference;
   two-anchor sentences yield mention-only; "not supported" beats
   "supported"; both-polarity sentences yield nothing; decimal periods never
   split sentences; cited-literature chapters never scanned.
3. **Agreement checks.** Per check id, one firing and one passing case:
   prose β=.34 vs stored 0.3391 passes (2 dp half-ulp); vs 0.31 → hard NU1;
   prose "p < .001" vs stored 0.049 → hard; vs stored "<0.001" → passes;
   weak attribution → NU2 soft; DI1 positive-direction/β=−0.3 → soft with
   the supported-decision message variant; CO1/CO2/CO3 coverage matrix.
4. **Severity contract.** No check other than NU1 can ever emit hard
   (asserted over a generated corpus of mismatches); soft-only payloads never
   block.
5. **The M5 gate** (temp-dir `ProjectStateStore`, the `test_state_tools.py`
   pattern): clean commit passes untouched; NU1 commit returns
   `coherence_failed` and state is unchanged; soft-only commit succeeds with
   `coherence_warnings`; no `analysis_results` in store → commit passes with
   zero findings; monkeypatched crash → commit proceeds with
   `coherence: "unavailable"`; non-M5 commits byte-identical behavior.
6. **X2 delegation regression.** The full shipped
   `agent/tests/test_stats_validation.py` stays green; new cases prove
   "r-H1"-style ids now count as covered and orphan entries fire CO2.
7. **Rubric dimension.** Synthetic nested store scores 1.0 clean; a
   prose-number corruption lands NU1 in `blocking`; the existing
   `tests/good_pls_thesis.json` fixture produces **zero hard** findings (soft
   allowed); string/legacy shapes never crash (never-crash global constraint,
   `quality/rubric.py:186-213` pattern).
8. **Determinism.** Same inputs twice → byte-identical findings list.

## 10. Rollout / compatibility

- No schema migration, no new tool, no thesis-stats change (no submodule
  bump — everything lives in the parent repo).
- Additive JSON keys only (`coherence_warnings`, `coherence` on commit
  payloads); existing consumers unaffected.
- The M5 gate fires only on new chat commits; existing projects meet the
  layer through the rubric first (advisory-surface-first, #1's rollout §10).
- **Risk to #1 (shipped):** the only shipped code modified is the X2 block
  in `agent/stats_validation.py` (§7.3) and additive lines in
  `state_tools.py`. Mitigation: delegation preserves check id, severity, and
  message shape; the shipped test suite is the regression harness and runs
  in the same phase as the change (plan Phase 4).
- Consumers downstream: initiative #10 (viva) keys examiner questions on
  `coherence.*` check ids; #12 (certificate) records the coherence
  attestation (`roadmap:305-310`, `:358-361`) — both get stable ids from §5.
