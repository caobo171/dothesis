# thesis-stats: Shared Statistical Library — Design Spec

**Date:** 2026-07-17
**Status:** Approved for implementation (implementer: Opus agent; see companion plan
`2026-07-17-thesis-stats-shared-lib-plan.md`)
**Scope owner:** cao.nv17@gmail.com

---

## 1. Problem / Motivation

Two projects need the same statistical engine and today only one has it:

- **fillform** (`/Users/caonguyenvan/project/fillform/analyser`) owns a complete,
  battle-tested PLS-SEM + SPSS-style analysis engine (~1,900 lines of analyzer code)
  buried inside a FastAPI microservice. It is not importable from anywhere else — it is a
  flat script directory with no package structure.
- **dothesis** (`/Users/caonguyenvan/project/dothesis`) has a `run_stats` agent tool that
  can only do basic stats (describe/corr/cronbach/OLS/ttest). Everything a thesis
  actually needs beyond that — PLS-SEM, EFA, HTMT, mediation, moderation — is handled by
  **parsing output the student pastes in** from SmartPLS/SPSS
  (`orchestrator/tools/m4_parsers/{smartpls,spss,lavaan,transcript}.py` + LLM fallback).
  dothesis cannot *compute* these numbers itself.

Extract the engine into a standalone library **`thesis-stats`** consumed by both. This
gives dothesis real computation, removes fillform's inability to share the code, and
creates one place to add new statistical rigor checks.

**Hard constraint:** dothesis's `run_stats` is a security boundary (whitelisted ops,
in-process, network-less sandbox). The integration must be a Python import, **never** an
HTTP call to fillform's server on :4002 — that would punch a hole in the sandbox.

---

## 2. Current State (verified facts, with file:line refs)

### 2.1 fillform/analyser — the engine

All paths relative to `/Users/caonguyenvan/project/fillform/analyser/`.

**`smartpls_analyzer.py` (1,060 lines)**
- `class PLSEngine` (line 19): hand-rolled PLS-PM estimator (Mode A, path weighting,
  standardized indicators) that **replaces the `plspm` package** — its docstring
  (lines 24–28) explains plspm's dominant-sign correction is broken. Constructor
  (line 35): `PLSEngine(data: pd.DataFrame, construct_items: Dict[str, List[str]], structure: Dict[str, List[str]], iterations=300, tolerance=1e-7)`.
  Methods: `_fit` (66), `scores` (151), `path_coefficients` (154), `inner_model` (157),
  `outer_model` (160), `crossloadings` (175), `inner_summary` (185),
  `goodness_of_fit` (203), `effects` (209 — direct/indirect/total = **mediation**),
  `unidimensionality` (229).
- `class SmartPLSAnalyzer` (line 252): `analyze_bootstrapping(model, data, bootstrap_samples=1000)`
  (line 261) orchestrates single-stage (`_run_pls_single_stage`, 477) or **two-stage
  moderation** (`_run_pls_with_moderation`, 495; `_fit_two_stage`, 512 — interaction
  terms as products of standardized LV scores, added as single-indicator constructs).
  Bootstrap machinery `_bootstrap_engine` (580). Quality metrics: `_calculate_htmt`
  (794, Henseler 2015), `_calculate_fornell_larcker` (841), `_calculate_vif` (867),
  `_calculate_f_squared` (972). Output keys: `raw_scores`, `raw_outer_model`,
  `raw_inner_model`, `raw_path_coefficients`, `raw_crossloadings`, `raw_inner_summary`,
  `raw_goodness_of_fit`, `raw_effects`, `raw_unidimensionality`, `raw_bootstrap`,
  `raw_htmt`, `raw_fornell_larcker`, `raw_vif`, `raw_f_squared`.
- **`plspm` is never imported** — only mentioned in docstrings (30, 586) and a stale
  comment (spss_analyzer.py:511). `requirements.txt` still pins `plspm==0.5.7`;
  thesis-stats can drop it.

