"""M1 — Topic Discovery agent."""
import json
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.widgets import CardGridHint, CardOption
from orchestrator.schemas.m1 import M1Output
from orchestrator.tools.m1_topic import refine_title, suggest_topics


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m1.md").read_text()
_FIELD_OPTIONS = json.loads((_PROMPT_DIR / "m1" / "_options_field.json").read_text())
_RESEARCH_TYPE_OPTIONS = json.loads((_PROMPT_DIR / "m1" / "_options_research_type.json").read_text())


class M1Agent(ModuleAgent):
    schema = M1Output
    module_key = "M1"
    system_prompt = _PROMPT
    tools = [suggest_topics, refine_title]

    def render_hint_for_field(self, field_name: str) -> dict | None:
        # SP3: card-grid widgets for `field` + `research_type` only. Other M1
        # fields stay free-text. New variants land via this same override pattern.
        if field_name == "field":
            return CardGridHint(
                field_name="field",
                title="Which academic field is your research in?",
                options=[CardOption(**o) for o in _FIELD_OPTIONS],
                columns=3,
            ).model_dump()
        if field_name == "research_type":
            return CardGridHint(
                field_name="research_type",
                title="Which research approach fits your question?",
                options=[CardOption(**o) for o in _RESEARCH_TYPE_OPTIONS],
                columns=3,
            ).model_dump()
        return None
