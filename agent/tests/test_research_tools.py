"""M2 research tool tests — the Crossref fallback path.

No network, no real LLM: httpx and the LLM factory are both stubbed. The
fallback is the degraded path that runs when the deep scout is unavailable, so
its query string and its zero-source signal are the two things worth pinning.
"""
from __future__ import annotations

import json

import pytest

from agent.tools import research


class _FakeResp:
    def __init__(self, items):
        self._items = items

    def json(self):
        return {"message": {"items": self._items}}


class _FakeLLMResp:
    def __init__(self, content):
        self.content = content


@pytest.fixture
def crossref_calls(monkeypatch):
    """Stub research.httpx.get; record the params every call was made with."""
    calls: list[dict] = []
    items: list[dict] = []

    class _FakeHttpx:
        @staticmethod
        def get(url, params=None, **kw):
            calls.append({"url": url, "params": params or {}})
            return _FakeResp(items)

    monkeypatch.setattr(research, "httpx", _FakeHttpx)
    return {"calls": calls, "items": items}


@pytest.fixture
def dead_scout(monkeypatch):
    """Force the deep scout to fail so every test lands in the fallback."""
    from orchestrator.tools import m2_literature

    class _Boom:
        @staticmethod
        def func(*a, **kw):
            raise RuntimeError("scout unavailable")

    monkeypatch.setattr(m2_literature, "scout_citations", _Boom)


@pytest.fixture
def fake_llm(monkeypatch):
    """Stub the translation LLM. Real calls cost money — never hit the gateway."""
    seen: list[str] = []

    def _factory():
        class _LLM:
            @staticmethod
            def invoke(prompt):
                seen.append(prompt)
                return _FakeLLMResp("technology acceptance model online banking Vietnam")
        return _LLM()

    from orchestrator.tools import m5_writing
    monkeypatch.setattr(m5_writing, "_get_llm", _factory)
    return seen


def _one_item():
    return {
        "title": ["A Real Paper"],
        "author": [{"family": "Nguyen"}],
        "issued": {"date-parts": [[2020]]},
        "container-title": ["Journal of Things"],
        "DOI": "10.1/abc",
        "URL": "https://doi.org/10.1/abc",
    }


# --- fix 1: what query actually reaches Crossref ------------------------------

def test_crossref_gets_translated_topic_not_the_composed_scaffold(
    crossref_calls, dead_scout, fake_llm
):
    crossref_calls["items"].append(_one_item())

    research.research_scout.func(
        topic="Ý định sử dụng ngân hàng số của sinh viên Việt Nam",
        research_questions=["RQ1: Yếu tố nào ảnh hưởng?"],
        seed_refs=["Davis 1989"],
    )

    assert len(crossref_calls["calls"]) == 1
    q = crossref_calls["calls"][0]["params"]["query.bibliographic"]
    # The scaffold labels are prompt furniture, not search terms. Sending them
    # to a bibliographic index poisons the query in every language.
    assert "Research questions:" not in q
    assert "Seed references:" not in q
    assert "RQ1" not in q
    assert "Davis 1989" not in q
    # English keywords, from the translation hop — Crossref is an English index.
    assert q == "technology acceptance model online banking Vietnam"


def test_translation_hop_sees_the_bare_topic_and_the_rqs(
    crossref_calls, dead_scout, fake_llm
):
    research.research_scout.func(
        topic="Ý định sử dụng ngân hàng số",
        research_questions=["RQ1: Yếu tố nào?"],
    )
    assert len(fake_llm) == 1
    assert "Ý định sử dụng ngân hàng số" in fake_llm[0]
    assert "RQ1: Yếu tố nào?" in fake_llm[0]


def test_translation_failure_degrades_to_raw_topic(crossref_calls, dead_scout, monkeypatch):
    from orchestrator.tools import m5_writing

    def _boom():
        raise RuntimeError("gateway down")

    monkeypatch.setattr(m5_writing, "_get_llm", _boom)
    crossref_calls["items"].append(_one_item())

    research.research_scout.func(topic="digital banking adoption")

    q = crossref_calls["calls"][0]["params"]["query.bibliographic"]
    assert q == "digital banking adoption"


def test_translation_hop_is_time_bounded(crossref_calls, dead_scout, monkeypatch):
    """A hung LLM in the recovery path must not become the new stall."""
    import time

    from orchestrator.tools import m5_writing

    def _factory():
        class _LLM:
            @staticmethod
            def invoke(prompt):
                time.sleep(5)
                return _FakeLLMResp("never arrives")
        return _LLM()

    monkeypatch.setattr(m5_writing, "_get_llm", _factory)
    monkeypatch.setenv("DOTHESIS_TRANSLATE_TIMEOUT_S", "1")
    crossref_calls["items"].append(_one_item())

    started = time.monotonic()
    research.research_scout.func(topic="digital banking adoption")
    elapsed = time.monotonic() - started

    assert elapsed < 4
    assert crossref_calls["calls"][0]["params"]["query.bibliographic"] == "digital banking adoption"


# --- fix 2: the zero-source outcome must be unmistakable ----------------------

def test_empty_crossref_yields_actionable_zero_signal(crossref_calls, dead_scout, fake_llm):
    out = json.loads(research.research_scout.func(topic="a topic with no matches"))

    assert out["count"] == 0
    assert out["sources"] == []
    # A zero-source fallback must not read like a successful one.
    assert out["note"] != "budgeted fallback (Crossref)"
    assert "hint" in out
    hint = out["hint"].lower()
    assert "doi" in hint or "upload" in hint


def test_nonempty_fallback_keeps_the_honesty_marker(crossref_calls, dead_scout, fake_llm):
    crossref_calls["items"].append(_one_item())
    out = json.loads(research.research_scout.func(topic="digital banking"))

    assert out["count"] == 1
    assert "fallback" in out["note"].lower()
    assert out["sources"][0]["doi"] == "10.1/abc"
