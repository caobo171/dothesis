"""qa: the mechanical gate, every FAIL class and every WARN class."""
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


def _seed_dir_linking_to(tmp_path, slug):
    """A copy of the exemplar with one extra link, in a directory of its own."""
    post = _passing_seed()
    post["body"] += f"\n\nĐọc thêm bài [ghi chú](/blog/vi/{slug}).\n"
    out = tmp_path / "posts"
    out.mkdir()
    (out / "0001-cronbach-alpha-la-gi.json").write_text(
        json.dumps(post, ensure_ascii=False), encoding="utf-8")
    return str(out)


def test_an_unresolvable_link_still_fails_without_the_flag(tmp_path, capsys):
    seed_dir = _seed_dir_linking_to(tmp_path, "khong-he-co-trong-backlog")
    assert qa.main([seed_dir]) == 1
    assert "resolve to nothing known" in capsys.readouterr().out


def test_known_slugs_file_teaches_the_standalone_gate_what_resolves(tmp_path, capsys):
    """The default is unchanged; the flag only widens what counts as known."""
    seed_dir = _seed_dir_linking_to(tmp_path, "khong-he-co-trong-backlog")
    listing = tmp_path / "known.txt"
    listing.write_text("# slugs that exist on the site\n\n"
                       "khong-he-co-trong-backlog\n"
                       "/blog/vi/mot-bai-khac\n", encoding="utf-8")

    assert qa.main([seed_dir, "--known-slugs", str(listing)]) == 0
    assert "0 failing" in capsys.readouterr().out
    assert qa.main(["--known-slugs=" + str(listing), seed_dir]) == 0
    assert qa.read_slug_file(str(listing)) == {"khong-he-co-trong-backlog", "mot-bai-khac"}


def test_citations_are_extracted_in_both_vietnamese_and_english_forms():
    body = ("Ngưỡng 0.7 (Nunnally, 1978) và 0.5 (Hair và cộng sự, 2010). "
            "Hair et al. (2022) đề xuất 5,000 lần lặp. "
            "Phiên bản SmartPLS 4 (2024) không phải là một trích dẫn.")
    keys = {(k, y) for k, y, _ in qa.citations(body)}
    assert ("nunnally", 1978) in keys
    assert ("hair", 2010) in keys
    assert ("hair", 2022) in keys
    assert all(y != 2024 for _, y in keys), "a version number in parentheses is not a citation"


# ------------------------------------------ the doubled bar for unmeasured pages


def _seed(status="measured", body_transform=None, **overrides):
    post = _passing_seed()
    post["gate_status"] = status
    if body_transform:
        post["body"] = body_transform(post["body"])
    post.update(overrides)
    return post


def _check(post):
    return qa.check_post(post, qa.known_slugs(PASSING_DIR))


def _unlink_one(body):
    """Turn the last internal link into plain text, dropping the count by one."""
    href = qa.internal_links(body)[-1]
    return re.sub(r"\[([^\]]*)\]\(" + re.escape(href) + r"\)", r"\1", body)


def _keep_tables(body, keep):
    """Delete every GFM table after the first `keep` of them."""
    lines = body.splitlines()
    out, i, seen = [], 0, 0
    while i < len(lines):
        if (qa._TABLE_DELIM_RE.match(lines[i]) and "|" in lines[i]
                and i > 0 and "|" in lines[i - 1]):
            end = i + 1
            while end < len(lines) and "|" in lines[end] and lines[end].strip():
                end += 1
            seen += 1
            if seen > keep:
                out.pop()  # the header row, already appended
                i = end
                continue
            out.extend(lines[i:end])
            i = end
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def test_both_spellings_of_unmeasured_mean_the_same_thing():
    """`family-inferred` is the legacy name; agent-facing code must not care."""
    assert qa.is_unmeasured({"gate_status": "unmeasured"})
    assert qa.is_unmeasured({"gate_status": "family-inferred"})
    assert not qa.is_unmeasured({"gate_status": "measured"})
    assert not qa.is_unmeasured({})


