"""run_stats — whitelisted ops produce real numbers; non-ops are rejected."""
import json

import pytest

pd = pytest.importorskip("pandas")

from agent.tools.stats import run_stats


@pytest.fixture
def csv(tmp_path):
    # Deterministic toy data: y correlates strongly with x1, weakly with x2.
    rows = 40
    x1 = [i / 10 for i in range(rows)]
    x2 = [(i % 7) / 7 for i in range(rows)]
    y = [0.8 * a + 0.1 * b + 1.0 for a, b in zip(x1, x2)]
    df = pd.DataFrame({
        "x1": x1, "x2": x2, "y": y,
        "item1": x1, "item2": [v + 0.05 for v in x1], "item3": [v - 0.03 for v in x1],
        "group": ["a" if i % 2 else "b" for i in range(rows)],
    })
    p = tmp_path / "data.csv"
    df.to_csv(p, index=False)
    return str(p)


def _run(op, file, params=None):
    return json.loads(run_stats.func(op, file, params))


def test_non_whitelisted_op_rejected(csv):
    out = _run("eval_python", csv)
    assert out["error"].startswith("op 'eval_python' is not whitelisted")
    assert "detect" in out["available"]


def test_detect_returns_schema_not_data(csv):
    out = _run("detect", csv)
    assert out["rows"] == 40
    names = [c["name"] for c in out["columns"]]
    assert "y" in names and "group" in names
    # Schema only — no row dumps.
    assert "data" not in out


def test_cronbach_high_for_parallel_items(csv):
    out = _run("cronbach", csv, {"items": ["item1", "item2", "item3"]})
    assert out["alpha"] > 0.9


def test_regression_recovers_coefficients(csv):
    out = _run("regression", csv, {"y": "y", "x": ["x1", "x2"]})
    assert out["r2"] > 0.99
    assert abs(out["coefficients"]["x1"]["beta"] - 0.8) < 0.01
    assert out["coefficients"]["x1"]["p"] < 0.001


def test_ttest_runs(csv):
    out = _run("ttest", csv, {"value": "y", "group": "group"})
    assert "t" in out and "p" in out
    assert set(out["groups"]) == {"a", "b"}


def test_missing_file_is_clean_error(tmp_path):
    out = _run("describe", str(tmp_path / "nope.csv"))
    assert "failed" in out["error"]


# --- thesis-stats-backed ops ------------------------------------------------

ts = pytest.importorskip("thesis_stats")
np = pytest.importorskip("numpy")


@pytest.fixture
def pls(tmp_path):
    """3-construct reflective model A->B->C (+A->C), 3 items each, positive."""
    rng = np.random.default_rng(7)
    n = 120
    a = rng.normal(0, 1, n)
    b = 0.6 * a + rng.normal(0, 0.8, n)
    c = 0.5 * b + 0.3 * a + rng.normal(0, 0.8, n)

    def items(latent, prefix):
        out = {}
        for i in (1, 2, 3):
            raw = 0.8 * latent + rng.normal(0, 0.6, n)
            out[f"{prefix}{i}"] = np.clip(np.round(raw * 1.2 + 3.0), 1, 5).astype(int)
        return out

    cols = {}
    cols.update(items(a, "A"))
    cols.update(items(b, "B"))
    cols.update(items(c, "C"))
    p = tmp_path / "pls.csv"
    pd.DataFrame(cols).to_csv(p, index=False)
    cm = {
        "nodes": [
            {"id": "A", "label": "A", "questions": ["A1", "A2", "A3"]},
            {"id": "B", "label": "B", "questions": ["B1", "B2", "B3"]},
            {"id": "C", "label": "C", "questions": ["C1", "C2", "C3"]},
        ],
        "edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "C"},
                  {"source": "A", "target": "C"}],
    }
    return str(p), cm


def test_pls_sem_computes_bounded_payload(pls):
    path, cm = pls
    out = _run("pls_sem", path, {"conceptual_model": cm, "bootstrap_samples": 0})
    assert out["paths"]["A -> B"]["beta"] > 0  # positive by construction
    assert out["reliability"] and all("ave" in v for v in out["reliability"].values())
    assert out["htmt"] and out["f_squared"]
    # bounded, construct-level summary (schema not data)
    assert len(json.dumps(out)) < 8192


def test_pls_clamps_bootstrap_samples(pls, monkeypatch):
    path, cm = pls
    captured = {}

    def fake_run_pls(model, data, bootstrap_samples=1000, q2_omission_distance=None):
        captured["bs"] = bootstrap_samples
        return {"raw_path_coefficients": {}, "raw_inner_summary": {},
                "raw_unidimensionality": {}, "raw_outer_model": {}, "raw_bootstrap": None}

    monkeypatch.setattr(ts, "run_pls", fake_run_pls)
    out = _run("pls_sem", path, {"conceptual_model": cm, "bootstrap_samples": 999999})
    assert captured["bs"] == 1000  # clamped
    assert out["bootstrap_samples"] == 1000


