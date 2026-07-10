import json

from quality.eval_harness import run_harness


def test_harness_flags_regression(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text(json.dumps({"m1_topic": {}}))
    baselines = {"a.json": 0.90}
    import quality.eval_harness as h
    monkeypatch.setattr(h, "score_thesis", lambda cs, **k: {"overall": 0.50, "dimensions": []})
    code, rows = run_harness(str(tmp_path), baselines, tolerance=0.03)
    assert code == 1 and rows[0]["regressed"] is True


def test_harness_passes_when_at_baseline(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text(json.dumps({"m1_topic": {}}))
    import quality.eval_harness as h
    monkeypatch.setattr(h, "score_thesis", lambda cs, **k: {"overall": 0.91, "dimensions": []})
    code, _ = run_harness(str(tmp_path), {"a.json": 0.90}, tolerance=0.03)
    assert code == 0
