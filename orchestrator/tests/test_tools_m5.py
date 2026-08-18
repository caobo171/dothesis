from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.tools.m5_writing import (
    chapters_from_final_sections,
    compile_bibliography, compile_pdf, compose_section, export_docx, format_citations, validate_draft,
)


def test_chapters_from_final_sections_maps_canonical_names():
    out = chapters_from_final_sections([
        {"chapter_name": "intro", "title": "Chapter 1 — Introduction", "prose": "A"},
        {"title": "Chapter 2 — Literature Review", "body": "B"},   # title reverse-lookup + body key
        {"title": "Chương 3 — Phương pháp nghiên cứu", "prose": "C"},  # Vietnamese title
        {"title": "References", "prose": "D"},  # not a chapter — dropped
        {"title": "Chapter 4 — Results", "prose": "   "},  # empty prose — dropped
    ])
    assert out["intro"]["prose"] == "A"
    assert out["lit_review"]["prose"] == "B"
    assert out["methodology"]["prose"] == "C"
    assert "References" not in out and "results" not in out
    assert set(out) == {"intro", "lit_review", "methodology"}
    assert out["intro"] == {"name": "intro", "prose": "A"}


def test_chapters_from_final_sections_empty():
    assert chapters_from_final_sections([]) == {}
    assert chapters_from_final_sections(None) == {}


def test_compose_section_uses_engine_compose(monkeypatch):
    fake_compose = MagicMock(return_value="Chapter 2: Literature Review draft...")
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._compose_section_via_engine", fake_compose
    )
    out = compose_section.invoke({
        "section_name": "lit_review",
        "context_store": {
            "m1_topic": {"research_title": "X"},
            "m2_literature": {"research_gaps": [{"description": "..."}]},
        },
    })
    assert "Chapter" in out
    fake_compose.assert_called_once()


def test_validate_draft_returns_ok_when_no_issues(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing._validate_via_engine",
        lambda text: {"issues": [], "score": 0.95},
    )
    out = validate_draft.invoke({"text": "This is the draft."})
    assert out["score"] == 0.95
    assert out["issues"] == []


def test_compile_pdf_writes_artifact(tmp_path, monkeypatch):
    # SP6: compile_pdf now requires project_id and uploads to S3; mock s3 + engine.
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")

    captured = {}
    def fake_compile(sections, output_path, **kw):
        captured["sections"] = sections
        captured["output_path"] = output_path
        Path(output_path).write_bytes(b"%PDF-1.4 fake")
        return output_path
    monkeypatch.setattr(m5_writing, "_compile_pdf_via_engine", fake_compile)
    monkeypatch.setenv("ORCHESTRATOR_SCRATCH", str(tmp_path))

    out = compile_pdf.invoke({
        "sections": [{"name": "Ch.1", "text": "..."}],
        "project_id": "proj-test",
    })
    # SP6: returns {s3_key, size_bytes} dict — not a plain string
    assert out["s3_key"].startswith("projects/proj-test/exports/thesis-")
    assert out["s3_key"].endswith(".pdf")
    assert isinstance(out["size_bytes"], int)
    assert fake_s3.put_object.call_count == 1


def test_export_docx_writes_artifact(tmp_path, monkeypatch):
    # SP6: export_docx now requires project_id and uploads to S3; mock s3 + engine.
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")

    def fake_docx(sections, output_path, **kw):
        Path(output_path).write_bytes(b"PK\x03\x04 docx fake")
        return output_path
    monkeypatch.setattr(m5_writing, "_export_docx_via_engine", fake_docx)
    monkeypatch.setenv("ORCHESTRATOR_SCRATCH", str(tmp_path))

    out = export_docx.invoke({
        "sections": [{"name": "Ch.1", "text": "..."}],
        "project_id": "proj-test",
    })
    # SP6: returns {s3_key, size_bytes} dict — not a plain string
    assert out["s3_key"].startswith("projects/proj-test/exports/thesis-")
    assert out["s3_key"].endswith(".docx")
    assert isinstance(out["size_bytes"], int)
    assert fake_s3.put_object.call_count == 1


def test_format_citations_apa(monkeypatch):
    fake = MagicMock()
    fake.compile.return_value = "Wang, X. (2011). Title."
    monkeypatch.setattr(
        "orchestrator.tools.m5_writing.CitationCompiler", lambda style: fake
    )
    out = format_citations.invoke({
        "items": [{"author": "Wang", "year": 2011, "title": "Title"}],
        "style": "apa7",
    })
    assert "Wang" in out


