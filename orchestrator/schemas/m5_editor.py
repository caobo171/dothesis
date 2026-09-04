"""SP6.5: PendingEdit — a not-yet-accepted modification to a chapter's prose.

Sources are unified: paraphrase/translate/cite (from inline editor toolbar)
and chat_rewrite (from M5 NL-rewrite handler) all create the same record.
The editor's AiPending mark + accept/reject ribbon is a single UI surface
for all four sources.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator


# The inline selection actions. paraphrase/translate/cite/chat_rewrite are the
# originals; proofread…shorten are the "practical inline actions" ported from
# jenni — all of them land as a PendingEdit the user accepts or rejects.
PendingEditSource = Literal[
    "paraphrase", "translate", "cite", "chat_rewrite",
    "proofread", "improve", "humanize", "expand", "shorten",
]
ChapterName = Literal["intro", "lit_review", "methodology", "results", "conclusion"]


class PendingEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                                       # uuid4 hex
    chapter_name: ChapterName
    from_offset: int = Field(ge=0)                # char offset into chapter.prose at creation time
    to_offset: int = Field(ge=0)                  # >= from_offset; equal means insertion
    old_text: str                                 # must equal prose[from:to] when accept fires
    new_text: str
    source: PendingEditSource
    pending_at: datetime
    metadata: dict = Field(default_factory=dict)  # e.g. {"target_lang": "vi"} or {"reference_id": "..."}

    @model_validator(mode="after")
    def _validate_offset_range(self):
        """Enforce range invariant at construction time so accept-time slicing
        never silently produces empty/reversed text. from_offset == to_offset
        is allowed (insertion point for cite)."""
        if self.from_offset > self.to_offset:
            raise ValueError(
                f"from_offset ({self.from_offset}) must be <= to_offset ({self.to_offset})"
            )
        return self