def test_efa_returns_kmo_and_factors(pls):
    path, cm = pls
    out = _run("efa", path, {"conceptual_model": cm})
    assert out["kmo"] is not None and 0.0 < out["kmo"] <= 1.0
    assert out["factors"]


def test_regression_full_returns_table(pls):
    path, cm = pls
    out = _run("regression_full", path, {"conceptual_model": cm})
    assert out["regression"] is not None
    assert "r_squared" in out["regression"]


def test_mediation_returns_effects(pls):
    path, cm = pls
    out = _run("mediation", path, {"conceptual_model": cm, "bootstrap_samples": 0})
    # A -> C has an indirect path via B
    keys = list((out.get("effects") or {}).keys())
    assert any("A -> C" == k for k in keys)


def test_rigor_returns_envelope(pls):
    path, cm = pls
    out = _run("rigor", path, {"regressions": [{"y": "A1", "x": ["A2", "A3"]}]})
    assert {"checks", "warnings"} <= set(out)  # run_stats also adds "op"
    assert "normality" in out["checks"] and "effect_sizes" in out["checks"]


@pytest.fixture
def moderated(tmp_path):
    rng = np.random.default_rng(11)
    n = 300
    x = rng.normal(0, 1, n)
    w = rng.normal(0, 1, n)
    y = 0.4 * x + 0.3 * w + 0.4 * (x * w) + rng.normal(0, 0.7, n)

    def items(latent, prefix):
        return {f"{prefix}{i}": np.clip(np.round((0.8 * latent + rng.normal(0, 0.6, n)) * 1.2 + 3.0), 1, 5).astype(int)
                for i in (1, 2, 3)}

    cols = {}
    for latent, prefix in ((x, "X"), (w, "W"), (y, "Y")):
        cols.update(items(latent, prefix))
    p = tmp_path / "mod.csv"
    pd.DataFrame(cols).to_csv(p, index=False)
    cm = {"dependent_variable": "Y", "independent_variables": ["X"], "moderator": "W"}
    measurement = {"Y": ["Y1", "Y2", "Y3"], "X": ["X1", "X2", "X3"], "W": ["W1", "W2", "W3"]}
    return str(p), cm, measurement


def test_moderation_returns_interaction(moderated):
    path, cm, measurement = moderated
    out = _run("moderation", path, {"conceptual_model": cm, "measurement": measurement,
                                    "bootstrap_samples": 0})
    assert out.get("interactions"), f"expected an interaction term, got {out}"


def test_new_ops_are_whitelisted():
    from agent.tools.stats import OPS
    for name in ("pls_sem", "efa", "regression_full", "mediation", "moderation", "rigor"):
        assert name in OPS
    out = _run("eval_python", "x.csv")  # still rejected
    assert "not whitelisted" in out["error"]
    assert "pls_sem" in out["available"]


