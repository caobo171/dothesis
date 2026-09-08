"""Strip internal links that stopped resolving after a re-plan.

The writer removes an invented link at write time, judged against the backlog
as it stood in that run. `plan` reassigns and re-clusters, so a slug that was
real when a post was written can disappear from a later plan: five posts on the
2026-09-08 bank pointed at `/blog/vi/ly-thuyet-var`, a page the re-plan folded
away. Those links were not invented, they went stale, and no amount of care at
write time prevents it.

So this is a maintenance pass, not a gate: it re-checks every seed against the
slugs that resolve TODAY and unlinks the rest, keeping the anchor text. It
reports any post left under the internal-link floor rather than silently
repairing it, because a post that thin needs a writer, not a script.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .qa import MIN_INTERNAL_LINKS, internal_links, known_slugs, link_is_known
from .writer import normalise_internal_links


@dataclass
class RelinkStats:
    scanned: int = 0
    changed: int = 0
    removed: int = 0
    thin: list[str] = field(default_factory=list)
    dead: dict[str, int] = field(default_factory=dict)


def run(seed_dir: str, *, dry_run: bool = False,
        extra_slugs: set[str] | None = None) -> RelinkStats:
    stats = RelinkStats()
    known = known_slugs(seed_dir, extra_slugs)

    for name in sorted(os.listdir(seed_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(seed_dir, name)
        with open(path, encoding="utf-8") as fh:
            seed = json.load(fh)
        stats.scanned += 1

        body = seed.get("body") or ""
        for href in internal_links(body):
            if href.startswith("/") and not link_is_known(href, known):
                stats.dead[href] = stats.dead.get(href, 0) + 1

        cleaned, removed = normalise_internal_links(body, known)
        if not removed:
            continue
        stats.changed += 1
        stats.removed += removed
        surviving = [h for h in internal_links(cleaned) if h.startswith("/blog/")]
        if len(surviving) < MIN_INTERNAL_LINKS:
            stats.thin.append(seed.get("slug") or name)
        if not dry_run:
            seed["body"] = cleaned
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(seed, fh, ensure_ascii=False, indent=2)
                fh.write("\n")

    verb = "would unlink" if dry_run else "unlinked"
    print(f"relink: {stats.scanned} seed(s) scanned, {verb} {stats.removed} dead "
          f"link(s) in {stats.changed} post(s)")
    for href, count in sorted(stats.dead.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {count:>4}  {href}")
    if stats.thin:
        print(f"  {len(stats.thin)} post(s) now under the {MIN_INTERNAL_LINKS}-link "
              f"floor and need a writer: {', '.join(stats.thin[:5])}")
    return stats