def test_s3_from_env_returns_boto3_client(monkeypatch):
    """The factory should return a boto3 S3 client built from env vars."""
    from orchestrator.tools.m5_writing import s3_from_env
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY", "fake-key")
    monkeypatch.setenv("AWS_SECRET_KEY", "fake-secret")
    client = s3_from_env()
    assert hasattr(client, "put_object")
    assert hasattr(client, "generate_presigned_url")


def test_upload_to_s3_writes_correct_key_and_deletes_local(tmp_path, monkeypatch):
    """_upload_to_s3 uploads to projects/{id}/exports/{filename} and deletes local file."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")

    local = tmp_path / "thesis-abc123.docx"
    local.write_bytes(b"fake docx content")

    # _upload_to_s3 now returns (s3_key, size_bytes) tuple — unpack both.
    s3_key, size_bytes = m5_writing._upload_to_s3(
        str(local), project_id="proj-xyz", kind="docx", filename="thesis-abc123.docx",
    )
    assert s3_key == "projects/proj-xyz/exports/thesis-abc123.docx"
    assert size_bytes == len(b"fake docx content")
    call = fake_s3.put_object.call_args
    assert call.kwargs["Bucket"] == "test-bucket"
    assert call.kwargs["Key"] == "projects/proj-xyz/exports/thesis-abc123.docx"
    assert call.kwargs["ContentType"].startswith("application/vnd.openxmlformats")
    assert call.kwargs["Body"] == b"fake docx content"
    assert not local.exists()  # local file deleted


def test_upload_to_s3_pdf_content_type(tmp_path, monkeypatch):
    """PDF gets the right content type."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")

    local = tmp_path / "thesis-x.pdf"
    local.write_bytes(b"%PDF-1.4")
    m5_writing._upload_to_s3(str(local), "p", "pdf", "thesis-x.pdf")
    assert fake_s3.put_object.call_args.kwargs["ContentType"] == "application/pdf"


def test_compile_pdf_uploads_to_s3_and_returns_key(monkeypatch):
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")

    def fake_compile_via_engine(sections, output_path, **kw):
        Path(output_path).write_bytes(b"%PDF-1.4\nfake")
        return output_path
    monkeypatch.setattr(m5_writing, "_compile_pdf_via_engine", fake_compile_via_engine)

    # compile_pdf now returns {s3_key, size_bytes} dict — not a plain string.
    result = m5_writing.compile_pdf.invoke({
        "sections": [{"name": "intro", "text": "x"}],
        "project_id": "proj-xyz",
    })
    assert result["s3_key"].startswith("projects/proj-xyz/exports/thesis-")
    assert result["s3_key"].endswith(".pdf")
    assert result["size_bytes"] == len(b"%PDF-1.4\nfake")
    assert fake_s3.put_object.call_count == 1


def test_export_docx_uploads_to_s3_and_returns_key(monkeypatch):
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_s3 = MagicMock()
    monkeypatch.setattr(m5_writing, "s3_from_env", lambda: fake_s3)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")

    def fake_export_via_engine(sections, output_path, **kw):
        Path(output_path).write_bytes(b"PK\x03\x04 fake docx")
        return output_path
    monkeypatch.setattr(m5_writing, "_export_docx_via_engine", fake_export_via_engine)

    # export_docx now returns {s3_key, size_bytes} dict — not a plain string.
    result = m5_writing.export_docx.invoke({
        "sections": [{"name": "intro", "text": "x"}],
        "project_id": "proj-xyz",
    })
    assert result["s3_key"].startswith("projects/proj-xyz/exports/thesis-")
    assert result["s3_key"].endswith(".docx")
    assert result["size_bytes"] == len(b"PK\x03\x04 fake docx")


def test_compile_pdf_raises_without_project_id():
    from orchestrator.tools.m5_writing import compile_pdf
    with pytest.raises(ValueError, match="project_id"):
        compile_pdf.invoke({"sections": [], "project_id": ""})


def test_export_docx_raises_without_project_id():
    from orchestrator.tools.m5_writing import export_docx
    with pytest.raises(ValueError, match="project_id"):
        export_docx.invoke({"sections": [], "project_id": ""})


def test_validate_citations_matches_pool():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "Bass (1990) found... Later researchers confirmed (Avolio et al., 2009) that..."
    references = [
        {"author": "Bass", "year": 1990, "title": "Leadership"},
        {"author": "Avolio et al.", "year": 2009, "title": "Trans. leadership"},
    ]
    cited, uncited = validate_citations(prose, references)
    # The regex matches "(Author, Year)" — "Bass (1990)" is NOT in that shape;
    # only "(Avolio et al., 2009)" matches.
    assert "Avolio et al., 2009" in cited
    assert uncited == []


