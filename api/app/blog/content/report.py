"""What the run actually produced: counts, volume, spend, and the shortfall.

The target is 1,000 posts, so the two numbers that matter are printed side by
side: how many pages the backlog can support, and how many exist on disk. Since
2026-09-08 the ceiling is the topic bank's, not the demand gate's — the gate
cuts nothing now — so a shortfall means the axes need expanding, not that
demand ran out.
"""
from __future__ import annotations

import csv
import os

from . import topic_bank_dir
from .plan import read_backlog
from .writer import default_out_dir

TARGET_POSTS = 1000


def _read_log(path: str) -> list[dict]:
    if not path or not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _count_seeds(seed_dir: str) -> tuple[int, int]:
    if not os.path.isdir(seed_dir):
        return 0, 0
    written = len([f for f in os.listdir(seed_dir)
                   if f.endswith(".json") and f != "categories.json"])
    rejected_dir = os.path.join(seed_dir, "rejected")
    rejected = len([f for f in os.listdir(rejected_dir) if f.endswith(".json")]) \
        if os.path.isdir(rejected_dir) else 0
    return written, rejected


def run(backlog_path: str | None = None, seed_dir: str | None = None,
        log_path: str | None = None) -> dict:
    backlog_path = backlog_path or os.path.join(topic_bank_dir(), "backlog.tsv")
    seed_dir = seed_dir or default_out_dir()
    log_path = log_path or os.path.join(os.path.dirname(os.path.abspath(seed_dir)),
                                        "write-log.tsv")

    rows = read_backlog(backlog_path) if os.path.isfile(backlog_path) else []
    per_category: dict[str, int] = {}
    per_archetype: dict[str, int] = {}
    for r in rows:
        per_category[r.category] = per_category.get(r.category, 0) + 1
        per_archetype[r.archetype] = per_archetype.get(r.archetype, 0) + 1

    log = _read_log(log_path)
    usd = sum(float(r.get("usd") or 0) for r in log)
    prompt_tokens = sum(int(r.get("prompt_tokens") or 0) for r in log)
    output_tokens = sum(int(r.get("output_tokens") or 0) for r in log)
    statuses: dict[str, int] = {}
    for r in log:
        statuses[r.get("status", "")] = statuses.get(r.get("status", ""), 0) + 1

    written, rejected = _count_seeds(seed_dir)
    summary = {
        "backlog_rows": len(rows),
        "volume_total": sum(r.search_volume for r in rows),
        "unmeasured": sum(1 for r in rows if r.gate_status == "unmeasured"),
        "per_category": per_category,
        "per_archetype": per_archetype,
        "seeds_written": written,
        "seeds_rejected": rejected,
        "usd": usd,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "statuses": statuses,
        "ceiling_shortfall": max(TARGET_POSTS - len(rows), 0),
        "written_shortfall": max(TARGET_POSTS - written, 0),
    }

    print(f"backlog: {summary['backlog_rows']:,} rows, "
          f"{summary['volume_total']:,} searches/month, "
          f"{summary['unmeasured']} unmeasured")
    if per_category:
        print("  by category")
        for c in sorted(per_category, key=lambda c: -per_category[c]):
            print(f"    {c:24} {per_category[c]:6,}")
    if per_archetype:
        print("  by archetype")
        for a in sorted(per_archetype, key=lambda a: -per_archetype[a]):
            print(f"    {a:24} {per_archetype[a]:6,}")

    print(f"seeds:   {written:,} written, {rejected} rejected  ({seed_dir})")
    if statuses:
        print("  log statuses: "
              + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())))
    print(f"spend:   ${usd:.2f}  ({prompt_tokens:,} prompt + {output_tokens:,} output tokens)")
    print(f"target:  {TARGET_POSTS:,} posts. "
          f"Backlog ceiling is {summary['backlog_rows']:,} "
          f"(short by {summary['ceiling_shortfall']:,}), "
          f"{summary['written_shortfall']:,} still to write.")
    if summary["ceiling_shortfall"]:
        print("         The ceiling is what the topic bank supplies. Expand another "
              "axis to raise it; the gate stopped cutting on 2026-09-08, so the "
              "shortfall is candidates, not demand.")
    return summary
