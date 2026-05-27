"""M4 Data Analysis output schema (SP5 — adaptive analysis with real parsers)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DataType = Literal["SPSS", "SmartPLS", "CB-SEM", "Qualitative", "Mixed", "Unknown"]
Parser = Literal["regex", "llm_fallback", "stub"]


class StepResult(BaseModel):
    """One outline step's parsed output. The `parser` field records which path
    produced the values so we can audit regex coverage over time."""
    step_name: str
    table: list[dict] = Field(default_factory=list)
    thresholds_met: bool | None = None
    interpretation: str = ""
    raw_paste_excerpt: str = ""
    parser: Parser = "regex"


class M4Output(BaseModel):
    data_type_detected: DataType
    analysis_outline: dict                                  # {sections: [...], confirmed_by_user: bool}
    data_paste: str = ""                                    # capped at 50KB by the agent
    results: dict[str, dict] = Field(default_factory=dict)  # step_name → StepResult dict
    qual_codes: list[dict] = Field(default_factory=list)
    qual_themes: list[dict] = Field(default_factory=list)
    custom_analyses: list[dict] = Field(default_factory=list)
    # Existing field — preserved for back-compat with M5 readers
    interpretations: dict = Field(default_factory=dict)
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def _require_artifacts_on_confirm(self):
        """Paradigm-specific minimum artifacts when confirmed. Fires only when
        confirmed_at is set — in-progress partials remain valid."""
        if self.confirmed_at is None:
            return self
        if self.data_type_detected == "Qualitative":
            if not self.qual_codes:
                raise ValueError("qualitative analysis requires qual_codes when confirmed")
            if not self.qual_themes:
                raise ValueError("qualitative analysis requires qual_themes when confirmed")
        elif self.data_type_detected in ("SPSS", "SmartPLS", "CB-SEM"):
            if not self.results:
                raise ValueError(
                    f"{self.data_type_detected} analysis requires results when confirmed"
                )
        elif self.data_type_detected == "Mixed":
            if not self.results:
                raise ValueError("mixed analysis requires quant results when confirmed")
            if not self.qual_codes or not self.qual_themes:
                raise ValueError("mixed analysis requires qual_codes + qual_themes when confirmed")
        return self
