"""M3 — Research Design agent."""
from pathlib import Path
from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m3 import M3Output
from orchestrator.tools.m3_design import (
    build_conceptual_model, estimate_sample_size,
    recommend_methodology, suggest_scale_items,
)

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m3.md").read_text()


class M3Agent(ModuleAgent):
    schema = M3Output
    module_key = "M3"
    system_prompt = _PROMPT
    tools = [recommend_methodology, build_conceptual_model,
             suggest_scale_items, estimate_sample_size]
