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


def test_infer_table_kind():
    assert infer_table_kind(["Construct", "HTMT"]) == "htmt"
    assert infer_table_kind(["Item", "Outer loading"]) == "loadings"


def test_parse_html_htmt(monkeypatch):
    html = ("<table><tr><th>pair</th><th>HTMT</th></tr>"
            "<tr><td>BI-ATT</td><td>0.91</td></tr></table>").encode()
    # Stub the loader so the test never touches disk.
    monkeypatch.setattr(op, "_load_bytes", lambda f: html)
    out = json.loads(op.parse_smartpls_export.func(file="report.html"))
    assert out["table_kind"] == "htmt" and out["rows"][0]["value"] == 0.91


def test_vision_ok(monkeypatch):
    # Stub the vision boundary so no real Gemini call is made. A well-formed JSON
    # transcription flows straight through.
    monkeypatch.setattr(op, "_vision_read",
                        lambda f: '{"table_kind":"loadings","rows":[{"item":"X1","value":0.74}]}')
    out = json.loads(op.parse_output_table.func(file="shot.png"))
    assert out["table_kind"] == "loadings" and out["rows"][0]["value"] == 0.74


def test_vision_junk(monkeypatch):
    # A model that "couldn't read a table" must not be treated as a clean parse:
    # we surface an error or a needs_confirmation, never a fabricated table.
    monkeypatch.setattr(op, "_vision_read", lambda f: "the image is blurry")
    out = json.loads(op.parse_output_table.func(file="shot.png"))
    assert out.get("error") or out.get("needs_confirmation")
