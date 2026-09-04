from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from orchestrator.schemas.m1 import M1Output
from orchestrator.schemas.m2 import CitedGap, M2Output, PaperReference
from orchestrator.schemas.m3 import M3Output
from orchestrator.schemas.m4 import M4Output
from orchestrator.schemas.m5 import ExportArtifact, M5Output


def test_m1_required_fields():
    out = M1Output(
        research_title="A study on X",
        field="Marketing",
        research_type="quantitative",
        target_population="SME employees",
        scope="Vietnam, 2026",
        objectives=["Identify factors"],
        research_questions=["Does X affect Y?"],
    )
    assert out.confirmed_at is None


def test_m1_rejects_empty_objectives():
    with pytest.raises(ValidationError):
        M1Output(
            research_title="t", field="Marketing", research_type="quantitative",
            target_population="x", scope="y", objectives=[], research_questions=["q"],
        )


def test_m2_with_cited_gap():
    g = CitedGap(
        description="No SME context",
        supporting_papers=[PaperReference(author="Wang", year=2011, page=118)],
        relevance="High",
        confirmed=True,
    )
    out = M2Output(
        research_state_summary="…",
        research_gaps=[g],
        theoretical_framework="TL + EE",
        hypotheses=["H1"],
        literature_review_doc="…",
        citation_list=[{"author": "Wang", "year": 2011}],
    )
    assert out.research_gaps[0].supporting_papers[0].page == 118


def test_m3_paradigm_branch():
    # thematic_framework removed in SP4; qualitative partial is valid without confirmed_at
    out = M3Output(
        paradigm="qualitative", design="thematic_analysis", tool="manual",
        sampling_strategy="purposive", target_sample_size=12,
    )
    assert out.conceptual_model is None
    assert out.themes is None  # optional until confirmed


def test_m4_minimal():
    out = M4Output(
        data_type_detected="SPSS",
        analysis_outline={"sections": ["Descriptive", "Reliability"], "confirmed_by_user": True},
        results={},
        interpretations={},
    )
    assert out.data_type_detected == "SPSS"


def test_m5_export_artifact():
    # Decision: test is about ExportArtifact back-compat with the deprecated `uri`
    # field, not about a confirmed M5Output. Removing confirmed_at so the
    # @model_validator (which requires 6 chapters + docx on confirm) does not fire.
    a = ExportArtifact(kind="docx", uri="s3://bucket/key", size_bytes=12345)
    out = M5Output(
        sections=[{"name": "Ch.1", "text": "..."}],
        export_artifacts=[a],
    )
    assert out.export_artifacts[0].uri.startswith("s3://")


def test_m3_output_unconfirmed_partial_is_valid():
    """In-progress partials should validate even without paradigm-specific fields."""
    out = M3Output(
        paradigm="quantitative",
        design="PLS-SEM", tool="SmartPLS",
        sampling_strategy="convenience", target_sample_size=200,
        # No conceptual_model — but confirmed_at not set, so unconfirmed.
    )
    assert out.confirmed_at is None


def test_m3_output_quant_confirm_requires_conceptual_model():
    """Setting confirmed_at on a quant paradigm requires conceptual_model
    (which now carries both paths AND per-construct Likert items as
    node.questions, since the 2026-06 merge folded the prior scale_items
    field into the flow_chart shape)."""
    with pytest.raises(ValidationError):
        M3Output(
            paradigm="quantitative",
            design="PLS-SEM", tool="SmartPLS",
            sampling_strategy="convenience", target_sample_size=200,
            confirmed_at=datetime.now(timezone.utc),
            # missing conceptual_model
        )


def test_m3_output_quant_confirm_with_conceptual_model_validates():
    out = M3Output(
        paradigm="quantitative",
        design="PLS-SEM", tool="SmartPLS",
        sampling_strategy="convenience", target_sample_size=200,
        conceptual_model={
            "nodes": [{"id": "n0", "label": "TL",
                       "questions": ["My supervisor inspires me."]}],
            "edges": [],
        },
        confirmed_at=datetime.now(timezone.utc),
    )
    assert out.conceptual_model is not None


def test_m3_output_qual_confirm_requires_qual_artifacts():
    with pytest.raises(ValidationError):
        M3Output(
            paradigm="qualitative",
            design="Thematic Analysis", tool="NVivo",
            sampling_strategy="purposive", target_sample_size=12,
            confirmed_at=datetime.now(timezone.utc),
            # missing themes + interview_guide + purposive_criteria
        )


def test_m3_output_mixed_confirm_requires_design_type_and_both_sets():
    with pytest.raises(ValidationError):
        M3Output(
            paradigm="mixed",
            design="PLS-SEM", tool="SmartPLS",
            sampling_strategy="hybrid", target_sample_size=200,
            confirmed_at=datetime.now(timezone.utc),
            # missing mixed_design_type + qual artifacts
        )