def test_the_exemplar_clears_the_doubled_bar_too():
    """Two elements, three tables, five links: it is what the higher bar asks for."""
    fails, _warns, stats = _check(_seed("unmeasured"))
    assert fails == []
    assert stats["unmeasured"] is True
    assert stats["elements"] == 2


@pytest.mark.parametrize("status", ["unmeasured", "family-inferred"])
def test_an_unmeasured_page_needs_two_proprietary_elements(status):
    """One element is enough for a measured page and not for this one."""
    strip_label = lambda b: b.replace("số liệu minh họa", "các con số dưới đây")

    fails, _, stats = _check(_seed("measured", strip_label))
    assert fails == [], "one of the three still clears a measured page"
    assert stats["elements"] == 1

    fails, _, stats = _check(_seed(status, strip_label))
    assert stats["elements"] == 1
    assert any("1 of the three proprietary elements" in f
               and "no measured search volume" in f for f in fails), fails


def test_a_measured_page_still_needs_one_proprietary_element():
    """structure.md has always said so; until now nothing checked it."""
    def strip_both(body):
        body = body.replace("số liệu minh họa", "các con số dưới đây")
        return re.sub(r"\(([A-Z][^()]{1,60}), (\d{4})\)", r"theo \1 năm \2", body)

    fails, _, stats = _check(_seed("measured", strip_both))
    assert stats["elements"] == 0
    assert any("0 of the three proprietary elements (none)" in f for f in fails), fails


def test_an_unmeasured_page_needs_a_fifth_internal_link():
    fails, _, stats = _check(_seed("measured", _unlink_one))
    assert fails == [] and stats["links"] == 4

    fails, _, _ = _check(_seed("unmeasured", _unlink_one))
    assert any("need at least 5" in f and "no measured search volume" in f
               for f in fails), fails


def test_an_unmeasured_page_needs_a_second_table():
    one_table = lambda b: _keep_tables(b, 1)
    _fails, _, stats = _check(_seed("measured", one_table))
    assert stats["tables"] == 1

    fails, _, _ = _check(_seed("unmeasured", one_table))
    assert any("1 table(s), a page with no measured search volume needs at least 2" in f
               for f in fails), fails


# --------------------------------------------- detecting a proprietary element

_TABLE = ("| Chỉ số | Ngưỡng | Nguồn |\n| --- | --- | --- |\n"
          "| Alpha | 0.7 | (Nunnally, 1978) |\n")
_PLAIN_TABLE = ("| Bước | Thao tác |\n| --- | --- |\n| 1 | Mở Analyze |\n")


def test_a_threshold_table_is_a_table_with_a_citation_in_its_rows():
    assert qa.proprietary_elements(_TABLE) == ["threshold-table"]


def test_a_citation_beside_a_table_is_not_a_threshold_table():
    """The rule is a source column, not a source somewhere on the page."""
    body = "Ngưỡng 0.7 (Nunnally, 1978) được dùng rộng rãi.\n\n" + _PLAIN_TABLE
    assert qa.proprietary_elements(body) == []


def test_a_citation_outside_the_allowlist_does_not_make_a_threshold_table():
    body = _TABLE.replace("(Nunnally, 1978)", "(Nguyenxyz, 2019)")
    assert qa.proprietary_elements(body) == []


@pytest.mark.parametrize("body", [
    "Dưới đây là số liệu minh họa cho thang đo.\n\n" + _PLAIN_TABLE,
    _PLAIN_TABLE + "\nBảng trên là số liệu minh họa, không phải kết quả nghiên cứu.\n",
])
def test_a_worked_table_is_labelled_either_side_of_the_table(body):
    assert qa.proprietary_elements(body) == ["worked-table"]


def test_the_worked_label_with_no_table_is_not_a_worked_table():
    assert qa.proprietary_elements("Đây là số liệu minh họa trong bài khác.") == []


