"""plan: harvest + gate survivors -> backlog.tsv."""
import csv
import os

import pytest

from app.blog.content import plan


@pytest.fixture(autouse=True)
def _bind_db():
    """No database in the content engine. See test_blog_content_expand.py."""
    yield


def _write_tsv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return str(path)


HARVEST_HEADER = ["keyword", "search_volume", "kd", "intent", "competitor", "rank", "url"]


# ------------------------------------------------------------------ clustering


def test_cluster_key_folds_phrasings_of_one_intent_together():
    assert plan.cluster_key("cronbach alpha là gì") == plan.cluster_key("cronbach alpha")
    assert plan.cluster_key("hệ số cronbach alpha") == plan.cluster_key("cronbach alpha")
    assert plan.cluster_key("cronbach alpha bao nhiêu là tốt") == plan.cluster_key("cronbach alpha")
    # and keeps genuinely different intents apart
    assert plan.cluster_key("cronbach alpha là gì") != plan.cluster_key("efa là gì")
    assert plan.cluster_key("hồi quy tuyến tính là gì") != plan.cluster_key(
        "cách chạy hồi quy trong spss")


def test_clustering_keeps_the_biggest_phrasing_and_demotes_the_rest():
    phrasings = [
        plan.Phrasing("cronbach alpha", 1300, "reliability", "spss", "term-la-gi"),
        plan.Phrasing("cronbach alpha là gì", 880, "reliability", "spss", "term-la-gi"),
        plan.Phrasing("hệ số cronbach alpha", 210, "reliability", "spss", "term-la-gi"),
    ]
    rows = plan.build(phrasings)
    assert len(rows) == 1
    assert rows[0].focus_keyword == "cronbach alpha"
    assert rows[0].search_volume == 1300
    assert rows[0].secondary_keywords == ["cronbach alpha là gì", "hệ số cronbach alpha"]
    assert rows[0].slug == "cronbach-alpha"


def test_identical_volume_and_a_shared_head_token_merge_as_one_page():
    """WELE's morphological merge: close-variant grouping shows up as one number."""
    phrasings = [
        plan.Phrasing("thang đo likert", 1600, "measurement", "khao-sat", "term-la-gi"),
        plan.Phrasing("thang đo likert 5 mức độ", 1600, "measurement", "khao-sat", "term-la-gi"),
        plan.Phrasing("thang đo likert 7 mức độ", 90, "measurement", "khao-sat", "term-la-gi"),
    ]
    rows = plan.build(phrasings)
    slugs = {r.slug for r in rows}
    assert "thang-do-likert" in slugs
    assert "thang-do-likert-7-muc-do" in slugs, "a genuinely different volume stays its own page"
    merged = next(r for r in rows if r.slug == "thang-do-likert")
    assert "thang đo likert 5 mức độ" in merged.secondary_keywords


# ------------------------------------------------------------------ exclusions


def test_exclusions_drop_off_topic_harvest_rows(tmp_path):
    harvest = _write_tsv(tmp_path / "harvest.tsv", HARVEST_HEADER, [
        ["đáp án ets 2016 part 1234", "27100", "0", "navigational", "phamlocblog.com", "5", "/x"],
        ["bậc của đa thức", "2400", "0", "informational", "phamlocblog.com", "3", "/y"],
        ["tải spss", "1900", "0", "transactional", "phamlocblog.com", "2", "/z"],
        ["dịch vụ spss", "1900", "14", "informational", "phamlocblog.com", "1", "/w"],
        ["cronbach alpha", "1300", "0", "informational", "phantichspss.com", "4", "/v"],
    ])
    exclusions = tmp_path / "exclusions.txt"
    exclusions.write_text("# comment line\ntoeic\nđáp án ets\nđa thức\n\\btải\\b\ndịch vụ\n",
                          encoding="utf-8")

    kept, dropped = plan.read_harvest(harvest, plan.load_exclusions(str(exclusions)))
    assert [p.keyword for p in kept] == ["cronbach alpha"]
    assert len(dropped) == 4


