# DOI Verification in the Quality Rubric — Design Spec

**Date:** 2026-07-17
**Status:** Design — ready for implementation (companion plan: `2026-07-17-doi-verification-rubric-plan.md`)
**Owner:** cao.nv17@gmail.com
**Roadmap:** Initiative #5 in `docs/superpowers/specs/2026-07-17-dothesis-vertical-agent-roadmap.md` (Phase 1, "Wire DOI/metadata verification into the quality rubric", roadmap lines 166–185)
**Vision anchors:** `2026-07-17-dothesis-vertical-agent-vision.md` §4(2) — the **verified-sources chain**: "search → multi-API verification → reference pool → citation-integrity rubric → (end-state) DOI-verified bibliography in the export"

---

## 1. Motivation

The engine verifies sources at **ingestion** — the M2 scout routes queries
through a multi-API cascade (`engine/utils/api_citations/`: `crossref.py`,
`openalex.py`, `semantic_scholar.py`, `europe_pmc.py`, `eric.py`,
`gemini_grounded.py`, orchestrated by `CitationResearcher` at
`engine/utils/api_citations/orchestrator.py:134` with per-query API-chain
routing at `orchestrator.py:376–377`). But the **final gate** attests less
than the ingestion path guarantees: the rubric's citations dimension
(`quality/rubric.py:57–63`) only checks that in-text `(Author, Year)`
citations appear in the `literature_sources` pool. A source that entered the
pool by student paste, mid-journey import (`orchestrator/backfill.py:226–231`
writes the same key), or metadata drift is never re-verified. **The rubric
cannot tell a real DOI from a fabricated one.**

The engine already has exactly the verifier we need —
`engine/utils/citation_validator.py` — currently used only by
`engine/utils/citation_quality_filter.py` (lines 19, 248, 490) and a CLI
`main()`. This initiative wires it into the rubric as a new deterministic
dimension, closing the pool→world hole in the verified-sources chain.

---

## 2. Current state (verified in code)

### 2.1 The citations dimension only checks prose→pool linkage

- `quality/rubric.py:26–75` — `deterministic_dimensions(context_store)`
  builds three dims: `structure`, `citations`, `no_stubs`.
- `quality/rubric.py:45` — pool read:
  `(context_store.get("m2_literature") or {}).get("literature_sources") or []`.
- `quality/rubric.py:46–47` — delegates to `validate_citations_plain`
  (`orchestrator/tools/m5_writing.py:131–155`): pure regex extraction of
  `(Author, Year)` from prose, set-membership against pool keys built from
  each entry's author/year (`_ref_citation_key`). No DOI is ever read.
- `quality/rubric.py:57–63` — the `citations` dim: weight 0.20, uncited
  citations become **hard** findings ("possible fabrication"), score
  `1.0 - 0.1 * len(uncited)`.
- `quality/rubric.py:53–56` — analytics precedent: each rejected citation
  emits `agent.analytics.emit("citation_rejected", None, {"kind": "uncited",
  ...})`; `agent/analytics.py:15–22` makes `emit` a no-op until the app
  rebinds it.

### 2.2 Pool entry shape — every entry can carry a `doi`, none is guaranteed to

- `orchestrator/tools/m2_literature.py:219–230` — the M2 scout maps engine
  `Citation` objects to dicts: `{title, authors, year, source, url, doi}`
  (docstring at line 157). `doi` is `getattr(c, "doi", None)` — may be
  `None`.
- `orchestrator/backfill.py:226–231` — grounding backfill writes the same
  normalized dicts into `literature_sources` (and mirrors `citation_list`);
  `orchestrator/tests/test_backfill_grounding.py:70` confirms entries carry
  `doi`.
- The rubric's own test fixture shows entries may lack the key entirely:
  `api/tests/test_quality_rubric.py:23` — `{"title": "P", "authors":
  ["Smith"], "year": 2020}` with no `doi`. **The dimension must treat a
  missing/empty `doi` as "nothing to verify", never as a finding.**

### 2.3 The engine validator API (`engine/utils/citation_validator.py`)

- `CitationValidator(timeout: int = 10)` — line 29; CrossRef base
  `https://api.crossref.org/works/` at line 37.
