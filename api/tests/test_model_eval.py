"""Multi-model probe runner (F9 Task 3) + report/recommend/gate (Task 5).

No network: the single chokepoint `_complete` is stubbed in every test, so these
run offline and deterministically. Compose-quality (Task 4) is deferred until F3's
rubric lands, so it isn't tested here."""
import quality.model_eval as me


def test_evaluate_ranks_and_costs(monkeypatch):
    probes = [{"id": "opt", "prompt": "pick", "expect": {"kind": "marker", "value": "OPTIONS"}},
              {"id": "vi", "prompt": "trả lời", "expect": {"kind": "language", "value": "vi"}}]

    def fake_complete(model, prompt, system=None):
        if model == "good":
            return ("[OPTIONS] a | b\nĐây là nghiên cứu của tôi và các bạn", {"in": 100, "out": 50})
        return ("no markers, english only", {"in": 100, "out": 50})
    monkeypatch.setattr(me, "_complete", fake_complete)
    monkeypatch.setattr(me, "cost", lambda m, i, o: 0.001 if m == "good" else 0.002)

    rows = me.evaluate_models(["good", "bad"], probes)
    by = {r["model"]: r for r in rows}
    assert by["good"]["marker_reliability"] == 1.0
    assert by["bad"]["marker_reliability"] == 0.0
    assert by["good"]["vietnamese"] >= 0.5


def test_model_failure_is_isolated(monkeypatch):
    def boom(model, prompt, system=None):
        raise RuntimeError("provider down")
    monkeypatch.setattr(me, "_complete", boom)
    rows = me.evaluate_models(["x"], [{"id": "a", "prompt": "p",
                                       "expect": {"kind": "marker", "value": "OPTIONS"}}])
    assert rows[0]["errors"] >= 1 and rows[0]["marker_reliability"] == 0.0


# -- Task 5: report / recommend / gate -------------------------------------
def test_recommend_picks_best_value_above_floor():
    rows = [
        {"model": "cheapbad", "marker_reliability": 0.4, "quality": 0.8, "cost_per_task": 0.001},
        {"model": "good", "marker_reliability": 0.95, "quality": 0.82, "cost_per_task": 0.003},
        {"model": "expensive", "marker_reliability": 0.96, "quality": 0.83, "cost_per_task": 0.02},
    ]
    assert me.recommend(rows, marker_floor=0.9) == "good"


def test_gate_fails_on_reliability_regression():
    cand = {"model": "c", "marker_reliability": 0.7, "quality": 0.8}
    inc = {"model": "i", "marker_reliability": 0.95, "quality": 0.8}
    assert me.run_model_gate(cand, inc, {"marker_reliability": 0.9}) == 1


def test_gate_passes_when_floors_met():
    cand = {"model": "c", "marker_reliability": 0.95, "quality": 0.82}
    inc = {"model": "i", "marker_reliability": 0.9, "quality": 0.8}
    assert me.run_model_gate(cand, inc, {"marker_reliability": 0.9}) == 0


def test_render_report_is_markdown_table():
    rows = [{"model": "good", "quality": 0.82, "marker_reliability": 0.95,
             "instruction_reliability": 0.9, "vietnamese": 0.8, "cost_per_task": 0.003, "errors": 0}]
    out = me.render_report(rows)
    assert "| model |" in out and "good" in out
