"""M3 Research Design output schema. Mirrors PRD §6.3.6."""
from datetime import datetime
from pydantic import BaseModel, Field

from .common import Paradigm


class M3Output(BaseModel):
    paradigm: Paradigm
    design: str = Field(..., description="e.g. PLS-SEM, Thematic Analysis, Sequential Explanatory")
    tool: str = Field(..., description="SmartPLS, NVivo, SPSS, …")
    sampling_strategy: str
    target_sample_size: int = Field(..., gt=0)
    conceptual_model: dict | None = None      # quantitative
    thematic_framework: dict | None = None    # qualitative
    constructs: list[dict] = Field(default_factory=list)
    questionnaire_text: str | None = None
    interview_guide: str | None = None
    confirmed_at: datetime | None = None
