#!/usr/bin/env python
"""Delete tool-run input/output files past their 30-day retention.

The retention window is a promise the web app makes to the student ("File được
giữ đến …"). Nothing else deletes these objects, so if this is not scheduled
the promise is simply false and every thesis ever run through a document tool
stays on S3 forever. The systemd timer that runs it is installed by
scripts/deploy.sh.

Only the FILES go. The tool_runs row stays, because it is a billing record and
reclaiming storage must not erase the evidence that someone was charged.

Usage:
    ./scripts/purge_tool_run_files.py                 # purge what has expired
    ./scripts/purge_tool_run_files.py --dry-run       # count, change nothing
    ./scripts/purge_tool_run_files.py --limit 100     # cap one pass
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
log = logging.getLogger("purge_tool_run_files")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=500,
                    help="most runs to purge in one pass (default 500)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be purged, delete nothing")
    args = ap.parse_args()

    from app.db import get_session_factory
    from app.models import ToolRun
    from app.tool_artifacts import purge_expired
    from sqlalchemy import or_, select

    now = datetime.now(timezone.utc)
    Session = get_session_factory()
    with Session() as db:
        if args.dry_run:
            due = db.scalars(
                select(ToolRun)
                .where(ToolRun.files_expire_at.is_not(None),
                       ToolRun.files_expire_at < now)
                .where(or_(ToolRun.input_s3_uri.is_not(None),
                           ToolRun.output_s3_uri.is_not(None)))
                .limit(args.limit)
            ).all()
            log.info("dry run: %d run(s) due for purge", len(due))
            return 0
        purged = purge_expired(db, now=now, limit=args.limit)
        log.info("purged files for %d run(s)", purged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
