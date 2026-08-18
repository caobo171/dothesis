"""The authoritative [PROJECT STATE] header injected into every agent turn.

This is the fix for the chat-says-done / sidebar-says-needs_review drift: the
agent gets the real focus + per-module status prepended to the user message so
it can't confabulate completion.
"""
from agent.runtime import _state_header
from agent.state import ProjectStateStore


def test_header_all_locked_for_fresh_project(tmp_path):
    # Fresh project → authoritative "everything locked" context (accurate for
    # the M1 onboarding turn; not noise). The state line is now the FIRST line;
    # a derived [NEXT] line follows it (F2 Task 5).
    store = ProjectStateStore(tmp_path)
    header = _state_header(store)
    first_line = header.splitlines()[0]
    assert first_line == "[PROJECT STATE] focus=None | M1:locked M2:locked M3:locked M4:locked M5:locked"


def test_header_includes_next_line_midproject(tmp_path):
    # Mid-project (M1 has a title, needs questions) → the [NEXT] line leads to
    # the derived next sub-step so the agent closes the turn pointing there.
    store = ProjectStateStore(tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, reason="r")
    header = _state_header(store)
    assert "[PROJECT STATE]" in header
    assert "[NEXT]" in header
    assert "derive_questions" in header or "research question" in header.lower()


def test_execute_now_header_omits_competing_next_step(tmp_path):
    store = ProjectStateStore(tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, reason="r")
    header = _state_header(store, include_next=False)
    assert "[PROJECT STATE]" in header
    assert "[NEXT]" not in header


def test_header_survives_load_failure():
    # A roadmap/store hiccup must never break the turn — omit the header instead.
    class Boom:
        def load(self):
            raise RuntimeError("db down")

    assert _state_header(Boom()) == ""


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


def test_the_clicked_option_directive_is_injected_with_the_state_block():
    """A clicked option must reach the model as ground truth, not a suggestion.

    The student clicked a card the agent itself offered; answering that with
    another menu ("I cannot do that yet, first we must…") spends their turn and
    their credits to tell them no. The directive rides in the same injected
    block as [PROJECT STATE] / [NEXT], which the model already treats as
    something it may not argue with.
    """
    import asyncio
    from agent.runtime import CLICKED_OPTION_DIRECTIVE, stream_turn

    seen = {}

    class _Agent:
        async def astream(self, payload, *a, **k):
            # No attachments → the message is a plain dict.
            seen["text"] = payload["messages"][0]["content"]
            return
            yield  # pragma: no cover — makes this an async generator

    async def _run(clicked):
        async for _ in stream_turn(_Agent(), "t1", "Confirm", store=None,
                                   clicked_option=clicked):
            pass

    asyncio.run(_run(True))
    assert CLICKED_OPTION_DIRECTIVE in seen["text"]
    assert "Confirm" in seen["text"]          # their choice still rides along

    asyncio.run(_run(False))
    assert CLICKED_OPTION_DIRECTIVE not in seen["text"]
