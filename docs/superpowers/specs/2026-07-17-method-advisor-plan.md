# Assumption-Driven Method Advisor — Implementation Plan

**Date:** 2026-07-17
**Status:** Ready to execute
**Design:** `docs/superpowers/specs/2026-07-17-method-advisor-design.md` (read it first — the decision table §6, ranking rules §7, output shape, and every integration point are defined there; do not re-litigate placement §3 or surface §8)
**Executor notes:** All paths are relative to the dothesis repo root (`/Users/caonguyenvan/project/dothesis`); run all commands from there. Strict TDD: every task writes the failing test first, then the minimum code to pass. Phase 1 is the only submodule work and lands **before** any dothesis wiring (Phase 2's `build_data_profile` imports the new engine check). Everything is offline and deterministic — no network, no unseeded RNG, no LLM.

**Submodule workflow reminder** (`libs/thesis-stats/README.md`, "Editing from a consumer"): edit under `libs/thesis-stats/`, commit + push **inside the submodule**, then `git add libs/thesis-stats` in the parent repo to bump the pinned pointer. The submodule is installed editable, so edits apply immediately without reinstalling. **No new dependency anywhere** — pandas/numpy for the engine check; stdlib `hashlib`/`json` for the advisor.

**Two invariants to hold at every step:**
1. Every finding/verdict the advisor emits is **soft/advisory** — no `hard` severity, no gate, no auto-switch of `methodology` (design §1). If you find yourself writing a block, stop.
2. Store state (chosen method, `sample_plan.power_analysis`, `conceptual_model`) is read **server-side by the store-bound tool only** — never accepted as a model-supplied tool argument (design §5.3, §8; the `instrument.py:161-166` F0 lesson).

---

## Phase 1 — thesis-stats: `check_distribution` in `rigor.py`

Everything in this phase lives in the submodule. No dothesis imports.

### Task 1.1 — `check_distribution` + `run_rigor` wiring
- **Files:** `libs/thesis-stats/src/thesis_stats/rigor.py` (edit), `libs/thesis-stats/tests/test_rigor.py` (extend)
- Tests first (design §4, §10.1; seed all data with `numpy.random.default_rng(42)`):
  - `rng.exponential(size=300)` column → `skewness > 2`, `severe is True`; `rng.normal(size=300)` → `|skewness| < 1`, `severe is False`;
  - excess-kurtosis convention: a heavy-tailed column (e.g. Student-t df=3 draws) → `kurtosis > 7` flags `severe` even with modest skew;
  - `_summary` block: `n_items`, `severe_n`, `severe_pct` arithmetic (e.g. 7 severe of 16 → 43.75), `thresholds == {"abs_skew": 2.0, "abs_kurtosis": 7.0}`, citation string present;
  - constant column and n < 3 column → skipped into the returned `warnings`, not present in the result (mirror `check_normality`'s posture at `rigor.py:53-64`);
  - scoping: with a model supplied, columns are the model's measurement items via `_measurement_items` (`rigor.py:158-168`) — same columns as the `normality` check for the same model (assert set equality);
  - `run_rigor(data, checks=["distribution"])` returns the block under `result["checks"]["distribution"]`; `checks=None` (default) now includes it; inapplicable input (no numeric columns) → warning, never a raise (`rigor.py:173-179` composer contract);
  - agreement guard: for the same column, `check_distribution`'s skewness equals `pandas.Series.skew()` (the estimator `spss.py:193-194` uses) to 1e-9.
- Implement per design §4: `check_distribution(df, columns=None) -> tuple[dict, list[str]]`, `SEVERE_SKEW = 2.0` / `SEVERE_KURTOSIS = 7.0` module constants, wire `"distribution"` into `run_rigor`'s `selected` default list (`rigor.py:191`).
- **Verify:** `python -m pytest libs/thesis-stats/tests/test_rigor.py -q`
- **Done when:** green; `check_distribution` uses pandas/numpy only; no change to any existing check's output (run the whole rigor test file, not just new cases).

### Task 1.2 — validation ride-along (soft plausibility bounds only)
- **Files:** `libs/thesis-stats/src/thesis_stats/validation.py` (edit: `METRICS` at `:24`, `_bounds` at `:110`, `claims_from_rigor` at `:718`), `libs/thesis-stats/tests/test_validation_bounds.py` (extend), `libs/thesis-stats/tests/test_validation_adapters.py` (extend)
- Tests first (design §4 last bullet): `skew` claim value 25 → **soft** `bounds.skew_plausible`; `skew` = 1.8 → clean; `kurtosis` = 250 → soft; a real `run_rigor(checks=["distribution"])` output through `claims_from_rigor` → correct claims emitted and **zero findings** (golden-clean, `test_validation_golden.py` pattern). Regression-guard: no `hard` severity exists for either metric (assert explicitly — design §1's no-hard rule starts here).
- Implement: add `"skew"`, `"kurtosis"` metrics; soft bounds |skew| > 20, |kurtosis| > 200 ("mis-parsed column, not a distribution"); emit the claims from the `distribution` block in `claims_from_rigor`.
- **Verify:** `python -m pytest libs/thesis-stats/tests -q` (whole submodule suite — proves no engine/validation regression)
- **Done when:** whole submodule suite green.

### Task 1.3 — version bump, README, submodule commit + pointer bump
- **Files:** `libs/thesis-stats/src/thesis_stats/__init__.py` (bump `__version__` `"0.4.0"` → `"0.5.0"` at `:38`; no new exports — `check_distribution` is reached via `run_rigor` and `thesis_stats.rigor`), `libs/thesis-stats/README.md` (add skew/kurtosis severe-non-normality to the rigor bullet)
- Steps (submodule workflow):
  1. `cd libs/thesis-stats && git add -A && git commit -m "feat(rigor): check_distribution — per-item skewness/kurtosis with severe non-normality flags (West, Finch & Curran 1995)" && git push`
  2. `cd ../.. && git add libs/thesis-stats` (pointer bump — commits with the parent-repo work of later phases, or as its own commit now).
- **Verify:** from the repo root, `python -c "from thesis_stats.rigor import check_distribution; import pandas as pd, numpy as np; r,_ = check_distribution(pd.DataFrame({'x': np.random.default_rng(42).exponential(size=300)})); print(r['x']['severe'])"` prints `True`.
- **Done when:** import works from the parent repo; submodule remote has the commit; parent pointer staged (`git submodule status libs/thesis-stats` SHA matches the pushed commit).

## Phase 2 — the pure decision core (`agent/method_advisor.py`)

Pure module: stdlib + (lazy, optional) thesis_stats for the data profile only. **No LangChain, no store, no I/O in this phase** — the tool factory comes in Phase 3, mirroring how `agent/preflight.py` separates `preflight_check` (:18-42) from `make_preflight_tool` (:45-70).

### Task 2.1 — `profile_model` (three shapes) + `max_in_degree` single-sourcing
- **Files:** `agent/method_advisor.py` (new), `agent/tests/test_method_advisor.py` (new), `agent/tools/instrument.py` (edit: `_max_in_degree` at `:141-156` delegates), `agent/tests/test_sampling_plan_power.py` (must stay green — regression guard for the delegation)
- Tests first (design §5.1, §10.2 `mediation_shape` row):
  - all three conceptual_model shapes (`model_adapter.py:9-16`: nodes/edges, constructs/paths, decomposition) produce the **identical** profile dict for equivalent models — parameterize one model expressed three ways;
  - `latent_model` true iff any construct has ≥ 2 items (node `questions`, else grouped `instrument.items`); `single_item_constructs` lists names;
  - `has_mediation`: X→M→Y chain detected (a node with inbound + outbound edges on a directed path to the outcome); no false positive on a plain IV→DV star;
  - `has_moderation`: moderator node type, `effect: "moderates"` edge label (M3 skill shape, `SKILL.md:40-43`), decomposition `moderator` key, and `moderate_effect` node (`model_adapter.py:149-159`) all detected;
  - `max_in_degree` equals the current `instrument._max_in_degree` for a table of models (including the decomposition + moderator case, `instrument.py:152-155`) — then flip `instrument.py` to `from agent.method_advisor import max_in_degree` and re-run `test_sampling_plan_power.py` untouched;
  - `construct_nature`: node `nature: "formative"` honored; absent → `"unknown"`; never raises on missing measurement (unlike `to_advance_model`, `model_adapter.py:66-72` — assert a questions-free model profiles fine);
  - malformed/empty model → a minimal profile with `latent_model: None`-ish unknowns, never a raise.
- Implement `profile_model(conceptual_model, instrument=None) -> dict` and module-level `max_in_degree(cm) -> int` (moved logic; `instrument.py` keeps a thin delegating `_max_in_degree` so its callers and tests don't move).
- **Verify:** `python -m pytest agent/tests/test_method_advisor.py agent/tests/test_sampling_plan_power.py -q`
- **Done when:** green; `agent/method_advisor.py` imports with no thesis_stats / langchain / pandas at module level.

### Task 2.2 — `build_data_profile` (lazy engine composition)
- **Files:** `agent/method_advisor.py`, `agent/tests/test_method_advisor.py`
- Tests first (design §5.2; seeded tmp_path CSVs):
  - n_rows; `normality` populated from `thesis_stats.rigor.check_normality`, `distribution` from `check_distribution` (Phase 1) — for the `skewed_small` fixture (n = 95, exponential→Likert-1-5) assert `distribution["_summary"]["severe_pct"] > 25`;
  - `missing_overall_pct` from direct isna arithmetic (a fixture with 3 NaNs of 100×4 cells → 0.75);
  - `likert_levels`: integer 1-5 items → 5; a continuous column mixed in is excluded from the level count when an items list is given;
  - item scoping: explicit items list, else numeric columns (the `screening.py:396-400` fallback posture);
  - **fail-open:** monkeypatch the thesis_stats import to raise → profile returns with `normality`/`distribution` `None` + a warning string; no exception escapes (design §8 fail-open bullet).
- Implement `build_data_profile(df, items=None) -> dict` with lazy `from thesis_stats.rigor import ...` inside the function.
- **Done when:** green.

### Task 2.3 — decision table + `advise_method` + ranking + justifications + fingerprint
- **Files:** `agent/method_advisor.py`, `agent/tests/test_method_advisor.py`
- Tests first (design §6, §7, §10.2 — this is the heart; assert exact evidence rows, not just ranks):
  - **`skewed_small`** (n = 95, severe non-normality, latent model, chosen `"CB-SEM (AMOS)"`, store power N 160): `pls_sem` rank 1; evidence contains `cb_sem_sample_floor` row with `observed == {"n": 95}` and verdict `strongly_against` (n < 100), and `normality` row with the observed `severe_pct`/`severe_n`/`n_items` and verdicts `{"cb_sem": "strongly_against", "pls_sem": "favors", "nonparametric": "favors"}`; C4 caveat quotes `95` and `160`; `conflict_with_choice` non-null with `reasons == ["cb_sem_sample_floor", "normality"]` and a sentence naming both;
  - **`normal_adequate`** (n = 300, MVN→Likert-7, `goal="confirmation"`, chosen CB-SEM): cb_sem has zero `strongly_against`; cb_sem rank 1; `conflict_with_choice is None`;
  - **`no_latent`** (single-item constructs, n = 200): `regression` rank 1; C1 row `against` pls_sem and cb_sem;
  - **`design_mode`** (no data profile; `target_n = 80`, `power_analysis.required_n = 160`): `mode == "design"`; `unknown` contains `normality`/`missingness`/`scale_type` entries with the "re-run after data upload" line; C4 caveat uses the **store** numbers (80 < 160) — and stays correct when `thesis_stats` is absent entirely (no engine import on this path);
  - ranking mechanics: lexicographic `(strongly_against, against, -favors)` with tie-break order `regression → pls_sem → cb_sem → nonparametric` — construct a tie and assert the order (design §7);
  - conflict-null cases: chosen method rank 1 → null; unmapped methodology string (`"Thematic Analysis"`) → null + caveat;
  - `mcar_p = 0.01` → C7 note row present, `neutral` verdicts only, containing the v1 "applies neither" caveat wording (design §6 C7; `screening.py:332-335`); `mcar_p = None` → row limited to missing-pct;
  - justification pair: `plain` and `formal` both non-empty; `formal` contains at least one citation from the firing rows; deterministic templates (two identical calls → byte-identical `json.dumps` output, sorted keys);
  - `inputs_fingerprint`: changes when `methodology` / model / `target_n` / mode changes; stable otherwise;
  - **no hard anywhere**: walk the full payload of every fixture and assert the string `"hard"` never appears as a severity (invariant 1);
  - JSON-serializability of every payload; floats rounded to 4 dp.
- Implement: `DECISION_TABLE`-driven `advise_method(model_profile, data_profile, chosen_method_raw, target_n, power_analysis, mcar_p=None, goal=None) -> dict` per design §6-§7, `normalize_method(s)` (the `instrument.py:216-220` keyword mapping, extracted here and reused — same single-sourcing move as `max_in_degree`), `_justify` templates per top-method × firing-criteria (the `power.py:237-265` pattern), fingerprint = `sha1` over canonical JSON of the design-§7 input tuple.
- **Verify:** `python -m pytest agent/tests/test_method_advisor.py -q`
- **Done when:** green; the module still imports without thesis_stats installed (temporarily `pip uninstall`-free check: run the design_mode tests with the import monkeypatched away).

## Phase 3 — the store-bound tool

### Task 3.1 — `make_method_advisor_tool` + persistence + runtime registration
- **Files:** `agent/method_advisor.py` (add the factory at the bottom, `preflight.py:45-70` pattern), `agent/runtime.py` (import near `:159`, register in the tool list near `:518`/`:527`), `agent/tests/test_method_advisor.py` (extend with the temp-store pattern from `test_sampling_plan_power.py`)
- Tests first (design §8):
  - design mode: store carrying `methodology`/`conceptual_model`/`sample_plan` (flat keys), tool called with no `file` → JSON payload `mode == "design"`, and the store now holds `contextStore.method_advice` with the same payload (persisted via `commit_slice("M3", ...)` — assert the slice/reason like the sampling_plan persistence test does, `instrument.py:249-254`);
  - data mode: `file=` a seeded `skewed_small` CSV in tmp_path → `mode == "data"`, n from rows, conflict as in Task 2.3;
  - store trust: the tool signature exposes **only** `file`, `measurement`, `mcar_p`, `goal` — assert the LangChain tool's args schema contains no `methodology`/`context_store`/`target_n` argument (invariant 2, made executable);
  - nested store shape: a `{m3_design: {...}}`-wrapped store works (the `preflight.py:20-24` unwrap);
  - fail-open: store `commit_slice` raising → advice still returned (`instrument.py:249-254` posture); unreadable `file` path → `{"error": ...}` JSON, no raise;
  - screened-file convenience: passing `<stem>_screened.csv` just works (it's a plain CSV — one smoke case).
- Implement per design §8: `method_advice(file: str = "", measurement: dict | None = None, mcar_p: float | None = None, goal: str | None = None) -> str`; file loading may reuse `_load_df` via a local import from `agent.tools.stats` (`stats.py:21-32`) — do not duplicate the .sav/.xlsx logic.
- **Verify:** `python -m pytest agent/tests/test_method_advisor.py -q && python -c "import agent.runtime"` (registration importable)
- **Done when:** green; tool registered in `agent/runtime.py`'s list next to `make_preflight_tool(store)`.

## Phase 4 — preflight items, rubric ride-along, defense hint

### Task 4.1 — two preflight items + fingerprint staleness
- **Files:** `agent/preflight.py` (edit `preflight_check`, `:27-42`), `agent/tests/test_m3_contract.py` or the module currently testing `preflight_check` (locate: `grep -rln preflight_check agent/tests quality`), one rubric test (locate `preflight_dimension` tests: `grep -rln preflight_dimension --include="test_*.py" .`)
- Tests first (design §9.2, §9.3):
  - `methodology` present, no `method_advice` → the "not advisor-checked" item; `method_advice` present → item absent;
  - persisted `method_advice.conflict_with_choice` with a **matching** fingerprint → the conflict item with the chosen/advised methods and first reason; with a **stale** fingerprint (mutate `methodology` after persisting) → item suppressed (design §7 fingerprint contract);
  - both store shapes (flat + nested `m3_design`, `preflight.py:20-24`);
  - rubric ride-along: three stores — advised-no-conflict, un-advised, advised-with-current-conflict — score strictly decreasing on the `preflight` dimension (`quality/rubric.py:111-128`), with **zero changes to quality/rubric.py** (the test IS the proof, per the power precedent `2026-07-17-power-analysis-design.md` §8.3);
  - findings remain advisory strings; `preflight_check` stays pure (fingerprint recomputation calls the pure helper from `agent.method_advisor` — pure-to-pure import, same layering as `quality/rubric.py:120` importing `agent.preflight`).
- **Verify:** `python -m pytest agent/tests -q -k "preflight or m3_contract or method_advisor"` plus the rubric test path found above
- **Done when:** green; no rubric code changed.

### Task 4.2 — defense model-answer hint
- **Files:** `agent/tools/defense.py` (edit `_state_weakpoints`; the power hint upgrade landed in the same function — extend it), its test module (`grep -rln _state_weakpoints agent/tests/`)
- Tests first (design §9.5): `method_advice` present → the method-choice staple's `model_answer_hint` contains the formal justification sentence; current-fingerprint conflict present → an examiner question naming the violated assumptions is added, with the evidence criteria in the hint; no `method_advice` → existing behavior byte-identical.
- **Done when:** green; pure function change only.

## Phase 5 — skills + copy + final gates

### Task 5.1 — M3 and M4 skill sections
- **Files:** `skills/dothesis-m3-design/SKILL.md` (edit §3c around `:109-115`: call `method_advice` before endorsing a method, quote its `formal` sentence; the matrix rule at `:112-115` becomes "tool first, matrix for narrative"; keep the tradeoffs rule `:155` language), `skills/dothesis-m4-analysis/SKILL.md` (pipeline `:92-103`: insert step 1.5 — after `screening`, re-run `method_advice(file=..., mcar_p=<missing.mcar.p from the screening report>)`; on conflict, surface in both registers + offer the methodology sentence + never refuse the chosen analysis, mirroring the preflight posture `:79-93`), `skills/dothesis-m3-design/references/design-test-matrix.md` (top note: "the executable form of this matrix is the `method_advice` tool; this file is the narrative + worked examples")
- No test files — the phase gate is the full suites plus copy checks.
- **Verify:** `grep -n "method_advice" skills/dothesis-m3-design/SKILL.md skills/dothesis-m4-analysis/SKILL.md` shows both surfaces documented; `python -m pytest agent/tests -q` green.
- **Done when:** skills and the tool docstring agree on the argument contract (`file`, `measurement`, `mcar_p`, `goal` — nothing else).

### Task 5.2 — final gates
- **Verify (all must pass):**
  1. `python -m pytest libs/thesis-stats/tests -q` — fully green;
  2. `python -m pytest agent/tests -q` — fully green (includes the untouched `test_sampling_plan_power.py`);
  3. the rubric ride-along test from Task 4.1 — green with `git diff --stat quality/` empty;
  4. `git submodule status libs/thesis-stats` — SHA matches the pushed Task 1.3 commit; parent commit includes the pointer bump;
  5. determinism spot-check: run the `skewed_small` advisor test twice — identical output (already asserted in-suite, re-run as the gate).
- **Done when:** all five pass. Do not merge with a red anywhere — the advisor's entire value is that its numbers and rows are exactly reproducible.

---

## Execution order & gates

1. Phase 1 entirely inside the submodule; **push the submodule before Phase 2** (Task 2.2 imports `check_distribution`).
2. Phase 2 before 3 (the tool is a thin shell over the pure core); Task 2.1's `max_in_degree` delegation must keep `test_sampling_plan_power.py` green before moving on.
3. Phase 4 after 3 (preflight reads what the tool persists).
4. Phase 5 last — it documents what already works.

**Fixed anchors (do not weaken):** severe-non-normality thresholds |skew| > 2 / |kurtosis| > 7 (West, Finch & Curran 1995); CB-SEM floors against-at-150 / strongly-against-at-100 (Kline 2016; `design-test-matrix.md:53-55`); ranking tie-break `regression → pls_sem → cb_sem → nonparametric` (M3 parsimony rule); **no hard findings, no gate, no auto-switch — anywhere**.
