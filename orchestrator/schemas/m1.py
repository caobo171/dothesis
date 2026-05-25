"""M1 Topic Discovery output schema. Mirrors PRD §6.1.3."""
from datetime import datetime
from pydantic import BaseModel, Field

from .common import AcademicField, ResearchType


class M1Output(BaseModel):
    """Confirmed when all required fields filled + user OK'd."""
    research_title: str = Field(..., min_length=1)
    field: AcademicField
    research_type: ResearchType
    target_population: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1)
    objectives: list[str] = Field(..., min_length=1)
    research_questions: list[str] = Field(..., min_length=1)
    confirmed_at: datetime | None = None
