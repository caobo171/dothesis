"""Source (DOI) verification rubric dimension — offline (roadmap #5)."""
import pytest

from quality import rubric
from quality.rubric import (
    _normalize_doi, score_thesis, source_verification_dimension,
)


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    rubric._DOI_CACHE.clear()
    monkeypatch.delenv("DOTHESIS_RUBRIC_DOI_CHECK", raising=False)
    yield
    rubric._DOI_CACHE.clear()


def _cs(sources):
    return {"m2_literature": {"literature_sources": sources}}


# --- Phase 1.1: skeleton + syntax -------------------------------------------

def test_empty_pool():
    d = source_verification_dimension({})
    assert d["name"] == "source_verification" and d["weight"] == 0.10
    assert d["score"] == 1.0 and d["findings"] == []
    assert d["meta"] == {"checked": 0, "verified": 0, "unverified": 0, "no_doi": 0,
                         "network_enabled": False}


def test_no_doi_entries_counted_not_flagged():
    d = source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."], "year": 2020},
                                          {"title": "U", "doi": None}, {"title": "V", "doi": ""}]))
    assert d["findings"] == [] and d["meta"]["no_doi"] == 3


def test_normalize_doi():
    assert _normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
    assert _normalize_doi("  doi:10.1/x  ") == "10.1/x"


def test_malformed_doi_soft_finding():
    d = source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."],
                                            "year": 2020, "doi": "not-a-doi"}]))
    assert len(d["findings"]) == 1
    f = d["findings"][0]
    assert f["severity"] == "soft" and f["chapter"] == "lit_review" and "DOI" in f["issue"]
    assert d["meta"]["checked"] == 0


# --- Phase 1.2: pure junk checks + fail-open --------------------------------

def test_author_sanity_flag():
    d = source_verification_dimension(_cs([{"title": "Real", "authors": ["E. A. W."],
                                            "year": 2020, "doi": "10.1234/ok"}]),
                                      doi_verifier=lambda x: True)
    assert any("Author" in f["issue"] for f in d["findings"])


def test_clean_entry_no_findings():
    d = source_verification_dimension(_cs([{"title": "A Real Paper", "authors": ["Smith, J."],
                                            "year": 2020, "doi": "10.1234/ok"}]),
                                      doi_verifier=lambda x: True)
    assert d["findings"] == [] and d["score"] == 1.0


def test_fail_open_when_engine_import_fails(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "engine.utils.citation_validator", None)
    d = source_verification_dimension(_cs([{"title": "T", "doi": "not-a-doi"}]))
    assert any("DOI" in f["issue"] for f in d["findings"])  # syntax finding survives


# --- Phase 1.3: injected verifier -------------------------------------------

def test_verifier_false_soft_finding():
    d = source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."],
                                            "year": 2020, "doi": "10.1234/ok"}]),
                                      doi_verifier=lambda x: False)
    assert len(d["findings"]) == 1 and "CrossRef" in d["findings"][0]["issue"]
    assert d["score"] == 0.9 and d["meta"]["checked"] == 1


def test_verifier_none_never_lowers_score():
    d = source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."],
                                            "year": 2020, "doi": "10.1234/ok"}]),
                                      doi_verifier=lambda x: None)
    assert d["findings"] == [] and d["score"] == 1.0 and d["meta"]["unverified"] == 1


def test_raising_verifier_treated_as_none():
    d = source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."],
                                            "year": 2020, "doi": "10.1234/ok"}]),
                                      doi_verifier=lambda x: 1 / 0)
    assert d["findings"] == [] and d["meta"]["unverified"] == 1


def test_verifier_receives_normalized_doi():
    seen = {}
    source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."], "year": 2020,
                                        "doi": "https://doi.org/10.1234/ABC"}]),
                                  doi_verifier=lambda d: seen.setdefault("doi", d) or True)
    assert seen["doi"] == "10.1234/abc"


def test_default_verifier_off():
    d = source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."],
                                            "year": 2020, "doi": "10.1234/ok"}]))
    assert d["meta"]["checked"] == 0 and d["meta"]["network_enabled"] is False


# --- Phase 1.4: score_thesis wiring -----------------------------------------

def test_score_thesis_includes_dimension(monkeypatch):
    monkeypatch.setattr(rubric, "judge_dimension",
                        lambda name, weight, prompt, cs: {"name": name, "weight": weight,
                                                          "score": 0.6, "findings": []})
    out = score_thesis(_cs([{"title": "T", "authors": ["Smith, J."], "year": 2020,
                             "doi": "10.1/x"}]), doi_verifier=lambda d: False)
    names = {d["name"] for d in out["dimensions"]}
    assert "source_verification" in names and {"citations", "stats_validity"} <= names
    assert 0.0 <= out["overall"] <= 1.0
    # soft finding must NOT block
    assert not any("CrossRef" in b for b in out["blocking"])


# --- Phase 2: env-gated default verifier + budget ---------------------------

def test_env_flag_enables_default(monkeypatch):
    monkeypatch.setenv("DOTHESIS_RUBRIC_DOI_CHECK", "1")
    calls = {"n": 0}

    def fake_validate(self, doi):
        calls["n"] += 1
        return False

    from engine.utils.citation_validator import CitationValidator
    monkeypatch.setattr(CitationValidator, "validate_doi", fake_validate)
    d = source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."],
                                            "year": 2020, "doi": "10.1234/ok"}]))
    assert d["meta"]["network_enabled"] is True and calls["n"] == 1
    assert any("CrossRef" in f["issue"] for f in d["findings"])


def test_cache_dedupes_lookups(monkeypatch):
    monkeypatch.setenv("DOTHESIS_RUBRIC_DOI_CHECK", "1")
    calls = {"n": 0}
    from engine.utils.citation_validator import CitationValidator
    monkeypatch.setattr(CitationValidator, "validate_doi",
                        lambda self, doi: (calls.__setitem__("n", calls["n"] + 1), True)[1])
    cs = _cs([{"title": "T", "authors": ["Smith, J."], "year": 2020, "doi": "10.1234/ok"}])
    source_verification_dimension(cs)
    source_verification_dimension(cs)  # second time hits cache
    assert calls["n"] == 1


def test_lookup_budget(monkeypatch):
    monkeypatch.setenv("DOTHESIS_RUBRIC_DOI_CHECK", "1")
    calls = {"n": 0}
    from engine.utils.citation_validator import CitationValidator
    monkeypatch.setattr(CitationValidator, "validate_doi",
                        lambda self, doi: (calls.__setitem__("n", calls["n"] + 1), True)[1])
    pool = [{"title": f"T{i}", "authors": ["Smith, J."], "year": 2020, "doi": f"10.1234/x{i}"}
            for i in range(25)]
    d = source_verification_dimension(_cs(pool))
    assert calls["n"] <= 20 and d["meta"]["unverified"] >= 5


def test_no_real_network(monkeypatch):
    monkeypatch.setenv("DOTHESIS_RUBRIC_DOI_CHECK", "1")
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network hit")))
    from engine.utils.citation_validator import CitationValidator
    monkeypatch.setattr(CitationValidator, "validate_doi", lambda self, doi: True)
    source_verification_dimension(_cs([{"title": "T", "authors": ["Smith, J."],
                                        "year": 2020, "doi": "10.1234/ok"}]))
