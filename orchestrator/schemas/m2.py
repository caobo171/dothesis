"""M2 Literature Review output schema. Mirrors PRD §6.2.4 + §5.2."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class PaperReference(BaseModel):
    author: str
    year: int
    page: int | None = None
    quote: str | None = None
    verified: bool = False


class CitedGap(BaseModel):
    description: str = Field(..., min_length=1)
    supporting_papers: list[PaperReference] = Field(default_factory=list)
    relevance: Literal["High", "Medium", "Low"] = "Medium"
    confirmed: bool = False


class M2Output(BaseModel):
    research_state_summary: str
    research_gaps: list[CitedGap] = Field(..., min_length=1)
    theoretical_framework: str
    hypotheses: list[str] = Field(default_factory=list)   # quant
    propositions: list[str] = Field(default_factory=list) # qual
    literature_review_doc: str
    citation_list: list[dict]
    confirmed_at: datetime | None = None
