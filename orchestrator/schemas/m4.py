"""M4 Data Analysis output schema. Mirrors PRD §6.4.7."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class M4Output(BaseModel):
    data_type_detected: Literal[
        "SPSS", "SmartPLS", "CB-SEM", "Qualitative", "Mixed", "Unknown"
    ]
    analysis_outline: dict
    results: dict
    interpretations: dict
    custom_analyses: list[dict] = Field(default_factory=list)
    confirmed_at: datetime | None = None
