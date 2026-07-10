"""Sampling-plan tests (F7 Task 2).

`target_sample_n` is the pure power helper shared with F8's preflight — unit-
tested directly. `make_sampling_plan_tool` is the store-bound agent tool: per the
F0 correction it must READ the project store (not take a model-supplied
context_store) AND PERSIST the computed plan to the owned M3 `sample_plan` key so
the preflight/field-it surfaces can read it back. We drive it against a real
file-backed ProjectStateStore in a tmp dir — no DB, no LLM, no network.
"""
import json

from agent.sampling import target_sample_n
from agent.state import ProjectStateStore
from agent.tools.instrument import make_sampling_plan_tool


def test_pls_10x_rule():
    n, rule = target_sample_n("pls-sem", n_paths=5, n_indicators=6)
    assert n >= 60 and "10" in rule  # 10x the largest of paths-into-a-construct / arrows


def test_cb_sem_minimum_applied():
    n, _ = target_sample_n("cb-sem", n_paths=4, n_indicators=20)
    assert n >= 200


def _seeded_store(tmp_path, method, n_paths, n_items):
    store = ProjectStateStore(tmp_path)
    store.commit_slice("M3", {
        "methodology": method,
        "conceptual_model": {"paths": list(range(n_paths))},
        "instrument": {"items": [{} for _ in range(n_items)]},
    }, reason="seed design for sampling plan test")
    return store


def test_sampling_plan_shape(tmp_path):
    store = _seeded_store(tmp_path, "PLS-SEM", n_paths=3, n_items=3)
    plan = json.loads(make_sampling_plan_tool(store).func())
    assert plan["target_n"] and plan["timeline_weeks"] and plan["method_rule"]


def test_sampling_plan_persists_to_store(tmp_path):
    # F0 correction: the computed plan must land in the store's owned sample_plan
    # key, not just be returned to the model.
    store = _seeded_store(tmp_path, "PLS-SEM", n_paths=5, n_items=6)
    make_sampling_plan_tool(store).func()
    saved = store.load()["contextStore"]["sample_plan"]
    assert saved["target_n"] >= 60
    # And preflight (F8) can now read a planned sample size from it.
    assert saved["target_n"] == json.loads(make_sampling_plan_tool(store).func())["target_n"]
