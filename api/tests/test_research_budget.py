"""_budgeted_scout's discipline (wall-clock cap + Crossref fallback) moved
behind research_scout (spec §3) — the same tool now protects all three
surfaces from a hung/rate-limited deep scout.

NOTE: scout_citations is a pydantic StructuredTool — `.func` is not a settable
field (same trap the compose_export tests document for compose_chapter), so we
swap the WHOLE object in the m2 namespace; research_scout resolves it by a
call-time `from ... import scout_citations`, which reads the patched binding.

No real network: the deep scout is always monkeypatched, and research.httpx.get
is stubbed so the Crossref fallback never leaves the process.
"""
import json
from types import SimpleNamespace

import agent.tools.research as research


class _Resp:
    def json(self):
        return {"message": {"items": [{
            "title": ["Livestream commerce and purchase intention"],
            "author": [{"family": "Sun"}],
            "issued": {"date-parts": [[2019]]},
            "container-title": ["ECRA"],
            "DOI": "10.1/x", "URL": "https://doi.org/10.1/x",
        }]}}


def test_scout_failure_falls_back_to_crossref(monkeypatch):
    import orchestrator.tools.m2_literature as m2

    def boom(*a, **k):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(m2, "scout_citations", SimpleNamespace(func=boom))
    monkeypatch.setattr(research.httpx, "get", lambda *a, **k: _Resp())
    out = json.loads(research.research_scout.func("livestream commerce"))
    assert out["count"] == 1
    assert out["sources"][0]["doi"] == "10.1/x"
    assert out["note"] == "budgeted fallback (Crossref)"


def test_scout_timeout_falls_back(monkeypatch):
    import time

    import orchestrator.tools.m2_literature as m2

    def hang(*a, **k):
        time.sleep(3)
        return []

    monkeypatch.setenv("DOTHESIS_SCOUT_TIMEOUT_S", "1")
    monkeypatch.setattr(m2, "scout_citations", SimpleNamespace(func=hang))
    monkeypatch.setattr(research.httpx, "get", lambda *a, **k: _Resp())
    out = json.loads(research.research_scout.func("anything"))
    assert out["note"] == "budgeted fallback (Crossref)"


def test_scout_success_is_unchanged(monkeypatch):
    import orchestrator.tools.m2_literature as m2
    monkeypatch.setattr(
        m2, "scout_citations",
        SimpleNamespace(func=lambda *a, **k: [{"title": "P", "doi": "10.2/y"}]))
    out = json.loads(research.research_scout.func("topic"))
    assert out["count"] == 1 and "note" not in out
