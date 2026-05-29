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
    # SP3 originally only carded `field` + `research_type` (the bounded-choice
    # schema slots). Expanded to `target_population` + `scope` because M1's
    # LLM prompts for those fields naturally suggest 2-3 options inline (e.g.
    # "Gen Z consumers, marketers, or businesses?") and forcing free-text
    # input there made the UX feel like a quiz instead of a choice. With the
    # dynamic generator, the LLM produces partial-state-grounded cards so
    # `target_population` for "Gen Z TikTok marketing" surfaces the same
    # options the prose suggests — clickable.
    card_fields = {"field", "research_type", "target_population", "scope"}
    card_field_titles = {
        "field": "Which academic field is your research in?",
        "research_type": "Which research approach fits your question?",
        "target_population": "Who is your target population?",
        "scope": "What's the scope of your study?",
    }

    # objectives + research_questions are list[str] in M1Output. Rendering
    # them as editable lists (instead of "type N bullets here") matches the
    # zero-typing UX rule: the LLM seeds 3-4 contextually grounded items
    # from the partial state; the user edits in place and clicks Confirm.
    # Anyone who wants to type from scratch can clear the list and add their
    # own items — list_editor is itself a typing surface.
    list_fields = {"objectives", "research_questions"}
    list_field_titles = {
        "objectives": "Research objectives — edit and confirm",
        "research_questions": "Research questions — edit and confirm",
    }
