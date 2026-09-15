"""`targets` ADDS modules to the backfill walk — it must never shrink it.

The model picks `targets` when it calls `backfill_upstream_modules`, and on a
real thread (c10f6d13, 2026-09-15) it picked `['M4']` for a student whose
`m2_literature` was null and whose `m3_design` held only a questionnaire. The
auto-target — "every module up to the highest one with content that is not
COMPLETE" — would have selected M2 and M3. The narrowing was the model's, and
it decided those two chapters stayed empty.

What shipped: a Chapter 2 written with no literature state at all, and a
Chapter 3 that was 955 characters of "Chưa thể biên soạn Chương 3…" sitting in
the exported docx where a methodology chapter belongs.

The model may know the student is asking about the analysis; it does not get to
conclude from that that the literature review should stay empty.
"""
from unittest.mock import MagicMock

from orchestrator.backfill import reconstruct_upstream
from orchestrator.state import ContextStore


def _fake_llm() -> MagicMock:
    """Answers every slice with a candidate that is valid enough to keep."""
    llm = MagicMock()
    # One JSON for every slice: each module's filter keeps only its own fields,
    # so this must carry at least one REAL field per module or the candidate is
    # dropped as empty and the module silently drops out of the walk.
    llm.invoke.return_value.content = (
        '{"research_title": "T", "research_type": "quantitative", '
        '"field": "Du lịch", '
        '"research_state_summary": "S", "research_gaps": ["gap"], '
        '"citation_list": [{"title": "S", "year": 2024}], '
        '"paradigm": "quantitative", "design": "PLS-SEM", '
        '"tool": "SmartPLS", "sampling_strategy": "convenience", '
        '"target_sample_size": 200, '
        '"data_type_detected": "SmartPLS", '
        '"_rationale": "inferred"}'
    )
    return llm


def _thread_c10f6d13() -> ContextStore:
    """The real shape: M1 reconstructed, M2 null, M3 questionnaire-only, M4 thin."""
    return ContextStore(
        m1_topic={"research_title": "Tác động của tiếp thị người ảnh hưởng",
                  "research_type": "quantitative", "confirmed_at": "2026-09-15T05:31:59Z"},
        m3_design={"instrument": {"items": ["q1", "q2"]}},
        m4_analysis={"analysis_outline": {"research_design": "Định lượng, Likert 5"}},
    )


class _Store:
    """Enough DbProjectStateStore for the tool: slices in, commits recorded."""

    def __init__(self, slices):
        self._slices = slices
        self.committed: list[str] = []

    def load_full_context_store(self):
        return dict(self._slices)

    def commit_reconstructed(self, module, candidate):
        self.committed.append(module)
        return {"module": module, "status": "done"}

    def commit_slice(self, *a, **k):  # _move_final_chapter_to_m5
        raise RuntimeError("not used in this test")


def _tool_walked(targets, slices=None, monkeypatch=None):
    """Run the TOOL (where a model's `targets` arrives) and report the walk."""
    from agent.tools.backfill_tool import make_backfill_tool

    store = _Store(slices if slices is not None else {
        "m1_topic": _thread_c10f6d13().m1_topic,
        "m3_design": {"instrument": {"items": ["q1", "q2"]}},
        "m4_analysis": {"analysis_outline": {"research_design": "Định lượng, Likert 5"}},
    })
    seen: list[str] = []
    import orchestrator.backfill as bf
    real = bf.reconstruct_upstream

    def spy(cs, **kw):
        kw.setdefault("llm", _fake_llm())
        kw["ground_m2"] = False
        for e in real(cs, **kw) or []:
            seen.append(e["module"])
        return []

    monkeypatch.setattr(bf, "reconstruct_upstream", spy)
    make_backfill_tool(store).func(targets=targets, language="vi")
    return seen


def test_model_asking_for_m4_still_reconstructs_m2_and_m3(monkeypatch):
    walked = _tool_walked(["M4"], monkeypatch=monkeypatch)
    assert "M2" in walked, f"M2 (null slice) was skipped: {walked}"
    assert "M3" in walked, f"M3 (questionnaire only) was skipped: {walked}"


def test_the_asked_for_module_is_still_walked(monkeypatch):
    assert "M4" in _tool_walked(["M4"], monkeypatch=monkeypatch)


def test_no_targets_is_unchanged(monkeypatch):
    assert set(_tool_walked(None, monkeypatch=monkeypatch)) >= {"M2", "M3", "M4"}


def test_a_complete_module_is_still_skipped(monkeypatch):
    # Widening does not mean "redo finished work" — M1 here is whole.
    walked = _tool_walked(["M4"], monkeypatch=monkeypatch, slices={
        "m1_topic": {"research_title": "T", "research_type": "quantitative",
                     "field": "Du lịch", "scope": "VN", "objectives": ["o"],
                     "research_questions": ["rq"], "target_population": "p",
                     "confirmed_at": "2026-09-15T05:31:59Z"},
        "m4_analysis": {"analysis_outline": {"research_design": "Định lượng"}},
    })
    assert "M1" not in walked, f"a COMPLETE module was re-walked: {walked}"


def test_reconstruct_upstream_itself_stays_strict():
    # The widening belongs at the tool boundary. The primitive must keep meaning
    # exactly what it is told, or import paths and tests lose their scoping.
    seen: list[str] = []
    reconstruct_upstream(_thread_c10f6d13(), targets=["M4"], llm=_fake_llm(),
                         ground_m2=False, on_module=lambda e: seen.append(e["module"]))
    assert seen == ["M4"]


def test_the_card_shows_what_landed_not_what_was_proposed(monkeypatch):
    """A 21-construct proposal must not be advertised when 12 were saved.

    The candidate is an offer; the commit is the decision. Only owned keys
    survive and existing values beat the inference, so the two differ routinely.
    On a real project the chat card read "21 constructs · 23 edges" beside a
    context panel reading "12 constructs · 12 edges" — same model, two numbers,
    and the 21 included constructs the student's SmartPLS run never tested.
    """
    from agent.tools.backfill_tool import make_backfill_tool
    import orchestrator.backfill as bf

    landed = {"conceptual_model": {"nodes": [{"id": "n1"}], "edges": []},
              "paradigm": "quantitative"}
    store = _Store({"m4_analysis": {"analysis_outline": {"research_design": "Định lượng"}}})
    # commit_reconstructed "persists" the trimmed slice the store would keep.
    store.commit_reconstructed = lambda m, c: (
        store._slices.__setitem__("m3_design", landed) or {"module": m, "status": "done"})

    captured: list[dict] = []
    monkeypatch.setattr(bf, "reconstruct_upstream", lambda cs, **kw: [
        kw["on_module"]({"module": "M3", "artifact": "design",
                         "candidate": {"conceptual_model": {
                             "nodes": [{"id": f"n{i}"} for i in range(21)],
                             "edges": [{"from": "a", "to": "b"}] * 23}},
                         "rationale": None, "ready_to_confirm": True, "review": []})])
    import json
    out = json.loads(make_backfill_tool(store).func(targets=["M3"], language="vi"))
    shown = out["reconstructed"][0]["candidate"]["conceptual_model"]
    assert len(shown["nodes"]) == 1, "the card advertised the proposal, not the commit"
    assert shown["edges"] == []
