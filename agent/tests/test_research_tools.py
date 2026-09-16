"""M2 broad discovery delegates to the shared bounded discovery seam.

No provider or LLM calls run here. Provider fan-out, deadlines, and query planning
belong to ``orchestrator.tools.literature_discovery``; this boundary only shapes
agent-visible metadata and retains domain supplements.
"""
from __future__ import annotations

import json

from agent.tools import research


def test_scout_uses_shared_discovery_default_target_and_preserves_evidence(monkeypatch):
    seen = {}

    def discover(topic, **kwargs):
        seen["topic"] = topic
        seen.update(kwargs)
        return {
            "sources": [{
                "title": "A candidate paper", "authors": ["Nguyen"], "year": 2024,
                "doi": "10.1/example", "url": "https://doi.org/10.1/example",
                "abstract": "Provider-supplied abstract evidence.", "provider": "semantic_scholar",
                # The helper deliberately never verifies metadata candidates.
                "verified": False,
            }],
            "count": 2, "verified_count": 2, "relevant_verified_count": 1,
            "new_count": 1, "unverified_count": 4,
            "existing_needs_review": [{"title": "Off-topic inherited source", "reason": "not relevant"}],
            "target": 24, "shortfall": 23,
            "queries": ["digital banking adoption"], "warnings": ["openalex timeout"], "complete": False,
        }

    monkeypatch.setattr(research, "discover_literature", discover)
    out = json.loads(research.research_scout.func(
        topic="digital banking adoption", research_questions=["What predicts adoption?"],
        seed_refs=["Davis 1989"],
    ))

    assert seen["topic"] == "digital banking adoption"
    assert seen["research_questions"] == ["What predicts adoption?"]
    assert seen["min_sources"] == 24
    assert seen["concepts"] == ["Davis 1989"]
    assert out["count"] == 2 and out["target"] == 24 and out["shortfall"] == 23
    assert out["verified_count"] == 2 and out["relevant_verified_count"] == 1
    assert out["new_count"] == 1 and out["unverified_count"] == 4
    assert out["existing_needs_review"] == [{"title": "Off-topic inherited source", "reason": "not relevant"}]
    assert out["coverage"] == {
        "queries": ["digital banking adoption"], "query_coverage": {}, "query_hits": {},
        "complete": False, "warnings": ["openalex timeout"], "requests_completed": 0, "providers": [],
    }
    assert out["sources"][0]["abstract"] == "Provider-supplied abstract evidence."
    assert out["sources"][0]["provider"] == "semantic_scholar"
    assert out["sources"][0]["verified"] is False


def test_scout_honestly_returns_partial_empty_discovery(monkeypatch):
    monkeypatch.setattr(research, "discover_literature", lambda *_args, **_kwargs: {
        "sources": [], "count": 0, "target": 7, "shortfall": 7,
        "queries": ["narrow topic"], "warnings": ["crossref unavailable"], "complete": False,
    })

    out = json.loads(research.research_scout.func(topic="narrow topic", min_sources=7))

    assert out["sources"] == []
    assert out["count"] == 0 and out["target"] == 7 and out["shortfall"] == 7
    assert out["coverage"]["complete"] is False
    assert "Không được viết" in out["hint"]


def test_scout_passes_specialized_domain_to_shared_collector(monkeypatch):
    seen = {}

    def discover(*_args, **kwargs):
        seen.update(kwargs)
        return {
            "sources": [
                {"title": "Universal", "doi": "10.base/1", "provider": "openalex", "verified": True},
                {"title": "Medical index", "doi": "10.med/1", "provider": "medical", "abstract": "Indexed abstract", "verified": True},
            ],
            "count": 2, "verified_count": 2, "new_count": 2,
            "target": 3, "shortfall": 1, "queries": ["diabetes telemedicine"],
            "coverage": {"construct": True}, "query_hits": {"diabetes telemedicine": 2},
            "complete": False, "warnings": [], "requests_completed": 4, "providers": ["medical", "openalex"],
        }

    monkeypatch.setattr(research, "discover_literature", discover)
    out = json.loads(research._research_scout_impl(
        "telemedicine glycemic control in diabetes patients", min_sources=3,
    ))

    assert seen["domain"] == "medical"
    assert {source["doi"] for source in out["sources"]} == {"10.base/1", "10.med/1"}
    assert out["sources"][1]["abstract"] == "Indexed abstract"
    assert out["verified_count"] == 2 and out["target"] == 3 and out["shortfall"] == 1
