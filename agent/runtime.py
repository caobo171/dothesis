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

import json
import os
import re
from pathlib import Path
from typing import Any, AsyncIterator


# Matches a single line at the end of an AI message that turns text into
# clickable cards. Examples the agent can emit:
#   [OPTIONS] Có | Không | Chỉnh sửa
#   [OPTIONS:paradigm] Định lượng | Định tính | Hỗn hợp
#   [OPTIONS:gap_ids multi] Gap 1 | Gap 2 | Gap 3
# `field_name` (the `:foo` part) tells the frontend which slice/field the
# user's pick maps to; defaults to "user_choice" when omitted. `multi`
# turns on multi-select (commits a comma-joined list on submit).
_OPTIONS_RE = re.compile(
    r"\[OPTIONS(?:\s*:\s*(?P<field>[a-zA-Z_][a-zA-Z0-9_]*))?(?P<multi>\s+multi)?\]\s*"
    r"(?P<options>.+)",
)


def _parse_options_marker(text: str) -> dict | None:
    """Pull the trailing `[OPTIONS] …` line out of an AI message and shape
    it into a `CardGridHint`. Returns None when no marker is present.

    Scans backward from the last non-empty line; the marker MUST be on its
    own line (we don't want to false-match prose that happens to contain
    the literal text `[OPTIONS]`). If multiple markers appear, only the
    last one wins — the agent should never emit more than one per turn.
    """
    if "[OPTIONS" not in text:
        return None
    for raw in reversed(text.rstrip().splitlines()):
        line = raw.strip()
        if not line:
            continue
        m = _OPTIONS_RE.fullmatch(line)
        if m is None:
            # First non-empty line from the bottom isn't a marker → done.
            return None
        labels = [s.strip() for s in m.group("options").split("|") if s.strip()]
        if not labels:
            return None
        return {
            "widget_type": "card_grid",
            "field_name": m.group("field") or "user_choice",
            "title": "",  # Empty title — the chat bubble above carries the question.
            "options": [{"value": lbl, "label": lbl} for lbl in labels],
            "multi_select": bool(m.group("multi")),
        }
    return None


# Foundational citations panel marker. The agent embeds a JSON payload
# between `[PAPERS]` and `[/PAPERS]` fences anywhere in its message; we
# extract it, shape it into a `PapersPanelHint`, and yield a `tool_calls`
# event for the frontend `PapersPanel` widget to render. The marker text
# itself is stripped on the client (MessageBubble) so the user only sees
# the panel.
#
# Why JSON inline rather than a tool call: the agent's response is already
# streaming as Markdown; switching to a tool call mid-stream would require
# wiring a `display_papers_panel` tool through deepagents, persist the
# payload twice (tool result + message), and pay an extra LLM turn. The
# inline marker is the same trick `[OPTIONS]` and ```mermaid``` use.
_PAPERS_RE = re.compile(
    r"\[PAPERS\]\s*(?P<payload>\{.*?\})\s*\[/PAPERS\]",
    re.DOTALL,
)


def _parse_papers_marker(text: str) -> dict | None:
    """Pull the first `[PAPERS] {json} [/PAPERS]` block out of `text` and
    shape it into a `PapersPanelHint`. Returns None when no marker is
    present or the payload is malformed.

    The agent should emit `widget_type` inside the JSON, but for ergonomics
    we'll inject it here if missing — so the agent only has to write
    `{camps: [...]}` and we fill in the rest.
    """
    if "[PAPERS]" not in text:
        return None
    m = _PAPERS_RE.search(text)
    if m is None:
        return None
    try:
        payload = json.loads(m.group("payload"))
    except json.JSONDecodeError:
        # Best-effort: a malformed payload is the agent's mistake, not a
        # crash-worthy event. The marker text will still be visible in
        # the message because the client only strips it when the parse
        # succeeds — that's a useful signal to the agent next turn.
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("camps"), list):
        return None
    payload.setdefault("widget_type", "papers_panel")
    return payload

from deepagents import create_deep_agent
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend

from agent.state import ProjectStateStore
from agent.tools.research import parse_reference, research_scout
from agent.tools.state_tools import make_state_tools
from agent.tools.stats import run_stats
from agent.tools.writing import make_writing_tools

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"