def test_validate_citations_flags_uncited():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "Some studies (Smith, 2023) claim X. Others (Bass, 1990) agree."
    references = [
        {"author": "Bass", "year": 1990, "title": "Leadership"},
    ]
    cited, uncited = validate_citations(prose, references)
    assert cited == ["Bass, 1990"]
    assert uncited == ["Smith, 2023"]


def test_convert_cite_pills_to_apa():
    from orchestrator.tools.m5_writing import _convert_cite_pills
    prose = ("hành vi {{cite: Davis 1989 | Perceived Usefulness | "
             "https://doi.org/10.2307/249040}}. Also {{cite: Nguyen et al. 2021 | T | http://x}} "
             "and {{cite: Hair & Ringle, 2019 | T | http://y}}.")
    out = _convert_cite_pills(prose)
    assert "{{cite" not in out and "doi.org" not in out and "http://" not in out
    assert "(Davis, 1989)" in out
    assert "(Nguyen et al., 2021)" in out
    assert "(Hair & Ringle, 2019)" in out


def test_convert_cite_pills_variants():
    from orchestrator.tools.m5_writing import _convert_cite_pills
    assert _convert_cite_pills("x {{cite: WHO 2020}} y") == "x (WHO, 2020) y"        # label-only
    assert _convert_cite_pills("x {{cite: Jeong 2025 | Title}} y") == "x (Jeong, 2025) y"  # 2-field
    assert _convert_cite_pills("x {{cite: Some Org | R | http://z}} y") == "x (Some Org) y"  # no year
    assert _convert_cite_pills("no pills here") == "no pills here"                    # idempotent-noop


def test_sanitize_prose_strips_raw_pill_markup():
    from orchestrator.tools.m5_writing import sanitize_prose
    out = sanitize_prose("thực tế {{cite: Davis 1989 | Long Title | https://doi.org/10.2307/249040}}.")
    assert "{{cite" not in out and "|" not in out
    assert "(Davis, 1989)" in out


def test_sanitize_inserts_blank_before_glued_list():
    from orchestrator.tools.m5_writing import sanitize_prose
    # lead-in paragraph directly above list items (no blank line) — markdown
    # needs the separator or pandoc renders "- " markers as one run-on paragraph.
    src = ("Nghiên cứu có các câu hỏi sau:\n"
           "- **RQ1**: một\n- **RQ2**: hai\n- **RQ3**: ba\nĐoạn kế tiếp.")
    out = sanitize_prose(src).split("\n")
    assert out[0] == "Nghiên cứu có các câu hỏi sau:"
    assert out[1] == "", "expected a blank line inserted before the list"
    assert [l for l in out if l.startswith("- ")] == [
        "- **RQ1**: một", "- **RQ2**: hai", "- **RQ3**: ba"]
    # no blank line inserted BETWEEN consecutive items
    assert "\n\n- **RQ2**" not in sanitize_prose(src)


def test_sanitize_blank_before_list_noop_when_already_separated():
    from orchestrator.tools.m5_writing import sanitize_prose
    src = "Lead:\n\n- a\n- b\n"
    # already has the blank line — must not add a second one
    assert "Lead:\n\n- a" in sanitize_prose(src)
    assert "Lead:\n\n\n- a" not in sanitize_prose(src)


def test_generate_scale_items_falls_back_to_conceptual_model(monkeypatch):
    # No instrument at all (headless/partner) → derive the construct list from
    # the conceptual_model node labels so the methodology still ships a scale.
    import orchestrator.tools.m3_design as m3
    captured = {}

    class _FakeTool:
        def invoke(self, payload):
            captured["constructs"] = payload["constructs"]
            return {c: [{"text": f"{c} item {i}"} for i in range(payload["n"])]
                    for c in payload["constructs"]}

    monkeypatch.setattr(m3, "suggest_scale_items_batch", _FakeTool())
    from orchestrator.tools.m5_writing import _generate_scale_items
    cm = {"nodes": [{"id": "PU", "label": "Perceived Usefulness"},
                    {"id": "BI", "label": "Behavioral Intention"}]}
    out = _generate_scale_items(None, "vi", conceptual_model=cm)
    assert captured["constructs"] == ["Perceived Usefulness", "Behavioral Intention"]
    assert [r["construct"] for r in out] == ["Perceived Usefulness", "Behavioral Intention"]
    assert all(len(r["items"]) == 4 for r in out)


