"""Brief §5 — context assembly tests.

Phase 1: FULL_MODE for short projects (most), stopgap truncation for
projects that overflow. Phase 2 (pgvector + summaries) is deferred but
the dataclass shape carries the fields it'll populate.
"""
from langchain_core.messages import AIMessage, HumanMessage

from orchestrator import memory
from orchestrator.state import ContextStore


def test_full_mode_when_under_ceiling():
    # Default ceiling is 90k tokens. A 3-turn transcript with a small
    # system prompt is nowhere near it → FULL mode, transcript intact.
    ctx = memory.assemble_context(
        system_prompt="You are a thesis assistant.",
        handler_prompt="Working on M1.",
        focus="M1", target="M1", cs=ContextStore(),
        transcript=[
            HumanMessage(content="Hello"),
            AIMessage(content="Hi, what's your topic?"),
            HumanMessage(content="Gen Z and TikTok"),
        ],
    )
    assert ctx.mode == "full"
    assert len(ctx.turns) == 3
    assert ctx.retrieved == []
    assert ctx.summaries == {}


def test_focus_and_target_slices_returned_separately():
    # Brief §5: callers need both focus AND target slices to support
    # cross-module read/mutate. The function returns them as separate
    # fields so handlers don't have to re-derive.
    cs = ContextStore(
        m1_topic={"research_title": "X"},
        m2_literature={"research_gaps": ["g1"]},
    )
    ctx = memory.assemble_context(
        system_prompt="", handler_prompt="",
        focus="M1", target="M2", cs=cs, transcript=[],
    )
    assert ctx.focus_slice == {"research_title": "X"}
    assert ctx.target_slice == {"research_gaps": ["g1"]}


def test_full_mode_target_equals_focus_returns_same_slice():
    # Same-module case (continue intent): target == focus, both fields
    # point at the same data so callers can use either uniformly.
    cs = ContextStore(m1_topic={"research_title": "X"})
    ctx = memory.assemble_context(
        system_prompt="", handler_prompt="",
        focus="M1", target="M1", cs=cs, transcript=[],
    )
    assert ctx.focus_slice == ctx.target_slice == {"research_title": "X"}


def test_overflow_falls_back_to_stopgap_truncation(monkeypatch):
    # Force a tiny ceiling so the test transcript blows through it. The
    # stopgap MUST keep the most-recent turns and drop the oldest.
    monkeypatch.setattr(memory, "FULL_MODE_CEILING", 50)  # tokens
    transcript = [
        HumanMessage(content="A" * 200),  # oldest, ~50 tokens
        AIMessage(content="B" * 200),
        HumanMessage(content="C" * 100),  # most recent
    ]
    ctx = memory.assemble_context(
        system_prompt="sys", handler_prompt="hp",
        focus="M1", target="M1", cs=ContextStore(),
        transcript=transcript,
    )
    assert ctx.mode == "tiered"
    # Most recent kept, oldest dropped.
    assert ctx.turns[-1].content == "C" * 100
    # We dropped at least one turn.
    assert len(ctx.turns) < 3


def test_no_focus_returns_empty_focus_slice():
    # First turn on a new project has focus=None — handlers must still
    # be able to assemble (e.g. for the cold-start M1 pick).
    ctx = memory.assemble_context(
        system_prompt="", handler_prompt="",
        focus=None, target="M1", cs=ContextStore(), transcript=[],
    )
    assert ctx.focus_slice == {}
    assert ctx.target_slice == {}


def test_empty_transcript_returns_empty_turns():
    ctx = memory.assemble_context(
        system_prompt="hi", handler_prompt="hp",
        focus="M1", target="M1", cs=ContextStore(), transcript=[],
    )
    assert ctx.mode == "full"
    assert ctx.turns == []
