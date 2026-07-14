"""M1 — Topic Discovery agent."""
import logging
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.shapes import WizardAgent
from orchestrator.agents.widgets import CardOption
from orchestrator.schemas.m1 import M1Output
from orchestrator.tools.m1_topic import refine_title, research_brief, suggest_topics


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m1.md").read_text(encoding="utf-8")
_log = logging.getLogger(__name__)


class M1Agent(WizardAgent, ModuleAgent):
    # PR #5 — declared as the Wizard shape per brief §3. The wizard refactor
    # (one structured-output call per turn, no clarification loop) is the
    # follow-up PR #5b; ModuleAgent's concrete step() resolves via MRO until
    # then. The shape declaration pins the contract so the refactor PR can
    # be reviewed against an explicit isinstance check.
    schema = M1Output
    module_key = "M1"
    slice_field = "m1_topic"  # brief §6 — ModuleHandler contract
    system_prompt = _PROMPT
    tools = [research_brief, suggest_topics, refine_title]

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

    # Static fallbacks for literal-bounded card_fields. The dynamic LLM
    # generator (base._generate_card_options) is best-effort; when it
    # fails the user used to see the bot promise 'pick a card' with no
    # cards rendered. The schema literal IS the option set for these
    # fields, so the fallback is exact, not just plausible.
    _STATIC_RESEARCH_TYPE_OPTIONS = [
        CardOption(value="quantitative", label="Quantitative",
                   description=("Numerical data, statistical tests, "
                                "hypothesis-driven.")),
        CardOption(value="qualitative", label="Qualitative",
                   description=("Themes, interviews, narrative analysis — "
                                "meaning over numbers.")),
        CardOption(value="mixed", label="Mixed methods",
                   description=("Combine quant and qual in one design "
                                "(sequential or concurrent).")),
        CardOption(value="Other", label="Other / Specify",
                   description="Type a custom approach if none above fit."),
    ]

    def _static_card_options(self, field_name, partial):
        if field_name == "research_type":
            return self._STATIC_RESEARCH_TYPE_OPTIONS
        return super()._static_card_options(field_name, partial)

    def _auto_fill(self, state, partial):
        """Auto-mode M1 = base field fill PLUS a grounded research brief.

        Interactive M1 exposes `research_brief` as a tool the agent may call,
        but auto-mode never invokes tools (one structured-output shot). So the
        headless M1 slice used to carry only title/objectives/RQs. Here we run
        the brief once and attach context + research_gaps + suggested_topics
        (each grounded in real literature) to the slice — best-effort, so a
        failed/slow brief never blocks the auto-draft.
        """
        result = super()._auto_fill(state, partial)
        patch = getattr(result, "context_patch", None)
        if not isinstance(patch, dict) or patch.get("research_gaps"):
            return result
        idea = str(patch.get("research_title") or "").strip()
        if not idea:
            try:
                idea = " ".join(
                    str(getattr(m, "content", "") or "")
                    for m in (state.get("messages") or [])
                ).strip()
            except Exception:
                idea = ""
        if not idea:
            return result
        try:
            brief = research_brief.func(idea, field=str(patch.get("field") or ""))
            if brief.get("context"):
                patch["context"] = brief["context"]
            if brief.get("gaps"):
                patch["research_gaps"] = brief["gaps"]
            if brief.get("suggested_topics"):
                patch["suggested_topics"] = brief["suggested_topics"]
            if brief.get("sources"):
                patch["brief_sources"] = brief["sources"]
        except Exception:
            _log.warning("M1 auto research_brief failed", exc_info=True)
        return result