**`spss_analyzer.py` (675 lines)**
- `class SPSSAnalyzer` (line 22):
  - `analyze_basic_statistics(model, data)` (31): descriptives incl. skewness/kurtosis
    (163), Cronbach's alpha per construct (194), EFA with Varimax + KMO (305) +
    Bartlett (331) via `factor_analyzer` (236), correlation matrix (354), plus an
    embedded PLS fit with `bootstrap_samples=0` (line 62, `_run_pls_sem` at 509 which
    delegates to `SmartPLSAnalyzer`).
  - `analyze_linear_regression(model, data)` (77): composite scores (374), multiple
    OLS per structural relationship with F-test, R²/adj-R², coefficient significance
    (388, 537).

**`models.py` (158 lines)** — pydantic v2 schema, the input contract for both analyzers:
- `AdvanceModel` (60) = `{name, nodes: List[Node], edges: List[Edge]}`, `extra="ignore"`.
- `Node` (46): `{id, data: NodeData (discriminator 'nodeType'), questions: List[str]}`.
- `VariableNodeData` (23): `{label, nodeType:"variable", likertScale, average, standardDeviation}`.
- `ModerateEffectNodeData` (31): `{label, nodeType:"moderate_effect", moderateVariable, independentVariable, effectType, likertScale:Optional}`.
- `Edge` (54): `{id, source, target, data:{effectType: positive|negative}}`.
- Response models: `AnalysisResponse` (77), `BasicAnalysisResponse` (128),
  `LinearRegressionResponse` (157), etc.

