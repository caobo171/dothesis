# M5 Writing as a Renderer over Verified State — Design

**Date:** 2026-07-18
**Status:** Design — implementation plan in `2026-07-18-m5-renderer-plan.md`
**Vision:** `2026-07-17-dothesis-vertical-agent-vision.md` §3.6 (:164-173) — "the
writing layer is a *renderer over verified state*, not a generator. Tables
4.1–4.3 render from the structured `analysis_results` blocks the M4 skill
already mandates; the data-cleaning section renders from the screening report;
the limitations section is seeded from real flagged weaknesses."
**Also closes:** vision §3.8a (:186-198, the coherence spine has less to catch
when the number-source is authoritative) and checklist item "Chapter 4 tables
match persisted results verbatim; limitations disclose the flagged weaknesses"
(:282-283).
**Binding principles:** vision §5 (:225-259) — deterministic before generative,
advisory not blocking, everything traceable, never fabricate.

---

## 1. Problem

Today every number that reaches a chapter passes through an LLM's token stream.
The compose path (`orchestrator/tools/m5_writing.py:2490-2584 compose_chapter`)
interpolates the persisted `analysis_results` into the results prompt as JSON
(`{results}`, `orchestrator/prompts/m5/results.md:11,22-30`) and *instructs* the
model to build Tables 4.1–4.3 from it (`results.md:53-66`). The guardrails
around this are all *reactive*:

- `_drop_placeholder_tables` (`m5_writing.py:2437-2479`) deletes tables the LLM
  filled with "…" cells — after the LLM already invented a table shell.
- The coherence gate (`agent/coherence.py:354-384 _number_checks`) hard-blocks a
  prose β/t/p/R²/f² that contradicts the persisted value at
  `commit_slice("M5", …)` (`agent/tools/state_tools.py:144-162`) — but its own
  docstring defers "markdown-table numbers" to a future judge
  (`coherence.py:8-9`): a retyped number **inside a table cell** is invisible
  to it today.
- The rubric's `stats_validity` / `coherence` dimensions
  (`quality/rubric.py:257-288, 430-452`) are safety nets over state, not over
  what the LLM typed into a table.

Meanwhile the verified state that the tables *should* be a pure projection of
already exists, shipped this cycle:

| Verified state | Producer | Shape reference |
|---|---|---|
| `analysis_results.measurement_model` (per-construct loadings/α/CR/AVE) | M4 skill mandate | `skills/dothesis-m4-analysis/SKILL.md:168-173` |
| `analysis_results.discriminant_validity` (HTMT/F-L matrix) | same | `SKILL.md:174-175` |
| `analysis_results.hypothesis_tests[]` (id/path/numbers{beta,t,p,f2}/decision) | same | `SKILL.md:176-182` |
| `analysis_results.structural_model` (r2, q2; CB-SEM cfi/tli/rmsea/srmr/chi2_df) | same + roadmap #9 | `SKILL.md:183`, `agent/stats_validation.py:300-308`, `2026-07-17-cb-sem-design.md` §6.2 |
| `analysis_results.data_screening` (n_before/n_after, MCAR, outliers, careless, verbatim `narrative`) | roadmap #3 | `2026-07-17-data-screening-design.md` §8.2 (:493-510), `libs/thesis-stats/src/thesis_stats/screening.py:353-378, 492-504` |
| `sample_plan.power_analysis` (required N + justification) vs achieved n | roadmap #2 | read exactly as `agent/viva.py:208-235, 166-175` |
| Soft validity findings (borderline HTMT, α>0.98, coverage gaps) | roadmap #1 | `agent/stats_validation.py:344-366 validate_analysis_results` |
| Provenance summary (`analysis_provenance`, dataset hash, computed-vs-pasted tiers) | roadmap #12 | `agent/provenance.py` module docstring |

`claims_from_analysis_results` (`agent/stats_validation.py:217-313`) already
parses every one of these shapes — the renderer reads the **same fields the
validator validates**, so a rendered number is by construction a checked number.

