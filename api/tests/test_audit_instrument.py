"""Questionnaire Doctor tests (F7 Task 1).

Pure/deterministic lint — no LLM, no store, no network. We assert the tool's
`.func` (the unwrapped callable behind the LangChain @tool) surfaces the
item-level issues the guidance file documents.
"""
import json

from agent.tools.instrument import audit_instrument, audit_instrument_findings


def test_double_barreled_item_flagged():
    inst = {"items": [{"id": "q1", "text": "The app is fast and reliable", "construct": "PE"}]}
    out = json.loads(audit_instrument.func(instrument=inst, hypotheses=[], constructs=["PE"]))
    assert any("double" in f["issue"].lower() for f in out["findings"])


def test_missing_reverse_coded_per_construct_flagged():
    inst = {"items": [{"id": "q1", "text": "I like it", "construct": "ATT", "reverse_coded": False}]}
    out = json.loads(audit_instrument.func(instrument=inst, hypotheses=[], constructs=["ATT"]))
    assert any("reverse" in f["issue"].lower() for f in out["findings"])


def test_scale_provenance_skeleton_has_one_row_per_construct():
    inst = {"items": [{"id": "q1", "text": "ok", "construct": "PE"}]}
    out = json.loads(audit_instrument.func(instrument=inst, hypotheses=[], constructs=["PE", "ATT"]))
    provenance = out["scale_provenance"]
    assert {p["construct"] for p in provenance} == {"PE", "ATT"}


def test_attention_check_present_suppresses_finding():
    inst = {"items": [
        {"id": "q1", "text": "I like it", "construct": "ATT", "reverse_coded": True},
        {"id": "att", "text": "Please select Strongly Agree", "construct": "ATT",
         "attention_check": True},
    ]}
    out = audit_instrument_findings(inst, [], ["ATT"])
    assert not any("attention" in f["issue"].lower() for f in out["findings"])
