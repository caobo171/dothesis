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


def _parse_export_artifacts(content: Any) -> dict | None:
    """Shape an export_docx tool result into an `export_artifacts` widget hint.

    The tool returns JSON like {"ok": true, "artifacts": [{kind, download_url,
    size_bytes, …}]}. We surface those as a download card in the chat message.
    Returns None unless the result is a successful export with artifacts.
    """
    if not isinstance(content, str):
        return None
    try:
        data = json.loads(content)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    artifacts = data.get("artifacts") or []
    if not artifacts:
        return None
    return {"widget_type": "export_artifacts", "artifacts": artifacts}


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

from agent.preflight import make_preflight_tool
from agent.state import MODULES, ProjectStateStore
from agent.tools.forms import make_google_form_script
from agent.tools.instrument import (  # F7: Questionnaire Doctor + sampling plan
    audit_instrument,
    consent_notice,
    make_sampling_plan_tool,
)
from agent.tools.output_parse import parse_output_table, parse_smartpls_export
from agent.tools.research import parse_reference, quick_sources, research_scout
from agent.tools.state_tools import make_state_tools
from agent.tools.stats import check_thresholds, run_stats
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

## Project state — `[PROJECT STATE]` line is authoritative

A user message may be preceded by a line like:

    [PROJECT STATE] focus=M4 | M1:done M2:done M3:done M4:done M5:needs_review

This is the REAL per-module status from the state store, injected fresh every
turn. It overrides anything you remember. Rules:
- When the user asks about progress, report THESE statuses verbatim — never
  recite a status list from memory.
- A module is `done` ONLY if it shows `done` here. NEVER tell the user a module
  is done/complete when this line says `needs_review`, `in_progress`, or
  `locked`.
- Saying "I'll mark M5 done" does NOTHING on its own. To change a status you
  MUST call `commit_slice(module, …, confirm_done=True)` and it must succeed
  (it now refuses to mark a module done if its slice is empty). After it
  returns, the status line on the next turn reflects the change.
- If the user says a module looks good but its slice has no committed content,
  do the work and `commit_slice` it — don't just declare it done.
- Strip the `[PROJECT STATE]` marker from your reply — it's a wire-format
  marker, not something the user wrote.
- The `[NEXT]` line (when present, right after `[PROJECT STATE]`) is the single
  most useful next step, computed from real project state. Unless the user
  redirects, CLOSE every turn by leading toward it: name what to do next and
  why, and offer its options with the `[OPTIONS]` marker. Never invent a
  different "next step" than the one derived. Strip `[NEXT]` from your reply too.

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

# Answer formatting — make every substantive reply scannable

Default to a polished, briefing-style layout (like a good AI overview):
- Open with ONE short sentence that frames the answer.
- Break the body into sections with `##` headings (short, plain). One idea per section.
- Keep paragraphs to 2–4 sentences. Use bullet lists for parallel points, and
  **bold the lead term** at the start of each bullet when listing factors.
- Leave a blank line between blocks (paragraphs, headings, lists, tables) so
  sections breathe.
Skip this only for a genuinely one-line answer.

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

For early/topic-stage grounding — before M2's full research_scout has run —
use `quick_sources` to fetch a few real papers so factual or landscape claims
carry citations from the very first message.

HARD RULE — surfacing what you fetched is mandatory: whenever `quick_sources`
(or `research_scout`) returns sources, you MUST render them in a `[PAPERS]`
panel in that same reply, AND cite them inline with `{{cite}}` pills (see
"Grounding" below) next to the claims they support. NEVER call the tool and then
answer without showing the papers — fetching sources but not displaying them is
a failure. Never make an ungrounded landscape claim. When the tool returns
nothing real, say so plainly and do not invent a panel.

## Grounding — inline source pills `{{cite: label | title | url}}`

