# Committee-Readiness Certificate / Evidence Ledger — Implementation Plan (roadmap #12)

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-certificate-design.md` (read it first — the placement decision §3, ledger row schema §4.2, matching tiers §5, certificate schema §6.2, `gate_summary` §6.3, and the mandatory honesty strings §8.3 are normative there; this plan only sequences them).
**Executor notes:** All paths relative to the dothesis repo root; run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. Tests live in top-level `tests/` (`pytest.ini`: `testpaths = tests`, `-m "not integration"`); everything in this plan is offline — no network, no LLM calls, no `integration` marker. Ordering is deliberate: the deterministic assembler first (Phase 1 — pure, testable against synthetic state, no wiring), then ledger capture (Phase 2), then the export/gate-summary surfaces (Phase 3). Do not reorder.

**Hard constraints (from the design — enforce by test, not comment):**
- Nothing in this initiative ever blocks a commit or an export. Every new code path is `try/except` fail-open with `logger.exception` (pattern: `agent/tools/stats.py:511-520`, `agent/tools/writing.py:274-282`).
- `quality/certificate.py` is pure over its inputs and never raises from a public entry point; default assembly makes **zero** LLM calls (`include_judge=False`) and **zero** network calls (no `doi_verifier` unless injected).
- The model can never author `analysis_provenance` (rides `NON_CONTENT_KEYS` — same rule as `decisions`, `agent/state.py:54-66`, `agent/tools/state_tools.py:73-82`).
- Determinism: same state in → byte-identical certificate out, excluding `generated_at` (assert by building twice and diffing with the timestamp field removed).
- Bounds: `analysis_provenance` ≤ ~4 KB (`seqs_matched` ≤ 50, `unmatched` ≤ 10); ledger row `values` ≤ 400 entries; ledger file capped at 1000 rows; `gate_summary` < 2 KB serialized.
- Value-only matching NEVER applies to `p`, `n`, `df`, `bootstrap_samples` (design §5.3).

---

## Phase 1 — deterministic certificate assembler (`quality/certificate.py`)

Pure functions over a nested context_store (the `load_full_context_store` shape, `api/app/agent_state.py:157-171`). No ledger I/O, no store, no wiring — Phase 1 is fully testable with dict fixtures.

### Task 1.1 — `score_thesis(include_judge=...)` parameter
- **Files:** `quality/rubric.py`, `tests/test_certificate_rubric_spine.py` (new)
- Tests first:
  - `score_thesis(cs, include_judge=False)` returns a result whose `dimensions` contain **no** `methodology`/`writing` judge dims (the only two LLM dims, `quality/rubric.py:482-485`) and all ten deterministic dims (structure, citations, no_stubs, results_validity, advisor, preflight, instrument_quality, stats_validity, source_verification, coherence, similarity).
  - With `include_judge=False`, no LLM is constructed: monkeypatch `orchestrator.tools.m5_writing._get_llm` to raise; the call must still succeed (proves the judge path is skipped, not just tolerated).
  - Default `include_judge=True` preserves today's behavior byte-for-byte on a fixture store (regression guard for `review_thesis`, `agent/tools/writing.py:302-327`): existing suites `tests/test_stats_validity_dimension.py`, `tests/test_source_verification_dimension.py`, `tests/test_coherence_dimension.py`, `tests/test_similarity.py` stay green in this same task.
  - `blocking` aggregation (`rubric.py:509`) unchanged in both modes.
- **Verify:** `python -m pytest tests/test_certificate_rubric_spine.py tests/test_stats_validity_dimension.py tests/test_source_verification_dimension.py tests/test_coherence_dimension.py -q`
- **Done when:** green; `git diff quality/rubric.py` shows only the parameter + conditional around the two judge appends.

### Task 1.2 — checklist item builders
- **Files:** `quality/certificate.py` (new), `tests/test_certificate_checklist.py` (new)
- Tests first (one test class per item; fixtures are synthetic nested stores):
  - The 11 fixed item ids in the design-§6.2 table, in fixed order, each `{id, title, status, evidence, limitations}` (+ `coverage` where the table says so). Status enum exactly `pass|warn|fail|not_checked`.
  - `sources_verified`: maps the `source_verification` dim's `meta` (`quality/rubric.py:355`, `{checked, verified, unverified, no_doi, network_enabled}`) into `coverage`; `warn` when `network_enabled` is false; `not_checked` on an empty pool.
  - `power_defended`: `pass` from an `analysis_results` power block or a provenance `ops_seen.power` (pass a stubbed `analysis_provenance` in the fixture — Phase 1 does not read ledgers); `warn` for post-hoc-only; `not_checked` otherwise.
  - `screening_documented`: `not_checked` with **no dataset** is not `fail` (assert the status and that no blocking string is produced).
  - `measurement_model_reported`: hard `stats_validity` finding ⇒ `fail`; soft ⇒ `warn` (breaches surfaced = still creditable, per vision:277-279).
  - `hypotheses_decided`: a hypothesis without a decision (drive via `agent.coherence.coverage_findings`, reached through `agent/stats_validation.py:347-352` semantics) ⇒ `fail`.
  - `similarity_selfchecked`: can never be `fail` (all similarity findings are soft by design — assert over a fixture with maximal findings).
  - `defense_drilled`: **always** `not_checked` in v1, with its limitation string.
- **Verify:** `python -m pytest tests/test_certificate_checklist.py -q`
- **Done when:** green; a subprocess `python -c "import quality.certificate"` succeeds with `langchain` absent from `sys.modules` (precedent: similarity plan Task 1.1).

### Task 1.3 — `build_certificate`
- **Files:** `quality/certificate.py`, `tests/test_certificate_build.py` (new)
- Tests first:
  - Full schema shape per design §6.2: `schema_version: 1`, `kind: "dothesis.certificate"`, `thesis.method` from `_detect_method` (`rubric.py:517-525`), `readiness`, `checklist`, `provenance`, `advisory`, `limitations`, `attestation`, `content_sha256`.
  - `readiness.status == "ready"` iff `blocking` empty AND no checklist `fail`; `warn`/`not_checked` never unready (assert both directions with fixtures).
  - `provenance` block passed through verbatim from `m4_analysis.analysis_provenance` when present; when absent → `{"numbers": {"total": 0, ...}}` shape with the tier `note` string still present.
  - `advisory.similarity` embeds `similarity_report(cs_flat_or_nested)` (`quality/similarity.py:367-392`) and its `coverage_note` appears verbatim in top-level `limitations`.
  - **Mandatory honesty strings** (design §8.3): exact-substring asserts for the Turnitin, CrossRef-only, validated-tier, unsigned-certificate, and defense-drill strings; the pruned-ledger string appears iff `ledger.pruned` is true; the offline string iff `network_enabled` is false.
  - Determinism: build twice on the same fixture, delete `generated_at` from both, `assert a == b`; `content_sha256` recomputes correctly (hash of canonical JSON minus `content_sha256` + `generated_at`).
  - Never raises: a garbage store (`{"m4_analysis": "not a dict"}`), and a monkeypatched `score_thesis` that raises, both yield a degraded-but-valid certificate (`readiness.status: "not_ready"` with an explanatory limitation), not an exception.
  - `rubric=` injection: passing a precomputed full-judge rubric puts judge dims under `advisory.judge_dimensions` and provably does NOT change `readiness` or any checklist status versus the deterministic build.
- **Verify:** `python -m pytest tests/test_certificate_build.py -q`
- **Done when:** green.

### Task 1.4 — `gate_summary`
- **Files:** `quality/certificate.py`, `tests/test_gate_summary.py` (new)
- Tests first:
  - Pure projection of a certificate per design §6.3: all 11 items in fixed order, `deterministic: true` always, `blocking` capped at 20, `coverage.numbers` + `coverage.sources` present, `certificate.content_sha256` echoes the parent.
  - `len(json.dumps(gate_summary(cert)))` < 2048 even for a certificate built from a maximal fixture (50 blocking findings, huge unmatched lists).
  - `ready` mirrors `readiness.status`.
  - Round-trip stability: `gate_summary(build_certificate(cs))` twice → identical minus `generated_at`.
- **Verify:** `python -m pytest tests/test_gate_summary.py -q`
- **Done when:** green.

### Task 1.5 — `render_certificate_md`
- **Files:** `quality/certificate.py`, `tests/test_certificate_render.py` (new)
- Tests first:
  - Deterministic markdown (two renders byte-equal); contains the checklist as a table with all 11 ids, the provenance counts as "N of M" phrasing, and every `limitations` string verbatim.
  - Leads with verified content: the first section after the heading lists `pass` items before `warn`/`fail`/`not_checked` (design risk §10.1 — a low-coverage certificate must read as truthful, not as a failure grade).
  - No LLM, no network: import-light assert as in Task 1.2; renders a fully-`not_checked` certificate without error and without the word "fail" appearing for `not_checked` items.
  - Output bounded: < 8000 chars on the maximal fixture.
- **Verify:** `python -m pytest tests/test_certificate_render.py -q`
- **Done when:** green. **Phase 1 exit:** `python -m pytest tests/ -q -k "certificate or gate_summary"` green, full suite green.

---

## Phase 2 — provenance ledger capture

### Task 2.1 — pure row builder (`agent/provenance.py`)
- **Files:** `agent/provenance.py` (new), `tests/test_provenance_rows.py` (new)
- Tests first:
  - `dataset_fingerprint(path) -> {file, sha256, rows, cols} | None`: streamed sha256 over raw bytes (write a small CSV tmpfile, assert against `hashlib.sha256(file_bytes)`); `rows`/`cols` optional args supplied by the caller (the wrapper already has the frame); missing file → `None`, never raises.
  - `build_ledger_row(op, params, summary, dataset, seq) -> dict` per design §4.2: `values` built by reusing `claims_from_run_stats` (`agent/stats_validation.py:55-96`) reduced to `[metric, round(value, 4), unit_label]` triples, capped at 400; `params_fp`/`result_digest` are sha256-12 of canonical JSON (`sort_keys=True`, `ensure_ascii=False`); `validation` lifted from the summary's attached block (stats.py:517-519) or `{"passed": null}` when absent; `engine` carries `thesis_stats.__version__`.
  - `attest` extracts per the design-§4.3 table — one test per op for `power` (required_n + justification ≤ 300 chars), `screening` (n_before/after, `derived_file`), `method_advice` (top recommendation, conflict count, `inputs_fingerprint` — stats.py:361), `mga` (`comparison_defensible`); `pls_sem` attest ≤ 1 KB.
  - Determinism: same inputs → identical row minus `ts`/`seq`.
- **Verify:** `python -m pytest tests/test_provenance_rows.py -q`
- **Done when:** green; `python -c "import agent.provenance"` clean without langchain in `sys.modules`.

### Task 2.2 — sidecar append + read (`agent/provenance.py`)
- **Files:** `agent/provenance.py`, `tests/test_provenance_sidecar.py` (new)
- Tests first:
  - `append_ledger_row(data_file_path, row)` writes JSONL at `Path(file).with_name("stats_provenance.jsonl")` (precedent: `_op_screening`'s `_screened.csv`, `agent/tools/stats.py:328-331`); assigns `seq` = previous max + 1; two appends → seqs 1, 2.
  - Cap: appending row 1001 rewrites keeping the newest 1000; `min(seq) > 1` afterward (the pruned signal, design §4.1).
  - Fail-open: read-only directory (chmod the tmpdir), corrupt existing file (garbage line) — append returns `False`/logs, never raises; corrupt lines are skipped by the reader, valid ones survive.
  - `load_ledger_rows(project_dir) -> list[dict]`: bounded discovery (`rglob` depth ≤ 3, ≤ 20 files), merged and seq-sorted per file; a huge decoy tree doesn't blow up (bound asserted with a counting monkeypatch).
- **Verify:** `python -m pytest tests/test_provenance_sidecar.py -q`
- **Done when:** green.

### Task 2.3 — capture at the `run_stats` boundary
- **Files:** `agent/tools/stats.py`, `tests/test_run_stats_ledger.py` (new)
- Tests first (invoke the real `run_stats` tool on tmp CSV fixtures, in-process):
  - A successful `run_stats(op="describe", file=...)` appends exactly one ledger row next to the file with correct `op`, `dataset.sha256`, and `validation`; the tool's JSON return is unchanged in shape (existing callers unaffected — assert the return parses and has no new required field).
  - An op **error** return (`{"error": ...}`) appends nothing; a file-less a-priori `power` call appends nothing (design §4.1).
  - Capture happens **after** validation attach: the row's `validation` equals the returned `validation` block for an op forced (via monkeypatched validator) to emit a soft finding.
  - Fail-open: monkeypatch `agent.provenance.append_ledger_row` to raise → `run_stats` still returns its normal payload (mirror of the validation fail-open test pattern).
  - Ops never write the ledger themselves: grep-style test asserting `stats_provenance` appears in `stats.py` only inside the wrapper function body (cheap structural guard, mirrors "the whitelist IS the boundary" posture).
- **Verify:** `python -m pytest tests/test_run_stats_ledger.py -q`
- **Done when:** green; existing `run_stats` tests green.

### Task 2.4 — state model: the `analysis_provenance` key
- **Files:** `agent/state.py`, `tests/test_state_provenance_key.py` (new, or extend `agent/tests/test_state_tools.py` conventions — note agent has its own `agent/tests/`; follow where the existing SLICE_OWNERSHIP tests live)
- Tests first:
  - `"analysis_provenance"` ∈ `SLICE_OWNERSHIP["M4"]` and ∈ `NON_CONTENT_KEYS` — and the four properties that must follow: (a) `commit_slice("M4", {"analysis_provenance": ...})` accepted from deterministic code; (b) `read_slice("M4")` does NOT expose it (state.py:203-209); (c) it never earns a `done` (`confirm_done` with only `analysis_provenance` written raises the empty-done error, state.py:283-294); (d) the model-edge wrapper strips it from model writes (state_tools.py:81-82) — commit via the tool with a forged `analysis_provenance` in `writes`, assert the persisted value is absent/unchanged.
  - Db round-trip: extend the existing `api/tests/test_headless_db_roundtrip.py` pattern — a saved `analysis_provenance` lands in the `m4_analysis` column and survives `load()` (the `SLICE_OWNERSHIP` lift, `api/app/agent_state.py:129-138`, :189-195).
- **Verify:** `python -m pytest agent/tests/ api/tests/test_headless_db_roundtrip.py -q` (adjust to the repo's actual agent/api test invocation — `agent/tests/` and `api/tests/` exist alongside top-level `tests/`)
- **Done when:** green; no other `state.py` diff than the two set memberships (design §3.1).

### Task 2.5 — matcher + injection at the M4 commit gate
- **Files:** `agent/provenance.py` (matcher), `agent/tools/state_tools.py` (injection), `tests/test_provenance_matching.py` (new)
- Tests first — matcher (`match_claims(claims, ledger_rows) -> summary` per design §5):
  - Tier `computed`: a beta claim `(beta, -0.31, "TRUST -> INT")` matches a ledger `values` entry after `_norm_path` normalization; a 2dp parsed claim matches a 4dp ledger value after rounding the ledger side to the claim's precision (`_DEFAULT_DECIMALS` convention, `libs/thesis-stats/src/thesis_stats/validation.py:31`).
  - Unit discipline: same value under a *different* path does NOT match when both sides carry units; unit-less claims may value-match — but **never** for `p`/`n`/`df`/`bootstrap_samples` (adversarial fixture: a ledger containing 0.05 must not grant a p-claim `computed`).
  - Tiers `validated`/`unchecked`: unmatched structured claims → `validated`; a crashed-validator commit or free-text results → `unchecked` (drive via `validate_analysis_results` shapes, `agent/stats_validation.py:333-355`).
  - Summary bounds and shape per design §5.4: `coverage` totals sum to `total`; `seqs_matched` ≤ 50; `unmatched` ≤ 10; `pruned` propagated; serialized ≤ 4 KB on a maximal fixture.
- Tests — injection (via the `commit_slice` tool wrapper with a file-store + tmp workspace):
  - An M4 commit of `analysis_results` whose numbers exist in a planted sidecar → persisted state contains `analysis_provenance` with `computed > 0`; the tool's returned JSON gains nothing model-facing (summary is state-only, not payload — keep the return contract stable).
  - Injection ordering: a model-forged `analysis_provenance` in the same `writes` is discarded and replaced by the deterministic summary (extends Task 2.4d).
  - The hard validation gate still fires first: an impossible-number commit is blocked (state_tools.py:116-122) and writes **no** provenance.
  - Fail-open: matcher raising (monkeypatch) → commit succeeds without `analysis_provenance`.
  - Non-M4 commits and M4 commits without `analysis_results` are untouched (no ledger I/O — assert via monkeypatched `load_ledger_rows` call counter).
- **Verify:** `python -m pytest tests/test_provenance_matching.py agent/tests/ -q`
- **Done when:** green; existing `agent/tests/test_state_tools.py` green unchanged. **Phase 2 exit:** an end-to-end offline test — `run_stats(pls_sem)` on a tiny fixture CSV → commit its summarized results via the tool → `build_certificate` over the resulting nested store shows `provenance.numbers.computed > 0`.

---

## Phase 3 — surfaces: export, gate-summary API

### Task 3.1 — certificate artifact helper (engine side)
- **Files:** `orchestrator/tools/m5_writing.py`, `tests/test_certificate_artifact.py` (new)
- Tests first:
  - `export_certificate_json(cert: dict, project_id: str) -> dict`: serializes canonical JSON to a tmp file, uploads via the existing `_upload_to_s3` (:72-94; monkeypatch `s3_from_env`), returns `_artifact_dict("certificate", pid, s3_key, size)` (:2117-2123) with key `projects/<pid>/exports/certificate.json`.
  - Raises are contained by the *caller* (next task) — this helper may raise on S3 failure like its docx/pdf siblings.
- **Verify:** `python -m pytest tests/test_certificate_artifact.py -q`
- **Done when:** green.

### Task 3.2 — `export_docx` full-path integration
- **Files:** `agent/tools/writing.py`, `tests/test_export_certificate.py` (new)
- Tests first (drive the `export_docx` tool with a stub store exposing `project_id`, `load`, `load_full_context_store`, `persist_export_artifacts`, and monkeypatched `run_export`/`export_certificate_json` — mirror however the existing similarity-attach tests stub this tool):
  - Full export: payload gains `"certificate": <gate_summary dict>` beside the existing `similarity` field (writing.py:283-300); `persist_export_artifacts` receives the certificate artifact; the docx `sections` passed to `run_export` include a final `{"title": "Appendix — DoThesis Verification Report", "prose": render_certificate_md(...)}` section, and the appendix's numbers came from persisted state (fixture-check one count).
  - `chapter_count`/`chapters` in the payload do NOT count the appendix (the return-honesty rule at writing.py:266-269 — the agent must not claim 7 chapters).
  - Module-scoped export (`scope="M3"`): **no** certificate, no appendix (design §7.2 — v1 full exports only).
  - Fail-open ×3: `build_certificate` raising, `export_certificate_json` raising, `render_certificate_md` raising — each still yields `ok: true` with `certificate: null` and the export artifacts intact.
  - `include_judge` is False on this path (assert no `_get_llm` construction, as in Task 1.1).
- **Verify:** `python -m pytest tests/test_export_certificate.py -q`
- **Done when:** green; existing export tests green.

### Task 3.3 — `review_thesis` surfacing (chat)
- **Files:** `agent/tools/writing.py`, `tests/test_review_gate_summary.py` (new)
- Tests first:
  - `review_thesis` payload gains a `gate_summary` field built from the same `score_thesis` result it already computes (pass the full-judge rubric via `rubric=`; assert judge dims still do not affect item statuses — the Task 1.3 invariant, re-proven at this surface).
  - Fail-open: certificate failure leaves the existing rubric payload untouched.
- **Verify:** `python -m pytest tests/test_review_gate_summary.py -q`
- **Done when:** green.

### Task 3.4 — B2B route: `GET /projects/{pid}/gate-summary`
- **Files:** `api/app/routers/certificate.py` (new), router registration in `api/app/main.py`, `api/tests/test_gate_summary_route.py` (new)
- Tests first (FastAPI test client, following `api/app/routers/exports.py` auth/ownership conventions exactly — same dependency stack, same 404-on-foreign-project behavior):
  - Returns `gate_summary(build_certificate(store.load_full_context_store(), ...))` for an owned project; `deterministic: true`; institution profile + advisor feedback read through the store's typed getters (`agent/state.py:179-189`), never `getattr` (the documented store bug, state.py:170-175).
  - No LLM and no network on this route (monkeypatch guards on `_get_llm` and the DOI verifier builder).
  - Unauthorized / foreign project → the same status codes `exports.py` produces.
  - `certificate.artifact` is null when no certificate export exists yet (the route never triggers an export).
- **Verify:** `python -m pytest api/tests/test_gate_summary_route.py -q`
- **Done when:** green.

### Task 3.5 — partner-run exposure + final sweep
- **Files:** `api/app/partner_run.py`, `tests/`/`api/tests/` touch-ups
- Tests first:
  - `run_partner_export` (`api/app/partner_run.py:191+`) attaches `gate_summary` to its return dict (advisory field; a certificate failure must not fail a paid export — fail-open test).
  - **Honesty regression fixture:** one integration-style offline test building a certificate for (a) a parse-path project (numbers committed without any ledger) → `computed: 0`, `validated > 0`, readiness unaffected by coverage, all mandatory limitation strings present; (b) a compute-path project → `computed > 0`. This pair is the design's #1-risk guard (design §10.1) — it pins that low coverage degrades wording, never correctness.
  - Full suite: `python -m pytest tests/ -q` and the agent/api suites green; `python -m pytest -q -k "certificate or provenance or gate_summary"` as the initiative's named slice.
- **Verify:** commands above.
- **Done when:** everything green; `docs/superpowers/specs/2026-07-17-certificate-design.md` §9 deferred list still accurate (no scope creep — no signing, no public page, no client wiring, no drill attestation shipped).

---

## Explicitly out of scope (do not implement, per design §9)

Cryptographic signing / hash-chained ledger rows; hosted verification endpoint or public "verified by DoThesis" page; provenance capture for `parse_smartpls_export` / `parse_output_table` inputs; `defense_drilled` evidence; certificates on module-scoped exports; ledger backfill for legacy projects; any web client rendering.
