"""The authoritative [PROJECT STATE] header injected into every agent turn.

This is the fix for the chat-says-done / sidebar-says-needs_review drift: the
agent gets the real focus + per-module status prepended to the user message so
it can't confabulate completion.
"""
from agent.runtime import _state_header
from agent.state import ProjectStateStore


def test_header_all_locked_for_fresh_project(tmp_path):
    # Fresh project → authoritative "everything locked" context (accurate for
    # the M1 onboarding turn; not noise).
    store = ProjectStateStore(tmp_path)
    header = _state_header(store)
    assert header == "[PROJECT STATE] focus=None | M1:locked M2:locked M3:locked M4:locked M5:locked"


def test_header_none_store():
    assert _state_header(None) == ""


def test_header_reflects_real_status(tmp_path):
    store = ProjectStateStore(tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    # Committing M1 sets focus=M1; downstream stay locked (untouched).
    header = _state_header(store)
    assert header.startswith("[PROJECT STATE]")
    assert "focus=M1" in header
    assert "M1:done" in header
    assert "M5:locked" in header


def test_header_surfaces_needs_review_drift(tmp_path):
    # Reproduces the bug's truth: M5 done, then an M4 commit flips it to
    # needs_review. The header must show needs_review so the agent can't claim
    # "M5 done".
    store = ProjectStateStore(tmp_path)
    store.commit_slice("M4", {"analysis_results": {"r": 1}}, reason="r", confirm_done=True)
    store.commit_slice("M5", {"final_sections": [{"title": "Intro"}]}, reason="r", confirm_done=True)
    store.commit_slice("M4", {"analysis_results": {"r": 2}}, reason="rerun", confirm_done=True)
    header = _state_header(store)
    assert "M5:needs_review" in header
