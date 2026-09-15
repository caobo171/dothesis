"""Backfill availability reaches the agent as a doctor finding, every turn.

Previously a standalone `_new_context_backfill_directive` in chat_v3, gated on
attachments. That gate was the bug: the student's retry was "hãy xuất lại đi
quá thiếu nhiều thông tin" — a plain message, no file — so the directive stayed
silent and chapters 2 and 3 exported empty for the second time. The signal is
the STATE (modules reconstructable and unfinished), not whether this particular
turn carried a file.

These are the same five assertions that file made, moved onto the doctor.
"""
from app.doctor_adapter import _render_directive
from orchestrator.doctor import DoctorInput, diagnose

# Project 500319a8 as of 2026-09-15: M2 absent entirely, M3 holding only a
# questionnaire, M4 thin.
_THREAD_C10F6D13 = {
    "m1_topic": {"research_title": "Tác động của tiếp thị người ảnh hưởng",
                 "research_type": "quantitative"},
    "m3_design": {"instrument": {"items": ["q1"]}},
    "m4_analysis": {"analysis_outline": {"research_design": "Định lượng"}},
}


def _backfill_finding(context_store):
    found = [f for f in diagnose(DoctorInput(context_store=context_store,
                                             uploads=[], chapter_prose={}))
             if f.code == "BACKFILL_AVAILABLE"]
    return found[0] if found else None


def test_a_turn_with_no_attachment_still_produces_the_finding():
    f = _backfill_finding(_THREAD_C10F6D13)
    assert f is not None
    assert {"M2", "M3"} <= set(f.payload["modules"])


def test_the_directive_names_the_modules_and_the_tool():
    f = _backfill_finding(_THREAD_C10F6D13)
    out = _render_directive(f)
    assert "backfill_upstream_modules" in out
    assert "M2" in out and "M3" in out


def test_the_directive_overrides_the_locked_status_the_header_shows():
    """`[PROJECT STATE]` prints `M2:locked`, and the model reads that as "not
    mine to touch" — which is why it scoped the backfill to M4. The directive
    has to contradict that line, or it loses to the one printed above it."""
    assert "locked" in _render_directive(_backfill_finding(_THREAD_C10F6D13)).lower()


def test_the_directive_forbids_narrowing():
    out = _render_directive(_backfill_finding(_THREAD_C10F6D13))
    assert "Do not narrow it" in out


def test_no_finding_when_there_is_nothing_left_to_reconstruct():
    whole = {"m1_topic": {"research_title": "T", "research_type": "quantitative",
                          "field": "F", "scope": "S", "objectives": ["o"],
                          "research_questions": ["rq"], "target_population": "p",
                          "confirmed_at": "2026-09-15T05:31:59+00:00"}}
    assert _backfill_finding(whole) is None


def test_an_empty_project_produces_no_finding():
    assert _backfill_finding({}) is None
