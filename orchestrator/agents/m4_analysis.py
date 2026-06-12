"""M4 — Data Analysis agent (SP5 adaptive analysis with paste-text parsers).

PR #5 — declared as the Pipeline shape per brief §3. Today's implementation
still uses paste-text parsers + LLM interpretation; brief §8's sandboxed
Python stats (pandas/scipy/statsmodels/pingouin in gVisor or a network-less
container) is a separate downstream PR. The shape declaration pins the
contract so that PR can't drift back into chat-loop territory.
"""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.shapes import PipelineAgent
from orchestrator.message_utils import text_of
from orchestrator.schemas.m4 import M4Output
from orchestrator.tools.m4_analysis import (
    detect_data_type, generate_analysis_outline, interpret_result,
    run_analysis_step, run_extra_analysis,
)
from orchestrator.tools.m4_parsers.transcript import (
    cluster_codes_into_themes, suggest_qual_codes,
)


_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m4.md").read_text()


# SP5: outline-type-aware field walk. Keys resolved from m3_design.tool via
# _outline_template_key_from_tool. Pseudo-fields _run_execution and
# _run_qual_pipeline trigger an execution phase inside step() (added in Task 12).
_FIELDS_BY_OUTLINE_TYPE = {
    "SPSS":        ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "SmartPLS":    ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "CB-SEM":      ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "Qualitative": ["data_paste", "analysis_outline", "_run_qual_pipeline", "_summary"],
    "Mixed":       ["data_paste_quant", "outline_quant", "_run_execution",
                    "data_paste_qual",  "outline_qual",  "_run_qual_pipeline", "_summary"],
    # Unknown defaults to SPSS-like flow so the agent still functions.
    "Unknown":     ["data_paste", "analysis_outline", "_run_execution", "_summary"],
}

_PSEUDO_FIELDS = {"_run_execution", "_run_qual_pipeline", "_summary"}


