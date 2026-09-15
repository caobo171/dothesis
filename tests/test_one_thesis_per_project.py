"""One project has ONE thesis — whichever flow renders or scores it.

The thesis prose has two storage homes in `m5_writing`:

- `chapters: {intro: {prose}, …}` — what the editor SAVES, and what each module
  composes into as it completes (the continuous-writing pivot).
- `final_sections: [{title, prose}, …]` — the snapshot the conversational
  export leaves behind.

`chapters` is not in `SLICE_OWNERSHIP["M5"]`, so the agent's flat contextStore
cannot carry it and the agent half of the system writes `final_sections`
instead. Two writers, two keys, nothing syncing them: on the live database 11
of the 15 projects that have any prose carry BOTH shapes, and in every one of
them EVERY chapter differs between the two copies (intro 22040b vs 21258b,
lit_review 58430b vs 49698b on the project this was traced from).

That would be survivable if one rule decided which copy is the thesis. Instead
seven readers each rolled their own, with three different answers — so the
document you got depended on which button you pressed, and the quality score
was computed on a third version nobody downloaded.

These tests pin the invariant: every reader resolves the same prose, and
`chapters` wins because it is the copy the student's own edits land in.
"""
import pytest

from orchestrator.tools.m5_writing import chapter_prose, sections_from_m5_slice


# The editor's copy (canonical) and the conversational snapshot (stale), with
# deliberately different prose for the same chapters — exactly the shape the
# live rows are in. Long enough to clear the _is_stub_prose 120-char floor.
def _pad(tag: str) -> str:
    return (f"{tag}. " + "Nội dung chương được viết đầy đủ để vượt ngưỡng stub. " * 6).strip()


EDITED = {name: _pad(f"EDITED-{name}") for name in
          ("intro", "lit_review", "methodology", "results", "conclusion")}
STALE = {name: _pad(f"STALE-{name}") for name in
         ("intro", "lit_review", "methodology", "results")}


def _slice() -> dict:
    """An m5_writing slice carrying both shapes, as the live rows do."""
    return {
        "chapters": {name: {"name": name, "prose": prose}
                     for name, prose in EDITED.items()},
        "final_sections": (
            [{"chapter_name": name, "prose": prose} for name, prose in STALE.items()]
            + [{"title": "Tài liệu tham khảo", "prose": "Nguyen, A. (2020)."}]
        ),
    }


def _flat() -> dict:
    """The FLAT contextStore the agent sees. `chapters` is absent because it is
    not an M5-owned key — this is the projection, not an oversight in the test.
    """
    return {"final_sections": _slice()["final_sections"]}


# --- the resolver itself ----------------------------------------------------

def test_the_editors_copy_is_the_thesis():
    """`chapters` wins per chapter: it is where the student's edits land."""
    resolved = chapter_prose(_slice())
    for name, prose in EDITED.items():
        assert resolved[name] == prose, f"{name} resolved to the stale copy"


def test_a_chapter_only_the_snapshot_has_is_not_lost():
    """Gap-FILL, not winner-takes-all: one live project's prose is in
    `final_sections` only, and dropping it would blank the thesis."""
    m5 = _slice()
    del m5["chapters"]["conclusion"]
    m5["final_sections"].append(
        {"chapter_name": "conclusion", "prose": _pad("STALE-conclusion")})
    resolved = chapter_prose(m5)
    assert resolved["intro"] == EDITED["intro"]
    assert resolved["conclusion"] == _pad("STALE-conclusion")


def test_the_two_copies_are_never_concatenated():
    """Both homes hold a near-duplicate draft of the same chapter. Folding both
    in would print the chapter twice — a visible defect, not "losing nothing".
    (merge_chapter_prose still concatenates WITHIN one shape: that is the
    legacy discussion+conclusion rule, and it stays.)"""
    resolved = chapter_prose(_slice())
    assert "STALE-intro" not in resolved["intro"]
    assert resolved["intro"].count("EDITED-intro") == 1


