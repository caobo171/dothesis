# thesis-stats: Shared Statistical Library — Implementation Plan

**Date:** 2026-07-17
**Design spec:** `2026-07-17-thesis-stats-shared-lib-design.md` (same directory —
read it first; it contains the verified file:line facts, API contract, adapter rules,
and risk register this plan executes).
**Implementer:** Opus agent. Work TDD where a test can exist before the code; every
step ends with an explicit verification command and a "done when". Do the phases in
order — the parity proof (Phase 1–2) gates everything after it.

Paths:
- LIB = `/Users/caonguyenvan/project/thesis-stats` (new)
- FF  = `/Users/caonguyenvan/project/fillform/analyser`
- DT  = `/Users/caonguyenvan/project/dothesis`

Conventions:
- fillform's interpreter: `$FF/venv/bin/python` (Python 3.13.2, all deps installed).
- Create a fresh venv for LIB (`python3 -m venv $LIB/.venv`); dothesis uses its own env.
- Never edit numeric logic while porting (design spec §4 "verbatim-port rule").
- Commit at the end of each phase minimum; each task is meant to be independently
  verifiable before moving on.

---

## Phase 0 — Baseline & golden capture (no refactoring yet)

Goal: pin today's numbers to disk so the extraction can be *proven* numerically inert.

- [ ] **0.1 Record baseline test results.**
  Files touched: none.
  Verify:
  ```bash
  cd /Users/caonguyenvan/project/fillform/analyser
  ./venv/bin/python test_smartpls_accuracy.py
  ./venv/bin/python test_analyzers.py; echo "exit=$?"
  ```
  Done when: accuracy test prints `RESULT: all checks passed` (it does today — if it
  does not, STOP and investigate before anything else). Note in the working log that
  `test_analyzers.py` is expected to report `SPSS Analyzer: FAILED` and
  `SmartPLS Analyzer: FAILED` (dict-vs-AdvanceModel, design spec §2.1) with
  `Python Executor: PASSED` — that is the accepted baseline, to be turned green in
  Phase 2, not now.

- [ ] **0.2 Scaffold the LIB directory and capture golden outputs.**
  Files touched: `$LIB/pyproject.toml`, `$LIB/src/thesis_stats/__init__.py` (empty
  stub), `$LIB/tests/golden/` (generated JSON), `$LIB/tests/capture_golden.py`.
  Create the package skeleton (src layout, name `thesis-stats`, import name
  `thesis_stats`, `requires-python >= 3.10`, deps per design spec §3 — **no plspm**).
  Write `capture_golden.py`: builds the seeded fixtures from
  `$FF/test_smartpls_accuracy.py` (`make_model()`, `make_data(n=300, seed=42)`) and the
  2-construct fixture from `$FF/test_analyzers.py` (wrapped in `AdvanceModel`), runs —
  **importing from FF, not the lib** —
  `SmartPLSAnalyzer().analyze_bootstrapping(model, data, bootstrap_samples=0)`,
  `SPSSAnalyzer().analyze_basic_statistics(...)`,
  `SPSSAnalyzer().analyze_linear_regression(...)`, strips non-deterministic keys
  (`raw_bootstrap`), and writes sorted-key JSON to `$LIB/tests/golden/{pls,basic,regression}.json`.
  Verify:
  ```bash
  cd /Users/caonguyenvan/project/fillform/analyser
  ./venv/bin/python /Users/caonguyenvan/project/thesis-stats/tests/capture_golden.py
  ls -la /Users/caonguyenvan/project/thesis-stats/tests/golden/
  ```
  Done when: three non-empty golden JSON files exist; re-running the script produces
  byte-identical files (determinism check: run twice, `diff`).

---

## Phase 1 — Extract the library (port verbatim, prove parity)

