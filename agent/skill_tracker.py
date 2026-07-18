"""Mechanical skill-adherence nudge (boundary hardening, gap 3).

"Read the module's skill before acting on that module" was instruction-only.
This turns it into a state machine the model passes through ONCE: the first
commit_slice(module) in a session with no recorded read of that module's skill
returns a correctable nudge; the nudge is recorded so a repeat proceeds even if
the model still doesn't read (no deadlock — the transferable core of opencode's
read-before-edit, kept fail-open for legitimate flow).

Process-local by design: worst case after an API restart is one extra nudge —
benign, deterministic, no store schema change.
"""
from __future__ import annotations

from typing import Dict, Set

# module → its skill directory (M1–M5 only; root/bootstrap/defense skills are
# not module-gated).
_MODULE_SKILL: Dict[str, str] = {
    "M1": "dothesis-m1-topic", "M2": "dothesis-m2-literature", "M3": "dothesis-m3-design",
    "M4": "dothesis-m4-analysis", "M5": "dothesis-m5-writing",
}

_registry: Dict[str, Dict[str, Set[str]]] = {}
_armed: Set[str] = set()


def arm(project_key) -> None:
    """Enable nudging for a project. Called when the skill-reading channel exists
    (build_agent wraps the /skills/ backend in RecordingBackend). Until armed,
    should_nudge is inert — so direct/tool tests and any non-agent caller that
    can't read skills is never nudged (there'd be no way to satisfy it)."""
    _armed.add(str(project_key))


def _slot(project_key) -> Dict[str, Set[str]]:
    return _registry.setdefault(str(project_key), {"read": set(), "nudged": set()})


def note_read(project_key, path) -> None:
    """Record that a module skill was read (from a /skills/.../SKILL.md path)."""
    p = str(path or "")
    for module, skill_dir in _MODULE_SKILL.items():
        if f"/{skill_dir}/" in p or p.endswith(f"/{skill_dir}") or skill_dir in p.split("/"):
            _slot(project_key)["read"].add(module)
            return


def skill_path(module: str) -> str:
    return f"/skills/{_MODULE_SKILL[module]}/SKILL.md"


def should_nudge(project_key, module: str) -> bool:
    """True exactly ONCE per (project, module): the module has a skill, it was
    not read, and we haven't nudged for it yet. Records the nudge on True so the
    next commit proceeds (never a deadlock)."""
    if module not in _MODULE_SKILL or str(project_key) not in _armed:
        return False
    slot = _slot(project_key)
    if module in slot["read"] or module in slot["nudged"]:
        return False
    slot["nudged"].add(module)
    return True


def reset(project_key=None) -> None:
    """Test/maintenance helper: clear one project's or all tracking state."""
    if project_key is None:
        _registry.clear()
        _armed.clear()
    else:
        _registry.pop(str(project_key), None)
        _armed.discard(str(project_key))


class RecordingBackend:
    """Thin decorator over a read backend: every read of a module SKILL.md is
    recorded via note_read, then delegated unchanged (same bytes, same virtual
    refusals). Only the `read` hook is observed; everything else passes through."""

    def __init__(self, inner, project_key):
        self._inner = inner
        self._project_key = str(project_key)
        arm(project_key)      # the skill-reading channel now exists → nudging on

    def read(self, file_path: str, *args, **kwargs):
        try:
            note_read(self._project_key, file_path)
        except Exception:
            pass  # observation must never break a read
        return self._inner.read(file_path, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)
