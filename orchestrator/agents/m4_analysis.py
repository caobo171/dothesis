"""M4 — Data Analysis agent (SP5 adaptive analysis with paste-text parsers)."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
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


class M4Agent(ModuleAgent):
    schema = M4Output
    module_key = "M4"
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
