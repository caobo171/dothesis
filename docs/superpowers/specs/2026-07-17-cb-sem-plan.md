# CB-SEM Compute (`cb_sem` op) — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-cb-sem-design.md` (read it first — the semopy decision, the lavaan-syntax mapping, the hand-computed SRMR/RMSEA-CI/R² formulas, the payload shape, the family-mix fix, and every anchor value with its tolerance are defined there)
**Executor notes:** All paths relative to the dothesis repo root; run all commands from there with `api/.venv/bin/python` (the env `dev.sh` builds). Strict TDD: every task writes the failing test first, then the minimum code to pass. Phases 0–2 live **entirely inside the submodule** and land (commit + push + pointer bump) before any dothesis wiring. Do not reorder.

**Submodule workflow reminder** (`libs/thesis-stats/README.md:66-69`): edit under `libs/thesis-stats/`, commit + push **inside the submodule**, then `git add libs/thesis-stats` in the parent to bump the pinned pointer. The package is installed editable, so edits apply immediately.

**⚠ The two landmines:**
1. **Dependency (design §4, risk §10.1):** semopy is NOT importable today; it is added as the pinned optional extra `cbsem = ["semopy==2.3.11", "sympy==1.14.0", "numdifftools==0.9.42"]` — never as a core dependency, and never unpinned. Verified 2026-07-17: this resolve leaves every existing pin untouched. Inside semopy, **never call `ModelGeneralizedEffects`, `ModelEffects`, or `create_regularization`** — they use `np.float`/`np.int` (removed in numpy ≥ 1.24) and crash under our pins. Only `Model`, `Model.fit`, `Model.inspect`, `semopy.calc_stats`.
2. **Family-mix self-fire (design §7.3):** without narrowing `_PLS_FAMILY` to `{"htmt","gof","f2","q2"}`, every clean computed CB-SEM result (which legitimately carries AVE) fires a hard `xtable.family_mix` on itself. Task 2.2 fixes this BEFORE the adapter's golden-clean test can pass.

**Anchor values (do not weaken tolerances — `libs/thesis-stats/README.md:88`):** the full pinned tables live in design §9.1. Headlines — Holzinger–Swineford 1939 CFA (n=301): χ²=85.306 (±0.01), df=24 (exact), CFI=0.931, TLI=0.896, RMSEA=0.092, SRMR=0.065 (each ±0.005), RMSEA 90% CI [0.071, 0.114] (±0.003), std loadings .772/.424/.581/.852/.855/.838/.570/.723/.665 (±0.005). Political Democracy (n=75): χ²=38.125/df=35, CFI=0.995, TLI=0.993, RMSEA=0.035, SRMR=0.044, unstd paths 1.483/0.572/0.837 with SE 0.399/0.221/0.098, std paths 0.447/0.182/0.885.

---

## Phase 0 — dependency enactment + fixtures

