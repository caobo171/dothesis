"""M3 — Research Design agent (paradigm-aware multi-method)."""
import json
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m3 import M3Output
from orchestrator.tools.m3_design import (
    build_conceptual_model, compose_interview_guide, estimate_sample_size,
    recommend_methodology, suggest_purposive_criteria, suggest_scale_items,
    suggest_themes,
)


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m3.md").read_text()


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