def test_generate_scale_items_empty_without_model_or_instrument():
    from orchestrator.tools.m5_writing import _generate_scale_items
    assert _generate_scale_items(None, "vi") == []
    assert _generate_scale_items(None, "vi", conceptual_model={"nodes": []}) == []


def test_scale_item_helpers_tolerate_legacy_string_model():
    from orchestrator.tools.m5_writing import (
        _collect_construct_labels,
        _derive_scale_items,
    )

    # Historical interactive projects stored this field as free-form prose.
    assert _derive_scale_items("PU -> BI", None) == []
    assert _collect_construct_labels("PU -> BI", None) == []


def test_scale_item_helpers_parse_legacy_json_string_model():
    from orchestrator.tools.m5_writing import _derive_scale_items

    model = '{"nodes":[{"id":"PU","label":"Hữu ích","questions":["PU1"]}]}'
    assert _derive_scale_items(model, None) == [
        {"construct": "Hữu ích", "items": ["PU1"]}
    ]


def test_final_scrubber_removes_unresolved_dt_tokens():
    from orchestrator.tools.m5_writing import _scrub_internal_markers

    prose = "Trước khi phân tích:\n\n[[DT:data_cleaning]]\n\nNội dung tiếp."
    cleaned = _scrub_internal_markers(prose)
    assert "[[DT:" not in cleaned
    assert "Trước khi phân tích" in cleaned
    assert "Nội dung tiếp" in cleaned


def test_export_safety_net_adds_model_to_stored_methodology(monkeypatch):
    import orchestrator.tools.m5_writing as M

    monkeypatch.setattr(
        M, "_ensure_model_diagram",
        lambda prose, cm, language: prose + f"\n\nMODEL:{len(cm['nodes'])}:{language}",
    )
    sections = [{"chapter_name": "methodology", "title": "Chương 3",
                 "prose": "Phương pháp đã lưu."}]
    cs = {"m3_design": {"conceptual_model": {"nodes": [{"id": "A"}], "edges": []}}}
    out = M._ensure_export_model_diagrams(sections, cs, "vi")
    assert "MODEL:1:vi" in out[0]["prose"]
    assert sections[0]["prose"] == "Phương pháp đã lưu."


def test_pillow_model_fallback_creates_real_png():
    import re
    from pathlib import Path
    from orchestrator.tools.m5_writing import _pillow_model_figure

    cm = {
        "nodes": [
            {"id": "PB", "label": "Lợi ích", "type": "independent"},
            {"id": "BI", "label": "Ý định", "type": "dependent"},
        ],
        "edges": [{"source": "PB", "target": "BI", "hypothesis": "H1"}],
    }
    markdown = _pillow_model_figure(cm, "vi")
    match = re.search(r"!\[[^]]+\]\(([^)]+\.png)\)", markdown or "")
    assert match and Path(match.group(1)).exists()
    assert Path(match.group(1)).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_pillow_model_fallback_supports_sequential_outcome_chain():
    """Four predictors -> awareness -> intention must still produce an image."""
    import re
    from pathlib import Path
    from orchestrator.tools.m5_writing import _pillow_model_figure

    cm = {
        "nodes": [
            *[{"id": node_id, "label": node_id, "type": "independent"}
              for node_id in ("DS", "EX", "IN", "SU")],
            {"id": "AW", "label": "Nhận thức", "type": "dependent"},
            {"id": "INT", "label": "Ý định", "type": "dependent"},
        ],
        "edges": [
            *[{"source": node_id, "target": "AW", "hypothesis": f"H{i}"}
              for i, node_id in enumerate(("DS", "EX", "IN", "SU"), 1)],
            {"source": "AW", "target": "INT", "hypothesis": "H5"},
        ],
    }
    markdown = _pillow_model_figure(cm, "vi")
    match = re.search(r"!\[[^]]+\]\(([^)]+\.png)\)", markdown or "")
    assert match and Path(match.group(1)).exists()
    assert Path(match.group(1)).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_validate_citations_empty_prose():
    from orchestrator.tools.m5_writing import validate_citations
    cited, uncited = validate_citations("", [])
    assert cited == []
    assert uncited == []


def test_validate_citations_deduplicates():
    from orchestrator.tools.m5_writing import validate_citations
    prose = "(Bass, 1990) said X. Later (Bass, 1990) also said Y."
    references = [{"author": "Bass", "year": 1990}]
    cited, uncited = validate_citations(prose, references)
    assert cited == ["Bass, 1990"]  # de-duplicated


