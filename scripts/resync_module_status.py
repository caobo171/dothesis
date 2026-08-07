#!/usr/bin/env python
"""Recompute projects.module_status from the context_store it is derived from.

`module_status` is a cache — models.py says so: "Derived from context_store via
orchestrator.state.compute_status_map and persisted here for fast UI reads —
NEVER the source of truth." It is written when a slice is committed, so a
project whose slices stop changing keeps whatever the rules said on the day it
was last touched.

That matters whenever a definition-of-done changes. dod_analysis learned to
accept an imported write-up and dod_writing was added, which moved a lot of
projects from in_progress to done — but only for projects that get written to
again. Everyone else keeps seeing the old answer, and is asked to redo work the
system now agrees is finished.

Safe to run repeatedly: it only ever rewrites the cache to match what
compute_status_map already says, and touches nothing else.

    python scripts/resync_module_status.py            # report only
    python scripts/resync_module_status.py --apply    # write
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_SLICES = ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing")


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATABASE_URL not set and not found in .env")


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    from sqlalchemy import create_engine, text

    from orchestrator.state import ContextStore, compute_status_map

    engine = create_engine(_database_url(), connect_args={"connect_timeout": 30})
    select = ("select p.id, p.module_status, "
              + ", ".join("cs." + s for s in _SLICES)
              + " from projects p join context_store cs on cs.project_id = p.id")

    changed: list[tuple[str, dict]] = []
    with engine.begin() as conn:
        for row in conn.execute(text(select)).mappings().fetchall():
            computed = compute_status_map(
                ContextStore(**{s: row[s] for s in _SLICES})).model_dump()
            cached = row["module_status"] or {}
            diff = {m: (cached.get(m), computed[m])
                    for m in computed if cached.get(m) != computed[m]}
            if not diff:
                continue
            changed.append((str(row["id"]), diff))
            if apply:
                conn.execute(
                    text("update projects set module_status = cast(:v as jsonb) "
                         "where id = :p"),
                    {"v": json.dumps(computed), "p": row["id"]})

    for pid, diff in changed:
        print(f"{pid[:8]}  " + ", ".join(
            f"{m}: {was or '-'} -> {now}" for m, (was, now) in sorted(diff.items())))
    verb = "resynced" if apply else "would resync"
    print(f"\n{verb} {len(changed)} project(s)."
          + ("" if apply else "  Re-run with --apply to write."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