def test_resolver_tolerates_plain_string_chapter_values():
    """Auto-mode has written `chapters: {intro: "prose"}` as well as
    `{intro: {prose: …}}`; coherence.py already tolerates both."""
    assert chapter_prose({"chapters": {"intro": _pad("BARE")}})["intro"] == _pad("BARE")


def test_resolver_is_empty_for_an_empty_slice():
    for empty in ({}, None, {"chapters": {}, "final_sections": []}):
        assert chapter_prose(empty) == {}


# --- every reader agrees ----------------------------------------------------

def _via_sections_from_m5_slice(m5):
    return {s["chapter_name"]: s["prose"]
            for s in sections_from_m5_slice(m5, language="vi")
            if s.get("chapter_name")}


def _via_artifacts(m5):
    from orchestrator.artifacts import _m5_chapter_prose
    return _m5_chapter_prose(m5)


def _via_rubric(m5):
    from quality.rubric import _all_prose
    return _all_prose({"m5_writing": m5})


def _via_similarity(m5):
    from quality.similarity import _resolve_chapters, _slices
    return _resolve_chapters(_slices({"m5_writing": m5})[0])


def _via_coherence(m5):
    from agent.coherence import _resolve_chapters, m5_prose
    return _resolve_chapters(m5_prose(m5))


def test_every_reader_renders_the_editors_intro():
    """The one invariant the whole bug reduces to. `_via_rubric` returns joined
    prose rather than a map, so it is checked by containment."""
    m5 = _slice()
    for reader in (_via_sections_from_m5_slice, _via_artifacts,
                   _via_similarity, _via_coherence):
        got = reader(m5)
        assert got.get("intro") == EDITED["intro"], (
            f"{reader.__name__} resolved intro to the stale copy")
    joined = _via_rubric(m5)
    assert "EDITED-intro" in joined and "STALE-intro" not in joined, (
        "the rubric scores a draft nobody downloaded")


def test_every_reader_agrees_on_every_chapter():
    m5 = _slice()
    baseline = _via_sections_from_m5_slice(m5)
    assert set(baseline) == set(EDITED), "the exporter lost a chapter"
    for reader in (_via_artifacts, _via_similarity, _via_coherence):
        got = reader(m5)
        for name in EDITED:
            assert (got.get(name) or "").strip() == baseline[name].strip(), (
                f"{reader.__name__} disagrees with the exporter on {name}")


# --- the store cannot be forgotten ------------------------------------------

def test_run_export_requires_the_context_store():
    """`context_store` defaulted to None and four of the seven callers quietly
    omitted it, so the same project exported with a cover, result tables and a
    model figure from one button and bare from another. It took three separate
    fixes to find them all, because a default makes an omission invisible.

    Keyword-only with NO default: a new caller cannot forget it, and passing
    None is a decision a reader can see.
    """
    import inspect

    from orchestrator.tools.m5_writing import run_export

    p = inspect.signature(run_export).parameters["context_store"]
    assert p.default is inspect.Parameter.empty, "a default is back — omitting it is invisible again"
    assert p.kind is inspect.Parameter.KEYWORD_ONLY, "must be keyword-only, not positional"

    with pytest.raises(TypeError):
        run_export([], "pid")