- [ ] **1.1 Port the four source modules.**
  Files touched: `$LIB/src/thesis_stats/{models.py,pls_engine.py,smartpls.py,spss.py}`.
  - `models.py`: copy `$FF/models.py` verbatim.
  - `pls_engine.py`: move `class PLSEngine` (FF smartpls_analyzer.py:19–249) out into
    its own module, unchanged.
  - `smartpls.py`: the rest of `$FF/smartpls_analyzer.py` (`SmartPLSAnalyzer`, module
    `main()` may be dropped), with `from .pls_engine import PLSEngine` and
    `from .models import ...`.
  - `spss.py`: copy `$FF/spss_analyzer.py`, imports adjusted
    (`from .smartpls import SmartPLSAnalyzer` for `_run_pls_sem`, spss_analyzer.py:509).
  Only imports/docstrings/logger names change — diff-review your own port against the
  originals to confirm no logic lines moved.
  Verify:
  ```bash
  cd /Users/caonguyenvan/project/thesis-stats && python3 -m venv .venv && \
    .venv/bin/pip install -e ".[dev]" && \
    .venv/bin/python -c "from thesis_stats.smartpls import SmartPLSAnalyzer; from thesis_stats.spss import SPSSAnalyzer; print('imports ok')"
  # No-network audit (design spec §6.3):
  grep -rn "requests\|urllib\|httpx\|socket" src/thesis_stats/ && echo "FAIL: network import" || echo "clean"
  ```
  Done when: imports succeed in the lib venv; grep finds no network imports.

- [ ] **1.2 Public API + typed errors (TDD).**
  Files touched: `$LIB/src/thesis_stats/__init__.py`, `$LIB/tests/test_api.py`.
  Write `tests/test_api.py` FIRST: `run_pls`/`run_spss_basic`/`run_spss_regression`
  accept both an `AdvanceModel` and a **plain dict** (use the Phase-0 fixtures — the
  dict case is exactly what breaks today, design spec §2.1); invalid model raises
  `ModelSpecError`; data missing a mapped column raises `DataError`; results are
  `json.dumps`-able. Then implement the thin wrappers per design spec §4 (coerce via
  `AdvanceModel.model_validate`, re-wrap analyzer exceptions).
  Verify: `cd $LIB && .venv/bin/python -m pytest tests/test_api.py -v`
  Done when: test_api green; wrappers contain no statistics, only
  coercion/validation/re-raising.

- [ ] **1.3 Port the accuracy suite to pytest.**
  Files touched: `$LIB/tests/conftest.py` (seeded model/data fixtures lifted from
  `$FF/test_smartpls_accuracy.py`), `$LIB/tests/test_pls_accuracy.py`.
  Same four reference implementations (loadings vs corr(indicator, LV score); Henseler
  HTMT; Fornell-Larcker; leave-one-out f²), same tolerances (1e-4; 5e-3 for loadings),
  asserted with pytest instead of print/exit. Import target: `thesis_stats`.
  Verify: `cd $LIB && .venv/bin/python -m pytest tests/test_pls_accuracy.py -v`
  Done when: all four metric groups pass against the lib.

- [ ] **1.4 Golden-parity test — the extraction proof.**
  Files touched: `$LIB/tests/test_golden_parity.py`.
  Recompute the three Phase-0 payloads via `thesis_stats.run_*` on identical fixtures
  and deep-compare against `tests/golden/*.json` with `pytest.approx(abs=1e-9)` on
  every float leaf (write a small recursive comparator; key sets must match exactly).
  Verify: `cd $LIB && .venv/bin/python -m pytest tests/test_golden_parity.py -v`
  Done when: parity test green. **If any leaf differs, the port introduced drift —
  fix the port, never the golden files.**

- [ ] **1.5 SPSS smoke/known-value tests.**
  Files touched: `$LIB/tests/test_spss.py`.
  On the seeded fixtures: descriptives count/mean sanity, Cronbach alpha > 0.7 for the
  parallel-item construct, EFA returns KMO in (0,1] and Bartlett p < .05, regression
  recovers positive coefficient with p < .05 on the known X→Y structure.
  Verify: `cd $LIB && .venv/bin/python -m pytest tests/ -v`
  Done when: entire lib suite green in one run.

---

## Phase 2 — Strengthen the PLS safety net (before anyone new depends on it)

Design spec §11: the hand-rolled `PLSEngine`'s accuracy rests entirely on the accuracy
suite, which today has **no moderation and no bootstrap coverage**. Close that before
dothesis builds on it.

- [ ] **2.1 Moderation accuracy test (TDD against existing behavior).**
  Files touched: `$LIB/tests/test_pls_moderation.py`.
  Seeded fixture: 3 constructs + a `moderate_effect` node (schema per FF
  models.py:31–41; wiring per smartpls_analyzer.py:526–541) where data is generated
  with a true interaction (`z = a·x + b·w + c·(x·w) + noise`). Assert: (a) the
  interaction construct (`"W * X"` label) appears in `raw_path_coefficients`; (b) its
  coefficient matches an independent reference — OLS of the stage-1 LV scores product
  term, same two-stage recipe — within 5e-3; (c) sign of c is recovered.
  Verify: `cd $LIB && .venv/bin/python -m pytest tests/test_pls_moderation.py -v`
  Done when: green. If the engine fails the reference here, STOP — that is a real
  pre-existing accuracy bug; document it and raise before proceeding (do not tune the
  test to the engine).

