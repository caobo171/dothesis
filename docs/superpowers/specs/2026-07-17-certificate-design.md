# Committee-Readiness Certificate / Evidence Ledger — Design Spec (roadmap #12)

**Date:** 2026-07-17
**Status:** Design — ready for planning
**Roadmap:** `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md:351-371` (initiative #12, normative)
**Vision:** `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-vision.md` §4 (:202-224), §5 (:225-260), §6 (:263-289)
**Depends on (ALL SHIPPED):** #1 stats self-validation, #2 power, #3 screening, #5 DOI→rubric, #6 coherence, #11 similarity
**Companion plan:** `2026-07-17-certificate-plan.md`

---

## 1. Problem and goal

Roadmap #12 (roadmap:353-363): *"Trust artifacts today are internal (rubric JSON,
tool logs). A student, advisor, or B2B partner cannot see the chain that makes a
DoThesis thesis different from ChatGPT output. … Every export ships with a
machine-checkable appendix + shareable report: per-source verification status,
per-number provenance (op, dataset hash, timestamp, validation pass), power
computation, screening summary, coherence attestation, similarity result — the
vision-§6 checklist rendered with evidence. For B2B this is the product."*

This initiative builds **no new checks**. Every chain it renders already exists
and already emits findings. #12 is a *rendering + provenance-capture* layer:

1. an **append-only provenance ledger** capturing, at the `run_stats` boundary,
   where each computed number came from (op, dataset hash, timestamp,
   validation pass) — and, at the `commit_slice` boundary, a durable per-project
   summary of which committed numbers that ledger covers;
2. a **certificate assembler**: one bounded, deterministic JSON that renders the
   vision-§6 checklist with evidence, plus a `gate_summary` contract for B2B
   callers and a renderable appendix for the export;
3. **honesty as schema**: coverage and limitations are first-class fields; the
   certificate reports what was actually checked, never more (vision principles
   1–2, vision:227-234).

Two binding principles from the vision govern every decision below:
**never fabricate** and **everything traceable** (vision:227-234); plus
**advisory, not blocking** (vision:240-244) — the ledger and certificate never
block a commit or an export.

---

## 2. Verified inventory — what exists to render (grounded 2026-07-17)