def test_every_run_export_caller_passes_the_store():
    """The signature only protects code that is compiled against it. This walks
    the actual call sites, because the bug was never a wrong value — it was an
    argument that was not there at all."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    skip = {".git", "node_modules", ".venv", "__pycache__", ".next", ".claude", "research", "tests"}
    missing = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if set(rel.parts) & skip or rel.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name != "run_export":
                continue
            if not any(kw.arg == "context_store" for kw in node.keywords):
                missing.append(f"{rel}:{node.lineno}")
    assert not missing, f"run_export called without context_store at: {missing}"


# Files allowed to touch the raw prose keys, and why. Everything else must go
# through `chapter_prose` / `sections_from_m5_slice`: reading a home directly is
# how seven readers ended up with three different answers about which copy of a
# chapter is the thesis.
_RAW_PROSE_ALLOWED = {
    # The resolver itself, and the renderer built on it.
    "orchestrator/tools/m5_writing.py": "owns the precedence rule",
    # WRITERS. Both homes are still written; that is the drift the resolver
    # absorbs on read. A writer has to name the key it writes.
    "api/app/routers/m5_editor.py": "editor CRUD + the heal-on-read backfill",
    "api/app/agent_state.py": "_auto_compose_module writes chapters",
    "agent/tools/state_tools.py": "commit-edge guard on the incoming writes payload",
    "agent/tools/backfill_tool.py": "writes final_sections",
    "api/app/import_work.py": "writes the student's preserved chapters",
    "quality/model_eval.py": "seeds a fixture slice",
    # DECLARATIONS that name the key rather than read prose through it.
    "agent/state.py": "SLICE_OWNERSHIP names the M5-owned key",
    "agent/roadmap.py": "names the artifact backing M5's writing step",
    "agent/artifact_routing.py": "WriteTarget routing table",
    # The documented flat->nested adapter: `chapters` is not an M5-owned key, so
    # the flat contextStore never carries it (that is the bug it exists to fix).
    "agent/tools/writing.py": "_m5_slice_for_export",
    # m5_prose's fail-open fallback when the resolver cannot be imported.
    "agent/coherence.py": "m5_prose fallback",
}

# `chapters` is an overloaded word: in a partner order it is the requested
# chapter LIST, and in the engine it is a word-count target. Those are not prose.
_NOT_PROSE_RECEIVERS = ("params", "meta", "body", "word_targets", "ctx")


def test_nothing_new_reads_the_prose_homes_directly():
    """A new reader that reaches for `final_sections` or an m5 `chapters` dict
    is how this bug class comes back. `final_sections` is unambiguous — it only
    ever means prose. `chapters` is filtered by receiver, because a partner
    order's chapter list shares the name."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    skip = {".git", "node_modules", ".venv", "__pycache__", ".next", ".claude",
            "research", "tests", "node_modules"}
    final = re.compile(r"""["']final_sections["']""")
    chapters = re.compile(r"""(\w+)\s*\.\s*get\(\s*["']chapters["']""")

    offenders = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if set(rel.parts) & skip or rel.name.startswith("test_"):
            continue
        if rel.as_posix() in _RAW_PROSE_ALLOWED:
            continue
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            code = line.split("#", 1)[0]
            if final.search(code):
                offenders.append(f"{rel}:{i} (final_sections)")
            m = chapters.search(code)
            if m and m.group(1) not in _NOT_PROSE_RECEIVERS:
                offenders.append(f"{rel}:{i} (chapters off {m.group(1)!r})")
    assert not offenders, (
        "read the thesis through m5_writing.chapter_prose (or "
        "sections_from_m5_slice) instead of a storage key — or add the file to "
        f"_RAW_PROSE_ALLOWED with a reason:\n  " + "\n  ".join(offenders))


# --- one module write-up composer -------------------------------------------

def test_the_module_write_up_has_one_composer(monkeypatch):
    """`/export/module` carried a second copy of `compose_module_prose`:
    identical guide map and skip keys, but a different prompt header, a
    different temperature and no leading-heading strip — so the same module for
    the same project read differently depending on whether the student asked
    chat for it or clicked Download. S3 vs a direct BytesIO is the only real
    difference, and that is delivery, not content."""
    import orchestrator.tools.m5_writing as M
    from app.routers.exports import _compose_module_prose

    seen: list[str] = []
    monkeypatch.setattr(M, "_get_llm", lambda: type("L", (), {
        "invoke": lambda self, prompt: seen.append(prompt) or type(
            "R", (), {"content": "## X\n\nBody."})(),
    })())

    M.compose_module_prose("M3", {"hypotheses": ["H1"]}, "T")
    _compose_module_prose("M3", M.MODULE_SECTION_LABELS["M3"], "T", {"hypotheses": ["H1"]})

    assert len(seen) == 2
    assert seen[0] == seen[1], "the two surfaces still build different prompts"


