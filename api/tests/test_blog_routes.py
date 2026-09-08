"""Public blog routes, and the visibility rule they all share."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.blog import STATUS_DRAFT, STATUS_PUBLISHED, STATUS_SCHEDULED
from app.db import get_session_factory
from app.main import create_app
from app.models import BlogCategory, BlogPost

NOW = datetime.now(timezone.utc)


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def db():
    with get_session_factory()() as s:
        yield s


def _category(db, slug="spss", name="SPSS", order=0, locale="vi"):
    c = BlogCategory(locale=locale, slug=slug, name=name, display_name=name,
                     intro_md=f"Giới thiệu {name}.", sort_order=order)
    db.add(c)
    db.commit()
    return c


def _post(db, slug, *, status=STATUS_PUBLISHED, published_at=None, scheduled_at=None,
          category=None, tags=None, locale="vi", title=None, body="Một đoạn nội dung."):
    p = BlogPost(
        locale=locale, slug=slug, title=title or slug.replace("-", " "),
        body=body, excerpt=f"Tóm tắt {slug}.", status=status,
        published_at=published_at if published_at is not None else NOW,
        scheduled_at=scheduled_at,
        category_id=category.id if category else None, tags=tags or [],
        reading_time=3, meta_description="mô tả",
    )
    db.add(p)
    db.commit()
    return p


# --- visibility ------------------------------------------------------------

def test_list_shows_only_what_the_public_may_see(client, db):
    _post(db, "published")
    _post(db, "draft", status=STATUS_DRAFT)
    _post(db, "future", status=STATUS_SCHEDULED, scheduled_at=NOW + timedelta(days=7))
    _post(db, "past-scheduled", status=STATUS_SCHEDULED, scheduled_at=NOW - timedelta(days=1))

    slugs = {p["slug"] for p in client.post("/api/v1/blog/list", json={}).json()["posts"]}
    assert slugs == {"published", "past-scheduled"}


def test_a_scheduled_post_without_a_date_stays_hidden(client, db):
    _post(db, "orphan", status=STATUS_SCHEDULED, scheduled_at=None)
    assert client.post("/api/v1/blog/list", json={}).json()["total"] == 0


def test_get_refuses_a_post_that_is_not_visible_yet(client, db):
    _post(db, "future", status=STATUS_SCHEDULED, scheduled_at=NOW + timedelta(days=7))
    r = client.post("/api/v1/blog/get", json={"slug": "future"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "not_found"


# --- list ------------------------------------------------------------------

def test_list_paginates_and_reports_the_total(client, db):
    for i in range(7):
        _post(db, f"p-{i}", published_at=NOW - timedelta(days=i))
    r = client.post("/api/v1/blog/list", json={"page": 2, "page_size": 3}).json()
    assert r["total"] == 7
    assert [p["slug"] for p in r["posts"]] == ["p-3", "p-4", "p-5"]


def test_list_cards_carry_no_body(client, db):
    _post(db, "p")
    assert "body" not in client.post("/api/v1/blog/list", json={}).json()["posts"][0]


def test_list_filters_by_category(client, db):
    spss = _category(db)
    _post(db, "in-spss", category=spss)
    _post(db, "uncategorised")
    r = client.post("/api/v1/blog/list", json={"category": "spss"}).json()
    assert [p["slug"] for p in r["posts"]] == ["in-spss"]
    assert r["posts"][0]["category"]["display_name"] == "SPSS"


def test_list_filters_by_the_category_of_the_requested_locale(client, db):
    vi_spss = _category(db, "spss", "SPSS", locale="vi")
    en_spss = _category(db, "spss", "SPSS", locale="en")
    _post(db, "vi-post", category=vi_spss, locale="vi")
    _post(db, "en-post", category=en_spss, locale="en")

    r = client.post("/api/v1/blog/list", json={"locale": "en", "category": "spss"}).json()
    assert [p["slug"] for p in r["posts"]] == ["en-post"]
    r = client.post("/api/v1/blog/list", json={"locale": "vi", "category": "spss"}).json()
    assert [p["slug"] for p in r["posts"]] == ["vi-post"]


def test_a_category_that_exists_only_in_another_locale_is_an_empty_page(client, db):
    en_spss = _category(db, "spss", "SPSS", locale="en")
    _post(db, "en-post", category=en_spss, locale="en")
    r = client.post("/api/v1/blog/list", json={"locale": "vi", "category": "spss"}).json()
    assert r == {"posts": [], "total": 0, "page": 1, "page_size": 12}


def test_a_post_carries_its_own_locales_category(client, db):
    _category(db, "spss", "SPSS", locale="vi")
    en_spss = _category(db, "spss", "Quantitative software", locale="en")
    _post(db, "en-post", category=en_spss, locale="en")

    r = client.post("/api/v1/blog/get", json={"locale": "en", "slug": "en-post"}).json()
    assert r["category"]["display_name"] == "Quantitative software"


def test_an_unknown_category_is_an_empty_page_not_an_error(client, db):
    _post(db, "p")
    r = client.post("/api/v1/blog/list", json={"category": "khong-ton-tai"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_list_searches_title_and_keyword(client, db):
    _post(db, "hoi-quy", title="Cách chạy hồi quy")
    _post(db, "efa", title="Phân tích EFA")
    r = client.post("/api/v1/blog/list", json={"q": "hồi quy"}).json()
    assert [p["slug"] for p in r["posts"]] == ["hoi-quy"]


def test_list_is_scoped_to_one_locale(client, db):
    _post(db, "p", locale="vi")
    _post(db, "p", locale="en")
    assert client.post("/api/v1/blog/list", json={"locale": "en"}).json()["total"] == 1


def test_page_size_is_capped(client):
    assert client.post("/api/v1/blog/list", json={"page_size": 500}).status_code == 422


# --- get -------------------------------------------------------------------

def test_get_returns_the_body_and_the_category(client, db):
    spss = _category(db)
    _post(db, "cronbach", category=spss, body="## Mở đầu\n\nNội dung.")
    r = client.post("/api/v1/blog/get", json={"slug": "cronbach"}).json()
    assert r["body"].startswith("## Mở đầu")
    assert r["category"]["slug"] == "spss"


def test_get_returns_up_to_five_related_posts_from_the_same_category(client, db):
    spss = _category(db)
    subject = _post(db, "subject", category=spss)
    for i in range(6):
        _post(db, f"sibling-{i}", category=spss, published_at=NOW - timedelta(days=i))
    related = client.post("/api/v1/blog/get", json={"slug": subject.slug}).json()["related"]
    assert len(related) == 5
    assert subject.slug not in {p["slug"] for p in related}


def test_related_falls_back_to_shared_tags(client, db):
    _post(db, "subject", tags=["efa", "spss"])
    _post(db, "shares-a-tag", tags=["spss"])
    _post(db, "shares-nothing", tags=["smartpls"])
    related = client.post("/api/v1/blog/get", json={"slug": "subject"}).json()["related"]
    assert [p["slug"] for p in related] == ["shares-a-tag"]


def test_related_never_includes_a_hidden_post(client, db):
    spss = _category(db)
    _post(db, "subject", category=spss)
    _post(db, "hidden", category=spss, status=STATUS_DRAFT)
    assert client.post("/api/v1/blog/get", json={"slug": "subject"}).json()["related"] == []


def test_get_increments_views(client, db):
    post = _post(db, "counted")
    client.post("/api/v1/blog/get", json={"slug": "counted"})
    client.post("/api/v1/blog/get", json={"slug": "counted"})
    db.expire_all()
    assert db.get(BlogPost, post.id).views == 2


# --- categories ------------------------------------------------------------

def test_categories_count_only_visible_posts(client, db):
    spss = _category(db, "spss", "SPSS", 0)
    pls = _category(db, "smartpls", "SmartPLS", 1)
    _post(db, "a", category=spss)
    _post(db, "b", category=spss, status=STATUS_DRAFT)
    rows = client.post("/api/v1/blog/categories", json={}).json()["categories"]
    counts = {c["slug"]: c["post_count"] for c in rows}
    assert counts == {"spss": 1, "smartpls": 0}
    assert [c["slug"] for c in rows] == ["spss", "smartpls"]  # sort_order
    assert rows[0]["intro_md"]


def test_categories_returns_only_the_requested_locales_rows(client, db):
    _category(db, "spss", "SPSS", 0, locale="vi")
    _category(db, "spss", "SPSS", 0, locale="en")
    _category(db, "smartpls", "SmartPLS", 1, locale="vi")

    en = client.post("/api/v1/blog/categories", json={"locale": "en"}).json()["categories"]
    # One row, not three: the English hub list must not carry the Vietnamese
    # copy, and `spss` exists once per locale under the same slug on purpose.
    assert [c["slug"] for c in en] == ["spss"]

    vi = client.post("/api/v1/blog/categories", json={}).json()["categories"]
    assert [c["slug"] for c in vi] == ["spss", "smartpls"]


def test_category_post_counts_do_not_leak_across_locales(client, db):
    vi_spss = _category(db, "spss", "SPSS", 0, locale="vi")
    en_spss = _category(db, "spss", "SPSS", 0, locale="en")
    _post(db, "vi-a", category=vi_spss, locale="vi")
    _post(db, "en-a", category=en_spss, locale="en")
    _post(db, "en-b", category=en_spss, locale="en")

    en = client.post("/api/v1/blog/categories", json={"locale": "en"}).json()["categories"]
    assert {c["slug"]: c["post_count"] for c in en} == {"spss": 2}


def test_a_category_response_keeps_its_shape(client, db):
    _category(db)
    row = client.post("/api/v1/blog/categories", json={}).json()["categories"][0]
    # The web client reads exactly these keys. Adding `locale` here would be a
    # response-shape change, and the column exists to pick the row, not to be
    # rendered.
    assert set(row) == {"slug", "name", "display_name", "intro_md", "sort_order",
                        "post_count"}


# --- sitemap ---------------------------------------------------------------

def test_sitemap_lists_visible_posts_only(client, db):
    _post(db, "live")
    _post(db, "draft", status=STATUS_DRAFT)
    rows = client.post("/api/v1/blog/sitemap", json={}).json()
    assert [r["slug"] for r in rows] == ["live"]
    assert rows[0]["locale"] == "vi"
    assert rows[0]["updated_at"]


def test_sitemap_can_be_scoped_to_a_locale(client, db):
    _post(db, "vi-post", locale="vi")
    _post(db, "en-post", locale="en")
    rows = client.post("/api/v1/blog/sitemap", json={"locale": "en"}).json()
    assert [r["slug"] for r in rows] == ["en-post"]


# --- translations, for hreflang -------------------------------------------


def test_get_names_the_other_visible_editions_of_the_same_article(client, db):
    """Slugs differ per locale and a translated keyword is in its own language,
    so `translation_key` is the only thing that pairs two editions."""
    from datetime import datetime, timezone
    from app.blog import STATUS_PUBLISHED, STATUS_SCHEDULED
    from app.models import BlogPost

    now = datetime.now(timezone.utc)
    later = now.replace(year=now.year + 1)
    for locale, slug, status, when in (
        ("vi", "cronbach-alpha-la-gi", STATUS_PUBLISHED, now),
        ("en", "what-is-cronbach-alpha", STATUS_PUBLISHED, now),
        ("fr", "quest-ce-que-cronbach", STATUS_SCHEDULED, later),
    ):
        db.add(BlogPost(locale=locale, slug=slug, title=slug, body="x", excerpt="x",
                        status=status, published_at=when, scheduled_at=when,
                        translation_key="cronbach-alpha-la-gi"))
    db.add(BlogPost(locale="vi", slug="phuong-sai", title="Phương sai", body="x",
                    excerpt="x", status=STATUS_PUBLISHED, published_at=now,
                    translation_key="phuong-sai"))
    db.commit()

    body = client.post("/api/v1/blog/get",
                       json={"locale": "vi", "slug": "cronbach-alpha-la-gi"}).json()
    assert body["translations"] == [{"locale": "en", "slug": "what-is-cronbach-alpha"}], \
        "the scheduled French edition is not visible, so hreflang must not point at it"

    other = client.post("/api/v1/blog/get", json={"locale": "vi", "slug": "phuong-sai"}).json()
    assert other["translations"] == [], "an untranslated post has no pair to declare"