@pytest.mark.parametrize("body", [
    "## Cách viết vào luận văn\n\nBạn có thể viết: thang đo đạt độ tin cậy.\n",
    "**Cách viết vào luận văn.** Bạn có thể viết: thang đo đạt độ tin cậy.\n",
])
def test_a_writing_paragraph_announces_itself_as_a_heading_or_a_bold_lead(body):
    assert qa.proprietary_elements(body) == ["writing-paragraph"]


def test_a_bare_mention_in_prose_is_not_a_writing_paragraph():
    """A cross-reference to another post's section is not the section."""
    body = "Phần cách viết vào luận văn nằm ở bài về EFA.\n"
    assert qa.proprietary_elements(body) == []


def test_all_three_elements_are_reported_in_a_stable_order():
    body = (_TABLE + "\nBảng số liệu minh họa:\n\n" + _PLAIN_TABLE
            + "\n## Cách viết vào luận văn\n\nBạn viết như sau.\n")
    assert qa.proprietary_elements(body) == list(qa.PROPRIETARY_ELEMENTS)


# ----------------------------------------------------- corpus near-duplication


def _sketch(body):
    return qa.sketch(body)


def _j(a, b):
    return qa.sketch_jaccard(_sketch(a), _sketch(b))


def test_the_sketch_is_reproducible_across_processes():
    """`hash()` is salted per process; a sketch built yesterday must still compare."""
    body = _passing_seed()["body"]
    assert qa.shingle_hashes(body) == qa.shingle_hashes(body)
    assert qa.shingle_hashes("mot hai ba bon nam sau") == {
        qa.zlib.crc32("mot hai ba bon nam".encode("utf-8")),
        qa.zlib.crc32("hai ba bon nam sau".encode("utf-8")),
    }


def test_shingles_ignore_punctuation_and_case():
    assert (qa.shingle_hashes("Một hai, ba; bốn năm")
            == qa.shingle_hashes("một  hai ba bốn  NĂM"))


def test_a_body_is_a_perfect_duplicate_of_itself():
    body = _passing_seed()["body"]
    assert _j(body, body) == 1.0


def test_a_swapped_noun_refill_scores_far_above_the_threshold():
    """The failure the gate exists for: one term replaced, everything else kept."""
    body = _passing_seed()["body"]
    swapped = body.replace("SPSS", "SmartPLS").replace("Alpha", "Omega")
    score = _j(body, swapped)
    assert score > 0.6, score
    assert score >= qa.NEAR_DUPLICATE, "a measured pair this close must fail too"


def test_two_genuinely_different_posts_score_under_the_stricter_threshold():
    """Calibrated on the real bank: no pair of the 421 seeds exceeds 0.081."""
    a = _passing_seed()["body"]
    b = ("## Chọn mẫu cho luận văn\n\nCỡ mẫu phụ thuộc số biến quan sát và "
         "phương pháp phân tích bạn dự định chạy. " * 60)
    assert _j(a, b) < qa.NEAR_DUPLICATE_UNMEASURED


def test_the_unmeasured_threshold_is_exactly_twice_as_strict():
    assert qa.NEAR_DUPLICATE_UNMEASURED == qa.NEAR_DUPLICATE / 2
    assert qa.pair_threshold(False, False) == qa.NEAR_DUPLICATE
    for pair in [(True, False), (False, True), (True, True)]:
        assert qa.pair_threshold(*pair) == qa.NEAR_DUPLICATE_UNMEASURED


