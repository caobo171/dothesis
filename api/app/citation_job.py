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
import signal
import sys
import threading
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("citation_job")

# The deep planner's whole point is that it gets to take its time. This is a
# safety net against a hung provider, not a performance budget.
_DEFAULT_TIMEOUT_S = int(os.getenv("CITATION_JOB_TIMEOUT_S", "900"))


def _arm_timeout(seconds: int, on_expiry) -> None:
    """Fail this job after `seconds` no matter where it is stuck.

    This constant existed and was never wired to anything. Measured
    consequence: a job spawned at 22:13 was still sitting at step 1 of 3 half an
    hour later, inside a deep search with a per-topic timeout but no cap on the
    number of topics. Nothing was going to stop it, and because the run row only
    leaves `running` in this process's `finally`, /tools/runs/active kept
    reporting a hung job as the user's live one — so the next screen they opened
    showed a spinner for work that was never coming back.

    Two layers, because one is not enough. SIGALRM raises inside the main thread
    and lets the normal except/finally close the run row and log the failure —
    but it only lands at an interruptible point, and a wedged socket read in a C
    extension may never reach one. The watchdog is the floor under that: it
    closes the row itself and then hard-exits, because a subprocess whose entire
    purpose is this one search has nothing left to wind down.
    """
    def _raise(_sig, _frm):
        raise TimeoutError(f"citation job exceeded {seconds}s")

    try:
        signal.signal(signal.SIGALRM, _raise)
        signal.alarm(seconds)
    except (AttributeError, ValueError):
        logger.warning("SIGALRM unavailable — relying on the watchdog alone")

    def _watchdog():
        time.sleep(seconds + 60)
        logger.error("watchdog: still alive %ds past the deadline — exiting", 60)
        try:
            on_expiry()
        finally:
            os._exit(1)

    threading.Thread(target=_watchdog, daemon=True).start()


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

    _arm_timeout(_DEFAULT_TIMEOUT_S, lambda: finish_tool_run(run_id, ok=False) if run_id else None)

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
        writes = {"literature_sources": merged, "citation_list": merged}

        # Derive the research gaps FROM the papers, now that there are papers.
        #
        # The backfill reconstructs M2 before any real search has run, so its
        # gaps are whatever the model recalled — and on a reconstructed import
        # they routinely came back empty, leaving the card saying "research_gaps
        # is empty" next to a literature module that looked otherwise complete.
        # Gaps are the one M2 field that is worthless when guessed: they are the
        # argument for the whole study, and a supervisor will ask which paper
        # each one comes from. find_research_gaps answers exactly that — it
        # cites the supporting papers by DOI from the list it was given.
        #
        # Only when empty: a gap the student wrote or approved outranks anything
        # derived here.
        m2_now = (row[1] if row else None) or {}
        if not (m2_now.get("research_gaps") or []):
            # Every outcome is logged, including "ran fine and found nothing".
            # This used to fail silently in two ways at once — an exception was
            # swallowed and an empty return logged nothing at all — so a card
            # reading "research_gaps is empty" next to N found papers was
            # indistinguishable from the job never having run. That is what made
            # the gaps look random: the same import produced gaps or not with no
            # way to tell which path it took.
            try:
                from orchestrator.tools.m2_literature import find_research_gaps
                gaps = find_research_gaps.func(merged)
                if gaps:
                    writes["research_gaps"] = gaps
                    logger.info("derived %d research gaps for %s", len(gaps), project_id)
                else:
                    logger.warning(
                        "gap derivation returned nothing for %s despite %d sources",
                        project_id, len(merged))
            except Exception:
                # The citations are the point; gaps are a bonus on top of them.
                logger.exception("gap derivation failed for %s", project_id)

        _store(project_id).commit_reconstructed(
            "M2", writes, reason="deep literature search (background)")
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
