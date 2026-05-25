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
    out = M3Output(
        paradigm="qualitative", design="thematic_analysis", tool="manual",
        sampling_strategy="purposive", target_sample_size=12,
    )
    assert out.conceptual_model is None
    assert out.thematic_framework is None  # optional


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
