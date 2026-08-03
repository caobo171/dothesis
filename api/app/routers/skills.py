"""Skill catalogue — what the agent can actually do, read from the skills tree.

The chat picker used to offer six "expert personas" defined in
web/app/lib/experts.ts, which its own docstring admitted were prompt prefixes:
"biases the agent's response by prefixing the user message with a persona
directive — no backend change". They changed the VOICE, not the capability,
while the real capabilities — the SKILL.md files agent/runtime.py hands the deep
agent via `skills=["/skills/"]` — had no entry point at all. Humanize was the
clearest casualty: a fully written skill with no way for a student to ask for it.

The list is derived from the directory rather than duplicated in the frontend on
purpose. A hardcoded copy is the same drift class as the logo mark that only
updated on three of four surfaces: adding a skill would silently not appear, and
deleting one would leave a button that invokes nothing.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import current_user
from ..jwt_auth import AuthedBody
from ..models import User

router = APIRouter(tags=["skills"])

# repo_root/skills — api/app/routers/skills.py is four levels down.
_SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"

# Module skills are deliberately NOT offered in the picker. The agent already
# selects them from `focus`, and the left rail already navigates M1-M5 — listing
# them again would make the picker read as a duplicate of the sidebar rather
# than as "things I can ask for that I couldn't otherwise".
_MODULE_SKILL_RE = re.compile(r"^dothesis-m[1-5]-")

# The umbrella skill the agent always has; not a user-pickable action.
_HIDDEN = {"dothesis", "dothesis-bootstrap"}

# Which module each cross-cutting skill is most relevant to, for the
# "Suggested for M4" grouping the picker renders. Kept here rather than in the
# SKILL.md frontmatter because it is a UI affordance, not part of the skill
# contract the agent reads.
_SUGGESTED_FOR: dict[str, list[str]] = {
    "dothesis-humanize": ["M5"],
    "dothesis-defense": ["M5"],
    # The QuillBot-shaped writing tools. All four act on prose that already
    # exists, so they surface alongside M5; paraphrase also earns M2, where
    # students are restating sources and are most likely to over-copy.
    "dothesis-grammar": ["M5"],
    "dothesis-paraphrase": ["M2", "M5"],
    "dothesis-writing-rhythm": ["M5"],
    "dothesis-plagiarism": ["M2", "M5"],
}


class SkillOut(BaseModel):
    id: str
    name: str
    description: str
    suggested_for: list[str] = []


class SkillListOut(BaseModel):
    skills: list[SkillOut]


def _parse_frontmatter(path: Path) -> dict[str, str]:
    """Pull `name:` / `description:` out of a SKILL.md YAML header.

    Hand-rolled rather than pulling in a YAML parser: the header is two known
    scalar keys, and descriptions contain colons and quotes (they quote real
    student phrasing), which a naive split would mangle. Anything unparseable
    yields {} and the skill is skipped rather than crashing the picker.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^(name|description):\s*(.+)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


@lru_cache(maxsize=1)
def _catalogue() -> list[SkillOut]:
    """Scan the skills tree once per process — it ships with the image and
    cannot change under a running server."""
    if not _SKILLS_DIR.is_dir():
        return []
    found: list[SkillOut] = []
    for d in sorted(_SKILLS_DIR.iterdir()):
        if not d.is_dir() or d.name in _HIDDEN or _MODULE_SKILL_RE.match(d.name):
            continue
        fm = _parse_frontmatter(d / "SKILL.md")
        if not fm.get("description"):
            continue
        # "dothesis-humanize" -> "Humanize": the directory prefix is a packaging
        # detail, not something to show a student.
        label = fm.get("name", d.name).removeprefix("dothesis-").replace("-", " ")
        found.append(SkillOut(
            id=d.name,
            name=label[:1].upper() + label[1:],
            description=fm["description"],
            suggested_for=_SUGGESTED_FOR.get(d.name, []),
        ))
    return found


@router.post("/skills/list", response_model=SkillListOut)
def list_skills(_body: AuthedBody, _user: User = Depends(current_user)) -> SkillListOut:
    """Skills a student can explicitly invoke from the chat picker."""
    return SkillListOut(skills=_catalogue())
