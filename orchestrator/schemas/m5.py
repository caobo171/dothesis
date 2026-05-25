"""M5 Writing & Finalization output schema. Mirrors PRD §6.5."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ExportArtifact(BaseModel):
    kind: Literal["docx", "pdf", "latex", "md"]
    uri: str
    size_bytes: int = Field(..., ge=0)


class M5Output(BaseModel):
    sections: list[dict] = Field(..., min_length=1)  # [{name, text, ...}]
    export_artifacts: list[ExportArtifact] = Field(default_factory=list)
    confirmed_at: datetime | None = None
