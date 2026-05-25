"""Enums and shared types used across module schemas."""
from typing import Literal

ResearchType = Literal["quantitative", "qualitative", "mixed"]
Paradigm = Literal["quantitative", "qualitative", "mixed"]
AcademicField = str  # Free-form for sub-project 1; tightens later.
CitationStyle = Literal["apa7", "apa6", "vancouver", "chicago", "harvard", "ieee", "custom"]
Language = Literal["vi", "en", "bilingual"]
