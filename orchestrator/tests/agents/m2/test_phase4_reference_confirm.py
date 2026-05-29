"""Tests for Phase 4 — Reference_Confirm."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


def _state(mode="interactive", user_msg="continue"):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="X",
        research_type="quantitative", language="en",
        paper_uris=[], mode=mode,
    )
    s["messages"] = [HumanMessage(content=user_msg)]
    s["candidate_gaps"] = [
        {"id": "1", "description": "g1",
         "supporting_papers": [
             {"author": "Wang", "year": 2011, "page": 118},
             {"author": "Bass", "year": 1985, "page": 31},
         ]},
    ]
    s["selected_gap_ids"] = ["1"]
    return s


def test_phase4_first_call_populates_queue_and_asks_first(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    patch = phase4_reference_confirm.run(_state())
    assert len(patch["pending_page_checks"]) == 2
    assert patch.get("page_check_cursor") == 0
    msgs = patch.get("messages", [])
    assert "Wang" in msgs[0].content


def test_phase4_confirm_advances_cursor(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    s = _state(user_msg="yes")
    s["pending_page_checks"] = [
        {"author": "Wang", "year": 2011, "page": 118, "verified": False},
        {"author": "Bass", "year": 1985, "page": 31, "verified": False},
    ]
    s["page_check_cursor"] = 0
    patch = phase4_reference_confirm.run(s)
    assert patch.get("page_check_cursor") == 1
    new_verified = patch.get("verified_refs", [])
    assert len(new_verified) == 1
    assert new_verified[0]["verified"] is True


def test_phase4_correct_page_updates_and_advances(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    from orchestrator.agents.m2 import intent as m2_intent
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    # LLM intent: correct_page. Regex backfill picks "120" from the message.
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = m2_intent.PhaseIntent(action="correct_page")
    fake_intent = MagicMock()
    fake_intent.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(m2_intent, "_intent_llm", lambda: fake_intent)

    s = _state(user_msg="correct page 120")
    s["pending_page_checks"] = [
        {"author": "Wang", "year": 2011, "page": 118, "verified": False},
        {"author": "Bass", "year": 1985, "page": 31, "verified": False},
    ]
    s["page_check_cursor"] = 0
    patch = phase4_reference_confirm.run(s)
    assert patch["verified_refs"][0]["page"] == 120
    assert patch["verified_refs"][0]["verified"] is True
    assert patch["page_check_cursor"] == 1


def test_phase4_skip_all_marks_remaining_unverified(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    from orchestrator.agents.m2 import intent as m2_intent
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    # LLM-classified intent: skip_all.
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = m2_intent.PhaseIntent(action="skip_all")
    fake_intent = MagicMock()
    fake_intent.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(m2_intent, "_intent_llm", lambda: fake_intent)

    s = _state(user_msg="skip all")
    s["pending_page_checks"] = [
        {"author": "Wang", "year": 2011, "page": 118, "verified": False},
        {"author": "Bass", "year": 1985, "page": 31, "verified": False},
    ]
    s["page_check_cursor"] = 0
    patch = phase4_reference_confirm.run(s)
    assert patch.get("current_phase") == "output_gen"
    assert len(patch.get("verified_refs", [])) == 2
    assert all(r["verified"] is False for r in patch["verified_refs"])


def test_phase4_auto_mode_skips_all_user_prompts(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify",
                        lambda paper_uris, refs: refs)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    patch = phase4_reference_confirm.run(_state(mode="auto"))
    assert patch.get("current_phase") == "output_gen"


def test_phase4_auto_verify_marks_matched_references(monkeypatch):
    from orchestrator.agents.m2.phases import phase4_reference_confirm

    def fake_auto_verify(paper_uris, refs):
        return [
            {**r, "verified": True} if r["author"] == "Wang" else r
            for r in refs
        ]
    monkeypatch.setattr(phase4_reference_confirm, "_auto_verify", fake_auto_verify)
    monkeypatch.setattr(phase4_reference_confirm, "_get_llm", lambda: MagicMock())

    s = _state()
    s["paper_uris"] = ["s3://b/wang2011.pdf"]
    patch = phase4_reference_confirm.run(s)
    pending = patch["pending_page_checks"]
    assert pending[0]["author"] == "Wang"
    assert pending[0]["verified"] is True
    msgs = patch.get("messages", [])
    assert msgs and "Bass" in msgs[0].content
