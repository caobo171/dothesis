"""The CLI, driven through `main([...])` exactly as the shell drives it."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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


def test_update_from_seed_accepts_a_single_file(capsys, db):
    cli.main(["create", "--dir", FIXTURE_DIR])
    capsys.readouterr()
    path = str(Path(FIXTURE_DIR) / "posts" / "0001-cronbach-alpha-la-gi.json")
    assert cli.main(["update-from-seed", "--file", path]) == 0
    assert "UPDATED cronbach-alpha-la-gi" in capsys.readouterr().out


# --- audits ----------------------------------------------------------------

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


# --- family-inferred seeds insert as drafts (design §5) ---------------------

def _mixed_dir(tmp_path):
    """Four seeds, alternating measured and family-inferred.

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


def test_inferred_seeds_draft_while_measured_ones_take_consecutive_slots(capsys, db, tmp_path):
    start = (NOW + timedelta(days=3)).date().isoformat()
    assert cli.main(["create", "--dir", _mixed_dir(tmp_path),
                     "--schedule-start", start, "--per-week", "1"]) == 0

    posts = {p.slug: p for p in db.query(BlogPost).all()}
    assert len(posts) == 4

    for slug in ("bien-hiem-la-gi", "chi-so-hiem-gap"):
        assert posts[slug].status == STATUS_DRAFT
        assert posts[slug].scheduled_at is None
        assert posts[slug].published_at is None

    # The two measured posts hold slots 0 and 1, so one week apart. If the
    # drafts had consumed slots they would be three weeks apart instead.
    a, b = posts["do-tin-cay-thang-do"], posts["phan-tich-efa"]
    assert a.status == b.status == STATUS_SCHEDULED
    assert b.scheduled_at - a.scheduled_at == timedelta(days=7)
    assert a.scheduled_at == datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=VN_TZ)

    out = capsys.readouterr().out
    assert "DRAFT, demand family-inferred" in out
    assert "Drafts (family-inferred, no schedule slot): 2" in out


def test_create_dry_run_reports_the_draft_count(capsys, db, tmp_path):
    assert cli.main(["create", "--dir", _mixed_dir(tmp_path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Posts would create: 4" in out
    assert "Drafts (family-inferred, no schedule slot): 2" in out
    assert db.query(BlogPost).count() == 0


def test_reschedule_leaves_family_inferred_drafts_alone(capsys, db, tmp_path):
    start = (NOW + timedelta(days=3)).date().isoformat()
    cli.main(["create", "--dir", _mixed_dir(tmp_path), "--schedule-start", start,
              "--per-week", "1"])
    capsys.readouterr()

    later = (NOW + timedelta(days=40)).date().isoformat()
    assert cli.main(["create", "--reschedule", "--schedule-start", later,
                     "--per-week", "2"]) == 0
    out = capsys.readouterr().out
    assert "Rescheduled: 2 post(s)" in out
    assert "bien-hiem-la-gi" not in out

    drafts = db.query(BlogPost).filter_by(status=STATUS_DRAFT).all()
    assert {d.slug for d in drafts} == {"bien-hiem-la-gi", "chi-so-hiem-gap"}
    assert all(d.scheduled_at is None for d in drafts)
