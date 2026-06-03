"""M3 Research Design output schema. Mirrors PRD §6.3.6.

SP4 makes paradigm-specific fields explicit and enforces them via a
@model_validator that only fires when `confirmed_at` is being set
(in-progress partials remain valid)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .common import Paradigm

MixedDesignType = Literal["sequential_explanatory", "sequential_exploratory"]


class M3Output(BaseModel):
    # Shared common fields
    paradigm: Paradigm
    design: str = Field(..., description="e.g. PLS-SEM, Thematic Analysis, Sequential Explanatory")
    tool: str = Field(..., description="SmartPLS, NVivo, SPSS, ...")
    sampling_strategy: str
    target_sample_size: int = Field(..., gt=0)
    confirmed_at: datetime | None = None

    # Quant-only (required when paradigm == quantitative, or part of mixed).
    # Design merge (2026-06): conceptual_model now carries the full graph
    # — {nodes:[{id,label,questions:[...]}], edges:[{id,source,target,
    # hypothesis,effect_type}]}. The prior separate `scale_items` field is
    # gone; per-construct Likert items live on each node's `questions` list.
    conceptual_model: dict | None = None
    hypotheses: list[dict] | None = None

    # Qual-only (required when paradigm == qualitative, or part of mixed)
    themes: list[dict] | None = None
    interview_guide: dict | None = None
    purposive_criteria: list[dict] | None = None

    # Mixed-only
    mixed_design_type: MixedDesignType | None = None

    # Backward-compat fields (existing M5 consumers read these names)
    constructs: list[dict] = Field(default_factory=list)
    questionnaire_text: str | None = None

    @model_validator(mode="after")
    def _require_by_paradigm(self):
        """Paradigm-specific required-field check, only fires when confirmed."""
        if self.confirmed_at is None:
            return self

        if self.paradigm == "quantitative":
            if not self.conceptual_model:
                raise ValueError("quantitative paradigm requires conceptual_model when confirmed")

        elif self.paradigm == "qualitative":
            if not self.themes:
                raise ValueError("qualitative paradigm requires themes when confirmed")
            if not self.interview_guide:
                raise ValueError("qualitative paradigm requires interview_guide when confirmed")
            if not self.purposive_criteria:
                raise ValueError("qualitative paradigm requires purposive_criteria when confirmed")

        elif self.paradigm == "mixed":
            if not self.mixed_design_type:
                raise ValueError("mixed paradigm requires mixed_design_type when confirmed")
            if not self.conceptual_model:
                raise ValueError("mixed paradigm requires conceptual_model (quant artifact) when confirmed")
            if not (self.themes and self.interview_guide and self.purposive_criteria):
                raise ValueError("mixed paradigm requires qual artifacts when confirmed")

        return self