def test_committed_exclusions_file_compiles_and_cuts_the_known_junk():
    patterns = plan.load_exclusions()
    assert patterns, "docs/seo/topic-bank/exclusions.txt should not be empty"
    for keyword in ["đáp án ets 2016", "600 từ vựng toeic", "bậc của đa thức",
                    "cú pháp khai báo biến", "loc", "crack spss", "spss download",
                    "dịch vụ chạy spss", "siberian wellness lừa đảo", "spss 27",
                    "d f", "d f# là gì", "o r là gì", "model la gi"]:
        assert plan.is_excluded(keyword, "", patterns), f"{keyword!r} should be excluded"
    for keyword in ["cronbach alpha", "cách chạy efa trong spss", "thang đo likert",
                    "ma trận xoay", "cỡ mẫu là gì", "mô hình servqual"]:
        assert not plan.is_excluded(keyword, "", patterns), f"{keyword!r} should survive"


# --------------------------------------------------------- category, archetype


def test_harvest_rows_get_a_category_and_an_archetype():
    assert plan.classify_category("cách chạy efa trong spss") == "spss"
    assert plan.classify_category("bootstrapping trong smartpls") == "smartpls"
    assert plan.classify_category("cỡ mẫu là gì") == "khao-sat"
    assert plan.classify_category("mô hình servqual") == "mo-hinh-nghien-cuu"
    assert plan.classify_category("cách viết khóa luận tốt nghiệp") == "khoa-luan-tot-nghiep"
    assert plan.classify_category("p value là gì") == "thong-ke"

    assert plan.classify_archetype("cronbach alpha là gì") == "term-la-gi"
    assert plan.classify_archetype("cách chạy hồi quy trong spss") == "spss-howto"
    assert plan.classify_archetype("bootstrapping trong smartpls") == "smartpls-howto"
    assert plan.classify_archetype("kiểm định t-test") == "test"
    assert plan.classify_archetype("ma trận xoay lộn xộn phải làm sao") == "troubleshoot"
    assert plan.classify_archetype("đề tài luận văn marketing") == "topic-list"
    assert plan.classify_archetype("thang đo sự hài lòng") == "scale"


# -------------------------------------------------------------------- siblings


def test_every_row_gets_three_to_five_siblings_family_first():
    phrasings = [plan.Phrasing(f"kw efa {i}", 1000 - i, "efa", "spss", "term-la-gi")
                 for i in range(6)]
    phrasings += [plan.Phrasing(f"kw reg {i}", 500 - i, "regression", "spss", "term-la-gi")
                  for i in range(3)]
    rows = {r.focus_keyword: r for r in plan.build(phrasings)}

    efa_row = rows["kw efa 0"]
    assert 3 <= len(efa_row.sibling_slugs) <= 5
    assert all(s.startswith("kw-efa") for s in efa_row.sibling_slugs), "family first"
    assert efa_row.slug not in efa_row.sibling_slugs, "never links to itself"

    reg_row = rows["kw reg 0"]
    assert len(reg_row.sibling_slugs) >= 3, "a thin family is topped up from the category"
    assert any(s.startswith("kw-efa") for s in reg_row.sibling_slugs)


def test_siblings_are_empty_when_there_is_nothing_to_link_to():
    rows = plan.build([plan.Phrasing("lẻ loi", 100, "misc", "spss", "term-la-gi")])
    assert rows[0].sibling_slugs == []


# ---------------------------------------------------------------- round robin


def test_rows_are_ordered_category_round_robin_by_volume():
    phrasings = [
        plan.Phrasing("spss a", 900, "f1", "spss", "term-la-gi"),
        plan.Phrasing("spss b", 800, "f1", "spss", "term-la-gi"),
        plan.Phrasing("spss c", 700, "f1", "spss", "term-la-gi"),
        plan.Phrasing("pls a", 600, "f2", "smartpls", "smartpls-howto"),
        plan.Phrasing("pls b", 500, "f2", "smartpls", "smartpls-howto"),
    ]
    rows = plan.build(phrasings)
    assert [r.priority for r in rows] == [1, 2, 3, 4, 5]
    categories = [r.category for r in rows]
    assert categories[:4] == ["spss", "smartpls", "spss", "smartpls"]
    assert [r.focus_keyword for r in rows][:2] == ["spss a", "pls a"], "best of each first"


# -------------------------------------------------------------- the whole run


