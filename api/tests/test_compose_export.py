"""F1 gate unification + shared compose back-half. Pure functions over a
context_store dict — no network, no export subprocess (run_export/compose_chapter
are stubbed where used)."""
from orchestrator.tools.m5_writing import assess_export_readiness

# Five-chapter collapse: "discussion" is retired as a canonical chapter name
# (LEGACY_CHAPTER_ALIASES maps it to "conclusion"); this list matches
# M5_CHAPTER_ORDER.
_FULL = ["intro", "lit_review", "methodology", "results", "conclusion"]


def test_gate_all_chapters_reports_everything_missing():
    assert assess_export_readiness({}, _FULL)  # empty store -> many missing


def test_gate_scopes_to_requested_chapters():
    # A store with only M4 results, composing ONLY results+conclusion:
    store = {"m4_analysis": {"analysis_results": "AVE=0.62 HTMT ok R2=.41"}}
    missing = assess_export_readiness(store, ["results", "conclusion"])
    # methodology not requested -> not reported; M4 results present -> not reported.
    assert not any("methodology" in m.lower() for m in missing)
    assert not any("analysis results" in m.lower() for m in missing)


def test_gate_none_chapters_is_backcompat_full_check():
    assert assess_export_readiness({}) == assess_export_readiness({}, None)


# --- Task 2: shared prose sanitation lives in the engine now ----------------
from orchestrator.tools.m5_writing import sanitize_prose


def test_sanitize_demotes_heading_hypothesis():
    # "### H1: full sentence." -> "**H1:** full sentence." (no oversized heading, no TOC).
    out = sanitize_prose("### H1: Trust positively affects intention to use the system.")
    assert out.startswith("**H1:**")
    assert not out.lstrip().startswith("#")


def test_sanitize_drops_placeholder_table():
    md = "**Bảng 4.1**\n\n| A | B |\n|---|---|\n| … | … |\n\n*Nguồn: tác giả*\n\nReal prose."
    out = sanitize_prose(md)
    assert "|" not in out          # the dotted shell table is gone
    assert "Real prose." in out    # surrounding prose kept


# --- Task 3: shared compose_and_export back half ----------------------------
import orchestrator.tools.m5_writing as m5
from orchestrator.tools import compose_export as ce


def test_compose_sections_orders_canonically_and_calls_compose(monkeypatch):
    seen = []

    # compose_chapter is a LangChain StructuredTool (pydantic) whose .invoke is
    # not a settable field, so we swap the whole object in the ce namespace that
    # compose_sections resolves — proving compose is called once per chapter.
    class _FakeTool:
        def invoke(self, payload):
            seen.append(payload["chapter_name"])
            return {"prose": f"prose for {payload['chapter_name']}"}

    monkeypatch.setattr(ce, "compose_chapter", _FakeTool())
    store = {"m1_topic": {"research_title": "T"}, "m4_analysis": {"analysis_results": "x"}}
    # Pass chapters OUT of order; expect canonical order in the output.
    out = ce.compose_sections(store, ["results", "intro"], "en")
    assert [s["title"] for s in out]  # titles resolved
    assert seen == ["intro", "results"]  # canonical order enforced


# --- the composer must SEE M2 -----------------------------------------------
def test_context_slice_carries_m2_research_gaps(monkeypatch):
    """The Introduction/Lit-review/Conclusion prompts all interpolate
    {research_gaps} and label it "from M2" — but the slice was built from
    m1+m3+m4 only, so the key was ALWAYS empty and the gap-rendering block right
    below it was dead code. `research_gaps` is M2-owned (agent/state.py), so the
    only way a real gap reaches a prompt is by merging m2.
    """
    seen = {}

    class _FakeTool:
        def invoke(self, payload):
            seen.update(payload)
            return {"prose": "prose"}

    monkeypatch.setattr(ce, "compose_chapter", _FakeTool())
    ce.compose_sections(
        {"m1_topic": {"research_title": "T"},
         "m2_literature": {"research_gaps": [{"description": "no VN evidence [3]"}]}},
        ["intro"], "en",
    )
    # Rendered prose, source numbers stripped (they index the brief's scout, not
    # this report's bibliography).
    assert seen["context_slice"]["research_gaps"] == "- no VN evidence"


