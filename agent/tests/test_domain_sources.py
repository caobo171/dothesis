"""Domain-routed academic sources (Europe PMC / ERIC) for the M2 scout.

Covers the read-side routing added to agent/tools/research.py: classify the
thesis domain, supplement the universal base (OpenAlex/Crossref/Semantic
Scholar) with a specialized index for medical/education theses, dedup across
sources, and degrade gracefully. No network — clients are faked.
"""
import json

import pytest

import agent.tools.research as R
from engine.utils.api_citations import EuropePmcClient, EricClient, OpenAlexClient


# --- classifier -------------------------------------------------------------

@pytest.mark.parametrize("field,expected", [
    ("Y khoa", "medical"), ("Medicine", "medical"), ("Nursing", "medical"),
    ("Giáo dục", "education"), ("Education", "education"),
    ("Marketing", "general"), ("", "general"), (None, "general"),
])
def test_classify_domain_from_field(field, expected):
    assert R._classify_domain(field, "some unrelated topic text") == expected


@pytest.mark.parametrize("topic,expected", [
    ("telemedicine glycemic control in type 2 diabetes patients", "medical"),
    ("Ý định sử dụng dịch vụ y tế từ xa của bệnh nhân", "medical"),
    ("formative assessment in the primary classroom", "education"),
    ("Phương pháp giảng dạy tích cực trong giáo dục đại học", "education"),
    ("brand loyalty in e-commerce in Vietnam", "general"),
])
def test_classify_domain_keyword_fallback(topic, expected):
    assert R._classify_domain(None, topic) == expected


def test_classify_ambiguous_is_general():
    # both medical + education signals -> general (a wrong supplement is noise)
    assert R._classify_domain(None, "medical education curriculum for nursing students") == "general"


# --- client shape contract --------------------------------------------------

def test_client_shape_matches_openalex():
    oa = set(OpenAlexClient()._extract_metadata({
        "title": "T", "authorships": [{"author": {"display_name": "Jane Smith"}}],
        "publication_year": 2020, "doi": "https://doi.org/10.1/x"}).keys())
    epmc = set(EuropePmcClient()._extract_metadata({
        "title": "Statins.", "authorList": {"author": [{"lastName": "Berube"}]},
        "pubYear": "2021", "doi": "10.1/y",
        "journalInfo": {"journal": {"title": "Lancet"}},
        "pubTypeList": {"pubType": ["research-article"]}}).keys())
    eric = set(EricClient()._extract_metadata({
        "title": "Teaching", "author": ["Weasmer, Jerie"],
        "publicationdateyear": 2019, "url": "http://dx.doi.org/10.1080/z",
        "publicationtype": ["Journal Articles"]}).keys())
    assert epmc == oa
    assert eric == oa


def test_eric_author_and_doi_parsing():
    m = EricClient()._extract_metadata({
        "title": "X", "author": ["Weasmer, Jerie", "Elka Johansson"],
        "publicationdateyear": 2019, "url": "http://dx.doi.org/10.1080/abc"})
    assert m["authors"] == ["Weasmer", "Johansson"]
    assert m["doi"] == "10.1080/abc"


def test_europepmc_strips_html_and_missing_journalinfo():
    m = EuropePmcClient()._extract_metadata({
        "title": "Preprint title.", "authorString": "Nguyen L, Tran M.",
        "pubYear": "2024", "doi": "10.21203/rs.1",
        "pubTypeList": {"pubType": ["Preprint"]},
        "abstractText": "<h4>Background</h4> body"})
    assert m["journal"] == ""          # journalInfo absent -> no crash
    assert m["abstract"] == "Background  body"
    assert m["source_type"] == "report"  # preprint


# --- supplement routing + degradation ---------------------------------------

class _FakeEPMC:
    called = 0
    def search_papers(self, q, limit=10):
        type(self).called += 1
        return [{"title": "Med", "authors": ["Ng"], "year": 2022, "doi": "10.med/1", "journal": "Lancet"}]


class _FakeERIC:
    called = 0
    def search_papers(self, q, limit=10):
        type(self).called += 1
        return [{"title": "Edu", "authors": ["Le"], "year": 2021, "doi": "", "url": "https://eric.ed.gov/?id=EJ1"}]


@pytest.fixture
def fakes(monkeypatch):
    _FakeEPMC.called = _FakeERIC.called = 0
    monkeypatch.setattr(R, "EuropePmcClient", _FakeEPMC)
    monkeypatch.setattr(R, "EricClient", _FakeERIC)
    return _FakeEPMC, _FakeERIC


def test_medical_routes_to_europe_pmc(fakes):
    epmc, eric = fakes
    out = R._domain_supplement("q", "medical")
    assert epmc.called == 1 and eric.called == 0
    assert out[0]["doi"] == "10.med/1" and out[0]["verified"] is True


def test_education_routes_to_eric(fakes):
    epmc, eric = fakes
    out = R._domain_supplement("q", "education")
    assert eric.called == 1 and epmc.called == 0
    assert out[0]["verified"] is False  # ERIC row without DOI


def test_general_fires_neither(fakes):
    epmc, eric = fakes
    assert R._domain_supplement("q", "general") == []
    assert epmc.called == 0 and eric.called == 0


def test_supplement_failure_degrades(monkeypatch):
    class Boom:
        def search_papers(self, q, limit=10):
            raise RuntimeError("429 storm")
    monkeypatch.setattr(R, "EuropePmcClient", Boom)
    assert R._domain_supplement("q", "medical") == []  # never raises, never hangs


# --- dedup ------------------------------------------------------------------

def test_dedup_by_doi_title_and_backfill():
    rows = [
        {"title": "Alpha", "doi": "10.1/x", "verified": True},
        {"title": "Alpha copy", "doi": "https://doi.org/10.1/X", "verified": True},  # same DOI
        {"title": "Beta study", "doi": None, "verified": False},                     # base, no DOI
        {"title": "Beta  Study!", "doi": "10.2/y", "verified": True},                # title dup w/ DOI
        {"title": "Gamma", "doi": "10.3/z", "verified": True},
    ]
    out = R._dedup_sources(rows)
    assert len(out) == 3
    beta = next(s for s in out if R._title_key(s["title"]) == "beta study")
    assert beta["doi"] == "10.2/y" and beta["verified"] is True  # backfilled


# --- end-to-end fallback path merges supplement -----------------------------

def test_research_scout_fallback_merges_supplement(monkeypatch):
    # Force the deep scout to fail so the Crossref fallback path runs.
    import orchestrator.tools.m2_literature as m2
    monkeypatch.setattr(m2.scout_citations, "func", lambda *a, **k: None)
    # Deterministic query + base refs, and a fake medical index.
    monkeypatch.setattr(R, "_search_query_en", lambda t, rq: "diabetes telemedicine")
    monkeypatch.setattr(R, "_crossref_fallback",
                        lambda q, n=8: [{"title": "Base", "doi": "10.base/1", "verified": True}])
    monkeypatch.setattr(R, "EuropePmcClient", _FakeEPMC)
    _FakeEPMC.called = 0

    res = json.loads(R.research_scout.func(
        topic="telemedicine glycemic control in diabetes patients", min_sources=5))
    dois = {s["doi"] for s in res["sources"]}
    assert "10.base/1" in dois and "10.med/1" in dois       # base + supplement merged
    assert res["note"].startswith("budgeted fallback")      # honesty marker preserved
    assert _FakeEPMC.called == 1
