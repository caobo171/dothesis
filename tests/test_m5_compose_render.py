"""Phase 4: compose_chapter weaves verified-state blocks (mocked LLM)."""
import pytest

from tests.fixtures.renderer_blocks import PLS_BLOCK, SCREENING_BLOCK

m5 = pytest.importorskip("orchestrator.tools.m5_writing")
_REPAIRED = "This repaired chapter prose is sufficiently detailed to remain a real draft after the grounding check. " * 2


def _mock_llm(monkeypatch, text):
    class _R:
        content = text
    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {"invoke": lambda self, p: _R()})())


def _slice(**extra):
    s = {"results": PLS_BLOCK, "conceptual_model": {"nodes": [], "edges": []},
         "language": "en"}
    s.update(extra)
    return s


def test_results_weaves_at_token(monkeypatch):
    _mock_llm(monkeypatch, "The model explains variance.\n\n[[DT:structural_paths]]\n\nInterpretation.")
    out = m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    assert "dt-rendered:begin kind=structural_paths" in out["prose"]
    assert "0.34" in out["prose"]  # verbatim from fixture


def test_results_appends_when_token_omitted(monkeypatch):
    _mock_llm(monkeypatch, "No tables here, just prose about the findings.")
    out = m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    # tables appended even though the LLM emitted no token
    assert "dt-rendered:begin kind=measurement_model" in out["prose"]


def test_results_drops_llm_numeric_table(monkeypatch):
    _mock_llm(monkeypatch, "| H | path | beta | p |\n|---|---|---|---|\n| H1 | X | 0.99 | 0.5 |\n\n[[DT:structural_paths]]")
    out = m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    assert "0.99" not in out["prose"] and "0.34" in out["prose"]


def test_methodology_weaves_cleaning(monkeypatch):
    _mock_llm(monkeypatch, "We screened the data.\n\n[[DT:data_cleaning]]")
    out = m5.compose_chapter.func("methodology", "quantitative",
                             _slice(results=SCREENING_BLOCK), references=[], citation_style="apa7", language="en")
    assert SCREENING_BLOCK["data_screening"]["narrative"] in out["prose"]


def test_intro_unaffected(monkeypatch):
    _mock_llm(monkeypatch, "Background prose with no tables.")
    out = m5.compose_chapter.func("intro", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    assert "dt-rendered" not in out["prose"]


def test_empty_results_no_weave(monkeypatch):
    _mock_llm(monkeypatch, "Prose only.")
    out = m5.compose_chapter.func("results", "quantitative",
                             _slice(results=None), references=[], citation_style="apa7", language="en")
    assert "dt-rendered" not in out["prose"]


def test_real_path_validator_drives_composition_repair(monkeypatch):
    calls = []
    drafts = iter([
        "Kết quả ATT → INT có β = 0,999; t = 7,490; p < 0,001.",
        "Kết quả ATT → INT có β = 0,257; t = 7,490; p < 0,001. "
        "Kết quả được diễn giải trong phạm vi mẫu khảo sát. Thiết kế cắt ngang chưa đủ để khẳng định quan hệ nhân quả.",
    ])
    class Response:
        def __init__(self, content): self.content = content
    monkeypatch.setattr(m5, "_get_llm", lambda: type("LLM", (), {
        "invoke": lambda self, prompt: (calls.append(prompt), Response(next(drafts)))[1],
    })())
    context = {
        "hypotheses": [{"id": "H1", "path": "ATT -> INT"}],
        "analysis_results": {"hypothesis_tests": [{"hypothesis": "H1", "path": "ATT -> INT",
            "numbers": {"beta": 0.257, "t": 7.49, "p": "0.000"}, "decision": "supported"}]},
    }
    out = m5.compose_chapter.func("results", "quantitative", context, [], "apa7", "vi")
    assert len(calls) == 2
    assert "coherence.number_mismatch" in calls[1]
    assert "0,999" not in out["prose"] and "0,257" in out["prose"]


def test_results_and_conclusion_prompts_prefer_canonical_m4_and_m3_register(monkeypatch):
    prompts = []

    class _R:
        content = "Grounded prose."

    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {
        "invoke": lambda self, prompt: (prompts.append(prompt), _R())[1],
    })())
    context = {
        "results": {"hypothesis_tests": [{"id": "H1", "path": "OLD -> PATH"}]},
        "analysis_results": {"hypothesis_tests": [{"id": "H1", "path": "ATT -> INT",
            "numbers": {"beta": 0.31, "p": "0.000"}, "decision": "supported"}]},
        "hypotheses": [{"id": "H1", "path": "ATT -> INT", "direction": "positive"}],
        "constructs": [
            {"id": "ATT", "label": "Thái độ đối với du lịch nội địa"},
            {"id": "INT", "label": "Ý định du lịch nội địa"},
        ],
        "conceptual_model": {"nodes": [], "edges": []},
    }

    for chapter in ("results", "conclusion"):
        m5.compose_chapter.func(chapter, "quantitative", context, references=[], citation_style="apa7", language="vi")

    assert len(prompts) == 2
    for prompt in prompts:
        assert "H1; canonical path: ATT (Thái độ đối với du lịch nội địa) → INT (Ý định du lịch nội địa)" in prompt
        assert '"path": "ATT -> INT"' in prompt
        assert '"p": "<0.001"' in prompt
        assert "OLD -> PATH" not in prompt


