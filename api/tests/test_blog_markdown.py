"""Markdown helpers, including the heading-id contract shared with the web.

`fixtures/blog/headings.{md,json}` is copied verbatim into the web package.
If this file and its vitest twin disagree by one character, every link in the
rendered contents box points at an anchor that does not exist.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.blog import markdown as md

FIXTURES = Path(__file__).parent / "fixtures" / "blog"


def _fixture():
    body = (FIXTURES / "headings.md").read_text(encoding="utf-8")
    expected = json.loads((FIXTURES / "headings.json").read_text(encoding="utf-8"))
    return body, expected


def test_headings_match_the_shared_fixture():
    body, expected = _fixture()
    got = [{"level": h.level, "text": h.text, "id": h.id} for h in md.headings(body)]
    assert got == expected["headings"]


def test_slugify_strips_vietnamese_diacritics():
    assert md.slugify("Phân tích EFA") == "phan-tich-efa"
    assert md.slugify("Kiểm định t-test") == "kiem-dinh-t-test"


def test_slugify_maps_d_with_stroke_to_d():
    # Đ / đ carry a stroke, not a combining mark, so NFD leaves them alone and
    # they need the explicit mapping every Vietnamese slugger has.
    assert md.slugify("Điều kiện áp dụng") == "dieu-kien-ap-dung"
    assert md.slugify("đại lượng") == "dai-luong"


def test_slugify_collapses_and_trims_punctuation():
    assert md.slugify("Ma trận xoay lộn xộn: phải làm sao?") == "ma-tran-xoay-lon-xon-phai-lam-sao"
    assert md.slugify("  ***Hồi quy***  ") == "hoi-quy"


def test_repeated_headings_get_numeric_suffixes():
    body = "## Phân tích EFA\n\n## Phân tích EFA\n\n## Phân tích EFA\n"
    assert [h.id for h in md.headings(body)] == [
        "phan-tich-efa", "phan-tich-efa-1", "phan-tich-efa-2"]


def test_headings_ignore_hashes_inside_fenced_code():
    body = "## Thật\n\n```\n## Không phải tiêu đề\n```\n\n## Cũng thật\n"
    assert [h.text for h in md.headings(body)] == ["Thật", "Cũng thật"]


def test_heading_text_drops_inline_markup():
    body = "## **Cronbach's Alpha** và `KMO`\n"
    (h,) = md.headings(body)
    assert h.text == "Cronbach's Alpha và KMO"
    assert h.id == "cronbach-s-alpha-va-kmo"


def test_faq_extraction_matches_the_shared_fixture():
    body, expected = _fixture()
    assert [q.question for q in md.faq(body)] == expected["faq_questions"]


def test_faq_answers_stop_at_the_next_question():
    body, _ = _fixture()
    first = md.faq(body)[0]
    assert first.answer.startswith("Từ 0.7 trở lên")
    assert "loại biến" not in first.answer


def test_faq_is_empty_when_there_is_no_faq_section():
    assert md.faq("## Mở đầu\n\n### Một câu hỏi?\n\nTrả lời.\n") == []


def test_internal_links_match_the_shared_fixture():
    body, expected = _fixture()
    assert md.internal_links(body) == expected["internal_links"]


def test_internal_links_ignore_external_urls_and_deduplicate():
    body = ("[a](/blog/vi/x) [b](https://example.com/y) [c](/blog/vi/x) "
            "[d](mailto:a@b.c) [e](#anchor)")
    assert md.internal_links(body) == ["/blog/vi/x"]


def test_links_reports_every_href_including_schemeless_ones():
    # WELE's link audit exists because authors pasted `example.com/x` with no
    # scheme and the browser resolved it under /blog/vi/. The audit needs to
    # see those, so `links` reports hrefs the internal-link filter drops.
    body = "[a](/landing) [b](example.com/x) [c](https://x.test)"
    assert [href for _, href in md.links(body)] == [
        "/landing", "example.com/x", "https://x.test"]


def test_word_count_ignores_link_urls():
    assert md.word_count("Xem [bảng ngưỡng](/blog/vi/do-tin-cay-thang-do) ngay.") == 4


def test_word_count_ignores_table_pipes_and_separator_rows():
    body = "| A | B |\n| --- | --- |\n| one | two |\n"
    assert md.word_count(body) == 4


def test_word_count_ignores_fenced_code_and_markup():
    body = "## Tiêu đề\n\n- **một** hai\n\n```python\nprint('ba bon nam')\n```\n"
    assert md.word_count(body) == 4  # Tiêu đề một hai


def test_plain_text_keeps_link_text_and_drops_images():
    text = md.plain_text("![alt text](/a.png) Xem [đây](/b) nhé.")
    assert text == "Xem đây nhé."


def test_reading_time_rounds_up_at_200_words_per_minute():
    assert md.reading_time(" ".join(["tu"] * 200)) == 1
    assert md.reading_time(" ".join(["tu"] * 201)) == 2
    assert md.reading_time("") == 1  # never zero minutes