Ground every factual / empirical / landscape claim with an inline source pill,
placed immediately after the sentence it supports (Google AI-Overview style):

    Fasting shifts the body from glucose to ketones for fuel. {{cite: Jeong 2025 | Study of Beauty Consumer Behavior on Social Media | https://doi.org/10.52660/jksc.2025.31.1.120}}

Exactly three pipe-separated fields:
  1. `label` — short pill text the user sees (e.g. "Jeong 2025", "WHO", a domain)
  2. `title` — full source title (shown on hover)
  3. `url`   — a REAL link: a DOI (https://doi.org/…) or a web URL

Where the grounding comes from (module-aware):
- **M2 and onward** → cite the project's RESEARCHED PAPERS. Use the
  `literature_sources` you committed: author+year as `label`, the real `title`,
  and the DOI as `url`. Do not cite random web pages here.
- **Before M2 (M1 / early topic research)** → you MAY cite real WEB sources
  returned by `quick_sources` / `research_scout`, but PREFER a paper whenever one
  is available. A topic-stage claim still needs grounding — never leave it bare.

Rules:
- Put pills inline next to the claim, not as a list at the end. 2–3 pills in a
  row is fine when several sources back one claim.
- NEVER fabricate a citation, title, or URL. Only cite sources you actually
  fetched, or papers in the project. No real source → state the claim cautiously
  with no pill; don't fake one.
- The `[PAPERS]` panel (full bibliography) and `{{cite}}` pills (inline
  grounding) complement each other — use both when you've surfaced papers.

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
- Math (`$…$` / `$$…$$`) is ONLY for real mathematical notation — numbers,
  Greek, operators, equations (e.g. `$N \\ge 140$`, `$\\beta = 0.37$`,
  `$$YD = \\beta_1 X_1 + \\beta_2 X_2$$`). NEVER wrap plain words or labels in
  `\\text{}`, and NEVER build a text flow with `\\longrightarrow` /
  `\\rightarrow` — write a normal arrow `→` in prose, or draw a ```mermaid```
  flowchart. Never put a raw `&`, `%`, `#`, or `_` inside math or `\\text{}` —
  they break the math renderer and show as broken red source.

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
        quick_sources,
        research_scout,
        parse_reference,
        run_stats,
        # F8: output sanity layer — classify pasted result tables (loadings/AVE/
        # CR/HTMT/VIF) against thresholds + flag suspiciously-perfect data.
        check_thresholds,
        # F13: turn a results EXPORT (SmartPLS/SPSS HTML/xlsx) or a SCREENSHOT into
        # {table_kind, rows} that feed check_thresholds. Both take a workspace path.
        parse_smartpls_export,
        parse_output_table,
        # F8: methods pre-flight — the M3->M4 readiness audit (advisory). Bound
        # to the store so the agent can run it before kicking off M4 analysis.
        make_preflight_tool(store),
        make_google_form_script,
        # F7: Questionnaire Doctor — deterministic instrument lint before
        # fielding (double-barreled/leading items, reverse-coded coverage,
        # attention checks, scale-provenance skeleton). Pure, no store needed.
        audit_instrument,
        # F7: sampling plan — defensible target n + timeline from method/model
        # size. Store-bound so it persists the plan to the M3 sample_plan key
        # (shares the power helper with F8's methods pre-flight).
        make_sampling_plan_tool(store),
        # F7: informed-consent / data-privacy preamble generator (bilingual) to
        # open a survey with before fielding. Pure, no store needed.
        consent_notice,
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
    # E2E harness hook (docs/superpowers/specs/2026-07-08-e2e-testing-design.md).
    # This is the single model factory for the chat agent (build_agent falls
    # here whenever no model is passed — the api's chat_v3._get_agent never
    # passes one), so one guard mocks every turn. Everything downstream of
    # the completion — deepagents loop, tools, store, DB — stays real.
    if os.getenv("DOTHESIS_E2E_MOCK") == "1":
        from agent.testing.fake_model import FakeChatModel
        return FakeChatModel.from_fixtures_dir(os.environ["DOTHESIS_E2E_FIXTURES_DIR"])
    if os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=os.getenv("DOTHESIS_AGENT_MODEL", "claude-sonnet-4-6"),
            max_tokens=8_000,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI
    # Default to gemini-3.5-flash (Gemini 3 family): stronger tool-use /
    # instruction-following than 2.5-flash, so the agent reliably emits the
    # [OPTIONS]/[PAPERS] UI markers the chat surface depends on. The hardcoded
    # default matches DOTHESIS_AGENT_MODEL in .env so the model stays 3.5 even
    # when the env var is absent (tests, CLI, a fresh deploy).
    return ChatGoogleGenerativeAI(
        model=os.getenv("DOTHESIS_AGENT_MODEL", "gemini-3.5-flash"),
        temperature=0.4,
    )


def _state_header(store: ProjectStateStore | None) -> str:
    """One-line authoritative status snapshot prepended to the user turn.

    The model routinely confabulates module status (e.g. printing "M1–M5 all
    done" while the store says M5 needs_review). Injecting the real focus +
    status every turn — same rationale as the every-turn UI-convention block —
    gives it ground truth it can't ignore. Errs silent: a load failure just
    omits the header rather than breaking the turn.
    """
    if store is None:
        return ""
    try:
        state = store.load()
    except Exception:
        return ""
    status = state.get("status") or {}
    if not status:
        return ""
    pairs = " ".join(f"{m}:{status.get(m, 'locked')}" for m in MODULES)
    header = f"[PROJECT STATE] focus={state.get('focus')} | {pairs}"
    # Append the single next action so the model leads from ground truth every
    # turn (same rationale as the state line: it can't narrate its own position).
    try:
        from agent.roadmap import next_action  # local import: avoid load cycle
        na = next_action(state)
        if na:
            header += (f"\n[NEXT] {na['module']}/{na.get('substep') or '-'} — "
                       f"{na['title']} :: {na['why']}")
    except Exception:
        pass  # a roadmap hiccup must never break the turn
    return header


async def stream_turn(
    agent: Any,
    thread_id: str,
    user_text: str,
    attachments: list | None = None,
    store: ProjectStateStore | None = None,
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
    # Prepend the authoritative status snapshot so the agent can't drift from
    # real state. Goes on the user turn (like [ATTACHED]) so it rides through
    # the multimodal path too.
    header = _state_header(store)
    user_text = f"{header}\n{user_text}" if header else user_text
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
                            _tool_name = getattr(m, "name", "") or ""
                            yield {
                                "type": "tool_end",
                                "name": _tool_name,
                                "preview": _preview(m.content),
                            }
                            # When the export tool succeeds, surface its
                            # artifacts as a download card in the chat message
                            # (Claude-artifact style) — not just the Context
                            # store panel. Parsed from the tool's JSON result.
                            if _tool_name == "export_docx":
                                hint = _parse_export_artifacts(m.content)
                                if hint is not None:
                                    yield {"type": "tool_calls", "payload": hint}
                        else:
                            # Token usage for cost metering. Gemini surfaces
                            # usage_metadata on the completed AIMessage in the
                            # updates stream; sum across every LLM step in the
                            # turn so the per-response cost reflects tool loops.
                            _usage = getattr(m, "usage_metadata", None)
                            if _usage:
                                yield {
                                    "type": "usage",
                                    "input_tokens": int(_usage.get("input_tokens", 0) or 0),
                                    "output_tokens": int(_usage.get("output_tokens", 0) or 0),
                                }
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
                            # Normalize content to text FIRST. Gemini 3.x
                            # (gemini-3.5-flash) returns content as a LIST of
                            # parts ([{type:"text",...}, thinking blocks]) rather
                            # than a plain string like 2.5-flash. Parsing only the
                            # str case silently dropped [OPTIONS]/[PAPERS] markers
                            # on Gemini 3 → no clickable choice cards. Join the
                            # text parts so markers are found regardless of model.
                            content = _text_content(getattr(m, "content", ""))
                            if content:
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


def _text_content(content: Any) -> str:
    """Flatten an LLM message's content to plain text.

    2.5-flash returns a string; Gemini 3.x (3.5-flash) returns a list of
    content parts ({type:"text",text:…} plus thinking/signature blocks). Join
    the text parts so downstream marker parsing ([OPTIONS], [PAPERS]) and any
    text inspection works the same across both shapes. Non-text blocks
    (thinking) are skipped — they're never shown to the user.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


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