| Chain | Where | What the certificate consumes |
|---|---|---|
| Verified numbers: compute | `agent/tools/stats.py:366-385` `OPS` whitelist (`pls_sem`/`efa`/`regression_full`/`mediation`/`moderation`/`rigor`/`power`/`screening`/`method_advice`/`mga`/`ipma`); every op returns a bounded summary | op names + summaries (via ledger capture, §4) |
| Verified numbers: self-validation | `run_stats` attaches `validation: {passed, hard, soft, findings}` to every result (`agent/tools/stats.py:511-520` → `agent/stats_validation.py:324-330` → `libs/thesis-stats/src/thesis_stats/validation.py`); claim shape `make_claim` (validation.py:64-80), finding shape (:36-60) | per-row `validation` block; claim extraction for value matching |
| Verified numbers: commit gate | M4 hard gate in `agent/tools/state_tools.py:98-127` — `hard` findings **block** `analysis_results` commits; M5 prose-number gate :128-162 | "every persisted number passed validation" attestation |
| Verified sources | ingestion cascade `engine/utils/api_citations/` (crossref, openalex, semantic_scholar, europe_pmc, eric, …); rubric `source_verification` dimension `quality/rubric.py:347-427` with `meta = {checked, verified, unverified, no_doi, network_enabled}` | the `meta` counts + findings; the "CrossRef only, opt-in network" caveat is already encoded (:291-295) |
| Coherence (#6) | `agent/coherence.py` (pure, offline); rubric dim `quality/rubric.py:430-452`; hard prose-number contradictions block at M5 commit (state_tools.py:144-157) | coherence findings + hard/soft counts |
| Similarity (#11) | `quality/similarity.py:367-392` `similarity_report` — bounded, `headline` deliberately `null`, `coverage_note` says "NOT a Turnitin scan" (:384-387); already attached to export payload (`agent/tools/writing.py:274-289`) | the report verbatim — its honesty wording is the template for ours |
| Power (#2) | `run_stats(op="power")` → `libs/thesis-stats/src/thesis_stats/power.py` — `required_n`/`achieved_power` + a committee-ready `justification` sentence (:244-254) | ledger `attest` extract (§4.3) |
| Screening (#3) | `run_stats(op="screening")` → `screening.py:385-436` with deterministic `narrative`; persisted `analysis_results.data_screening` is validated at commit (`agent/stats_validation.py:281-287`) | persisted block or ledger attest |
| Method advisor (#7, shipped) | `run_stats(op="method_advice")` → `agent/method_advisor.py:212-231` (`recommendation` ranking, `conflicts`) + `inputs_fingerprint` (`agent/tools/stats.py:361`) | ledger attest: top recommendation, conflict count |
| Rubric aggregate | `quality/rubric.py:472-514` `score_thesis` → `{overall, method, dimensions[], advisor, blocking[]}`; `blocking` = all hard findings (:509); method detection :517-525 | the aggregation spine (§6) |
| Export path | `agent/tools/writing.py:36-300` `export_docx` (full path attaches `similarity` :274-289); `orchestrator/tools/m5_writing.py:2127-2156` `run_export`, `_upload_to_s3` :72-94, `_artifact_dict` :2117-2123; `DbProjectStateStore.persist_export_artifacts` `api/app/agent_state.py:293-324` (arbitrary `kind` string) | where the certificate artifact ships (§7) |
| B2B path | `api/app/partner_run.py:191+` `run_partner_export`; routers in `api/app/routers/` (e.g. `exports.py`, `partner_report.py`) | `gate_summary` consumers (§6.3) |

### 2.1 What `ProjectStateStore` already captures — and what it doesn't

Verified provenance facts that drive the placement decision (§3):

- **Version snapshots exist but are NOT durable in prod.** The file store
  snapshots the full pre-commit state per commit (`agent/state.py:298-305`,
  capped at 50, :108), but `DbProjectStateStore.load()` returns
  `"versionHistory": []` with the comment *"Version snapshots are in-turn only
  for now; durable history lands in the version_history table in a follow-up"*
  (`api/app/agent_state.py:151-155`). A ledger riding `versionHistory` would
  pass file-store tests and **vanish in prod**.
- **The `decisions` trail is the proven durable-audit mechanism.** `decisions`
  is owned by every module (`agent/state.py:54-66`), written only by
  deterministic code (`agent/headless.py:19-56` `record_decision`), stripped
  from model-authored writes at the tool edge (`agent/tools/state_tools.py:73-82`),
  hidden from `read_slice` (`agent/state.py:203-209`), and never earns a `done`
  (`NON_CONTENT_KEYS`, `agent/state.py:86-93`). `DbProjectStateStore._save`
  persists it automatically because it iterates `SLICE_OWNERSHIP`
  (`api/app/agent_state.py:189-195`). The codebase's own rule: *"An audit trail
  is only worth anything if the thing being audited can't write it"*
  (state.py:62-66, state_tools.py:76-80).
- **Timestamps + reasons exist per commit** (snapshot `ts`/`reason`/`module`,
  state.py:298-304) but carry no dataset hash, no op identity, no validation
  outcome — the *what* is versioned, the *where-from* is not. That gap is
  exactly what the ledger adds.
- `run_stats` is a **stateless module-level tool** — registered directly, not
  via a store-bound factory (`agent/runtime.py:173`, :508), so it cannot write
  project state. Its one existing mutation precedent is workspace-local:
  `_op_screening` writes `<stem>_screened.csv` next to the source file
  (`agent/tools/stats.py:328-331`, "the ONLY mutation path").

---

## 3. Decision D1 — ledger placement (the #1 decision)

**Decision: two layers, both riding existing machinery. (a) A workspace-local
append-only JSONL sidecar written by `run_stats` at capture time; (b) a bounded,
durable `analysis_provenance` summary key — M4-owned, `NON_CONTENT` — injected
by deterministic code at the M4 `commit_slice` gate.** No new store methods, no
new DB table, no new tool.

Options considered:

| Option | Verdict | Why |
|---|---|---|
| Ride `versionHistory` | **Rejected** | Not persisted in prod (`api/app/agent_state.py:151-155`) — the exact `project_db_store_persistence_gap` failure mode the codebase warns about three separate times (state.py:26-31, :59-62, headless.py:28-31). |
| Ride the `decisions` list | **Rejected (shape), adopted (mechanism)** | `decisions` rows are `{options, choice, rationale}` auto-decision audits (headless.py:42-48) with existing consumers; overloading them with provenance rows corrupts that contract. But its *mechanism* — an owned `NON_CONTENT` key written only by deterministic code, persisted for free by both stores — is exactly right, so we clone it. |
| New DB table / store method | **Rejected** | A store-specific write path is the known CRITICAL gap (works in file-store tests, silently diverges in prod); also violates "state is the interface" (vision:249-252). |
| **New M4-owned `NON_CONTENT` key `analysis_provenance` + workspace sidecar** | **Adopted** | Persists via the same `SLICE_OWNERSHIP` iteration that already carries `decisions` and `field_it_*` into the `m4_analysis` column (agent_state.py:189-195 for `_save`, :129-138 for `load`); the model cannot author it (stripped at state_tools.py:81-82 once listed in `NON_CONTENT_KEYS`); it never earns a `done` (state.py:123-131); zero new persistence code. |

**Why two layers.** Capture and durability have different homes:

- **Capture** must happen where the number is born — inside `run_stats`, which
  is stateless and (in production) runs in the network-less sandbox
  (`agent/tools/stats.py:1-8`). It cannot call `commit_slice`. So capture
  writes a sidecar `stats_provenance.jsonl` next to the data file — the same
  posture as `_screened.csv` (stats.py:328-331): workspace-local, no network,
  no new whitelist surface, deterministic code only (the `run_stats` wrapper,
  never an op, never the model).
- **Durability** must live in the DB, because the workspace's lifetime is not
  guaranteed across deploys while the `m4_analysis` column is. At the M4 commit
  gate — where deterministic code already runs validation and coherence
  (state_tools.py:98-142) — we read the sidecar, match committed numbers
  against ledger rows (§5), and inject the bounded `analysis_provenance`
  summary into the same commit's writes. One commit, no extra focus/status side
  effects, durable in prod by construction.

**Never blocks (binding).** Sidecar append failure, ledger read failure, and
matching failure are all fail-open advisory (`try/except` + `logger.exception`,
the exact pattern of the validation ride-along at stats.py:511-520). The only
hard gates remain the two that exist today (impossible numbers, contradicting
prose — state_tools.py:116-122, :149-157). Roadmap #12's ledger is "advisory
capture only"; a provenance bug must never cost a student a commit.

### 3.1 State-model changes (complete list)

- `agent/state.py`: add `"analysis_provenance"` to `SLICE_OWNERSHIP["M4"]`
  (:49-51) and to `NON_CONTENT_KEYS` (:93). Nothing else — every property we
  need (model-edge strip, read_slice hiding, done-gate exclusion, Db
  persistence/round-trip) follows from those two set memberships, each already
  unit-tested for `decisions`.

---

## 4. The provenance ledger

### 4.1 Sidecar file

- **Path:** `Path(file).with_name("stats_provenance.jsonl")` — next to the data
  file the op ran on (precedent: stats.py:328-331). Ops invoked with no `file`
  (a-priori `power`, design-time `method_advice` — stats.py:287-302, :337-341)
  cannot be ledgered: the workspace root is not resolvable from inside the
  stateless tool, so there is nowhere deterministic to write. Their evidence
  enters via later data-time reruns or the persisted `analysis_results` block;
  recorded as a limitation (§8) and revisited if `run_stats` ever becomes a
  store-bound factory.
- **Format:** JSON Lines, UTF-8, one row per successful `run_stats` op return.
  Append-only with a hard cap: on append, if the file exceeds **1000 rows**,
  rewrite keeping the newest 1000. Each row carries a monotonically increasing
  `seq` (previous max + 1); pruning is detectable as `min(seq) > 1` — the
  certificate must report `pruned: true` when it is (§8, honesty).
- **Written by:** deterministic code in the `run_stats` wrapper
  (stats.py:445-521), after the op succeeds and validation has been attached.
  Never by an op, never by the model (no tool writes it; the filesystem backend
  the model sees is a different surface — `agent/runtime.py:491-498` — and the
  matcher treats sidecar content as *evidence to verify against recomputable
  digests*, not as trusted assertions; see tamper note in §5).

### 4.2 Row schema

```jsonc
{
  "seq": 17,
  "ts": "2026-07-17T09:14:02.113Z",          // capture wall-clock (provenance, not identity)
  "op": "pls_sem",                            // whitelisted op name (stats.py OPS)
  "dataset": {                                // null when op ran file-less
    "file": "uploads/survey_final.csv",       // workspace-relative as passed to run_stats
    "sha256": "<64 hex>",                     // streamed hash of the raw file bytes
    "rows": 214, "cols": 32                   // shape from the loaded frame
  },
  "params_fp": "<12 hex>",                    // sha256 of canonical-JSON params (sorted keys)
  "result_digest": "<12 hex>",                // sha256 of canonical-JSON summarized result
  "values": [                                 // value index for matching (§5), capped at 400
    ["beta", -0.31, "TRUST -> INT"],          // [metric, value(4dp), unit-label|null]
    ["ave", 0.62, "TRUST"], ...
  ],
  "attest": { ... },                          // small op-typed extract (§4.3), ≤ 1 KB
  "validation": {"passed": true, "hard": 0, "soft": 1},
  "engine": "thesis_stats 0.6.0"              // libs/thesis-stats __init__.__version__
}
```

- `values` is built by reusing `claims_from_run_stats(op, summary)`
  (`agent/stats_validation.py:55-96`) — the exact extraction validation already
  performs — reduced to `(metric, round(value, 4), unit-label)` triples.
  No new number-walking code; the validator and the ledger can never disagree
  about what a result "contains".
- **Dataset hash** = SHA-256 over the raw file bytes, streamed in 1 MiB chunks
  (survey files are small; `_BOOTSTRAP_CAP`-sized PLS runs dominate runtime,
  not hashing — stats.py:127). Bytes, not parsed frame: byte identity is the
  strongest reproducibility claim we can make without re-running, and it's
  representation-independent of pandas versioning. `rows`/`cols` ride along as
  a human-legible cross-check. Computed inside the wrapper (once per call),
  never inside ops.
- **Determinism:** capture adds no randomness — every field is a pure function
  of (op, params, file bytes, result, clock). `ts` is provenance metadata, not
  identity; `result_digest`/`params_fp` are the identity and are clock-free.

### 4.3 `attest` extracts (per op, bounded)

The certificate needs a few op outcomes verbatim, not just digests:

| op | attest fields |
|---|---|
| `power` | `mode`, `analysis`, `required_n` / `achieved_power` (power.py:113-213), first 300 chars of `justification` (:244-254) |
| `screening` | `n_before`, `n_after`, `mcar_p` if present, `applied` flags, `derived_file` (stats.py:316-333) |
| `method_advice` | top `recommendation` entry, `len(conflicts)`, `inputs_fingerprint` (method_advisor.py:212-231, stats.py:361) |
| `mga` | `comparison_defensible` (pls_advanced.py:265-272) |
| `pls_sem`/others | `bootstrap_samples`, `q2` present (bool) — nothing more; the numbers live in `values` |

---

## 5. Provenance matching at the M4 commit gate

New pure module `agent/provenance.py` (no LangChain, no LLM, stdlib +
`hashlib`; I/O confined to two small read/append helpers), called from the
existing M4 branch of `commit_slice` in `agent/tools/state_tools.py` (after the
validation gate at :98-127, before `store.commit_slice`):

1. `claims = claims_from_analysis_results(writes["analysis_results"])`
   (`agent/stats_validation.py:214-302`) — the same claim set the gate already
   validates.
2. Load ledger rows: `store.project_dir` (both stores anchor the workspace —
   `api/app/agent_state.py:46-50`) globbed for `stats_provenance.jsonl`
   (bounded `rglob`, depth ≤ 3, ≤ 20 files).
3. Classify each claim into a **provenance tier**:
   - **`computed`** — matches a ledger row `values` entry: same `metric`, and
     value equal after rounding the ledger value to the claim's precision
     (parsed claims are 2dp, computed 4dp — mirror `_DEFAULT_DECIMALS`,
     `libs/thesis-stats/src/thesis_stats/validation.py:31`). Matching requires
     the unit-label to agree (normalized via `_norm_path`,
     `agent/stats_validation.py:25-28`) whenever **both** sides carry one;
     value-only matching is allowed only for unit-less claims and **never for
     `p`, `n`, `df`, `bootstrap_samples`** (too collision-prone — a bare 0.05
     must not inherit provenance).
   - **`validated`** — no ledger match, but the claim passed this commit's
     validation gate (true for every committed structured claim unless the
     validator crashed). This is the tier for pasted/parsed SmartPLS/SPSS
     numbers: *checked for internal consistency, but DoThesis did not compute
     them* — the honest middle.
   - **`unchecked`** — free-text results (`agent/stats_validation.py:338-345`)
     or validator crash (`crashed: true`).
4. Inject the summary into the same commit:

```jsonc
"analysis_provenance": {
  "captured_at": "...",
  "coverage": {"total": 40, "computed": 28, "validated": 12, "unchecked": 0},
  "by_table": {"structural_model": {"computed": 9, "validated": 0}, ...},
  "datasets": [{"file": "...", "sha256_12": "...", "rows": 214, "cols": 32}],
  "ledger": {"rows_seen": 17, "seqs_matched": [3,4,9], "pruned": false},
  "ops_seen": {"pls_sem": 2, "power": 1, "screening": 1},
  "validation": {"hard": 0, "soft": 2, "crashed": false},
  "unmatched": ["beta TRUST -> SAT", ...]     // ≤ 10 labels, for the drill/report
}
```

Bounded: ≤ ~4 KB regardless of project size (`seqs_matched` ≤ 50, `unmatched`
≤ 10, `by_table` keyed by the fixed table vocabulary). Injection happens after
the model-edge `NON_CONTENT` strip (state_tools.py:81-82), so a model-supplied
`analysis_provenance` is discarded before deterministic code writes the real
one — the audit-trail rule holds by ordering.

**Tamper posture.** The model can, via the filesystem tools, read the sidecar
and could in principle edit it (the backend roots at the project dir,
runtime.py:491-498). Defense: the matcher only *upgrades* a claim's tier —
a forged row could at worst mark a *validated* number as *computed*. The number
itself still had to pass the hard validation gate to be committed at all, so
tampering cannot launder an impossible number; it can only overstate the
compute share. Real integrity (row signing / hash-chaining) is **deferred**
(§9); v1 adds a cheap tamper-evidence field: each row's `result_digest` must
re-derive from... nothing we retain — so v1 explicitly documents this as a
limitation in the certificate (`limitations[]`, §8) rather than pretending.
Honest > impressive.

---

## 6. The certificate

### 6.1 Assembler — decision D3 (deterministic vs `score_thesis`)

**Decision: `score_thesis` is the spine; the certificate adds a parameter, not
a fork.** Add `include_judge: bool = True` to `score_thesis`
(`quality/rubric.py:472-514`): when `False`, the two `judge_dimension` calls
(:482-485 — the only LLM in the rubric) are skipped. Everything else in the
rubric is already deterministic (structure, citations, stubs, results_validity,
preflight, instrument, stats_validity, source_verification, coherence,
similarity, advisor). New module `quality/certificate.py`:

```python
def build_certificate(context_store, *, institution_profile=None,
                      advisor_feedback=None, doi_verifier=None,
                      rubric=None) -> dict          # pure over inputs, never raises
def gate_summary(certificate) -> dict               # pure projection, bounded
def render_certificate_md(certificate) -> str       # deterministic markdown, no LLM
```

- `rubric=None` ⇒ the assembler calls
  `score_thesis(context_store, ..., include_judge=False)` itself — the default
  certificate is **fully deterministic**: same state in, byte-same certificate
  out (modulo `generated_at`). Callers that already ran the full rubric (e.g.
  `review_thesis`, writing.py:302-327) may pass it in; judge dimensions, when
  present, land only in the `advisory` block and **never** affect `readiness`
  or `gate_summary` — the B2B guarantee is deterministic per principle 5
  (vision:245-248).
- Read-only over the **nested** context store (`load_full_context_store`
  shape, agent_state.py:157-171), exactly like the rubric — so chat, headless,
  and partner paths share one certificate for one state (vision principle 6).
- `analysis_provenance` is read from `m4_analysis.analysis_provenance` (it
  persists there via §3.1). No sidecar I/O in the assembler — it must run in
  the API process against DB state alone.

### 6.2 Certificate JSON schema (the machine-checkable appendix)

```jsonc
{
  "schema_version": 1,
  "kind": "dothesis.certificate",
  "generated_at": "2026-07-17T10:00:00Z",
  "project_id": "…",
  "thesis": {"title": "…", "language": "vi", "method": "pls-sem"},   // rubric.py:517-525
  "engine": {"thesis_stats": "0.6.0", "rubric": "deterministic", "judge_included": false},

  "readiness": {
    "status": "ready" | "not_ready",
    "overall_score": 0.87,                    // score_thesis overall (deterministic dims)
    "blocking": ["…"]                         // score_thesis blocking (rubric.py:509)
  },

  "checklist": [                              // vision §6, one entry per box
    {
      "id": "sources_verified",
      "title": "Every bibliography source is verification-passed",
      "status": "pass" | "warn" | "fail" | "not_checked",
      "coverage": {"checked": 18, "total": 25},      // omitted where N/A
      "evidence": [ {"kind": "rubric_dim", "name": "source_verification",
                     "meta": {...}, "findings_hard": 0, "findings_soft": 2} ],
      "limitations": ["DOI existence checked against CrossRef only; …"]
    },
    ...
  ],

  "provenance": {                             // §5 summary, verbatim from state
    "numbers": {"total": 40, "computed": 28, "validated": 12, "unchecked": 0},
    "datasets": [...], "ledger": {...}, "ops_seen": {...},
    "note": "computed = calculated by DoThesis from the student's data file and
             matched to a ledger row; validated = supplied by the student and
             checked for internal consistency only; unchecked = free-text."
  },

  "advisory": {                               // NEVER feeds readiness/gate_summary
    "similarity": { ...similarity_report verbatim... },   // similarity.py:367-392
    "judge_dimensions": null | [...],
    "advisor_directives": {"total": 3, "addressed": 2, "open": 1}
  },

  "limitations": [ ... ],                     // §8 — mandatory strings, first-class
  "attestation": "…one deterministic paragraph: what DoThesis checked, on what
                  evidence, and what it explicitly did not check…",
  "content_sha256": "<64 hex>"                // hash of the certificate minus this
                                              // field + generated_at — tamper-EVIDENCE
                                              // for the shipped JSON, not a signature
}
```

**Checklist items** (ids fixed; each maps to a vision-§6 box and names its
evidence source):

| id | vision box (vision:268-287) | evidence | status logic |
|---|---|---|---|
| `rq_hypothesis_trace` | 1 | `m3_design.hypotheses` present; gap links when the schema carries them | `warn` at best in v1 (semantic gap-trace is the judge's job — deterministic check is existence + non-empty), `not_checked` when hypotheses absent |
| `sources_verified` | 2 | `source_verification` dim `meta` + findings (rubric.py:347-427) | `pass` if no findings and `verified == checked > 0`; `warn` on soft findings or `network_enabled: false`; `not_checked` if pool empty |
| `citation_integrity` | 2 | `citations` dim (rubric.py:44-63) | `fail` on any uncited (hard) finding |
| `method_justified` | 3 | ledger `method_advice` attest (via `ops_seen` + persisted rows) | `pass` if advice ran with 0 conflicts; `warn` with conflicts; `not_checked` if never run |
| `power_defended` | 4 | ledger `power` attest, or a power block inside `analysis_results` | `pass` (a-priori), `warn` (post-hoc only — "disclosed as limitation"), `not_checked` |
| `screening_documented` | 5 | `analysis_results.data_screening` (validated at commit, stats_validation.py:281-287) or ledger `screening` attest | `pass`/`warn`/`not_checked`; `not_checked` when no dataset exists is *normal*, not a failure |
| `measurement_model_reported` | 6 | `analysis_results.measurement_model` + `stats_validity` dim | `fail` on hard validity findings; `warn` on soft ("breaches surfaced, not buried" is a PASS with `warn` wording, per the vision box) |
| `hypotheses_decided` | 7 | `coverage_findings` via the coherence module (stats_validation.py:347-352) + `stats_validity` | `fail` if a hypothesis lacks a decision; `pass` when all decided from validated numbers |
| `chapters_coherent` | 8 | `coherence` dim (rubric.py:430-452) | `fail` on hard (prose contradicts persisted numbers), `warn` on soft |
| `similarity_selfchecked` | 9 | `similarity` dim + report (rubric.py:455-469) | `pass` when the check ran (findings are always soft by design — similarity is never `fail`); `not_checked` when no prose |
| `defense_drilled` | 10 | — none persisted (drill state is conversational, `agent/tools/defense.py`) | **always `not_checked` in v1**; listed in `limitations` and §9 |

`readiness.status = "ready"` iff `blocking` is empty **and** no checklist item
is `fail`. `not_checked` and `warn` never block readiness — they are reported,
loudly (advisory-not-blocking, vision:240-244).

### 6.3 `gate_summary` — the B2B contract

A bounded (< 2 KB), fully deterministic projection for machine callers
(`api/app/partner_run.py` consumers and a thin new route):

```jsonc
{
  "schema_version": 1,
  "project_id": "…",
  "generated_at": "…",
  "ready": true,
  "deterministic": true,                      // always true; judge dims are excluded by construction
  "items": [ {"id": "sources_verified", "status": "pass", "blocking": false}, ... ],  // all 11, fixed order
  "blocking": ["…"],                          // hard-finding strings, ≤ 20
  "coverage": {
    "numbers": {"computed": 28, "validated": 12, "unchecked": 0, "total": 40},
    "sources": {"verified": 18, "checked": 18, "total": 25}
  },
  "certificate": {"content_sha256": "…", "artifact": "projects/<pid>/exports/certificate.json" | null}
}
```

The guarantee this makes to a B2B caller — and the only one: *for this exact
project state, these deterministic checks produced these statuses; re-running
against the same state reproduces this summary byte-for-byte (minus
`generated_at`).* It does **not** claim the thesis is good, plagiarism-free, or
committee-approved; the `items` vocabulary is the whole claim.

---

## 7. Render surfaces

1. **Export payload + artifact (the main surface, mirrors #11).** In
   `export_docx`'s full-export path (`agent/tools/writing.py`, beside the
   similarity attach at :274-289): best-effort build the certificate, then
   (a) attach `certificate: gate_summary(cert)` to the tool's return payload
   (bounded — the full JSON is too big for a tool return), and (b) ship the
   full JSON as an export artifact: new helper `export_certificate_json(cert,
   project_id)` in `orchestrator/tools/m5_writing.py` using the existing
   `_upload_to_s3` (:72-94) + `_artifact_dict(kind="certificate", …)`
   (:2117-2123), persisted through `persist_export_artifacts`
   (agent_state.py:293-324 — `kind` is a plain string column, no schema
   change). Any failure here is logged and the export succeeds without a
   certificate (fail-open, exactly like similarity).
2. **Docx appendix (the human-readable appendix).** `render_certificate_md`
   produces a deterministic markdown section (checklist table, provenance
   counts, limitations verbatim); the full-export path appends it as a section
   `{"title": "Appendix — DoThesis Verification Report", "prose": …}` before
   calling `run_export`. Numbers in this prose come from the certificate, which
   comes from persisted state — the renderer-over-verified-state rule
   (vision:165-173). Appendix on full exports only; module-scoped exports
   (writing.py:114-184) get no certificate in v1 (§9).
3. **Web view / "verified by DoThesis" page.** In scope: the JSON contract only
   — the §6.2 schema **is** the contract (`schema_version` governs it), served
   by a thin route `GET /projects/{pid}/gate-summary` (new
   `api/app/routers/certificate.py`, auth mirroring `routers/exports.py`)
   returning `gate_summary`, plus the `certificate.json` artifact via the
   existing exports download route. Client rendering is out of scope, exactly
   as #11 left the run-drawer wiring (writing.py:277-279).

---

## 8. Honesty design (first-class, non-negotiable)

The certificate's credibility is the product; overclaiming once destroys it.
Encoded as schema, not as tone:

1. **`not_checked` is a real status**, rendered as prominently as `pass`. A
   certificate with eight `not_checked` items is a *true* certificate of a
   young project.
2. **Coverage everywhere a count exists**: `N of M` for sources
   (`checked/total` from the dim's `meta`), numbers (`computed/validated/
   unchecked/total`), hypotheses (decided/total). Never a bare checkmark over
   a partial check.
3. **Mandatory `limitations[]` strings** (exact wording fixed by test):
   - similarity: reuse `similarity_report.coverage_note` verbatim — "This is
     NOT a Turnitin scan and cannot substitute for one"
     (quality/similarity.py:384-387);
   - sources: "DOI existence is checked against CrossRef only; DataCite/arXiv
     DOIs can 404 there. Metadata sanity is heuristic." (per rubric.py:291-295);
   - provenance: "`validated` numbers were supplied by the student (pasted or
     parsed output) and checked for internal consistency; DoThesis did not
     compute them and cannot attest their origin.";
   - ledger: when `pruned: true` — "the provenance ledger was truncated; early
     computations are not individually attested";
   - integrity: "This certificate is not cryptographically signed;
     `content_sha256` detects accidental alteration only.";
   - defense: "Defense-drill completion is not yet recorded and is not
     attested.";
   - when the certificate was built without network (`network_enabled: false`):
     "Source verification ran offline; DOI existence was not re-checked."
4. **The attestation paragraph is assembled from the above** — template + facts,
   no free text, no LLM. Nothing in the certificate is generated prose.
5. **Nothing fabricated, everything traceable**: every checklist `evidence`
   entry names its source (`rubric_dim` name, ledger `seq`s, persisted block
   path) so a human can walk from any certificate line to the state that
   produced it (vision:231-234).

---

## 9. Deferred (explicit non-goals of v1)

- **Real cryptographic signing** of certificate or ledger rows (key management,
  hash-chained rows). v1 ships `content_sha256` tamper-evidence only, and says
  so in `limitations`.
- **Hosted verification endpoint / public "verified by DoThesis" page** — the
  JSON contract ships; the marketing surface and any tokenized public URL do
  not.
- **Per-number provenance for pasted/parsed numbers** — they cap at the
  `validated` tier by construction; upstream capture (e.g. hashing the parsed
  SmartPLS export file in `parse_smartpls_export`) is a natural v2.
- **Defense-drill attestation** (`defense_drilled` stays `not_checked` until
  #10's drill persists state).
- **Certificates for module-scoped/partner-subset exports** — full exports
  only in v1; `gate_summary` is still available for any project state via the
  route.
- **Ledger backfill for legacy projects** — projects analyzed before this
  ships show `computed: 0` honestly.
- **Client/web rendering** of the certificate page and run-drawer chip.

---

## 10. Risks

1. **#1 risk — coverage will look bad, and the design must make bad-looking
   honest.** Most existing projects entered numbers via the parse path
   (SmartPLS/SPSS pastes), so `computed` will be 0 and many items
   `not_checked`. If the certificate reads as a failure grade, students and
   partners will reject the feature or pressure it into overclaiming. The
   three-tier provenance vocabulary (§5), `not_checked`-as-normal (§8.1), and
   the fixed limitation strings exist precisely to make a low-coverage
   certificate a truthful artifact instead of a scarlet letter. The renderer
   (`render_certificate_md`) must lead with what *was* verified.
2. **Workspace durability.** If the sandbox/API workspace is ephemeral, sidecar
   rows vanish; mitigated by design — the durable artifact is the
   `analysis_provenance` summary captured at commit time in the same session,
   and the certificate never reads the sidecar (§6.1). Certificate correctness
   degrades to `validated`-tier honesty, never to a wrong claim.
3. **Value-match false positives** could overstate `computed`. Mitigated by
   unit-label requirement + the `p`/`n`/`df` exclusion (§5.3); tested with
   adversarial fixtures.
4. **Schema churn.** `schema_version: 1` from day one; `gate_summary` is the
   stable subset; additive-only evolution within a major.
