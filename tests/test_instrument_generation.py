"""Instrument generation depth (§3.4): attention checks + scale provenance."""
from agent.tools.instrument import (
    audit_instrument_findings, generate_attention_check_items,
)


def test_generate_attention_check_en():
    items = generate_attention_check_items("en", n=1)
    assert len(items) == 1 and items[0]["attention_check"] is True
    assert "select" in items[0]["text"].lower() and items[0]["expected_answer"]


def test_generate_attention_check_vi():
    items = generate_attention_check_items("vi", n=1)
    assert "chọn" in items[0]["text"].lower()


def test_provenance_prefilled_from_sources():
    sources = [{"title": "Transformational leadership and engagement", "authors": ["Bass"], "year": 2019},
               {"title": "Coffee market volatility", "authors": ["Lee"], "year": 2020}]
    out = audit_instrument_findings({"items": [{"id": "L1", "construct": "Leadership"}]},
                                    [], ["Leadership"], sources=sources)
    prov = out["scale_provenance"][0]
    assert prov["construct"] == "Leadership"
    assert "Bass (2019)" == prov["adapted_from"]      # best token match, not coffee
    assert prov["adapted_from_confirmed"] is False


def test_provenance_blank_without_sources():
    out = audit_instrument_findings({"items": [{"id": "L1", "construct": "Leadership"}]},
                                    [], ["Leadership"])
    assert out["scale_provenance"][0]["adapted_from"] == ""


def test_missing_attention_check_offers_ready_item():
    out = audit_instrument_findings(
        {"items": [{"id": "L1", "construct": "Leadership", "text": "I trust my leader."}]},
        [], ["Leadership"], language="en")
    assert any(f["issue"] == "No attention-check item." for f in out["findings"])
    assert out["suggested_attention_checks"] and out["suggested_attention_checks"][0]["attention_check"]


def test_present_attention_check_no_suggestion():
    out = audit_instrument_findings(
        {"items": [{"id": "AC1", "attention_check": True, "text": "select 5"}]}, [], [])
    assert out["suggested_attention_checks"] == []
