"""Behavioral probe scoring (F9 Task 2). Deterministic — no network. Pins each
probe kind's pass/fail contract, including the F0-corrected clean marker branch
and the cheap Vietnamese-language heuristic."""
import json
from pathlib import Path

from quality.probes import score_probe, load_probes


def test_marker_probe_pass_and_fail():
    assert score_probe("Pick one:\n[OPTIONS] a | b | c", {"kind": "marker", "value": "OPTIONS"})
    assert not score_probe("Pick one: a, b, c", {"kind": "marker", "value": "OPTIONS"})


def test_regex_probe_matches_cite_marker():
    assert score_probe("TAM predicts usage {{cite: Davis 1989}}.", {"kind": "regex", "value": r"\{\{\s*cite:"})
    assert not score_probe("TAM predicts usage.", {"kind": "regex", "value": r"\{\{\s*cite:"})


def test_json_probe():
    assert score_probe('{"x": 1}', {"kind": "json", "value": None})
    assert not score_probe("not json", {"kind": "json", "value": None})


def test_language_probe_vietnamese():
    vi = "Đây là một câu trả lời bằng tiếng Việt về phương pháp nghiên cứu."
    assert score_probe(vi, {"kind": "language", "value": "vi"})
    assert not score_probe("This is English.", {"kind": "language", "value": "vi"})


def test_load_probes_reads_seed_fixtures():
    root = Path(__file__).resolve().parents[2]
    probes = load_probes(str(root / "quality/fixtures/model_probes"))
    ids = {p["id"] for p in probes}
    assert {"options", "cite", "json_only", "vi_answer", "terse"} <= ids
    for p in probes:  # every probe is a runnable spec
        assert "prompt" in p and "expect" in p and "kind" in p["expect"]
