"""A sentence written once and pasted into eighty posts.

`variants` hands a group of interchangeable phrasings out positionally. These
cover the three properties that make that safe: it levels the group rather than
moving the concentration, it leaves quoted structure alone, and running it twice
changes nothing the first run did not.
"""
import json

from app.blog.content import variants


POOLS = {
    "vi": [
        {"members": ["A rất hiếm.", "A hiếm khi xảy ra.", "A ít khi xảy ra."]},
        {"members": ["Trong `Descriptives`, chọn `KMO`.",
                     "Ở `Descriptives`, tick `KMO`."]},
    ],
    "en": [{"members": ["one", "two"]}],
}


def _pools(tmp_path):
    path = tmp_path / "pools.json"
    path.write_text(json.dumps(POOLS, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _bank(tmp_path, bodies):
    d = tmp_path / "posts"
    d.mkdir(exist_ok=True)
    for index, body in enumerate(bodies):
        post = {"schema": "dothesis-blog-seed/1", "slug": f"p{index}",
                "locale": "vi", "title": f"p{index}", "body": body}
        (d / f"{index:04d}-p{index}.json").write_text(
            json.dumps(post, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(d)


def _bodies(seed_dir):
    import os
    return [json.load(open(os.path.join(seed_dir, n), encoding="utf-8"))["body"]
            for n in sorted(os.listdir(seed_dir))]


def test_one_phrasing_in_every_post_becomes_three_used_evenly(tmp_path):
    seed_dir = _bank(tmp_path, ["A rất hiếm. Còn lại giữ nguyên."] * 6)

    stats = variants.run(seed_dir, "vi", _pools(tmp_path))

    used = [body.split(".")[0] + "." for body in _bodies(seed_dir)]
    assert sorted(set(used)) == sorted(POOLS["vi"][0]["members"])
    assert all(used.count(m) == 2 for m in POOLS["vi"][0]["members"])
    assert stats.touched == 4 and stats.unchanged == 2


def test_phrasings_the_bank_already_had_are_members_not_competition(tmp_path):
    # Four posts on one phrasing and two on another is the real shape: rotating
    # over the union levels them, rotating one into the other would not.
    seed_dir = _bank(tmp_path, ["A rất hiếm."] * 4 + ["A hiếm khi xảy ra."] * 2)

    variants.run(seed_dir, "vi", _pools(tmp_path))

    used = _bodies(seed_dir)
    assert all(used.count(m) == 2 for m in POOLS["vi"][0]["members"])


def test_a_second_run_changes_nothing(tmp_path):
    seed_dir = _bank(tmp_path, ["A rất hiếm."] * 5)
    variants.run(seed_dir, "vi", _pools(tmp_path))
    after_first = _bodies(seed_dir)

    stats = variants.run(seed_dir, "vi", _pools(tmp_path))

    assert _bodies(seed_dir) == after_first
    assert stats.replacements == 0 and stats.touched == 0


def test_an_occurrence_wrapped_in_code_marks_is_replaced_whole(tmp_path):
    # The bank writes software names in backticks in most posts and bare in a
    # few. Both are the same sentence, and neither may leave a stray mark behind.
    seed_dir = _bank(tmp_path, ["Trong Descriptives, chọn KMO."] * 2)

    variants.run(seed_dir, "vi", _pools(tmp_path))

    assert _bodies(seed_dir) == POOLS["vi"][1]["members"]


def test_headings_tables_and_code_blocks_are_left_alone(tmp_path):
    quoted = "## A rất hiếm.\n| A rất hiếm. |\n```\nA rất hiếm.\n```\n> A rất hiếm."
    seed_dir = _bank(tmp_path, [quoted])

    stats = variants.run(seed_dir, "vi", _pools(tmp_path))

    assert _bodies(seed_dir) == [quoted]
    assert stats.replacements == 0


def test_two_occurrences_in_one_post_do_not_become_the_same_sentence(tmp_path):
    seed_dir = _bank(tmp_path, ["A rất hiếm.\n\nA rất hiếm."])

    variants.run(seed_dir, "vi", _pools(tmp_path))

    first, second = _bodies(seed_dir)[0].split("\n\n")
    assert first != second


def test_a_dry_run_reports_without_writing(tmp_path):
    seed_dir = _bank(tmp_path, ["A rất hiếm."] * 3)

    stats = variants.run(seed_dir, "vi", _pools(tmp_path), dry_run=True)

    assert stats.touched == 2
    assert _bodies(seed_dir) == ["A rất hiếm."] * 3
