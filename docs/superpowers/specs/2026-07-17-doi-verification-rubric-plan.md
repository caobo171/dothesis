# DOI Verification in the Quality Rubric — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-doi-verification-rubric-design.md` (read it first — verifier contract, severity table, findings shape, cache/budget numbers, and all out-of-scope calls are defined there)
**Executor notes:** All paths are relative to the dothesis repo root; run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. **Phase 1 (pure dimension + injected verifier, fully offline) lands before any network wiring (Phase 2).** Do not reorder. New tests go in root `tests/` (beside `tests/test_stats_validity_dimension.py` — no Docker needed), not `api/tests/` (its autouse fixture spins a Postgres testcontainer, `api/tests/conftest.py:12–24`). No test in Phase 1 or the unit part of Phase 2 may touch the network — the default code path must make that true without mocking `requests`.

---

## Phase 1 — Pure dimension with injected verifier (offline; no engine-network code exists yet)

### Task 1.1 — Skeleton dimension + DOI normalization/syntax helpers
- **Files:** `quality/rubric.py`, `tests/test_source_verification_dimension.py` (new)
- Tests first:
  - `source_verification_dimension({})` and `..._dimension({"m2_literature": {"literature_sources": []}})` → `{"name": "source_verification", "weight": 0.10, "score": 1.0, "findings": [], "meta": {...}}` with `meta == {"checked": 0, "verified": 0, "unverified": 0, "no_doi": 0, "network_enabled": False}`.
  - Entries without a `doi` key / `doi: None` / `doi: ""` → no findings, `meta.no_doi` counts them (use the shape from `orchestrator/tools/m2_literature.py:219–230`: `{title, authors, year, source, url, doi}`).
  - `_normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"`; `doi:`-prefixed and whitespace-padded variants normalize too.
  - Syntax: `"10.1234/xyz.1"` passes; `"not-a-doi"`, `"http://example.com/paper"`, `"10./broken"` each yield exactly one **soft** finding with `chapter == "lit_review"` and issue text containing "DOI"; malformed DOIs are never counted toward `meta.checked`.
- Implement: `_normalize_doi(doi) -> str`, `_doi_syntax_ok(doi) -> bool` (regex `^10\.\d{4,9}/\S+$`, case-insensitive), and `source_verification_dimension(context_store, doi_verifier=None)` doing only the empty/no-doi/syntax logic; score `max(0.0, 1.0 - 0.1 * len(findings))`.
- **Verify:** `python -m pytest tests/test_source_verification_dimension.py -q`
- **Done when:** green; `python -c "import quality.rubric"` still succeeds with no new module-level imports (lazy-import discipline, `quality/rubric.py:27–28`).

### Task 1.2 — Pure junk checks via the engine validator (lazy, fail-open)
- **Files:** `quality/rubric.py`, `tests/test_source_verification_dimension.py`
- Tests first (all offline — these engine methods are pure, `engine/utils/citation_validator.py:63–102,140–184`):
  - Entry with `authors: ["E. A. W."]` → one soft `author_sanity`-flavored finding (issue text quotes the author).
  - Entry with `title: "example.com"` → one soft junk-metadata finding; `year: 1885` → one soft finding.
  - Clean entry (`{"title": "Real Paper", "authors": ["Smith, J."], "year": 2020, "doi": "10.1234/ok"}`, verifier `lambda d: True`) → zero findings, score 1.0.
  - `authors` given as a string (defensive import-path shape) does not crash.
  - Fail-open: monkeypatch the lazy import target so importing `engine.utils.citation_validator` raises (`monkeypatch.setitem(sys.modules, "engine.utils.citation_validator", None)` or equivalent) → dimension still returns, syntax findings still present, no exception.
- Implement: lazy `from engine.utils.citation_validator import CitationValidator` inside the dimension body wrapped in `try/except Exception` with `logger.exception`; run `check_author_sanity` + `check_metadata_quality` per entry; map each message to a soft finding (`{issue, fix, chapter: "lit_review", severity: "soft"}`).
- **Verify:** `python -m pytest tests/test_source_verification_dimension.py -q`
- **Done when:** green, including the fail-open test.