def test_the_module_label_is_not_internal_jargon():
    """M1's label was "Introduction" in chat and "Topic Discovery" — our own
    module name — in the route that prints it at the top of a teacher-ready
    document. One map now; see [[project_no_brand_in_thesis_output]] for the
    same class of leak."""
    from orchestrator.tools.m5_writing import MODULE_SECTION_LABELS
    assert MODULE_SECTION_LABELS["M1"] == "Introduction"
    assert "Topic Discovery" not in MODULE_SECTION_LABELS.values()


# --- what the agent DESCRIBES is what the document IS ------------------------

# A live project's stored `final_sections`, from the six-chapter era.
_LEGACY_SIX = [
    {"title": "Chương 1 — Giới thiệu", "prose": _pad("intro")},
    {"title": "Chương 2 — Tổng quan tài liệu", "prose": _pad("lit")},
    {"title": "Chương 3 — Phương pháp nghiên cứu", "prose": _pad("method")},
    {"title": "Chương 4 — Kết quả", "prose": _pad("results")},
    {"title": "Chương 5 — Thảo luận", "prose": _pad("discussion")},
    {"title": "Chương 6 — Kết luận", "prose": _pad("conclusion")},
    {"title": "Tài liệu tham khảo", "prose": "Nguyen, A. (2020)."},
]


def test_the_agent_reads_the_thesis_the_exporter_renders(tmp_path):
    """`read_slice("M5")` handed the model the raw STORAGE shape, so a project
    holding the six-chapter `final_sections` made the agent tell the student
    their thesis had seven chapters — naming a "Chương 5 — Thảo luận" that is
    not in the file they downloaded, while the exporter collapsed it into the
    canonical Chapter 5. Traced from a real project (8738b987)."""
    from agent.state import ProjectStateStore

    store = ProjectStateStore(tmp_path)
    store.commit_slice("M5", {"final_sections": _LEGACY_SIX}, "seed")

    seen = store.read_slice("M5")["slices"]["final_sections"]
    titles = [s.get("title") for s in seen]

    assert "Chương 5 — Thảo luận" not in titles
    assert not any("Chương 6" in (t or "") for t in titles)
    # Exactly what the exporter would ship from the same slice.
    assert titles == [s.get("title") for s in
                      sections_from_m5_slice({"final_sections": _LEGACY_SIX})]
    # The discussion prose is not lost — it leads the canonical Chapter 5.
    conclusion = next(s for s in seen if s.get("chapter_name") == "conclusion")
    assert _pad("discussion") in conclusion["prose"]
    assert _pad("conclusion") in conclusion["prose"]


def test_the_five_chapter_shape_is_what_the_agent_sees(tmp_path):
    from agent.state import ProjectStateStore
    from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER

    store = ProjectStateStore(tmp_path)
    store.commit_slice("M5", {"final_sections": _LEGACY_SIX}, "seed")
    seen = store.read_slice("M5")["slices"]["final_sections"]
    chapters = [s["chapter_name"] for s in seen if s.get("chapter_name")]
    assert chapters == list(M5_CHAPTER_ORDER)


# --- the flows --------------------------------------------------------------

def test_the_bibliography_closes_the_document():
    """Section order followed `final_sections`' own sequence, which only holds
    when that list IS the whole thesis. Once `chapters` supplies some of them, a
    chapter appended after a References entry rendered after the bibliography —
    a real project came out intro, lit_review, methodology, results, References,
    conclusion."""
    m5 = _slice()
    # The snapshot ends at References; `conclusion` exists only in `chapters`.
    order = [s.get("chapter_name") or s.get("title")
             for s in sections_from_m5_slice(m5, language="vi")]
    assert order == ["intro", "lit_review", "methodology", "results",
                     "conclusion", "Tài liệu tham khảo"]