- `validate_doi(doi) -> Optional[bool]` — lines 39–61. Strips
  `https://doi.org/` prefixes (line 50), GETs CrossRef. Returns **`True`**
  (exists), **`False`** (CrossRef 404), **`None`** (network error — "assume
  DOI might be valid", line 60). Measured live: ~0.9 s per lookup.
  **Network.**
- `check_author_sanity(authors) -> list[str]` — lines 63–102. Pure regex:
  repetitive initials, same first/last name, initials-only, domain-as-author.
  **No network.**
- `check_metadata_quality(citation) -> list[str]` — lines 140–184. Pure:
  domain-as-title, author-duplicates-title, error-keyword URLs, year out of
  range, placeholder titles. **No network.**
- `validate_citation(citation) -> list[ValidationIssue]` — lines 186–291.
  Composite; includes the network DOI check **and** per-URL HTTP HEAD checks
  (`validate_url_status`, lines 104–138). We deliberately do **not** call
  this composite from the rubric (see §7 — URL checks are too slow for the
  gate); we call the three granular pieces above.
- `ValidationIssue` dataclass — lines 16–24: severity `'critical' |
  'warning' | 'info'`. The rubric maps to its own `hard | soft` vocabulary
  (§5), it does not reuse these strings.

### 2.4 Import layering — the validator is already reachable from the rubric

`deterministic_dimensions` lazily imports `orchestrator.tools.m5_writing`
first thing (`quality/rubric.py:29–31`), and `m5_writing.py:28–40` inserts
**both** the repo root and `engine/` onto `sys.path`. Therefore
`from engine.utils.citation_validator import CitationValidator` works
anywhere the rubric already runs (verified by direct import + pure-check
execution). `citation_validator.py` itself imports only `requests` + stdlib
(lines 7–13) — no transitive `utils.*` engine imports — so the lazy import is
cheap and safe. The `quality` package keeps its zero-dependency contract
(`quality/pyproject.toml`: `dependencies = []`) because the import is lazy
and fail-open.

### 2.5 Global constraints the design must honor

- **Never crash:** `judge_dimension` docstring (`quality/rubric.py:186–188`)
  and `stats_validity_dimension`'s fail-open `except` block
  (`quality/rubric.py:282–283`) are the precedents.
- **Read-only:** the rubric "is read-only over a nested context_store, so it
  can never corrupt a thesis" (`quality/rubric.py:1–4`). No
  verification-status field is persisted onto pool entries in this
  initiative (roadmap #5 mentions one; that belongs to an ingestion-side
  change — see §7).
- **No network in unit tests:** root `pytest.ini` runs `-m "not
  integration"` with `integration: tests requiring external API/network
  access`; the rubric's api-side tests stub the LLM judge with an autouse
  fixture ("F0: no test may hit a live model",
  `api/tests/test_quality_rubric.py:7–18`); the initiative-#1 dimension
  tests live at root `tests/test_stats_validity_dimension.py` and are fully
  offline.
- **Advisory-not-blocking, except provably wrong:** roadmap lines 69–73 —
  `hard` = impossible, and hard-blocking is "the one justified exception to
  advisory-not-blocking, because an impossible number is a fabrication with
  extra steps." `score_thesis` folds every `hard` finding into `blocking`
  (`quality/rubric.py:322`).

### 2.6 Callers that inherit the new dimension automatically

`score_thesis` is called by the agent's grade tool
(`agent/tools/writing.py:298,307`), the defense drill
(`agent/tools/defense.py:107–108`), and the eval harness / model eval
(`quality/eval_harness.py`, `quality/model_eval.py`). All get
`source_verification` for free; all must keep working offline by default.

---

## 3. Design overview

One new deterministic dimension in `quality/rubric.py`:

```python
def source_verification_dimension(context_store: dict,
                                  doi_verifier: Callable[[str], bool | None] | None = None) -> dict:
    ...
```

appended in `score_thesis` alongside the other dims (after
`stats_validity_dimension`, before the institution overlay,
`quality/rubric.py:318–321`), and `score_thesis` grows a keyword-only
passthrough parameter `doi_verifier=None`.

The dimension has two layers:

**Layer A — pure offline checks (always on).** For every pool entry:

1. **DOI syntax** (new ~5-line helper in `quality/rubric.py`): after
   stripping `https://doi.org/` / `http://doi.org/` / `doi:` prefixes and
   whitespace, a non-empty `doi` that does not match
   `^10\.\d{4,9}/\S+$` (case-insensitive) → one soft finding
   ("malformed DOI"). Empty/missing `doi` → no finding, counted in
   `meta.no_doi`.
2. **Author sanity** — `CitationValidator.check_author_sanity(entry.get("authors") or [])`
   (`engine/utils/citation_validator.py:63–102`). Each returned message → one
   soft finding. Entries whose `authors` is a string (defensive: import paths
   vary) are wrapped in a list.
3. **Junk metadata** — `CitationValidator.check_metadata_quality(entry)`
   (`engine/utils/citation_validator.py:140–184`). Each message → one soft
   finding. (The method reads keys `title/authors/url/year` with `.get`
   defaults, so the pool dict shape from §2.2 is accepted as-is.)

Layer A needs one lazily-imported `CitationValidator` instance; constructing
it does no I/O (`__init__` sets two attributes, lines 29–37).

**Layer B — DOI existence (network, off by default).** Only for entries whose
DOI passed the syntax check, call a **verifier callable**
`(doi: str) -> bool | None` with `validate_doi` semantics (§2.3):

- `False` (registrar says the DOI does not exist) → **soft** finding per §5.
- `None` (network failure / timeout / verifier raised) → **no finding**;
  counted in `meta.unverified`.
- `True` → no finding; counted in `meta.verified`.

The verifier is resolved in this order:

1. **Injected:** the `doi_verifier` argument, when not `None`. This is the
   test seam and the hook for future callers that already have a verifier.
2. **Env-enabled:** if `os.getenv("DOTHESIS_RUBRIC_DOI_CHECK") == "1"`,
   build the default verifier: `CitationValidator(timeout=3).validate_doi`
   wrapped with the cache + budget of §4. (Env-flag test/ops seam precedent:
   `M2_SCOUT_TOPIC_COUNT`, `orchestrator/tools/m2_literature.py:160–165`.)
3. **Disabled (the default):** Layer B is skipped entirely; `meta` records
   `"network_enabled": false`. **This is the path every unit test and every
   default production call takes.**

### Why this mechanism (vs. the alternatives)

- *Recorded HTTP fixtures (VCR/responses)* — roadmap #5's "rough scope"
  suggests recorded fixtures. Rejected for the scoring path: it adds a test
  dependency the repo doesn't have, and it tests `requests` plumbing the
  engine already owns. The rubric's job is the **mapping** from verifier
  verdicts to findings; a three-valued injected callable
  (`lambda d: False`) tests that mapping exactly, with zero network and zero
  new deps — the same philosophy as the autouse `_get_llm` stub
  (`api/tests/test_quality_rubric.py:7–18`) and the `judge_dimension`
  monkeypatch (`tests/test_stats_validity_dimension.py:63–70`). One opt-in
  `@pytest.mark.integration` test covers the real CrossRef wiring (plan
  Phase 2), consistent with `pytest.ini`'s marker.
- *Always-on network with a try/except* — rejected: `score_thesis` is called
  synchronously from the grade tool and the defense drill (§2.6); at ~0.9 s
  per CrossRef lookup a 40-source pool would add ~35 s to every grade, and
  the eval harness would hammer CrossRef. Default-off with explicit opt-in
  keeps the gate cheap (roadmap #5: "Cached + rate-limited so the gate stays
  cheap") and keeps `-m "not integration"` runs hermetic by construction,
  not by mocking.
- *Constructor/config object* — over-engineered for one callable; a
  `Callable[[str], bool | None]` is the whole contract.

---

## 4. Cache, timeout, budget (the default verifier only)

All of this lives inside the default-verifier factory in `quality/rubric.py`;
injected verifiers bypass it (tests stay deterministic).

- **Timeout:** `CitationValidator(timeout=3)` — 3 s per request instead of
  the validator's default 10 (`citation_validator.py:29`).
- **Cache:** module-level `_DOI_CACHE: dict[str, tuple[bool | None, float]]`
  keyed by the normalized DOI (prefix-stripped, lowercased). TTL: 24 h for
  `True`/`False` verdicts, 5 min for `None` (transient failures should
  retry soon; verdicts are stable). Rationale: `score_thesis` runs repeatedly
  over the same pool (grade tool, defense drill, nightly eval), and the
  engine's own researcher caches API results for the same reason
  (`engine/utils/api_citations/orchestrator.py:259` `_load_cache`). In-process
  dict only — no file persistence (the rubric is read-only, §2.5).
- **Budget:** per `score_thesis` call, at most **20 uncached lookups** and a
  **10 s wall-clock budget** (checked before each lookup). Once either is
  exhausted, remaining DOIs are counted in `meta.unverified` with no
  findings. Sequential calls + budget is sufficient rate-limiting for
  CrossRef's public pool; no shared limiter is needed (out of scope, §7).
- **Fail-open everywhere:** the entire Layer B loop (and the engine import
  itself) sits in `try/except Exception` with `logger.exception`, mirroring
  `stats_validity_dimension` (`quality/rubric.py:282–283`). A raising
  injected verifier is treated as `None` per DOI.

---

## 5. Severity policy

**Every finding in this dimension is `soft` in v1. Nothing here ever enters
`blocking`.**

| Signal | Severity | Rationale |
|---|---|---|
| DOI positively 404s at CrossRef (`validate_doi → False`) | **soft** | Strong evidence, not proof. `validate_doi` checks **only** `api.crossref.org` (`citation_validator.py:37,53`); DataCite, mEDRA, and many arXiv-issued DOIs legitimately 404 there. Initiative #1's binding principle (roadmap lines 69–73) reserves `hard` for the *provably* wrong; a CrossRef 404 is not proof of fabrication. Finding text says so and tells the student what to do. |
| DOI unverifiable (network failure, timeout, budget exhausted; `None`) | **no finding** | Advisory-not-blocking is absolute here: a flaky network must never change a student's score. Recorded in `meta.unverified` only, so the defense drill can still say "N sources could not be verified". |
| Malformed DOI syntax (pure check) | soft | Provably not a DOI, but it's a metadata-hygiene defect of a pool entry, not a fabricated claim in prose. The prose-side hard-severity precedent (`quality/rubric.py:60–62`) targets citations with *no* pool entry; this is a pool entry with a bad field. |
| Author-sanity / junk-metadata patterns (pure checks) | soft | Heuristics (regex patterns), explicitly not proofs — the engine itself labels several of these "likely" (`citation_validator.py:75`). |

**Escalation path (v2, out of scope):** a DOI that 404s at CrossRef **and**
at the `doi.org` resolver is provably nonexistent and could then justify
`hard` under the initiative-#1 principle. Deferred until a second resolver is
wired (see §7); v1 stays uniformly soft, which also means shipping this
dimension can never regress anyone's `blocking` list.

### Findings shape

Exactly the rubric shape (`{issue, fix, chapter, severity}`):

```python
{"issue": 'Source "Smith (2020) — Title…": DOI 10.1234/xyz not found at CrossRef (possible fabrication or non-CrossRef registrar).',
 "fix": "Check the DOI on doi.org; correct it, replace the source, or confirm it is registered outside CrossRef.",
 "chapter": "lit_review", "severity": "soft"}
```

**Chapter is `"lit_review"`**, matching the rubric's chapter vocabulary
(`_ALL_CHAPTERS`, `quality/rubric.py:12`) and the existing literature-side
finding in `apply_institution_overlay` (`quality/rubric.py:181`). (The
initiative brief said chapter "literature"; the codebase has no such chapter
id — `lit_review` is the grounded spelling.)

### Scoring, weight, dimension identity

- **Separate dimension named `source_verification`** (roadmap #5's own
  name), **not** folded into `citations`. Rationale: (a) it answers a
  different question — `citations` is prose→pool linkage, this is
  pool→world validity; (b) `citations`' hard-severity semantics and score
  formula stay untouched (back-compat with
  `api/tests/test_quality_rubric.py:36–41` and the institution overlay,
  which targets the `citations` dim *by name* at `quality/rubric.py:177`);
  (c) the defense drill consumes per-dimension findings, and a distinct
  name gives "two of your sources could not be verified — expect the
  question" (roadmap #5 outcome) its own bucket.
- **Weight 0.10** — same band as the other advisory dims (`preflight`,
  `instrument_quality`, `no_stubs`). Weights are normalized by total
  (`_weighted`, `quality/rubric.py:250–254`), so adding a dim is safe.
- **Score:** `max(0.0, 1.0 - 0.1 * len(findings))` — the
  `instrument_quality` formula (`quality/rubric.py:153`): a couple of soft
  issues leaves a usable-but-flagged score. Empty pool → score 1.0, no
  findings (nothing to verify is not a defect; the min-references
  requirement is the overlay's job, `quality/rubric.py:172–182`).
- **`meta` key (additive):** the returned dim dict carries
  `"meta": {"checked": int, "verified": int, "unverified": int,
  "no_doi": int, "network_enabled": bool}`. Safe: consumers read only
  `name/weight/score/findings` (`_weighted` at 250–254, `blocking` at 322);
  extra keys serialize harmlessly and give the defense drill its counts.

### Analytics

Mirror `quality/rubric.py:53–56`: one
`emit("citation_rejected", None, {"kind": <k>, "citation": <id/title>})` per
finding, with `kind ∈ {"invalid_doi", "malformed_doi", "author_sanity",
"junk_metadata"}` — breakdown-able alongside the existing `"uncited"` kind.
`agent.analytics.emit` is a safe no-op until the app wires it
(`agent/analytics.py:15–22`).

---

## 6. Offline-testable architecture (summary of the contract)

1. **Default = pure.** With no injected verifier and the env flag unset, the
   dimension performs zero network I/O — Layer A only. No test needs to mock
   `requests` to stay hermetic.
2. **Tests inject.** `source_verification_dimension(cs, doi_verifier=lambda
   d: False)` exercises the nonexistent-DOI path; `lambda d: None` the
   unverifiable path; `lambda d: True` the clean path; a raising lambda the
   fail-open path. `score_thesis(cs, doi_verifier=...)` passes it through.
3. **Env-gated wiring is tested without network** by monkeypatching
   `CitationValidator.validate_doi` (the engine class is importable in the
   test env, §2.4) and setting `DOTHESIS_RUBRIC_DOI_CHECK=1` via
   `monkeypatch.setenv`.
4. **One real-network test** is marked `integration` and excluded by default
   (`pytest.ini` addopts).
5. Test files live at root `tests/` beside
   `test_stats_validity_dimension.py` (no Docker/Postgres needed there,
   unlike `api/tests/` whose autouse fixture spins a testcontainer,
   `api/tests/conftest.py:12–24`).

---

## 7. Out of scope (explicitly)

- **Re-architecting the engine cascade.** `engine/utils/api_citations/*`
  (CrossRef/OpenAlex/Semantic Scholar/Europe PMC/ERIC/Gemini-grounded
  routing, caching, rate limiting) is untouched. The rubric consumes one
  method of one class.
- **Registrar metadata matching** (title/author/year match "within
  tolerance", roadmap #5 outcome). v2 — it needs the CrossRef *response
  body*, not just the status code, and a tolerance design of its own.
- **URL liveness checks** (`validate_url_status`,
  `citation_validator.py:104–138`). Per-source HTTP HEADs are too slow for
  the gate and mostly duplicate the DOI signal.
- **Persisting a verification-status field onto pool entries** (roadmap #5
  "rough scope"). The rubric is read-only by contract
  (`quality/rubric.py:1–4`); write-side status belongs to an M2/ingestion
  initiative.
- **A second resolver (doi.org) and hard-severity escalation** — v2, §5.
- **Cross-process/persistent caching or shared rate limiting** — the
  in-process TTL cache + budget is enough for the gate's call pattern.

---

## 8. Risks

1. **#1 — enabling `DOTHESIS_RUBRIC_DOI_CHECK=1` in a synchronous product
   path.** The grade tool and defense drill call `score_thesis` inline
   (§2.6); at ~0.9 s per uncached lookup, a large pool could add up to the
   10 s budget to every grade. Mitigations: the budget cap is absolute, the
   24 h cache makes repeat grades cheap, and the rollout recommendation is
   **eval-harness / nightly first**, product surfaces only after latency is
   observed. The flag defaulting to off means nothing changes until someone
   opts in.
2. **False-positive soft findings on non-CrossRef DOIs** (DataCite/arXiv)
   depressing the score by 0.1 each. Bounded: soft-only, floor at 0, finding
   text names the possibility, and the fix text points at doi.org.
3. **Junk in the `doi` field** (URLs, "n/a", stray text) from paste/import
   paths. Handled: the syntax pre-filter (Layer A #1) catches these as
   `malformed_doi` and keeps them away from the network path.
4. **Engine import failure in exotic deployments** (engine not on path).
   Handled: lazy import inside `try/except` → Layer A silently degrades to
   the syntax check only, dimension still returns (never-crash).
