"""The CLI, driven through `main([...])` exactly as the shell drives it."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.blog import STATUS_DRAFT, STATUS_PUBLISHED, STATUS_SCHEDULED, cli
from app.blog.schedule import VN_TZ
from app.blog.index import BANNER
from app.db import get_session_factory
from app.models import BlogCategory, BlogPost

FIXTURE_DIR = str(Path(__file__).resolve().parents[2] / "docs" / "seo" / "fixtures" / "seeds")
NOW = datetime.now(timezone.utc)


@pytest.fixture
def db():
    with get_session_factory()() as s:
        yield s


def _post(db, slug, **kw):
    fields = {"locale": "vi", "slug": slug, "title": slug.replace("-", " "),
              "body": "Một đoạn.", "status": STATUS_PUBLISHED, "published_at": NOW,
              "meta_description": "mô tả"}
    fields.update(kw)
    p = BlogPost(**fields)
    db.add(p)
    db.commit()
    return p


# --- create ----------------------------------------------------------------

def test_create_dry_run_writes_nothing_and_prints_the_plan(capsys, db):
    assert cli.main(["create", "--dir", FIXTURE_DIR, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "WOULD CREATE cronbach-alpha-la-gi" in out
    assert "WOULD CREATE category: spss" in out
    assert db.query(BlogPost).count() == 0
    assert db.query(BlogCategory).count() == 0


def test_create_inserts_the_seeds_and_the_categories(capsys, db):
    assert cli.main(["create", "--dir", FIXTURE_DIR]) == 0
    out = capsys.readouterr().out
    assert "CREATE  cronbach-alpha-la-gi" in out
    assert db.query(BlogPost).count() == 2
    assert db.query(BlogCategory).count() == 9
    post = db.query(BlogPost).filter_by(slug="cronbach-alpha-la-gi").one()
    assert post.status == STATUS_PUBLISHED
    assert post.category_id is not None


def _english_dir(tmp_path, *, declare_locale: bool) -> str:
    """The fixture seeds copied out at locale `en`, categories beside them.

    `declare_locale` decides whether categories.json says `en` itself or leaves
    the loader to take it from the seeds in the directory.
    """
    import json

    posts = tmp_path / "posts"
    posts.mkdir()
    for src in sorted((Path(FIXTURE_DIR) / "posts").glob("*.json")):
        seed = json.loads(src.read_text(encoding="utf-8"))
        seed["locale"] = "en"
        (posts / src.name).write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

    rows = json.loads((Path(FIXTURE_DIR) / "categories.json").read_text(encoding="utf-8"))
    for row in rows:
        row["display_name"] = f"EN {row['slug']}"
        row["intro_md"] = f"The English intro to {row['slug']}."
        if declare_locale:
            row["locale"] = "en"
    (tmp_path / "categories.json").write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return str(tmp_path)


@pytest.mark.parametrize("declare_locale", [True, False])
def test_create_upserts_the_english_categories_beside_the_vietnamese_ones(
        capsys, db, tmp_path, declare_locale):
    """`create --dir .../en` must add hubs, not rewrite the live Vietnamese copy.

    Both spellings of the locale are exercised: declared in categories.json, and
    inferred from the seeds in the directory. Neither reads the directory name.
    """
    assert cli.main(["create", "--dir", FIXTURE_DIR]) == 0
    capsys.readouterr()

    assert cli.main(["create", "--dir", _english_dir(tmp_path, declare_locale=declare_locale)]) == 0

    rows = {(c.locale, c.slug): c for c in db.query(BlogCategory).all()}
    assert len(rows) == 18
    assert rows[("en", "spss")].display_name == "EN spss"
    assert rows[("vi", "spss")].display_name == "SPSS"

    post = db.query(BlogPost).filter_by(slug="cronbach-alpha-la-gi", locale="en").one()
    assert post.category_id == rows[("en", "spss")].id


def test_create_refuses_a_mixed_batch_whose_categories_do_not_name_a_locale(db, tmp_path):
    import json

    directory = _english_dir(tmp_path, declare_locale=False)
    stray = json.loads(
        (Path(FIXTURE_DIR) / "posts" / "0001-cronbach-alpha-la-gi.json").read_text("utf-8"))
    stray["slug"] = "bai-tieng-viet"
    (tmp_path / "posts" / "0003-bai-tieng-viet.json").write_text(
        json.dumps(stray, ensure_ascii=False), encoding="utf-8")

    # `vi` and `en` in one directory and nothing saying which the categories are.
    # Guessing would file half the posts under the wrong language's hub.
    assert cli.main(["create", "--dir", directory]) == 1
    assert db.query(BlogCategory).count() == 0


def test_the_dry_run_names_the_locale_it_would_create_a_category_at(capsys, db, tmp_path):
    directory = _english_dir(tmp_path, declare_locale=True)
    assert cli.main(["create", "--dir", directory, "--dry-run"]) == 0
    assert "WOULD CREATE category: spss [en]" in capsys.readouterr().out


def test_a_second_create_run_skips_rather_than_accusing_itself(capsys, db):
    cli.main(["create", "--dir", FIXTURE_DIR])
    capsys.readouterr()
    assert cli.main(["create", "--dir", FIXTURE_DIR]) == 0
    out = capsys.readouterr().out
    assert out.count("SKIP") >= 2
    assert "REFUSE" not in out
    assert db.query(BlogPost).count() == 2


def test_create_schedules_future_rows(capsys, db):
    start = (NOW + timedelta(days=3)).date().isoformat()
    assert cli.main(["create", "--dir", FIXTURE_DIR,
                     "--schedule-start", start, "--per-week", "1"]) == 0
    statuses = {p.slug: p.status for p in db.query(BlogPost).all()}
    assert set(statuses.values()) == {STATUS_SCHEDULED}
    # One a week means the second post lands seven days after the first.
    dates = sorted(p.scheduled_at for p in db.query(BlogPost).all())
    assert dates[1] - dates[0] == timedelta(days=7)


def test_create_refuses_a_seed_that_duplicates_a_live_post(capsys, db):
    _post(db, "bai-cu", focus_keyword="hệ số cronbach alpha là gì")
    assert cli.main(["create", "--dir", FIXTURE_DIR]) == 1
    out = capsys.readouterr().out
    assert "REFUSE  cronbach-alpha-la-gi" in out
    assert "bai-cu" in out
    assert "Refused (duplicate intent): 1" in out
    # The clean seed in the same batch still lands.
    assert db.query(BlogPost).filter_by(slug="cach-chay-hoi-quy-trong-spss").count() == 1


def test_create_reports_a_broken_seed_by_file_and_field(capsys, tmp_path):
    (tmp_path / "bad.json").write_text('{"schema": "dothesis-blog-seed/1"}',
                                       encoding="utf-8")
    assert cli.main(["create", "--dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "bad.json" in err and "title" in err


def test_create_needs_a_source(capsys):
    assert cli.main(["create"]) == 2


# --- reschedule ------------------------------------------------------------

def test_reschedule_respreads_the_queue(capsys, db):
    # Comfortably in the future: a start date of "tomorrow" is midnight in
    # Hanoi, which is already in the past once it is past 17:00 UTC.
    start = (NOW + timedelta(days=7)).date().isoformat()
    cli.main(["create", "--dir", FIXTURE_DIR, "--schedule-start", start, "--per-week", "1"])
    capsys.readouterr()

    later = (NOW + timedelta(days=30)).date().isoformat()
    assert cli.main(["create", "--reschedule", "--schedule-start", later,
                     "--per-week", "7"]) == 0
    dates = sorted(p.scheduled_at for p in db.query(BlogPost).all())
    assert dates[1] - dates[0] == timedelta(days=1)  # seven a week
    # Compared in Vietnam time: that is the timezone the start date was
    # read in, and 2026-10-07 there is still 2026-10-06 in UTC.
    assert dates[0].astimezone(VN_TZ).date().isoformat() == later


def test_reschedule_needs_a_start_date(capsys):
    assert cli.main(["create", "--reschedule"]) == 2


# --- update-from-seed ------------------------------------------------------

def test_update_from_seed_refreshes_a_live_post(capsys, db):
    cli.main(["create", "--dir", FIXTURE_DIR])
    post = db.query(BlogPost).filter_by(slug="cronbach-alpha-la-gi").one()
    post.title = "Tiêu đề cũ"
    db.commit()
    capsys.readouterr()

    assert cli.main(["update-from-seed", "--dir", FIXTURE_DIR]) == 0
    assert "UPDATED cronbach-alpha-la-gi" in capsys.readouterr().out
    db.expire_all()
    assert db.get(BlogPost, post.id).title.startswith("Cronbach")


def test_update_from_seed_dry_run_changes_nothing(capsys, db):
    cli.main(["create", "--dir", FIXTURE_DIR])
    post = db.query(BlogPost).filter_by(slug="cronbach-alpha-la-gi").one()
    post.title = "Tiêu đề cũ"
    db.commit()
    capsys.readouterr()

    assert cli.main(["update-from-seed", "--dir", FIXTURE_DIR, "--dry-run"]) == 0
    assert "WOULD UPDATE" in capsys.readouterr().out
    db.expire_all()
    assert db.get(BlogPost, post.id).title == "Tiêu đề cũ"


def test_update_from_seed_accepts_a_single_file(capsys, db, tmp_path):
    cli.main(["create", "--dir", FIXTURE_DIR])
    capsys.readouterr()
    path = Path(FIXTURE_DIR) / "posts" / "0001-cronbach-alpha-la-gi.json"
    seed = json.loads(path.read_text(encoding="utf-8"))
    seed["body"] = seed["body"] + "\n\nMột câu mới ở cuối bài."
    edited = tmp_path / "edited.json"
    edited.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

    assert cli.main(["update-from-seed", "--file", str(edited)]) == 0

    assert "UPDATED cronbach-alpha-la-gi" in capsys.readouterr().out


def test_a_seed_that_says_what_the_row_already_says_is_left_alone(capsys, db):
    """A bulk refresh must not restamp the bank.

    `updated_at` is what `modifiedTime` reports to a crawler and what a reader
    sees as the post's date. Rewriting 1,957 rows with their own content would
    announce that every post changed today, which is both untrue and the kind of
    signal a scaled-content check is looking for."""
    cli.main(["create", "--dir", FIXTURE_DIR])
    capsys.readouterr()
    before = db.scalar(select(BlogPost).where(BlogPost.slug == "cronbach-alpha-la-gi")).updated_at

    assert cli.main(["update-from-seed", "--dir", FIXTURE_DIR]) == 0

    out = capsys.readouterr().out
    assert "Updated: 0" in out and "Unchanged: 2" in out
    db.expire_all()
    after = db.scalar(select(BlogPost).where(BlogPost.slug == "cronbach-alpha-la-gi")).updated_at
    assert after == before


def test_only_existing_refuses_to_insert_what_the_duplicate_gate_refused(capsys, db):
    """`create` rejects a seed whose intent duplicates a live post. Nothing that
    walks around that gate may live in a refresh command."""
    assert cli.main(["update-from-seed", "--dir", FIXTURE_DIR, "--only-existing"]) == 0

    out = capsys.readouterr().out
    assert "Created: 0" in out
    assert "Skipped (no row): 2" in out
    assert db.scalar(select(BlogPost).where(BlogPost.slug == "cronbach-alpha-la-gi")) is None


# --- audits ----------------------------------------------------------------

# --- retire ----------------------------------------------------------------

def test_retire_deletes_the_merged_post_and_leaves_the_keeper(capsys, db):
    _post(db, "outlier", focus_keyword="outlier")
    _post(db, "outliers", focus_keyword="outliers")
    assert cli.main(["retire", "--slug", "outliers", "--into", "outlier"]) == 0
    out = capsys.readouterr().out
    assert "Deleted: outliers [vi]" in out
    assert {p.slug for p in db.query(BlogPost).all()} == {"outlier"}


def test_retire_prints_the_redirect_it_needs_before_the_row_goes(capsys, db):
    _post(db, "outlier", focus_keyword="outlier")
    _post(db, "outliers", focus_keyword="outliers")
    assert cli.main(["retire", "--slug", "outliers", "--into", "outlier"]) == 0
    out = capsys.readouterr().out
    # The exact line, because a deleted slug with no redirect is a 404 on a URL
    # the other posts already link to.
    assert ('{ source: "/blog/vi/outliers", destination: "/blog/vi/outlier", '
            "permanent: true }," ) in out
    assert "BEFORE the row goes" in out


def test_retire_dry_run_shows_the_row_and_deletes_nothing(capsys, db):
    _post(db, "outlier", focus_keyword="outlier")
    _post(db, "outliers", focus_keyword="outliers", title="Outliers là gì")
    assert cli.main(["retire", "--slug", "outliers", "--into", "outlier",
                     "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Outliers là gì" in out and "Dry run, nothing deleted." in out
    assert db.query(BlogPost).count() == 2


def test_retire_refuses_when_the_redirect_would_have_nowhere_to_land(capsys, db):
    _post(db, "outliers", focus_keyword="outliers")
    assert cli.main(["retire", "--slug", "outliers", "--into", "outlier"]) == 1
    assert db.query(BlogPost).count() == 1


def test_retire_refuses_a_post_that_is_not_there(capsys, db):
    _post(db, "outlier", focus_keyword="outlier")
    assert cli.main(["retire", "--slug", "outliers", "--into", "outlier"]) == 1
    assert db.query(BlogPost).count() == 1


def test_retire_will_not_point_a_post_at_itself(capsys, db):
    _post(db, "outlier", focus_keyword="outlier")
    assert cli.main(["retire", "--slug", "outlier", "--into", "outlier"]) == 2
    assert db.query(BlogPost).count() == 1


def test_retire_keeps_the_locales_apart(capsys, db):
    # The en bank has its own `outliers`; retiring the vi one must not see it.
    _post(db, "outlier", focus_keyword="outlier")
    _post(db, "outliers", locale="en", focus_keyword="outliers")
    assert cli.main(["retire", "--slug", "outliers", "--into", "outlier"]) == 1
    assert db.query(BlogPost).count() == 2


def test_audit_seo_reports_a_planted_overlap(capsys, db):
    _post(db, "efa-la-gi", focus_keyword="phân tích efa là gì")
    _post(db, "efa-la-gi-2", focus_keyword="phân tích efa là gì")
    assert cli.main(["audit-seo"]) == 1
    out = capsys.readouterr().out
    assert "efa-la-gi" in out and "efa-la-gi-2" in out
    assert "Intent clashes:  1" in out


def test_audit_seo_is_clean_when_nothing_collides(capsys, db):
    _post(db, "efa-la-gi", focus_keyword="phân tích efa là gì")
    _post(db, "chay-hoi-quy", focus_keyword="cách chạy hồi quy trong spss")
    assert cli.main(["audit-seo"]) == 0
    assert "Intent clashes:  0" in capsys.readouterr().out


def test_audit_seo_reports_thin_posts_without_failing(capsys, db):
    _post(db, "mong", focus_keyword="cỡ mẫu tối thiểu")
    assert cli.main(["audit-seo", "--thin", "50"]) == 0
    assert "Under 50 words:" in capsys.readouterr().out


def test_audit_seo_can_be_scoped_to_a_locale(capsys, db):
    _post(db, "vi-post", focus_keyword="phân tích efa là gì")
    _post(db, "en-post", locale="en", focus_keyword="phân tích efa là gì")
    assert cli.main(["audit-seo", "--locale", "vi"]) == 0  # different locales never clash


def test_audit_links_reports_a_link_to_a_missing_slug(capsys, db):
    _post(db, "co-lien-ket", body="Xem [bài kia](/blog/vi/khong-ton-tai) nhé.")
    assert cli.main(["audit-links"]) == 1
    out = capsys.readouterr().out
    assert "/blog/vi/khong-ton-tai" in out
    assert "co-lien-ket" in out


def test_audit_links_reports_a_schemeless_href(capsys, db):
    _post(db, "loi-tuong-doi", body="Xem [bài kia](cronbach-alpha-la-gi).")
    assert cli.main(["audit-links"]) == 1
    assert "relative href" in capsys.readouterr().out


def test_audit_links_accepts_posts_categories_and_allow_listed_routes(capsys, db):
    db.add(BlogCategory(slug="spss", name="SPSS", display_name="SPSS"))
    db.commit()
    _post(db, "dich", body="ok")
    _post(db, "nguon", body=("[a](/blog/vi/dich) [b](/blog/vi/chu-de/spss) "
                             "[c](/landing) [d](https://x.test) [e](#faq)"))
    assert cli.main(["audit-links"]) == 0
    assert "Every internal link resolves." in capsys.readouterr().out


def test_a_category_hub_only_resolves_at_its_own_locale(capsys, db):
    """An English-only hub does not make /blog/vi/chu-de/<slug> a real page."""
    db.add(BlogCategory(locale="en", slug="khao-sat", name="Surveys",
                        display_name="Surveys"))
    db.commit()
    _post(db, "nguon", body="[a](/blog/vi/chu-de/khao-sat)")

    assert cli.main(["audit-links"]) == 1
    assert "/blog/vi/chu-de/khao-sat" in capsys.readouterr().out


# --- export-index ----------------------------------------------------------

def test_export_index_writes_the_snapshot(capsys, tmp_path, db):
    _post(db, "cronbach-alpha-la-gi", focus_keyword="cronbach alpha là gì",
          excerpt="Tóm tắt.", tags=["spss"])
    target = tmp_path / "blog-index.md"
    assert cli.main(["export-index", "--out", str(target)]) == 0

    text = target.read_text(encoding="utf-8")
    assert BANNER in text
    assert "### cronbach-alpha-la-gi" in text
    assert "`cronbach alpha là gì`" in text
    assert "## Duplication overrides" in text
    assert "_None._" in text
    assert str(target) in capsys.readouterr().out


def test_export_index_records_an_override(tmp_path, db):
    _post(db, "co-ly-do", focus_keyword="k",
          duplicate_override_reason="Trường hợp hai biến quan sát, bài kia không nói tới.")
    target = tmp_path / "blog-index.md"
    cli.main(["export-index", "--out", str(target)])
    assert "Trường hợp hai biến quan sát" in target.read_text(encoding="utf-8")


def test_export_index_defaults_to_the_repo_docs_directory():
    from app.blog.index import default_index_path

    path = default_index_path()
    assert path.name == "blog-index.md"
    assert (path.parents[1] / "api").is_dir()  # found the checkout root, not /


# --- unmeasured seeds publish like any other (rule changed 2026-09-08) ------
#
# Before that date an unmeasured seed inserted as a dateless DRAFT and consumed
# no schedule slot, and these three tests asserted exactly that. The product
# owner replaced the rule: volume orders the backlog, the quality gates decide
# what exists, so every seed takes a slot in backlog order.

def _mixed_dir(tmp_path):
    """Four seeds, alternating measured and unmeasured.

    The two unmeasured ones are written with the pre-rename `family-inferred`
    spelling on purpose: 149 seed files on disk still carry it, and `create`
    has to schedule them like anything else.

    Distinct focus keywords throughout so the duplicate guard has nothing to
    say and the test is only about scheduling.
    """
    import json

    base = json.loads((Path(FIXTURE_DIR) / "posts" / "0001-cronbach-alpha-la-gi.json")
                      .read_text(encoding="utf-8"))
    posts = tmp_path / "posts"
    posts.mkdir()
    (tmp_path / "categories.json").write_text(
        (Path(FIXTURE_DIR) / "categories.json").read_text(encoding="utf-8"),
        encoding="utf-8")

    plan = [("do-tin-cay-thang-do", "measured"), ("bien-hiem-la-gi", "family-inferred"),
            ("phan-tich-efa", "measured"), ("chi-so-hiem-gap", "family-inferred")]
    for i, (slug, status) in enumerate(plan, 1):
        seed = dict(base, slug=slug, title=slug.replace("-", " "),
                    focus_keyword=slug.replace("-", " "), secondary_keywords=[],
                    gate_status=status)
        (posts / f"{i:04d}-{slug}.json").write_text(
            json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    return str(tmp_path)


def test_every_seed_takes_a_slot_in_backlog_order(capsys, db, tmp_path):
    """Rule changed 2026-09-08: the unmeasured seeds used to be skipped here."""
    start = (NOW + timedelta(days=3)).date().isoformat()
    assert cli.main(["create", "--dir", _mixed_dir(tmp_path),
                     "--schedule-start", start, "--per-week", "1"]) == 0

    posts = {p.slug: p for p in db.query(BlogPost).all()}
    assert len(posts) == 4
    assert {p.status for p in posts.values()} == {STATUS_SCHEDULED}

    # Slots 0..3, one a week, in the order the seed filenames give: nothing
    # steps over an unmeasured page any more.
    ordered = ["do-tin-cay-thang-do", "bien-hiem-la-gi", "phan-tich-efa",
               "chi-so-hiem-gap"]
    first = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=VN_TZ)
    for week, slug in enumerate(ordered):
        assert posts[slug].scheduled_at == first + timedelta(days=7 * week)

    out = capsys.readouterr().out
    assert "demand unmeasured" in out
    assert "unmeasured (scheduled anyway, quality gates decided): 2" in out


def test_create_dry_run_reports_the_unmeasured_count(capsys, db, tmp_path):
    assert cli.main(["create", "--dir", _mixed_dir(tmp_path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Posts would create: 4" in out
    assert "unmeasured (scheduled anyway, quality gates decided): 2" in out
    assert db.query(BlogPost).count() == 0


def test_reschedule_respreads_the_unmeasured_posts_too(capsys, db, tmp_path):
    """They are ordinary scheduled posts now, so they move with the rest."""
    start = (NOW + timedelta(days=3)).date().isoformat()
    cli.main(["create", "--dir", _mixed_dir(tmp_path), "--schedule-start", start,
              "--per-week", "1"])
    capsys.readouterr()

    later = (NOW + timedelta(days=40)).date().isoformat()
    assert cli.main(["create", "--reschedule", "--schedule-start", later,
                     "--per-week", "2"]) == 0
    out = capsys.readouterr().out
    assert "Rescheduled: 4 post(s)" in out
    assert "bien-hiem-la-gi" in out

    assert db.query(BlogPost).filter_by(status=STATUS_DRAFT).count() == 0
