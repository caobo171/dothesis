"""LLM extraction fallback (Task 8 adds real implementation)."""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def extract_step_data(text: str, step_name: str, data_type: str) -> dict | None:
    """LLM-driven step data extraction. Task 8 replaces this stub."""
    return None  # filled in by Task 8
