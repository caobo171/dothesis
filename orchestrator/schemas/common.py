"""Enums and shared types used across module schemas."""
from typing import Literal

ResearchType = Literal["quantitative", "qualitative", "mixed"]
Paradigm = Literal["quantitative", "qualitative", "mixed"]
AcademicField = str  # Free-form for sub-project 1; tightens later.
CitationStyle = Literal["apa7", "apa6", "vancouver", "chicago", "harvard", "ieee", "custom"]
Language = Literal["vi", "en", "bilingual"]


def normalize_research_type(v):
    """Coerce common LLM phrasings into the canonical quantitative/qualitative/
    mixed enum. Auto-fill kept emitting variants like "Mixed-methods",
    "Quantitative", or "qual" that failed Literal validation. Substring match
    keeps it tolerant; unknown values pass through unchanged so genuinely bad
    input still raises the validation error.
    """
    if not isinstance(v, str):
        return v
    s = v.strip().lower()
    if "mix" in s:
        return "mixed"
    if "quant" in s:
        return "quantitative"
    if "qual" in s:
        return "qualitative"
    return s
