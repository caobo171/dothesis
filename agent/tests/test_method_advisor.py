"""Assumption-driven method advisor (roadmap #7) — pure, advisory-only."""
import json

import pytest

from agent.method_advisor import advise, model_profile, normalize_method

LATENT_CM = {"nodes": [{"id": "n1", "label": "A", "questions": ["A1", "A2", "A3"]},
                       {"id": "n2", "label": "B", "questions": ["B1", "B2", "B3"]},
                       {"id": "n3", "label": "C", "questions": ["C1", "C2", "C3"]}],
             "edges": [{"source": "n1", "target": "n3"}, {"source": "n2", "target": "n3"}]}


def test_normalize_method():
    assert normalize_method("CB-SEM (AMOS)") == "cb_sem"
    assert normalize_method("PLS-SEM") == "pls_sem"
    assert normalize_method("SPSS regression") == "regression"
    assert normalize_method("something") is None


def test_model_profile():
    p = model_profile(LATENT_CM)
    assert p["has_latent"] and p["n_constructs"] == 3 and p["max_in_degree"] == 2


def test_mediation_detected():
    cm = {"nodes": [{"id": x, "label": x, "questions": [f"{x}1", f"{x}2"]} for x in ("A", "B", "C")],
          "edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}]}
    assert model_profile(cm)["has_mediation"] is True


def test_severe_nonnormal_small_n_favors_pls_over_cbsem():
    dist = {"n_items": 16, "severe_n": 7, "severe_pct": 43.8}
    out = advise(profile=model_profile(LATENT_CM), n=95, distribution=dist, mode="data",
                 source_note="rows of data.csv")
    ranked = [r["method"] for r in out["recommendation"]]
    assert ranked.index("pls_sem") < ranked.index("cb_sem")
    cb = next(r for r in out["recommendation"] if r["method"] == "cb_sem")
    assert cb["tally"]["strongly_against"] >= 2  # sample floor + normality


def test_conflict_surfaced_when_choice_disagrees():
    dist = {"n_items": 16, "severe_n": 7, "severe_pct": 43.8}
    out = advise(profile=model_profile(LATENT_CM), n=95, distribution=dist, mode="data",
                 chosen="cb_sem")
    assert out["conflict_with_choice"] is not None
    assert out["conflict_with_choice"]["advised"] == "pls_sem"
    assert "cb_sem_sample_floor" in out["conflict_with_choice"]["reasons"]


def test_no_conflict_when_choice_is_top():
    dist = {"n_items": 16, "severe_n": 0, "severe_pct": 0.0}
    out = advise(profile=model_profile(LATENT_CM), n=400, distribution=dist, mode="data",
                 chosen="pls_sem")
    assert out["conflict_with_choice"] is None


def test_design_mode_marks_data_inputs_unknown():
    out = advise(profile=model_profile(LATENT_CM), n=200, mode="design")
    assert "normality (re-run after data upload)" in out["unknown"]


def test_power_shortfall_caveat():
    out = advise(profile=model_profile(LATENT_CM), n=95, mode="data",
                 power_analysis={"required_n": 160, "citations": ["Kock & Hadaya (2018)"]})
    assert any("below the a-priori power-based N = 160" in c for c in out["caveats"])


def test_no_latent_favors_regression():
    cm = {"nodes": [{"id": "x", "label": "X", "questions": ["X1"]},
                    {"id": "y", "label": "Y", "questions": ["Y1"]}],
          "edges": [{"source": "x", "target": "y"}]}
    out = advise(profile=model_profile(cm), n=200, mode="data",
                 distribution={"n_items": 2, "severe_pct": 0.0})
    ranked = [r["method"] for r in out["recommendation"]]
    assert ranked.index("regression") < ranked.index("pls_sem")


def test_never_hard_and_deterministic():
    dist = {"n_items": 16, "severe_n": 7, "severe_pct": 43.8}
    a = advise(profile=model_profile(LATENT_CM), n=95, distribution=dist, mode="data", chosen="cb_sem")
    b = advise(profile=model_profile(LATENT_CM), n=95, distribution=dist, mode="data", chosen="cb_sem")
    assert json.dumps(a) == json.dumps(b)
    blob = json.dumps(a)
    assert '"hard"' not in blob  # advisory only — never a hard verdict
    for r in a["recommendation"]:
        json.dumps(r)
