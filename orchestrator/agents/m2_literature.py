"""M2 — Literature Review agent."""
from pathlib import Path
from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m2 import M2Output
from orchestrator.tools.m2_literature import (
    compile_citations, find_research_gaps, scout_citations,
    summarize_paper, verify_page_numbers,
)

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m2.md").read_text()


class M2Agent(ModuleAgent):
    schema = M2Output
    module_key = "M2"
    system_prompt = _PROMPT
    tools = [scout_citations, summarize_paper, find_research_gaps,
             compile_citations, verify_page_numbers]
