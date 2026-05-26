"""M3 — Research Design agent (paradigm-aware multi-method)."""
import json
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.widgets import CardGridHint, CardOption, ListEditorHint, ListItem
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

    # SP4: class-level caches the agent's step() populates before the
    # ModuleAgent base calls render_hint_for_field. The hook signature is
    # parameter-less for compatibility with the other 4 agents; M3 stashes
    # everything it needs here.
    _render_paradigm: str | None = None
    _render_research_question: str = ""
    _render_gaps_summary: str = ""
    _render_themes: list = []
    _render_constructs: list = []
    _render_conceptual_model: dict | None = None

    def step(self, state):
        """Stash paradigm + RQ + M2 gaps + already-confirmed M3 partials so
        render_hint_for_field can read them without `partial` access.

        Decision: using class-level attributes (rather than instance) means
        the stashed values survive across the base-class call chain and are
        also directly patchable in unit tests without needing a real state dict.
        All dependencies for list_editor renders (themes, constructs,
        conceptual_model) are stashed here so the hint methods stay stateless.
        """
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        cls._render_paradigm = partial.get("paradigm")
        # M1's research_question (first one if multiple), M2's gap summary
        m1 = state["context_store"].m1_topic or {}
        m2 = state["context_store"].m2_literature or {}
        cls._render_research_question = (m1.get("research_questions") or [""])[0]
        gaps = m2.get("candidate_gaps") or []
        cls._render_gaps_summary = "; ".join(
            g.get("description", "") for g in gaps[:3]
        )
        # Already-confirmed M3 partials that later list_editor renders depend on
        cls._render_themes = partial.get("themes") or []
        cls._render_constructs = (partial.get("conceptual_model") or {}).get("constructs", [])
        cls._render_conceptual_model = partial.get("conceptual_model")
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
        """Return a widget hint dict for the field, or None for free-text fields.

        Decision: card_grid for bounded-selection fields (tool, design,
        mixed_design_type); list_editor for list-valued fields that benefit from
        AI-suggested initial items (themes, interview_guide, purposive_criteria,
        conceptual_model, scale_items). Free-text fields like sampling_strategy
        and target_sample_size return None so the LLM coaches interactively.
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

        # List-editor hints (editable list fields) ---
        if field_name == "themes":
            # Decision: call suggest_themes with the RQ + paradigm + gap context
            # so the initial item set is already aligned with the study framing.
            # Sub-themes become nested ListItem children (allow_nested=True).
            raw = suggest_themes.invoke({
                "research_question": self._render_research_question,
                "paradigm": self._render_paradigm or "qualitative",
                "gaps_summary": self._render_gaps_summary,
            })
            items = [
                ListItem(
                    id=t.get("id", f"t{i}"),
                    text=t.get("theme", ""),
                    sub_items=[ListItem(id=f"{t.get('id','t')}_s{j}", text=s)
                               for j, s in enumerate(t.get("sub_themes", []))],
                )
                for i, t in enumerate(raw)
            ]
            return ListEditorHint(
                field_name="themes",
                title="Thematic framework — edit and confirm",
                initial_items=items,
                allow_nested=True,
            ).model_dump()

        if field_name == "interview_guide":
            # Decision: guide is structured into phases/sections with timed slots.
            # Each question becomes a top-level item; probes become sub_items so
            # the student can expand/collapse them without losing structure.
            guide = compose_interview_guide.invoke({
                "themes": self._render_themes,
                "research_question": self._render_research_question,
            })
            items: list[ListItem] = []
            for s_idx, section in enumerate(guide.get("sections", [])):
                phase = section.get("phase", "main")
                for q_idx, q in enumerate(section.get("questions", [])):
                    items.append(ListItem(
                        id=f"{phase}_{s_idx}_{q_idx}",
                        text=f"[{phase}] {q.get('q', '')}",
                        sub_items=[
                            ListItem(id=f"{phase}_{s_idx}_{q_idx}_p{p_idx}", text=p)
                            for p_idx, p in enumerate(q.get("probes", []))
                        ],
                        meta={"phase": phase, "time_minutes": section.get("time_minutes")},
                    ))
            return ListEditorHint(
                field_name="interview_guide",
                title="Interview guide — edit questions and probes",
                initial_items=items,
                allow_nested=True,
            ).model_dump()

        if field_name == "purposive_criteria":
            # Decision: criteria are flat strings — no nesting needed, so
            # allow_nested=False and items are a simple flat list.
            raw = suggest_purposive_criteria.invoke({
                "research_question": self._render_research_question,
                "paradigm": self._render_paradigm or "qualitative",
            })
            items = [
                ListItem(id=f"c{i}", text=c)
                for i, c in enumerate(raw.get("criteria", []))
            ]
            return ListEditorHint(
                field_name="purposive_criteria",
                title="Purposive sampling criteria",
                initial_items=items,
                allow_nested=False,
            ).model_dump()

        if field_name == "conceptual_model":
            # Decision: build_conceptual_model returns {constructs, paths:[{from,to,hypothesis}]}.
            # We adapt paths into flat ListItem rows (one per path) because the
            # student edits hypotheses, not constructs — constructs are derived
            # from confirmed paths at submission time. hypothesis is stashed in
            # meta so the frontend can surface it as a tooltip or secondary label.
            model = build_conceptual_model.invoke({
                "constructs": self._render_constructs,
                "research_question": self._render_research_question,
            })
            items = []
            for i, p in enumerate(model.get("paths", [])):
                items.append(ListItem(
                    id=f"H{i+1}",
                    text=f"{p.get('from', '?')} → {p.get('to', '?')}",
                    meta={"hypothesis": p.get("hypothesis", "")},
                ))
            return ListEditorHint(
                field_name="conceptual_model",
                title="Conceptual model — paths between constructs",
                initial_items=items,
                allow_nested=False,
            ).model_dump()

        if field_name == "scale_items":
            # Decision: each construct becomes a top-level ListItem; its 5
            # suggested scale items become sub_items. allow_nested=True so the
            # student can add/remove items per construct in the editor.
            cm = self._render_conceptual_model or {}
            constructs = cm.get("constructs", []) if isinstance(cm, dict) else []
            items_list: list[ListItem] = []
            for c_idx, c in enumerate(constructs):
                suggested = suggest_scale_items.invoke({"construct": c, "n": 5})
                items_list.append(ListItem(
                    id=f"c{c_idx}",
                    text=c,
                    sub_items=[
                        ListItem(id=f"c{c_idx}_i{j}", text=s.get("text", ""))
                        for j, s in enumerate(suggested)
                    ],
                ))
            return ListEditorHint(
                field_name="scale_items",
                title="Scale items per construct",
                initial_items=items_list,
                allow_nested=True,
            ).model_dump()

        return None  # free-text for sampling_strategy / target_sample_size
