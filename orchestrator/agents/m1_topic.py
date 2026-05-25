"""M1 — Topic Discovery agent."""
from pathlib import Path
from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m1 import M1Output
from orchestrator.tools.m1_topic import refine_title, suggest_topics

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m1.md").read_text()


class M1Agent(ModuleAgent):
    schema = M1Output
    module_key = "M1"
    system_prompt = _PROMPT
    tools = [suggest_topics, refine_title]
