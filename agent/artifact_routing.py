"""Conservative artifact routing for state writes.

The model remains free to choose tools and work across modules.  This module
only supplies a canonical destination when the student's requested artifact is
unambiguous, and validates matching ``commit_slice`` calls.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage


@dataclass(frozen=True)
class WriteTarget:
    module: str
    key: str
    artifact: str


_ARTIFACT_PATTERNS: tuple[tuple[re.Pattern[str], WriteTarget], ...] = (
    (re.compile(
        r"\b(?:questionnaire|survey\s+instrument|instrument|"
        r"bộ\s+câu\s+hỏi|bo\s+cau\s+hoi|bảng\s+hỏi|bang\s+hoi)\b", re.I),
     WriteTarget("M3", "instrument", "questionnaire")),
    (re.compile(
        r"\b(?:conceptual\s+model|research\s+model|mô\s+hình\s+(?:nghiên\s+cứu|"
        r"khái\s+niệm)|mo\s+hinh\s+(?:nghien\s+cuu|khai\s+niem))\b", re.I),
     WriteTarget("M3", "conceptual_model", "conceptual_model")),
    (re.compile(r"\b(?:hypotheses?|giả\s+thuyết|gia\s+thuyet)\b", re.I),
     WriteTarget("M3", "hypotheses", "hypotheses")),
    (re.compile(
        r"\b(?:methodology|research\s+design|phương\s+pháp\s+nghiên\s+cứu|"
        r"phuong\s+phap\s+nghien\s+cuu)\b", re.I),
     WriteTarget("M3", "methodology", "methodology")),
    (re.compile(
        r"\b(?:analysis\s+results?|smartpls\s+results?|kết\s+quả\s+phân\s+tích|"
        r"ket\s+qua\s+phan\s+tich)\b", re.I),
     WriteTarget("M4", "analysis_results", "analysis_results")),
    (re.compile(
        r"\b(?:research\s+gaps?|literature\s+gaps?|khoảng\s+trống\s+nghiên\s+cứu|"
        r"khoang\s+trong\s+nghien\s+cuu)\b", re.I),
     WriteTarget("M2", "research_gaps", "research_gaps")),
    (re.compile(
        r"\b(?:literature\s+(?:review|sources?)|tổng\s+quan\s+tài\s+liệu|"
        r"tong\s+quan\s+tai\s+lieu)\b", re.I),
     WriteTarget("M2", "literature_sources", "literature")),
    (re.compile(
        r"\b(?:research\s+questions?|câu\s+hỏi\s+nghiên\s+cứu|"
        r"cau\s+hoi\s+nghien\s+cuu)\b", re.I),
     WriteTarget("M1", "research_questions", "research_questions")),
    (re.compile(
        r"\b(?:research\s+title|thesis\s+topic|đề\s+tài|de\s+tai)\b", re.I),
     WriteTarget("M1", "research_title", "topic")),
    (re.compile(
        r"\b(?:chapters?|chapter\s+\d+|chương|chuong|final\s+(?:draft|sections?)|"
        r"thesis\s+draft)\b", re.I),
     WriteTarget("M5", "final_sections", "chapters")),
)

_SAVE_LIKE = re.compile(
    r"\b(?:save|commit|persist|lưu|luu|ghi\s+vào|ghi\s+vao|"
    r"cập\s+nhật|cap\s+nhat)\b",
    re.I,
)
_MARKER = "[WRITE TARGET]"


def _explicit_target(text: str) -> WriteTarget | None:
    for pattern, target in _ARTIFACT_PATTERNS:
        if pattern.search(text or ""):
            return target
    return None


def resolve_write_target(
    text: str,
    recent_messages: Sequence[str] = (),
) -> WriteTarget | None:
    """Resolve an explicit artifact, or inherit one for a save-like follow-up.

    ``recent_messages`` is chronological.  Inheritance scans newest-first and
    stops at the first unambiguous artifact.
    """
    current = _explicit_target(text)
    if current is not None:
        return current
    if not _SAVE_LIKE.search(text or ""):
        return None
    for message in reversed(recent_messages):
        inherited = _explicit_target(message)
        if inherited is not None:
            return inherited
    return None


def write_target_marker(target: WriteTarget) -> str:
    payload = {
        "module": target.module,
        "key": target.key,
        "artifact": target.artifact,
    }
    return f"{_MARKER} {json.dumps(payload, separators=(',', ':'))}"


def parse_write_target(text: str) -> WriteTarget | None:
    for line in (text or "").splitlines():
        if not line.startswith(f"{_MARKER} "):
            continue
        try:
            payload = json.loads(line[len(_MARKER) + 1:])
            module = str(payload["module"])
            key = str(payload["key"])
            artifact = str(payload["artifact"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if module not in {"M1", "M2", "M3", "M4", "M5"} or not key:
            return None
        return WriteTarget(module=module, key=key, artifact=artifact)
    return None


def validate_tool_call(
    target: WriteTarget | None,
    tool_name: str,
    args: dict[str, Any],
) -> str | None:
    """Return a corrective error for a misrouted state write."""
    if target is None or tool_name != "commit_slice":
        return None
    module = str(args.get("module") or "")
    writes = args.get("writes")
    keys = set(writes) if isinstance(writes, dict) else set()
    if module == target.module and target.key in keys:
        return None
    return (
        f"artifact_routing_mismatch — {target.artifact} must be saved to "
        f"{target.module}.{target.key}; retry commit_slice in this turn with "
        f'module="{target.module}" and writes containing "{target.key}". '
        "The current project focus is advisory and must not override this target."
    )


class ArtifactRoutingMiddleware(AgentMiddleware):
    """Validate targeted state writes without constraining tool selection."""

    @staticmethod
    def _routing_error(request) -> ToolMessage | None:
        target = None
        messages = (request.state or {}).get("messages", [])
        for message in reversed(messages):
            if getattr(message, "type", None) != "human":
                continue
            target = parse_write_target(str(getattr(message, "content", "")))
            if target is not None:
                break

        call = request.tool_call
        error = validate_tool_call(
            target,
            str(call.get("name") or ""),
            call.get("args") if isinstance(call.get("args"), dict) else {},
        )
        if error is None:
            return None
        return ToolMessage(
            content=json.dumps({
                "error": error,
                "expected": {
                    "module": target.module,
                    "key": target.key,
                    "artifact": target.artifact,
                },
            }),
            tool_call_id=str(call.get("id") or ""),
            name=str(call.get("name") or ""),
            status="error",
        )

    def wrap_tool_call(self, request, handler):
        error = self._routing_error(request)
        return error if error is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        error = self._routing_error(request)
        return error if error is not None else await handler(request)
