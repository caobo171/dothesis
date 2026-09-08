"""Vietnamese seed JSON + the model -> the English edition of the same bank.

The Vietnamese bank is 979 posts that already passed the gate, so the translator
is not writing: the structure, the numbers, the tables, the citations and the
links are decided, and the model's whole job is to say the same things in
English a graduate student would actually write. What it produces is checked by
the same gate on its English rules, which is why `qa.LOCALE_RULES` and the
translation prompt quote each other rather than restating the same three strings.

Resumable the way `write` is: one file per source post, and a source whose
English seed already exists is skipped. `source_slug` on the English seed is
what makes that work, and it is also the key of the vi -> en map the link pass
needs, so it is written even though nothing else reads it.

Two passes, and the order is forced. A translated body still points at
`/blog/vi/<vietnamese-slug>`, and the English slug of the post on the other end
of that link is not known until that post has been translated. So the rewrite is
a second pass over the finished directory (`rewrite_links`), it is idempotent,
and anything it cannot map is left to `relink.py`, which unlinks a dead target
and keeps its anchor text.

The one number worth watching is the word floor. Vietnamese writes each syllable
as a separate word, so the gate's whitespace count reads high on the source and
low on a faithful translation: the 979 seeds run a median of 3,025 Vietnamese
tokens, and the 27 under 2,000 are the ones that can land under the 1,500-word
English floor. That is not a reason to lower the floor, it is a signal that the
translation dropped something, and the repair attempt is told exactly that.
"""
from __future__ import annotations

import csv
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from . import repo_root
from .prompts import build_translate_prompt, build_translate_repair_prompt

# The gate's own link grammar and slug rules, not a second copy: what this
# module writes has to be exactly what the gate reads.
from .qa import (CATEGORY_SEGMENT, DEFAULT_LOCALE, SCHEMA, SLUG_MAX, _LINK_RE,
                 check_post, known_slugs, slugify)

# `_write_json` is the writer's atomic write (tmp file, then `os.replace`), so a
# killed run never leaves half a seed behind. One implementation, not two.
from .writer import _write_json, parse_model_json

SOURCE_LOCALE = DEFAULT_LOCALE   # "vi"
TARGET_LOCALE = "en"

LOG_COLUMNS = ("source_slug", "slug", "status", "attempts", "prompt_tokens",
               "output_tokens", "usd", "seconds", "failures")

STATUS_OK = "ok"
STATUS_REPAIRED = "repaired"
STATUS_REJECTED = "rejected"
STATUS_ERROR = "error"

# Fields the English edition inherits verbatim. `category`, `archetype` and
# `family` are taxonomy: the English post is the same post and belongs in the
# same places. `image_url` and `images` are the artwork, which is not language.
#
# `gate_status` is here for a reason worth stating: it decides whether this post
# is held to the doubled bar, and the honest answer is the source's. Nobody
# measured the English query, but nobody measured a translation either way, and
# reclassifying every page as unmeasured would put the whole bank on a bar its
# own source was never written to. The source's demand evidence is the only
# evidence there is, so it carries.
#
# `focus_keyword_volume` deliberately does not carry. It is a Vietnamese search
# volume for a Vietnamese query in the Vietnamese market, and copying it onto an
# English page would be a measurement nobody made.
CARRIED_FIELDS = ("category", "archetype", "family", "gate_status", "image_url",
                  "images")

# The three authored strings the model must return, plus the keyword fields.
PRODUCED_FIELDS = ("title", "meta_title", "meta_description", "excerpt",
                   "focus_keyword", "secondary_keywords", "tags", "body")

# ~3 characters per token for a prompt that is mostly Vietnamese prose and
# markdown, and about 3,500 output tokens for one translated post. An estimate,
# printed as one.
_CHARS_PER_TOKEN = 3
_EST_OUTPUT_TOKENS = 3500


def default_src_dir() -> str:
    return os.path.join(repo_root(), "api", "data", "blog-seeds", SOURCE_LOCALE, "posts")