def test_context_slice_prefers_downstream_modules_over_m2(monkeypatch):
    """m2 merges BETWEEN m1 and m3 so the module precedence m1 < m2 < m3 < m4
    matches READS order — a later module's value still wins."""
    seen = {}

    class _FakeTool:
        def invoke(self, payload):
            seen.update(payload)
            return {"prose": "prose"}

    monkeypatch.setattr(ce, "compose_chapter", _FakeTool())
    ce.compose_sections(
        {"m1_topic": {"decisions": ["m1"]}, "m2_literature": {"decisions": ["m2"]},
         "m3_design": {"decisions": ["m3"]}},
        ["intro"], "en",
    )
    assert seen["context_slice"]["decisions"] == ["m3"]


def test_compose_and_export_calls_run_export(monkeypatch):
    monkeypatch.setattr(ce, "compose_sections",
                        lambda *a, **k: [{"title": "Chapter 4 — Results", "prose": "p"}])
    called = {}
    # compose_and_export calls run_export THROUGH the m5_writing module (not a
    # name bound at import), so patching m5.run_export intercepts it.
    # **kw, not a fixed signature: a stub that pins the caller's arguments as
    # they were fails the moment a real argument is added, and this one hid the
    # fact that no caller passed the store run_export reads the cover title off.
    monkeypatch.setattr(m5, "run_export",
                        lambda sections, pid, **kw:
                        called.update(pid=pid, n=len(sections), cs=kw.get("context_store")) or
                        [{"kind": "pdf", "s3_key": f"projects/{pid}/x.pdf", "size_bytes": 1}])
    arts = ce.compose_and_export({"m1_topic": {"research_title": "T"}}, "partner-abc",
                                 chapters=["results"], language="en")
    assert called["pid"] == "partner-abc" and called["n"] == 1
    # The store has to reach run_export or the cover page has no title.
    assert called["cs"] == {"m1_topic": {"research_title": "T"}}
    assert arts[0]["kind"] == "pdf"


# --- Task 2: the conclusion-merge machinery is deleted, not just unused -----
# With M5_CHAPTER_ORDER collapsed to five chapters (Task 1), `conclusion` IS
# the final chapter — there is nothing left to merge it INTO. The old
# merge_conclusion argument existed only because the canonical order used to
# declare six chapters and this was the one path that patched it back to five;
# now every path (auto-export, agent tool, editor, partner) gets five chapters
# for free, from the same order, with no caller having to remember an argument.
def test_compose_sections_emits_five_chapters_with_no_chapter_six(monkeypatch):
    # The whole point of the collapse: no caller has to remember to merge,
    # because there is no sixth chapter to merge away.
    #
    # compose_chapter is a LangChain StructuredTool (pydantic): `.invoke` is
    # not a settable field on the instance (pydantic raises "no field
    # 'invoke'"), so — same as the other fakes in this file — swap the whole
    # object in the ce namespace rather than patching an attribute onto it.
    class _FakeTool:
        def invoke(self, payload):
            return {"prose": f"Prose for {payload['chapter_name']}."}

    monkeypatch.setattr(ce, "compose_chapter", _FakeTool())

    out = ce.compose_sections({}, list(ce.M5_CHAPTER_ORDER), "vi")

    assert len(out) == 5
    titles = [s["title"] for s in out]
    assert titles[-1] == "Chương 5 — Kết luận và Kiến nghị"
    assert not any("6" in t for t in titles)


def test_compose_sections_has_no_merge_parameter():
    # Guards against the merge being reintroduced as an argument some callers
    # pass and others forget — the exact bug this change removes.
    import inspect
    assert "merge_conclusion" not in inspect.signature(ce.compose_sections).parameters
    assert not hasattr(ce, "wants_merged_conclusion")
    assert not hasattr(ce, "merged_chapter_keys")
