"""backlog.tsv + the model -> seed JSON, gated in process, logged per row.

Resumable by design: one file per row, named from the row's priority and slug,
and a row whose file exists is skipped. That makes the run interruptible, which
matters more than throughput when a thousand posts are involved.

Internal links are normalised before QA sees the draft: a link to a page nobody
has planned is unlinked, keeping its anchor text. The model invents sibling
slugs no matter what the brief says, and a broken link is not worth a second
call, so the gate is only ever asked whether enough real links remain.

Each row gets at most two calls. The first writes the draft; if QA fails, the
second gets the failure list and repairs it. A second failure lands in
`rejected/` and the run continues, because one bad row must never stop the
batch. Read `rejected/` after every run: three rejects sharing a failure means
the prompt is wrong, not the model.
"""
from __future__ import annotations

import csv
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from . import repo_root
from .plan import read_backlog
from .prompts import build_prompt, build_repair_prompt

# `_LINK_RE` and `link_is_known` come from the gate on purpose: the writer must
# strip exactly the links the gate would fail, and a second link grammar here
# would drift from it.
from .qa import _LINK_RE, UNMEASURED_STATUSES, check_post, link_is_known

LOG_COLUMNS = ("slug", "status", "attempts", "unlinked", "prompt_tokens",
               "output_tokens", "usd", "seconds", "failures")

# Entries the brief's link list should offer. Three real targets (category
# route, one sibling, /landing) against a floor of four distinct links is what
# pushed the model into inventing a fourth, so a thin row is topped up from its
# own category before the prompt is built.
LINK_LIST_MIN = 6
LINK_LIST_MAX = 8
_FIXED_LINKS = 2  # the category route and /landing, always on the list

STATUS_OK = "ok"
STATUS_REPAIRED = "repaired"
STATUS_REJECTED = "rejected"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def default_out_dir() -> str:
    return os.path.join(repo_root(), "api", "data", "blog-seeds", "vi", "posts")


def default_backlog_path() -> str:
    return os.path.join(repo_root(), "docs", "seo", "topic-bank", "backlog.tsv")


def seed_filename(row) -> str:
    return f"{row.priority:04d}-{row.slug}.json"


def parse_model_json(text: str) -> dict:
    """The model returns a json object. Tolerate a code fence around it."""
    cleaned = _FENCE_RE.sub("", (text or "").strip())
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("model returned json that is not an object")
    return data


def link_slugs_for(row, rows) -> list[str]:
    """The row's own siblings, topped up so the brief lists `LINK_LIST_MIN`.

    Top-ups are ordered the way `plan._round_robin` already orders rows:
    measured before unmeasured, highest volume first inside each tier. An
    unmeasured row's volume is a guess, so it must not outrank a measured page
    just because the guess was large. The tier test goes through the gate's
    `UNMEASURED_STATUSES` rather than a literal, so the legacy `family-inferred`
    spelling and the current one sort the same way.

    The row's `sibling_slugs` are not mutated: they are a pipeline field that
    ends up in the published seed, and a link the model was merely offered is
    not a sibling relationship.
    """
    picked: list[str] = []
    seen = {row.slug}
    for slug in row.sibling_slugs:
        if slug not in seen:
            seen.add(slug)
            picked.append(slug)
    want = LINK_LIST_MIN - _FIXED_LINKS
    if len(picked) < want:
        others = sorted(
            (r for r in rows if r.category == row.category and r.slug not in seen),
            key=lambda r: (r.gate_status in UNMEASURED_STATUSES, -r.search_volume, r.slug))
        for other in others:
            picked.append(other.slug)
            seen.add(other.slug)
            if len(picked) >= want:
                break
    return picked[:LINK_LIST_MAX - _FIXED_LINKS]


def normalise_internal_links(body: str, slugs: set[str]) -> tuple[str, int]:
    """Unlink every internal target the gate would not resolve.

    `[EFA](/blog/vi/efa-la-gi)` becomes `EFA` when no page and no backlog row
    owns that slug. The model keeps inventing plausible siblings, and telling it not to
    has not worked; an invented link is a broken link whichever way it arrived,
    so it is removed here instead of costing a repair call. Returns the body and
    how many links were removed (occurrences, not distinct targets).
    """
    stripped = 0

    def replace(match):
        nonlocal stripped
        if match.group(0).startswith("!"):
            return match.group(0)  # an image, not a link
        href = (match.group(2) or "").strip()
        if not href.startswith("/") or link_is_known(href, slugs):
            return match.group(0)  # external, an in-page anchor, or a real page
        stripped += 1
        return match.group(1)

    return _LINK_RE.sub(replace, body or ""), stripped