# --- section identity -------------------------------------------------------

def test_a_section_is_identified_by_its_chapter_key_too():
    """A live row stores `{"title": "Chương 4 — Kết quả nghiên cứu", "chapter":
    "results"}`. The answer was in the row under a key no reader looked at."""
    m5 = {"final_sections": [{"title": "Chương 4 — Kết quả nghiên cứu",
                              "chapter": "results", "body": _pad("FROM-KEY")}]}
    assert chapter_prose(m5) == {"results": _pad("FROM-KEY")}


def test_a_near_miss_heading_resolves_by_its_chapter_number():
    """Exact title matching is brittle against a heading a producer wrote
    itself: "Chương 4 — Kết quả nghiên cứu" misses the canonical "Chương 4 —
    Kết quả" by two words. The number is unambiguous."""
    m5 = {"final_sections": [{"title": "Chương 4 — Kết quả nghiên cứu",
                              "prose": _pad("BY-NUMBER")}]}
    assert chapter_prose(m5) == {"results": _pad("BY-NUMBER")}


def test_a_superseded_remnant_does_not_render_as_a_sixth_section():
    """Two live rows carried an early draft in `final_sections` that resolves to
    no chapter — a 747-byte "we have no data yet" closing fragment, and a 4.6KB
    early Chapter 4. Rendering them after the real chapters ships a thesis that
    says the same chapter twice."""
    m5 = _slice()
    m5["final_sections"].append(
        {"title": "Kết luận và hướng nghiên cứu tiếp theo", "body": _pad("REMNANT")})
    titles = [s.get("chapter_name") or s.get("title")
              for s in sections_from_m5_slice(m5, language="vi")]
    assert "Kết luận và hướng nghiên cứu tiếp theo" not in titles
    # The bibliography is the one non-chapter that survives: the plain render
    # path has no other way to produce it.
    assert titles[-1] == "Tài liệu tham khảo"


def test_a_snapshot_only_thesis_keeps_its_extra_sections():
    """With no `chapters`, `final_sections` IS the thesis — an imported one may
    carry genuine extra sections, and dropping them would delete the student's
    work. Unchanged from before."""
    m5 = {"final_sections": [
        {"chapter_name": "intro", "prose": _pad("INTRO")},
        {"title": "Phụ lục A", "prose": _pad("APPENDIX")},
    ]}
    titles = [s.get("chapter_name") or s.get("title")
              for s in sections_from_m5_slice(m5, language="vi")]
    assert titles == ["intro", "Phụ lục A"]


def test_chat_and_editor_export_the_same_sections():
    """The chat export built its slice from the FLAT contextStore, which omits
    `chapters` — so it rendered the stale snapshot while the editor's Re-export
    rendered the edited chapters. Same project, two different documents; this is
    the difference that was visible in the downloaded files.
    """
    from agent.tools.writing import _m5_slice_for_export
    editor = _via_sections_from_m5_slice(_slice())
    chat = _via_sections_from_m5_slice(
        _m5_slice_for_export(_flat(), {"m5_writing": _slice()}))
    assert chat == editor


def test_chat_export_still_works_without_the_nested_store():
    """`load_full_context_store` is optional on the file-backed store — falling
    back to the flat projection must still produce the thesis it can see."""
    from agent.tools.writing import _m5_slice_for_export
    resolved = _via_sections_from_m5_slice(_m5_slice_for_export(_flat(), None))
    assert resolved["intro"] == STALE["intro"]


