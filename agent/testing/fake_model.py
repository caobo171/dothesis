"""Scripted chat model for the E2E harness (DOTHESIS_E2E_MOCK=1).

Replays web/e2e/fixtures/*.json. Only the COMPLETION is fake: emitted
tool_calls are real LangChain tool-call blocks that deepagents executes
against real tools (commit_slice -> DbProjectStateStore -> Postgres,
export_docx -> engine -> S3). Responses carry the real UI marker syntax
([OPTIONS], [PAPERS], {{cite: ...}}) so the frontend renders exactly as in
production.

Matching is stateless and deterministic — no hidden counters:
- scenario: entry regex re.search'd against the FIRST HumanMessage (the
  runtime prepends a [PROJECT STATE] header, so entries are never anchored);
- step index: number of AIMessages already in the history. One step == one
  completion, so a tool_calls step is followed by the model being called
  again with ToolMessages appended -> that call consumes the NEXT step.
- any mismatch raises FixtureError: stream_turn converts exceptions into an
  SSE error event, which the web shows as the error-bubble testid — the
  Playwright assertion then fails with the mismatch text in the trace,
  instead of the test silently passing down a wrong path.

Layering: agent/ must never import app/ — this module uses only
langchain_core + stdlib.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, AsyncIterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr


class FixtureError(RuntimeError):
    """The conversation diverged from the scripted fixture."""


def _text_of(content: Any) -> str:
    # Same shape-tolerance as runtime._text_content: providers (and our own
    # chunks) may carry either a plain string or a list of content parts.
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


class FakeChatModel(BaseChatModel):
    fixtures_dir: str
    _scripts: list[dict] | None = PrivateAttr(default=None)

    # -- construction --------------------------------------------------------

    @classmethod
    def from_fixtures_dir(cls, path: str) -> "FakeChatModel":
        return cls(fixtures_dir=path)

    def _load_scripts(self) -> list[dict]:
        if self._scripts is None:
            scripts: list[dict] = []
            # Sorted-glob so scenario resolution order is deterministic when
            # (buggy) fixtures have overlapping entries.
            for p in sorted(Path(self.fixtures_dir).glob("*.json")):
                data = json.loads(p.read_text(encoding="utf-8"))
                data["_entry_re"] = re.compile(data["entry"])
                scripts.append(data)
            self._scripts = scripts
        return self._scripts

    # -- LangChain plumbing ---------------------------------------------------

    @property
    def _llm_type(self) -> str:
        return "dothesis-e2e-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeChatModel":
        # deepagents binds its tool set at agent build. The fixture decides
        # which calls to emit, so binding is a deliberate no-op (the
        # BaseChatModel default raises NotImplementedError).
        return self

    # -- scripted matching ----------------------------------------------------

    def _next_message(self, messages: list[BaseMessage]) -> AIMessage:
        first_human = next(
            (m for m in messages if getattr(m, "type", None) == "human"), None)
        if first_human is None:
            raise FixtureError("no HumanMessage in the conversation")
        first_text = _text_of(first_human.content)

        script = next(
            (s for s in self._load_scripts() if s["_entry_re"].search(first_text)),
            None)
        if script is None:
            raise FixtureError(
                f"no fixture entry matches first user message: {first_text[:200]!r}")

        step_idx = sum(1 for m in messages if getattr(m, "type", None) == "ai")
        steps = script["steps"]
        if step_idx >= len(steps):
            raise FixtureError(
                f"scenario {script['scenario']!r} exhausted: completion "
                f"#{step_idx + 1} requested but only {len(steps)} steps scripted")
        step = steps[step_idx]

        expect = step.get("expect_user")
        if expect:
            last = next(
                (m for m in reversed(messages)
                 if getattr(m, "type", None) in ("human", "tool")), None)
            last_text = _text_of(last.content) if last is not None else ""
            if not re.search(expect, last_text):
                raise FixtureError(
                    f"scenario {script['scenario']!r} step {step_idx}: expected "
                    f"latest human/tool message to match {expect!r}, got: "
                    f"{last_text[:300]!r}")

        tool_calls = [
            {
                "name": tc["name"],
                "args": tc.get("args") or {},
                "id": f"e2e-{step_idx}-{i}",
                "type": "tool_call",
            }
            for i, tc in enumerate(step.get("tool_calls") or [])
        ]
        return AIMessage(content=step.get("response") or "", tool_calls=tool_calls)

    # -- generation -----------------------------------------------------------

    def _generate(self, messages: list[BaseMessage], stop: Any = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=self._next_message(messages))])

    async def _astream(self, messages: list[BaseMessage], stop: Any = None,
                       run_manager: Any = None,
                       **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        # Stream in small text chunks so the web's token-delta path
        # (streaming-cursor, incremental markdown) is exercised like
        # production, then a final chunk carrying any tool calls.
        msg = self._next_message(messages)
        text = msg.content if isinstance(msg.content, str) else _text_of(msg.content)
        for i in range(0, len(text), 48):
            piece = text[i:i + 48]
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=piece))
            if run_manager:
                await run_manager.on_llm_new_token(piece, chunk=chunk)
            yield chunk
        if msg.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": tc["name"],
                        "args": json.dumps(tc["args"]),
                        "id": tc["id"],
                        "index": i,
                        "type": "tool_call_chunk",
                    }
                    for i, tc in enumerate(msg.tool_calls)
                ],
            ))
