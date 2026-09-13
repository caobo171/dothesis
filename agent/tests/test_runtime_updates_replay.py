"""Each message in an `updates` chunk gets announced once, not once per step.

deepagents middleware (patch_tool_calls, the filesystem eviction hook) does not
return the step's new messages — it returns the ENTIRE checkpointed thread
wrapped in `Overwrite(...)`, so the add_messages reducer is bypassed.
runtime.py unwraps that to get at the real messages, which means a turn that
trips a middleware re-walks every ToolMessage and AIMessage the thread has ever
held.

What the student saw: one "I re-exported your thesis" reply carrying four
download cards, one per export they had run in that thread (46 KB, 103 KB,
195 KB, and the real one). The same replay double-counts `usage`, which is what
the credit ledger debits, and repeats tool_start/tool_end progress beats.
"""
import asyncio
import json

from agent.runtime import stream_turn


class _Msg:
    """Minimal stand-in for a LangChain message — runtime reads it by attr."""

    def __init__(self, id, type, *, name="", content="", usage=None, tool_calls=None):
        self.id = id
        self.type = type
        self.name = name
        self.content = content
        self.tool_calls = tool_calls or []
        self.response_metadata = {}
        if usage:
            self.usage_metadata = {
                "input_tokens": usage[0], "output_tokens": usage[1],
                "total_tokens": usage[0] + usage[1],
            }


def _export(id, size):
    return _Msg(id, "tool", name="export_docx", content=json.dumps({
        "ok": True,
        "artifacts": [{"kind": "docx", "download_url": f"/x/{id}", "size_bytes": size}],
    }))


class _State:
    def __init__(self, messages):
        self.values = {"messages": messages}


class _Agent:
    """Streams `updates` twice: the new tool result, then a middleware Overwrite
    that hands back the whole thread (history + that same result)."""

    def __init__(self, history, fresh):
        self._history = history
        self._fresh = fresh

    async def aget_state(self, config):
        return _State(self._history)

    async def astream(self, payload, *a, **k):
        from langgraph.types import Overwrite
        yield ("updates", {"tools": {"messages": self._fresh}})
        yield ("updates", {"model": {"messages": Overwrite(self._history + self._fresh)}})


def _drain(agent):
    async def _run():
        return [ev async for ev in stream_turn(agent, "t-replay", "export it", store=None)]
    return asyncio.run(_run())


def test_a_middleware_overwrite_does_not_replay_earlier_turns_exports():
    history = [_export("e1", 46_000), _export("e2", 103_000)]
    fresh = [_export("e3", 195_000)]

    events = _drain(_Agent(history, fresh))

    hints = [e for e in events if e["type"] == "tool_calls"]
    assert len(hints) == 1, f"one export this turn, one card: {hints}"
    assert hints[0]["payload"]["artifacts"][0]["size_bytes"] == 195_000


def test_usage_from_an_earlier_turn_is_not_billed_again():
    history = [_Msg("a1", "ai", usage=(10_000, 500))]
    fresh = [_Msg("a2", "ai", usage=(12_000, 700))]

    events = _drain(_Agent(history, fresh))

    usage = [e for e in events if e["type"] == "usage"]
    assert len(usage) == 1, f"only this turn's tokens are billable: {usage}"
    assert usage[0]["input_tokens"] == 12_000


def test_the_same_message_arriving_twice_in_one_turn_announces_once():
    fresh = [_export("e1", 195_000)]

    # No history at all: the duplicate comes purely from the tool node and the
    # middleware both carrying the message within this one turn.
    events = _drain(_Agent([], fresh))

    assert len([e for e in events if e["type"] == "tool_calls"]) == 1
    assert len([e for e in events if e["type"] == "tool_end"]) == 1


# --- the compaction summary is not the answer -------------------------------

class _Chunk:
    """An AIMessageChunk as the `messages` stream hands it over."""

    def __init__(self, text):
        self.content = text
        self.type = "AIMessageChunk"
        self.id = None


class _StreamingAgent:
    def __init__(self, chunks):
        self._chunks = chunks

    async def aget_state(self, config):
        return _State([])

    async def astream(self, payload, *a, **k):
        for msg, meta in self._chunks:
            yield ("messages", (msg, meta))


def test_the_auto_compaction_summary_is_not_streamed_as_the_reply():
    """What the student actually received when the thread crossed the compaction
    threshold: "## SESSION INTENT / ## SUMMARY / M1: done, M2: done …" — the
    agent's private notes about their own project, in place of an answer to the
    question they asked (merge the construct cells in the table).

    The summary is written by the SAME model, so its tokens are indistinguishable
    from a reply except for the tag SummarizationMiddleware puts on the call.
    """
    agent = _StreamingAgent([
        (_Chunk("## SESSION INTENT\n\nCải thiện và xuất lại luận văn"),
         {"lc_source": "summarization"}),
        (_Chunk("## SUMMARY\n\n- M1: done\n- M2: done"),
         {"langgraph_node": "model", "metadata": {"lc_source": "summarization"}}),
        (_Chunk("Đã gộp các biến quan sát."), {"langgraph_node": "model"}),
    ])

    events = _drain(agent)
    text = "".join(e.get("text", "") for e in events if e["type"] == "token")

    assert "SESSION INTENT" not in text
    assert "SUMMARY" not in text
    assert text == "Đã gộp các biến quan sát."


def test_the_summary_is_surfaced_as_its_own_labelled_card():
    """Hiding it outright was too quiet — compaction spends the student's
    credits and decides what the agent remembers about their thesis, so the
    text is kept and handed to the UI as its own collapsed card instead of
    being pasted over the answer."""
    agent = _StreamingAgent([
        (_Chunk("## SESSION INTENT\n\nCải thiện luận văn"), {"lc_source": "summarization"}),
        (_Chunk("\n\n## SUMMARY\n- M1: done"), {"lc_source": "summarization"}),
        (_Chunk("Đã gộp các biến quan sát."), {"langgraph_node": "model"}),
    ])

    events = _drain(agent)
    cards = [e["payload"] for e in events
             if e["type"] == "tool_calls"
             and e["payload"].get("widget_type") == "context_summary"]

    assert len(cards) == 1, "one compaction, one card"
    assert cards[0]["text"].startswith("## SESSION INTENT")
    assert "## SUMMARY" in cards[0]["text"]


def test_no_compaction_means_no_card():
    agent = _StreamingAgent([(_Chunk("Xong rồi."), {"langgraph_node": "model"})])
    events = _drain(agent)
    assert not [e for e in events if e["type"] == "tool_calls"]
