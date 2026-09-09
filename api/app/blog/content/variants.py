"""Rotate a repeated narrative sentence through its interchangeable phrasings.

A bank generated from archetype skeletons drifts into saying one thing one way.
WELE found it first: one connective sentence stood in 89 of its 166 verb
articles, and a reader who landed on two of them had read one page twice. The
fix there, and here, is not to rewrite the family. It is to give the sentence
several honest phrasings and hand them out.

Three rules make this safe rather than spun:

- **A group is interchangeable, not merely similar.** Every member says the same
  thing to the same reader. The pools live in `docs/seo/prose-variants.json`
  where they can be read and argued with, not in this file.
- **Existing phrasings are members, not competition.** Most of these sentences
  already had four to eight wordings spread unevenly across the bank. Rotating
  over the union levels them; rotating one phrasing into another would just move
  the concentration.
- **Nothing sourced, numbered or quoted from the software is in a pool.** A
  threshold repeats because there is one right answer, and a menu path repeats
  because there is one menu. `qa.py` exempts both from the shared-prose check
  for the same reason.

The assignment is positional: files in sorted order, occurrences in document
order, the next member each time. That makes the result reproducible and
idempotent — a second run sees the same posts in the same order, each still
holding one member of the group, and hands out the same phrasing again.
"""
from __future__ import annotations

import dataclasses
import io
import json
import os
import re

DEFAULT_POOLS = "docs/seo/prose-variants.json"

# Mirrors `qa.prose_sentences`: a replacement may only touch narrative. A
# heading, a table row and a fenced block are quoted structure, and a sentence
# that happens to sit in one is not this pass's business.
_SKIP_PREFIXES = ("#", "|", ">")


@dataclasses.dataclass
class Stats:
    posts: int = 0            # posts in the directory
    touched: int = 0          # posts this pass changed
    replacements: int = 0     # occurrences rewritten
    unchanged: int = 0        # occurrences already holding the assigned phrasing
    per_group: dict = dataclasses.field(default_factory=dict)


def default_pools_path() -> str:
    """`docs/seo/prose-variants.json`, found from this file rather than from cwd."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    return os.path.join(root, DEFAULT_POOLS)


def load_groups(path: str | None, locale: str) -> list[list[str]]:
    with io.open(path or default_pools_path(), encoding="utf-8") as fh:
        doc = json.load(fh)
    return [g["members"] for g in doc.get(locale, []) if len(g.get("members") or []) > 1]


# Inline code and emphasis marks. The bank writes software names as
# `` `Total Variance Explained` `` in most posts and bare in a few, so a matcher
# that reads the raw line would find one spelling and miss the other. Both the
# gate's `prose_sentences` and this pass compare with the marks removed, and the
# pool holds the marked-up form, so an unmarked occurrence is written back
# marked up — the convention the rest of the corpus already follows.
_MARK_RE = re.compile(r"[`*_]")


def _strip_marks(line: str) -> tuple[str, list[int]]:
    """`(text without marks, offset in `line` of each surviving character)`."""
    kept, offsets = [], []
    for index, char in enumerate(line):
        if _MARK_RE.match(char):
            continue
        kept.append(char)
        offsets.append(index)
    return "".join(kept), offsets


def _group_pattern(members: list[str]) -> re.Pattern:
    """One alternation over the group's mark-free forms, longest first.

    Longest first matters: several of these families nest — `Không có một con số
    cố định áp dụng cho mọi đề tài.` ends the same way as three shorter members —
    and a shorter alternative matching first would leave the head of the longer
    one stranded in front of the replacement.
    """
    ordered = sorted((_MARK_RE.sub("", m) for m in members), key=len, reverse=True)
    return re.compile("|".join(re.escape(m) for m in ordered))


def _rewrite_line(line: str, members: list[str], pattern: re.Pattern,
                  counters: list[int], index: int, stats: Stats) -> str:
    """Every occurrence in one line, left to right, each taking the next member.

    Matched on the mark-free text and spliced back into the real line, so a match
    that spans an inline-code span is replaced whole rather than leaving a stray
    backtick behind. The scan resumes after the text just written, which is
    itself a member of the group and would otherwise be rewritten forever.
    """
    pos = 0
    while pos < len(line):
        bare, offsets = _strip_marks(line[pos:])
        match = pattern.search(bare)
        if not match:
            break
        start = pos + offsets[match.start()]
        end = pos + offsets[match.end() - 1] + 1
        pick = members[counters[index] % len(members)]
        counters[index] += 1
        if line[start:end] == pick:
            stats.unchanged += 1
        else:
            stats.replacements += 1
            stats.per_group[index] = stats.per_group.get(index, 0) + 1
        line = line[:start] + pick + line[end:]
        pos = start + len(pick)
    return line


def apply_to_body(body: str, groups: list[list[str]], counters: list[int],
                  stats: Stats) -> str:
    """Rewrite one body, advancing `counters` as occurrences are consumed."""
    patterns = [_group_pattern(members) for members in groups]
    out = []
    fenced = False
    for line in body.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            out.append(line)
            continue
        if fenced or stripped.startswith(_SKIP_PREFIXES):
            out.append(line)
            continue
        for index, (members, pattern) in enumerate(zip(groups, patterns)):
            line = _rewrite_line(line, members, pattern, counters, index, stats)
        out.append(line)
    return "\n".join(out)


def run(seed_dir: str, locale: str, pools_path: str | None = None,
        dry_run: bool = False) -> Stats:
    groups = load_groups(pools_path, locale)
    stats = Stats()
    if not groups:
        return stats
    counters = [0] * len(groups)

    for name in sorted(os.listdir(seed_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(seed_dir, name)
        with io.open(path, encoding="utf-8") as fh:
            post = json.load(fh)
        body = post.get("body") or ""
        if not body:
            continue
        stats.posts += 1

        rewritten = apply_to_body(body, groups, counters, stats)
        if rewritten == body:
            continue
        stats.touched += 1
        if dry_run:
            continue
        post["body"] = rewritten
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(post, ensure_ascii=False, indent=2) + "\n")

    return stats
