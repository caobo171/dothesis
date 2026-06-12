"""DoThesis deep-agent runtime.

Builds the skills-driven agent (deepagents.create_deep_agent) and exposes a
streaming turn API designed for the app's SSE transport: every event the chat
frontend needs (token deltas, tool activity, skill reads, errors, done) comes
out of `stream_turn` as a plain dict the FastAPI layer can write straight to
the SSE channel — long turns (the 30–90s M2 scout, full-chapter writes) stay
visibly alive instead of timing out a request/response cycle.

Scoping (the two invariants from the user):
- The context_store is PROJECT-scoped: `ProjectStateStore(project_dir)` is
  shared by every thread/session in the project.
- The conversation is THREAD-scoped: `thread_id` keys the LangGraph
  checkpointer, so multiple long-running chat threads can coexist over the
  same shared state.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, AsyncIterator

from deepagents import create_deep_agent
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend

from agent.state import ProjectStateStore
from agent.tools.research import parse_reference, research_scout
from agent.tools.state_tools import make_state_tools
from agent.tools.stats import run_stats
from agent.tools.writing import export_docx, write_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"

# Short on purpose: identity + the one hard pointer. Domain behavior lives in
# the skills (progressive disclosure) — duplicating it here would just fight
# them and bloat every turn.
SYSTEM_PROMPT = """\
You are DoThesis, a thesis/research copilot. Before doing ANY thesis work in a
conversation, read the `dothesis` skill — it defines the module map (M1–M5),
the state protocol (read_slice / commit_slice), and which module skill to read
when. Mirror the user's language (English or Vietnamese). Be warm, concrete,
and proactive — propose, then let the user decide.
"""


def build_agent(
    project_dir: str | Path,
    *,
    model: Any | None = None,
    checkpointer: Any | None = None,
    store: ProjectStateStore | None = None,
):
    """Create the deep agent bound to one project.

    `store` defaults to the file-backed store in project_dir (CLI spike);
    the api passes a DB-backed subclass so commits land in Postgres while
    project_dir stays the file workspace (uploads, exports).
    """
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    store = store or ProjectStateStore(project_dir)

    # /skills/ is read-only domain knowledge from the repo; everything else
    # (uploads, scratch, exports) lives in the project directory. The state
    # file is deliberately NOT exposed as a writable file — commit_slice is
    # the only write path (the file lands in project_dir via the store).
    # virtual_mode=True: virtual path semantics so the /skills/ route works
    # and absolute-path / '..' escapes from root_dir are refused. (Not a
    # sandbox — script execution stays off; see architecture §7 risk 4.)
    backend = CompositeBackend(
        default=FilesystemBackend(root_dir=project_dir, virtual_mode=True),
        routes={"/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True)},
    )

    if model is None:
        model = _default_model()

    tools = [
        *make_state_tools(store),
        research_scout,
        parse_reference,
        run_stats,
        write_pipeline,
        export_docx,
    ]

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        skills=["/skills/"],
        backend=backend,
        checkpointer=checkpointer,
        name="dothesis",
    )


def _default_model():
    """Claude when a key is configured, else Gemini.

    This deployment currently runs the whole engine on Gemini
    (ANTHROPIC_API_KEY is declared-but-empty in .env), so Gemini is the
    working default; the architecture's preferred model is Claude and it
    takes over automatically once a key lands.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=os.getenv("DOTHESIS_AGENT_MODEL", "claude-sonnet-4-6"),
            max_tokens=8_000,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=os.getenv("DOTHESIS_AGENT_MODEL", "gemini-2.5-flash"),
        temperature=0.4,
    )


async def stream_turn(
    agent: Any,
    thread_id: str,
    user_text: str,
) -> AsyncIterator[dict]:
    """Run one user turn, yielding SSE-shaped events.

    Event vocabulary (matches the web client's existing SSE handling):
      {"type": "token", "text": str}          — assistant text delta
      {"type": "tool_start", "name": str, "args": dict}
      {"type": "tool_end", "name": str, "preview": str}
      {"type": "error", "message": str}
      {"type": "done"}
    """
    config = {"configurable": {"thread_id": thread_id}}
    payload = {"messages": [{"role": "user", "content": user_text}]}

    try:
        async for mode, chunk in agent.astream(
            payload, config=config, stream_mode=["messages", "updates"]
        ):
            if mode == "messages":
                msg, _meta = chunk
                for ev in _events_from_message(msg):
                    yield ev
            elif mode == "updates":
                # Node-level updates carry completed ToolMessages (results)
                # AND the planning AIMessages that issued the tool_calls.
                for node_payload in chunk.values():
                    raw_msgs = (node_payload or {}).get("messages", []) or []
                    # deepagents middleware (patch_tool_calls, filesystem
                    # eviction) returns `{"messages": Overwrite([...])}` so
                    # the add_messages reducer is bypassed. Unwrap to .value
                    # so the rest of the loop sees the underlying list.
                    from langgraph.types import Overwrite as _Overwrite
                    if isinstance(raw_msgs, _Overwrite):
                        raw_msgs = raw_msgs.value or []
                    for m in raw_msgs:
                        m_type = getattr(m, "type", None)
                        if m_type == "tool":
                            yield {
                                "type": "tool_end",
                                "name": getattr(m, "name", "") or "",
                                "preview": _preview(m.content),
                            }
                        else:
                            # Why also yield tool_start here: the messages-
                            # mode stream only carries tool_calls on chunks
                            # the model streams as AIMessageChunk. The
                            # deepagents middleware path emits tool decisions
                            # as a complete AIMessage attached to a node-
                            # update payload, NOT as streamed chunks. Without
                            # surfacing tool_calls from updates mode too, the
                            # UI sees `✓ tool_end` flashes with no preceding
                            # `⚙ tool_start` — the banner stays on a typing
                            # dot for the whole tool execution window
                            # (research_scout is 30–90s of silent waiting).
                            for tc in getattr(m, "tool_calls", None) or []:
                                if tc.get("name"):
                                    yield {
                                        "type": "tool_start",
                                        "name": tc["name"],
                                        "args": tc.get("args") or {},
                                    }
    except Exception as e:  # surface failures as events — never a dead stream
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
    yield {"type": "done"}


def _events_from_message(msg: Any):
    """Token deltas + tool-call starts from a streamed message chunk."""
    if getattr(msg, "type", None) not in ("AIMessageChunk", "ai", "AIMessage"):
        # LangChain v1 chunks report type "AIMessageChunk"; be permissive.
        if not type(msg).__name__.startswith("AIMessage"):
            return
    content = msg.content
    if isinstance(content, str):
        if content:
            yield {"type": "token", "text": content}
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                yield {"type": "token", "text": block["text"]}
    for tc in getattr(msg, "tool_calls", None) or []:
        if tc.get("name"):
            yield {"type": "tool_start", "name": tc["name"], "args": tc.get("args") or {}}


def _preview(content: Any, limit: int = 200) -> str:
    s = content if isinstance(content, str) else str(content)
    return s[:limit] + ("…" if len(s) > limit else "")
