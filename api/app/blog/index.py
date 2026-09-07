"""Write `docs/blog-index.md` — what the blog covers, readable without a database.

`audit-seo` answers the same question better, but it needs a live connection,
so in practice it gets skipped and duplicate posts ship. This exists so the
check costs nothing: any checkout, no connection, one file.

It is a SNAPSHOT. The database is the source of truth and this goes stale the
moment anyone publishes, which is why the file says when it was generated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from . import STATUS_PUBLISHED, STATUS_SCHEDULED
from .markdown import word_count

BANNER = "**Generated file — do not edit.**"


def repo_root() -> Path:
    """The checkout root: the first ancestor that contains an `api/` directory.

    Walked rather than hard-coded because this runs from a worktree as often as
    from the main checkout, and the two are at different paths.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "api").is_dir():
            return parent
    raise RuntimeError("could not locate the repo root (no ancestor contains api/)")


def default_index_path() -> Path:
    return repo_root() / "docs" / "blog-index.md"


def build_index(db: Session, *, generated_on: str | None = None) -> str:
    from ..models import BlogPost  # noqa: PLC0415

    posts = db.scalars(
        select(BlogPost).order_by(asc(BlogPost.locale), desc(BlogPost.published_at))
    ).all()
    today = generated_on or datetime.now(timezone.utc).date().isoformat()

    out: list[str] = [
        "# DoThesis blog index",
        "",
        f"{BANNER} Regenerate with:",
        "`cd api && ./run.sh python -m app.blog.cli export-index`",
        "",
        f"Snapshot taken {today}. The database is the source of truth; this goes",
        "stale as soon as anyone publishes. For live data run",
        "`./run.sh python -m app.blog.cli audit-seo`.",
        "",
        f"{len(posts)} post(s).",
        "",
    ]

    by_locale: dict[str, list] = {}
    for p in posts:
        by_locale.setdefault(p.locale, []).append(p)

    for locale, rows in by_locale.items():
        published = [p for p in rows if p.status == STATUS_PUBLISHED]
        scheduled = [p for p in rows if p.status == STATUS_SCHEDULED]
        note = f", {len(scheduled)} scheduled" if scheduled else ""
        out += [f"## {locale} — {len(rows)} post(s), {len(published)} published{note}", ""]
        for p in rows:
            if p.status == STATUS_PUBLISHED:
                state = f"published {p.published_at.date().isoformat() if p.published_at else 'undated'}"
            elif p.status == STATUS_SCHEDULED:
                state = f"scheduled {p.scheduled_at.date().isoformat() if p.scheduled_at else 'undated'}"
            else:
                state = "draft"
            out += [
                f"### {p.slug}",
                f"**{p.title}** · {p.locale} · {state} · {word_count(p.body)} words",
                f"Keyword: `{p.focus_keyword}`" if p.focus_keyword else "Keyword: _none recorded_",
            ]
            if p.tags:
                out.append("Tags: " + ", ".join(str(t) for t in p.tags))
            if p.excerpt:
                out.append("> " + " ".join(p.excerpt.split()))
            out += [f"/blog/{p.locale}/{p.slug}", ""]

    out += [
        "## Keyword coverage",
        "",
        "Every recorded target keyword, sorted. Two entries that read the same",
        "are two pages splitting one ranking.",
        "",
    ]
    keywords = sorted(f"- `{p.focus_keyword}` — {p.slug} [{p.locale}]"
                      for p in posts if p.focus_keyword)
    out += keywords or ["_none recorded_"]
    out.append("")

    overridden = [p for p in posts if p.duplicate_override_reason]
    out += ["## Duplication overrides", ""]
    if not overridden:
        out.append("_None._")
    else:
        out += [
            "Posts published despite colliding with an existing one, and the",
            "stated reason. If a reason here does not convince you, the post",
            "should probably have been an edit to the one it collided with.",
            "",
        ]
        out += [f"- **{p.slug}** [{p.locale}] — {p.duplicate_override_reason}"
                for p in overridden]
    out.append("")

    return "\n".join(out)


def export_index(db: Session, path: str | Path | None = None) -> Path:
    target = Path(path) if path else default_index_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_index(db), encoding="utf-8")
    return target