**Entry points**
- `main.py`: FastAPI on `0.0.0.0:4002` (line 109). `POST /bootstrapping` (40),
  `POST /basic_analysis` (64), `POST /linear_regression` (87).
  **Known latent bug** (main.py:47): `/bootstrapping` passes `request.model.dict()` — a
  plain dict — into `analyze_bootstrapping`, which does attribute access
  (`model.nodes`, smartpls_analyzer.py:373+). The other two endpoints pass the pydantic
  model. See §7 (the lib's public API coerces dicts, fixing this class of bug).
- `exec_python.py`: CLI `python exec_python.py <spss|smartpls> <method> <json-file>`
  (`spss basic_analysis|linear_regression`, `smartpls bootstrapping`); `PythonExecutor`
  (21) wraps model dicts in `AdvanceModel` (lines 59, 73).
- `start_server.py`: uvicorn launcher.

**Tests — the numerical safety net**
- `test_smartpls_accuracy.py` (222 lines): recomputes outer loadings, HTMT
  (Henseler 2015), Fornell-Larcker, and f² with independent reference implementations
  on a seeded 3-construct fixture (X→Y, X→Z, Y→Z; n=300, seed=42), tolerance 1e-4
  (5e-3 for loadings). Run: `python3 test_smartpls_accuracy.py`.
  **Verified 2026-07-17: all checks PASS** with the project venv (Python 3.13.2).
- `test_analyzers.py` (201 lines): smoke test of both analyzers + `PythonExecutor`.
  **Verified 2026-07-17: baseline is PARTIALLY RED** — the "SPSS Analyzer" and
  "SmartPLS Analyzer" sections pass **plain dicts** where the analyzers now require
  `AdvanceModel` (errors: `'dict' object has no attribute 'nodes'` / `Failed to prepare
  PLS configuration`); only the "Python Executor" section passes. The plan records this
  baseline and fixes the test (dict coercion in the lib makes all three green).

**Deps** (`requirements.txt`): fastapi 0.116.1, uvicorn 0.35.0, pydantic 2.11.9,
pandas 2.3.2, numpy 2.3.3, plspm 0.5.7 (unused), scipy 1.16.2, statsmodels 0.14.5,
scikit-learn 1.7.2, factor-analyzer 0.5.1.

### 2.2 dothesis — the consumer

All paths relative to `/Users/caonguyenvan/project/dothesis/`.

**`agent/tools/stats.py` (205 lines) — the security-bounded whitelist**
- Docstring (lines 1–8): "The whitelist IS the security boundary — every op is a vetted
  function here; the model only picks ops and parameters. In production these run
  inside the network-less sandbox service."
- `OPS` dict (120–127): `detect`, `describe`, `corr`, `cronbach`, `regression` (OLS via
  numpy/scipy), `ttest`. An op not in the dict does not run (`run_stats`, 178–204).
- `_load_df` (21–32): reads `.csv`, `.xlsx/.xls`, `.sav` (pyreadstat). Heavy deps
  (pandas/scipy/pyreadstat) are **lazy-imported**; `ModuleNotFoundError` is turned into
  a clean JSON error (199–200). Note: dothesis's `requirements.txt` does **not** list
  pandas/scipy — they are environment-provided extras. thesis-stats will bring them.
- `check_thresholds` (147): deliberately compute-free classifier for **pasted** numbers.
  Unaffected by this refactor.
- Registered in `agent/runtime.py:173`: `from agent.tools.stats import check_thresholds, run_stats`.
- Tests: `agent/tests/test_stats_tool.py` (calls `run_stats.func(...)`,
  `pytest.importorskip("pandas")`, asserts whitelist rejection, schema-only `detect`,
  known-value cronbach/regression/ttest).

**`conceptual_model` in the context_store — three shapes in the wild**
- Canonical (post 2026-06 design merge), `orchestrator/schemas/m3.py:32–36`:
  `{nodes:[{id, label, questions:[...]}], edges:[{id, source, target, hypothesis, effect_type}]}`.
  Required for quantitative/mixed paradigms when confirmed (m3.py:57–73;
  `orchestrator/artifacts.py:84–116` `dod_design`).
- Legacy widget/LLM shape, `orchestrator/tools/m3_design.py:96–138`
  (`build_conceptual_model`): `{constructs:[str], paths:[{from, to, hypothesis}]}`.
- Variable-decomposition shape, seen in `agent/tools/instrument.py:173–176`
  (`sampling_plan`): `{dependent_variable, independent_variables:[...], moderator}`.
- Robust multi-shape consumption precedent: `orchestrator/tools/m5_writing.py:551+`
  (`_derive_scale_items` handles nodes[].questions vs flat `instrument.items` with a
  `construct` key); `instrument.py:169–191` counts paths/items across all shapes.

Mapping to `AdvanceModel` is close but not identity: dothesis nodes are **flat**
(`label` at top level, no `likertScale/average/standardDeviation`), dothesis edges say
`effect_type`/`hypothesis` instead of `data.effectType`, and dothesis has no
`moderate_effect` node type (moderation appears as a `moderator` field or a labeled
edge). Hence the adapter in §6.

**M4 parsing today**: `orchestrator/tools/m4_analysis.py` + `m4_parsers/` parse pasted
SmartPLS/SPSS/lavaan output (`dispatch_parse`, LLM fallback). These remain; the new
compute ops complement them for students who upload raw data instead of pasted output.

---

## 3. Architecture Overview

```
/Users/caonguyenvan/project/thesis-stats        (NEW standalone repo/dir)
├── pyproject.toml                              name = "thesis-stats", src layout
├── src/thesis_stats/
│   ├── __init__.py        # public API: run_spss_basic, run_spss_regression,
│   │                      #             run_pls, run_rigor  (+ AdvanceModel re-export)
│   ├── models.py          # ported verbatim from fillform models.py (pydantic schema)
│   ├── pls_engine.py      # ported PLSEngine (split out of smartpls_analyzer.py)
│   ├── smartpls.py        # ported SmartPLSAnalyzer (imports PLSEngine from pls_engine)
│   ├── spss.py            # ported SPSSAnalyzer
│   └── rigor.py           # NEW: assumption tests, effect sizes, Harman's test
└── tests/
    ├── conftest.py        # shared fixtures (seeded model + data from accuracy test)
    ├── test_pls_accuracy.py       # pytest port of test_smartpls_accuracy.py
    ├── test_pls_moderation.py     # NEW accuracy coverage for two-stage moderation
    ├── test_spss.py               # smoke + known-value tests for SPSSAnalyzer
    ├── test_golden_parity.py      # golden-JSON parity vs pre-extraction outputs
    ├── test_api.py                # public API coercion/error contract
    └── test_rigor.py              # NEW rigor layer, known-value tests

fillform/analyser           → thin consumer: main.py / exec_python.py import thesis_stats;
                              smartpls_analyzer.py / spss_analyzer.py / models.py DELETED

dothesis/agent/tools/stats.py → new whitelisted ops (pls_sem, efa, regression_full,
                                mediation, moderation, rigor) calling thesis_stats
                                in-process via a conceptual_model→AdvanceModel adapter
                                (agent/tools/model_adapter.py)
```

**Distribution:** not on PyPI. Both projects install via path/editable install:
- fillform: `-e /Users/caonguyenvan/project/thesis-stats` in `requirements.txt` (with a
  comment giving the git URL for CI), or `thesis-stats @ git+...` once a remote exists.
- dothesis: same line appended to `requirements.txt` under a new
  `# === Statistics engine (thesis-stats) ===` section, together with the transitive
  scientific deps it drags in. dothesis's sandbox image must add the package; the lib
  itself makes **zero network calls** so the network-less posture is unchanged.

**Python compatibility:** `requires-python = ">=3.10"` (dothesis floor is 3.10,
fillform venv runs 3.13.2). Dependency pins as **lower bounds** matching fillform's
known-good versions (`pandas>=2.2`, `numpy>=1.26`, `scipy>=1.11`, `pydantic>=2.5`,
`scikit-learn>=1.3`, `statsmodels>=0.14`, `factor-analyzer>=0.5.1`). `plspm` is dropped
(§2.1 — never imported). fastapi/uvicorn stay in fillform only.

---

## 4. Public API (`thesis_stats/__init__.py`)

Design principles: (1) every entry point accepts `AdvanceModel | dict` and coerces via
`AdvanceModel.model_validate` — this fixes the fillform `/bootstrapping` dict bug and
the `test_analyzers.py` baseline failures for free; (2) return plain
JSON-serializable dicts identical to today's analyzer outputs (numerical parity is the
contract); (3) raise typed exceptions, never `sys.exit` or bare `Exception`.

