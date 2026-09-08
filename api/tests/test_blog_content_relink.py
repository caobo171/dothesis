"""A link can go stale without anyone inventing it.

`plan` re-clusters on every run, so a slug that resolved when a post was
written can be folded away later. These cover the maintenance pass that finds
those and unlinks them.
"""
import json
import os

from app.blog.content import relink


def _seed(tmp_path, slug, body, **extra):
    d = tmp_path / "posts"
    d.mkdir(exist_ok=True)
    post = {"schema": "dothesis-blog-seed/1", "slug": slug, "locale": "vi",
            "title": slug, "meta_title": slug, "meta_description": "x" * 130,
            "excerpt": "x", "category": "spss", "archetype": "term-la-gi",
            "body": body}
    post.update(extra)
    (d / f"0001-{slug}.json").write_text(json.dumps(post, ensure_ascii=False),
                                        encoding="utf-8")
    return str(d)


LIVE_LINKS = ("[a](/blog/vi/alive) [b](/blog/vi/alive-2) "
              "[c](/blog/vi/alive-3) [d](/blog/vi/alive-4)")


def _bank(tmp_path, body):
    seed_dir = _seed(tmp_path, "subject", body)
    for other in ("alive", "alive-2", "alive-3", "alive-4"):
        _seed(tmp_path, other, "filler")
    return seed_dir


def test_a_dead_link_is_unlinked_and_its_text_kept(tmp_path):
    seed_dir = _bank(tmp_path, f"{LIVE_LINKS} và [lý thuyết VAR](/blog/vi/ly-thuyet-var).")
    stats = relink.run(seed_dir)

    assert stats.removed == 1 and stats.changed == 1 and stats.thin == []
    body = json.loads((tmp_path / "posts" / "0001-subject.json").read_text(encoding="utf-8"))["body"]
    assert "/blog/vi/ly-thuyet-var" not in body
    assert "lý thuyết VAR" in body, "the sentence keeps its words"
    assert "/blog/vi/alive-4" in body, "a live link is left alone"


def test_a_dry_run_reports_without_writing(tmp_path):
    body = f"{LIVE_LINKS} và [x](/blog/vi/gone)."
    seed_dir = _bank(tmp_path, body)
    stats = relink.run(seed_dir, dry_run=True)

    assert stats.removed == 1
    assert stats.dead == {"/blog/vi/gone": 1}
    on_disk = json.loads((tmp_path / "posts" / "0001-subject.json").read_text(encoding="utf-8"))
    assert on_disk["body"] == body


def test_a_post_pushed_under_the_floor_is_named_not_silently_shipped(tmp_path):
    seed_dir = _bank(tmp_path, "[a](/blog/vi/alive) [x](/blog/vi/gone) [y](/blog/vi/gone-2).")
    stats = relink.run(seed_dir)

    assert stats.thin == ["subject"], "a post this thin needs a writer, not a script"


def test_a_clean_bank_changes_nothing(tmp_path):
    seed_dir = _bank(tmp_path, LIVE_LINKS)
    stats = relink.run(seed_dir)
    assert stats.changed == 0 and stats.removed == 0 and stats.dead == {}


def test_the_cli_exposes_it(tmp_path, capsys):
    from app.blog.content import cli

    seed_dir = _bank(tmp_path, f"{LIVE_LINKS} [x](/blog/vi/gone).")
    assert cli.main(["relink", "--dir", seed_dir]) == 0
    assert "unlinked 1 dead link" in capsys.readouterr().out