def test_compile_bibliography_formats_references():
    from orchestrator.tools.m5_writing import compile_bibliography
    refs = [
        {"author": "Bass", "year": 1990, "title": "Transformational leadership"},
        {"author": "Avolio et al.", "year": 2009, "title": "Authentic leadership"},
    ]
    out = compile_bibliography.invoke({"references": refs, "citation_style": "apa7"})
    assert "Bass" in out
    assert "1990" in out
    assert "Avolio" in out


def test_compile_bibliography_empty_references():
    from orchestrator.tools.m5_writing import compile_bibliography
    out = compile_bibliography.invoke({"references": [], "citation_style": "apa7"})
    assert "No references" in out


def test_compose_chapter_returns_chapter_draft_shape(monkeypatch):
    """compose_chapter calls the LLM with a chapter prompt + returns ChapterDraft dict."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        "# Introduction\n\nThis is a draft intro citing (Bass, 1990).\n"
    )
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    refs = [{"author": "Bass", "year": 1990, "title": "Leadership"}]
    out = m5_writing.compose_chapter.invoke({
        "chapter_name": "intro",
        "paradigm": "quantitative",
        "context_slice": {
            "research_title": "Leadership and Engagement",
            "field": "Management", "paradigm": "quantitative",
            "research_type": "quantitative",
            "objectives": ["O1"], "research_questions": ["RQ1"],
            "target_population": "SME employees", "scope": "VN, 2026",
        },
        "references": refs,
        "citation_style": "apa7",
        "language": "en",
    })
    assert out["name"] == "intro"
    assert out["prose"].startswith("# Introduction")
    assert "Bass, 1990" in out["citations_used"]
    assert out["uncited_warnings"] == []


def test_compose_chapter_flags_uncited(monkeypatch):
    """When the LLM cites a reference NOT in the pool, it's flagged."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        "Some studies (Smith, 2023) suggest X. Others (Bass, 1990) agree.\n"
    )
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    refs = [{"author": "Bass", "year": 1990}]
    out = m5_writing.compose_chapter.invoke({
        "chapter_name": "intro",
        "paradigm": "quantitative",
        "context_slice": {"research_title": "x", "objectives": []},
        "references": refs,
        "citation_style": "apa7", "language": "en",
    })
    assert "Bass, 1990" in out["citations_used"]
    assert "Smith, 2023" in out["uncited_warnings"]
    # Shipped behavior (m5_writing._strip_uncited_citations): the uncited citation
    # is STRIPPED from the prose (which renders verbatim) and surfaced only in the
    # returned uncited_warnings metadata — never injected back into the prose.
    assert "Smith" not in out["prose"] and "(Bass, 1990)" in out["prose"]


def test_compose_chapter_falls_back_on_llm_error(monkeypatch):
    """compose_chapter survives an LLM exception with a placeholder prose."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = RuntimeError("API down")
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    out = m5_writing.compose_chapter.invoke({
        "chapter_name": "intro",
        "paradigm": "quantitative",
        "context_slice": {"research_title": "x", "objectives": []},
        "references": [],
        "citation_style": "apa7", "language": "en",
    })
    assert out["name"] == "intro"
    assert "Composition failed" in out["prose"] or "[Composition failed" in out["prose"]


def test_rewrite_chapter_returns_new_draft(monkeypatch):
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Less formal intro version here.\n"
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    out = m5_writing.rewrite_chapter.invoke({
        "chapter_name": "intro",
        "current_prose": "# Introduction\n\nFormal intro.",
        "instruction": "rewrite to be less formal",
        "context_slice": {"research_title": "x", "objectives": []},
        "references": [],
        "language": "en",
    })
    assert out["name"] == "intro"
    assert "Less formal" in out["prose"]


def test_rewrite_chapter_falls_back_on_llm_error(monkeypatch):
    """If the LLM errors, return the original prose unchanged (don't lose work)."""
    from orchestrator.tools import m5_writing
    from unittest.mock import MagicMock

    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = RuntimeError("API down")
    monkeypatch.setattr(m5_writing, "_get_llm", lambda: fake_llm)

    original = "# Original prose"
    out = m5_writing.rewrite_chapter.invoke({
        "chapter_name": "intro",
        "current_prose": original,
        "instruction": "any",
        "context_slice": {"research_title": "x", "objectives": []},
        "references": [], "language": "en",
    })
    assert out["prose"] == original  # unchanged on failure