```python
# thesis_stats/__init__.py
from .models import AdvanceModel                    # re-exported for consumers

def run_spss_basic(model: AdvanceModel | dict, data: list[dict]) -> dict:
    """Descriptives + Cronbach + EFA (KMO/Bartlett/Varimax) + correlations + PLS fit.
    Same payload as SPSSAnalyzer.analyze_basic_statistics today."""

def run_spss_regression(model: AdvanceModel | dict, data: list[dict]) -> dict:
    """Multiple OLS per structural edge; F-test, R²/adj-R², coefficient table.
    Same payload as SPSSAnalyzer.analyze_linear_regression today."""

def run_pls(model: AdvanceModel | dict, data: list[dict],
            bootstrap_samples: int = 1000) -> dict:
    """Full PLS-SEM incl. two-stage moderation when the model contains
    moderate_effect nodes; mediation via raw_effects (direct/indirect/total).
    Same payload as SmartPLSAnalyzer.analyze_bootstrapping today."""

def run_rigor(data: list[dict] | "pd.DataFrame",
              *,
              model: AdvanceModel | dict | None = None,
              groups: str | None = None,
              regressions: list[dict] | None = None,   # [{"y": col, "x": [cols]}]
              checks: list[str] | None = None) -> dict:
    """NEW rigor layer — see §8. checks ⊆ {"normality","homogeneity",
    "effect_sizes","harman"}; None = run everything applicable to the inputs."""
```

Exceptions (defined in `thesis_stats/errors.py` or at top of `__init__.py`):

```python
class ThesisStatsError(Exception): ...          # base
class ModelSpecError(ThesisStatsError): ...     # bad/inconsistent AdvanceModel
class DataError(ThesisStatsError): ...          # missing columns, n too small, NaN block
```

