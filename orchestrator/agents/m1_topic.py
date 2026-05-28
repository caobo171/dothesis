"""M1 — Topic Discovery agent."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m1 import M1Output
from orchestrator.tools.m1_topic import refine_title, suggest_topics


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m1.md").read_text()


class M1Agent(ModuleAgent):
    schema = M1Output
    module_key = "M1"
    system_prompt = _PROMPT
    tools = [suggest_topics, refine_title]

    # Dynamic LLM-generated cards for these fields — see base.ModuleAgent.
    # The base class's render_hint_for_field reads `card_fields` and asks the
    # LLM for options grounded in the partial state, so e.g. once the user
    # enters research_title="Gen Z social media use" the `field` cards will
    # surface Sociology / Media Studies / Marketing / Education rather than
    # a generic catalog. Static JSON option files used to live in
    # prompts/m1/_options_{field,research_type}.json and were retired when
    # this opt-in was added.
    card_fields = {"field", "research_type"}
    card_field_titles = {
        "field": "Which academic field is your research in?",
        "research_type": "Which research approach fits your question?",
    }