def test_m3_output_mixed_confirm_with_full_artifacts_validates():
    out = M3Output(
        paradigm="mixed",
        design="PLS-SEM", tool="SmartPLS",
        sampling_strategy="quant: random N=200; qual: purposive N=12",
        target_sample_size=200,
        mixed_design_type="sequential_explanatory",
        conceptual_model={
            "nodes": [{"id": "n0", "label": "TL", "questions": ["I1"]}],
            "edges": [],
        },
        themes=[{"id": "t1", "theme": "Leadership style", "sub_themes": []}],
        interview_guide={"sections": [{"phase": "main", "questions": []}]},
        purposive_criteria=[{"criterion": "tenure >= 6 months"}],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert out.mixed_design_type == "sequential_explanatory"


def test_step_result_minimal():
    from orchestrator.schemas.m4 import StepResult
    sr = StepResult(step_name="Cronbach's Alpha")
    assert sr.step_name == "Cronbach's Alpha"
    assert sr.table == []
    assert sr.thresholds_met is None
    assert sr.interpretation == ""
    assert sr.parser == "regex"


def test_step_result_full():
    from orchestrator.schemas.m4 import StepResult
    sr = StepResult(
        step_name="Reliability",
        table=[{"construct": "TL", "alpha": 0.84, "n_items": 5}],
        thresholds_met=True,
        interpretation="All scales reliable.",
        raw_paste_excerpt="Cronbach's Alpha\n.840",
        parser="regex",
    )
    blob = sr.model_dump()
    assert blob["table"][0]["alpha"] == 0.84
    assert blob["parser"] == "regex"


def test_m4_unconfirmed_partial_is_valid_minimal():
    """In-progress partials are valid even with no results."""
    from orchestrator.schemas.m4 import M4Output
    out = M4Output(
        data_type_detected="SPSS",
        analysis_outline={"sections": [], "confirmed_by_user": False},
    )
    assert out.confirmed_at is None
    assert out.results == {}


def test_m4_spss_confirm_requires_results():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m4 import M4Output
    with pytest.raises(ValidationError):
        M4Output(
            data_type_detected="SPSS",
            analysis_outline={"sections": [{"name": "Descriptive"}], "confirmed_by_user": True},
            confirmed_at=datetime.now(timezone.utc),
            # missing results
        )


def test_m4_qualitative_confirm_requires_codes_and_themes():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m4 import M4Output
    with pytest.raises(ValidationError):
        M4Output(
            data_type_detected="Qualitative",
            analysis_outline={"sections": [], "confirmed_by_user": True},
            confirmed_at=datetime.now(timezone.utc),
            qual_codes=[{"code": "leadership style", "quote": "..."}],
            # missing qual_themes
        )


def test_m4_qualitative_confirm_with_codes_and_themes_validates():
    from datetime import datetime, timezone
    from orchestrator.schemas.m4 import M4Output
    out = M4Output(
        data_type_detected="Qualitative",
        analysis_outline={"sections": [{"name": "Initial coding"}], "confirmed_by_user": True},
        qual_codes=[{"code": "leadership style", "quote": "..."}],
        qual_themes=[{"theme": "Leadership", "codes": ["leadership style"]}],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert len(out.qual_codes) == 1
    assert len(out.qual_themes) == 1


def test_m4_mixed_confirm_requires_both_sets():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m4 import M4Output
    with pytest.raises(ValidationError):
        M4Output(
            data_type_detected="Mixed",
            analysis_outline={"sections": [], "confirmed_by_user": True},
            confirmed_at=datetime.now(timezone.utc),
            results={"Descriptive": {"step_name": "Descriptive"}},
            qual_codes=[],
            qual_themes=[],
        )


def test_chapter_draft_minimal():
    from orchestrator.schemas.m5 import ChapterDraft
    cd = ChapterDraft(name="intro", prose="# Introduction\n...")
    assert cd.name == "intro"
    assert cd.prose.startswith("# Introduction")
    assert cd.citations_used == []
    assert cd.uncited_warnings == []


def test_chapter_draft_with_citations():
    from orchestrator.schemas.m5 import ChapterDraft
    cd = ChapterDraft(
        name="lit_review", prose="...",
        citations_used=["Bass, 1990", "Avolio et al., 2009"],
        uncited_warnings=["Smith, 2023"],
    )
    blob = cd.model_dump()
    assert blob["citations_used"][0] == "Bass, 1990"
    assert blob["uncited_warnings"] == ["Smith, 2023"]


def test_export_artifact_new_shape():
    from orchestrator.schemas.m5 import ExportArtifact
    a = ExportArtifact(
        kind="docx",
        s3_key="projects/abc/exports/thesis-X.docx",
        download_url="/api/v1/projects/abc/exports/thesis-X.docx",
        size_bytes=12345,
    )
    assert a.s3_key.startswith("projects/")
    assert a.download_url.startswith("/api/v1/")
    assert a.uri == ""  # deprecated field, default empty


def test_m5_unconfirmed_partial_is_valid_minimal():
    from orchestrator.schemas.m5 import M5Output
    out = M5Output()  # all fields default
    assert out.chapters == {}
    assert out.export_artifacts == []
    assert out.confirmed_at is None


def test_m5_confirm_requires_all_five_chapters():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m5 import M5Output, ExportArtifact
    from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER
    with pytest.raises(ValidationError) as exc:
        M5Output(
            chapters={"intro": {"name": "intro", "prose": "x"}},
            export_artifacts=[ExportArtifact(
                kind="docx", s3_key="k", download_url="u", size_bytes=1,
            )],
            confirmed_at=datetime.now(timezone.utc),
        )
    # Discriminating: pins the *exact* missing set the validator reports —
    # the other four canonical chapters, never "discussion" (retired) and
    # never more/fewer than what M5_CHAPTER_ORDER actually requires. A
    # regression back to six (or a dropped member) changes this list.
    expected_missing = sorted(set(M5_CHAPTER_ORDER) - {"intro"})
    assert f"missing: {expected_missing}" in str(exc.value)


def test_m5_confirm_requires_docx_artifact():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m5 import M5Output
    from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER
    chapters = {n: {"name": n, "prose": "x"} for n in M5_CHAPTER_ORDER}
    with pytest.raises(ValidationError) as exc:
        M5Output(
            chapters=chapters,
            export_artifacts=[],  # no docx
            confirmed_at=datetime.now(timezone.utc),
        )
    assert "docx" in str(exc.value).lower()


def test_m5_confirm_passes_with_five_chapters_and_docx():
    from datetime import datetime, timezone
    from orchestrator.schemas.m5 import M5Output, ExportArtifact
    from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER
    chapters = {n: {"name": n, "prose": "x"} for n in M5_CHAPTER_ORDER}
    out = M5Output(
        chapters=chapters,
        export_artifacts=[ExportArtifact(
            kind="docx", s3_key="k", download_url="u", size_bytes=1,
        )],
        confirmed_at=datetime.now(timezone.utc),
    )
    # Discriminating against the required set drifting: asserts the present
    # chapters are exactly the five canonical names (M5_CHAPTER_ORDER), not
    # a hardcoded count that would stay green under a six-chapter regression.
    assert set(out.chapters) == set(M5_CHAPTER_ORDER)
    assert len(out.chapters) == 5


def test_m5_confirm_tolerates_a_stray_retired_discussion_key():
    """`chapters` is typed `dict[str, dict]`, not keyed on `ChapterName`, so
    a project carrying a leftover "discussion" chapter from before the
    five-chapter collapse must NOT fail confirm — it's dead weight, not a
    shape violation. In-flight projects depend on this tolerance until
    they're backfilled; this pins it as deliberate, not accidental."""
    from datetime import datetime, timezone
    from orchestrator.schemas.m5 import M5Output, ExportArtifact
    from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER
    chapters = {n: {"name": n, "prose": "x"} for n in M5_CHAPTER_ORDER}
    chapters["discussion"] = {"name": "discussion", "prose": "stale leftover"}
    out = M5Output(
        chapters=chapters,
        export_artifacts=[ExportArtifact(
            kind="docx", s3_key="k", download_url="u", size_bytes=1,
        )],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert len(out.chapters) == 6
    assert "discussion" in out.chapters


def test_chapter_draft_pending_edits_default_empty():
    from orchestrator.schemas.m5 import ChapterDraft
    c = ChapterDraft(name="intro", prose="hello world")
    assert c.pending_edits == []


def test_chapter_draft_accepts_pending_edits():
    from datetime import datetime, timezone
    from orchestrator.schemas.m5 import ChapterDraft
    from orchestrator.schemas.m5_editor import PendingEdit
    pe = PendingEdit(
        id="x", chapter_name="intro", from_offset=0, to_offset=5,
        old_text="hello", new_text="hi", source="paraphrase",
        pending_at=datetime.now(timezone.utc),
    )
    c = ChapterDraft(name="intro", prose="hello world", pending_edits=[pe])
    assert len(c.pending_edits) == 1
    assert c.pending_edits[0].source == "paraphrase"


def test_every_hand_copied_chapter_list_matches_the_canonical_order():
    # Three hand-maintained copies of the chapter list is how the six/five
    # split survived: the canonical order said six, the merge said five, and
    # each copy drifted on its own. This test is cheaper than a fourth copy.
    from typing import get_args
    from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER
    from orchestrator.schemas.m5 import ChapterName as M5Name
    from orchestrator.schemas.m5_editor import ChapterName as EditorName
    from api.app.routers.m5_editor import _VALID_CHAPTER_NAMES

    canonical = set(M5_CHAPTER_ORDER)
    assert set(get_args(M5Name)) == canonical
    assert set(get_args(EditorName)) == canonical
    assert _VALID_CHAPTER_NAMES == canonical