The class-level API (`PLSEngine`, `SmartPLSAnalyzer`, `SPSSAnalyzer`) remains importable
from the submodules for power users and for the ported tests, but the four functions
above are the supported surface.

**Internal porting rule (parity-critical):** the analyzer/engine bodies are moved
**verbatim** — only import statements, module docstrings, and logging names change.
No numeric expression, iteration order, default, or rounding may be edited in the
extraction commits. Behavioral fixes (dict coercion) live only in the new thin
`run_*` wrappers, never inside the ported classes. The existing broad
`except Exception → raise Exception(...)` wrappers inside the analyzers
(e.g. smartpls_analyzer.py:293–296) are kept as-is in this pass and re-wrapped into
`ThesisStatsError` at the `run_*` boundary.

---

## 5. fillform Refactor (thin consumer)

Files touched in `/Users/caonguyenvan/project/fillform/analyser/`:

- **DELETE**: `smartpls_analyzer.py`, `spss_analyzer.py`, `models.py` (after the lib
  proves parity — the plan sequences this).
- **`main.py`**: replace analyzer imports with
  `from thesis_stats import run_pls, run_spss_basic, run_spss_regression` and
  `from thesis_stats.models import (AnalysisRequest, AnalysisResponse, BasicAnalysisResponse, LinearRegressionResponse)`.
  Endpoint bodies become one-liners. `/bootstrapping` may keep passing
  `request.model.dict()` — the lib now coerces — but should be cleaned to pass
  `request.model`. Map `ModelSpecError`/`DataError` → HTTP 422, other
  `ThesisStatsError` → 500. Server behavior on :4002 and response schemas are
  byte-compatible (same pydantic response models, now imported from the lib).
- **`exec_python.py`**: `PythonExecutor` delegates to the lib functions; CLI contract
  (`spss basic_analysis|linear_regression`, `smartpls bootstrapping`, JSON-file input,
  JSON-stdout output, exit codes) unchanged.
- **`test_smartpls_accuracy.py`** / **`test_analyzers.py`**: change imports to
  `from thesis_stats.smartpls import SmartPLSAnalyzer` etc. These stay in fillform as
  the consumer-side regression net *in addition to* their pytest ports inside the lib.
  `test_analyzers.py`'s dict-passing sections become green via API coercion (use the
  `run_*` functions there).
- **`requirements.txt`**: drop `plspm`, `pandas`, `numpy`, `scipy`, `statsmodels`,
  `scikit-learn`, `factor-analyzer` (now transitive via thesis-stats); keep
  fastapi/uvicorn/pydantic; add the thesis-stats path/git dependency.
  `setup_venv.sh` / `.bat` gain the editable install line.

Out of scope here: the Node.js caller (`nodejs_example.js`), systemd/launchd unit files
— the CLI and HTTP contracts they consume do not change.

---

## 6. dothesis Integration

### 6.1 Adapter: `agent/tools/model_adapter.py` (NEW)

`to_advance_model(conceptual_model: dict, *, measurement: dict[str, list[str]] | None = None, likert_scale: int = 5) -> dict`
— returns an `AdvanceModel`-shaped **dict** (kept as a dict so the module imports even
when thesis_stats is absent; the lib validates on entry). Handles all three verified
shapes (§2.2), tried in order:

1. **nodes/edges** (m3.py canonical): node `{id, label, questions}` →
   `{id, data:{label, nodeType:"variable", likertScale, average:0.0, standardDeviation:0.0}, questions}`
   (`average`/`standardDeviation` are only used by fillform's data *generator*, not the
   analyzers — safe placeholders); edge `{id, source, target, effect_type}` →
   `{id, source, target, data:{effectType: "negative" if effect_type=="negative" else "positive"}}`.
2. **constructs/paths** (m3_design legacy): construct labels double as node ids;
   `paths[].from/to` matched to constructs case-insensitively; edge ids synthesized
   (`e1..eN`). Questions must come from `measurement`.