### Task 1.3 — Injected-verifier DOI verdicts + analytics
- **Files:** `quality/rubric.py`, `tests/test_source_verification_dimension.py`
- Tests first (verifier injected as a plain lambda — never the real one):
  - `doi_verifier=lambda d: False` on one DOI-bearing entry → exactly one **soft** finding (issue mentions the DOI and "CrossRef"; fix mentions doi.org); score 0.9; `meta.checked == 1`.
  - `doi_verifier=lambda d: None` → **zero findings**, score 1.0, `meta.unverified == 1` (network failure must never change the score — design §5).
  - `doi_verifier=lambda d: True` → zero findings, `meta.verified == 1`.
  - Raising verifier (`lambda d: 1/0`) → treated as `None`: no findings, no crash, `meta.unverified` counts it.
  - Verifier receives the **normalized** DOI (capture the arg and assert).
  - `doi_verifier=None` (default) → verifier never invoked (use a sentinel: pass entries with valid-syntax DOIs, assert `meta.checked == 0` and `meta["network_enabled"] is False`).
  - Analytics: monkeypatch `quality.rubric`'s emit call target (`agent.analytics.emit`, precedent `quality/rubric.py:53–56`) with a recorder; assert one `citation_rejected` event per finding with `kind` in `{"invalid_doi", "malformed_doi", "author_sanity", "junk_metadata"}`.
- Implement: Layer B loop per design §3; per-DOI `try/except` mapping exceptions to `None`; emits.
- **Verify:** `python -m pytest tests/test_source_verification_dimension.py -q`
- **Done when:** green; grep confirms no `requests`/network import was added to `quality/rubric.py`.

### Task 1.4 — Wire into `score_thesis` + advisory guarantee
- **Files:** `quality/rubric.py`, `tests/test_source_verification_dimension.py`
- Tests first (stub the judge exactly as `tests/test_stats_validity_dimension.py:63–70` does — `monkeypatch.setattr(rubric, "judge_dimension", ...)`):
  - `score_thesis(cs)` output's `dimensions` includes a dim named `source_verification`; existing dims (`structure`, `citations`, `no_stubs`, `results_validity`, `preflight`, `instrument_quality`, `stats_validity`, `advisor`) all still present.
  - `score_thesis(cs, doi_verifier=lambda d: False)` with a fabricated-DOI pool: the finding appears under `source_verification`, and **`blocking` does not contain it** (everything soft — design §5; `blocking` built at `quality/rubric.py:322`).
  - The `citations` dimension's score/findings are byte-identical with and without `doi_verifier` (separation of concerns — design §5).
- Implement: `score_thesis(..., doi_verifier: Callable | None = None)` keyword-only param; append `source_verification_dimension(context_store, doi_verifier)` after `stats_validity_dimension` and before `apply_institution_overlay` (`quality/rubric.py:318–321`).
- **Verify:** `python -m pytest tests/test_source_verification_dimension.py tests/test_stats_validity_dimension.py -q` **and** the existing api-side rubric suite if the dev env has Docker: `cd api && python -m pytest tests/test_quality_rubric.py -q`
- **Done when:** all green — proving the new dim breaks no existing shape assertion and the default path is still network-free.

---

## Phase 2 — Env-gated real verifier: cache, timeout, budget (still no network in unit tests)

### Task 2.1 — Default-verifier factory behind `DOTHESIS_RUBRIC_DOI_CHECK`
- **Files:** `quality/rubric.py`, `tests/test_source_verification_dimension.py`
- Tests first (network stubbed at the engine boundary, not at `requests`):
  - Flag unset → factory not consulted; `meta.network_enabled is False`.
  - `monkeypatch.setenv("DOTHESIS_RUBRIC_DOI_CHECK", "1")` + `monkeypatch.setattr` on `CitationValidator.validate_doi` returning `False` → soft finding produced without any injected verifier; `meta.network_enabled is True`.
  - Injected `doi_verifier` **wins** over the env flag (resolution order, design §3).
  - Cache: with the flag on and a counting stub, scoring twice over the same pool calls `validate_doi` once per unique DOI (module-level `_DOI_CACHE`, normalized-DOI keys). `None` verdicts are re-attempted after their short TTL — test by faking the stored timestamp, not by sleeping.
  - Budget: a pool of 25 valid-syntax DOIs with the flag on → at most 20 lookups (counting stub); the untested remainder lands in `meta.unverified` with no findings. Wall-clock budget: stub `validate_doi` to advance a monkeypatched clock past 10 s → loop stops early, no crash.
