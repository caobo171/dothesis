"""F13 — screenshot / export output ingest.

These tests exercise the two parsers that turn a SmartPLS/SPSS results table
(export file OR screenshot) into {table_kind, rows} for the F8 sanity layer.

No test may hit a real vision/OCR model, a network call, or the filesystem:
the loader (`_load_bytes`) and the vision boundary (`_vision_read`) are the two
functions isolated for exactly this reason and are stubbed via monkeypatch.
Every tool is called through `.func(file=...)` — a model supplies a workspace
path, never bytes.
"""
import json

import agent.tools.output_parse as op
from agent.tools.output_parse import infer_table_kind


def _tools(tmp_path):
    # Workspace-bound parsers (gap 1a). The read functions are stubbed, so the
    # workspace-relative path just needs to resolve in-root (it does).
    return {t.name: t for t in op.make_parse_tools(tmp_path)}


def test_infer_table_kind():
    assert infer_table_kind(["Construct", "HTMT"]) == "htmt"
    assert infer_table_kind(["Item", "Outer loading"]) == "loadings"


def test_parse_html_htmt(tmp_path, monkeypatch):
    html = ("<table><tr><th>pair</th><th>HTMT</th></tr>"
            "<tr><td>BI-ATT</td><td>0.91</td></tr></table>").encode()
    # Stub the loader so the test never touches disk.
    monkeypatch.setattr(op, "_load_bytes", lambda f: html)
    out = json.loads(_tools(tmp_path)["parse_smartpls_export"].func(file="report.html"))
    assert out["table_kind"] == "htmt" and out["rows"][0]["value"] == 0.91


def test_vision_ok(tmp_path, monkeypatch):
    # Stub the vision boundary so no real Gemini call is made. A well-formed JSON
    # transcription flows straight through.
    monkeypatch.setattr(op, "_vision_read",
                        lambda f: '{"table_kind":"loadings","rows":[{"item":"X1","value":0.74}]}')
    out = json.loads(_tools(tmp_path)["parse_output_table"].func(file="shot.png"))
    assert out["table_kind"] == "loadings" and out["rows"][0]["value"] == 0.74


def test_vision_junk(tmp_path, monkeypatch):
    # A model that "couldn't read a table" must not be treated as a clean parse:
    # we surface an error or a needs_confirmation, never a fabricated table.
    monkeypatch.setattr(op, "_vision_read", lambda f: "the image is blurry")
    out = json.loads(_tools(tmp_path)["parse_output_table"].func(file="shot.png"))
    assert out.get("error") or out.get("needs_confirmation")


def test_export_feeds_check_thresholds(tmp_path, monkeypatch):
    # End-to-end: a real export -> parsed rows -> F8's check_thresholds. An HTMT of
    # 0.91 (>= 0.85) must trip the discriminant-validity flag.
    from agent.tools.stats import check_thresholds     # F8
    html = "<table><tr><th>pair</th><th>HTMT</th></tr><tr><td>BI-ATT</td><td>0.91</td></tr></table>".encode()
    monkeypatch.setattr(op, "_load_bytes", lambda f: html)
    parsed = json.loads(_tools(tmp_path)["parse_smartpls_export"].func(file="r.html"))
    flags = json.loads(check_thresholds.func(table_kind=parsed["table_kind"], rows=parsed["rows"]))
    assert any("discriminant" in f["issue"].lower() for f in flags["findings"])