- [ ] **2.2 Bootstrap sanity test.**
  Files touched: `$LIB/tests/test_pls_moderation.py` or new `test_pls_bootstrap.py`.
  `run_pls(model, data, bootstrap_samples=200)` on the Phase-1 fixture: bootstrap mean
  of each path within 0.1 of the point estimate, SEs strictly positive, t = mean/SE
  consistent. Mark `@pytest.mark.slow` if runtime > ~30 s.
  Verify: `cd $LIB && .venv/bin/python -m pytest tests/ -v` (full suite)
  Done when: full lib suite green, runtime acceptable (< ~2 min).

---

## Phase 3 — Rigor layer

- [ ] **3.1 Tests first.**
  Files touched: `$LIB/tests/test_rigor.py`.
  Known-value cases (design spec §8/§10): Shapiro on seeded `N(0,1)` n=200 → p > .05,
  on `Exponential` → p < .05; Levene on equal-variance groups → homogeneous=True, on
  sd-ratio-3 groups → False; Cohen's d on N(0,1) vs N(0.8,1), n=2000/group → d within
  0.1 of 0.8; per-predictor f² cross-checked against the leave-one-out reference from
  `test_pls_accuracy.py`; Harman on single-factor-generated items →
  `first_factor_variance_pct > 50` & `concern=True`, on two orthogonal factors →
  `concern=False`; skip-with-warning paths (no group column; n<3 column).
  Verify: `cd $LIB && .venv/bin/python -m pytest tests/test_rigor.py -v` (red)
  Done when: tests exist, fail with ImportError/NotImplemented (red confirmed).

- [ ] **3.2 Implement `rigor.py` + `run_rigor` export.**
  Files touched: `$LIB/src/thesis_stats/rigor.py`, `$LIB/src/thesis_stats/__init__.py`.
  Per design spec §8: `check_normality`, `check_homogeneity`, `effect_sizes`
  (Cohen's f² overall + per-predictor + Cohen's d), `harman_single_factor`; `run_rigor`
  composes, skipping inapplicable checks into `warnings`, never raising for missing
  optional inputs. Reuse the f² leave-one-out formula semantics from
  `smartpls.py::_calculate_f_squared` — do not invent a variant.
  Verify: `cd $LIB && .venv/bin/python -m pytest tests/ -v`
  Done when: full lib suite green including rigor; `from thesis_stats import run_rigor` works.

---

## Phase 4 — fillform becomes a thin consumer

- [ ] **4.1 Install the lib into fillform's venv.**
  Files touched: `$FF/requirements.txt`, `$FF/setup_venv.sh`, `$FF/setup_venv.bat`.
  Add `-e /Users/caonguyenvan/project/thesis-stats  # thesis-stats shared engine` (plus
  a comment noting the git URL once one exists); remove `plspm`, `pandas`, `numpy`,
  `scipy`, `statsmodels`, `scikit-learn`, `factor-analyzer` (transitive now); keep
  fastapi/uvicorn/pydantic.
  Verify:
  ```bash
  cd /Users/caonguyenvan/project/fillform/analyser
  ./venv/bin/pip install -e /Users/caonguyenvan/project/thesis-stats
  ./venv/bin/python -c "import thesis_stats; print(thesis_stats.__file__)"
  ```
  Done when: import resolves to the LIB src tree from fillform's venv.

- [ ] **4.2 Rewire `main.py` and `exec_python.py`; switch test imports.**
  Files touched: `$FF/main.py`, `$FF/exec_python.py`, `$FF/test_smartpls_accuracy.py`,
  `$FF/test_analyzers.py`.
  Per design spec §5: endpoints call `run_pls`/`run_spss_basic`/`run_spss_regression`;
  request/response pydantic models imported from `thesis_stats.models`;
  `/bootstrapping` passes `request.model` (not `.dict()` — main.py:47 bug);
  `ModelSpecError|DataError → 422`, other `ThesisStatsError → 500`. `PythonExecutor`
  delegates to the lib functions (CLI argv/JSON contract unchanged, default
  bootstrap_samples 500 preserved). Tests: accuracy test imports
  `from thesis_stats.smartpls import SmartPLSAnalyzer` / `from thesis_stats.models
  import AdvanceModel`; `test_analyzers.py` calls the `run_*` API so its dict-passing
  sections finally pass.
  Verify:
  ```bash
  cd /Users/caonguyenvan/project/fillform/analyser
  ./venv/bin/python test_smartpls_accuracy.py     # RESULT: all checks passed
  ./venv/bin/python test_analyzers.py; echo "exit=$?"   # exit=0, ALL sections PASSED
  ```
  Done when: accuracy suite green AND `test_analyzers.py` is now **fully** green
  (better than baseline, per design spec §2.1/§11).

