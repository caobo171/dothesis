"""M5 Writing & Finalization output schema (SP6 — chapter-by-chapter compose + S3 export)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from orchestrator.schemas.m5_editor import PendingEdit


ChapterName = Literal["intro", "lit_review", "methodology", "results", "conclusion"]


class ChapterDraft(BaseModel):
    """One composed chapter with provenance info."""
    name: ChapterName
    prose: str
    citations_used: list[str] = Field(default_factory=list)
    uncited_warnings: list[str] = Field(default_factory=list)
    # SP6.5 — additive; defaults empty so existing M5Output data still validates
    pending_edits: list[PendingEdit] = Field(default_factory=list)


class ExportArtifact(BaseModel):
    kind: Literal["docx", "pdf", "latex", "md"]
    s3_key: str = ""
    download_url: str = ""
    size_bytes: int = Field(default=0, ge=0)
    # SP1 field — DEPRECATED but kept for back-compat with auto-mode readers
    uri: str = ""


class M5Output(BaseModel):
    chapters: dict[str, dict] = Field(default_factory=dict)
    bibliography: str = ""
    export_artifacts: list[ExportArtifact] = Field(default_factory=list)
    # SP1 — preserved for back-compat with engine-fallback auto-mode
    sections: list[dict] = Field(default_factory=list)
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def _require_artifacts_on_confirm(self):
        """When confirmed, the agent must have produced all 5 chapters + at
        least the docx export. Pre-confirm partials remain valid."""
        if self.confirmed_at is None:
            return self
        required = {"intro", "lit_review", "methodology", "results", "conclusion"}
        present = set(self.chapters.keys())
        missing = required - present
        if missing:
            raise ValueError(f"M5 confirm requires all 5 chapters; missing: {sorted(missing)}")
        if not any(a.kind == "docx" for a in self.export_artifacts):
            raise ValueError("M5 confirm requires at least the docx export artifact")
        return self
