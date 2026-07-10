"""Intake helpers — assess and import a student's existing work.

v1 provides `merge_import`: seed `ContextStore` slices from a user-supplied blob
(e.g. "I already have a topic and a methodology"). This is the data path behind
the `POST /projects/{id}/import` endpoint — the first half of "enter at any
step". A later phase adds an assessment agent that classifies uploaded prose
into slices automatically; this function is the deterministic merge it feeds.
"""
from __future__ import annotations

import json
import logging
import os

from orchestrator.state import ContextStore

logger = logging.getLogger(__name__)

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


def _assess_llm():
    # Route through the engine-wide factory (ORCHESTRATOR_LLM_ROUTE) so the whole
    # engine is switchable. temperature 0.2 + the per-request timeout are this
    # site's original settings, preserved so native behavior is unchanged.
    from orchestrator.llm import get_orchestrator_llm
    return get_orchestrator_llm(
        temperature=0.2,
        timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
    )


def assess_work(text: str, llm=None) -> dict:
    """Classify free-form existing work into proposed context_store slices.

    Reads whatever the student pastes (an abstract, a methodology section, a
    rough draft) and asks the LLM which thesis components are present, extracting
    each into its slice. Returns a blob shaped for merge_import — only the slices
    the model can populate; unknown keys are dropped. The assessment is a
    PROPOSAL the user reviews before committing (never silently seeded).

    `llm` is injectable for tests. Returns {} on empty text or LLM/parse failure
    so the caller degrades gracefully (the user can still fill fields manually).
    """
    if not text or not text.strip():
        return {}
    llm = llm or _assess_llm()
    prompt = (
        "You are assessing a student's existing thesis work. Read the text and "
        "extract whatever thesis components are clearly present into this JSON "
        "shape (include a slice ONLY when the text genuinely supports it; omit "
        "anything you'd have to invent):\n"
        '{\n'
        '  "m1_topic": {"research_title", "field", "research_type", '
        '"target_population", "scope", "objectives": [..], "research_questions": [..]},\n'
        '  "m2_literature": {"research_state_summary", "theoretical_framework", '
        '"research_gaps": [..]},\n'
        '  "m3_design": {"paradigm", "design", "sampling_strategy", '
        '"target_sample_size"},\n'
        '  "m4_analysis": {"data_type_detected", "results"},\n'
        '  "m5_writing": {"chapters": {"<name>": {"prose"}}}\n'
        '}\n\n'
        "Rules: extract only what the text supports; leave out uncertain fields; "
        "do NOT fabricate. Respond with ONLY the JSON object — no prose, no "
        "markdown.\n\n"
        f"Student's text:\n{text}"
    )
    try:
        raw = llm.invoke(prompt).content
        data = json.loads(_strip_code_fence(raw))
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items()
                if k in _SLICE_KEYS and isinstance(v, dict) and v}
    except Exception:  # noqa: BLE001 - best-effort; degrade to manual entry
        logger.exception("intake assess_work failed")
        return {}


def _strip_code_fence(s: str) -> str:
    """Remove leading/trailing markdown code fences from an LLM response."""
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()
