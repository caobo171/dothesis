"""The explicit rewrite tool must be atomic from the student's perspective."""
from __future__ import annotations

import copy
import json

import pytest

import agent.tools.writing as W
from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER


def _prose(name: str) -> str:
    return (f"{name} substantive thesis prose with evidence and analysis. " * 8)


class _Store:
    project_id = "rewrite-project"

    def __init__(self):
        self.commits = []
        self.context = {
            "m1_topic": {"research_title": "T", "language": "en"},
            "m2_literature": {"literature_sources": []},
            "m3_design": {"constructs": []},
            "m4_analysis": {"analysis_results": {}},
            "m5_writing": {"chapters": {
                name: {"prose": _prose(f"old {name}")} for name in M5_CHAPTER_ORDER
            }},
        }

    def load_full_context_store(self):
        return copy.deepcopy(self.context)

    def load(self):
        return {"contextStore": {"final_sections": self.context["m5_writing"].get("final_sections")}}

    def commit_slice(self, module, writes, *_args, **_kwargs):
        self.commits.append((module, copy.deepcopy(writes)))
        self.context["m5_writing"]["chapters"] = copy.deepcopy(writes["chapters"])
        return {"version": len(self.commits)}


@pytest.fixture
def writer(monkeypatch):
    import agent.coherence as coherence
    import orchestrator.tools.m5_writing as m5

    monkeypatch.setattr(coherence, "validate_m5_sections", lambda *_: {"findings": []})
    monkeypatch.setattr(m5, "run_export", lambda sections, *_args, **_kwargs: [
        {"kind": "docx", "chapters": [s.get("chapter_name") for s in sections]}
    ])

    def compose(_context, chapters=None, force_recompose=False):
        assert force_recompose is True
        return [{"chapter_name": name, "title": name,
                 "prose": _prose(f"new {name}")} for name in chapters]

    monkeypatch.setattr(m5, "compose_all_sections", compose)
    return m5


def _rewrite(store, **kwargs):
    tool = next(t for t in W.make_writing_tools(store) if t.name == "rewrite_thesis")
    return json.loads(tool.invoke(kwargs))


def test_full_rewrite_commits_once_then_exports_the_committed_chapters(writer):
    store = _Store()
    out = _rewrite(store)

    assert out["ok"] is True and out["persisted"] is True and out["exported"] is True
    assert out["rewritten_chapters"] == list(M5_CHAPTER_ORDER)
    assert len(store.commits) == 1
    assert all("new " + name in store.context["m5_writing"]["chapters"][name]["prose"]
               for name in M5_CHAPTER_ORDER)
    assert out["artifacts"][0]["chapters"] == list(M5_CHAPTER_ORDER)
    assert out["committed_chapter_hashes"]


def test_subset_rewrite_keeps_unrequested_chapters(writer):
    store = _Store()
    old_results = store.context["m5_writing"]["chapters"]["results"]["prose"]
    out = _rewrite(store, scope="chapter:intro|conclusion", export_after=False)

    assert out["ok"] is True
    assert out["rewritten_chapters"] == ["intro", "conclusion"]
    assert store.context["m5_writing"]["chapters"]["results"]["prose"] == old_results


def test_generation_or_validation_failure_leaves_the_draft_unchanged(monkeypatch, writer):
    store = _Store()
    original = copy.deepcopy(store.context)
    monkeypatch.setattr(writer, "compose_all_sections", lambda *_args, **_kwargs:
                        (_ for _ in ()).throw(RuntimeError("LLM unavailable")))
    out = _rewrite(store, export_after=False)
    assert out["error"] == "rewrite_generation_failed"
    assert store.context == original and not store.commits

    import agent.coherence as coherence
    monkeypatch.setattr(writer, "compose_all_sections", lambda _c, chapters=None, **_kw: [
        {"chapter_name": name, "prose": _prose(name)} for name in chapters])
    monkeypatch.setattr(coherence, "validate_m5_sections", lambda *_: {"findings": [
        {"severity": "hard", "check": "coherence.numeric_mismatch"}
    ]})
    out = _rewrite(store, export_after=False)
    assert out["error"] == "composition_grounding_failed"
    assert store.context == original and not store.commits


def test_hash_conflict_and_commit_error_never_claim_persistence(monkeypatch, writer):
    store = _Store()
    original = copy.deepcopy(store.context)

    def concurrent_compose(_context, chapters=None, **_kwargs):
        store.context["m5_writing"]["chapters"]["results"]["prose"] = _prose("concurrent edit")
        return [{"chapter_name": name, "prose": _prose(name)} for name in chapters]

    monkeypatch.setattr(writer, "compose_all_sections", concurrent_compose)
    out = _rewrite(store, export_after=False)
    assert out["error"] == "rewrite_conflict" and out["persisted"] is False
    assert not store.commits

    store = _Store()
    store.commit_slice = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("store down"))
    monkeypatch.setattr(writer, "compose_all_sections", lambda _c, chapters=None, **_kw: [
        {"chapter_name": name, "prose": _prose(name)} for name in chapters])
    out = _rewrite(store, export_after=False)
    assert out["error"] == "persistence_failed" and out["persisted"] is False
