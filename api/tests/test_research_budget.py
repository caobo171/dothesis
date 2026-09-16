"""The M2 scout delegates bounded discovery and reports partial coverage honestly.

All provider calls are injected; these tests must never use the network or a model.
"""
import json

import agent.tools.research as research


def test_scout_passes_shared_budget_and_target(monkeypatch):
    seen = {}

    def discover(topic, **kwargs):
        seen.update(topic=topic, **kwargs)
        return {
            "sources": [{"title": "A", "doi": "10.1/a", "abstract": "Abstract", "provider": "openalex", "verified": True}],
            "queries": ["digital banking adoption"], "warnings": [],
        }

    monkeypatch.setenv("DOTHESIS_SCOUT_TIMEOUT_S", "7")
    monkeypatch.setattr(research, "discover_literature", discover)
    out = json.loads(research.research_scout.func(
        "digital banking adoption", ["What predicts adoption?"], ["Davis 1989"], min_sources=20))

    assert seen == {
        "topic": "digital banking adoption",
        "research_questions": ["What predicts adoption?"],
        "min_sources": 20,
        "concepts": ["Davis 1989"],
        "budget_s": 7.0,
        "domain": "general",
    }
    assert out["target"] == 20 and out["count"] == 1 and out["shortfall"] == 19
    assert out["sources"][0]["abstract"] == "Abstract"
    assert out["sources"][0]["provider"] == "openalex"
    assert out["sources"][0]["verified"] is True  # exact helper resolution is preserved


def test_scout_returns_partial_discovery_without_a_second_fallback(monkeypatch):
    monkeypatch.setattr(research, "discover_literature", lambda *args, **kwargs: {
        "sources": [{"title": "Partial", "doi": "10.1/p", "verified": False}],
        "queries": ["query one", "query two"],
        "warnings": ["crossref không phản hồi cho một truy vấn."],
    })

    out = json.loads(research.research_scout.func("livestream commerce", min_sources=4))

    assert out["count"] == 1 and out["verified_count"] == 0 and out["target"] == 4 and out["shortfall"] == 4
    assert out["coverage"] == {
        "queries": ["query one", "query two"],
        "query_coverage": {},
        "query_hits": {},
        "complete": False,
        "warnings": ["crossref không phản hồi cho một truy vấn."],
        "requests_completed": 0,
        "providers": [],
    }
    assert "note" not in out  # no old Crossref fallback claim


def test_scout_failure_returns_honest_empty_coverage(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(research, "discover_literature", boom)
    out = json.loads(research.research_scout.func("livestream commerce", min_sources=3))

    assert out["sources"] == []
    assert out["count"] == 0 and out["target"] == 3 and out["shortfall"] == 3
    assert out["coverage"]["complete"] is False
    assert "Không được viết như đã có literature" in out["hint"]