def test_run_writes_backlog_tsv_with_the_agreed_columns(tmp_path):
    harvest = _write_tsv(tmp_path / "harvest.tsv", HARVEST_HEADER, [
        ["cronbach alpha", "1300", "0", "informational", "phantichspss.com", "4", "/cronbach"],
        ["cronbach alpha là gì", "880", "0", "informational", "xulysolieu.info", "2", "/ca-la-gi"],
        ["tải spss", "1900", "0", "transactional", "phamlocblog.com", "2", "/tai-spss"],
    ])
    candidates = _write_tsv(
        tmp_path / "candidates.tsv",
        ["keyword", "axis", "unit", "family", "category", "archetype"],
        [["ma trận xoay lộn xộn phải làm sao", "troubleshoot", "ma-tran-xoay-lon-xon",
          "efa", "spss", "troubleshoot"],
         ["biến hiếm là gì", "statistical-term", "bien-hiem", "misc", "thong-ke", "term-la-gi"]])
    _write_tsv(tmp_path / "gate-troubleshoot.tsv",
               ["keyword", "search_volume", "verdict", "reason"],
               [["ma trận xoay lộn xộn phải làm sao", "6600", "pass", "volume 6600"]])
    _write_tsv(tmp_path / "gate-statistical-term.tsv",
               ["keyword", "search_volume", "verdict", "reason"],
               [["biến hiếm là gì", "5", "pass",
                 "volume 5 under 10, family 'misc' aggregate 900"]])
    exclusions = tmp_path / "exclusions.txt"
    exclusions.write_text("\\btải\\b\n", encoding="utf-8")

    out = tmp_path / "backlog.tsv"
    summary = plan.run(harvest_path=harvest, candidates_path=candidates,
                       gate_dir=str(tmp_path), exclusions_path=str(exclusions),
                       out_path=str(out), index_path=None)

    with open(out, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    assert list(rows[0]) == list(plan.BACKLOG_COLUMNS)
    by_slug = {r["slug"]: r for r in rows}
    assert "cronbach-alpha" in by_slug
    assert "tai-spss" not in by_slug, "excluded rows never reach the backlog"
    assert by_slug["cronbach-alpha"]["secondary_keywords"] == "cronbach alpha là gì"
    assert "phantichspss.com:/cronbach" in by_slug["cronbach-alpha"]["competitor_urls"]
    assert by_slug["cronbach-alpha"]["gate_status"] == "measured"
    assert by_slug["bien-hiem-la-gi"]["gate_status"] == "family-inferred"
    assert summary["rows"] == 3
    assert summary["excluded"] == 1


def test_run_skips_slugs_already_in_the_blog_index(tmp_path):
    harvest = _write_tsv(tmp_path / "harvest.tsv", HARVEST_HEADER, [
        ["cronbach alpha", "1300", "0", "informational", "phantichspss.com", "4", "/c"],
        ["ma trận xoay", "6600", "0", "informational", "phamlocblog.com", "1", "/m"],
    ])
    candidates = _write_tsv(tmp_path / "candidates.tsv",
                            ["keyword", "axis", "unit", "family", "category", "archetype"], [])
    index = tmp_path / "blog-index.md"
    index.write_text("- [Cronbach](/blog/vi/cronbach-alpha) 1,900 words\n", encoding="utf-8")

    out = tmp_path / "backlog.tsv"
    summary = plan.run(harvest_path=harvest, candidates_path=candidates,
                       gate_dir=str(tmp_path), exclusions_path=os.devnull,
                       out_path=str(out), index_path=str(index))
    slugs = [r["slug"] for r in csv.DictReader(open(out, encoding="utf-8"), delimiter="\t")]
    assert slugs == ["ma-tran-xoay"]
    assert summary["already_covered"] == 1


def test_family_inferred_rows_come_after_every_measured_row():
    """Drafts must not consume early slots.

    `create` schedules in priority order and a family-inferred row is inserted
    as DRAFT, never scheduled, so a low priority number spent on one would push
    a measured page out of the first tranche.
    """
    phrasings = [
        plan.Phrasing("spss alpha", 900, "f1", "spss", "term-la-gi"),
        plan.Phrasing("spss beta", 5, "f1", "spss", "term-la-gi",
                      gate_status="family-inferred"),
        plan.Phrasing("pls gamma", 800, "f2", "smartpls", "smartpls-howto"),
        plan.Phrasing("pls delta", 700, "f2", "smartpls", "smartpls-howto"),
        plan.Phrasing("pls epsilon", 600, "f2", "smartpls", "smartpls-howto"),
    ]
    rows = plan.build(phrasings)
    assert [r.gate_status for r in rows] == ["measured"] * 4 + ["family-inferred"]
    assert [r.priority for r in rows] == [1, 2, 3, 4, 5]
    # the measured tier keeps the category round robin it had before
    assert [r.focus_keyword for r in rows][:2] == ["spss alpha", "pls gamma"]


def test_family_inferred_rows_of_a_big_category_still_wait_for_small_categories():
    """The tier split beats the round robin, not the other way round."""
    phrasings = [plan.Phrasing(f"spss d{i}", 100 - i, "f1", "spss", "term-la-gi",
                               gate_status="family-inferred") for i in range(3)]
    phrasings.append(plan.Phrasing("luan van m", 40, "f2", "luan-van-thac-si",
                                   "thesis-writing"))
    rows = plan.build(phrasings)
    assert rows[0].focus_keyword == "luan van m"
    assert all(r.gate_status == "family-inferred" for r in rows[1:])


def test_a_candidate_measured_through_the_harvest_stays_measured(tmp_path):
    """Exact keyword match with a harvest row is measurement, whatever the gate said."""
    harvest = _write_tsv(tmp_path / "harvest.tsv", HARVEST_HEADER, [
        ["biến hiếm là gì", "880", "0", "informational", "phamlocblog.com", "3", "/b"],
    ])
    candidates = _write_tsv(
        tmp_path / "candidates.tsv",
        ["keyword", "axis", "unit", "family", "category", "archetype"],
        [["biến hiếm là gì", "statistical-term", "bien-hiem", "misc", "thong-ke",
          "term-la-gi"]])
    _write_tsv(tmp_path / "gate-statistical-term.tsv",
               ["keyword", "search_volume", "verdict", "reason"],
               [["biến hiếm là gì", "", "pass",
                 "unmeasured; family 'misc' sample 4/5 pass, aggregate 9,300"]])

    out = tmp_path / "backlog.tsv"
    summary = plan.run(harvest_path=harvest, candidates_path=candidates,
                       gate_dir=str(tmp_path), exclusions_path=os.devnull,
                       out_path=str(out), index_path=None)
    rows = list(csv.DictReader(open(out, encoding="utf-8"), delimiter="\t"))
    assert len(rows) == 1
    assert rows[0]["gate_status"] == "measured"
    assert rows[0]["search_volume"] == "880"
    assert summary["family_inferred"] == 0


# ------------------------------------------------------- the vocabulary gate


# Real rows from harvest-2026-09-07.tsv that must never become pages. The newest
# competitor (trithuccongdong.net) is a thesis-writing service with a general
# homework Q&A section, so it ranks for school algebra, English essay templates
# and the CFA charter exam. A blacklist cannot keep up with that; the whitelist
# is what stops them.
OFF_TOPIC_HARVEST_ROWS = [
    ("cách làm tài liệu", 368000),
    ("quản lý giáo dục", 40500),
    ("hàm số nào sau đây đồng biến trên r", 27100),
    ("phương trình", 27100),
    ("luận", 22200),
    ("narrative essay mẫu", 22200),
    ("acknowledgement là gì", 18100),
    ("tích", 18100),
    ("đề thi cfa", 12100),
    ("sự cháy", 12100),
    ("quản lý mầm non", 9900),
    ("straight", 5400),
    ("outline essay mẫu", 4400),
    ("outline là gì", 3600),
    ("outlined là gì", 3600),
]

ON_TOPIC_HARVEST_ROWS = [
    ("cronbach alpha", 1300),
    ("ma trận xoay", 6600),
    ("cỡ mẫu là gì", 4400),
    ("thang đo likert", 1600),
    ("pls-sem", 720),
    ("cách ghi tài liệu tham khảo", 14800),
    ("tháp nhu cầu maslow", 14800),
    ("thạc sĩ", 6600),
    ("phiếu khảo sát online", 14800),
    ("dữ liệu sơ cấp", 720),
]


def _read_committed_filters(tmp_path, rows):
    """Run the committed exclusions, vocabulary and axes over `rows`."""
    harvest = _write_tsv(tmp_path / "harvest.tsv", HARVEST_HEADER,
                         [[kw, vol, "0", "informational", "trithuccongdong.net", "1", "/x"]
                          for kw, vol in rows])
    return plan.read_harvest(harvest, plan.load_exclusions())


def test_the_committed_vocabulary_cuts_the_off_topic_harvest_rows(tmp_path):
    kept, dropped = _read_committed_filters(tmp_path, OFF_TOPIC_HARVEST_ROWS)
    assert [p.keyword for p in kept] == [], "no off-topic row may reach the backlog"
    assert {k for k, _, _ in dropped} == {k for k, _ in OFF_TOPIC_HARVEST_ROWS}
    reasons = {k: r for k, _, r in dropped}
    # `cfa` is in the vocabulary (confirmatory factor analysis) so the finance
    # exam has to be caught by the blacklist, not by the whitelist.
    assert reasons["đề thi cfa"].startswith("exclusion:")
    # `s-tra-ight` used to inherit the TRA model's family from a substring match.
    assert reasons["straight"] == "off-vocabulary"
    assert reasons["hàm số nào sau đây đồng biến trên r"] == "off-vocabulary"


def test_the_committed_vocabulary_keeps_the_real_queries(tmp_path):
    kept, dropped = _read_committed_filters(tmp_path, ON_TOPIC_HARVEST_ROWS)
    assert {p.keyword for p in kept} == {k for k, _ in ON_TOPIC_HARVEST_ROWS}, \
        f"whitelist over-rejected: {[k for k, _, _ in dropped]}"


def test_a_vocabulary_entry_matches_a_whole_word_not_a_substring():
    matcher = plan.compile_terms(["ave", "tra", "sem", "t-test"])
    assert plan.matches_vocabulary("ave là gì", matcher)
    assert plan.matches_vocabulary("mô hình tra", matcher)
    assert plan.matches_vocabulary("kiểm định t-test spss", matcher)
    assert not plan.matches_vocabulary("average là gì", matcher)
    assert not plan.matches_vocabulary("straight", matcher)
    assert not plan.matches_vocabulary("assembly", matcher)


def test_a_candidate_keyword_is_never_rejected_by_the_vocabulary(tmp_path):
    """`expand` produced it from an axis, so it is on topic by construction."""
    harvest = _write_tsv(tmp_path / "harvest.tsv", HARVEST_HEADER,
                         [["biến hiếm là gì", "880", "0", "x", "phamlocblog.com", "1", "/b"]])
    kept, dropped = plan.read_harvest(harvest, [], allow={"biến hiếm là gì"})
    assert [p.keyword for p in kept] == ["biến hiếm là gì"]
    assert dropped == []


def test_run_writes_every_dropped_row_with_its_reason(tmp_path):
    harvest = _write_tsv(tmp_path / "harvest.tsv", HARVEST_HEADER, [
        ["cronbach alpha", "1300", "0", "informational", "phantichspss.com", "4", "/c"],
        ["tải spss", "1900", "0", "transactional", "phamlocblog.com", "2", "/t"],
        ["sự cháy", "12100", "0", "informational", "trithuccongdong.net", "1", "/s"],
        ["mẫu chưa đo", "0", "0", "informational", "trithuccongdong.net", "9", "/m"],
    ])
    candidates = _write_tsv(tmp_path / "candidates.tsv",
                            ["keyword", "axis", "unit", "family", "category", "archetype"], [])
    exclusions = tmp_path / "exclusions.txt"
    exclusions.write_text("\\btải\\b\n", encoding="utf-8")
    vocabulary = tmp_path / "vocabulary.txt"
    vocabulary.write_text("# only one term\ncronbach\n", encoding="utf-8")

    out = tmp_path / "backlog.tsv"
    summary = plan.run(harvest_path=harvest, candidates_path=candidates,
                       gate_dir=str(tmp_path), exclusions_path=str(exclusions),
                       vocabulary_path=str(vocabulary), out_path=str(out), index_path=None)

    rejected = tmp_path / "plan-rejected.tsv"
    assert rejected.is_file(), "the rejects land beside the backlog they explain"
    with open(rejected, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    assert list(rows[0]) == list(plan.REJECTED_COLUMNS)
    by_keyword = {r["keyword"]: r for r in rows}
    assert by_keyword["sự cháy"]["reason"] == "off-vocabulary"
    assert by_keyword["sự cháy"]["volume"] == "12100"
    assert by_keyword["tải spss"]["reason"].startswith("exclusion:")
    assert by_keyword["mẫu chưa đo"]["reason"] == "no measured volume"
    assert [r["keyword"] for r in rows] == ["sự cháy", "tải spss", "mẫu chưa đo"], \
        "biggest first, so a human skims the expensive mistakes"
    assert summary["off_vocabulary"] == 1
    assert summary["blacklisted"] == 1


# ----------------------------------------------- category and archetype rules


# Ten real harvest keywords, one per category plus the two shapes that override
# the category default. `plan` used to put `outline essay mẫu` in `smartpls` and
# `cách làm tài liệu` in `thong-ke`.
REPRESENTATIVE_ROWS = [
    ("độ lệch chuẩn", "thong-ke", "term-la-gi"),
    ("ma trận xoay", "spss", "spss-howto"),
    ("pls-sem", "smartpls", "term-la-gi"),
    ("phiếu khảo sát online", "khao-sat", "survey"),
    ("tháp nhu cầu maslow", "mo-hinh-nghien-cuu", "model-theory"),
    ("cách ghi tài liệu tham khảo", "khoa-luan-tot-nghiep", "thesis-writing"),
    ("đề tài nghiên cứu khoa học", "khoa-luan-tot-nghiep", "topic-list"),
    ("thạc sĩ", "luan-van-thac-si", "thesis-writing"),
    ("dữ liệu sơ cấp", "nghien-cuu-khoa-hoc", "term-la-gi"),
    ("xử lý dữ liệu", "phan-tich-du-lieu", "term-la-gi"),
]


@pytest.mark.parametrize(("keyword", "category", "archetype"), REPRESENTATIVE_ROWS)
def test_representative_harvest_keywords_land_in_the_right_category(keyword, category,
                                                                    archetype):
    assert plan.classify_category(keyword) == category
    assert plan.classify_archetype(keyword) == archetype


def test_the_category_head_terms_each_land_in_their_own_category():
    """Nine categories, nine measured head terms. `spss` used to fall to thong-ke."""
    heads = {
        "spss": "spss",
        "thống kê": "thong-ke",
        "khảo sát": "khao-sat",
        "nghiên cứu khoa học": "nghien-cuu-khoa-hoc",
        "khóa luận tốt nghiệp": "khoa-luan-tot-nghiep",
        "smartpls": "smartpls",
        "phân tích dữ liệu": "phan-tich-du-lieu",
        "luận văn thạc sĩ": "luan-van-thac-si",
        "mô hình nghiên cứu": "mo-hinh-nghien-cuu",
    }
    for keyword, category in heads.items():
        assert plan.classify_category(keyword) == category, keyword


def test_the_first_matching_rule_wins():
    """Order is the editorial decision, so it is worth pinning."""
    # the degree beats the generic thesis word
    assert plan.classify_category("luận văn thạc sĩ ngành marketing") == "luan-van-thac-si"
    # the tool the searcher named beats the concept
    assert plan.classify_category("cách chạy efa trong spss") == "spss"
    assert plan.classify_category("bootstrapping trong smartpls 4") == "smartpls"
    # a survey word beats the model word that follows it in the rules
    assert plan.classify_category("thang đo likert 5 mức độ") == "khao-sat"


def test_the_page_shape_overrides_the_category_default():
    assert plan.classify_archetype("htmt vượt ngưỡng phải làm sao") == "troubleshoot"
    assert plan.classify_archetype("lỗi ma trận xoay trong spss") == "troubleshoot"
    assert plan.classify_archetype("đề tài luận văn thạc sĩ quản trị") == "topic-list"
    # and a caller that already knows the category is not made to re-derive it
    assert plan.classify_archetype("ave là gì", "smartpls") == "term-la-gi"
    assert plan.classify_archetype("cách chạy ave", "smartpls") == "smartpls-howto"


def test_an_axis_display_must_be_named_not_spelled_inside_another_word():
    lookup = [("tra", "behavior", "mo-hinh-nghien-cuu", "model-theory")]
    assert plan._classify_from_axes("mô hình tra", lookup) is not None
    assert plan._classify_from_axes("straight", lookup) is None