3. **decomposition** (`dependent_variable` / `independent_variables` / `moderator`):
   star graph IV→DV; a `moderator` produces a `moderate_effect` node
   (`moderateVariable` = moderator id, `independentVariable` = first IV, plus a
   variable node for the moderator itself) targeting the DV — mirroring fillform's
   two-stage input contract (smartpls_analyzer.py:526–541).

`measurement` (construct label → data-file column names) **overrides** `questions` on
every path; when nodes carry `questions` that are Likert item *texts* rather than
column names (the widget shape — see m3.py:33–35), measurement is **required** and the
adapter raises `ValueError` listing the constructs that lack columns. The adapter also
validates that every mapped column exists in the uploaded file's header (the op passes
the columns in) and that each construct used in an edge exists as a node.

Unit-testable pure function; no store access, no LLM, no I/O.

### 6.2 New whitelisted ops in `agent/tools/stats.py`

Extend the existing `OPS` dict — same shape as today's vetted functions, same lazy
imports, same error envelope. `thesis_stats` is imported inside each op function so a
missing install degrades to the existing `"stats dependency missing"` JSON error path
(stats.py:199–200).

| op | params | returns (summarized for the LLM, not raw dumps) |
|---|---|---|
| `pls_sem` | `conceptual_model` (dict), `measurement`, `bootstrap_samples` (default 500, capped at 1000) | path coefficients + bootstrap t/p, R², outer loadings, AVE/CR/alpha (`raw_inner_summary`), HTMT, Fornell-Larcker, VIF, f², GoF |
| `efa` | `conceptual_model`, `measurement` | KMO, Bartlett, factors (eigenvalue, variance, loadings) — from `run_spss_basic`'s `efa_result` |
| `regression_full` | `conceptual_model`, `measurement` | per-hypothesis OLS: F-test, R²/adj-R², coefficient table w/ significance — `run_spss_regression` |
| `mediation` | `conceptual_model`, `measurement`, `bootstrap_samples` | `raw_effects` slice of `run_pls`: direct/indirect/total per path |
| `moderation` | `conceptual_model` (must yield a `moderate_effect` node — decomposition shape or explicit moderator param), `measurement`, `moderator`, `independent`, `target`, `bootstrap_samples` | interaction-term path coefficient + bootstrap significance from two-stage PLS |
| `rigor` | `columns` or `measurement`, optional `group`, optional `regressions` | §8 payload: Shapiro-Wilk, Levene, Cohen's f²/d, Harman single-factor |

Each op body: `df = _load_df(file)` (existing loader, so `.sav`/xlsx/csv all work) →
adapter → `thesis_stats.run_*(model, df.to_dict("records"), ...)` → **summarize** to a
bounded JSON payload (drop `raw_scores`, `raw_crossloadings` row-level data — the LLM
needs tables, not matrices of n×k floats; cap matrices at the construct level). The
`run_stats` tool docstring (stats.py:179–190) is updated to advertise the new ops and
their params.

**Result-size guard:** summarizers must keep each op's JSON under a few KB (constructs
are ≤ ~10 in practice). This is both a token-budget and a "schema not data" guarantee
consistent with `test_detect_returns_schema_not_data`.

### 6.3 Security posture — explicitly preserved

- Ops remain **vetted functions in the whitelist dict**; the model still only picks
  `op` + `params`. No new code path evaluates model-supplied strings.
- All computation is **in-process** pandas/numpy/scipy — no subprocess, no sockets.
  thesis_stats performs no network I/O by construction (audit requirement: the lib must
  not import `requests`/`urllib`/`httpx` anywhere).
- fillform's HTTP server is **not** called from dothesis, ever.
- `bootstrap_samples` is clamped server-side (≤1000) so a hostile prompt cannot turn an
  op into a CPU DoS; default 500 matches `exec_python.py:75`.
- `conceptual_model` should be sourced from the context_store where available. This
  pass keeps `run_stats`'s existing stateless signature (op/file/params) — the agent
  passes the model dict it read via `read_slice` — but the op validates the dict
  structurally before use. A store-bound factory variant (pattern:
  `make_sampling_plan_tool`, instrument.py:141) is a noted follow-up, not required now.

