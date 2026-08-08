"""A clicked option must be ACTED ON, not answered with another menu.

Reported turn: the agent offered "Complete and confirm the English thesis",
the student clicked it, and the reply was "I cannot complete the confirmation
in this turn…" plus a NEW menu whose first option was the prerequisite. The
click cost them a turn and its credits to be told no.
"""
import uuid

from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Message, Project, Thread, User
from app.routers.chat_v3 import _clicked_a_previous_option


def _thread_with_options(options, *, widget_type="card_grid", wrap=False):
    engine = get_engine()
    with Session(engine) as s:
        u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
                 password_hash="x", email_verified=True)
        s.add(u); s.flush()
        p = Project(user_id=u.id, name="T", current_module="M1", status="draft")
        s.add(p); s.flush()
        t = Thread(project_id=p.id, name="Main", langgraph_thread_id=str(uuid.uuid4()))
        s.add(t); s.flush()
        hint = {
            "widget_type": widget_type, "field_name": "user_choice", "title": "",
            "options": [{"value": o, "label": o} for o in options],
            "multi_select": False,
        }
        s.add(Message(thread_id=t.id, role="assistant", content="Pick one",
                      tool_calls_json={"widgets": [hint]} if wrap else hint))
        s.commit()
        return t.id


def test_an_offered_option_is_recognised():
    tid = _thread_with_options(["Complete and confirm the English thesis",
                                "Review Chapters 4–5 first"])
    with Session(get_engine()) as s:
        assert _clicked_a_previous_option(
            s, tid, "Complete and confirm the English thesis") is True


def test_a_normal_typed_message_is_not_a_click():
    tid = _thread_with_options(["Confirm", "Refine"])
    with Session(get_engine()) as s:
        assert _clicked_a_previous_option(s, tid, "actually, can you explain HTMT?") is False


def test_matching_ignores_case_and_surrounding_space():
    tid = _thread_with_options(["Generate the complete English thesis"])
    with Session(get_engine()) as s:
        assert _clicked_a_previous_option(
            s, tid, "  generate the complete english thesis ") is True


def test_options_wrapped_in_a_widgets_list_still_match():
    """One turn can emit several widgets; both shapes are persisted."""
    tid = _thread_with_options(["Confirm"], wrap=True)
    with Session(get_engine()) as s:
        assert _clicked_a_previous_option(s, tid, "Confirm") is True


def test_a_non_option_widget_is_not_a_click_source():
    """An export download card carries no choices to click."""
    tid = _thread_with_options(["thesis.docx"], widget_type="download_card")
    with Session(get_engine()) as s:
        assert _clicked_a_previous_option(s, tid, "thesis.docx") is False


def test_no_previous_assistant_message_is_not_a_click():
    engine = get_engine()
    with Session(engine) as s:
        u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
                 password_hash="x", email_verified=True)
        s.add(u); s.flush()
        p = Project(user_id=u.id, name="T", current_module="M1", status="draft")
        s.add(p); s.flush()
        t = Thread(project_id=p.id, name="Main", langgraph_thread_id=str(uuid.uuid4()))
        s.add(t); s.commit()
        assert _clicked_a_previous_option(s, t.id, "anything") is False


def test_an_empty_message_is_never_a_click():
    tid = _thread_with_options(["Confirm"])
    with Session(get_engine()) as s:
        assert _clicked_a_previous_option(s, tid, "   ") is False
