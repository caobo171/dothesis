"""M3 — Research Design agent (paradigm-aware multi-method)."""
import json
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.widgets import CardGridHint, CardOption
from orchestrator.schemas.m3 import M3Output
from orchestrator.tools.m3_design import (
    build_conceptual_model, compose_interview_guide, estimate_sample_size,
    recommend_methodology, suggest_purposive_criteria, suggest_scale_items,
    suggest_themes,
)


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m3.md").read_text()
_OPTIONS_DIR = _PROMPT_DIR / "m3"


def _load_options(name: str) -> list[CardOption]:
    """Load a `_options_<name>.json` file and return as a list of CardOption.

    Decision: reading from static JSON files keeps option data out of Python
    code and makes it easy to update labels/descriptions without touching agent
    logic. The files live next to the m3 prompt so they ship together.
    """
    raw = json.loads((_OPTIONS_DIR / f"_options_{name}.json").read_text())
    return [CardOption(**o) for o in raw]


# SP4: paradigm-aware field walk order. Keys are the resolved paradigm-or-mixed-type.
# The agent's _next_missing_field walks the list for the resolved key. Mixed flows
# compose quant + qual sub-flows — no separate "mixed-only" code path.
_FIELDS_BY_PARADIGM = {
    "quantitative": [
        "design", "tool", "conceptual_model", "scale_items",
        "target_sample_size", "sampling_strategy",
    ],
    "qualitative": [
        "design", "tool", "themes", "interview_guide", "purposive_criteria",
        "target_sample_size", "sampling_strategy",
    ],
    "mixed_sequential_explanatory": [
        "mixed_design_type",
        # Quant first
        "design", "tool", "conceptual_model", "scale_items",
        # Qual second (reuses the same design/tool slots — the agent's prompt
        # explains which phase the field belongs to). A V2 enhancement could
        # split into design_quant/design_qual.
        "themes", "interview_guide", "purposive_criteria",
        # Shared at the end
        "target_sample_size", "sampling_strategy",
    ],
    "mixed_sequential_exploratory": [
        "mixed_design_type",
        # Qual first
        "themes", "interview_guide", "purposive_criteria",
        # Quant second
        "design", "tool", "conceptual_model", "scale_items",
        # Shared at the end
        "target_sample_size", "sampling_strategy",
    ],
}


class M3Agent(ModuleAgent):
    schema = M3Output
    module_key = "M3"
    system_prompt = _PROMPT
    tools = [
        recommend_methodology, build_conceptual_model, suggest_scale_items,
        estimate_sample_size, suggest_themes, compose_interview_guide,
        suggest_purposive_criteria,
    ]

    # SP4: a class-level cache the agent's step() writes to before the
    # ModuleAgent base calls render_hint_for_field. We can't pass `partial`
    # into the hook without changing the base-class signature (which would
    # ripple to all 5 module agents), so M3 keeps the paradigm context here.
    # Tests patch this attribute directly.
    _render_paradigm: str | None = None

    def step(self, state):
        """Stash the resolved paradigm so render_hint_for_field can read it
        without the base class needing to pass `partial` into the hook.

        Decision: using a class-level attribute (rather than instance) means
        the stashed value survives across the base-class call chain and is
        also directly patchable in unit tests without needing a real state dict.
        """
        from orchestrator.state import get_module_slice
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        type(self)._render_paradigm = partial.get("paradigm")
        return super().step(state)

    def _resolved_paradigm_key(self, partial: dict) -> str | None:
        """Pick the _FIELDS_BY_PARADIGM key for the current partial state.

        For mixed paradigm we can't pick the full walk order until
        mixed_design_type is set. Until then default to sequential_explanatory —
        both walk orders start with mixed_design_type, so the first prompt is
        identical; after fill the resolved key flips to the right walk order.
        """
        p = partial.get("paradigm")
        if p == "mixed":
            return f"mixed_{partial.get('mixed_design_type') or 'sequential_explanatory'}"
        return p

    def _next_missing_field(self, partial: dict) -> str | None:
        """Paradigm-aware override. Walk the ordered list for the resolved key.

        We override `_next_missing_field` (not `_required_field_names`) because
        the base abstraction's parameter-less signature must stay intact for
        the other 4 module agents.
        """
        key = self._resolved_paradigm_key(partial)
        if key is None or key not in _FIELDS_BY_PARADIGM:
            # Paradigm not yet known — fall back to base class behavior.
            return super()._next_missing_field(partial)
        for name in _FIELDS_BY_PARADIGM[key]:
            v = partial.get(name)
            if v is None or v == "" or v == []:
                return name
        return None

    def render_hint_for_field(self, field_name: str) -> dict | None:
        """Return a CardGridHint for the three selection-point fields; None for
        all free-text fields (handled conversationally by the agent tools).

        Decision: only the fields where the user picks from a bounded set get a
        card_grid widget. Free-text fields like sampling_strategy and
        target_sample_size are left as chat input so the LLM can coach the
        student through sizing decisions interactively.
        """
        # Card-grid hints (selection points) ---
        if field_name == "tool":
            opts = _load_options("tool_qual" if self._render_paradigm == "qualitative"
                                 else "tool_quant")
            return CardGridHint(
                field_name="tool",
                title="Which analysis tool will you use?",
                options=opts, columns=3,
            ).model_dump()

        if field_name == "design":
            # Quant `design` is free-text (recommend_methodology drives the
            # conversation). Qual `design` shows the four canonical designs.
            if self._render_paradigm != "qualitative":
                return None
            return CardGridHint(
                field_name="design",
                title="Which qualitative design fits your study?",
                options=_load_options("design_qual"), columns=2,
            ).model_dump()

        if field_name == "mixed_design_type":
            return CardGridHint(
                field_name="mixed_design_type",
                title="Which mixed-methods design?",
                options=_load_options("mixed_design_type"), columns=2,
            ).model_dump()

        # List-editor branches land in Task 9.
        return None
