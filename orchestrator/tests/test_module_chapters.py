"""Per-module chapter ownership + composition.

The pivot: instead of M5 composing the whole thesis, each module owns and
composes its own chapter(s) as it completes, so the docx grows continuously.
No LLM — compose_all_sections is stubbed at its seam.
"""
import orchestrator.tools.m5_writing as M


def test_module_chapters_partition_the_canonical_order_exactly():
    # Every canonical chapter is owned by exactly one module, and no module
    # claims a chapter that isn't in the canonical order.
    owned = [c for names in M.MODULE_CHAPTERS.values() for c in names]
    assert sorted(owned) == sorted(M.M5_CHAPTER_ORDER)
    assert len(owned) == len(set(owned)), "a chapter is owned by two modules"


def test_m5_owns_discussion_and_conclusion():
    assert M.MODULE_CHAPTERS["M5"] == ["discussion", "conclusion"]
    assert M.chapters_for_module("M1") == ["intro"]
    assert M.chapters_for_module("m4") == ["results"]  # case-insensitive
    assert M.chapters_for_module("nope") == []


def test_module_for_chapter_reverse_lookup():
    assert M.module_for_chapter("intro") == "M1"
    assert M.module_for_chapter("discussion") == "M5"
    assert M.module_for_chapter("conclusion") == "M5"
    assert M.module_for_chapter("unknown") is None


def test_compose_module_chapters_shapes_and_filters(monkeypatch):
    # Stub composition: M5 owns [discussion, conclusion]; compose_all_sections
    # returns those two plus a References section that must be filtered out.
    def fake_compose(cs, chapters=None):
        assert chapters == ["discussion", "conclusion"]
        return [
            {"chapter_name": "discussion", "title": "Ch5", "prose": "Discussion prose."},
            {"chapter_name": "conclusion", "title": "Ch6", "prose": "Conclusion prose."},
            {"title": "References", "prose": "[1] Smith 2024"},  # no chapter_name
        ]
    monkeypatch.setattr(M, "compose_all_sections", fake_compose)

    out = M.compose_module_chapters({"m1_topic": {}}, "M5")
    assert set(out) == {"discussion", "conclusion"}
    assert out["discussion"] == {"name": "discussion", "prose": "Discussion prose."}
    assert "References" not in out


def test_compose_module_chapters_skips_empty_prose(monkeypatch):
    monkeypatch.setattr(M, "compose_all_sections",
                        lambda cs, chapters=None: [{"chapter_name": "intro", "prose": "   "}])
    assert M.compose_module_chapters({}, "M1") == {}


def test_compose_module_chapters_fail_open(monkeypatch):
    def boom(cs, chapters=None):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(M, "compose_all_sections", boom)
    assert M.compose_module_chapters({}, "M2") == {}
    assert M.compose_module_chapters({}, "unknown_module") == {}
