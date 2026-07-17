"""M3 sampling_plan becomes power-primary (roadmap #2, Phase 4)."""
import json
import uuid

import pytest

pytest.importorskip("thesis_stats")

from agent.state import ProjectStateStore
from agent.tools.instrument import _max_in_degree, make_sampling_plan_tool


def _store_with(tmp_path, methodology, conceptual_model, instrument=None):
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    store.commit_slice("M3", {"methodology": methodology,
                              "conceptual_model": conceptual_model,
                              "instrument": instrument or {}},
                       reason="seed")
    return store


# 5 edges, but max 3 arrows into any one construct (Y).
_MODEL = {"nodes": [{"id": n, "label": n, "questions": [f"{n}1", f"{n}2", f"{n}3"]}
                    for n in ("A", "B", "C", "D", "Y")],
          "edges": [{"source": "A", "target": "Y"}, {"source": "B", "target": "Y"},
                    {"source": "C", "target": "Y"}, {"source": "D", "target": "A"},
                    {"source": "C", "target": "B"}]}


def test_max_in_degree():
    assert _max_in_degree(_MODEL) == 3


def test_pls_plan_is_power_primary(tmp_path):
    store = _store_with(tmp_path, "PLS-SEM", _MODEL)
    plan = json.loads(make_sampling_plan_tool(store).func())
    assert "power_analysis" in plan
    assert plan["power_analysis"]["inputs"]["predictors"] == 3  # max in-degree, not 5 edges
    assert plan["power_analysis"]["justification"] in plan["rationale"]
    # target_n is the max of heuristic and power-based n
    pa = plan["power_analysis"]
    assert plan["target_n"] >= (pa.get("recommended_n") or pa["required_n"])
    # backward-compat keys intact
    assert {"target_n", "method_rule", "screening", "timeline_weeks", "rationale"} <= set(plan)


def test_cbsem_defers_power(tmp_path):
    store = _store_with(tmp_path, "CB-SEM (AMOS)", _MODEL)
    plan = json.loads(make_sampling_plan_tool(store).func())
    assert "power_analysis" not in plan


def test_fail_open_when_power_raises(tmp_path, monkeypatch):
    import thesis_stats
    monkeypatch.setattr(thesis_stats, "run_power",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    store = _store_with(tmp_path, "PLS-SEM", _MODEL)
    plan = json.loads(make_sampling_plan_tool(store).func())
    assert "power_analysis" not in plan and plan["target_n"] > 0  # heuristic survived