# A citation the model wrapped in backticks: `(Hair và cộng sự, 2010)`. It renders
# as a code span, which reads as a variable name rather than a source.
_CODE_CITATION_RE = re.compile(r"`(\([^`()\n]{3,80}?\d{4}[a-z]?\))`")


def normalise_citations(body: str) -> tuple[str, int]:
    """Strip backticks around author-year citations.

    Measured on the first five real posts: 33 of the citations in three of them
    arrived as code spans, even though the contract asks for plain text. A
    deterministic strip is cheaper and safer than a repair call, and it changes
    nothing the QA gate reads (the allowlist match is on the parenthesised text).
    """
    fixed = 0

    def replace(match):
        nonlocal fixed
        fixed += 1
        return match.group(1)

    return _CODE_CITATION_RE.sub(replace, body or ""), fixed


_FAQ_H2_RE = re.compile(r"^## .*(Câu hỏi thường gặp|Hỏi đáp|FAQ).*$", re.IGNORECASE | re.MULTILINE)
MIN_INTERNAL_LINKS = 4


def link_floor(row) -> int:
    """How many distinct internal links the gate will demand of this row."""
    return MIN_INTERNAL_LINKS + (1 if row.gate_status in UNMEASURED_STATUSES else 0)


def ensure_read_more(body: str, row, link_slugs: list[str], titles: dict[str, str],
                     known: set[str] | None = None,
                     minimum: int = MIN_INTERNAL_LINKS) -> tuple[str, int]:
    """Guarantee the internal-link floor with a "Đọc thêm" line built from the brief.

    After unknown links are stripped, a post can be left with one or two real
    links; the repair call then tends to invent new unknown targets and fail
    again (measured: 2 of the first 32 posts). WELE's structure closes with a
    "đọc thêm" block anyway, so instead of paying for a second model call the
    block is added mechanically from the same list the brief offered, right
    before the FAQ so the close paragraph stays last. Returns (body, links added).
    """
    from .qa import internal_links, link_is_known  # noqa: PLC0415 — keep qa stdlib-importable

    present = set(internal_links(body))
    have = [h for h in present if h.startswith("/blog/")]
    if len(have) >= minimum:
        return body, 0
    candidates = [f"/blog/vi/{slug}" for slug in link_slugs] + [f"/blog/vi/chu-de/{row.category}"]
    added: list[str] = []
    for href in candidates:
        if href in present or href in added:
            continue
        # Only a target the gate resolves: a sibling the brief named but the
        # backlog does not carry would be stripped again on the next pass.
        if known is not None and not link_is_known(href, known):
            continue
        added.append(href)
        if len(have) + len(added) >= minimum + 1:
            break
    if not added:
        return body, 0

    def label(href: str) -> str:
        slug = href.rsplit("/", 1)[-1]
        if "/chu-de/" in href:
            return f"chủ đề {slug.replace('-', ' ')}"
        return titles.get(slug) or slug.replace("-", " ")

    line = "Đọc thêm: " + ", ".join(f"[{label(h)}]({h})" for h in added) + ".\n\n"
    m = _FAQ_H2_RE.search(body)
    if m:
        body = body[:m.start()] + line + body[m.start():]
    else:
        body = body.rstrip() + "\n\n" + line
    return body, len(added)


