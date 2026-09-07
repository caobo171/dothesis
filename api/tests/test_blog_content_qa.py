"""qa: the mechanical gate, every FAIL class and every WARN class."""
import copy
import json
import os
import re
import unicodedata

import pytest

from app.blog.content import qa


@pytest.fixture(autouse=True)
def _bind_db():
    """No database in the content engine. See test_blog_content_expand.py."""
    yield


TESTS_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
FIXTURES = os.path.join(TESTS_DIR, "fixtures", "blog", "content")
PASSING_DIR = os.path.join(FIXTURES, "passing")
FAILING_DIR = os.path.join(FIXTURES, "failing")
SKILL_DIR = os.path.join(REPO_ROOT, ".claude", "skills", "dothesis-blog-content", "references")


def _passing_seed():
    path = os.path.join(PASSING_DIR, "0001-cronbach-alpha-la-gi.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------- the good seed


def test_the_exemplar_passes_and_is_a_real_article():
    post = _passing_seed()
    fails, warns, stats = qa.check_post(post, qa.known_slugs(PASSING_DIR))
    assert fails == []
    assert warns == []
    assert stats["words"] >= 1600, "the exemplar is what the skill points writers at"
    assert stats["h2"] >= 6 and stats["faq"] >= 4 and stats["tables"] >= 1
    assert stats["links"] >= qa.MIN_INTERNAL_LINKS


def test_main_reports_the_passing_directory_and_exits_zero(capsys):
    assert qa.main([PASSING_DIR]) == 0
    out = capsys.readouterr().out
    assert "words" in out and "status" in out
    assert "0001-cronbach-alpha-la-gi.json" in out
    assert "1 file(s), 0 failing" in out


def test_main_exits_one_on_a_failing_directory(capsys):
    assert qa.main([FAILING_DIR]) == 1
    out = capsys.readouterr().out
    assert "Detail" in out
    assert "FAIL" in out
    assert "21 file(s), 21 failing" in out


def test_main_refuses_a_directory_that_is_not_there(capsys):
    assert qa.main([os.path.join(FIXTURES, "nope")]) == 1
    assert "no seed dir" in capsys.readouterr().out


# ------------------------------------------------------------ every FAIL class

FAILURE_CASES = [
    ("01-bad-json.json", "JSON does not parse"),
    ("02-missing-field.json", "missing required field `meta_description`"),
    ("03-schema-mismatch.json", "schema is"),
    ("04-unknown-category.json", "is not one of the nine"),
    ("05-slug-not-normalised.json", "is not normalised"),
    ("06-meta-title-too-long.json", "meta_title is 110 chars"),
    ("07-meta-description-too-short.json", "meta_description is 23 chars"),
    ("08-body-too-short.json", "floor is 1500"),
    ("09-too-few-h2.json", "H2 sections, need at least 5"),
    ("10-no-faq.json", "no `## Câu hỏi thường gặp`"),
    ("11-too-few-faq-questions.json", "FAQ has 3 questions"),
    ("12-no-table.json", "no table"),
    ("13-em-dash.json", "em dash"),
    ("14-exclamation.json", "exclamation mark"),
    ("15-blacklisted-phrase.json", "blacklisted phrase"),
    ("16-citation-not-in-allowlist.json", "not in canonical-sources.md"),
    ("17-too-few-internal-links.json", "distinct internal links"),
    ("18-unknown-internal-link.json", "resolve to nothing known"),
    ("19-raw-html.json", "raw HTML tag"),
    ("20-dangling-image-ref.json", "no images[] entry"),
    ("21-qualitative-instruction.json", "quantitative only"),
]


@pytest.mark.parametrize("filename,expected", FAILURE_CASES)
def test_each_failure_class_is_caught(filename, expected):
    slugs = qa.known_slugs(PASSING_DIR)
    _, fails, _, _ = qa.check_file(os.path.join(FAILING_DIR, filename), slugs)
    assert any(expected in f for f in fails), f"{filename}: {fails}"


def test_every_failing_fixture_is_covered_by_a_case():
    on_disk = {f for f in os.listdir(FAILING_DIR) if f.endswith(".json")}
    assert on_disk == {name for name, _ in FAILURE_CASES}


# ------------------------------------------------------------ every WARN class


def _warns_for(body_transform=None, **overrides):
    post = _passing_seed()
    if body_transform:
        post["body"] = body_transform(post["body"])
    post.update(overrides)
    fails, warns, _ = qa.check_post(post, qa.known_slugs(PASSING_DIR))
    return fails, warns


def test_warn_on_a_body_over_three_thousand_words():
    fails, warns = _warns_for(lambda b: b + "\n\n" + ("thêm một từ nữa " * 700))
    assert fails == []
    assert any("soft ceiling" in w for w in warns)


def test_warn_on_a_paragraph_over_120_words():
    long_para = "Câu này rất dài và cứ tiếp tục mãi không dừng lại " * 30
    fails, warns = _warns_for(lambda b: b.replace(
        "## Lỗi thường gặp", long_para + "\n\n## Lỗi thường gặp"))
    assert fails == []
    assert any("a paragraph runs" in w for w in warns)


def test_warn_on_a_percentage_claim_outside_a_table():
    fails, warns = _warns_for(lambda b: b.replace(
        "## Lỗi thường gặp",
        "Khoảng 62% luận văn gặp lỗi này ở vòng chạy đầu tiên.\n\n## Lỗi thường gặp"))
    assert fails == []
    assert any("percentage outside a table" in w for w in warns)


def test_warn_on_nghien_cuu_cho_thay_without_a_citation():
    fails, warns = _warns_for(lambda b: b.replace(
        "## Lỗi thường gặp",
        "Nghiên cứu cho thấy thang đo dài thường có Alpha cao hơn.\n\n## Lỗi thường gặp"))
    assert fails == []
    assert any("nghiên cứu cho thấy" in w for w in warns)


def test_warn_on_a_second_cta_link():
    fails, warns = _warns_for(lambda b: b.replace(
        "## Lỗi thường gặp",
        "Xem thêm ở [DoThesis](/landing).\n\n## Lỗi thường gặp"))
    assert fails == []
    assert any("CTA links" in w for w in warns)


def test_warn_on_a_duplicate_h2():
    fails, warns = _warns_for(lambda b: b.replace(
        "## Lỗi thường gặp", "## Cronbach's Alpha là gì", 1))
    assert fails == []
    assert any("duplicate H2" in w for w in warns)


# --------------------------------------------------------- the shared slugger


def test_vendored_heading_ids_match_the_shared_fixture():
    """qa.py cannot import app.blog.markdown, so it must not drift from it.

    The contents box on the web is built from one implementation and the
    anchors from another; a single character of drift breaks every in-page link.
    """
    md_path = os.path.join(TESTS_DIR, "fixtures", "blog", "headings.md")
    json_path = os.path.join(TESTS_DIR, "fixtures", "blog", "headings.json")
    assert os.path.isfile(md_path) and os.path.isfile(json_path), (
        "the shared heading fixture should exist; if it does not, the api and web "
        "sides have nothing pinning them together")
    body = open(md_path, encoding="utf-8").read()
    expected = json.load(open(json_path, encoding="utf-8"))

    got = [{"level": lvl, "text": text, "id": ident} for lvl, text, ident in qa.headings(body)]
    assert got == expected["headings"]
    assert qa.faq_questions(body) == expected["faq_questions"]
    assert qa.internal_links(body) == expected["internal_links"]


def test_vendored_slugify_handles_vietnamese_and_repeats():
    assert qa.slugify("Phân tích EFA") == "phan-tich-efa"
    assert qa.slugify("Độ tin cậy thang đo") == "do-tin-cay-thang-do"
    assert qa.slugify("Đề tài luận văn") == "de-tai-luan-van"
    slugger = qa.Slugger()
    assert [slugger.slug("Phân tích EFA") for _ in range(3)] == [
        "phan-tich-efa", "phan-tich-efa-1", "phan-tich-efa-2"]


# ------------------------------------------------- the skill files are the source


def _parse_canonical_sources():
    """(surname key, year) for every in-text citation string in the skill file."""
    path = os.path.join(SKILL_DIR, "canonical-sources.md")
    keys = set()
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^\|\s*`\(([^`]+?),\s*(\d{4})\)`", line)
        if not m:
            continue
        name = unicodedata.normalize("NFD", m.group(1))
        name = "".join(c for c in name if unicodedata.category(c) != "Mn")
        keys.add((name.replace("đ", "d").lower().split()[0], int(m.group(2))))
    return keys


def test_citation_allowlist_matches_the_skill_file():
    assert _parse_canonical_sources() == set(qa.ALLOWED_CITATIONS)


def test_blacklist_matches_the_voice_file():
    text = open(os.path.join(SKILL_DIR, "voice.md"), encoding="utf-8").read()
    section = text.split("## Slop blacklist", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^- `([^`]+)`$", section, flags=re.M)
    assert listed, "voice.md should list the blacklisted phrases as backticked bullets"
    assert set(listed) == set(qa.BLACKLIST)


def test_categories_and_archetypes_match_the_engine():
    from app.blog.content.expand import ARCHETYPES, CATEGORY_SLUGS

    assert set(CATEGORY_SLUGS) == qa.ALLOWED_CATEGORIES
    assert set(ARCHETYPES) == qa.ALLOWED_ARCHETYPES


# ------------------------------------------------------------------- links


def test_link_resolution_knows_categories_routes_and_batch_slugs():
    slugs = {"cronbach-alpha-la-gi"}
    assert qa._link_is_known("/blog/vi/chu-de/spss", slugs)
    assert qa._link_is_known("/blog/vi/cronbach-alpha-la-gi", slugs)
    assert qa._link_is_known("/landing", slugs)
    assert qa._link_is_known("/blog/vi", slugs)
    assert not qa._link_is_known("/blog/vi/chu-de/tin-tuc", slugs)
    assert not qa._link_is_known("/blog/vi/khong-co-bai-nay", slugs)
    assert not qa._link_is_known("/chat", slugs)


def test_citations_are_extracted_in_both_vietnamese_and_english_forms():
    body = ("Ngưỡng 0.7 (Nunnally, 1978) và 0.5 (Hair và cộng sự, 2010). "
            "Hair et al. (2022) đề xuất 5,000 lần lặp. "
            "Phiên bản SmartPLS 4 (2024) không phải là một trích dẫn.")
    keys = {(k, y) for k, y, _ in qa.citations(body)}
    assert ("nunnally", 1978) in keys
    assert ("hair", 2010) in keys
    assert ("hair", 2022) in keys
    assert all(y != 2024 for _, y in keys), "a version number in parentheses is not a citation"