def test_missing_thesis_stats_degrades_cleanly(pls, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "thesis_stats":
            raise ModuleNotFoundError("No module named 'thesis_stats'", name="thesis_stats")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    path, cm = pls
    out = _run("pls_sem", path, {"conceptual_model": cm})
    assert "stats dependency missing" in out["error"]


# --- Phase 5: self-validation wiring ---------------------------------------

from agent.tools.stats import OPS, check_thresholds  # noqa: E402


def test_run_stats_attaches_validation_on_impossible(monkeypatch, pls):
    path, cm = pls
    monkeypatch.setitem(OPS, "pls_sem", lambda file, **k: {"reliability": {"X": {"r_squared": 1.4}}, "paths": {}})
    out = _run("pls_sem", path, {"conceptual_model": cm})
    assert out["validation"]["hard"] >= 1
    assert any(f["check"] == "bounds.r2" for f in out["validation"]["findings"])


def test_run_stats_clean_has_no_hard_validation(pls):
    path, cm = pls
    out = _run("pls_sem", path, {"conceptual_model": cm, "bootstrap_samples": 0})
    v = out.get("validation")
    assert v is None or v["hard"] == 0


def test_run_stats_validation_fail_open(monkeypatch, pls):
    path, cm = pls
    import agent.stats_validation as sv
    monkeypatch.setattr(sv, "validate_run_stats", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = _run("pls_sem", path, {"conceptual_model": cm, "bootstrap_samples": 0})
    assert "paths" in out and "validation" not in out  # numbers still returned, no crash


def test_check_thresholds_catches_impossible_loading():
    out = json.loads(check_thresholds.func("loadings", [{"item": "X1", "value": 1.31}, {"item": "X2", "value": 0.8}]))
    assert any(f.get("check") == "bounds.loading" and f["severity"] == "hard" for f in out["findings"])


def test_check_thresholds_htmt_above_one():
    out = json.loads(check_thresholds.func("htmt", [{"pair": "X-Y", "value": 1.05}]))
    checks = [f.get("check") for f in out["findings"]]
    assert "bounds.htmt_high" in checks  # soft verification finding
    assert any(f["severity"] == "hard" for f in out["findings"])  # existing threshold breach


def test_check_thresholds_valid_values_unchanged():
    out = json.loads(check_thresholds.func("loadings", [{"item": "X1", "value": 0.8}, {"item": "X2", "value": 0.75}]))
    assert not any(f.get("check", "").startswith("bounds") for f in out["findings"])


# --- power op (roadmap #2) --------------------------------------------------

def test_power_op_apriori_textbook(tmp_path):
    out = _run("power", "", {"analysis": "regression", "mode": "apriori",
                             "effect_size": "medium", "predictors": 3})
    assert out["op"] == "power" and out["required_n"] == 77
    assert out["justification"]


def test_power_op_posthoc_defaults_n_from_file(pls):
    path, cm = pls  # 120-row CSV
    out = _run("power", path, {"analysis": "regression", "mode": "posthoc",
                               "effect_size": "medium", "predictors": 3})
    assert 0 < out["achieved_power"] <= 1  # n defaulted to the file's row count


def test_power_op_missing_n_no_file_is_clean_error():
    out = _run("power", "", {"analysis": "regression", "mode": "posthoc",
                             "effect_size": "medium", "predictors": 3})
    assert "error" in out


def test_power_op_unknown_analysis_clean_error():
    out = _run("power", "", {"analysis": "anova", "mode": "apriori", "effect_size": "medium"})
    assert "error" in out


def test_power_op_validation_ride_along(monkeypatch):
    monkeypatch.setitem(OPS, "power", lambda file="", **k: {"analysis": "regression",
                        "mode": "posthoc", "achieved_power": 1.4, "inputs": {}})
    out = _run("power", "", {"analysis": "regression"})
    assert out["validation"]["hard"] == 1
    assert any(f["check"] == "bounds.power" for f in out["validation"]["findings"])


# --- screening op (roadmap #3) ----------------------------------------------

@pytest.fixture
def survey_csv(tmp_path):
    rng = np.random.default_rng(5)
    n = 120
    cols = {}
    for con in ("JS", "OC", "TI"):
        latent = rng.normal(0, 1, n)
        for i in (1, 2, 3, 4):
            cols[f"{con}{i}"] = np.clip(np.round(0.7 * latent + rng.normal(0, 0.7, n) + 3), 1, 5).astype(float)
    cols["JS1"][0] = np.nan  # one hole
    p = tmp_path / "survey.csv"
    pd.DataFrame(cols).to_csv(p, index=False)
    meas = {"JS": ["JS1", "JS2", "JS3", "JS4"], "OC": ["OC1", "OC2", "OC3", "OC4"],
            "TI": ["TI1", "TI2", "TI3", "TI4"]}
    return str(p), meas


def test_screening_report_only_writes_no_file(survey_csv, tmp_path):
    path, meas = survey_csv
    out = _run("screening", path, {"measurement": meas, "likert_min": 1, "likert_max": 5})
    assert out["op"] == "screening" and "narrative" in out and "missing" in out
    assert "applied" not in out
    assert not (tmp_path / "survey_screened.csv").exists()  # no silent mutation


def test_screening_apply_writes_derived_file(survey_csv, tmp_path):
    path, meas = survey_csv
    out = _run("screening", path, {"measurement": meas, "likert_min": 1, "likert_max": 5,
                                   "apply": {"missing": "listwise"}})
    assert (tmp_path / "survey_screened.csv").exists()
    assert out["applied"]["n_after"] == out["applied"]["n_before"] - 1  # the NaN row dropped
    assert "narrative_applied" in out


def test_screening_bad_apply_missing_is_clean_error(survey_csv):
    path, meas = survey_csv
    out = _run("screening", path, {"measurement": meas, "likert_min": 1, "likert_max": 5,
                                   "apply": {"missing": "regression"}})
    assert "error" in out


def test_screening_validation_ride_along(monkeypatch, survey_csv):
    path, _ = survey_csv
    monkeypatch.setitem(OPS, "screening", lambda file, **k: {
        "missing": {"per_variable": {"JS1": {"missing_pct": 180}}}})
    out = _run("screening", path, {})
    assert out["validation"]["hard"] >= 1
    assert any(f["check"] == "bounds.missing_pct" for f in out["validation"]["findings"])


# --- method_advice op (roadmap #7) ------------------------------------------

_ADV_CM = {"nodes": [{"id": n, "label": n, "questions": [f"{n}1", f"{n}2", f"{n}3"]}
                     for n in ("A", "B", "C")],
           "edges": [{"source": "A", "target": "C"}, {"source": "B", "target": "C"}]}


def test_method_advice_design_mode():
    out = _run("method_advice", "", {"conceptual_model": _ADV_CM, "target_n": 250, "chosen": "PLS-SEM"})
    assert out["op"] == "method_advice" and out["mode"] == "design"
    assert [r["method"] for r in out["recommendation"]]
    assert "inputs_fingerprint" in out


def test_method_advice_data_mode_conflict(survey_csv):
    path, meas = survey_csv  # 120 rows
    cm = {"nodes": [{"id": c, "label": c, "questions": meas[c]} for c in ("JS", "OC", "TI")],
          "edges": [{"source": "JS", "target": "TI"}, {"source": "OC", "target": "TI"}]}
    out = _run("method_advice", path, {"conceptual_model": cm, "chosen": "CB-SEM (AMOS)"})
    assert out["mode"] == "data"
    # n=120 < 150 → cb_sem penalized; conflict may surface
    assert out["recommendation"][0]["method"] in ("pls_sem", "regression", "cb_sem", "nonparametric")


def test_method_advice_never_blocks_no_hard():
    out = _run("method_advice", "", {"conceptual_model": _ADV_CM, "target_n": 90, "chosen": "CB-SEM"})
    assert '"hard"' not in json.dumps(out)


# --- PLS completeness ops (roadmap #8) --------------------------------------

def test_pls_sem_includes_q2(pls):
    path, cm = pls
    out = _run("pls_sem", path, {"conceptual_model": cm, "bootstrap_samples": 0})
    assert out["q2"] and out["q2"]["values"]  # per-endogenous Q²
    assert set(out["q2"]["values"]) <= {"B", "C"}


def test_pls_sem_q2_off(pls):
    path, cm = pls
    out = _run("pls_sem", path, {"conceptual_model": cm, "bootstrap_samples": 0, "q2": False})
    assert "q2" not in out


def test_pls_sem_q2_divisor_clean_error(pls):
    path, cm = pls  # n=120, k=3 → 360 % 6 == 0
    out = _run("pls_sem", path, {"conceptual_model": cm, "bootstrap_samples": 0, "omission_distance": 6})
    assert "error" in out


@pytest.fixture
def grouped_csv(tmp_path):
    rng = np.random.default_rng(9)
    def block(m, beta):
        x = rng.normal(0, 1, m); y = beta * x + rng.normal(0, 0.8, m); z = 0.4 * x + 0.35 * y + rng.normal(0, 0.75, m)
        cols = {}
        for lat, p in ((x, "A"), (y, "B"), (z, "C")):
            for i in (1, 2, 3):
                cols[f"{p}{i}"] = np.clip(np.round(0.8 * lat + rng.normal(0, 0.6, m) + 3), 1, 5).astype(int)
        return pd.DataFrame(cols)
    a, b = block(120, 0.6), block(120, 0.05)
    a["grp"] = "a"; b["grp"] = "b"
    p = tmp_path / "grp.csv"
    pd.concat([a, b], ignore_index=True).to_csv(p, index=False)
    cm = {"nodes": [{"id": c, "label": c, "questions": [f"{c}1", f"{c}2", f"{c}3"]} for c in ("A", "B", "C")],
          "edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}, {"source": "A", "target": "C"}]}
    return str(p), cm


def test_mga_op(grouped_csv):
    path, cm = grouped_csv
    out = _run("mga", path, {"conceptual_model": cm, "group": "grp", "n_permutations": 150, "seed": 42})
    assert out["op"] == "mga" and "micom" in out and "paths" in out
    assert "comparison_defensible" in out


def test_mga_op_missing_group_clean_error(grouped_csv):
    path, cm = grouped_csv
    out = _run("mga", path, {"conceptual_model": cm})
    assert "error" in out


def test_ipma_op(grouped_csv):
    path, cm = grouped_csv
    out = _run("ipma", path, {"conceptual_model": cm, "target": "C", "scale_min": 1, "scale_max": 5})
    assert out["target"] == "C" and out["rows"]
    assert all(0 <= r["performance"] <= 100 for r in out["rows"])


def test_ipma_op_missing_target_clean_error(grouped_csv):
    path, cm = grouped_csv
    out = _run("ipma", path, {"conceptual_model": cm})
    assert "error" in out


def test_new_pls_ops_whitelisted():
    for name in ("mga", "ipma"):
        assert name in OPS