def seed_from(row, produced: dict) -> dict:
    """Model output plus the pipeline's own fields.

    The pipeline fields are written from the backlog row, never from the model.
    A model that drifts on the slug or the category would otherwise corrupt the
    corpus in a way no reader would notice until the links broke.
    """
    return {
        "schema": "dothesis-blog-seed/1",
        "title": (produced.get("title") or "").strip(),
        "slug": row.slug,
        "locale": "vi",
        "meta_title": (produced.get("meta_title") or "").strip(),
        "meta_description": (produced.get("meta_description") or "").strip(),
        "focus_keyword": row.focus_keyword,
        "secondary_keywords": row.secondary_keywords,
        "focus_keyword_volume": row.search_volume,
        "excerpt": (produced.get("excerpt") or "").strip(),
        "category": row.category,
        "tags": [t for t in (produced.get("tags") or []) if isinstance(t, str)],
        "archetype": row.archetype,
        "family": row.family,
        "source_batch": "blog-content-engine",
        "gate_status": row.gate_status,
        "sibling_slugs": row.sibling_slugs,
        "images": [],
        "body": produced.get("body") or "",
    }


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)  # a killed run never leaves a half-written seed behind


class _Log:
    """write-log.tsv, appended under a lock so parallel workers do not interleave."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8", newline="") as fh:
                csv.writer(fh, delimiter="\t", lineterminator="\n").writerow(LOG_COLUMNS)

    def append(self, **row) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8", newline="") as fh:
            csv.writer(fh, delimiter="\t", lineterminator="\n").writerow(
                [row.get(c, "") for c in LOG_COLUMNS])


def run(backlog_path: str | None = None, out_dir: str | None = None,
        limit: int | None = None, workers: int = 6, model: str | None = None,
        budget_usd: float = 40.0, dry_run: bool = False, force: bool = False,
        client=None, log_path: str | None = None,
        skills_dir: str | None = None) -> dict:
    backlog_path = backlog_path or default_backlog_path()
    out_dir = out_dir or default_out_dir()
    rows = read_backlog(backlog_path)
    titles = {r.slug: r.focus_keyword for r in rows}
    known = {r.slug for r in rows}
    rejected_dir = os.path.join(out_dir, "rejected")
    log_path = log_path or os.path.join(os.path.dirname(os.path.abspath(out_dir)),
                                        "write-log.tsv")

    todo = []
    skipped = 0
    for row in rows:
        if os.path.isfile(os.path.join(out_dir, seed_filename(row))) and not force:
            skipped += 1
            continue
        todo.append(row)
        if limit and len(todo) >= limit:
            break

    if dry_run:
        prompts = [build_prompt(r, titles, skills_dir, link_slugs_for(r, rows)) for r in todo]
        chars = sum(len(p) for p in prompts)
        # ~3 characters per token for mixed Vietnamese and markdown, and about
        # 3,500 output tokens for a 2,000-word post. An estimate, printed as one.
        est_in = chars // 3
        est_out = 3500 * len(todo)
        from .llm import usd_for  # noqa: PLC0415

        summary = {"planned": len(todo), "skipped": skipped, "written": 0, "repaired": 0,
                   "rejected": 0, "errors": 0, "failed": 0, "usd": 0.0, "unlinked": 0,
                   "estimated_usd": usd_for(est_in, est_out), "stopped_on_budget": False}
        print(f"write --dry-run: {len(todo)} rows to write, {skipped} already on disk")
        print(f"      prompt is {len(prompts[0]) if prompts else 0:,} chars for the first row")
        print(f"      estimated ${summary['estimated_usd']:.2f} at "
              f"{est_in:,} in / {est_out:,} out tokens")
        return summary

    if client is None:
        from .llm import LunaClient  # noqa: PLC0415 — openai stays off the qa import path

        client = LunaClient(model=model)

    log = _Log(log_path)
    state = {"usd": 0.0, "written": 0, "repaired": 0, "rejected": 0, "errors": 0,
             "unlinked": 0, "stopped_on_budget": False}
    lock = threading.Lock()

    def budget_left() -> bool:
        with lock:
            if state["usd"] >= budget_usd:
                state["stopped_on_budget"] = True
                return False
            return True

    def write_one(row) -> None:
        attempts = 0
        spent = 0.0
        seconds = 0.0
        unlinked = 0
        prompt_tokens = output_tokens = 0
        produced: dict = {}
        failures: list[str] = []
        link_slugs = link_slugs_for(row, rows)
        try:
            prompt = build_prompt(row, titles, skills_dir, link_slugs)
            for attempt in range(2):
                completion = client.complete_json(prompt)
                attempts += 1
                spent += completion.usd
                seconds += completion.seconds
                prompt_tokens += completion.prompt_tokens
                output_tokens += completion.output_tokens
                produced = parse_model_json(completion.text)
                # Before the gate sees it: an internal link to a page nobody has
                # planned is unlinked. The gate then cannot fail on an unknown
                # target at all, and the repair pass is spent only on a post
                # that is genuinely short of real links.
                body, stripped = normalise_internal_links(produced.get("body") or "", known)
                body, _cites = normalise_citations(body)
                # The top-up aims at the floor this row is actually held to. A
                # page with no measured volume needs one more link than the
                # default, and topping up to four would hand the repair call a
                # failure the mechanical block could have prevented.
                body, _added = ensure_read_more(body, row, link_slugs, titles, known,
                                                minimum=link_floor(row))
                produced["body"] = body
                unlinked += stripped
                seed = seed_from(row, produced)
                failures, _warns, _stats = check_post(seed, known)
                if not failures:
                    _write_json(os.path.join(out_dir, seed_filename(row)), seed)
                    with lock:
                        state["usd"] += spent
                        state["unlinked"] += unlinked
                        if attempt == 0:
                            state["written"] += 1
                        else:
                            state["repaired"] += 1
                    log.append(slug=row.slug,
                               status=STATUS_OK if attempt == 0 else STATUS_REPAIRED,
                               attempts=attempts, unlinked=unlinked,
                               prompt_tokens=prompt_tokens,
                               output_tokens=output_tokens, usd=f"{spent:.5f}",
                               seconds=f"{seconds:.1f}", failures="")
                    return
                if attempt == 0:
                    # `produced` carries the already-stripped body, so the retry
                    # repairs the draft the checker actually read.
                    prompt = build_repair_prompt(row, produced, failures, titles,
                                                 skills_dir, link_slugs)

            _write_json(os.path.join(rejected_dir, seed_filename(row)),
                        seed_from(row, produced))
            with lock:
                state["usd"] += spent
                state["unlinked"] += unlinked
                state["rejected"] += 1
            log.append(slug=row.slug, status=STATUS_REJECTED, attempts=attempts,
                       unlinked=unlinked, prompt_tokens=prompt_tokens,
                       output_tokens=output_tokens,
                       usd=f"{spent:.5f}", seconds=f"{seconds:.1f}",
                       failures=" | ".join(failures))
        except Exception as exc:  # noqa: BLE001 — one bad row must not stop the batch
            with lock:
                state["usd"] += spent
                state["unlinked"] += unlinked
                state["errors"] += 1
            log.append(slug=row.slug, status=STATUS_ERROR, attempts=attempts,
                       unlinked=unlinked, prompt_tokens=prompt_tokens,
                       output_tokens=output_tokens,
                       usd=f"{spent:.5f}", seconds=f"{seconds:.1f}",
                       failures=f"{type(exc).__name__}: {exc}")

    if workers <= 1:
        for row in todo:
            if not budget_left():
                break
            write_one(row)
    else:
        # Submitted in waves of `workers` so the budget is re-checked between
        # waves. A single pool submission would spend the whole backlog before
        # the first result came back.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(todo), workers):
                if not budget_left():
                    break
                list(pool.map(write_one, todo[start:start + workers]))

    summary = {
        "planned": len(todo),
        "skipped": skipped,
        "written": state["written"],
        "repaired": state["repaired"],
        "rejected": state["rejected"],
        "errors": state["errors"],
        "failed": state["rejected"] + state["errors"],
        "usd": state["usd"],
        "unlinked": state["unlinked"],
        "stopped_on_budget": state["stopped_on_budget"],
    }
    print(f"write: {summary['written']} written, {summary['repaired']} repaired, "
          f"{summary['rejected']} rejected, {summary['errors']} errors, "
          f"{summary['skipped']} skipped")
    if summary["unlinked"]:
        # A number that keeps climbing means the brief's link list is too thin
        # for the archetype, not that the model is misbehaving.
        print(f"       {summary['unlinked']} invented internal link(s) unlinked")
    print(f"       spent ${summary['usd']:.2f} of ${budget_usd:.2f}"
          + (" (stopped on budget)" if summary["stopped_on_budget"] else ""))
    print(f"       log: {log_path}")
    if summary["rejected"]:
        print(f"       read {rejected_dir}: three rejects sharing a failure means the "
              f"prompt is wrong, not the model")
    return summary
