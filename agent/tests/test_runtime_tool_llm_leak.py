"""An LLM a TOOL calls is not the reply — its raw output must never stream out.

`stream_mode="messages"` is per-LLM-call, not per-reply: LangGraph's
StreamMessagesHandler registers every chat model started inside the graph and
emits its message on `on_llm_end` — so a plain, non-streaming `llm.invoke()`
made *inside a tool* lands on the same channel the answer does. chat_v3
accumulates that channel into the assistant message, so the tool's scratch
output becomes the student's reply.

What the student saw (thread c10f6d13, 2026-09-15): they asked for chapters 4
and 5 and got ~2 KB of raw JSON — `{"data_type_detected": "Unknown",
"analysis_outline": {…}, "_rationale": …}` — glued directly onto the front of
the real answer (`…}## Chương 4 và Chương 5`). That JSON is
orchestrator/backfill.py's `reconstruct_artifact` prompt result, which the
`backfill_upstream_modules` tool had ALREADY rendered properly as a
`reconstructed_modules` card. It was pure duplication, unformatted.

Not specific to backfill: every orchestrator tool (m1_topic, m2_literature,
m4_analysis, m5_writing, humanize, cite_docx, domain_sources) invokes an LLM
the same way, so each one can dump its scratch prompt output into a reply. The
guard is therefore on the node, not on any one tool.
"""
import asyncio

from agent.runtime import stream_turn

BACKFILL_JSON = (
    '{"data_type_detected": "Unknown", '
    '"_rationale": "Suy luận dựa trên việc đề tài được xác định là định lượng."}'
)
REPLY = "## Chương 4 và Chương 5\n\nMình đã soạn hai chương dựa trên dàn bài."


class _AIChunk:
    """Minimal AIMessageChunk stand-in — runtime reads these by attribute."""

    type = "AIMessageChunk"

    def __init__(self, content):
        self.content = content
        self.tool_calls = []
        self.response_metadata = {}


class _Agent:
    """Replays the real thread: the backfill tool's internal `llm.invoke()`
    surfaces on the `messages` channel from the `tools` node, then the agent's
    own model streams the actual answer from the `model` node."""

    async def aget_state(self, config):
        raise RuntimeError("no checkpoint")  # runtime tolerates this

    async def astream(self, payload, *a, **k):
        yield ("messages", (_AIChunk(BACKFILL_JSON), {
            "langgraph_node": "tools",
            "langgraph_checkpoint_ns": "tools:327209e1-29ff-10b5-f7bf-b2b48352ffbf",
        }))
        yield ("messages", (_AIChunk(REPLY), {
            "langgraph_node": "model",
            "langgraph_checkpoint_ns": "model:bc33f148-f302-fa5c-1461-1fd2f893b90e",
        }))


def _reply_text() -> str:
    async def _run():
        return [ev async for ev in stream_turn(
            _Agent(), "t-leak", "Dựa vào dàn bài này viết cho tôi chương 4 chương 5.",
            store=None)]
    events = asyncio.run(_run())
    return "".join(e["text"] for e in events if e.get("type") == "token")


def test_tool_internal_llm_output_is_not_in_the_reply():
    assert BACKFILL_JSON not in _reply_text()


def test_the_real_answer_still_streams():
    # The guard must key on the NODE, not on "looks like JSON" — a reply is
    # still a reply when the tool node has spoken earlier in the same turn.
    assert _reply_text() == REPLY
