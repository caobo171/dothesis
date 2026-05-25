"""M5 — Writing & Export agent."""
from pathlib import Path
from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m5 import M5Output
from orchestrator.tools.m5_writing import (
    compile_pdf, compose_section, export_docx,
    format_citations, validate_draft,
)

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m5.md").read_text()


class M5Agent(ModuleAgent):
    schema = M5Output
    module_key = "M5"
    system_prompt = _PROMPT
    tools = [compose_section, validate_draft, format_citations,
             compile_pdf, export_docx]