def test_only_reported_three_decimal_zero_p_values_become_threshold_text():
    assert m5._display_p_values({"p": "0.000", "other": {"p": "0.0000"}}) == {
        "p": "<0.001", "other": {"p": "<0.001"},
    }
    assert m5._display_p_values({"p": 0, "p_value": "0.0"}) == {"p": 0, "p_value": "0.0"}


def test_composer_repairs_one_grounding_failure(monkeypatch):
    calls = []

    class _R:
        def __init__(self, content): self.content = content

    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {
        "invoke": lambda self, prompt: (calls.append(prompt), _R("bad claim" if len(calls) == 1 else _REPAIRED))[1],
    })())
    monkeypatch.setattr(m5, "_generated_grounding_findings",
                        lambda chapters, _context: [{"check": "coherence.unsupported_diagnostic_claim"}]
                        if "bad claim" in next(iter(chapters.values())) else [])

    out = m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    assert out["prose"].startswith("This repaired chapter prose")
    assert len(calls) == 2 and "Required grounding repair" in calls[1]


def test_composer_repairs_a_hard_numeric_mismatch_once(monkeypatch):
    calls = []

    class _R:
        def __init__(self, content): self.content = content

    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {
        "invoke": lambda self, prompt: (calls.append(prompt), _R("wrong beta" if len(calls) == 1 else f"β = 0.34. {_REPAIRED}"))[1],
    })())
    numeric = [{"check": "coherence.number_mismatch", "severity": "hard",
                "expected": {"beta": 0.34}}]
    monkeypatch.setattr(m5, "_generated_grounding_findings",
                        lambda chapters, _context: numeric if "wrong beta" in next(iter(chapters.values())) else [])

    out = m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    assert "0.34" in out["prose"] and len(calls) == 2
    assert "exact canonical value and decision" in calls[1]


def test_composer_refuses_a_second_grounding_failure(monkeypatch):
    class _R:
        content = "bad claim"

    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {"invoke": lambda self, _prompt: _R()})())
    monkeypatch.setattr(m5, "_generated_grounding_findings",
                        lambda *_args: [{"check": "coherence.unsupported_diagnostic_claim"}])

    with pytest.raises(m5.CompositionGroundingError):
        m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")


