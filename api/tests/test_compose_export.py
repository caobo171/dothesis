"""F1 gate unification + shared compose back-half. Pure functions over a
context_store dict — no network, no export subprocess (run_export/compose_chapter
are stubbed where used)."""
from orchestrator.tools.m5_writing import assess_export_readiness

_FULL = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


def test_gate_all_chapters_reports_everything_missing():
    assert assess_export_readiness({}, _FULL)  # empty store -> many missing


def test_gate_scopes_to_requested_chapters():
    # A store with only M4 results, composing ONLY results+discussion:
    store = {"m4_analysis": {"analysis_results": "AVE=0.62 HTMT ok R2=.41"}}
    missing = assess_export_readiness(store, ["results", "discussion"])
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
    """The Introduction/Lit-review/Discussion prompts all interpolate
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
    monkeypatch.setattr(m5, "run_export",
                        lambda sections, pid, references=None, language="en":
                        called.update(pid=pid, n=len(sections)) or
                        [{"kind": "pdf", "s3_key": f"projects/{pid}/x.pdf", "size_bytes": 1}])
    arts = ce.compose_and_export({"m1_topic": {}}, "partner-abc",
                                 chapters=["results"], language="en")
    assert called == {"pid": "partner-abc", "n": 1}
    assert arts[0]["kind"] == "pdf"


# --- headless convergence: Discussion+Conclusion merge is an export argument -
def test_merge_conclusion_relabels_discussion(monkeypatch):
    seen = []

    class _FakeTool:
        def invoke(self, payload):
            seen.append(payload["chapter_name"])
            return {"prose": f"prose for {payload['chapter_name']}"}

    monkeypatch.setattr(ce, "compose_chapter", _FakeTool())
    sections = ce.compose_sections(
        {"m1_topic": {}, "m4_analysis": {}},
        ["intro", "results", "discussion", "conclusion"],
        "vi", merge_conclusion=True,
    )
    assert "conclusion" not in seen            # dropped, not composed twice
    # `seen` is append order across a ThreadPoolExecutor, so it says WHICH
    # chapters were composed, never in what order they finished. Ordering is
    # asserted below, on the returned sections, which compose_sections does
    # guarantee.
    assert "discussion" in seen
    assert sections[-1]["title"] == "Chương 5 — Kết luận"
