"""The MCP tool surface — one registry entry per tool.

Every tool is a thin forward to a DoThesis REST endpoint, carrying the caller's
own bearer, so the API's auth, ownership checks, quotas and credit debits all
apply unchanged. This module holds NO business logic; if a tool needs to decide
something, that decision belongs in the API where the web app gets it too.

WHAT BELONGS HERE, AND WHAT DOESN'T
-----------------------------------
A good MCP tool is short, self-contained, and useful mid-conversation. The
DoThesis app is better than a chat window at anything long-running and stateful
— it streams, it shows the context panel, it renders artifacts. So the surface
is: the stateless helpers (humanize, rhythm, citations), the read-only views a
student might want without switching tabs (credits, projects, artifacts), and
ONE long operation (starting a thesis) which returns a job id to poll rather
than pretending a chat can wait ten minutes.

TIERS drive the rate limit (ratelimit.py): `light` reads cost nothing, `model`
is a model round-trip, `heavy` spends credits and starts a job.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Tool:
    name: str
    tier: str                       # light | model | heavy
    description: str
    schema: dict
    # (args) -> (method_path, json_body). The bearer is added by the caller.
    request: Callable[[dict], tuple[str, dict]]
    # Pulled out of the response for the audit log's output_chars.
    text_of: Callable[[dict], str] = lambda r: ""


def _s(**props) -> dict:
    return {"type": "object", "properties": props}


def _req(schema: dict, *names: str) -> dict:
    return {**schema, "required": list(names)}


TOOLS: list[Tool] = [
    Tool(
        name="humanize",
        tier="model",
        description=(
            "Re-voice already-written academic prose so it reads less AI-generated, "
            "while freezing every number, table reference, term and citation (a rewrite "
            "that changes one is discarded and the original returned). Reduces the "
            "AI-detection smell; it is NOT a plagiarism/similarity tool and does NOT "
            "guarantee passing any detector. Work section by section."),
        schema=_req(_s(
            text={"type": "string", "description": "Passage to re-voice."},
            user_anchor={"type": "string", "description":
                         "~150 words the USER wrote themselves; required if the "
                         "result is error='no_anchor'. Never fabricate it."},
            language={"type": "string", "default": "vi"},
        ), "text"),
        request=lambda a: ("/api/v1/humanize", {
            "text": a.get("text", ""),
            "user_anchor": a.get("user_anchor"),
            "language": a.get("language", "vi")}),
        text_of=lambda r: str(r.get("text") or ""),
    ),

    Tool(
        name="writing_rhythm",
        tier="light",
        description=(
            "Measure how MECHANICAL a passage's sentence rhythm is (0-1, higher = more "
            "machine-even), based on sentence-length variation and formulaic connector "
            "density. This is NOT an AI detector and does not predict Turnitin, GPTZero "
            "or any commercial tool — it cannot see perplexity. Use it as concrete "
            "writing feedback ('your sentences are all the same length'), never as a "
            "verdict on whether text will be flagged."),
        schema=_req(_s(
            text={"type": "string", "description": "Passage to analyse (3+ sentences)."},
        ), "text"),
        request=lambda a: ("/api/v1/tools/writing-rhythm", {"text": a.get("text", "")}),
        text_of=lambda r: str(r.get("detail") or ""),
    ),

    Tool(
        name="verify_citation",
        tier="light",
        description=(
            "Check whether a reference actually exists, against CrossRef. Paste a DOI, "
            "a URL, or a full formatted reference. A DOI match is definitive; without "
            "one the lookup is a FUZZY bibliographic search and a hit only means "
            "something similar exists — compare the returned title/authors/year "
            "yourself. 'Not found' is not proof of fabrication: books, theses and many "
            "regional journals are not in CrossRef."),
        schema=_req(_s(
            reference={"type": "string", "description":
                       "A DOI, URL, or full reference string."},
        ), "reference"),
        request=lambda a: ("/api/v1/tools/verify-citation",
                           {"reference": a.get("reference", "")}),
        text_of=lambda r: str(r.get("title") or ""),
    ),

    Tool(
        name="check_credits",
        tier="light",
        description="The signed-in DoThesis account's remaining credit balance.",
        schema=_s(),
        request=lambda a: ("/api/v1/auth/me", {}),
        text_of=lambda r: str(r.get("credit") or ""),
    ),

    Tool(
        name="list_projects",
        tier="light",
        description=(
            "List the student's DoThesis thesis projects with their ids, names and "
            "current module. Call this first — the other project tools need an id, and "
            "students do not know their project UUIDs."),
        schema=_s(),
        request=lambda a: ("/api/v1/projects/list", {}),
    ),

    Tool(
        name="project_status",
        tier="light",
        description=(
            "Where a thesis project stands: name, current module, focus, and per-module "
            "status. Use list_projects first to get the id."),
        schema=_req(_s(
            project_id={"type": "string", "description": "From list_projects."},
        ), "project_id"),
        request=lambda a: (f"/api/v1/projects/{a.get('project_id', '')}", {}),
    ),

    Tool(
        name="get_artifacts",
        tier="light",
        description=(
            "The actual written content a project has produced so far (topic, "
            "literature, design, analysis, writing slices) — so it can be read, quoted "
            "or discussed in chat. Read-only; edits go through the DoThesis app."),
        schema=_req(_s(
            project_id={"type": "string", "description": "From list_projects."},
        ), "project_id"),
        request=lambda a: (f"/api/v1/projects/{a.get('project_id', '')}/artifacts", {}),
    ),

    Tool(
        name="start_thesis",
        tier="heavy",
        description=(
            "Start a full automated thesis run. SPENDS CREDITS and takes many minutes — "
            "confirm the topic with the user before calling, and never call it twice for "
            "the same request. Returns a job id; poll it with check_thesis_run. "
            "academic_level: bachelor|master|phd. citation_style: apa|mla|chicago|"
            "harvard|ieee|vancouver. model_tier: standard|premium."),
        schema=_req(_s(
            topic={"type": "string", "description": "The thesis topic."},
            research_question={"type": "string"},
            academic_level={"type": "string", "default": "master"},
            language={"type": "string", "default": "vi"},
            citation_style={"type": "string", "default": "apa"},
            model_tier={"type": "string", "default": "standard"},
        ), "topic"),
        request=lambda a: ("/api/v1/papers", {
            "topic": a.get("topic", ""),
            "research_question": a.get("research_question") or a.get("topic", ""),
            "academic_level": a.get("academic_level", "master"),
            "language": a.get("language", "vi"),
            "citation_style": a.get("citation_style", "apa"),
            "model_tier": a.get("model_tier", "standard"),
        }),
    ),

    Tool(
        name="check_thesis_run",
        tier="light",
        description=(
            "Progress of a thesis run started with start_thesis: status, phase and "
            "percentage. Poll this rather than calling start_thesis again."),
        schema=_req(_s(
            job_id={"type": "string", "description": "Returned by start_thesis."},
        ), "job_id"),
        request=lambda a: (f"/api/v1/jobs/{a.get('job_id', '')}", {}),
    ),
]

BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}

# tier -> tool names, for the rate limiter's per-tier counting.
TIERS: dict[str, list[str]] = {}
for _t in TOOLS:
    TIERS.setdefault(_t.tier, []).append(_t.name)


def as_mcp_schema() -> list[dict[str, Any]]:
    """The `tools/list` payload."""
    return [{"name": t.name, "description": t.description, "inputSchema": t.schema}
            for t in TOOLS]
