"""Seed loading, validation, and the insert that skips what already exists."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.blog import STATUS_DRAFT, STATUS_PUBLISHED, STATUS_SCHEDULED
from app.blog import seeds as S
from app.db import get_session_factory
from app.models import BlogCategory, BlogPost

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "docs" / "seo" / "fixtures" / "seeds"
NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


@pytest.fixture
def db():
    with get_session_factory()() as s:
        yield s


@pytest.fixture
def good_seed():
    _, seed = S.load_dir(FIXTURE_DIR)[0]
    return copy.deepcopy(seed)


@pytest.fixture
def categories(db):
    return S.upsert_categories(db, S.load_categories(FIXTURE_DIR))


# --- loading ---------------------------------------------------------------

def test_load_dir_reads_posts_in_filename_order():
    loaded = S.load_dir(FIXTURE_DIR)
    assert [p.name for p, _ in loaded] == [
        "0001-cronbach-alpha-la-gi.json", "0002-cach-chay-hoi-quy-trong-spss.json"]
    # The NNNN- prefix is the publish order, which is why sorting matters.
    assert [s["slug"] for _, s in loaded] == [
        "cronbach-alpha-la-gi", "cach-chay-hoi-quy-trong-spss"]


def test_load_dir_falls_back_to_a_flat_directory(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(
        json.loads((FIXTURE_DIR / "posts" / "0001-cronbach-alpha-la-gi.json")
                   .read_text(encoding="utf-8"))), encoding="utf-8")
    (tmp_path / "categories.json").write_text("[]", encoding="utf-8")
    loaded = S.load_dir(tmp_path)
    assert [p.name for p, _ in loaded] == ["a.json"]  # categories.json is not a post


def test_load_categories_returns_the_nine_slugs():
    got = [c["slug"] for c in S.load_categories(FIXTURE_DIR)]
    assert got == list(S.CATEGORY_SLUGS)


def test_load_seed_reports_the_file_it_could_not_parse(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(S.SeedError) as e:
        S.load_seed(bad)
    assert "broken.json" in str(e.value)


# --- validation ------------------------------------------------------------

def test_a_fixture_seed_validates(good_seed):
    assert S.validate_seed(good_seed)["slug"] == "cronbach-alpha-la-gi"


@pytest.mark.parametrize("field", S.REQUIRED_FIELDS)
def test_every_required_field_is_required_and_named(good_seed, field):
    good_seed.pop(field)
    with pytest.raises(S.SeedError) as e:
        S.validate_seed(good_seed)
    assert field in str(e.value)


def test_an_empty_required_field_fails_too(good_seed):
    good_seed["excerpt"] = "   "
    with pytest.raises(S.SeedError) as e:
        S.validate_seed(good_seed)
    assert "excerpt" in str(e.value)


def test_the_schema_string_must_match(good_seed):
    good_seed["schema"] = "dothesis-blog-seed/2"
    with pytest.raises(S.SeedError) as e:
        S.validate_seed(good_seed)
    assert S.SEED_SCHEMA in str(e.value)


def test_the_category_must_be_one_of_the_nine(good_seed):
    good_seed["category"] = "seo-tips"
    with pytest.raises(S.SeedError) as e:
        S.validate_seed(good_seed)
    assert "seo-tips" in str(e.value)


def test_an_unnormalized_slug_is_rejected_with_the_fix(good_seed):
    good_seed["slug"] = "Cronbach Alpha Là Gì"
    with pytest.raises(S.SeedError) as e:
        S.validate_seed(good_seed)
    assert "cronbach-alpha-la-gi" in str(e.value)


def test_an_overlong_slug_is_rejected(good_seed):
    good_seed["slug"] = "a" * (S.MAX_SLUG_LENGTH + 1)
    with pytest.raises(S.SeedError) as e:
        S.validate_seed(good_seed)
    assert str(S.MAX_SLUG_LENGTH) in str(e.value)


def test_optional_fields_get_stable_defaults(good_seed):
    for key in ("secondary_keywords", "tags", "sibling_slugs", "images"):
        good_seed.pop(key, None)
    clean = S.validate_seed(good_seed)
    assert clean["tags"] == [] and clean["secondary_keywords"] == []


def test_normalize_slug():
    assert S.normalize_slug("Cronbach's Alpha là gì") == "cronbach-s-alpha-la-gi"
    assert S.normalize_slug("Đề tài luận văn") == "de-tai-luan-van"
    assert len(S.normalize_slug("x" * 300)) == S.MAX_SLUG_LENGTH


# --- categories ------------------------------------------------------------

def test_upsert_categories_creates_then_updates(db):
    rows = S.load_categories(FIXTURE_DIR)
    ids = S.upsert_categories(db, rows)
    assert len(ids) == 9
    assert db.query(BlogCategory).count() == 9

    rows[0]["intro_md"] = "Bản giới thiệu mới."
    again = S.upsert_categories(db, rows)
    key = ("vi", rows[0]["slug"])
    assert again[key] == ids[key]  # same row, not a second one
    assert db.query(BlogCategory).count() == 9
    assert db.get(BlogCategory, ids[key]).intro_md == "Bản giới thiệu mới."


def test_categories_default_to_the_locale_the_bank_launched_with(db):
    rows = S.load_categories(FIXTURE_DIR)
    assert {r["locale"] for r in rows} == {"vi"}


def test_a_categories_file_can_be_loaded_at_another_locale():
    rows = S.load_categories(FIXTURE_DIR, default_locale="en")
    assert {r["locale"] for r in rows} == {"en"}


def test_a_row_naming_its_own_locale_wins_over_the_default(tmp_path):
    (tmp_path / "categories.json").write_text(json.dumps(
        [{"slug": "spss", "name": "SPSS", "locale": "en"},
         {"slug": "smartpls", "name": "SmartPLS"}]), encoding="utf-8")
    rows = S.load_categories(tmp_path, default_locale="vi")
    assert {r["slug"]: r["locale"] for r in rows} == {"spss": "en", "smartpls": "vi"}


def test_a_categories_file_with_nothing_to_infer_from_is_refused(tmp_path):
    """Nothing guesses a language here. A mixed batch has to say which it means."""
    (tmp_path / "categories.json").write_text(
        json.dumps([{"slug": "spss", "name": "SPSS"}]), encoding="utf-8")
    with pytest.raises(S.SeedError) as e:
        S.load_categories(tmp_path, default_locale=None)
    assert "locale" in str(e.value)


def test_a_locale_longer_than_the_column_is_refused(tmp_path):
    (tmp_path / "categories.json").write_text(json.dumps(
        [{"slug": "spss", "name": "SPSS", "locale": "vi-VN-x-toolong"}]), encoding="utf-8")
    with pytest.raises(S.SeedError):
        S.load_categories(tmp_path)


def test_seeds_locale_reports_agreement_and_refuses_to_guess():
    loaded = S.load_dir(FIXTURE_DIR)
    assert S.seeds_locale(loaded) == "vi"

    mixed = [(p, {**seed}) for p, seed in loaded]
    mixed[0][1]["locale"] = "en"
    assert S.seeds_locale(mixed) is None
    assert S.seeds_locale([]) is None


def test_the_same_slug_upserts_once_per_locale(db):
    rows = S.load_categories(FIXTURE_DIR)
    vi = S.upsert_categories(db, rows)
    en = S.upsert_categories(db, [{**r, "locale": "en", "display_name": "Statistics",
                                   "intro_md": "The English intro."} for r in rows])

    assert db.query(BlogCategory).count() == 18
    assert vi[("vi", "spss")] != en[("en", "spss")]
    # The English run must not have rewritten the Vietnamese copy: that copy IS
    # the Vietnamese hub page, and 420 live posts sit under it.
    assert db.get(BlogCategory, vi[("vi", "spss")]).intro_md.startswith("SPSS là phần mềm")
    assert db.get(BlogCategory, en[("en", "spss")]).intro_md == "The English intro."


def test_category_index_keys_on_locale_and_slug(db):
    S.upsert_categories(db, S.load_categories(FIXTURE_DIR))
    index = S.category_index(db)
    assert ("vi", "spss") in index
    assert ("en", "spss") not in index


# --- create ----------------------------------------------------------------

def test_create_from_seed_inserts_a_published_post(db, good_seed, categories):
    action, post = S.create_from_seed(db, good_seed, categories, now=NOW)
    assert action == "created"
    assert post.status == STATUS_PUBLISHED
    assert post.category_id == categories[("vi", "spss")]
    assert post.reading_time >= 2  # computed from the body, not from the seed
    assert post.tags == good_seed["tags"]
    assert post.focus_keyword_volume == 1300


def test_create_from_seed_honours_a_future_go_live(db, good_seed, categories):
    _, post = S.create_from_seed(db, good_seed, categories,
                                 go_live=NOW + timedelta(days=30), now=NOW)
    assert post.status == STATUS_SCHEDULED
    assert post.scheduled_at == NOW + timedelta(days=30)


def test_create_from_seed_skips_an_existing_locale_slug_pair(db, good_seed, categories):
    S.create_from_seed(db, good_seed, categories, now=NOW)
    action, _ = S.create_from_seed(db, good_seed, categories, now=NOW)
    assert action == "skipped"
    assert db.query(BlogPost).count() == 1


def test_the_same_slug_in_another_locale_is_a_different_post(db, good_seed, categories):
    S.create_from_seed(db, good_seed, categories, now=NOW)
    good_seed["locale"] = "en"
    action, _ = S.create_from_seed(db, good_seed, categories, now=NOW)
    assert action == "created"
    assert db.query(BlogPost).count() == 2


def test_a_post_never_binds_to_another_locales_category(db, good_seed, categories):
    """`categories` here is the Vietnamese set, so the English seed gets nothing.

    No category at all is the right answer: `category_id` is nullable, and a
    post filed under a hub written in a language its reader is not reading is
    worse than a post filed under none.
    """
    good_seed["locale"] = "en"
    _, post = S.create_from_seed(db, good_seed, categories, now=NOW)
    assert post.category_id is None


def test_a_post_binds_to_its_own_locales_category(db, good_seed, categories):
    english = S.upsert_categories(db, S.load_categories(FIXTURE_DIR, default_locale="en"))
    good_seed["locale"] = "en"
    _, post = S.create_from_seed(db, good_seed, {**categories, **english}, now=NOW)
    assert post.category_id == english[("en", "spss")]
    assert post.category_id != categories[("vi", "spss")]


# --- update ----------------------------------------------------------------

def test_upsert_from_seed_updates_content_without_republishing(db, good_seed, categories):
    _, original = S.create_from_seed(db, good_seed, categories,
                                     go_live=NOW + timedelta(days=30), now=NOW)
    good_seed["title"] = "Tiêu đề đã sửa"
    good_seed["body"] = good_seed["body"] + "\n\nMột đoạn bổ sung.\n"
    action, post = S.upsert_from_seed(db, good_seed, categories, now=NOW)

    assert action == "updated"
    assert post.id == original.id
    assert post.title == "Tiêu đề đã sửa"
    # The schedule is the publisher's decision, not the seed's: re-running the
    # writer must not drag a scheduled post forward or push a live one back.
    assert post.status == STATUS_SCHEDULED
    assert post.scheduled_at == NOW + timedelta(days=30)


def test_upsert_from_seed_creates_when_nothing_is_there(db, good_seed, categories):
    action, post = S.upsert_from_seed(db, good_seed, categories, now=NOW)
    assert action == "created"
    assert post.status == STATUS_PUBLISHED


# --- gate_status, and why it no longer decides publication ------------------
#
# Until 2026-09-08 an unmeasured seed was forced to DRAFT with no dates. The
# product owner replaced that rule: measured volume sets priority order only,
# and the three quality gates decide whether a page exists at all. So these
# tests assert the opposite of what they asserted before that date.

def test_gate_status_defaults_to_measured(good_seed):
    good_seed.pop("gate_status", None)
    assert S.validate_seed(good_seed)["gate_status"] == "measured"
    assert S.is_unmeasured(good_seed) is False


def test_gate_status_accepts_unmeasured(good_seed):
    good_seed["gate_status"] = "unmeasured"
    clean = S.validate_seed(good_seed)
    assert clean["gate_status"] == "unmeasured"
    assert S.is_unmeasured(clean) is True


def test_the_family_inferred_alias_normalises_to_unmeasured(good_seed):
    """The word changed on 2026-09-08; 149 seed files on disk still say the old one.

    They have to keep loading, and they have to load as the new value, or the
    same page would be `family-inferred` in the bank and `unmeasured` everywhere
    the engine writes about it.
    """
    good_seed["gate_status"] = "family-inferred"
    assert S.validate_seed(good_seed)["gate_status"] == "unmeasured"


def test_a_seed_file_written_before_the_rename_still_loads(tmp_path, good_seed):
    """End to end through `load_seed`, which is what `create --dir` actually calls."""
    good_seed["gate_status"] = "family-inferred"
    path = tmp_path / "0001-old.json"
    path.write_text(json.dumps(good_seed, ensure_ascii=False), encoding="utf-8")
    assert S.load_seed(path)["gate_status"] == "unmeasured"


def test_an_unknown_gate_status_is_refused_with_the_allowed_values(good_seed):
    good_seed["gate_status"] = "guessed"
    with pytest.raises(S.SeedError) as e:
        S.validate_seed(good_seed)
    assert "gate_status" in str(e.value) and "unmeasured" in str(e.value)


def test_an_unmeasured_seed_publishes_on_its_go_live_date(db, good_seed, categories):
    """Rule changed 2026-09-08: this used to insert as a dateless DRAFT."""
    good_seed["gate_status"] = "unmeasured"
    action, post = S.create_from_seed(db, good_seed, categories,
                                      go_live=NOW - timedelta(days=30), now=NOW)
    assert action == "created"
    assert post.status == STATUS_PUBLISHED
    assert post.published_at is not None


def test_an_unmeasured_seed_dated_ahead_schedules_like_any_other(db, good_seed, categories):
    good_seed["gate_status"] = "unmeasured"
    _, post = S.create_from_seed(db, good_seed, categories,
                                 go_live=NOW + timedelta(days=10), now=NOW)
    assert post.status == STATUS_SCHEDULED
    assert post.scheduled_at == NOW + timedelta(days=10)


def test_upsert_also_publishes_a_new_unmeasured_seed(db, good_seed, categories):
    """The two inserts have to agree, or one command would publish and the other not."""
    good_seed["gate_status"] = "unmeasured"
    action, post = S.upsert_from_seed(db, good_seed, categories, now=NOW)
    assert action == "created"
    assert post.status == STATUS_PUBLISHED


def test_an_explicit_status_still_wins_over_the_planned_one(db, good_seed, categories):
    """The admin route deliberately drafting a page must still win."""
    good_seed["gate_status"] = "unmeasured"
    _, post = S.upsert_from_seed(db, good_seed, categories, now=NOW,
                                 status=STATUS_DRAFT)
    assert post.status == STATUS_DRAFT
