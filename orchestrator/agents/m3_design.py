"""M3 — Research Design agent (paradigm-aware multi-method)."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.widgets import (
    CardGridHint, CardOption, FlowChartEdge, FlowChartHint, FlowChartNode,
    ListEditorHint, ListItem,
)


# Static fallback for `design` per paradigm. Used when the dynamic LLM
# card gen times out / returns junk — prevents the 'pick the cards' prompt
# from showing up with no cards. Picked to cover the 90th-percentile
# theses: regression / SEM for quant; phenomenological etc. for qual.
_STATIC_DESIGN_QUANT_OPTIONS = [
    CardOption(value="Linear regression", label="Linear regression",
               description=("One DV, predictors; assumes linear relations. "
                            "Analyze in SPSS / R / Stata.")),
    CardOption(value="Multiple regression", label="Multiple regression",
               description=("Linear regression with multiple IVs and "
                            "interaction/control terms.")),
    CardOption(value="ANOVA", label="ANOVA / ANCOVA",
               description=("Compare means across groups; covariates "
                            "via ANCOVA.")),
    CardOption(value="PLS-SEM", label="PLS-SEM",
               description=("Partial-least-squares structural equation "
                            "modeling. Use SmartPLS.")),
    CardOption(value="CB-SEM", label="CB-SEM",
               description=("Covariance-based SEM. Use AMOS / lavaan.")),
    CardOption(value="Other", label="Other / Specify",
               description="Type a different quant design (e.g. logistic, MLR)."),
]

_STATIC_DESIGN_QUAL_OPTIONS = [
    CardOption(value="Thematic Analysis", label="Thematic Analysis",
               description="Flexible coding-themes approach (Braun & Clarke)."),
    CardOption(value="Grounded Theory", label="Grounded Theory",
               description="Iterative theory-building from data."),
    CardOption(value="Phenomenological", label="Phenomenological",
               description="Lived experience of participants."),
    CardOption(value="Case Study", label="Case Study",
               description="One or a few bounded cases in depth."),
    CardOption(value="Other", label="Other / Specify",
               description="Type a different qual design (e.g. Narrative)."),
]


# Literal-bounded slot — same defense as M1.research_type. When the dynamic
# LLM card gen fails this lets the cards still render instead of leaving the
# user with a 'pick a card' prompt that has no cards.
_STATIC_MIXED_DESIGN_OPTIONS = [
    CardOption(value="sequential_explanatory", label="Sequential — Explanatory",
               description=("Quantitative first, then qualitative to explain the "
                            "numbers. Most common mixed design.")),
    CardOption(value="sequential_exploratory", label="Sequential — Exploratory",
               description=("Qualitative first to surface constructs, then "
                            "quantitative to test/generalise them.")),
    CardOption(value="Other", label="Other / Specify",
               description="Concurrent or another variant — type it in."),
]


def _sampling_strategy_hint() -> dict:
    """Card grid for sampling_strategy — covers the strategies that show up
    in 95% of social-science theses (probability + non-probability) plus
    Other for anything else."""
    return CardGridHint(
        widget_type="card_grid",
        field_name="sampling_strategy",
        title="Which sampling strategy will you use?",
        options=[
            CardOption(value="convenience", label="Convenience",
                       description=("Recruit whoever is easiest to reach. "
                                    "Common for student-population studies.")),
            CardOption(value="purposive", label="Purposive",
                       description=("Hand-pick participants who match a criterion. "
                                    "Standard for qualitative.")),
            CardOption(value="snowball", label="Snowball",
                       description=("Each participant refers the next. Good for "
                                    "hard-to-reach or hidden populations.")),
            CardOption(value="random", label="Simple random",
                       description=("Probability-based; every member of the frame "
                                    "has equal chance. Most generalisable.")),
            CardOption(value="stratified", label="Stratified random",
                       description=("Random within strata (age / region / role). "
                                    "Preserves subgroup representation.")),
            CardOption(value="Other", label="Other / Specify",
                       description="Type a different strategy in your own words."),
        ],
        columns=3,
    ).model_dump()


def _target_sample_size_hint() -> dict:
    """Card grid for target_sample_size — the four sizes that map to common
    statistical-power rules of thumb plus Other for typing a custom n."""
    return CardGridHint(
        widget_type="card_grid",
        field_name="target_sample_size",
        title="What's your target sample size?",
        options=[
            CardOption(value="30", label="n ≈ 30",
                       description=("Cohen's small-sample threshold; OK for "
                                    "exploratory or pilot studies.")),
            CardOption(value="100", label="n ≈ 100",
                       description=("Common minimum for survey research "
                                    "with a few subgroups.")),
            CardOption(value="200", label="n ≈ 200",
                       description=("Hair et al.'s SEM minimum; safe for "
                                    "PLS-SEM with up to ~10 constructs.")),
            CardOption(value="384", label="n ≈ 384",
                       description=("Yields 95% CI ±5% for an unknown "
                                    "population proportion. Conservative.")),
            CardOption(value="Other", label="Other / Specify",
                       description="Type a custom sample size."),
        ],
        columns=3,
    ).model_dump()
from orchestrator.schemas.m3 import M3Output
from orchestrator.tools.m3_design import (
    build_conceptual_model, compose_interview_guide, estimate_sample_size,
    recommend_methodology, suggest_purposive_criteria, suggest_scale_items,
    suggest_scale_items_batch, suggest_themes,
)


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m3.md").read_text()


# SP4: paradigm-aware field walk order. Keys are the resolved paradigm-or-mixed-type.
# The agent's _next_missing_field walks the list for the resolved key. Mixed flows
# compose quant + qual sub-flows — no separate "mixed-only" code path.
_FIELDS_BY_PARADIGM = {
    # Design merge (2026-06): scale_items used to be a separate walk step
    # after conceptual_model. The conceptual_model widget now ships the
    # full flow_chart (nodes-with-questions + edges) so structure and
    # measurement land in one bubble — scale_items is dropped from every
    # walk order and from the schema.
    "quantitative": [
        "design", "tool", "conceptual_model",
        "target_sample_size", "sampling_strategy",
    ],
    "qualitative": [
        "design", "tool", "themes", "interview_guide", "purposive_criteria",
        "target_sample_size", "sampling_strategy",
    ],
    "mixed_sequential_explanatory": [
        "mixed_design_type",
        # Quant first
        "design", "tool", "conceptual_model",
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
        "design", "tool", "conceptual_model",
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

    # Dynamic LLM-generated cards for the bounded-selection slots. The base
    # class reads `card_fields`, asks the LLM for options seeded by `partial`,
    # which already carries the resolved paradigm so quant vs qual suggestions
    # diverge naturally (e.g. SmartPLS/AMOS for quant `tool`, NVivo/MAXQDA for
    # qual). `design` is paradigm-gated in render_hint_for_field below.
    card_fields = {"tool", "design", "mixed_design_type"}
    card_field_titles = {
        "tool": "Which analysis tool will you use?",
        # Paradigm-agnostic — the dynamic LLM generator picks the right
        # design family per partial state (quant → PLS-SEM / regression /
        # ANOVA / etc.; qual → Thematic / Grounded / Phenomenological /
        # Case Study).
        "design": "Which design fits your study?",
        "mixed_design_type": "Which mixed-methods design?",
    }

    # SP4: class-level caches the agent's step() populates before the
    # ModuleAgent base calls render_hint_for_field. The list-editor branches
    # below read these; card branches now read paradigm from `partial` directly.
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
        # M1's research_question (first one if multiple), M2's gap summary.
        # M2 stores gaps under "research_gaps" in M2Output (translation.py:67);
        # the M2 sub-graph's internal "candidate_gaps" gets translated out.
        m1 = state["context_store"].m1_topic or {}
        m2 = state["context_store"].m2_literature or {}
        cls._render_research_question = (m1.get("research_questions") or [""])[0]
        gaps = m2.get("research_gaps") or []
        cls._render_gaps_summary = "; ".join(
            g.get("description", "") for g in gaps[:3]
        )
        # Already-confirmed M3 partials that later list_editor renders depend on
        cls._render_themes = partial.get("themes") or []
        cls._render_constructs = self._constructs_from(partial.get("conceptual_model"))
        cls._render_conceptual_model = partial.get("conceptual_model")
        return super().step(state)

    @staticmethod
    def _constructs_from(conceptual_model) -> list:
        """Extract construct names from a stored conceptual_model.

        The model can arrive in several shapes depending on how the LLM
        extractor parsed the user's 'Confirm' message back into the
        `conceptual_model: dict | None` field:

          1. {"constructs": ["A", "B"], "paths": [...]}   — ideal, what
             build_conceptual_model emits directly.
          2. {"paths": [{"from":"A","to":"B"}, ...]}      — no constructs
             key. summarizeList for conceptual_model only enumerates paths,
             so the extractor commonly drops the constructs list.
          3. [{"from":"A","to":"B"}, ...]                 — bare path-dict
             list (delegation path).
          4. ["A → B (H1)", "B → C (H2)"]                 — bare path-string
             list (LLM-extractor pass-through of the user's confirm message).
          5. ["A", "B"]                                   — bare construct
             list (rare; legacy delegation output).

        Reason this matters: scale_items widget render reads constructs to
        decide how many Likert-item rows to ship. Empty constructs → empty
        card (user-reported bug). Used in two places: step() to seed the
        conceptual_model rebuild, and render_hint_for_field('scale_items')
        to ship one row per construct.
        """
        import re as _re

        def _strip_paren_meta(s: str) -> str:
            # "EE (H1: text)" → "EE" — the parens in our path-string format
            # always carry the hypothesis label, never part of the construct.
            return _re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()

        def _from_paths(paths) -> list:
            seen: list = []
            for p in paths:
                if isinstance(p, dict):
                    for k in ("from", "to"):
                        v = p.get(k)
                        if v and v not in seen:
                            seen.append(v)
                elif isinstance(p, str):
                    # Support both Unicode → and ASCII -> separators.
                    parts = p.split("→") if "→" in p else p.split("->")
                    for v in parts:
                        v = _strip_paren_meta(v)
                        if v and v not in seen:
                            seen.append(v)
            return seen

        if conceptual_model is None:
            return []
        if isinstance(conceptual_model, dict):
            if conceptual_model.get("constructs"):
                return conceptual_model["constructs"]
            return _from_paths(conceptual_model.get("paths") or [])
        if isinstance(conceptual_model, list):
            # Inspect first item to decide path-list vs bare-constructs list.
            if conceptual_model and isinstance(conceptual_model[0], dict):
                return _from_paths(conceptual_model)
            if any(isinstance(x, str) and ("→" in x or "->" in x)
                   for x in conceptual_model):
                return _from_paths(conceptual_model)
            return list(conceptual_model)
        return []

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

    def _static_card_options(self, field_name, partial):
        # Defense for the literal-bounded slot — see _STATIC_MIXED_DESIGN_OPTIONS.
        if field_name == "mixed_design_type":
            return _STATIC_MIXED_DESIGN_OPTIONS
        # `design` has paradigm-specific static fallbacks. Mixed flows pick
        # the quant set by default — the user will narrow it via their own
        # walk; both halves of a mixed study still need a quant design.
        if field_name == "design":
            paradigm = (partial or {}).get("paradigm")
            if paradigm == "qualitative":
                return _STATIC_DESIGN_QUAL_OPTIONS
            return _STATIC_DESIGN_QUANT_OPTIONS
        return super()._static_card_options(field_name, partial)

    def render_hint_for_field(self, field_name: str, partial: dict | None = None) -> dict | None:
        """Return a widget hint dict for the field, or None for free-text fields.

        Card-grid fields (tool / design / mixed_design_type) defer to the base
        class's dynamic LLM generator — it reads `card_fields`, asks the LLM
        for options seeded by `partial`, returns a CardGridHint. `design` is
        paradigm-gated: quant flows return None so recommend_methodology drives
        the conversation as free text.

        List-editor fields (themes / interview_guide / purposive_criteria /
        conceptual_model / scale_items) still call the dedicated tools so the
        initial item set is structurally correct (nested sub_items, hypothesis
        meta, etc.) — those branches stay below.

        Free-text fields (sampling_strategy, target_sample_size) return None.
        """
        # Card-grid hints — delegate to base class dynamic generator. The
        # design gate that used to return None for quantitative is gone:
        # users couldn't pick Linear regression / ANOVA as the design and
        # were stuck with whatever recommend_methodology suggested (almost
        # always PLS-SEM). The dynamic LLM card gen, seeded with the
        # resolved paradigm, picks the right design family.
        if field_name in self.card_fields:
            return super().render_hint_for_field(field_name, partial)

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
            # Design merge (2026-06): one flow_chart widget carries BOTH the
            # paths (edges) and the per-construct Likert items (node.questions),
            # replacing the prior two-step list_editor flow. Mirrors Survify's
            # AdvanceModelType. Reasoning: users need to see structure +
            # measurement together — splitting them into two bubbles produced
            # the empty-scale-items bug because the second widget read stale
            # state, and made every confirm round-trip the conceptual model
            # twice through the LLM extractor.
            #
            # Build order:
            #   1. Ask build_conceptual_model for {constructs, paths}.
            #   2. Resolve the canonical construct list (prefer the tool's
            #      constructs key; fall back to path endpoints — same
            #      _constructs_from defence used by the prior scale_items
            #      branch).
            #   3. ONE batched LLM call for Likert items (regression-guard
            #      for the 'typing dots forever' bug — see SP4 history).
            #   4. Emit FlowChartNode per construct (questions attached) and
            #      FlowChartEdge per path (hypothesis + effect_type carried).
            model = build_conceptual_model.invoke({
                "constructs": self._render_constructs,
                "research_question": self._render_research_question,
            })
            paths = model.get("paths") or []
            constructs = (
                model.get("constructs")
                or self._constructs_from({"paths": paths})
                or list(self._render_constructs or [])
            )
            suggested_by_construct = suggest_scale_items_batch.invoke(
                {"constructs": list(constructs), "n": 5}
            ) if constructs else {}

            id_by_label: dict[str, str] = {}
            nodes: list[FlowChartNode] = []
            for c_idx, c in enumerate(constructs):
                node_id = f"n{c_idx}"
                id_by_label[c] = node_id
                nodes.append(FlowChartNode(
                    id=node_id,
                    label=c,
                    questions=[
                        s.get("text", "")
                        for s in suggested_by_construct.get(c, [])
                        if s.get("text")
                    ],
                ))

            edges: list[FlowChartEdge] = []
            for i, p in enumerate(paths):
                src_label = p.get("from", "")
                tgt_label = p.get("to", "")
                # Defensive: if a path mentions a construct the model.constructs
                # list didn't (LLM inconsistency), spawn the missing node now
                # so the edge has somewhere to attach.
                for label in (src_label, tgt_label):
                    if label and label not in id_by_label:
                        node_id = f"n{len(nodes)}"
                        id_by_label[label] = node_id
                        nodes.append(FlowChartNode(
                            id=node_id, label=label, questions=[],
                        ))
                if not (src_label and tgt_label):
                    continue
                edges.append(FlowChartEdge(
                    id=f"H{i+1}",
                    source=id_by_label[src_label],
                    target=id_by_label[tgt_label],
                    hypothesis=p.get("hypothesis", ""),
                    # Default positive — user can flip on the canvas. Most
                    # initial LLM hypotheses are positively-framed ('A leads
                    # to B'); negative paths are rarer and surface during edit.
                    effect_type="positive",
                ))

            return FlowChartHint(
                field_name="conceptual_model",
                title="Conceptual model — constructs, items, and hypothesis paths",
                initial_nodes=nodes,
                initial_edges=edges,
            ).model_dump()

        # W6: sampling fields used to fall through to free text. Now ship as
        # card grids — bounded choices that cover the standard textbook
        # options, with Other / Specify for anything custom.
        if field_name == "sampling_strategy":
            return _sampling_strategy_hint()
        if field_name == "target_sample_size":
            return _target_sample_size_hint()

        return None  # free-text fallback (no fields remaining at present)