### 6.4 What happens to the parsers

Nothing, this pass. `m4_parsers/` still serve students who paste tool output.
`check_thresholds` still classifies pasted tables. The new ops give the *computed*
numbers the same downstream treatment (the agent can feed computed tables into its
existing interpretation flow). Consolidation is a follow-up.

---

## 7. Data Flow

**fillform (unchanged externally):**
`Node.js → HTTP :4002 or spawn exec_python.py → thesis_stats.run_* → JSON response`

**dothesis (new capability):**
```
student uploads data.csv/.sav
  → agent reads conceptual_model from context_store (read_slice M3)
  → agent calls run_stats(op="pls_sem", file=<path>,
        params={conceptual_model, measurement, bootstrap_samples})
  → stats.py: _load_df → model_adapter.to_advance_model → thesis_stats.run_pls
  → summarizer → bounded JSON → agent narrates / feeds M4 artifacts
```

---

## 8. New Rigor Layer (`thesis_stats/rigor.py`)

All functions pure, scipy/numpy/sklearn only. `run_rigor` composes them; each is also
individually importable and unit-tested against known values.

1. **Normality — Shapiro-Wilk** (`scipy.stats.shapiro`) per numeric column (or per
   construct composite when a model/measurement is given). Returns
   `{column: {W, p, normal: p >= .05, n}}`. Skip with a warning entry when n > 5000
   (Shapiro's validity limit) or n < 3.
2. **Homogeneity — Levene** (`scipy.stats.levene`, center="median" i.e.
   Brown-Forsythe) for each numeric column across the levels of `groups`. Returns
   `{column: {W, p, homogeneous: p >= .05, group_ns}}`. Requires ≥2 groups with n ≥ 2.
3. **Regression effect sizes** — for each `{"y", "x"}` spec: model R² → **Cohen's f² =
   R²/(1−R²)**, plus per-predictor f² by the leave-one-out formula
   `(R²_full − R²_reduced)/(1 − R²_full)` (same formula as
   smartpls_analyzer.py:972–1020 — reuse/port, don't duplicate constants), with
   small/medium/large banding (.02/.15/.35). **Cohen's d** (pooled-SD) for the
   two-group case when `groups` is given: `{value_col: {d, interpretation}}` banding
   (.2/.5/.8).
4. **Harman's single-factor test** (common-method bias): unrotated single-factor EFA
   (factor_analyzer, rotation=None, n_factors=1) — or first principal component — over
   all measurement items; report `{first_factor_variance_pct, threshold: 50.0, concern: pct > 50}`.

Output envelope:
```json
{"checks": {"normality": {...}, "homogeneity": {...},
            "effect_sizes": {...}, "harman": {...}},
 "warnings": ["homogeneity skipped: no group column supplied", ...]}
```
Checks that can't run with the supplied inputs are skipped with a warning, never an
exception (rigor is advisory).

---

## 9. Error Handling

- **Library:** typed exceptions (§4). Validation order: schema (`ModelSpecError`) →
  data columns/shape (`DataError`) → computation (wrapped as `ThesisStatsError` with
  the underlying message). No `print`, no `sys.exit`; logging via module loggers.
- **fillform server:** 422 for `ModelSpecError`/`DataError`, 500 otherwise (today
  everything is 500 — this is a strict improvement, and the response *success* schema
  is unchanged).
- **fillform CLI:** unchanged envelope (`{"error", "traceback", ...}` + exit 1).
- **dothesis:** existing catch-all in `run_stats` (stats.py:197–203) already converts
  any exception into `{"error": "..."}` JSON — new ops inherit it. Adapter
  `ValueError`s surface with actionable text ("construct 'X' has no measurement
  columns; supply params.measurement").

---

## 10. Testing Strategy

**The numerical-parity guardrail is the centerpiece.** Order of proof:

1. **Baseline capture (before any code moves):** run
   `fillform/analyser/test_smartpls_accuracy.py` (must pass — verified it does) and a
   new one-off script that dumps golden JSON outputs of
   `analyze_bootstrapping(model, data, bootstrap_samples=0)`,
   `analyze_basic_statistics`, `analyze_linear_regression` on the seeded fixtures into
   `thesis-stats/tests/golden/*.json`. Bootstrap-dependent keys are excluded from
   golden comparison (bootstrap uses unseeded resampling); everything deterministic
   (scores, loadings, paths, HTMT, FL, VIF, f², EFA, descriptives, regression tables)
   is compared to ~1e-9.
2. **Lib-internal suite:** pytest port of the accuracy test (same reference
   implementations, same tolerances), golden-parity test, API contract tests
   (dict coercion, typed errors), **new moderation accuracy test** (seeded fixture
   with a `moderate_effect` node; assert stage-2 interaction construct exists and its
   path coefficient matches an independent LV-score-product OLS reference) — closing
   the biggest hole in today's net (the accuracy suite has zero moderation coverage).
3. **fillform consumer suite:** existing two test files, imports switched to the lib,
   all-green (including the two sections that are red today — see §2.1).
4. **dothesis suite:** adapter unit tests (three shapes ×
   happy/missing-measurement/unknown-construct), new-op tests in
   `agent/tests/test_stats_tool.py` style (`pytest.importorskip("thesis_stats")`,
   seeded CSV fixtures with known structure, assert e.g. PLS path sign/magnitude,
   whitelist rejection still works, result payload bounded), rigor known-value tests
   (e.g. Shapiro on N(0,1) sample p > .05; Levene on unequal-variance groups p < .05;
   Cohen's d on shifted samples ≈ known d).
5. **End-to-end:** fillform server smoke (`curl` the three endpoints), fillform CLI
   smoke, dothesis full test run.

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Hand-rolled PLS accuracy.** `PLSEngine` deliberately replaces `plspm` (its docstring documents plspm's broken sign correction). Its correctness rests **entirely** on `test_smartpls_accuracy.py` — one 3-construct recursive fixture, no moderation, no bootstrap validation. | Plan front-loads running the suite (done — passes), ports it into the lib's CI, and **adds** a moderation-accuracy fixture and a bootstrap sanity check (bootstrap mean ≈ original estimate, SE > 0) **before** dothesis ships ops on top of it. Documented in the lib README as the trust anchor. |
| Silent numeric drift during the move | Verbatim-port rule (§4) + golden-parity test at ~1e-9 + accuracy suite in both repos. |
| `test_analyzers.py` baseline is already partially red | Recorded here; fixed via API dict-coercion, not by weakening asserts. |
| Dependency weight in dothesis (pandas/scipy/sklearn/factor-analyzer enter its env) | Lazy imports inside ops keep dothesis importable without them (existing pattern); sandbox image updated deliberately; `plspm` dropped. |
| conceptual_model shape drift (3 shapes today, more tomorrow) | Adapter is a single pure function with exhaustive shape tests; unknown shapes raise a clear `ValueError` rather than mis-analyzing. |
| CPU abuse via bootstrap param | Clamp ≤1000 in the op layer. |
| Two repos + a path dependency = broken-checkout risk | Editable install documented in both READMEs/setup scripts; ops degrade to clean JSON error if lib missing. |
| fillform `/bootstrapping` dict bug interacts with refactor | Coercion at lib boundary fixes it; endpoint also cleaned to pass the model object; covered by server smoke test. |

---

## 12. Out of Scope (explicit, deferred follow-ups)

- **A-priori / post-hoc power analysis** (G*Power-style) — follow-up to rigor layer.
- **Missing-data imputation strategy** (today: pandas default NaN handling / dropna) —
  follow-up; rigor may later report missingness but does not impute.
- Publishing thesis-stats to PyPI; versioning/release automation.
- Consolidating `m4_parsers` with computed results; store-bound `run_stats` factory.
- Replacing fillform's HTTP server or Node.js integration.
- dothesis UI/skill-file work to surface the new ops beyond the tool docstring update.
