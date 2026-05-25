"""M4 — Data Analysis agent."""
from pathlib import Path
from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m4 import M4Output
from orchestrator.tools.m4_analysis import (
    detect_data_type, generate_analysis_outline,
    interpret_result, run_analysis_step,
)

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m4.md").read_text()


class M4Agent(ModuleAgent):
    schema = M4Output
    module_key = "M4"
    system_prompt = _PROMPT
    tools = [detect_data_type, generate_analysis_outline,
             run_analysis_step, interpret_result]
