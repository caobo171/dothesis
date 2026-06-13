"""M1 Topic Discovery output schema. Mirrors PRD §6.1.3."""
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from .common import AcademicField, ResearchType, normalize_research_type


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

    # Auto-fill LLM emits "Mixed-methods" / "Quantitative" / "qual" etc. —
    # normalize before the Literal check so a synonym doesn't fail validation.
    _norm_research_type = field_validator("research_type", mode="before")(
        normalize_research_type
    )
