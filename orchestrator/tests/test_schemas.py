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
    a = ExportArtifact(kind="docx", uri="s3://bucket/key", size_bytes=12345)
    out = M5Output(
        sections=[{"name": "Ch.1", "text": "..."}],
        export_artifacts=[a],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert out.export_artifacts[0].uri.startswith("s3://")


def test_m3_output_unconfirmed_partial_is_valid():
    """In-progress partials should validate even without paradigm-specific fields."""
    out = M3Output(
        paradigm="quantitative",
        design="PLS-SEM", tool="SmartPLS",
        sampling_strategy="convenience", target_sample_size=200,
        # No conceptual_model, no scale_items — but confirmed_at not set.
    )
    assert out.confirmed_at is None


def test_m3_output_quant_confirm_requires_artifacts():
    """Setting confirmed_at on a quant paradigm requires conceptual_model + scale_items."""
    with pytest.raises(ValidationError):
        M3Output(
            paradigm="quantitative",
            design="PLS-SEM", tool="SmartPLS",
            sampling_strategy="convenience", target_sample_size=200,
            confirmed_at=datetime.now(timezone.utc),
            # missing conceptual_model + scale_items
        )


def test_m3_output_quant_confirm_with_artifacts_validates():
    out = M3Output(
        paradigm="quantitative",
        design="PLS-SEM", tool="SmartPLS",
        sampling_strategy="convenience", target_sample_size=200,
        conceptual_model={"constructs": ["TL", "EE"], "paths": []},
        scale_items=[{"construct": "TL", "items": ["I1", "I2"]}],
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
        conceptual_model={"constructs": ["TL"], "paths": []},
        scale_items=[{"construct": "TL", "items": ["I1"]}],
        themes=[{"id": "t1", "theme": "Leadership style", "sub_themes": []}],
        interview_guide={"sections": [{"phase": "main", "questions": []}]},
        purposive_criteria=[{"criterion": "tenure >= 6 months"}],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert out.mixed_design_type == "sequential_explanatory"