class M4Agent(PipelineAgent, ModuleAgent):
    # PipelineAgent first for the isinstance shape assertion; ModuleAgent
    # provides the concrete step() until the sandbox-DSL refactor lands.
    schema = M4Output
    module_key = "M4"
    slice_field = "m4_analysis"  # brief §6 — ModuleHandler contract
    system_prompt = _PROMPT
    tools = [
        detect_data_type, generate_analysis_outline, run_analysis_step,
        interpret_result, run_extra_analysis,
        suggest_qual_codes, cluster_codes_into_themes,
    ]

    # SP5 class-level caches (populated by step() in Task 11)
    _render_outline_type: str | None = None
    _render_paste_text: str = ""
    _render_outline: dict | None = None
    _render_paradigm: str | None = None

    def _outline_template_key_from_tool(self, tool: str | None) -> str:
        """Map an M3-recorded analysis tool name to an outline template key."""
        if tool is None:
            return "Unknown"
        t = tool.lower()
        if "smartpls" in t:
            return "SmartPLS"
        if "amos" in t or "lavaan" in t:
            return "CB-SEM"
        if "spss" in t or "stata" in t:
            return "SPSS"
        if "nvivo" in t or "atlas" in t or "manual" in t:
            return "Qualitative"
        return "Unknown"

    def _resolved_outline_key(self, partial: dict) -> str | None:
        """Pick the _FIELDS_BY_OUTLINE_TYPE key for the current state.

        Mixed paradigm always returns "Mixed". Otherwise prefer the cached
        _render_outline_type (set by step() from m3.tool or partial.data_type_detected).
        """
        if self._render_paradigm == "mixed":
            return "Mixed"
        return self._render_outline_type

    def _next_missing_field(self, partial: dict) -> str | None:
        """Outline-type-aware override. Walk the ordered list for the resolved key.

        Pseudo-fields (_run_execution, _run_qual_pipeline, _summary) advance when
        their `<name>_done` marker key is set in the partial."""
        key = self._resolved_outline_key(partial)
        if key is None or key not in _FIELDS_BY_OUTLINE_TYPE:
            return super()._next_missing_field(partial)
        for name in _FIELDS_BY_OUTLINE_TYPE[key]:
            if name in _PSEUDO_FIELDS:
                if not partial.get(f"{name}_done"):
                    return name
                continue
            v = partial.get(name)
            if v is None or v == "" or v == []:
                return name
        return None

    # SP5 Task 11: outline step templates per outline-type-key, with thresholds metadata.
    # Used to populate the list_editor widget's ListItem.meta. For qualitative,
    # only the 2-step pipeline ships per Q5=C; writeup is M5's job.
    _AGENT_OUTLINE_TEMPLATES = {
        "SPSS": [
            {"name": "Descriptive Statistics", "thresholds": ""},
            {"name": "Reliability (Cronbach's Alpha)", "thresholds": "α ≥ 0.7"},
            {"name": "EFA", "thresholds": "KMO ≥ 0.5, factor loading ≥ 0.5"},
            {"name": "Correlation Matrix", "thresholds": "r < 0.85"},
            {"name": "Regression Analysis", "thresholds": "VIF < 10"},
            {"name": "ANOVA / t-tests", "thresholds": "p < 0.05"},
        ],
        "SmartPLS": [
            {"name": "Outer Loadings", "thresholds": "≥ 0.7"},
            {"name": "Convergent Validity: AVE & CR", "thresholds": "AVE ≥ 0.5, CR ≥ 0.7"},
            {"name": "Discriminant Validity: HTMT & Fornell-Larcker", "thresholds": "HTMT < 0.85"},
            {"name": "Collinearity: VIF", "thresholds": "VIF < 5"},
            {"name": "Path Coefficients (Bootstrap 5000)", "thresholds": "p < 0.05"},
            {"name": "R² and Adjusted R²", "thresholds": ""},
            {"name": "Effect size (f²)", "thresholds": "≥ 0.02 small, ≥ 0.15 medium, ≥ 0.35 large"},
            {"name": "Predictive Relevance (Q²)", "thresholds": "Q² > 0"},
        ],
        "CB-SEM": [
            {"name": "Confirmatory Factor Analysis (CFI/TLI/RMSEA)",
             "thresholds": "CFI/TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08"},
            {"name": "Discriminant Validity", "thresholds": "HTMT < 0.85"},
            {"name": "Structural Model", "thresholds": "p < 0.05"},
            {"name": "Mediation/Moderation", "thresholds": ""},
        ],
        "Qualitative": [
            {"name": "Initial coding (extract codes + verbatim quotes)", "thresholds": ""},
            {"name": "Theme generation (cluster codes into themes)", "thresholds": ""},
        ],
        "Unknown": [
            {"name": "Generic descriptive", "thresholds": ""},
            {"name": "Generic inferential", "thresholds": ""},
        ],
    }

    def step(self, state):
        """Populate caches, dispatch execution phase, OR detect ad-hoc request."""
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        m3 = state["context_store"].m3_design or {}
        cls._render_paradigm = m3.get("paradigm")
        cls._render_outline_type = (
            partial.get("data_type_detected")
            or self._outline_template_key_from_tool(m3.get("tool"))
        )
        cls._render_paste_text = partial.get("data_paste", "")
        cls._render_outline = partial.get("analysis_outline")

        # Ad-hoc detection: if execution is done and the latest user message
        # looks like an extra-analysis request, route to run_extra_analysis
        # before the base class's confirm flow takes over.
        # SP5 final-review fix: only route to ad-hoc when NOT awaiting confirm,
        # so "yes, also run ..." gets handled by the confirm path (it transitions)
        # rather than being treated as an ad-hoc request.
        if (
            (partial.get("_run_execution_done") or partial.get("_run_qual_pipeline_done"))
            and not partial.get("_awaiting_confirm")
        ):
            if self._is_ad_hoc_request(state["messages"]):
                return self._handle_ad_hoc(state, partial)

        missing = self._next_missing_field(partial)
        if missing == "_run_execution":
            return self._run_quant_execution(state, partial)
        if missing == "_run_qual_pipeline":
            return self._run_qual_pipeline(state, partial)
        return super().step(state)

    def _run_quant_execution(self, state, partial):
        """Loop confirmed outline sections, dispatch to run_analysis_step,
        emit one AIMessage per step via extra_messages.

        Decision: emit per-step AIMessages rather than one big blob so the
        frontend can stream results section-by-section in the chat pane.
        """
        from langchain_core.messages import AIMessage
        from orchestrator.agents.base import ModuleStepResult
        from orchestrator.tools.m4_parsers import format_step_as_markdown

        outline = partial.get("analysis_outline") or {}
        sections = outline.get("sections", []) or []
        results: dict[str, dict] = dict(partial.get("results", {}))
        extra: list = []
        for section in sections:
            step_name = section["name"]
            # SP5 fix: in mixed mode, quant paste is in data_paste_quant (not data_paste).
            # Read from partial directly, falling back to cache for non-mixed flows.
            paste = (
                partial.get("data_paste_quant")
                or partial.get("data_paste")
                or self._render_paste_text
            )
            sr = run_analysis_step.invoke({
                "step_name": step_name,
                "data": {
                    "paste": paste,
                    "data_type": self._render_outline_type or "Unknown",
                },
            })
            results[step_name] = sr
            extra.append(AIMessage(content=format_step_as_markdown(sr)))
        partial["results"] = results
        partial["_run_execution_done"] = True
        partial["_summary_done"] = True  # SP5 fix: summary message IS the summary step; advance it now
        partial["_awaiting_confirm"] = True
        summary = self._build_execution_summary(results)
        return ModuleStepResult(
            assistant_message=summary,
            context_patch=partial,
            transition=False,
            needs_user_reply=True,
            extra_messages=extra,
        )

    def _run_qual_pipeline(self, state, partial):
        """Two-step qual pipeline (Q5=C): codes + themes. Emit one message per step.

        Decision: separate AIMessages for codes and themes lets the UI render
        each pipeline stage as its own expandable block in the chat pane.
        """
        from langchain_core.messages import AIMessage
        from orchestrator.agents.base import ModuleStepResult

        # SP5 fix: in mixed mode, qual paste is in data_paste_qual (not data_paste).
        # Read from partial directly, falling back to cache for non-mixed flows.
        transcript = (
            partial.get("data_paste_qual")
            or partial.get("data_paste")
            or self._render_paste_text
        )
        codes = suggest_qual_codes.invoke({"transcript": transcript})
        themes = cluster_codes_into_themes.invoke({"codes": codes})
        partial["qual_codes"] = codes
        partial["qual_themes"] = themes
        partial["_run_qual_pipeline_done"] = True
        partial["_summary_done"] = True  # SP5 fix: summary message IS the summary step; advance it now
        partial["_awaiting_confirm"] = True

        code_msg = self._format_qual_codes_markdown(codes)
        theme_msg = self._format_qual_themes_markdown(themes)
        summary = (
            f"Qualitative pipeline complete: {len(codes)} codes clustered "
            f"into {len(themes)} themes. Confirm to move on to Chapter 4 writing."
        )
        return ModuleStepResult(
            assistant_message=summary,
            context_patch=partial,
            transition=False,
            needs_user_reply=True,
            extra_messages=[AIMessage(content=code_msg), AIMessage(content=theme_msg)],
        )

    def _build_execution_summary(self, results: dict[str, dict]) -> str:
        """One-paragraph summary of step thresholds for the user's confirm prompt."""
        total = len(results)
        breached = [name for name, sr in results.items()
                    if sr.get("thresholds_met") is False]
        if not breached:
            return (
                f"All {total} steps met their thresholds. "
                "Confirm to move on to Chapter 4 writing?"
            )
        flagged = ", ".join(breached)
        return (
            f"Ran {total} steps. ⚠️ {len(breached)} flagged threshold breaches: {flagged}. "
            "Review the per-step results above. Confirm to move on, or ask for an "
            "ad-hoc analysis to investigate further."
        )

    def _is_ad_hoc_request(self, messages) -> bool:
        """LLM check: is the user asking for an extra/ad-hoc analysis?

        Replaces a brittle keyword list ("also run" / "mediation" / etc.)
        that missed natural phrasings like "could you test the mediation
        path?" or "what if we control for age?". Falls back to False on LLM
        failure so the conversation stays on the outline track.
        """
        import json
        from langchain_core.messages import HumanMessage
        last_user = next(
            (text_of(m) for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )
        if not last_user:
            return False
        prompt = (
            f"The user is currently running the outlined analysis steps.\n"
            f"User reply: {last_user}\n\n"
            f"Is this an ad-hoc / extra-analysis request (e.g. 'also run a "
            f"mediation test', 'rerun with a control', 'try a moderation', "
            f"'what about an extra t-test')? Or is it a normal next-step / "
            f"confirmation / clarification reply?\n\n"
            f'Respond with ONLY: {{"ad_hoc": true|false}}'
        )
        try:
            from orchestrator.agents.base import _strip_code_fence
            raw = self._get_llm().invoke(prompt).content
            data = json.loads(_strip_code_fence(raw))
            return bool(data.get("ad_hoc"))
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("M4 ad-hoc classification failed")
        return False

    def _handle_ad_hoc(self, state, partial):
        """Route an ad-hoc user message to run_extra_analysis + append to custom_analyses.

        Decision: appending to custom_analyses (separate from results) lets the
        frontend render ad-hoc results distinctly from the confirmed outline steps,
        keeping the main results dict clean.
        """
        from langchain_core.messages import AIMessage, HumanMessage
        from orchestrator.agents.base import ModuleStepResult
        from orchestrator.tools.m4_parsers import format_step_as_markdown

        last_user = next(
            (text_of(m) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            "",
        )
        sr = run_extra_analysis.invoke({
            "step_description": last_user.strip(),
            "data_paste": self._render_paste_text,
        })
        custom = list(partial.get("custom_analyses", []))
        custom.append(sr)
        partial["custom_analyses"] = custom
        msg = format_step_as_markdown(sr)
        return ModuleStepResult(
            assistant_message=msg,
            context_patch=partial,
            transition=False,
            needs_user_reply=True,
        )

    def _format_qual_codes_markdown(self, codes: list[dict]) -> str:
        if not codes:
            return "**Initial coding** — no codes extracted."
        rows = "\n".join(
            f"- **{c.get('code', '?')}** — \"{c.get('quote', '')[:120]}\""
            for c in codes
        )
        return f"**Initial coding** — {len(codes)} codes extracted:\n\n{rows}"

    def _format_qual_themes_markdown(self, themes: list[dict]) -> str:
        if not themes:
            return "**Theme generation** — no themes clustered."
        rows = "\n".join(
            f"- **{t.get('theme', '?')}** — codes: {', '.join(t.get('codes', []))}"
            for t in themes
        )
        return f"**Theme generation** — {len(themes)} themes:\n\n{rows}"

    def render_hint_for_field(self, field_name: str, partial: dict | None = None) -> dict | None:
        """Emit ListEditorHint for outline fields; None for data_paste* and pseudo-fields.

        outline_quant uses the SmartPLS template (default quant for mixed flow).
        outline_qual always uses the Qualitative 2-step template.
        analysis_outline uses _render_outline_type (set by step() or patched in tests).
        """
        from orchestrator.agents.widgets import ListEditorHint, ListItem

        if field_name in ("analysis_outline", "outline_quant", "outline_qual"):
            # Pick the correct template key per field type.
            if field_name == "outline_qual":
                template_key = "Qualitative"
            elif field_name == "outline_quant":
                # SP5 fix: for mixed, prefer the user's actual quant tool resolved from
                # m3.tool. Default to SmartPLS if unknown (most common for
                # publishable mixed-methods studies).
                resolved = self._render_outline_type
                if resolved in ("SPSS", "SmartPLS", "CB-SEM"):
                    template_key = resolved
                else:
                    template_key = "SmartPLS"
            else:
                template_key = self._render_outline_type or "SPSS"
            sections = self._AGENT_OUTLINE_TEMPLATES.get(
                template_key, self._AGENT_OUTLINE_TEMPLATES["Unknown"]
            )
            items = [
                ListItem(
                    id=f"s{i}", text=s["name"],
                    meta={"thresholds": s.get("thresholds", "")},
                )
                for i, s in enumerate(sections)
            ]
            return ListEditorHint(
                field_name=field_name,
                title=f"{template_key} analysis outline — edit and confirm",
                initial_items=items,
                allow_nested=False,
            ).model_dump()
        return None  # free-text for data_paste*; None for pseudo-fields