### Task 0.1 — Pin the `cbsem` extra and prove the resolve
- **Files:** `libs/thesis-stats/pyproject.toml` (add `cbsem = ["semopy==2.3.11", "sympy==1.14.0", "numdifftools==0.9.42"]` under `[project.optional-dependencies]` at `:32-33`, with a comment mirroring the pins rationale at `:13-18`: validated 2026-07-17 against the exact core pins; semopy's own floors are unpinned so the transitives are pinned here)
- Steps:
  1. `api/.venv/bin/pip install -e "libs/thesis-stats[cbsem]"`
  2. `api/.venv/bin/pip list --format=freeze | grep -E "^(pandas|numpy|scipy|statsmodels|scikit-learn|factor-analyzer|pydantic|semopy|sympy|numdifftools)="` — every core pin must read exactly as `pyproject.toml:19-27`; semopy 2.3.11 / sympy 1.14.0 / numdifftools 0.9.42 present.
  3. Regression tripwire: `api/.venv/bin/python -m pytest libs/thesis-stats/tests -q` — the whole existing suite green (proves the install changed nothing; this is the EFA-pin protection, `README.md:71-75`).
- **Verify:** `api/.venv/bin/python -c "import semopy; print(semopy.__version__)"` prints `2.3.11`.
- **Done when:** all three steps pass. If step 2 shows ANY core pin moved, STOP — that contradicts the verified design premise; re-read design §4.1 before touching anything.

### Task 0.2 — Vendor the reference datasets
- **Files:** `libs/thesis-stats/tests/fixtures/holzinger_swineford_1939.csv` (new, 301 rows; must contain columns `x1..x9` — extra demographic columns are fine and exercise column scoping), `libs/thesis-stats/tests/fixtures/political_democracy.csv` (new, 75 rows, columns `x1..x3, y1..y8`)
- Source: the canonical datasets as distributed with lavaan/semopy (semopy 2.3.11 bundles both: `semopy/examples/holzinger_swineford39_data.csv`, `semopy/examples/pd_data.csv` — copying them into our fixtures makes the anchors independent of semopy's packaging). Add a short provenance header comment in a sibling `fixtures/README` line or in the test module docstring, NOT inside the CSVs.
- **Verify:** `api/.venv/bin/python -c "import pandas as pd; a=pd.read_csv('libs/thesis-stats/tests/fixtures/holzinger_swineford_1939.csv'); b=pd.read_csv('libs/thesis-stats/tests/fixtures/political_democracy.csv'); print(a.shape[0], b.shape[0], all(c in a for c in ['x1','x9']), all(c in b for c in ['x1','y8']))"` → `301 75 True True`
- **Done when:** both files load with the expected shapes.

## Phase 1 — thesis-stats: `cbsem.py` pure functions (TDD, anchors first)

All tests in `libs/thesis-stats/tests/test_cbsem.py` (new). Module-level `semopy = pytest.importorskip("semopy")` EXCEPT the fail-soft test (Task 1.4), which must run without semopy too — put that one in its own module `test_cbsem_failsoft.py` with no importorskip.

### Task 1.1 — lavaan-syntax mapper (no semopy import)
- **Files:** `libs/thesis-stats/src/thesis_stats/cbsem.py` (new), `libs/thesis-stats/tests/test_cbsem.py` (new)
- Tests first (design §5.1):
  - a 3-construct nodes/edges `AdvanceModel` dict → desc contains one `=~` line per construct and edges grouped by target (`B ~ A + C` style); deterministic line order (nodes order, then targets order);
  - labels with spaces/punctuation ("Perceived Usefulness", "attitude-2") → sanitized tokens, round-trip via the reverse map, no collisions (two labels sanitizing identically get suffixes);
  - `residual_covariances=[["y1","y5"]]` → `~~` line; unknown column → `DataError`;
  - `moderate_effect` node → `ModelSpecError` naming the PLS `moderation` op; single-indicator construct → `ModelSpecError` with the ≥ 2 message; duplicate edge / self-loop → `ModelSpecError`;
  - 2-indicator construct → mapper succeeds and flags it (the warning surfaces in the payload later);
  - no edges → measurement-only desc (no `~` lines).
- Implement: `_to_lavaan_desc(model) -> (desc, fwd_map, rev_map)` + sanitizer, pure, importable without semopy. Coerce/validate via the existing `_coerce_model`/`_check_measurement(strict=True)` helpers (`libs/thesis-stats/src/thesis_stats/__init__.py:81-123`) — call them from `run_cbsem`, keep the mapper itself dumb.
- **Verify:** `api/.venv/bin/python -m pytest libs/thesis-stats/tests/test_cbsem.py -q`
- **Done when:** green; `python -c "import thesis_stats.cbsem"` works in an env WITHOUT semopy (temporarily `pip uninstall -y semopy` in a scratch venv if needed, or trust the lazy-import test in Task 1.4).

### Task 1.2 — TRUST ANCHOR A: Holzinger–Swineford CFA (fit + loadings)
- **Files:** `libs/thesis-stats/src/thesis_stats/cbsem.py`, `libs/thesis-stats/tests/test_cbsem.py`
- Tests first: build the HS39 model as an AdvanceModel-shaped dict (visual =~ x1,x2,x3; textual =~ x4,x5,x6; speed =~ x7,x8,x9; NO edges), run `run_cbsem(model, records)` on the vendored CSV, assert the full design §9.1 Anchor A table: χ², df, CFI, TLI, RMSEA against the pinned lavaan values at the pinned tolerances, and all nine standardized loadings (±0.005). SRMR and RMSEA CI asserted in Task 1.3 (leave those two assertions commented-in-but-xfail or split the test — implementer's choice, but they must exist by end of 1.3).
- Implement the estimation core (design §5.2-§5.4): fresh `semopy.Model(desc)` per call, `fit(df, obj="MLW", solver="SLSQP")` on the listwise-dropped, renamed frame; `semopy.calc_stats` for χ²/df/CFI/TLI/RMSEA; `inspect(std_est=True)` for estimates/SE/z/p and standardized loadings; assemble the design §6.2 payload keys `fit` / `loadings` / `n` / `converged` (reliability/paths arrive in 1.3/1.4). Map `estimator="ML"` → `obj="MLW"`; any other value → `ModelSpecError` listing the supported set.
- **Verify:** `api/.venv/bin/python -m pytest libs/thesis-stats/tests/test_cbsem.py -q`
- **Done when:** Anchor A assertions green at the stated tolerances (no tolerance edits — if a value misses, the code is wrong).

### Task 1.3 — Hand-computed statistics: SRMR, RMSEA CI, R², α/CR/AVE + TRUST ANCHOR B
- **Files:** same two files.
- Tests first:
  - **SRMR independent reference:** HS39 → 0.065 ±0.005 AND PD → 0.044 ±0.005 (two datasets pin the formula, design §5.2);
  - **RMSEA 90% CI:** HS39 → [0.071, 0.114] ±0.003 each bound; degenerate case χ² < df → CI lower bound exactly 0.0;
  - **Anchor B (Political Democracy):** full design §9.1 table — model dict with the three structural edges and the seven `residual_covariances` pairs (y1-y5, y2-y4, y2-y6, y3-y7, y4-y8, y6-y8); assert fit indices, unstandardized paths + SE + z, standardized paths, all at pinned tolerances; assert `paths` keys use `"src -> tgt"` original-label form;
  - **R² identity:** `reliability["dem60"]["r_squared"]` equals (std β of ind60→dem60)² within 1e−6 (single-predictor identity, design §5.2); every reported R² ∈ [0, 1];
  - **α/CR/AVE:** on HS39, `AVE("visual")` equals mean of the three squared std loadings within 1e−6 (definitional); α("textual") equals a hand-computed Cronbach in the test (independent recompute with the `k/(k−1)` formula over raw x4,x5,x6); CR from the §5.2 formula within 1e−6;
  - `residual_highlights`: ≤ 5 rows, each `{pair, std_residual}`, sorted by |value| descending, pairs in original column names.
- Implement per design §5.2: `_srmr(model)` (correlation-metric residuals incl. diagonal over `model.mx_cov` vs `model.calc_sigma()[0]`), `_rmsea_ci(chi2, df, n)` (ncx2 + brentq inversion, N−1 denominator, clamp 0), R² = 1 − standardized residual variance of each endogenous latent from the `~~` diagonal, α from raw scoped items, CR/AVE from std loadings, residual highlights from the SRMR intermediates. Wire `reliability` and `paths` into the payload.
- **Verify:** `api/.venv/bin/python -m pytest libs/thesis-stats/tests/test_cbsem.py -q`
- **Done when:** both anchors fully green including SRMR + CI rows.

### Task 1.4 — Failure taxonomy + clean fixture + determinism + fail-soft
- **Files:** `libs/thesis-stats/src/thesis_stats/cbsem.py`, `libs/thesis-stats/tests/test_cbsem.py`, `libs/thesis-stats/tests/test_cbsem_failsoft.py` (new, no importorskip)
- Tests first (design §5.4, §9.2, §9.3, §9.5):
  - **Heywood:** seeded degenerate fixture (n=12, two near-duplicate items `f + 0.05ε` vs an unrelated construct — the recipe verified to drive semopy residual variances to the 0 boundary) → payload returned (no raise), `warnings` contains `{"kind": "heywood_case", ...}` naming the item/construct, `converged: true`;
  - **Non-convergence:** force `SolverResult.success == False` (try `fit(..., options={"maxiter": 1})`; if semopy doesn't forward it, monkeypatch) → `EstimationError`, message contains the solver message, and NO statistics in the exception payload;
  - **Numerical blow-up:** a zero-variance item column → typed error naming the column; n ≤ number of observed variables → `DataError`;
  - **df ≤ 0:** a just-identified model → `fit` block replaced by the note, estimates still present, warning added;
  - **Clean 3-factor fixture** (seeded `numpy.random.default_rng(42)` generator, 200×12, 3 constructs × 4 items, 2 structural paths with planted positive effects): loadings ∈ (0.5, 0.99), α/CR ≥ 0.7, both paths positive with p < 0.05, all fit indices finite and in-bounds, `n_dropped_listwise == 0`;
  - **Determinism:** run twice on the clean fixture → `json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)`;
  - **Fail-soft** (`test_cbsem_failsoft.py`): with `semopy` hidden via `monkeypatch.setitem(sys.modules, "semopy", None)` (plus a truthy-import guard: use `monkeypatch.setattr` on builtins import or `sys.modules` poisoning so `import semopy` raises), `run_cbsem(...)` raises `EstimatorUnavailableError` whose message contains `"CB-SEM estimator unavailable"` and `"thesis-stats[cbsem]"`; `import thesis_stats.cbsem` itself succeeds.
- Implement: `EstimationError` + `EstimatorUnavailableError` (subclass `ThesisStatsError`, defined in `cbsem.py`, re-exported from `__init__.py`), the lazy `import semopy` inside `run_cbsem`, boundary-Heywood detection (residual variance ≤ 1e−6 or |std λ| ≥ 0.999, plus any strictly negative variance), NaN scan over the fit dict, the df ≤ 0 branch, `n_dropped_listwise`, the 2-indicator warning from Task 1.1.
- **Verify:** `api/.venv/bin/python -m pytest libs/thesis-stats/tests/test_cbsem.py libs/thesis-stats/tests/test_cbsem_failsoft.py -q`
- **Done when:** green; no test ever sees a raw semopy/numpy traceback type escape `run_cbsem` (only `ThesisStatsError` subclasses).

## Phase 2 — thesis-stats: validation + release

### Task 2.1 — `claims_from_cbsem` + `validate_result("cbsem", ...)` + new checks
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py` (edit), `libs/thesis-stats/tests/test_validation_adapters.py` (extend), `libs/thesis-stats/tests/test_validation_bounds.py` (extend), `libs/thesis-stats/tests/test_validation_consistency.py` (extend)
- Tests first (design §7.1-§7.2):
  - adapter over a real Task-1.3 payload emits: `loading_cbsem` per item (NOT `loading`), `alpha`/`cr`/`ave` per construct (table `measurement_model`), `r2` per endogenous construct, `beta`+`t`(=z, df None)+`p` per path (table `structural_model`), `cfi`/`tli`/`rmsea`/`srmr`/`chi2_df` (table `model_fit`), `n`; malformed/non-dict payload → `[]`;
  - `validate_result("cbsem", payload)` dispatches (extend the dispatch at `validation.py:938-962`);
  - C1 extension: construct with `loading_cbsem` claims 0.7/0.8/0.9 and AVE 0.65 → hard `consistency.ave_loadings`; correct AVE (mean λ²) → clean (extend `_by_construct` grouping at `validation.py:292-303` to include `loading_cbsem`);
  - `chi2_df` bounds: −1 → hard; 2.5 → clean (new branch in `_bounds`);
  - rmsea-CI containment: rmsea 0.09 with ci [0.02, 0.05] → soft finding; contained → clean;
  - Heywood: `loading_cbsem` = 1.02 → soft `bounds.loading_heywood` (already exists, `validation.py:147-150` — assert it wires through the adapter);
  - z/p consistency: path with t(=z)=3.7, p=0.0002 → clean; t=3.7, p=0.4 → hard `consistency.t_p`.
- Implement: `claims_from_cbsem` next to `claims_from_ipma` (`validation.py:924-935`); the `chi2_df` bounds branch; the rmsea-CI containment check; the C1 grouping extension.
- **Verify:** `api/.venv/bin/python -m pytest libs/thesis-stats/tests -q` (whole submodule suite)
- **Done when:** whole suite green.

### Task 2.2 — Family-mix narrowing + golden-clean
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py` (`_PLS_FAMILY` at `:488`), `libs/thesis-stats/tests/test_validation_xtable.py` (extend), `libs/thesis-stats/tests/test_validation_golden.py` (extend), `libs/thesis-stats/tests/test_cbsem.py` (extend)
- Tests first (design §7.3, §9.4):
  - **golden-clean:** `validate_result("cbsem", payload)` over the clean-fixture AND both anchor payloads → **zero findings** (this fails before the narrowing — the self-fire — and passes after);
  - mix still fires: cbsem claims + one `htmt` claim → hard `xtable.family_mix`; + `q2` → fires; + `f2` → fires;
  - pure PLS mix unchanged: the existing test at `test_validation_xtable.py:19-22` (ave+htmt+cfi) still passes — because `htmt` remains in the family;
  - pure CB-SEM (ave+cfi+rmsea, no PLS-exclusive metric) → NO family-mix.
- Implement: `_PLS_FAMILY = {"htmt", "gof", "f2", "q2"}` (drop `ave`, `fornell_larcker_diag`) with a comment citing the design §7.3 rationale (AVE/F-L are shared between method families).
- **Verify:** `api/.venv/bin/python -m pytest libs/thesis-stats/tests -q`
- **Done when:** green including golden-clean.

### Task 2.3 — Export, version, README, submodule commit + push + pointer bump
- **Files:** `libs/thesis-stats/src/thesis_stats/__init__.py` (import + re-export `run_cbsem`, `EstimationError`, `EstimatorUnavailableError`; add to `__all__` at `:40-59`; bump `__version__` `"0.6.0"` → `"0.7.0"` at `:38`), `libs/thesis-stats/README.md` (add a "CB-SEM" bullet under "What it computes" at `:7-31` — CFA loadings/α/CR/AVE, χ²/df/CFI/TLI/RMSEA(+CI)/SRMR, structural paths + R², via the pinned optional extra `cbsem`; add `tests/test_cbsem.py` to the trust-anchor list at `:84-86` naming the HS39/PD lavaan anchors; note the extra in the Install section)
- Steps (submodule workflow, `README.md:66-69`):
  1. `cd libs/thesis-stats && git add -A && git commit -m "feat: CB-SEM (semopy) — CFA + structural model with lavaan-anchored fit indices (HS39 + Political Democracy)" && git push`
  2. `cd ../.. && git add libs/thesis-stats` (pointer bump; commits with the parent-repo work of Phase 3, or as its own commit now).
- **Verify:** from repo root: `api/.venv/bin/python -c "from thesis_stats import run_cbsem, EstimatorUnavailableError; import thesis_stats; print(thesis_stats.__version__)"` → `0.7.0`; `git -C libs/thesis-stats status` clean; `git submodule status libs/thesis-stats` shows the pushed SHA.
- **Done when:** all three verifies pass. **Phase 3 must not start before the submodule push** — the parent wiring imports `run_cbsem`.

## Phase 3 — dothesis wiring

### Task 3.1 — `_op_cb_sem` + whitelist + validation branch
- **Files:** `agent/tools/stats.py` (add `_op_cb_sem` per design §6.1 next to `_op_pls_sem` at `:194-207`; register `"cb_sem"` in `OPS` at `:366-385`; extend the `run_stats` docstring op list at `:445-496`), `agent/stats_validation.py` (add the `op == "cb_sem"` branch in `claims_from_run_stats` at `:55-96`, delegating to `thesis_stats.validation.claims_from_cbsem` — mirror the `mga` branch at `:90-92`), `agent/tests/test_stats_tool.py` (extend), `agent/tests/test_stats_validation.py` (extend)
- Tests first (design §6, §9.5; tmp_path CSV fixtures — reuse the clean 3-factor generator recipe):
  - clean run: `run_stats(op="cb_sem", file=csv, params={conceptual_model, measurement})` → JSON with `op: "cb_sem"` and the §6.2 keys (`fit`, `loadings`, `reliability`, `paths`, `warnings`); floats 4 dp;
  - `estimator` default `"ML"` echoed; `params={"estimator": "ULS"}` → `{"error": ...}` JSON (never a raise — `stats.py:497-509` unchanged);
  - moderation-shaped conceptual_model → `{"error": ...}` with the PLS-moderation hint; missing conceptual_model → the `_adapt` error (`stats.py:144-148`);
  - fail-soft: monkeypatch so the lazy semopy import raises → `{"error": "cb_sem failed: CB-SEM estimator unavailable — ..."}` (flows through `stats.py:507-509`, zero new plumbing — assert the message substring);
  - validation ride-along: monkeypatch `_op_cb_sem` to return `fit.cfi = 1.3` → response carries `validation.hard >= 1` with `bounds.cfi`; clean run → no `validation` key (`stats.py:510-521` needs NO change);
  - `claims_from_run_stats("cb_sem", summary)` unit tests: real payload → expected claims incl. `loading_cbsem`; malformed → `[]`.
- **Verify:** `api/.venv/bin/python -m pytest agent/tests/test_stats_tool.py agent/tests/test_stats_validation.py -q`
- **Done when:** green, pre-existing tests untouched.

### Task 3.2 — Persisted block coverage at the commit gate
- **Files:** `agent/stats_validation.py` (in `claims_from_analysis_results`: read `structural_model.chi2_df` alongside the existing cfi/tli/rmsea/srmr at `:294-297`; when any of those CB-SEM fit keys is present, emit `measurement_model` item loadings as `loading_cbsem` instead of `loading` at `:240-243` — design §7.4), `agent/tests/test_stats_validation.py` (extend), `agent/tests/test_state_tools.py` (extend)
- Tests first:
  - a clean CB-SEM-shaped `analysis_results` block (measurement_model + structural_model with cfi/tli/rmsea/srmr/chi2_df, hypothesis_tests with z-as-t + p) → zero hard findings; loading 1.02 in that block → soft (`bounds.loading_heywood`), NOT hard `bounds.loading`;
  - the same 1.02 loading in a PLS block (no fit indices) → still hard `bounds.loading` (the switch is family-scoped);
  - `structural_model.cfi = 1.4` → hard at the gate: `commit_slice("M4", ...)` → `stats_validation_failed` via the existing path (zero changes in `agent/tools/state_tools.py`);
  - the existing PLS family-mix gate test (`agent/tests/test_stats_validation.py:59-62`) still green after the Phase-2 `_PLS_FAMILY` narrowing (GOOD_BLOCK carries `f2`/`htmt`; if it somehow lacks every PLS-exclusive metric, add `f2` to its hypothesis_tests rather than touching the family set).
- **Verify:** `api/.venv/bin/python -m pytest agent/tests/test_stats_validation.py agent/tests/test_state_tools.py -q`
- **Done when:** green with zero `state_tools.py` changes.

### Task 3.3 — Installer wiring (dev.sh / deploy.sh)
- **Files:** `dev.sh` (`:155-157`: guard becomes `"$VENV_BIN/python" -c "import thesis_stats, semopy"`; install becomes `pip install -e "libs/thesis-stats[cbsem]"`; keep the one-time message), `scripts/deploy.sh` (`:197`: `pip install --quiet -e "./libs/thesis-stats[cbsem]"`)
- No unit tests; shell-level verify only.
- **Verify:** `bash -n dev.sh scripts/deploy.sh` (syntax); then simulate the stale-env path: `api/.venv/bin/pip uninstall -y semopy sympy numdifftools && ./dev.sh --help >/dev/null 2>&1 || true` is NOT required — instead run the guard line manually: `api/.venv/bin/python -c "import thesis_stats, semopy"` fails after the uninstall, then `api/.venv/bin/pip install -e "libs/thesis-stats[cbsem]"` restores it and the guard passes. (Skip the uninstall dance if you prefer; minimum bar: grep shows both files use the `[cbsem]` extra and the dual-import guard.)
- **Done when:** both scripts reference the extra; the guard catches a semopy-less env.

## Phase 4 — skill copy + final gate

### Task 4.1 — M4/M5 skill copy
- **Files:** `skills/dothesis-m4-analysis/SKILL.md` (op list `:48-88`: add the `cb_sem` bullet per design §8 — params, returned tables, Hu & Bentler thresholds (CFI/TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08 — same as the parser, `orchestrator/tools/m4_parsers/lavaan.py:22-26`), the Heywood-warning narration rule, the residual-covariances disclosure rule, "run `screening` first"; family rule `:36-38`: extend with "M3 tool CB-SEM → use op `cb_sem`, never `pls_sem`, and vice versa" closing the `method_advice` loop), `skills/dothesis-m5-writing/SKILL.md` (one rule: CB-SEM results chapters quote the computed `fit` table + per-construct reliability, same sourcing rule as PLS), `agent/tools/stats.py` docstring (already edited in Task 3.1 — re-verify the copy matches the skill)
- No new test files — the phase gate is the full suites.
- **Verify:** `grep -n "cb_sem" skills/dothesis-m4-analysis/SKILL.md` shows the op bullet and the family rule; `api/.venv/bin/python -m pytest agent/tests -q && api/.venv/bin/python -m pytest libs/thesis-stats/tests -q` both fully green.
- **Done when:** suites green; skill, docstring, and design §6 agree on the op contract.

---

## Execution order & gates

1. Phase 0 → 1 → 2 entirely inside the submodule; **push the submodule (Task 2.3) before any Phase-3 work** — the parent wiring imports `run_cbsem`.
2. Task 2.2 (family narrowing) must land before any golden-clean assertion can pass; do not "fix" a failing golden-clean by weakening the adapter instead.
3. Phase 3 before 4; Phase 4 documents what already works.
4. Final gate: both full suites green + the Task 2.3 one-liner works from the repo root + `git submodule status libs/thesis-stats` SHA matches the pushed submodule commit + both anchors green at pinned tolerances + the fail-soft test green.

**Anchors (do not weaken — same rule as the accuracy suites, `libs/thesis-stats/README.md:88`):** the HS39 and Political Democracy lavaan tables (design §9.1) including the hand-computed SRMR (0.065 / 0.044) and RMSEA CI ([0.071, 0.114]); the R² ≡ (std β)² identity; the AVE ≡ mean λ² identity; the Heywood fixture returning warnings-not-crashes; the non-convergence typed error; golden-clean (clean computed CB-SEM → zero validation findings); determinism (identical JSON on repeat). If an anchor drifts after a dependency change, that is a finding about the change — never a tolerance to loosen.