def default_out_dir() -> str:
    return os.path.join(repo_root(), "api", "data", "blog-seeds", TARGET_LOCALE, "posts")


def default_log_path(out_dir: str) -> str:
    """Beside the output directory, the way the writer puts `write-log.tsv`."""
    return os.path.join(os.path.dirname(os.path.abspath(out_dir)), "translate-log.tsv")


# ------------------------------------------------------------------- sources


def _seed_files(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    return sorted(f for f in os.listdir(directory)
                  if f.endswith(".json") and f != "categories.json")


def _split_prefix(filename: str) -> tuple[str, str]:
    """`0042-cfa.json` -> `("0042", "cfa")`, `cfa.json` -> `("", "cfa")`."""
    stem = filename[:-len(".json")] if filename.endswith(".json") else filename
    head, _, rest = stem.partition("-")
    return (head, rest) if head.isdigit() and rest else ("", stem)


def load_sources(src_dir: str) -> list[dict]:
    """Every readable Vietnamese seed, in filename order.

    Each entry carries the seed plus the two things the target file needs from
    the source's name: the numeric prefix, so the English directory sorts into
    the same publishing order, and a stable discriminator for a slug collision.
    """
    out = []
    for name in _seed_files(src_dir):
        path = os.path.join(src_dir, name)
        try:
            with open(path, encoding="utf-8") as fh:
                seed = json.load(fh)
        except Exception:  # a seed that does not parse is the gate's problem
            continue
        if not isinstance(seed, dict) or not seed.get("slug"):
            continue
        prefix, _stem = _split_prefix(name)
        out.append({"file": name, "prefix": prefix, "seed": seed,
                    "slug": seed["slug"]})
    return out


def scan_output(out_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    """`(source slug -> path, english slug -> source slug)` for what is written.

    Resume keys on the *source* slug, because the English slug of a post is not
    known until it has been translated. That is the whole reason `source_slug`
    is written into the English seed.
    """
    done: dict[str, str] = {}
    taken: dict[str, str] = {}
    for name in _seed_files(out_dir):
        path = os.path.join(out_dir, name)
        try:
            with open(path, encoding="utf-8") as fh:
                seed = json.load(fh)
        except Exception:
            continue
        if not isinstance(seed, dict):
            continue
        source = seed.get("source_slug") or ""
        slug = seed.get("slug") or ""
        if source:
            done[source] = path
        if slug:
            taken[slug] = source
    return done, taken


# ---------------------------------------------------------------------- slugs


# An apostrophe is dropped, not turned into a separator. `slugify` maps every
# run of non-alphanumerics to a hyphen, which is right for Vietnamese and wrong
# for the possessive that half these keywords carry: `Cronbach's Alpha` would
# become `cronbach-s-alpha`. The result still normalises to itself, which is
# what the gate checks.
_APOSTROPHES = str.maketrans("", "", "'\u2019\u02bc")


def _truncate(slug: str) -> str:
    """`SLUG_MAX` characters, cut at a hyphen so the last word is not halved."""
    if len(slug) <= SLUG_MAX:
        return slug
    cut = slug[:SLUG_MAX]
    return (cut.rsplit("-", 1)[0] if "-" in cut else cut).strip("-")


def english_slug(focus_keyword: str, source_slug: str, discriminator: str,
                 taken: dict[str, str]) -> str:
    """The English slug for one post: from the English focus keyword, stable.

    Stable means an assigned slug never moves. The slug is a pure function of
    the English focus keyword, so nothing about the run enters it, and the
    collision tie-break is `discriminator`, the source's own numeric prefix in
    the frozen Vietnamese bank: unique per source and fixed. It is not a counter
    over the output directory, which would renumber a post whenever a sibling
    was written before it.

    `taken` maps an English slug to the source that owns it and is read back off
    disk at the start of every run, so a resumed batch hands each post the slug
    it already has instead of treating it as a clash. That read-back is what
    carries stability across runs: which of two colliding posts gets the bare
    keyword is decided once, by whichever reached the gate first, and after that
    the directory decides.
    """
    text = (focus_keyword or "").translate(_APOSTROPHES)
    base = _truncate(slugify(text)) or _truncate(slugify(source_slug))
    owner = taken.get(base)
    if owner is None or owner == source_slug:
        return base
    candidate = _truncate(f"{base}-{discriminator}") if discriminator else ""
    owner = taken.get(candidate)
    if candidate and (owner is None or owner == source_slug):
        return candidate
    # Only reachable if two sources share a discriminator, which the Vietnamese
    # bank's filenames do not. Kept so a hand-made directory degrades into a
    # longer slug rather than two seeds claiming one URL.
    n = 2
    while _truncate(f"{base}-{discriminator}-{n}") in taken:
        n += 1
    return _truncate(f"{base}-{discriminator}-{n}")


def target_filename(prefix: str, slug: str) -> str:
    """Keep the source's numeric prefix so both editions sort the same way."""
    return f"{prefix}-{slug}.json" if prefix else f"{slug}.json"


# ----------------------------------------------------------------- the seed


def _strings(value) -> list[str]:
    return [v.strip() for v in (value or []) if isinstance(v, str) and v.strip()]


def translated_seed(source: dict, produced: dict, slug: str) -> dict:
    """The model's English fields plus the source's own, in seed order.

    The pipeline fields come from the source and never from the model, for the
    same reason the writer takes them from the backlog row: a model that drifts
    on the category or the archetype corrupts the corpus in a way nobody notices
    until the routing breaks.
    """
    return {
        "schema": SCHEMA,
        "title": (produced.get("title") or "").strip(),
        "slug": slug,
        "locale": TARGET_LOCALE,
        "meta_title": (produced.get("meta_title") or "").strip(),
        "meta_description": (produced.get("meta_description") or "").strip(),
        "focus_keyword": (produced.get("focus_keyword") or "").strip(),
        "secondary_keywords": _strings(produced.get("secondary_keywords")),
        "excerpt": (produced.get("excerpt") or "").strip(),
        "category": source.get("category"),
        "tags": _strings(produced.get("tags")),
        "archetype": source.get("archetype"),
        "family": source.get("family"),
        "source_batch": "blog-translate",
        "source_locale": source.get("locale") or SOURCE_LOCALE,
        "source_slug": source.get("slug"),
        "gate_status": source.get("gate_status"),
        "sibling_slugs": _strings(source.get("sibling_slugs")),
        "image_url": source.get("image_url"),
        "images": source.get("images") or [],
        "body": produced.get("body") or "",
    }


# ------------------------------------------------------------------- the log


class _Log:
    """translate-log.tsv, appended under a lock so workers do not interleave."""

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


# -------------------------------------------------------------------- the run


def run(src_dir: str | None = None, out_dir: str | None = None,
        limit: int | None = None, workers: int = 6, model: str | None = None,
        budget_usd: float = 40.0, dry_run: bool = False, force: bool = False,
        client=None, log_path: str | None = None,
        skills_dir: str | None = None) -> dict:
    src_dir = src_dir or default_src_dir()
    out_dir = out_dir or default_out_dir()
    log_path = log_path or default_log_path(out_dir)
    rejected_dir = os.path.join(out_dir, "rejected")

    sources = load_sources(src_dir)
    done, taken = scan_output(out_dir)

    todo = []
    skipped = 0
    for item in sources:
        if item["slug"] in done and not force:
            skipped += 1
            continue
        todo.append(item)
        if limit and len(todo) >= limit:
            break

    if dry_run:
        # Prompts are built one at a time and thrown away: the whole bank at
        # once is 40MB of strings for a number that only needs the character
        # count.
        chars = 0
        first = 0
        for i, item in enumerate(todo):
            size = len(build_translate_prompt(item["seed"], skills_dir))
            chars += size
            if i == 0:
                first = size
        est_in = chars // _CHARS_PER_TOKEN
        est_out = _EST_OUTPUT_TOKENS * len(todo)
        from .llm import usd_for  # noqa: PLC0415 — openai stays off the qa import path

        summary = {"planned": len(todo), "skipped": skipped, "written": 0,
                   "repaired": 0, "rejected": 0, "errors": 0, "failed": 0,
                   "usd": 0.0, "estimated_usd": usd_for(est_in, est_out),
                   "stopped_on_budget": False}
        print(f"translate --dry-run: {len(todo)} post(s) to translate, "
              f"{skipped} already in {out_dir}")
        print(f"          prompt is {first:,} chars for the first post")
        print(f"          estimated ${summary['estimated_usd']:.2f} at "
              f"{est_in:,} in / {est_out:,} out tokens")
        return summary

    if client is None:
        from .llm import LunaClient  # noqa: PLC0415

        client = LunaClient(model=model)

    # Link targets in the source bodies are Vietnamese and still point at the
    # Vietnamese bank, so they are resolved against it. `rewrite_links` moves
    # them to their English targets once every post exists.
    source_known = known_slugs(src_dir)

    log = _Log(log_path)
    state = {"usd": 0.0, "written": 0, "repaired": 0, "rejected": 0, "errors": 0,
             "stopped_on_budget": False}
    lock = threading.Lock()

    def budget_left() -> bool:
        with lock:
            if state["usd"] >= budget_usd:
                state["stopped_on_budget"] = True
                return False
            return True

    def reserve(focus_keyword: str, item: dict, previous: str | None) -> str:
        """Claim an English slug for this source, releasing the one it held."""
        with lock:
            if previous and taken.get(previous) == item["slug"]:
                del taken[previous]
            slug = english_slug(focus_keyword, item["slug"], item["prefix"], taken)
            taken[slug] = item["slug"]
            return slug

    def translate_one(item) -> None:
        source = item["seed"]
        attempts = 0
        spent = seconds = 0.0
        prompt_tokens = output_tokens = 0
        produced: dict = {}
        failures: list[str] = []
        slug = ""
        try:
            prompt = build_translate_prompt(source, skills_dir)
            for attempt in range(2):
                completion = client.complete_json(prompt)
                attempts += 1
                spent += completion.usd
                seconds += completion.seconds
                prompt_tokens += completion.prompt_tokens
                output_tokens += completion.output_tokens
                produced = parse_model_json(completion.text)
                slug = reserve(produced.get("focus_keyword") or "", item, slug or None)
                seed = translated_seed(source, produced, slug)
                with lock:
                    known = source_known | set(taken)
                failures, _warns, _stats = check_post(seed, known)
                if not failures:
                    _write_json(os.path.join(out_dir, target_filename(item["prefix"], slug)),
                                seed)
                    with lock:
                        state["usd"] += spent
                        state["written" if attempt == 0 else "repaired"] += 1
                    log.append(source_slug=item["slug"], slug=slug,
                               status=STATUS_OK if attempt == 0 else STATUS_REPAIRED,
                               attempts=attempts, prompt_tokens=prompt_tokens,
                               output_tokens=output_tokens, usd=f"{spent:.5f}",
                               seconds=f"{seconds:.1f}", failures="")
                    return
                if attempt == 0:
                    prompt = build_translate_repair_prompt(source, produced, failures,
                                                           skills_dir)

            _write_json(os.path.join(rejected_dir, target_filename(item["prefix"], slug)),
                        translated_seed(source, produced, slug))
            with lock:
                state["usd"] += spent
                state["rejected"] += 1
                # A rejected post owns no URL, so it must not hold a slug the
                # next post in the batch could legitimately use.
                if taken.get(slug) == item["slug"]:
                    del taken[slug]
            log.append(source_slug=item["slug"], slug=slug, status=STATUS_REJECTED,
                       attempts=attempts, prompt_tokens=prompt_tokens,
                       output_tokens=output_tokens, usd=f"{spent:.5f}",
                       seconds=f"{seconds:.1f}", failures=" | ".join(failures))
        except Exception as exc:  # noqa: BLE001 — one bad post must not stop the batch
            with lock:
                state["usd"] += spent
                state["errors"] += 1
                if slug and taken.get(slug) == item["slug"]:
                    del taken[slug]
            log.append(source_slug=item["slug"], slug=slug, status=STATUS_ERROR,
                       attempts=attempts, prompt_tokens=prompt_tokens,
                       output_tokens=output_tokens, usd=f"{spent:.5f}",
                       seconds=f"{seconds:.1f}",
                       failures=f"{type(exc).__name__}: {exc}")

    if workers <= 1:
        for item in todo:
            if not budget_left():
                break
            translate_one(item)
    else:
        # Waves of `workers`, so the budget is re-checked between them. One pool
        # submission would spend the whole bank before the first result landed.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(todo), workers):
                if not budget_left():
                    break
                list(pool.map(translate_one, todo[start:start + workers]))

    summary = {
        "planned": len(todo),
        "skipped": skipped,
        "written": state["written"],
        "repaired": state["repaired"],
        "rejected": state["rejected"],
        "errors": state["errors"],
        "failed": state["rejected"] + state["errors"],
        "usd": state["usd"],
        "stopped_on_budget": state["stopped_on_budget"],
    }
    print(f"translate: {summary['written']} written, {summary['repaired']} repaired, "
          f"{summary['rejected']} rejected, {summary['errors']} errors, "
          f"{summary['skipped']} skipped")
    print(f"           spent ${summary['usd']:.2f} of ${budget_usd:.2f}"
          + (" (stopped on budget)" if summary["stopped_on_budget"] else ""))
    print(f"           log: {log_path}")
    remaining = len(sources) - summary["skipped"] - summary["written"] - summary["repaired"]
    if remaining > 0:
        print(f"           {remaining} post(s) still untranslated, so the link pass "
              f"would map into an incomplete bank; finish the batch first")
    else:
        print(f"           every post is translated: run `translate --rewrite-links` "
              f"to point the bodies at their English targets")
    if summary["rejected"]:
        print(f"           read {rejected_dir}: three rejects sharing a failure means "
              f"the prompt is wrong, not the model")
    return summary


# ------------------------------------------------------------ the link pass

# A translated body still points at `/blog/vi/<vietnamese-slug>`, because the
# translator was told to copy every href exactly: the English slug on the other
# end of that link does not exist yet when the post is written. This pass runs
# once the directory is finished, off the map the run itself built, and it is
# idempotent because it only ever recognises a Vietnamese target and an English
# one is left alone.

_HREF_PARTS_RE = re.compile(r"^([^#?]*)([#?].*)?$")


def slug_map(out_dir: str) -> dict[str, str]:
    """`vietnamese slug -> english slug`, read off the finished English seeds."""
    _done, taken = scan_output(out_dir)
    return {source: slug for slug, source in taken.items() if source}


def rewrite_href(href: str, mapping: dict[str, str]) -> str | None:
    """The English target for a Vietnamese href, or None to leave it alone.

    None covers three cases that all mean the same thing here: the link is not
    ours (`/landing`, an anchor, an external URL), it is already English, or it
    points at a post nothing translated. The last one is a dead link and it is
    `relink.py`'s job, not this pass's, so it is reported and left in place.
    """
    parts = _HREF_PARTS_RE.match(href or "")
    core = (parts.group(1) or "").rstrip("/")
    suffix = parts.group(2) or ""
    home = f"/blog/{SOURCE_LOCALE}"
    if core == home:
        return f"/blog/{TARGET_LOCALE}{suffix}"
    if not core.startswith(home + "/"):
        return None
    rest = core[len(home) + 1:]
    if rest.startswith(CATEGORY_SEGMENT + "/"):
        # The category route keeps the segment it has. `CATEGORY_SEGMENT` is the
        # only place it is spelled, and the gate's link grammar reads the same
        # constant, so pointing the English edition at an English segment later
        # is one edit in `qa.py` and nothing here.
        return f"/blog/{TARGET_LOCALE}/{CATEGORY_SEGMENT}/{rest.split('/', 1)[1]}{suffix}"
    target = mapping.get(rest)
    return f"/blog/{TARGET_LOCALE}/{target}{suffix}" if target else None


def rewrite_body(body: str, mapping: dict[str, str]) -> tuple[str, int, list[str]]:
    """`(body, links rewritten, hrefs that stayed Vietnamese)`."""
    rewritten = 0
    unmapped: list[str] = []

    def replace(match):
        nonlocal rewritten
        if match.group(0).startswith("!"):
            return match.group(0)  # an image, not a link
        href = (match.group(2) or "").strip()
        target = rewrite_href(href, mapping)
        if target is None:
            if href.startswith(f"/blog/{SOURCE_LOCALE}"):
                unmapped.append(href)
            return match.group(0)
        if target == href:
            return match.group(0)
        rewritten += 1
        # Rebuilt rather than patched in place; these bodies carry no link
        # titles, and the gate reads the target, not the syntax around it.
        return f"[{match.group(1)}]({target})"

    return _LINK_RE.sub(replace, body or ""), rewritten, unmapped


class RewriteStats:
    """What one link pass did. Public so the CLI and the tests read one shape."""

    __slots__ = ("scanned", "changed", "rewritten", "unmapped", "relink")

    def __init__(self):
        self.scanned = 0
        self.changed = 0
        self.rewritten = 0
        self.unmapped: dict[str, int] = {}
        self.relink = None


def rewrite_links(out_dir: str | None = None, *, dry_run: bool = False,
                  run_relink: bool = True) -> RewriteStats:
    """Point every internal link in the English bank at its English target.

    Idempotent: run it twice and the second run changes nothing, because a
    `/blog/en/...` href is never a candidate. Run it after the last post is
    translated, never during, since the map is only complete then.
    """
    out_dir = out_dir or default_out_dir()
    mapping = slug_map(out_dir)
    stats = RewriteStats()

    for name in _seed_files(out_dir):
        path = os.path.join(out_dir, name)
        with open(path, encoding="utf-8") as fh:
            seed = json.load(fh)
        stats.scanned += 1

        body, rewritten, unmapped = rewrite_body(seed.get("body") or "", mapping)
        for href in unmapped:
            stats.unmapped[href] = stats.unmapped.get(href, 0) + 1
        # The siblings ride the same map: an English post listing Vietnamese
        # slugs as its neighbours is a link nobody can follow. An entry with no
        # English counterpart is kept as it is, which is what makes a second run
        # a no-op instead of a delete.
        siblings = [mapping.get(s, s) for s in _strings(seed.get("sibling_slugs"))]
        if body == seed.get("body") and siblings == _strings(seed.get("sibling_slugs")):
            continue
        stats.changed += 1
        stats.rewritten += rewritten
        if not dry_run:
            seed["body"] = body
            seed["sibling_slugs"] = siblings
            _write_json(path, seed)

    verb = "would rewrite" if dry_run else "rewrote"
    print(f"translate --rewrite-links: {stats.scanned} seed(s) scanned, {verb} "
          f"{stats.rewritten} link(s) in {stats.changed} post(s), "
          f"{len(mapping)} slug(s) in the map")
    if stats.unmapped:
        total = sum(stats.unmapped.values())
        print(f"  {total} link(s) to {len(stats.unmapped)} untranslated post(s), "
              f"left for relink:")
        for href, count in sorted(stats.unmapped.items(), key=lambda kv: -kv[1])[:10]:
            print(f"  {count:>4}  {href}")

    if run_relink:
        # One unlinker for the whole engine. Whatever this pass could not map is
        # judged by the same predicate the gate uses, and unlinked with its
        # anchor text kept.
        from .relink import run as relink_run  # noqa: PLC0415

        stats.relink = relink_run(out_dir, dry_run=dry_run)
    return stats