This initiative flips the tables from "LLM writes, gates catch" to "renderer
writes, LLM narrates around."

## 2. Goals / non-goals

**Goals**

1. Chapter 4's Tables 4.1–4.3 (+ CB-SEM fit) are emitted by **pure Python**
   from `analysis_results` — the LLM never types a table number.
2. Chapter 3's data-cleaning passage renders from
   `analysis_results.data_screening` — the `narrative` quoted verbatim, plus a
   deterministic screening-summary table.
3. Chapter 5/6's limitations are **seeded** as deterministic bullets from real
   flagged weaknesses (power shortfall, threshold breaches, borderline HTMT,
   soft validity findings, screening removals, similarity findings), phrased
   with the disclose-and-frame register the viva sim already uses
   (`agent/viva.py:224-232`).
4. Rendered blocks are machine-marked so the coherence gate and similarity
   check treat them as **authoritative, not suspect**, and so tampering is
   detectable (content hash).
5. Both runtimes consume the same renderers: auto-mode/partner compose paths
   weave them in at composition; chat/editor/auto-export paths weave any
   missing blocks in at export ("two runtimes, one state", vision §4.4).

**Non-goals**

- No change to what M4 persists (the block contract in
  `SKILL.md:165-197` is the input, frozen).
- No rendering from the orchestrator's legacy `{results: {step: StepResult}}`
  shape (`stats_validation.py:224-229`) in v1 — fail-open to today's behavior.
  (Auto-mode's M3 auto-fill is constrained to plain regression today,
  vision §2 table; the regression family below covers its *canonical* block
  when roadmap #14 upgrades it.)
- No qualitative tables (themes/quotes stay LLM prose, vision §7).
- No LLM calls anywhere in the renderers (hard requirement).
- No new blocking gate — renderers are additive; every failure path degrades
  to exactly today's compose/export behavior (vision §5.4).

## 3. Architecture decision: where the renderers live

**Decision: a new pure module `orchestrator/tools/results_render.py`
(stdlib-only: `json`, `hashlib`, `re`), NOT an extension of `m5_writing.py`.**

Rationale:

- `m5_writing.py` imports `boto3` and `langchain_core` at module load
  (`m5_writing.py:24-25`) and mutates `sys.path` for the engine
  (`:28-40`). The coherence module (`agent/coherence.py`) and similarity module
  (`quality/similarity.py`) must call `strip_rendered_blocks()` (§6) — they are
  "pure, offline, never raises" modules (`coherence.py:1-12`) and must not
  inherit that import weight. A stdlib-only module is importable from `agent/`,
  `quality/`, `orchestrator/`, and tests with zero setup.
- Determinism is the point (vision §5.3): a module that *cannot* reach an LLM
  or the network is the strongest form of the guarantee.
- Precedent: `agent/coherence.py` and `libs/thesis-stats/*` follow exactly this
  "pure module + thin integration at the boundary" pattern; `m5_writing.py`
  keeps the boundary role (compose/export), `compose_export.py:61-196` keeps
  subset selection.
- `m5_writing.py` is 2652 lines; the renderer is a separately testable concern.

Import direction: `m5_writing`/`compose_export` → `results_render` (never the
reverse). `agent/coherence.py` and `quality/similarity.py` lazy-import it
fail-open, the same pattern as `coherence.py:292`.

## 4. The renderer API (all pure, all fail-open)

```python
# orchestrator/tools/results_render.py

RenderedBlock = dict  # {"kind": str, "markdown": str, "sha": str, "token": str}

def detect_family(analysis_results: Any, methodology: str | None = None)
        -> str | None                      # "pls_sem" | "cb_sem" | "regression" | None
def render_results_tables(analysis_results: Any, language: str = "en")
        -> list[RenderedBlock]             # kinds: descriptives, measurement_model,
                                           #   discriminant_validity, model_fit,
                                           #   structural_paths, r2_q2
def render_cleaning_section(analysis_results: Any, language: str = "en")
        -> RenderedBlock | None            # kind: data_cleaning
def render_limitations(nested_cs: dict, *, rubric_findings: list | None = None,
                       language: str = "en") -> RenderedBlock | None
                                           # kind: limitations
def weave(prose: str, blocks: list[RenderedBlock]) -> str
def strip_rendered_blocks(prose: str) -> str
def rendered_kinds(prose: str) -> set[str]
def verify_rendered_blocks(prose: str, analysis_results: Any) -> list[dict]
```

Every public function: `try/except → log + return empty/None/input-unchanged`,
the exact posture of `stats_validation.py:335-366` and
`coherence.py:463-507`. A renderer bug must never block a legitimate thesis.

### 4.1 Number fidelity rules

- Floats are formatted `f"{v:.4f}".rstrip("0").rstrip(".")` — the stats layer
  already rounds payloads to 4 dp (`_round_floats`, cited at
  `2026-07-17-cb-sem-design.md` §6.1/§6.2), so this renders the stored value
  **verbatim**, never re-rounded. Ints render as ints.
- `p` values render exactly as stored — the M4 contract allows the string
  `"<0.001"` (`SKILL.md:178`); the renderer must not parse-and-reformat it
  (`stats_validation.py:31-40 _p_value` shows how fragile that is; we don't
  do it at all).
- Missing cell → `—` (em dash in-cell is fine; `_sections_to_markdown`'s
  dash normalization at `m5_writing.py:291` turns it into `-`, still a
  visible "not available" marker, never an invented value).
- No derived numbers. The renderer never computes (no mean λ², no √AVE): if
  Fornell-Larcker diagonals aren't in the matrix, they aren't in the table.
  Computation belongs to `thesis_stats` ops (vision §5.1).

### 4.2 Family rule (which tables render)

Presence-first detection, mirroring the validator's own CB-SEM discriminator
(`stats_validation.py:242-245`: fit keys on `structural_model`), with the M3
methodology string (`quality/rubric.py:522-529 _detect_method`) as tiebreaker
only. Never mix families — the M4 invariant (`SKILL.md:187-193`).

| Family | Detected by | Tables rendered (when source sub-block present) |
|---|---|---|
| `cb_sem` | any of `cfi/tli/rmsea/srmr/chi2_df` on `structural_model` (or a `fit` sub-dict, tolerated for the op-payload shape `cb-sem-design.md` §6.2) | 4.0 descriptives · 4.1 measurement (item, λ, α, CR, AVE) · 4.2 model fit (χ², df, χ²/df, CFI, TLI, RMSEA [90% CI], SRMR — each with its Hu & Bentler threshold column, `SKILL.md:68-69`) · 4.3 structural paths (H, path, β, SE/z **or** t, p, decision) · R² block |
| `pls_sem` | `measurement_model` present with AVE/CR **and/or** `discriminant_validity` present, no fit keys | 4.0 descriptives · 4.1 measurement (item, outer loading, α, CR, AVE) · 4.2 discriminant validity (HTMT or Fornell-Larcker matrix, labeled by `discriminant_validity.method`) · 4.3 hypothesis tests (H, path, β, t, p, f², decision) · R²/Q² block |
| `regression` | `hypothesis_tests`/`structural_model.r2` present without measurement/fit blocks | 4.0 descriptives · 4.1 reliability (α per construct if `measurement_model` rows exist) · 4.2 model summary (R², adj. R² if present) · 4.3 coefficients (H, path, β, t, p, decision) |
| `None` | block missing, free-text (`str`), or legacy step shape | render nothing — compose behaves exactly as today |

Per-table sourcing is 1:1 with what `claims_from_analysis_results` reads:
4.1 ← `measurement_model[]` (`stats_validation.py:247-260`), 4.2 ←
`discriminant_validity.matrix` (`:262-264, 316-328`), 4.3 ←
`hypothesis_tests[]` (`:266-288`), fit/R² ← `structural_model`
(`:300-308`). A field the validator can't see, the renderer doesn't print.

### 4.3 Table anatomy (one worked example)

For the fixture block in `SKILL.md:165-185`, `render_results_tables` emits
(English variant; Vietnamese headers via a `_HEADERS_VI` map following the
`M5_CHAPTER_TITLES_VI` precedent, `m5_writing.py:1625-1632`):

```markdown
<!--dt-rendered:begin kind=measurement_model sha=3fa9c02d11ab-->
**Table 4.1 — Measurement model: reliability and convergent validity**

| Construct | Item | Loading | Cronbach's α | CR | AVE |
|---|---|---|---|---|---|
| LS | LS1 | 0.81 | 0.86 | 0.9 | 0.62 |
| LS | LS2 | 0.78 |  |  |  |
| PI | PI1 | … | 0.84 | 0.88 | 0.58 |

*Source: rendered from persisted analysis results (DoThesis).*
<!--dt-rendered:end kind=measurement_model-->
```

- Caption uses the canonical "Bảng 4.x/Table 4.x" bold form the sanitizer
  already recognizes (`m5_writing.py:2460`).
- `sha` = first 12 hex of sha256 over the canonical JSON of the *source
  sub-block* (`json.dumps(…, sort_keys=True)`), the exact `_sha12` recipe from
  `agent/provenance.py`. `verify_rendered_blocks` re-renders from state and
  compares — the certificate (roadmap #12) can later attest "tables rendered
  from state, unmodified" with evidence, and a hand-edited table cell in the
  M5 editor is detectable (advisory, never blocking).
- The source line is the provenance breadcrumb (vision §5.2); when the M4
  commit wrote an `analysis_provenance` summary (`agent/provenance.py`), the
  line upgrades to "computed from the uploaded dataset (sha256 …)".

### 4.4 Sentinel survivability (verified against the export pipeline)

The HTML-comment sentinels must survive `_sections_to_markdown`'s cleanup
chain (`m5_writing.py:272-291`):

- `_scrub_internal_markers` (:338-348) — only strips `⚠️` blockquotes and
  `[Composition failed…]` brackets: safe.
- `_split_run_on_hypotheses` (:351-379) — fires only on `H\d:` **with colon**;
  table rows are `| H1 |` (no colon): safe.
- `_mermaid_to_prose` (:454-548) — requires `flowchart`/`graph `/`mermaid`
  tokens: safe.
- `_normalize_prose_markdown` (:1159-1204) — needs ≥2 inline ` * `/` • `
  markers per line: table and sentinel lines have none: safe.
- Em-dash normalization (:291) — sentinels use ASCII only (`dt-rendered`,
  `kind=`, `sha=`): safe.
- Pandoc passes raw HTML comments through markdown → they do not appear in
  the DOCX/PDF text (invisible to the committee, visible to our checkers).

`sanitize_prose`'s `_drop_placeholder_tables` (:2437-2479) drops only tables
with `…` placeholder cells — rendered tables never contain them (missing →
`—`, and `—`→`-` is not in `_PLACEHOLDER_CELL_RE`'s dot/ellipsis set; the
plan adds a regression test pinning this).

## 5. The renderer/LLM split — who writes what

**The renderer owns every statistic. The LLM owns every connective sentence.**

Concretely, per chapter:

| Chapter | Renderer supplies (verbatim, marked) | LLM still writes |
|---|---|---|
| 3 Methodology | data-cleaning block: screening summary table + the `data_screening.narrative` quoted verbatim (the "committee-ready paragraph", `screening.py:353-378` / `_narrative_applied` :492-504) | everything else: design, instrument, procedure, and the sentence *introducing* the screening block |
| 4 Results | Tables 4.0–4.3 + fit/R² blocks per §4.2 | the overview sentence before each table and the interpretation paragraph after it — the `[overview] → [table] → [interpretation]` pattern the results prompt already teaches (`orchestrator/prompts/m5/results.md:92-96`) |
| 5/6 Discussion·Conclusion | limitations seed: one disclosed-limitation bullet per real flagged weakness (§7) | the discussion of each finding against M2 gaps, implications, future work prose |
| References | (already shipped) `_references_section_body` — the existing proof this pattern works (`m5_writing.py:1772-1802`, appended at `:1874-1876`) | nothing |

**Placement mechanism.** The chapter prompts gain placement tokens:
the compose prompt receives each block's *rendered markdown as read-only
context* plus the instruction "where a table belongs, emit exactly the token
`[[DT:measurement_model]]` on its own line — never write the table yourself."
After the LLM returns, `weave(prose, blocks)` (pure):

1. replaces each token line with the block's sentinel-wrapped markdown;
2. **appends** any block whose token the LLM failed to emit (fail-open: the
   table always ships, placement is merely nicer);
3. deletes duplicate tokens/kinds (idempotent — weaving twice is a no-op,
   keyed on the sentinel `kind=`);
4. in the **results chapter only**, when ≥1 quantitative block was woven,
   drops any *unmarked* pipe table whose data cells are majority-numeric —
   the deterministic "authoritative replacement" rule that removes an
   LLM-improvised Table 4.x. Text-heavy tables (qual themes, `SKILL.md`'s
   mixed-methods §4.3 content) are untouched.

Why tokens-then-weave rather than "paste the table into the prompt and trust
the LLM to copy it": a copied table is still LLM output — one transposed digit
and the guarantee is gone. With weave, the bytes in the document come from the
renderer, full stop. The LLM sees the real numbers (so its narrative can
reference them — and the coherence gate then checks that narrative), but it
physically cannot alter a table cell.

**Why the LLM keeps the narrative:** interpretation is genuinely language work
(vision §5.3 — "LLM judgment is reserved for what genuinely needs language"),
and the gate already polices it: every β/t/p/R²/f² the narrative quotes is
checked against the same persisted block the table rendered from
(`coherence.py:354-384`; M5 skill quality bar `SKILL.md:137-142`).

## 6. Making rendered blocks authoritative-not-suspect

Rendered blocks are, by construction, byte-projections of the state the
checkers compare against — so the checkers should not re-litigate them:

- **Coherence** (`agent/coherence.py`): `_resolve_chapters` (:286-303) pipes
  each chapter's prose through `strip_rendered_blocks` (lazy import,
  fail-open) before sentence segmentation. Rendered table rows therefore never
  produce number claims. This is strictly safe: the stripped content cannot
  disagree with state (same source, verbatim), and the narrative *around* the
  blocks remains fully checked — including the LLM's post-table
  interpretation paragraphs. The gate keeps its teeth exactly where the LLM
  still writes. (Today's `_NUM` regex `coherence.py:116-118` mostly can't see
  table cells anyway — the docstring's deferred "markdown-table numbers"
  gap — the renderer + strip closes that gap from the source side: the table
  is right because it *is* the state.)
- **Similarity** (`quality/similarity.py`): `_resolve_chapters` (:221-236)
  applies the same strip before tokenization, so two chapters that both carry
  rendered blocks (e.g., n appearing in the cleaning narrative and the
  descriptives table) never fire the intra-thesis duplication check
  (`similarity.py:288+`; rubric dim `quality/rubric.py:455-469`) against
  machine-emitted text. Rendered text is ours; only student/LLM prose is
  similarity-relevant.
- **Editor tampering**: `verify_rendered_blocks` compares each sentinel's
  `sha` against a re-render from current state; mismatches surface as a soft
  finding through `stats_validity_dimension`'s existing fail-open pathway
  (wire-up is a small rubric addition, advisory-only, vision §5.4).

## 7. The three renderers in detail

### 7.1 Results tables (Chapter 4) — §4.2/§4.3 above

Ordering is deterministic: constructs and items in persisted order,
hypothesis rows in persisted `hypothesis_tests` order (M4 appends, never
overwrites — `SKILL.md:254`; when the same normalized id appears twice the
renderer keeps **the last entry** per id, matching the registry's superseded
logic `coherence.py:227-248`, and footnotes "supersedes an earlier run").

### 7.2 Data-cleaning section (Chapter 3)

Input: `analysis_results.data_screening` (design §8.2 shape:
`n_before/n_after`, `missing{overall_pct, mcar{chi2,df,p}, treatment}`,
`outliers{multivariate_flagged, removed, method}`,
`careless{flagged, removed, method}`, `reverse_coded{recoded}`, `narrative`).

Output block (kind `data_cleaning`):

1. the `narrative` string **verbatim** — it is already the committee-ready
   sentence built by the screening engine ("Of 260 responses, screening
   identified 14 straight-lined case(s)… Little's MCAR test was
   non-significant (χ²(41) = 44.2, p = 0.34). Recommended treatment:
   listwise." — `screening.py:353-378`; post-apply variant with "Final N ="
   accounting, `:492-504`). This fulfils the data-screening design's own M5
   rule: "quotes `analysis_results.data_screening.narrative` verbatim
   (numbers never re-typed)" (`2026-07-17-data-screening-design.md:538-541`).
2. a screening-summary table (Stage | Cases removed | n remaining) derived
   only from fields present; omitted entirely if only `narrative` exists.

Fail-open: no `data_screening` → `None` → Chapter 3 composes exactly as today.

### 7.3 Limitations seed (Chapter 5/6)

`render_limitations(nested_cs, rubric_findings=None, language)` builds one
bullet per **real, evidenced** weakness — never a boilerplate bullet, and
never a weakness without its numbers (vision §3.6: "disclosed, not
discovered"). Sources, all deterministic reads:

| Weakness | Read from | Bullet framing (mirrors the viva's honest register) |
|---|---|---|
| Power shortfall | `m3_design.sample_plan.power_analysis.{recommended_n\|required_n, justification}` vs achieved n from `analysis_results.descriptives.n` / `field_it_responses` — the exact reads at `agent/viva.py:208-217, 166-175` | "The achieved sample (n=X) fell short of the a-priori requirement (N=Y, {justification}); findings are interpreted as a boundary condition, with replication at full power as future work." — the disclose-and-frame hint at `viva.py:224-232`, never an excuse |
| Threshold breach / borderline | recomputed from the block against the committee cutoffs the M4 skill states (loadings ≥0.708, AVE ≥0.5, CR 0.7–0.95, HTMT <0.85 — `SKILL.md:203-205`); HTMT in [0.85, 0.90) phrased as "borderline", ≥0.90 as a breach | "Discriminant validity between A and B is borderline (HTMT = 0.87 against the .85 criterion); results involving this pair are interpreted with caution." |
| Soft stats-validity findings | `agent.stats_validation.validate_analysis_results(block)["findings_soft"]` (lazy import; pure, offline; fail-open per `:344-366`) — α>0.98, HTMT>1, coverage gaps | one bullet per finding message, deduped |
| Screening removals / MCAR rejected | `data_screening` (§7.2 fields) | "20 of 260 responses were removed during screening (14 careless, 6 multivariate outliers); missingness was not MCAR (p=.03) and is disclosed as a potential bias source." |
| Similarity / rubric findings | **passed in** via `rubric_findings` by callers that already computed them (`review_thesis`'s `score_thesis` result, `agent/tools/writing.py:321-330`; the certificate's deterministic rubric, `quality/rubric.py:472-478 include_judge=False`) — the renderer never runs the rubric itself (keeps it dependency-light and side-effect free) | generic disclose-and-frame template per finding, capped |
| Not-supported hypotheses | `hypothesis_tests[].decision` not starting "support" (the read at `viva.py:255-267`) | "H3 (A → B, β=…, p=…) was not supported; §5.x offers a theoretical account — a null result reported as a finding, not suppressed." |

Cap: 8 bullets, hard findings first (the `viva.py:127-128` sort). Output kind
`limitations`, woven into the conclusion chapter (merged-conclusion exports
inherit it automatically because the merge relabels the discussion chapter,
`compose_export.py:71-81`). Zero weaknesses found → `None` (no fabricated
humility; the M5 skill's "Limitations are honest" bar, `SKILL.md:148`).

## 8. Integration: how both modes consume the renderers

There are exactly two seams, and every surface goes through one of them:

### 8.1 Compose-time weaving (auto-mode, partner, chat full-draft)

`compose_chapter` (`m5_writing.py:2490-2584`) gains a post-LLM weave step for
the three affected chapters: build blocks from `context_slice` (it already
receives the full merged slice with `results` = `analysis_results`,
`m5_writing.py:1833-1834`, `compose_export.py:101-102`), inject the rendered
markdown + token instructions into the prompt kwargs, and run
`weave(prose, blocks)` right after `sanitize_prose` (`:2572`) so the sanitizer
can never mangle a rendered block. Because both `compose_all_sections`
(`:1805-1877`, chat full-draft + auto-export compose) and
`compose_export.compose_sections` (`:61-174`, partner/auto subset) delegate to
`compose_chapter`, one change covers every composing surface.

Prompt updates (`orchestrator/prompts/m5/results.md:53-66` and the
methodology/conclusion templates): replace "Present a Markdown table…" with
"the following tables are rendered for you (read-only); place
`[[DT:<kind>]]` where each belongs and write the overview + interpretation
prose around it; never emit a table of statistics yourself."

### 8.2 Export-time safety net (drafts composed before this ships, chat-drafted sections, editor edits)

`run_export` (`m5_writing.py:2127-2157`) gains an optional
`context_store: dict | None = None` kwarg (default `None` = exact current
behavior). When provided, it calls `ensure_rendered(sections, context_store)`
first: for the results/methodology/conclusion sections, compute
`rendered_kinds(prose)` and weave (append-mode) only the missing kinds.
Idempotent by sentinel dedupe, so a section already woven at compose time is
untouched.

Callers updated to pass their store (each already holds it):

- chat export tool — `agent/tools/writing.py:251` (has `full_cs` from
  `load_full_context_store`, `:107-111`)
- auto-export hook on M5 done — `api/app/agent_state.py:256-281`
- M5 editor export route — `api/app/routers/m5_editor.py:538-576`
- partner — via `compose_export.compose_and_export` (`:177-196`), which
  passes the `context_store` it already receives.

This is the same "single shared export path" consolidation the codebase
already committed to (`m5_writing.py:2131-2134`).

### 8.3 Chat-mode targeted drafting (the "student pastes" path)

The M5 wizard drafts single sections conversationally
(`skills/dothesis-m5-writing/SKILL.md:97-111`). A new read-only factory tool
in `agent/tools/writing.py` (alongside `export_docx`/`review_thesis`,
`:25-351`): `render_verified_sections(kind: str)` → returns the rendered
markdown for `results_tables` | `data_cleaning` | `limitations` from current
state. The M5 skill copy is updated: when drafting Results/the cleaning
passage/limitations, call the tool and include its output **verbatim**, then
write narrative around it — never hand-build Tables 4.1–4.3 (this supersedes
the skill's current "copy, never retype" instruction `SKILL.md:137-138` with
"you don't even copy — the tool renders"). Even if the agent disobeys, §8.2
weaves the authoritative blocks at export and §5's replacement rule drops the
hand-built numeric table; the commit-gate coherence check
(`state_tools.py:144-162`) still polices its narrative.

## 9. Failure modes (deterministic + fail-open, enumerated)

| Condition | Behavior |
|---|---|
| `analysis_results` missing / free text / legacy step-shape | `detect_family` → `None`; no blocks; compose/export identical to today (`assess_export_readiness` still gates an empty M4, `m5_writing.py:1735-1769`) |
| A sub-block missing (e.g. no `discriminant_validity`) | that table omitted; others render; no placeholder, no crash |
| A row/cell malformed (non-dict item, string loading) | cell → `—` or row skipped, mirroring the tolerant reads of `claims_from_analysis_results` (`stats_validation.py:247-260`) |
| Renderer raises anywhere | caught at the public boundary → log + no blocks (posture of `stats_validation.py:335-366`) |
| LLM never emits a token | block appended at chapter end (weave rule 2) |
| LLM emits its own numeric table anyway | dropped by weave rule 4 (results chapter only, majority-numeric cells, only when rendered blocks exist) |
| Same section woven twice (compose + export) | sentinel-kind dedupe → no duplicates |
| `weave`/`ensure_rendered` raises | export proceeds with unwoven sections (wrapped fail-open at the caller) |
| Editor user hand-edits a rendered cell | export still ships (advisory product); `verify_rendered_blocks` sha mismatch surfaces as a soft finding |

Nothing in this design can *block* a thesis: the only hard gates remain the
two fabrication boundaries and the pre-existing commit gates (vision §5.4).

## 10. Testing strategy (offline, deterministic — summary; full matrix in the plan)

- **Golden tables**: a PLS fixture block (the `SKILL.md:165-185` example
  verbatim) and a CB-SEM fixture (fit keys per `stats_validation.py:305-308` +
  `cb-sem-design.md` §6.2) → assert the **exact expected markdown**,
  byte-for-byte, including sentinels and shas.
- **Cleaning paragraph**: a `data_screening` fixture (design §8.2 example)
  → exact paragraph; assert the `narrative` substring is verbatim-identical.
- **Limitations**: a weakness fixture (power shortfall + borderline HTMT +
  screening removals + one not-supported H) → exact bullets; empty-weakness
  fixture → `None`.
- **Determinism**: every renderer called twice on deep-copied input →
  byte-identical output; dict-key order shuffled → identical output.
- **Fail-open**: partial/missing/malformed blocks per §9 → no raise, correct
  omissions; free-text block → `[]`/`None`.
- **Coherence-gate proof**: build `final_sections` whose results chapter is
  rendered-tables-plus-clean-narrative → `validate_m5_sections`
  (`coherence.py:463-475`) returns zero hard findings; then inject one wrong
  β into the *narrative* (outside sentinels) → the hard
  `coherence.number_mismatch` still fires. Proves: rendered tables never trip
  prose≠numbers, and the gate keeps catching real drift.
- **Pipeline survivability**: a woven section through `_sections_to_markdown`
  + `sanitize_prose` → table intact, sentinels intact,
  `_drop_placeholder_tables` leaves it alone.
- **Similarity neutrality**: two chapters sharing rendered blocks →
  `check_similarity` reports no intra-thesis finding attributable to them.

## 11. Risks

1. **(#1) Chapter-flow degradation** — deterministic splicing can read as
   "table dumped at the end" when the LLM misplaces or omits tokens, and the
   numeric-table drop rule could remove a legitimate LLM table we didn't
   anticipate (e.g., a custom-analysis table from `custom_analyses`).
   *Mitigations:* append-fallback keeps content complete even when placement
   fails; drop rule is scoped (results chapter, majority-numeric cells, only
   when rendered blocks woven); `custom_analyses` tables can be exempted by a
   header allowlist if eval shows loss; the model-cost eval harness
   (`quality/eval_harness.py`) can A/B token-compliance across providers.
2. **Shape drift in the wild** — old projects carry free-text or exotic
   blocks; renderer correctly yields nothing, but then §3.6's bar isn't met
   for them. Accepted: the bar applies to the shipped M4 contract; the
   rubric's existing dimensions still cover legacy state.
3. **Sentinel leakage** — a future exporter change could print HTML comments.
   Pinned by the pipeline-survivability test; sentinels are also harmless
   ASCII if ever visible.
4. **Language coverage** — vi/en templates only (matches
   `M5_CHAPTER_TITLES`/`_VI` precedent); other languages fall back to English
   headers, numbers unaffected.
