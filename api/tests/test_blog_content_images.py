"""The shared illustration library: resolution, assignment, conversion, cost.

Every test stubs the generator. Nothing here touches an image API — the whole
point of the library is that a scene is paid for once, and a test suite that
bills per run would be the exact opposite of the feature.
"""
import io
import json
import os

import pytest

from app.blog import content
from app.blog.content import cli, images

# The content engine talks to no database. Override the session-wide autouse
# fixture from conftest.py so these tests do not pay for a Postgres container.
@pytest.fixture(autouse=True)
def _bind_db():
    yield


def _png(width=1600, height=1066) -> bytes:
    """A real PNG from Pillow, so `to_webp` has something to decode."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (40, 46, 255)).save(buf, format="PNG")
    return buf.getvalue()


class Recorder:
    """A generator stub that counts calls and never leaves the process."""

    def __init__(self, payload=None):
        self.prompts = []
        self.payload = payload or _png()

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.payload

    @property
    def calls(self):
        return len(self.prompts)


def _library(tmp_path, entries):
    path = tmp_path / "blog-image-library.json"
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _seed(directory, name, **overrides):
    directory.mkdir(parents=True, exist_ok=True)
    seed = {"schema": "dothesis-blog-seed/1", "slug": name.split("-", 1)[1].removesuffix(".json"),
            "locale": "vi", "category": "spss", "archetype": "term-la-gi", "images": []}
    seed.update(overrides)
    (directory / name).write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    return directory / name


# --------------------------------------------------------------------------
# resolve
# --------------------------------------------------------------------------


def test_a_key_that_already_has_a_url_is_reused_and_never_regenerated(tmp_path):
    lib = _library(tmp_path, {"spss": {"prompt": "p", "url": "/img/blog/spss.webp"}})
    gen = Recorder()
    stats = images.Stats()

    url = images.resolve("spss", lib_path=lib, out_dir=tmp_path / "out",
                         generator=gen, stats=stats)

    assert url == "/img/blog/spss.webp"
    assert gen.calls == 0
    assert stats.reused == ["spss"] and stats.generated == []


def test_an_empty_key_is_generated_once_and_written_back(tmp_path):
    lib = _library(tmp_path, {"spss": {"prompt": "a calm desk"}})
    out = tmp_path / "out"
    gen = Recorder()
    stats = images.Stats()

    url = images.resolve("spss", lib_path=lib, out_dir=out, generator=gen, stats=stats)

    assert url == "/img/blog/spss.webp"
    assert gen.prompts == ["a calm desk"]
    assert (out / "spss.webp").is_file()
    # Written back, with the prompt intact: the next run must reuse, not repay.
    written = json.loads(lib.read_text(encoding="utf-8"))
    assert written["spss"] == {"prompt": "a calm desk", "url": "/img/blog/spss.webp"}
    assert stats.generated == ["spss"] and stats.bytes_written > 0


def test_two_seeds_wanting_the_same_empty_key_in_one_run_generate_it_once(tmp_path):
    lib = _library(tmp_path, {"term-la-gi-1": {"prompt": "a desk"}})
    gen = Recorder()
    stats = images.Stats()

    first = images.resolve("term-la-gi-1", lib_path=lib, out_dir=tmp_path / "out",
                           generator=gen, stats=stats)
    second = images.resolve("term-la-gi-1", lib_path=lib, out_dir=tmp_path / "out",
                            generator=gen, stats=stats)

    assert first == second == "/img/blog/term-la-gi-1.webp"
    assert gen.calls == 1
    assert stats.generated == ["term-la-gi-1"] and stats.reused == ["term-la-gi-1"]


def test_force_regenerates_a_key_that_already_has_an_image(tmp_path):
    lib = _library(tmp_path, {"spss": {"prompt": "p", "url": "/img/blog/spss.webp"}})
    gen = Recorder()
    stats = images.Stats()

    images.resolve("spss", lib_path=lib, out_dir=tmp_path / "out", generator=gen,
                   force=True, stats=stats)

    assert gen.calls == 1
    assert (tmp_path / "out" / "spss.webp").is_file()
    assert stats.generated == ["spss"]


def test_force_still_bills_a_repeated_key_only_once_in_the_same_run(tmp_path):
    lib = _library(tmp_path, {"spss": {"prompt": "p", "url": "/img/blog/spss.webp"}})
    gen = Recorder()
    stats = images.Stats()

    for _ in range(3):
        images.resolve("spss", lib_path=lib, out_dir=tmp_path / "out", generator=gen,
                       force=True, stats=stats)

    assert gen.calls == 1


def test_a_missing_key_is_reported_rather_than_crashing(tmp_path, capsys):
    lib = _library(tmp_path, {"spss": {"prompt": "p"}})
    gen = Recorder()
    stats = images.Stats()

    url = images.resolve("khong-co-key", lib_path=lib, out_dir=tmp_path / "out",
                         generator=gen, stats=stats)

    assert url is None
    assert gen.calls == 0
    assert stats.missing == ["khong-co-key"]
    assert "khong-co-key" in capsys.readouterr().out


# --------------------------------------------------------------------------
# WebP conversion
# --------------------------------------------------------------------------


def test_webp_conversion_caps_the_width_and_shrinks_the_file(tmp_path):
    from PIL import Image

    raw = _png(1600, 1066)
    data, width, height = images.to_webp(raw)

    assert width == images.MAX_WIDTH
    assert height == round(1066 * images.MAX_WIDTH / 1600)
    assert len(data) < len(raw)
    path = tmp_path / "x.webp"
    path.write_bytes(data)
    with Image.open(path) as reopened:
        assert reopened.format == "WEBP"
        assert reopened.width <= images.MAX_WIDTH


def test_a_small_image_is_not_upscaled():
    _, width, _ = images.to_webp(_png(600, 400))
    assert width == 600


def test_undecodable_bytes_raise_image_error_rather_than_writing_a_broken_file():
    with pytest.raises(images.ImageError):
        images.to_webp(b"this is not a picture")


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------


VARIANT_LIBRARY = {
    "spss": {"prompt": "category"},
    "term-la-gi-1": {"prompt": "1"},
    "term-la-gi-2": {"prompt": "2"},
    "term-la-gi-3": {"prompt": "3"},
    "topic-list-1": {"prompt": "1"},
}


def test_assignment_gives_every_seed_a_hero_key_with_vietnamese_alt(tmp_path):
    lib = _library(tmp_path, VARIANT_LIBRARY)
    posts = tmp_path / "posts"
    for i, slug in enumerate(["cronbach-alpha", "efa", "hoi-quy"], start=1):
        _seed(posts, f"{i:04d}-{slug}.json", slug=slug)

    chosen = images.assign(posts, lib_path=lib)

    assert len(chosen) == 3
    for path in sorted(posts.glob("*.json")):
        seed = json.loads(path.read_text(encoding="utf-8"))
        hero = seed["images"][0]
        assert hero["id"] == "hero"
        assert hero["source"].startswith("library:term-la-gi-")
        # Real Vietnamese alt, not an empty string and not the title.
        assert hero["alt"] == images.ALT_VI[hero["source"].split(":", 1)[1]]
        # No url in the library yet, so no image_url is invented.
        assert "image_url" not in seed


def test_assignment_is_stable_across_runs(tmp_path):
    lib = _library(tmp_path, VARIANT_LIBRARY)
    posts = tmp_path / "posts"
    for i, slug in enumerate(["cronbach-alpha", "efa", "hoi-quy", "anova"], start=1):
        _seed(posts, f"{i:04d}-{slug}.json", slug=slug)

    first = images.assign(posts, lib_path=lib)
    second = images.assign(posts, lib_path=lib)

    assert first == second


def test_neighbouring_seeds_never_share_a_key(tmp_path):
    lib = _library(tmp_path, VARIANT_LIBRARY)
    posts = tmp_path / "posts"
    slugs = ["a-mot", "b-hai", "c-ba", "d-bon", "e-nam", "f-sau", "g-bay", "h-tam"]
    for i, slug in enumerate(slugs, start=1):
        _seed(posts, f"{i:04d}-{slug}.json", slug=slug)

    chosen = images.assign(posts, lib_path=lib)
    keys = [chosen[p] for p in sorted(chosen)]

    assert len(keys) == len(slugs)
    assert all(a != b for a, b in zip(keys, keys[1:])), keys


def test_an_archetype_with_no_variants_falls_back_to_the_category_key(tmp_path):
    lib = _library(tmp_path, VARIANT_LIBRARY)
    posts = tmp_path / "posts"
    _seed(posts, "0001-spss.json", slug="spss", archetype="spss-howto", category="spss")

    chosen = images.assign(posts, lib_path=lib)

    assert list(chosen.values()) == ["spss"]


def test_assignment_copies_an_existing_url_onto_the_seed(tmp_path):
    lib = _library(tmp_path, {**VARIANT_LIBRARY,
                              "term-la-gi-1": {"prompt": "1", "url": "/img/blog/term-la-gi-1.webp"},
                              "term-la-gi-2": {"prompt": "2", "url": "/img/blog/term-la-gi-2.webp"},
                              "term-la-gi-3": {"prompt": "3", "url": "/img/blog/term-la-gi-3.webp"}})
    posts = tmp_path / "posts"
    _seed(posts, "0001-cronbach-alpha.json", slug="cronbach-alpha")

    images.assign(posts, lib_path=lib)

    seed = json.loads((posts / "0001-cronbach-alpha.json").read_text(encoding="utf-8"))
    # Root-relative on purpose: an absolute origin in the database bakes in the
    # environment. The web layer runs it through absoluteUrl() where it needs one.
    assert seed["image_url"].startswith("/img/blog/")


def test_a_seed_whose_key_is_absent_is_reported_and_left_alone(tmp_path, capsys):
    lib = _library(tmp_path, {"term-la-gi-1": {"prompt": "1"}})
    posts = tmp_path / "posts"
    _seed(posts, "0001-de-tai.json", slug="de-tai", archetype="khong-biet",
          category="khong-biet")

    stats = images.Stats()
    chosen = images.assign(posts, lib_path=lib, stats=stats)

    assert chosen == {}
    assert stats.missing == ["de-tai"]
    assert "de-tai" in capsys.readouterr().out
    assert json.loads((posts / "0001-de-tai.json").read_text(encoding="utf-8"))["images"] == []


# --------------------------------------------------------------------------
# The run, end to end
# --------------------------------------------------------------------------


def test_run_assigns_generates_once_per_key_and_writes_the_url_back(tmp_path, capsys):
    lib = _library(tmp_path, VARIANT_LIBRARY)
    posts = tmp_path / "posts"
    for i, slug in enumerate(["cronbach-alpha", "efa", "hoi-quy"], start=1):
        _seed(posts, f"{i:04d}-{slug}.json", slug=slug)
    gen = Recorder()

    stats = images.run(seed_dir=posts, do_assign=True, do_generate=True,
                       lib_path=lib, out_dir=tmp_path / "out", generator=gen)

    # Three posts, at most three distinct scenes, one generation each.
    assert gen.calls == len(set(stats.generated))
    assert stats.missing == []
    for path in sorted(posts.glob("*.json")):
        seed = json.loads(path.read_text(encoding="utf-8"))
        assert seed["image_url"] == f"/img/blog/{seed['images'][0]['source'].split(':')[1]}.webp"

    out = capsys.readouterr().out
    # The cost comparison is the whole argument for a library, so it is printed.
    assert "whole library" in out and "per-post would" in out


def test_dry_run_writes_nothing(tmp_path, capsys):
    lib = _library(tmp_path, VARIANT_LIBRARY)
    before = lib.read_text(encoding="utf-8")
    posts = tmp_path / "posts"
    seed_path = _seed(posts, "0001-cronbach-alpha.json", slug="cronbach-alpha")
    seed_before = seed_path.read_text(encoding="utf-8")
    gen = Recorder()

    stats = images.run(seed_dir=posts, do_assign=True, do_generate=True, dry_run=True,
                       lib_path=lib, out_dir=tmp_path / "out", generator=gen)

    assert gen.calls == 0
    assert stats.generated == [] and stats.would_generate
    assert lib.read_text(encoding="utf-8") == before
    assert seed_path.read_text(encoding="utf-8") == seed_before
    assert not (tmp_path / "out").exists()
    assert "would generate" in capsys.readouterr().out


def test_generate_without_assign_uses_the_keys_the_seeds_already_carry(tmp_path):
    lib = _library(tmp_path, VARIANT_LIBRARY)
    posts = tmp_path / "posts"
    _seed(posts, "0001-cronbach-alpha.json", slug="cronbach-alpha",
          images=[{"id": "hero", "source": "library:term-la-gi-2", "alt": "x"}])
    gen = Recorder()

    stats = images.run(seed_dir=posts, do_generate=True, lib_path=lib,
                       out_dir=tmp_path / "out", generator=gen)

    assert stats.generated == ["term-la-gi-2"]
    assert gen.calls == 1


def test_the_cli_dry_run_reaches_the_library_and_calls_nothing(tmp_path, capsys):
    """`--dry-run` through the real argument parser, with no stub in sight."""
    posts = tmp_path / "posts"
    _seed(posts, "0001-cronbach-alpha.json", slug="cronbach-alpha")

    code = cli.main(["images", "--dir", str(posts), "--assign", "--generate", "--dry-run"])

    assert code == 0
    out = capsys.readouterr().out
    assert "would generate" in out
    assert json.loads((posts / "0001-cronbach-alpha.json").read_text(
        encoding="utf-8"))["images"] == []


# --------------------------------------------------------------------------
# The committed library itself
# --------------------------------------------------------------------------


def test_the_committed_library_covers_every_category_and_archetype():
    library = images.load_library()
    with open(os.path.join(content.repo_root(), "docs", "seo", "categories.json"),
              encoding="utf-8") as fh:
        categories = json.load(fh)

    for category in categories:
        assert category["slug"] in library, category["slug"]
    for archetype in ("term-la-gi", "spss-howto", "smartpls-howto", "test",
                      "model-theory", "scale", "thesis-writing", "survey",
                      "topic-list", "troubleshoot"):
        assert len(images.variants_for(archetype, library)) == 3, archetype


def test_every_prompt_forbids_generated_type():
    """Wrong Vietnamese in a picture is worse than no picture."""
    for key, entry in images.load_library().items():
        prompt = entry["prompt"].lower()
        for clause in ("no text", "no letters", "no numbers", "no charts with labels",
                       "no ui", "no logos"):
            assert clause in prompt, f"{key} is missing {clause!r}"


def test_every_library_key_has_vietnamese_alt_text():
    for key in images.load_library():
        assert images.ALT_VI.get(key), key