def test_a_pair_can_pass_as_measured_and_fail_as_unmeasured():
    """The whole point of the doubled bar, on one body."""
    body = _passing_seed()["body"]
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    half = "\n\n".join(paragraphs[:len(paragraphs) // 4])
    score = _j(body, half + "\n\n" + "Một câu khác hẳn về cỡ mẫu và thang đo. " * 400)
    assert qa.NEAR_DUPLICATE_UNMEASURED <= score < qa.NEAR_DUPLICATE, score

    def docs(unmeasured):
        return [{"key": "a", "unmeasured": False, "sketch": _sketch(body)},
                {"key": "b", "unmeasured": unmeasured,
                 "sketch": _sketch(half + "\n\n" + "Một câu khác hẳn về cỡ mẫu và thang đo. " * 400)}]

    assert qa.near_duplicates(docs(False)) == []
    hit = qa.near_duplicates(docs(True))
    assert len(hit) == 1 and hit[0]["unmeasured"] is True


def test_a_short_body_keeps_every_shingle_and_still_compares():
    """The dense fallback: a sampled sketch of a short doc is too thin to trust."""
    short = "một hai ba bốn năm sáu bảy tám chín mười " * 5
    dense = _sketch(short)
    assert dense.dense and len(dense) == dense.shingles

    long_body = _passing_seed()["body"]
    assert not _sketch(long_body).dense
    # A dense sketch is put back on the sampled plane before it meets a sampled
    # one, so an unrelated pair scores near zero rather than accidentally high.
    assert _j(short, long_body) < 0.01
    assert _j(short, short) == 1.0


def test_candidates_come_from_the_index_not_from_every_pair(monkeypatch):
    """60 documents sharing no vocabulary must cost no pair comparisons at all."""
    calls = []
    real = qa.sketch_jaccard
    monkeypatch.setattr(qa, "sketch_jaccard",
                        lambda a, b: (calls.append(1), real(a, b))[1])
    docs = [{"key": f"d{i}", "unmeasured": False,
             "sketch": _sketch(" ".join(f"tu{i}x{w}" for w in range(400)))}
            for i in range(60)]
    assert qa.near_duplicates(docs) == []
    assert calls == [], f"{len(calls)} comparisons for 1,770 possible pairs"


def _corpus_dir(tmp_path, bodies):
    out = tmp_path / "posts"
    out.mkdir()
    base = _passing_seed()
    for i, (slug, status, body) in enumerate(bodies, 1):
        post = dict(base, slug=slug, gate_status=status, body=body)
        (out / f"{i:04d}-{slug}.json").write_text(
            json.dumps(post, ensure_ascii=False), encoding="utf-8")
    return str(out)


def test_corpus_mode_fails_a_refilled_page_and_names_both_slugs(tmp_path, capsys):
    body = _passing_seed()["body"]
    swapped = body.replace("Alpha", "Omega")
    seed_dir = _corpus_dir(tmp_path, [
        ("cronbach-alpha-la-gi", "measured", body),
        ("omega-la-gi", "unmeasured", swapped),
    ])
    assert qa.main([seed_dir, "--corpus"]) == 1
    out = capsys.readouterr().out
    assert "cronbach-alpha-la-gi" in out and "omega-la-gi" in out
    assert "1 near-duplicate pair(s)" in out
    assert "(unmeasured)" in out
    assert "words" in out and "status" in out, "the per-file table is unchanged"


def test_corpus_mode_clears_pages_that_share_a_skeleton_but_not_their_substance():
    """The negative control, and the reason the limit sits where it does.

    Template siblings share the archetype skeleton, the domain vocabulary and
    the citation allowlist, so a naive comparison flags the whole family. Only
    the substance is compared, and on the real 421-post bank on 2026-09-08 the
    closest pair scored 0.081 with a p99 of 0.038, so the 0.175 unmeasured
    limit sits more than twice above anything the writer actually produces.
    """
    headings = ("## {} là gì", "## Ý nghĩa trong nghiên cứu định lượng",
                "## {} bao nhiêu là đạt", "## Cách đọc trên output",
                "## Lỗi thường gặp", "## Câu hỏi thường gặp")

    def page(term, sentences):
        parts = []
        for h in headings:
            parts.append(h.format(term))
            parts.extend(sentences)
        return "\n\n".join(parts)

    alpha = page("Cronbach's Alpha", [
        "Hệ số này đo mức độ nhất quán nội bộ giữa các biến quan sát của một thang đo.",
        "Ngưỡng 0.7 được chấp nhận rộng rãi, và 0.6 vẫn dùng được với khái niệm mới.",
        "Bảng Item-Total Statistics cho biết loại biến nào thì hệ số tăng lên.",
        "Sinh viên hay quên rằng biến đảo chiều phải được mã hóa lại trước khi chạy.",
    ])
    vif = page("VIF", [
        "Chỉ số này cho biết một biến độc lập bị giải thích bao nhiêu bởi các biến còn lại.",
        "Giá trị dưới 2 là an toàn, vượt quá 10 thì mô hình gần như chắc chắn có vấn đề.",
        "Cột Collinearity Statistics nằm trong bảng Coefficients của phần hồi quy.",
        "Cách xử lý thường là bỏ bớt một biến trùng nội dung chứ không phải thêm quan sát.",
    ])

    docs = [
        {"key": "cronbach-alpha-la-gi", "unmeasured": True, "sketch": qa.sketch(alpha)},
        {"key": "vif-la-gi", "unmeasured": True, "sketch": qa.sketch(vif)},
    ]
    assert qa.near_duplicates(docs) == [], "same skeleton, different substance"
    # And the score is not merely under the limit, it is far under it.
    assert qa.sketch_jaccard(docs[0]["sketch"], docs[1]["sketch"]) < 0.10


def test_corpus_mode_reports_a_clean_bank(tmp_path, capsys):
    seed_dir = _corpus_dir(tmp_path, [
        ("cronbach-alpha-la-gi", "measured", _passing_seed()["body"]),
    ])
    assert qa.main([seed_dir, "--corpus"]) == 0
    assert "no pair is a near duplicate" in capsys.readouterr().out


def test_corpus_mode_is_off_unless_asked(tmp_path, capsys):
    """Without the flag the gate behaves exactly as it did."""
    body = _passing_seed()["body"]
    seed_dir = _corpus_dir(tmp_path, [
        ("cronbach-alpha-la-gi", "measured", body),
        ("cronbach-alpha-spss", "measured", body),
    ])
    assert qa.main([seed_dir]) == 0
    out = capsys.readouterr().out
    assert "near-duplicate" not in out
    assert qa.main([seed_dir, "--corpus"]) == 1


def test_the_engine_cli_forwards_the_corpus_flag(tmp_path, capsys):
    """The subcommand and `qa.main` must agree: the flag fell between two
    owners once already and the corpus check silently did not run."""
    from app.blog.content import cli

    body = _passing_seed()["body"]
    seed_dir = _corpus_dir(tmp_path, [
        ("cronbach-alpha-la-gi", "measured", body),
        ("omega-la-gi", "unmeasured", body.replace("Alpha", "Omega")),
    ])
    assert cli.main(["qa", seed_dir]) == 0, "without the flag, one seed at a time"
    assert cli.main(["qa", seed_dir, "--corpus"]) == 1
    assert "near-duplicate pair(s)" in capsys.readouterr().out


def test_a_threshold_table_may_be_sourced_in_the_sentence_above_it():
    """How the sentence is actually written, and where the line sits.

    Measured on the first bank: 20 posts carried a genuine threshold table whose
    source was in the paragraph introducing it. A citation beside a table that
    states no threshold still buys nothing, which is the case the test below
    this one holds.
    """
    above = ("Theo (Hair và cộng sự, 2010), tỷ lệ quan sát trên biến là 5:1.\n\n"
             "| Số biến | Mức tối thiểu |\n|---|---:|\n| 20 | 100 |\n| 30 | 150 |\n")
    unsourced = ("Bảng dưới đây tổng hợp các mức thường gặp.\n\n"
                 "| Số biến | Mức tối thiểu |\n|---|---:|\n| 20 | 100 |\n")
    assert "threshold-table" in qa.proprietary_elements(above)
    assert "threshold-table" not in qa.proprietary_elements(unsourced)