- [ ] **4.3 Delete the duplicated engine; end-to-end smoke.**
  Files touched (deleted): `$FF/smartpls_analyzer.py`, `$FF/spss_analyzer.py`,
  `$FF/models.py`. Also `grep -rn "smartpls_analyzer\|spss_analyzer\|from models import"
  $FF --include="*.py"` and fix any straggler (e.g. `start_server.py`, `README.md`
  snippets — update docs mentions too).
  Verify:
  ```bash
  cd /Users/caonguyenvan/project/fillform/analyser
  ./venv/bin/python test_smartpls_accuracy.py && ./venv/bin/python test_analyzers.py
  # CLI smoke (reuse a temp JSON: {"model": <2-construct model>, "data": [...], "bootstrap_samples": 50}):
  ./venv/bin/python exec_python.py smartpls bootstrapping /tmp/ff_smoke.json | head -5
  # Server smoke:
  ./venv/bin/python start_server.py &  sleep 3
  curl -s localhost:4002/ | grep healthy
  curl -s -X POST localhost:4002/basic_analysis -H 'Content-Type: application/json' -d @/tmp/ff_smoke.json | head -c 300
  curl -s -X POST localhost:4002/bootstrapping  -H 'Content-Type: application/json' -d @/tmp/ff_smoke.json | head -c 300
  curl -s -X POST localhost:4002/linear_regression -H 'Content-Type: application/json' -d @/tmp/ff_smoke.json | head -c 300
  kill %1
  ```
  Done when: no analyzer source remains in FF; both test files green; CLI prints a
  result JSON; all three endpoints (including the previously-broken `/bootstrapping`)
  return 200 with the expected top-level keys.

---

## Phase 5 — dothesis integration

- [ ] **5.1 Adapter, tests first.**
  Files touched: `$DT/agent/tests/test_model_adapter.py` (new),
  `$DT/agent/tools/model_adapter.py` (new).
  Tests (pure-python, no thesis_stats import needed since the adapter returns dicts):
  the three shapes from design spec §6.1 —
  (a) canonical nodes/edges (`orchestrator/schemas/m3.py:32–36`) with `effect_type:
  "negative"` mapped to `data.effectType`; (b) `{constructs, paths}`
  (m3_design.py:96–138) requiring `measurement`; (c) decomposition with `moderator` →
  emits a `moderate_effect` node wired per FF contract. Error cases: unknown construct
  in an edge, question-texts-without-measurement, empty model → `ValueError` with
  actionable message. Positive outputs must validate:
  `AdvanceModel.model_validate(result)` (guard with `importorskip("thesis_stats")` in
  that one assertion).
  Then implement `to_advance_model(...)` per §6.1.
  Verify: `cd $DT && python -m pytest agent/tests/test_model_adapter.py -v`
  Done when: all shape + error tests green.

- [ ] **5.2 New whitelisted ops in `stats.py`, tests first.**
  Files touched: `$DT/agent/tests/test_stats_tool.py` (extend),
  `$DT/agent/tools/stats.py`, `$DT/requirements.txt`.
  requirements.txt gains a `# === Statistics engine (thesis-stats) ===` section with
  the editable/path dependency (and note for the sandbox image). Tests (guarded by
  `pytest.importorskip("thesis_stats")`, seeded CSV fixture with 2–3 constructs ×3
  items and known structure, following the existing fixture style at
  test_stats_tool.py:12–26):
  - `pls_sem` returns path coefficient with correct sign, AVE/CR present, payload
    < 8 KB (bounded-summary guarantee, design spec §6.2), and honors the
    `bootstrap_samples` clamp (pass 999999, assert it ran and did not explode —
    inspect that params were clamped, e.g. echo `bootstrap_samples_used ≤ 1000`).
  - `efa` returns KMO + factors; `regression_full` returns per-hypothesis tables;
    `mediation` returns direct/indirect/total; `moderation` on a fixture with an
    interaction returns the interaction path; `rigor` returns the §8 envelope.
  - Whitelist still enforced: `run_stats("eval_python", ...)` rejected and the new op
    names appear in `available`.
  - Missing thesis_stats → the existing `"stats dependency missing"` error envelope
    (monkeypatch the import to raise `ModuleNotFoundError` and assert).
  Then implement the six op functions + `OPS` entries + updated `run_stats` docstring
  (op list with params). Each op: `_load_df` → `to_advance_model` →
  `thesis_stats.run_*` → summarizer (drop `raw_scores`/`raw_crossloadings`; keep
  construct-level tables; round floats to 4 d.p. like existing ops).
  Verify: `cd $DT && python -m pytest agent/tests/test_stats_tool.py -v`
  Done when: old six op tests still green, new op tests green, payload-size and
  clamp assertions green.

