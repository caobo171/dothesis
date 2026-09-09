"""`python -m app.blog.cli <command>` — load, update and audit the blog bank.

Run it through the arch wrapper, which is the only way the venv's arm64 wheels
import from a Rosetta shell:

    cd api && ./run.sh python -m app.blog.cli create --dir ../docs/seo/fixtures/seeds

Every command prints one line per item and a summary, and exits 1 if anything
failed. Exit codes matter: these run in batches of hundreds, and a summary line
nobody reads is not a gate.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from . import STATUS_PUBLISHED, STATUS_SCHEDULED
from .audit import DEFAULT_THIN, audit_links, audit_seo
from .guard import assert_no_duplicate
from .index import BANNER, export_index
from .schedule import go_live_at, parse_start_date
from .seeds import (
    SeedError,
    category_index,
    create_from_seed,
    find_post,
    is_unmeasured,
    load_categories,
    load_dir,
    load_seed,
    seeds_locale,
    upsert_categories,
    upsert_from_seed,
)

# WELE ships 25 a week; this bank is forty times bigger, so forty a week puts
# a thousand posts live over about twenty-five weeks (design §15).
DEFAULT_PER_WEEK = 40


def _session() -> Session:
    from ..db import get_session_factory  # noqa: PLC0415

    return get_session_factory()()


def _load_inputs(args) -> tuple[list[tuple[Path, dict]], list[dict]]:
    """(seeds, categories) for `--dir` or `--file`.

    The categories are loaded at the locale the seeds in the same run carry, so
    `create --dir data/blog-seeds/en` upserts seven English category rows rather
    than rewriting the Vietnamese ones. A row naming its own `locale` still
    wins; `seeds_locale` returns None for a mixed batch, and then
    `load_categories` refuses instead of picking a language for the operator.
    """
    if args.dir:
        directory = Path(args.dir)
        seeds = load_dir(directory)
        return seeds, load_categories(directory, default_locale=seeds_locale(seeds))

    path = Path(args.file)
    seeds = [(path, load_seed(path))]
    locale = seeds_locale(seeds)
    # A single seed file still needs its categories. The canonical layout puts
    # categories.json beside `posts/`, so look one level up as well.
    for candidate in (path.parent, path.parent.parent):
        categories = load_categories(candidate, default_locale=locale)
        if categories:
            return seeds, categories
    return seeds, []


def _category_ids(db: Session, categories: list[dict], *, dry_run: bool) -> dict:
    """`{(locale, slug): id}` for the seeds to bind against."""
    if dry_run:
        # A dry run must not write, so report against what the database already
        # has and say which categories a real run would create.
        existing = category_index(db)
        for row in categories:
            if (row["locale"], row["slug"]) not in existing:
                print(f"  WOULD CREATE category: {row['slug']} [{row['locale']}]")
        return existing
    return upsert_categories(db, categories) if categories else category_index(db)


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------

def cmd_create(args) -> int:
    if args.reschedule:
        return _reschedule(args)

    if not args.dir and not args.file:
        print("create needs --dir or --file (or --reschedule)", file=sys.stderr)
        return 2

    seeds, categories = _load_inputs(args)
    now = datetime.now(timezone.utc)

    start = parse_start_date(args.schedule_start) if args.schedule_start else None
    if start:
        print(f"Scheduling {args.per_week} post(s)/week from {args.schedule_start}. "
              "Posts dated in the future insert as SCHEDULED and stay hidden until then.")
    else:
        print("No --schedule-start: every post goes live immediately.")

    created = skipped = refused = unmeasured = 0
    # The publishing slot is the loop index now (rule changed 2026-09-08): every
    # seed takes a slot in backlog order, unmeasured ones included, because they
    # publish like any other page. It still advances for a seed that is skipped
    # or refused, so a re-run gives the same post the same date as the first run.
    slot = 0
    with _session() as db:
        category_ids = _category_ids(db, categories, dry_run=args.dry_run)

        for path, seed in seeds:
            slug, locale = seed["slug"], seed["locale"]
            unproven = is_unmeasured(seed)
            go_live = go_live_at(slot, start, args.per_week) if start else now
            slot += 1

            # Existence first, guard second. A re-run of `create` over the same
            # directory must report SKIP, not accuse every post of duplicating
            # the copy of itself that the previous run inserted.
            if find_post(db, locale, slug) is not None:
                print(f"  SKIP    {slug} [{locale}] (already exists)")
                skipped += 1
                continue

            # Unlike WELE's create.blog, which skipped the guard entirely, this
            # enforces it per seed: at a thousand posts, "we will notice the
            # duplicate later" is not true.
            verdict = assert_no_duplicate(db, seed)
            if verdict.blocked:
                print(f"  REFUSE  {slug} [{locale}] ({path.name})")
                print(f"          {verdict.message}")
                refused += 1
                continue

            when = go_live.date().isoformat()
            state = "live now" if go_live <= now else f"scheduled {when}"
            if unproven:
                # Named on the line, not hidden in the summary: an operator
                # skimming a tranche should see which pages went out without a
                # number behind them.
                state += ", demand unmeasured"
            if args.dry_run:
                print(f"  WOULD CREATE {slug} [{locale}] ({state}, "
                      f"category: {seed['category']})")
                created += 1
                unmeasured += unproven
                continue

            action, _ = create_from_seed(db, seed, category_ids, go_live=go_live, now=now)
            print(f"  {'CREATE ' if action == 'created' else 'SKIP   '} {slug} "
                  f"[{locale}] ({state}, category: {seed['category']})")
            created += action == "created"
            skipped += action == "skipped"
            unmeasured += unproven and action == "created"

    verb = "would create" if args.dry_run else "created"
    print(f"\n=== Summary ===\nPosts {verb}: {created}\n"
          f"Of those, unmeasured (scheduled anyway, quality gates decided): {unmeasured}\n"
          f"Skipped: {skipped}\nRefused (duplicate intent): {refused}")
    return 1 if refused else 0


def _reschedule(args) -> int:
    """Re-spread the posts still waiting in status 2 (design §15)."""
    from ..models import BlogPost  # noqa: PLC0415

    if not args.schedule_start:
        print("--reschedule needs --schedule-start", file=sys.stderr)
        return 2
    start = parse_start_date(args.schedule_start)
    now = datetime.now(timezone.utc)

    moved = 0
    with _session() as db:
        # Status 2 only: a published post keeps the date it went out with, and a
        # draft has no date to move. Unmeasured pages are ordinary scheduled
        # posts since 2026-09-08, so they respread with everything else.
        rows = db.scalars(
            select(BlogPost).where(BlogPost.status == STATUS_SCHEDULED)
            .order_by(asc(BlogPost.scheduled_at), asc(BlogPost.created_at))
        ).all()
        for index, post in enumerate(rows):
            go_live = go_live_at(index, start, args.per_week)
            print(f"  {'WOULD MOVE' if args.dry_run else 'MOVE'} {post.slug} "
                  f"[{post.locale}] -> {go_live.date().isoformat()}")
            if not args.dry_run:
                post.scheduled_at = go_live
                post.published_at = go_live
            moved += 1
        if not args.dry_run:
            db.commit()

    print(f"\n=== Summary ===\nRescheduled: {moved} post(s) at {args.per_week}/week")
    return 0


# --------------------------------------------------------------------------
# update-from-seed
# --------------------------------------------------------------------------

def cmd_publish(args) -> int:
    """Send the first N waiting posts out today, and re-spread the rest.

    `--reschedule` can only move the queue through time, so bringing half the
    bank forward with it means dating those posts weeks in the past, on a site
    that had no blog then. That is false in the one field a reader and a crawler
    both trust. This publishes them as what they are: live today, newest first
    in backlog priority order, a minute apart so the listing has a stable order
    instead of hundreds of rows sharing one timestamp.
    """
    from ..models import BlogPost  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    with _session() as db:
        waiting = db.scalars(
            select(BlogPost).where(BlogPost.status == STATUS_SCHEDULED)
            .order_by(asc(BlogPost.scheduled_at), asc(BlogPost.created_at))
        ).all()
        if not waiting:
            print("Nothing is waiting: every post is already published or a draft.")
            return 0

        count = min(args.count, len(waiting))
        going, rest = waiting[:count], waiting[count:]

        for index, post in enumerate(going):
            # Highest priority is newest, so the listing leads with the pages
            # that earn the most.
            stamp = now - timedelta(minutes=index)
            if not args.dry_run:
                post.status = STATUS_PUBLISHED
                post.published_at = stamp
                post.scheduled_at = None

        moved = 0
        if args.rest_from and rest:
            start = parse_start_date(args.rest_from)
            for index, post in enumerate(rest):
                go_live = go_live_at(index, start, args.per_week)
                if not args.dry_run:
                    post.scheduled_at = go_live
                    post.published_at = go_live
                moved += 1

        if not args.dry_run:
            db.commit()

    verb = "Would publish" if args.dry_run else "Published"
    print(f"\n=== Summary ===\n{verb}: {count} post(s), live now")
    if args.rest_from:
        print(f"Rescheduled: {moved} post(s) at {args.per_week}/week from {args.rest_from}")
    else:
        print(f"Still waiting: {len(rest)} post(s), dates unchanged")
    return 0


def cmd_update_from_seed(args) -> int:
    if not args.dir and not args.file:
        print("update-from-seed needs --dir or --file", file=sys.stderr)
        return 2

    seeds, categories = _load_inputs(args)
    now = datetime.now(timezone.utc)
    updated = created = unchanged = skipped = 0

    with _session() as db:
        category_ids = _category_ids(db, categories, dry_run=args.dry_run)
        for path, seed in seeds:
            slug, locale = seed["slug"], seed["locale"]
            existing = find_post(db, locale, slug)
            # A seed with no row is usually one the duplicate-intent gate refused
            # at `create` time. Inserting it here would walk straight around that
            # gate, which is the one thing a content refresh must never do, so a
            # bulk refresh says so explicitly with `--only-existing`.
            if existing is None and args.only_existing:
                skipped += 1
                continue
            if args.dry_run:
                print(f"  {'WOULD UPDATE' if existing else 'WOULD CREATE'} "
                      f"{slug} [{locale}] ({path.name})")
                updated += bool(existing)
                created += not existing
                continue
            action, _ = upsert_from_seed(db, seed, category_ids, now=now,
                                         skip_unchanged=True)
            if action != "unchanged":
                print(f"  {action.upper():7} {slug} [{locale}]")
            updated += action == "updated"
            created += action == "created"
            unchanged += action == "unchanged"

    print(f"\n=== Summary ===\nUpdated: {updated}\nCreated: {created}\n"
          f"Unchanged: {unchanged}\nSkipped (no row): {skipped}")
    return 0


def cmd_retire(args) -> int:
    """Delete a post that has been merged into another one.

    Written for the `outlier` / `outliers` merge on 2026-09-09, where two posts
    chased one 6,600-volume keyword and differed only in the plural. Deleting a
    row by hand on the production box was the alternative, and this is the same
    operation with the three checks that a psql session does not make:

      * `--into` must name a post that exists in the same locale, so the merge
        target cannot be a typo and the redirect always has somewhere to land.
      * The row it is about to delete is printed in full first, and `--dry-run`
        stops there. Deleting a post deletes its body; there is no undo and no
        soft-delete column on `blog_posts`.
      * The redirect is printed as the exact line to add, because a deleted slug
        that nothing redirects is a 404 on a URL other posts already link to.

    ORDER MATTERS, and the command says so rather than assuming it: the redirect
    lives in `web/next.config.mjs`, which Next bakes at build time, so it has to
    be built and live BEFORE the row goes. The other way round leaves every
    internal link to the retired slug pointing at a 404 in the gap.
    """
    if args.slug == args.into:
        print("retire: --slug and --into are the same post", file=sys.stderr)
        return 2

    with _session() as db:
        doomed = find_post(db, args.locale, args.slug)
        if doomed is None:
            print(f"retire: no post {args.slug!r} [{args.locale}]", file=sys.stderr)
            return 1
        keeper = find_post(db, args.locale, args.into)
        if keeper is None:
            print(f"retire: --into {args.into!r} [{args.locale}] does not exist; "
                  "a redirect needs a destination", file=sys.stderr)
            return 1

        print(f"  retiring   {doomed.slug} [{doomed.locale}]")
        print(f"      title    {doomed.title}")
        print(f"      keyword  {doomed.focus_keyword!r} (volume {doomed.focus_keyword_volume})")
        print(f"      status   {doomed.status}, published {doomed.published_at}, "
              f"scheduled {doomed.scheduled_at}")
        print(f"      body     {len(doomed.body)} chars")
        print(f"  into       {keeper.slug} [{keeper.locale}] — {keeper.title}")
        print()
        print("  the redirect this needs, live BEFORE the row goes "
              "(web/next.config.mjs, then a web build):")
        print(f'    {{ source: "/blog/{doomed.locale}/{doomed.slug}", '
              f'destination: "/blog/{keeper.locale}/{keeper.slug}", permanent: true }},')
        print()

        if args.dry_run:
            print("=== Summary ===\nDry run, nothing deleted.")
            return 0

        db.delete(doomed)
        db.commit()

    print(f"=== Summary ===\nDeleted: {args.slug} [{args.locale}]\n"
          f"Run export-index to refresh docs/blog-index.md.")
    return 0


# --------------------------------------------------------------------------
# audits
# --------------------------------------------------------------------------

def cmd_audit_seo(args) -> int:
    with _session() as db:
        report = audit_seo(db, locale=args.locale, thin_floor=args.thin)

    print(f"\n=== Coverage map ({len(report.rows)} visible post(s))\n")
    for row in report.rows:
        keyword = f'"{row.focus}"' if row.focus else "_no target keyword_"
        print(f"  {row.slug} [{row.locale}]  {keyword}")
        print(f"      {row.intent_class}, {row.words} words")

    print("\n=== Overlapping intent\n")
    if not report.clashes:
        print(f"  None at or above {int(0.6 * 100)}%.")
    else:
        print(f"  {len(report.clashes)} pair(s). Two pages on one intent split "
              "their own ranking.")
        print("  Fix by re-angling one of them, or by consolidating and redirecting.\n")
        for pair in report.clashes:
            print(f"  {pair.score * 100:.0f}% overlap, both \"{pair.intent}\"")
            print(f"      {pair.a.slug}  ->  \"{pair.a.focus or pair.a.title}\"")
            print(f"      {pair.b.slug}  ->  \"{pair.b.focus or pair.b.title}\"")

    print("\n=== Quality flags\n")
    print(f"  Under {report.thin_floor} words:   {len(report.thin)}")
    for row in report.thin[:12]:
        print(f"      {row.words:>5}  {row.slug}")
    if len(report.thin) > 12:
        print(f"      ... and {len(report.thin) - 12} more")
    print(f"  No meta description: {len(report.no_meta)}")
    print(f"  No target keyword:   {len(report.no_focus)}")

    print("\n=== Summary ===")
    print(f"Visible posts:   {len(report.rows)}")
    print(f"Intent clashes:  {len(report.clashes)}")
    print(f"Thin (<{report.thin_floor}):    {len(report.thin)}")
    print("\nNothing was modified.")
    # Clashes fail the command; thin posts and missing metadata are work items,
    # not a reason to stop a publish.
    return 1 if report.clashes else 0


def cmd_audit_links(args) -> int:
    with _session() as db:
        report = audit_links(db)

    print(f"\nScanned {report.checked} visible post(s), {report.total_links} link(s)\n")
    if not report.findings:
        print("  Every internal link resolves.")
    for finding in report.findings:
        print(f'  "{finding.href}" — {finding.reason}')
        print(f"      in {len(finding.posts)} post(s): "
              + ", ".join(finding.posts[:3])
              + (" ..." if len(finding.posts) > 3 else ""))

    print("\n=== Summary ===")
    print(f"Posts scanned:   {report.checked}")
    print(f"Broken links:    {len(report.findings)}")
    print("\nNothing was modified.")
    return 1 if report.findings else 0


# --------------------------------------------------------------------------
# export-index
# --------------------------------------------------------------------------

def cmd_export_index(args) -> int:
    with _session() as db:
        target = export_index(db, args.out)
    print(f"Wrote {target}")
    print(f"  {BANNER} Commit it: it is the offline answer to "
          '"has this topic been written already".')
    return 0


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.blog.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="insert seeds, skipping what exists")
    create.add_argument("--dir")
    create.add_argument("--file")
    create.add_argument("--schedule-start", help="YYYY-MM-DD, midnight Vietnam time")
    create.add_argument("--per-week", type=int, default=DEFAULT_PER_WEEK)
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--reschedule", action="store_true",
                        help="re-spread posts still in status 2; ignores --dir/--file")
    create.set_defaults(func=cmd_create)

    pub = sub.add_parser("publish",
                         help="send the first N waiting posts out today and re-spread the rest")
    pub.add_argument("--count", type=int, required=True, help="how many to publish now")
    pub.add_argument("--rest-from", default=None,
                     help="re-spread everything still waiting from this date (YYYY-MM-DD)")
    pub.add_argument("--per-week", type=int, default=40, help="cadence for the remainder")
    pub.add_argument("--dry-run", action="store_true")
    pub.set_defaults(func=cmd_publish)

    update = sub.add_parser("update-from-seed", help="refresh live posts from seeds")
    update.add_argument("--dir")
    update.add_argument("--file")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--only-existing", action="store_true",
                        help="refresh posts that are already in the database and "
                             "insert nothing; a seed with no row is one the "
                             "duplicate-intent gate refused at create time")
    update.set_defaults(func=cmd_update_from_seed)

    retire = sub.add_parser("retire",
                            help="delete a post that was merged into another one")
    retire.add_argument("--slug", required=True, help="the post to delete")
    retire.add_argument("--into", required=True,
                        help="the slug it was merged into; the redirect destination")
    retire.add_argument("--locale", default="vi")
    retire.add_argument("--dry-run", action="store_true")
    retire.set_defaults(func=cmd_retire)

    seo = sub.add_parser("audit-seo", help="coverage and intent-clash report")
    seo.add_argument("--locale")
    seo.add_argument("--thin", type=int, default=DEFAULT_THIN)
    seo.set_defaults(func=cmd_audit_seo)

    link = sub.add_parser("audit-links", help="internal links that resolve to nothing")
    link.set_defaults(func=cmd_audit_links)

    index = sub.add_parser("export-index", help="write docs/blog-index.md")
    index.add_argument("--out", help="write somewhere other than docs/blog-index.md")
    index.set_defaults(func=cmd_export_index)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SeedError as e:
        # A bad seed is the expected failure of every command here, and its
        # message already names the file and the field.
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
