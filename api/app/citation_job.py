"""Deep literature search for M2, run OUT of the request.

Why this is a separate process rather than a few more seconds inside the
import: the deep planner expands one thesis topic into ~250 queries and wants
minutes, not seconds. Run inline it could never finish — _m2_real_sources caps
at 120s, so the future timed out and every real DOI it had already found was
discarded. Bounding the plan was tried and does not work (min_sources_deep does
not size the planner). The choice inside a request is "finishes but thin" or
"never finishes"; the only way out is to stop doing it inside a request.

So the import commits M2 with the fast shallow sources (a handful, on-topic,
immediately) and this job replaces them with the deep set when it lands. The
student gets a usable literature module at once and a real one shortly after,
instead of choosing between them.

Run as:  python -m app.citation_job --project-id <uuid> [--run-id <int>]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("citation_job")

# The deep planner's whole point is that it gets to take its time. This is a
# safety net against a hung provider, not a performance budget.
_DEFAULT_TIMEOUT_S = 900


def _store(project_id):
    from .agent_state import DbProjectStateStore
    from .db import get_engine
    from .routers.chat_v3 import _workspace_dir
    return DbProjectStateStore(get_engine(), project_id, _workspace_dir(project_id))


def run(project_id: str, run_id: int | None = None) -> int:
    """Search, then merge into M2. Returns the number of sources committed."""
    from sqlalchemy import text

    from .db import get_engine
    from .tool_billing import bump_progress, finish_tool_run

    def _progress(done: int, total: int) -> None:
        if run_id:
            bump_progress(run_id, done=done, total=total)

    ok = False
    try:
        _progress(0, 3)
        with get_engine().connect() as c:
            row = c.execute(
                text("select m1_topic, m2_literature from context_store "
                     "where project_id = :p"), {"p": project_id},
            ).first()
        m1 = (row[0] if row else None) or {}
        topic = str(m1.get("research_title") or "").strip()
        if not topic:
            # Nothing to search on. Not an error: the import may simply not have
            # reconstructed a topic, and a job that invents one would be worse.
            logger.warning("no research_title for %s — nothing to search", project_id)
            return 0

        rqs = [str(q) for q in (m1.get("research_questions") or [])]
        from orchestrator.tools.domain_sources import (
            classify_domain, dedup_sources, domain_supplement, search_query_en)
        from orchestrator.tools.m2_literature import scout_citations

        # English keywords only — the indexes are English catalogs and the
        # topic is usually Vietnamese. Deliberately NOT concatenating the
        # research questions after it: measured, appending that block halved
        # the results and quadrupled the time, and search_query_en has already
        # folded the questions into these keywords.
        query = search_query_en(topic, rqs) or topic
        logger.info("deep search for %s: %r", project_id, query[:120])

        _progress(1, 3)
        citations = scout_citations.func(
            query, min_n=30, deep=True,
            per_topic_timeout_s=int(os.getenv("CITATION_JOB_TOPIC_TIMEOUT_S", "60")),
        )
        sources = [{
            "title": c.get("title"), "authors": c.get("authors"), "year": c.get("year"),
            "venue": c.get("source") or c.get("venue"),
            "doi": c.get("doi"), "url": c.get("url"),
            "verified": bool(c.get("doi")),
        } for c in (citations or []) if (c.get("title") or "").strip()]

        domain = classify_domain(m1.get("field"), topic, rqs)
        if domain != "general":
            sources = dedup_sources(sources + domain_supplement(query, domain))
        sources = dedup_sources(sources)
        _progress(2, 3)

        if not sources:
            logger.warning("deep search found nothing for %s — leaving M2 as it is",
                           project_id)
            return 0

        # Never REPLACE with less than the import already had. The shallow
        # sources committed inline are real and on-topic; a deep run that came
        # back thin (provider trouble, an odd topic) must not cost the student
        # citations they could already see.
        existing = ((row[1] if row else None) or {}).get("literature_sources") or []
        merged = dedup_sources(sources + [s for s in existing if isinstance(s, dict)])

        # commit_reconstructed, not commit_slice: it PRESERVES the status of
        # downstream modules. Filling in citations grounds M2, it does not
        # invalidate the design or the analysis built on it — and telling a
        # student their finished M3/M4/M5 need re-review because their
        # bibliography improved is exactly the bug we just fixed elsewhere.
        _store(project_id).commit_reconstructed(
            "M2", {"literature_sources": merged, "citation_list": merged},
            reason="deep literature search (background)")
        logger.info("committed %d sources for %s", len(merged), project_id)
        ok = True
        return len(merged)
    except Exception:
        logger.exception("citation job failed for %s", project_id)
        return 0
    finally:
        _progress(3, 3)
        finish_tool_run(run_id, ok=ok)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--run-id", type=int, default=None)
    args = ap.parse_args(argv)
    run(args.project_id, args.run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