- [ ] **5.3 Wire-up sanity in the runtime.**
  Files touched: none expected (`agent/runtime.py:173` already imports `run_stats`;
  ops are data, not new tools). Confirm nothing else enumerates OPS.
  Verify:
  ```bash
  cd /Users/caonguyenvan/project/dothesis
  grep -rn "OPS\b" agent/ orchestrator/ --include="*.py" | grep -v tests
  python -c "from agent.tools.stats import OPS; print(sorted(OPS))"
  ```
  Done when: `sorted(OPS)` lists all 12 ops; no other code hardcodes the old op list.

---

## Phase 6 — End-to-end verification & documentation

- [ ] **6.1 Full test sweep, all three projects.**
  Verify:
  ```bash
  cd /Users/caonguyenvan/project/thesis-stats && .venv/bin/python -m pytest tests/ -v
  cd /Users/caonguyenvan/project/fillform/analyser && ./venv/bin/python test_smartpls_accuracy.py && ./venv/bin/python test_analyzers.py
  cd /Users/caonguyenvan/project/dothesis && python -m pytest agent/tests/ -x -q
  cd /Users/caonguyenvan/project/dothesis && python -m pytest orchestrator/tests/ -x -q   # regression: nothing here touches stats, must stay green
  ```
  Done when: every suite green in a single sweep.

- [ ] **6.2 Cross-engine consistency spot-check (the payoff demo).**
  One seeded dataset written to CSV; run dothesis `run_stats(op="pls_sem", ...)` via
  `run_stats.func(...)` in a scratch script AND fillform's
  `exec_python.py smartpls bootstrapping` on the same model/data; compare path
  coefficients — identical to 4 d.p. (same engine, so exact modulo summary rounding).
  Files touched: none permanent (scratch under /tmp).
  Done when: numbers match; paste the comparison into the PR/commit message.

- [ ] **6.3 Documentation.**
  Files touched: `$LIB/README.md` (public API, install-from-path instructions for both
  consumers, **trust-anchor note**: accuracy rests on the ported accuracy + moderation
  suites — design spec §11), `$FF/README.md` (analyzer now lives in thesis-stats),
  `$DT` docs touchpoint: update the run_stats op list wherever it is documented
  (`skills/dothesis-m4-analysis/` references the op set — grep for `cronbach` /
  `run_stats` under `$DT/skills/` and update the op enumeration only; no behavioral
  skill rewrites this pass).
  Verify: `grep -rn "pls_sem" $DT/skills/ | head` shows the updated op list.
  Done when: three docs updated; a fresh reader can install and run both consumers.

- [ ] **6.4 Deferred follow-ups filed (do NOT implement).**
  Record in `$LIB/README.md` "Roadmap" or the dothesis issue tracker: a-priori/post-hoc
  power analysis; missing-data imputation strategy; m4_parsers/computed-results
  consolidation; store-bound run_stats factory; PyPI publishing.
  Done when: the deferred list exists verbatim somewhere durable.

---

## Phase ordering rationale (for the implementer)

Extraction before parity would leave nothing to compare against — hence Phase 0's
golden capture runs **the old code**. Phases 1–2 make the lib trustworthy *in
isolation* (parity + strengthened accuracy net) before any consumer moves. Phase 4
(fillform) precedes Phase 5 (dothesis) because fillform's tests are the only
pre-existing numerical net; keeping them green across the delete step proves the
consumer path, after which dothesis is purely additive. If any parity or accuracy
check fails at any point: stop, diagnose the port (or document the pre-existing
engine bug), never adjust tolerances or golden files to make it pass.