- Implement: `_default_doi_verifier()` factory (lazy `CitationValidator(timeout=3)`, `_DOI_CACHE: dict[str, tuple[bool | None, float]]`, TTLs 24 h / 5 min, 20-lookup + 10 s budgets per design §4); resolution order inside `source_verification_dimension`.
- **Verify:** `python -m pytest tests/test_source_verification_dimension.py -q`
- **Done when:** green with zero real HTTP (assert by monkeypatching `requests.get` in one test to raise `AssertionError("network hit")` while the counting stub is active).

### Task 2.2 — Never-crash under real-world failure modes
- **Files:** `tests/test_source_verification_dimension.py`
- Tests first:
  - Flag on, `CitationValidator.validate_doi` monkeypatched to raise `requests.exceptions.ConnectionError` → dimension returns, zero findings from Layer B, `meta.unverified` counts, `score_thesis` completes.
  - Flag on, engine import forced to fail (as in Task 1.2) → dimension returns with Layer A syntax findings only.
  - Whole-dimension guard: monkeypatch an internal helper to raise mid-loop → `score_thesis` still returns a full result (mirrors `stats_validity_dimension` fail-open, `quality/rubric.py:282–283`).
- Implement: only whatever guard gaps the tests expose.
- **Verify:** `python -m pytest tests/test_source_verification_dimension.py -q`
- **Done when:** green; no code path in the dimension can propagate an exception out of `score_thesis`.

### Task 2.3 — One opt-in real-network integration test
- **Files:** `tests/test_source_verification_integration.py` (new)
- `@pytest.mark.integration` (marker already declared in `pytest.ini`; excluded by default via `-m "not integration"`): with `DOTHESIS_RUBRIC_DOI_CHECK=1`, a pool containing one known-good DOI (`10.1037/0033-2909.126.1.3` — verified live to return `True`) and one syntactically-valid fabricated DOI (e.g. `10.9999/definitely.not.real.2026`) → the good one lands in `meta.verified`, the fabricated one yields exactly one soft finding; total runtime under ~10 s. Tolerate `None` verdicts (skip-assert) so a flaky network doesn't fail CI when the suite is run explicitly.
- **Verify:** `python -m pytest tests/test_source_verification_integration.py -m integration -q` (requires network) and `python -m pytest tests -q` (must **not** collect/run it).
- **Done when:** both commands behave as stated.

---

## Phase 3 — Surfaces and closure

### Task 3.1 — Confirm downstream consumers inherit the dimension safely
- **Files:** none expected (verification task; touch only if something breaks)
- Run the consumer suites that call `score_thesis` (`agent/tools/writing.py:298,307`, `agent/tools/defense.py:107–108`): `cd api && python -m pytest tests/test_quality_rubric.py tests/test_defense.py tests/test_review_tool.py tests/test_eval_harness.py tests/test_model_eval.py -q` (needs Docker for the testcontainer conftest). All must pass with the flag unset — i.e., zero network — and any shape assertion broken by the new dim gets fixed in the **test**, not by weakening the dim.
- **Done when:** green; a quick grep confirms no consumer sets `DOTHESIS_RUBRIC_DOI_CHECK` (rollout stays opt-in per design §8 risk #1 — eval-harness/nightly first, product surfaces later, as a separate ops decision outside this plan).

### Task 3.2 — Docs: mark initiative #5 wired
- **Files:** `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md` (initiative #5 entry: note shipped scope + deferred items — registrar metadata matching, verification-status persistence, doi.org escalation, per design §7), `quality/rubric.py` module docstring (one line: source_verification is offline-by-default, env/injection-gated network).
- **Verify:** `python -m pytest tests/test_source_verification_dimension.py tests/test_stats_validity_dimension.py -q` one final time from a clean shell (no `DOTHESIS_RUBRIC_DOI_CHECK` in the environment).
- **Done when:** docs updated; full offline suite green.