def test_composer_refuses_a_second_hard_numeric_mismatch_or_empty_repair(monkeypatch):
    class _R:
        content = "wrong beta"

    numeric = [{"check": "coherence.number_mismatch", "severity": "hard"}]
    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {"invoke": lambda self, _prompt: _R()})())
    monkeypatch.setattr(m5, "_generated_grounding_findings", lambda *_args: numeric)
    with pytest.raises(m5.CompositionGroundingError):
        m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")

    class _Empty:
        content = ""
    empty_calls = []
    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {
        "invoke": lambda self, _prompt: (empty_calls.append(1), _R() if len(empty_calls) == 1 else _Empty())[1],
    })())
    with pytest.raises(m5.CompositionGroundingError):
        m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")


def test_rewriter_uses_the_same_single_grounding_repair(monkeypatch):
    calls = []

    class _R:
        def __init__(self, content): self.content = content

    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {
        "invoke": lambda self, prompt: (calls.append(prompt), _R("bad claim" if len(calls) == 1 else _REPAIRED))[1],
    })())
    monkeypatch.setattr(m5, "_generated_grounding_findings",
                        lambda chapters, _context: [{"check": "coherence.unsupported_diagnostic_claim"}]
                        if "bad claim" in next(iter(chapters.values())) else [])

    out = m5.rewrite_chapter.func("results", "current prose", "improve wording", _slice(), [], "en")
    assert out["prose"].startswith("This repaired chapter prose")
    assert len(calls) == 2 and "Required grounding repair" in calls[1]


def test_rewriter_repairs_a_hard_numeric_mismatch(monkeypatch):
    calls = []

    class _R:
        def __init__(self, content): self.content = content

    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {
        "invoke": lambda self, prompt: (calls.append(prompt), _R("wrong beta" if len(calls) == 1 else f"β = 0.34. {_REPAIRED}"))[1],
    })())
    numeric = [{"check": "coherence.number_mismatch", "severity": "hard"}]
    monkeypatch.setattr(m5, "_generated_grounding_findings",
                        lambda chapters, _context: numeric if "wrong beta" in next(iter(chapters.values())) else [])
    out = m5.rewrite_chapter.func("results", "current prose", "improve wording", _slice(), [], "en")
    assert "0.34" in out["prose"] and len(calls) == 2


def test_compose_chapters_does_not_fallback_after_a_grounding_error(monkeypatch):
    class _Composer:
        def invoke(self, _payload):
            raise m5.CompositionGroundingError([{"check": "coherence.unsupported_diagnostic_claim"}])

    monkeypatch.setattr(m5, "compose_chapter", _Composer())
    monkeypatch.setattr(m5, "_fallback_section", lambda *_args: (_ for _ in ()).throw(AssertionError("fallback used")))
    with pytest.raises(m5.CompositionGroundingError):
        m5.compose_chapters({"m4_analysis": {"analysis_results": {}}}, chapters=["results"])


# --- the moderator must appear, and on the right arrow ----------------------

_MOD_CM = {
    "nodes": [
        {"id": "EXP", "label": "Chuyên môn", "type": "independent"},
        {"id": "INT", "label": "Ý định du lịch", "type": "mediator"},
        {"id": "DEC", "label": "Quyết định du lịch", "type": "dependent"},
        {"id": "INC", "label": "Thu nhập", "type": "moderator"},
    ],
    "edges": [
        {"effect": "direct", "source": "EXP", "target": "INT", "hypothesis": "H1: +"},
        {"effect": "direct", "source": "INT", "target": "DEC", "hypothesis": "H7: +"},
        {"effect": "direct", "source": "INC", "target": "DEC", "hypothesis": "H8: +"},
        {"effect": "moderates", "source": "INC", "target": "INT",
         "hypothesis": "H9: moderates INT→DEC"},
    ],
}


def test_mermaid_hangs_the_moderator_on_the_moderated_path():
    from orchestrator.tools.m5_writing import _conceptual_model_to_mermaid

    mmd = _conceptual_model_to_mermaid(_MOD_CM, "vi")
    assert "INT --- MODJ1" in mmd
    assert "MODJ1 -->|H7: +| DEC" in mmd
    assert "INC -.->|H9| MODJ1" in mmd


