"""Intake helpers — assess and import a student's existing work.

v1 provides `merge_import`: seed `ContextStore` slices from a user-supplied blob
(e.g. "I already have a topic and a methodology"). This is the data path behind
the `POST /projects/{id}/import` endpoint — the first half of "enter at any
step". A later phase adds an assessment agent that classifies uploaded prose
into slices automatically; this function is the deterministic merge it feeds.
"""
from __future__ import annotations

from orchestrator.state import ContextStore

# The only slice fields a caller may import into (mirrors ContextStore columns).
_SLICE_KEYS = ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing")


def merge_import(cs: ContextStore, blob: dict) -> ContextStore:
    """Return a NEW ContextStore with the blob's slices merged in.

    - Only known slice keys are accepted; unknown keys are ignored (never error).
    - Each imported slice is merged field-wise over whatever was already there
      and tagged `_source="imported"`, so downstream steps can tell agent-
      generated work from user-provided work (and assess it rather than redo it).
    - Untouched slices are left exactly as they were.
    """
    data = cs.model_dump()
    for key in _SLICE_KEYS:
        incoming = blob.get(key)
        if isinstance(incoming, dict):
            data[key] = {**(data.get(key) or {}), **incoming, "_source": "imported"}
    return ContextStore(**data)