def test_a_written_chapter_is_never_recomposed(monkeypatch):
    """`compose_all_sections` reused from `final_sections` alone, so every
    chapter the editor had saved counted as "not written" and was rewritten —
    an LLM call paid to replace the student's own edits, and the seventh
    independent answer to which copy is the thesis."""
    import orchestrator.tools.m5_writing as M

    composed: list[str] = []

    def _compose(payload):
        composed.append(payload["chapter_name"])
        return {"prose": _pad("FRESH-" + payload["chapter_name"])}

    monkeypatch.setattr(M, "compose_chapter",
                        type("C", (), {"invoke": staticmethod(_compose)})())
    sections = M.compose_all_sections(
        {"m1_topic": {"language": "vi"}, "m2_literature": {}, "m3_design": {},
         "m4_analysis": {}, "m5_writing": _slice()})
    assert composed == [], f"recomposed already-written chapters: {composed}"
    assert {s["prose"] for s in sections} == set(EDITED.values())


# --- one composer ----------------------------------------------------------

_STORE_FOR_COMPOSE = {
    "m1_topic": {"research_title": "T", "language": "vi"},
    "m2_literature": {"research_gaps": [
        {"description": "Thiếu nghiên cứu về bối cảnh nội địa [3]", "refs": [3]},
    ]},
    # The paradigm stored NESTED, which is the shape only one composer handled.
    "m3_design": {"methodology": {"paradigm": "định lượng"}},
    "m4_analysis": {},
}


def test_both_entry_points_fill_the_prompt_from_the_same_slice(monkeypatch):
    """There were two composers, and they fed the same chapter templates
    different inputs for the same project: the partner one rendered
    `research_gaps` into a readable block and hardcoded `paradigm=""`, the
    chat/auto-mode one passed the raw gap list and filled the paradigm in.

    There is one composer now (`compose_chapters`) with two entry points that
    differ only in parameters, so this pins what those parameters resolve to.
    Patching `m5_writing.compose_chapter` alone reaches BOTH — which is itself
    the property being asserted: before the merge it would only have caught one.
    """
    import orchestrator.tools.m5_writing as M
    from orchestrator.tools import compose_export

    seen: list[dict] = []
    monkeypatch.setattr(M, "compose_chapter", type("C", (), {
        "invoke": staticmethod(lambda payload: seen.append(payload) or {"prose": _pad("X")}),
    })())

    M.compose_all_sections(_STORE_FOR_COMPOSE, chapters=["intro"])
    compose_export.compose_sections(_STORE_FOR_COMPOSE, ["intro"], "vi")

    assert len(seen) == 2, "one of the entry points bypassed the shared composer"
    chat, partner = seen
    assert chat["context_slice"] == partner["context_slice"]
    assert chat["paradigm"] == partner["paradigm"] == "định lượng"
    # Gaps arrive as a readable block with the brief's own [n] markers dropped —
    # they index the brief's scout, not this thesis's bibliography.
    assert chat["context_slice"]["research_gaps"] == "- Thiếu nghiên cứu về bối cảnh nội địa"


def test_research_gaps_is_always_a_string_for_the_template():
    """`{research_gaps}` is interpolated into three chapter templates."""
    from orchestrator.tools.m5_writing import compose_context_slice
    assert compose_context_slice({})["research_gaps"] == ""
    assert compose_context_slice(
        {"m2_literature": {"research_gaps": "already prose"}}
    )["research_gaps"] == "already prose"


def test_partner_export_reuses_the_edited_chapters(monkeypatch):
    """compose_sections read `final_sections` ONLY, so the partner report and
    headless auto-mode either shipped the stale snapshot or paid an LLM to
    recompose a chapter that was already written. Nothing may compose here."""
    import orchestrator.tools.m5_writing as M
    from orchestrator.tools import compose_export

    def _explode(_payload):
        raise AssertionError("recomposed a chapter that is already written")

    monkeypatch.setattr(M, "compose_chapter",
                        type("T", (), {"invoke": staticmethod(_explode)})())
    sections = compose_export.compose_sections(
        {"m5_writing": _slice(), "m1_topic": {}, "m2_literature": {},
         "m3_design": {}, "m4_analysis": {}},
        list(EDITED), "vi")
    assert {s["prose"] for s in sections} == set(EDITED.values())