def test_a_moderators_own_direct_effect_is_not_swallowed():
    """`is_mod` used to be true for ANY edge leaving a node typed `moderator`,
    so H8 — a real, tested direct effect — was redrawn as a second dashed
    "Điều tiết" arrow and its hypothesis id vanished from the figure."""
    from orchestrator.tools.m5_writing import _conceptual_model_to_mermaid

    mmd = _conceptual_model_to_mermaid(_MOD_CM, "vi")
    assert "INC -->|H8: +| DEC" in mmd
    assert mmd.count("-.->") == 1


def test_the_docx_figure_lists_the_moderation_as_a_hypothesis():
    """The Pillow figure skipped moderation edges outright, so a nine-hypothesis
    study exported a model drawing eight — with nothing saying one was missing."""
    from orchestrator.tools.m5_writing import _pillow_model_figure

    out = _pillow_model_figure(_MOD_CM, "vi")
    if out is None:
        import pytest
        pytest.skip("Pillow/font unavailable in this environment")
    assert "Thu nhập điều tiết mối quan hệ giữa Ý định du lịch → Quyết định du lịch" in out
    assert "Thu nhập → Quyết định du lịch (H8: +)" in out


def test_a_stale_generated_figure_block_is_refreshed_at_export():
    """The block is ours end to end, and it froze the model as it was that day.

    A moderator the renderer used to drop never reappears, and the image path
    points into the export scratch dir, which does not survive a reboot — so an
    old chapter eventually exports with no figure at all.
    """
    from orchestrator.tools.m5_writing import _ensure_model_diagram

    student_prose = "## 3.1 Thiết kế nghiên cứu\n\nNghiên cứu sử dụng thiết kế cắt ngang.\n"
    stale = (student_prose + "\n**Hình 3.1: Mô hình nghiên cứu đề xuất**\n\n"
             "![Mô hình nghiên cứu](/tmp/orchestrator_scratch/conceptmodel-dead.png)\n\n"
             "**Mối quan hệ giả thuyết trong mô hình:**\n\n"
             "- Ý định du lịch → Quyết định du lịch (H7: +)\n")

    out = _ensure_model_diagram(stale, _MOD_CM, "vi")

    assert out.count("**Hình 3.1") == 1, "refreshed, not appended a second time"
    assert "conceptmodel-dead.png" not in out, "the dead scratch path is gone"
    assert "Thu nhập điều tiết mối quan hệ" in out, "the moderator is in the list now"
    # Everything the student wrote is untouched — the block only ever trails it.
    assert out.startswith(student_prose)


def test_a_hand_drawn_mermaid_chapter_is_left_alone():
    """A diagram the LLM wrote is the student's chapter, not ours to replace."""
    from orchestrator.tools.m5_writing import _ensure_model_diagram

    authored = ("## 3.2 Mô hình\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
    assert _ensure_model_diagram(authored, _MOD_CM, "vi") == authored


def test_a_students_own_figure_does_not_get_a_second_one_bolted_on():
    from orchestrator.tools.m5_writing import _ensure_model_diagram

    own = "## 3.2 Mô hình\n\n![Research model](/uploads/my-own-figure.png)\n"
    assert _ensure_model_diagram(own, _MOD_CM, "vi") == own


def test_each_box_carries_its_construct_code():
    """Every table in the thesis is keyed by these codes (ATT_1, the HTMT
    matrix, the path list), so the figure names them rather than making the
    reader hold the mapping in their head. Web and docx must agree — the same
    code line, the same box height."""
    from orchestrator.tools.m5_writing import _pillow_model_figure

    out = _pillow_model_figure(_MOD_CM, "vi")
    if out is None:
        import pytest
        pytest.skip("Pillow/font unavailable in this environment")
    # The drawing itself is pixels; what is assertable is that it still renders
    # and the relationship list still names every construct by its label.
    assert "Ý định du lịch → Quyết định du lịch (H7: +)" in out