# Short on purpose: identity, the one hard pointer to the protocol skill,
# and the two UI-affordance conventions that the frontend depends on. The
# conventions are injected EVERY TURN here (rather than only in the skill
# file) because models routinely ignore instructions they only see after a
# skill-read, and `read_file("/skills/dothesis/SKILL.md")` is a per-session
# tool call the agent may skip entirely after the first turn — leaving the
# chat surface with no [OPTIONS] cards and no Mermaid diagrams. Domain
# behavior (M1–M5, state protocol) stays in the skill.
SYSTEM_PROMPT = """\
You are DoThesis, a thesis/research copilot.

# Protocol
Before doing ANY thesis work in a conversation, read the `dothesis` skill —
it defines the module map (M1–M5), the state protocol (read_slice /
commit_slice), and which module skill to read when. Mirror the user's
language (English or Vietnamese). Be warm, concrete, and proactive — propose,
then let the user decide.

## Attachments — `[ATTACHED]` prefix

When a user message begins with a line like:

    [ATTACHED] uploads/foo.pdf | uploads/data.csv

the user has just attached one or more files to the message. The files are
already mirrored into the project workspace at the listed paths — call
`read_file("uploads/foo.pdf.txt")` for the extracted text or
`parse_reference("uploads/foo.pdf")` for structured PDF metadata.

You MUST acknowledge attached files: briefly tell the user you've seen them
and what you'll do with each ("I'll read foo.pdf and pull the key claims;
data.csv looks like a dataset — want me to detect its schema for M4?"). Don't
just process the user's message text and ignore the attachments. Strip the
`[ATTACHED]` prefix from your reply — it's a wire-format marker, not
something the user wrote.

# UI affordances — ALWAYS use these when applicable

The chat surface renders Markdown. Two conventions turn walls of prose into
interactions:

## Clickable choices — `[OPTIONS]` marker

When you ask the user to pick among a small enumerable set (confirm / refine /
yes-no / which-gap / which-paradigm), END the message with one line:

    [OPTIONS] Có | Không | Chỉnh sửa

The frontend turns this into a row of clickable cards. Rules:
- The marker MUST be the last line of the message.
- Separate options with ` | ` (pipe). 2–6 options is the sweet spot.
- `[OPTIONS:field_name]` tags which slice field the pick maps to; defaults to
  `user_choice` when omitted.
- `[OPTIONS:gap_ids multi]` enables multi-select (e.g., picking gaps).

Use this whenever the next user reply has a small finite set of valid
choices. Do NOT use it for open-ended prompts ("Describe your sample…").

## Foundational citations panel — `[PAPERS] {...} [/PAPERS]`

When you want to show the user a structured list of seminal papers — e.g.,
the foundational citations behind an M2 literature review, or the sources
backing a methodology decision — embed a JSON payload between
`[PAPERS]` and `[/PAPERS]` fences. The frontend renders this as a card
panel with PDF thumbnails, clickable DOI links, page-cited quotes, and
per-paper actions (Open PDF, Cite, Flag). The marker text itself is
hidden in the chat bubble.

Shape:
```
[PAPERS]
{
  "title": "Foundational citations",
  "style": "APA 7",
  "indexed_count": 41,
  "camps": [
    {
      "id": "sor",
      "label": "STIMULUS-ORGANISM-RESPONSE",
      "papers": [
        {
          "id": "sun-2019",
          "author": "Sun, Y., Shao, X., Li, X., Guo, Y. & Nie, K.",
          "year": 2019,
          "title": "How live streaming influences purchase intentions in social commerce: An IT affordance perspective",
          "venue": "Electronic Commerce Research and Applications",
          "vol": "37",
          "doi": "10.1016/j.elerap.2019.100886",
          "cites": 612,
          "page": 41,
          "quote": "The live streaming context affords four IT affordances — visibility, metavoicing, guidance shopping, and trading — that map onto SOR stimulus.",
          "seminal": true
        }
      ]
    }
  ]
}
[/PAPERS]
```

Required: `camps[].label`, `camps[].papers[].id`, `papers[].author`,
`papers[].year`, `papers[].title`. Everything else is optional but you
should fill in `doi` (for the clickable title) and `quote` + `page`
(for the cited blockquote) whenever you have them. The user came for the
sources — surface them in this panel rather than as prose, and almost
never as raw URLs in the message text.

When you DON'T have real verified papers yet — when M2 hasn't run
research_scout — say so plainly, do not invent a panel.

## Diagrams — fenced ```mermaid``` blocks

For ANY visual concept — conceptual model, sequence of phases, research
flow, sampling design, analysis pipeline — emit a Mermaid block. The
frontend renders it as an SVG diagram. NEVER fall back to ASCII art or
prose "imagine boxes and arrows" — the user asked for a diagram, you
have a tool that draws them. Use it.

Example (M3 conceptual model):

```mermaid
flowchart LR
    SMU[Mạng xã hội] -->|H1: -| SA[Sự chú ý]
    SA -->|H2: +| AP[Học tập]
    SH[Thói quen học tập] -.->|H4: điều tiết| SA
    AD[Nhận thức xao nhãng] -.->|H5: điều tiết| SA
```

Supported types: flowchart, sequenceDiagram, classDiagram, stateDiagram,
erDiagram, gantt, mindmap, pie. Keep labels short — long node text wraps
awkwardly. When in doubt, draw it.

## Markdown gotchas to avoid

- NEVER write a line that's just `___` or 3+ underscores/dashes to indicate
  a "fill-in-the-blank" line. Markdown converts that to a horizontal rule
  that overflows the chat bubble. Use `[____]` (with brackets), `(điền…)`,
  or "(vui lòng ghi rõ: …)" instead.
- NEVER use `---` on its own line for the same reason — use bullet
  separation or a heading instead.
- NEVER use Unicode form characters like `☐ ☒ □ ✓` to fake a checkbox or
  radio button. They render at inconsistent sizes between fonts and look
  broken next to bullets. Just list the choices as plain bullets.

## Questionnaires & forms in chat — preview vs export

The chat is a PREVIEW surface, not a real form. Don't try to render
fill-in widgets inside it (checkboxes, fillable Likert tables) — they
always look ugly. Pick the right shape:

- **Single-answer item** (one question, N choices): list the question, then
  the choices as a Markdown TASK LIST so the frontend renders proper
  styled checkbox pills. Use `- [ ]` for unselected options. NEVER use
  Unicode `☐ ☒ □` or literal `[ ]` text — those render as broken glyphs.

  Example:
  > 1. Mỗi ngày bạn dành bao nhiêu thời gian cho mạng xã hội?
  >    - [ ] Dưới 1 giờ
  >    - [ ] 1–2 giờ
  >    - [ ] 2–3 giờ
  >    - [ ] Trên 4 giờ
  >    *(Chọn một đáp án)*

- **Likert-scale item** (N statements, all rated 1–5): list the statements
  numbered. Put the scale legend ABOVE the list once, NOT a 5-column
  table with `[ ]` cells per row. Multi-column tables wrap badly in chat
  and the `[ ]` markers look broken.

  Example:
  > **Thang đo Likert 5 điểm: 1 = Hoàn toàn không đồng ý ··· 5 = Hoàn toàn đồng ý**
  >
  > 1. Tôi thường xuyên kiểm tra mạng xã hội khi đang học.
  > 2. Tôi cảm thấy khó dừng khi đã bắt đầu.
  > 3. …

- **Finished thesis file**: when the user wants the complete thesis as a
  document — "viết luận văn", "đưa tôi bản thesis", "tạo file", "export" —
  call `export_docx()`. It auto-composes any missing chapters from M1–M4,
  renders DOCX + PDF, and surfaces download links in the Context store panel.
  Calling it IS the action — never redirect the user to a button instead, and
  never paste whole chapters into chat. On success, tell them the files are
  ready in the Context store panel.
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
        *make_writing_tools(store),
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
    attachments: list | None = None,
) -> AsyncIterator[dict]:
    """Run one user turn, yielding SSE-shaped events.

    Event vocabulary (matches the web client's existing SSE handling):
      {"type": "token", "text": str}          — assistant text delta
      {"type": "tool_start", "name": str, "args": dict}
      {"type": "tool_end", "name": str, "preview": str}
      {"type": "error", "message": str}
      {"type": "done"}

    `attachments` is a list of `agent.multimodal.Attachment` (kept as `list`
    here to avoid a circular import at module load). When non-empty, the
    user message is constructed via the provider-aware multimodal helper
    so the LLM sees the actual file bytes (Gemini inline for ≤20MB; File
    API URI for larger files), rather than just a path reference.
    """
    config = {"configurable": {"thread_id": thread_id}}
    if attachments:
        # Lazy import — multimodal.py pulls in google-genai which is heavy
        # and only needed when the user attached something.
        from agent.multimodal import build_user_message, detect_provider
        msg = build_user_message(user_text, attachments, detect_provider())
        payload = {"messages": [msg]}
    else:
        payload = {"messages": [{"role": "user", "content": user_text}]}

    # Diagnostic stderr beats — same idea as chat_v3.py's `[v3-emitter]`
    # diagnostics, but at the agent.astream layer. When a turn ends with
    # zero tokens / tool events the question is whether deepagents yielded
    # *anything*: an empty `messages` chunk (Gemini returned no text), an
    # `updates` chunk with no ToolMessages, or nothing at all (silent
    # short-circuit). Counting modes + types here pinpoints which.
    import sys as _sys
    _mode_counts = {"messages": 0, "updates": 0, "_other": 0}
    _msg_type_counts: dict[str, int] = {}
    _seen_any = False
    try:
        async for mode, chunk in agent.astream(
            payload, config=config, stream_mode=["messages", "updates"]
        ):
            _seen_any = True
            _mode_counts[mode] = _mode_counts.get(mode, 0) + 1
            if mode == "messages":
                msg, _meta = chunk
                # Log the chunk type + content preview so we can see
                # whether Gemini returned empty strings or no chunks at all.
                _tname = type(msg).__name__
                _msg_type_counts[_tname] = _msg_type_counts.get(_tname, 0) + 1
                _content = getattr(msg, "content", "")
                _preview_str = (
                    _content[:60] if isinstance(_content, str)
                    else f"<{type(_content).__name__}>"
                )
                if _msg_type_counts[_tname] <= 3:  # cap log spam
                    print(f"[agent.stream] messages chunk #{_msg_type_counts[_tname]} "
                          f"type={_tname} content={_preview_str!r}",
                          file=_sys.stderr, flush=True)
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
                            for tc in getattr(m, "tool_calls", None) or []:
                                if tc.get("name"):
                                    yield {
                                        "type": "tool_start",
                                        "name": tc["name"],
                                        "args": tc.get("args") or {},
                                    }
                            # Parse a `[OPTIONS] a | b | c` marker out of the
                            # AI message text and surface it as an interactive
                            # card grid. The agent learns this convention via
                            # the bootstrap skill — without it, every choice
                            # has to be typed instead of clicked.
                            content = getattr(m, "content", "")
                            if isinstance(content, str):
                                # Two marker shapes can ride on the same
                                # message: [OPTIONS] (clickable choices,
                                # always last line) and [PAPERS] (the
                                # foundational-citations panel, anywhere
                                # inline). When both are present, the
                                # papers panel wins — choices are usually a
                                # follow-up question the user can also type,
                                # but the papers panel carries the actual
                                # citation links the user came for.
                                hint = (
                                    _parse_papers_marker(content)
                                    or _parse_options_marker(content)
                                )
                                if hint is not None:
                                    yield {"type": "tool_calls", "payload": hint}
    except Exception as e:  # surface failures as events — never a dead stream
        import traceback as _tb
        print(f"\n=== agent.astream crashed in stream_turn (thread={thread_id}) ===",
              file=_sys.stderr, flush=True)
        _tb.print_exc(file=_sys.stderr)
        print("=== end traceback ===\n", file=_sys.stderr, flush=True)
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
    # End-of-stream telemetry — tells us whether the silent turn was caused
    # by zero chunks (deepagents returned nothing), or by chunks that
    # didn't translate to user-facing events (empty strings, non-AI types).
    print(f"[agent.stream] end seen_any={_seen_any} mode_counts={_mode_counts} "
          f"msg_types={_msg_type_counts}",
          file=_sys.stderr, flush=True)
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
