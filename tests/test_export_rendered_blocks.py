"""What the results renderer emits has to survive the trip into Word.

Two properties, both invisible until the renderer started producing blocks that
actually reach an export:

  - Its sentinels are internal markup. `<!--dt-rendered:begin …-->` tells the
    coherence and similarity checkers "this table is computed, not typed"; the
    docx writer had no comment branch, so they printed as body text and the one
    sharing a line with the caption swallowed the caption with it.
  - A table screenshot is captioned ABOVE it and a figure BELOW it. Every
    Vietnamese thesis template says so and it is a supervisor's first-page check.
"""
import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))
pytest.importorskip("docx")

from docx import Document  # noqa: E402

from engine.utils.export_professional import export_docx_basic  # noqa: E402

# Byte-for-byte the shape _wrap() emits, closing sentinel included. It sits
# DIRECTLY under the source line with no blank line between them, and the writer
# joins consecutive non-blank lines into one paragraph — so a per-line comment
# skip still shipped "*Nguồn: …* <!--dt-rendered:end …-->" into Word. Only an
# end-to-end render caught that; keep the adjacency in the fixture.
_MD = """# Chương 4

<!--dt-rendered:begin kind=measurement_model sha=e3e425c7f9aa-->
**Bảng 4.1 — Mô hình đo lường**

| Khái niệm | CR |
|---|---|
| ATT | 0.911 |
*Nguồn: kết xuất từ kết quả phân tích đã lưu (DoThesis).*
<!--dt-rendered:end kind=measurement_model-->
"""

# Smallest valid 1x1 PNG — python-docx has to be able to measure it.
_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _png(path: Path) -> Path:
    path.write_bytes(_PNG)
    return path


def _picture_index(doc) -> int:
    return next(i for i, p in enumerate(doc.paragraphs)
                if p.runs and any("graphic" in r._r.xml for r in p.runs))


def test_sentinels_do_not_reach_the_docx(tmp_path):
    md, out = tmp_path / "c4.md", tmp_path / "c4.docx"
    md.write_text(_MD, encoding="utf-8")
    assert export_docx_basic(md, out)

    doc = Document(str(out))
    body = "\n".join(p.text for p in doc.paragraphs)
    assert "dt-rendered" not in body
    assert "<!--" not in body
    # The caption survives as its own paragraph, and the table still renders.
    assert any("Bảng 4.1" in p.text for p in doc.paragraphs)
    assert len(doc.tables) == 1


def test_table_image_caption_sits_above_the_picture(tmp_path):
    img = _png(tmp_path / "hinh-04.png")
    md, out = tmp_path / "c4.md", tmp_path / "c4.docx"
    md.write_text(f"# Chương 4\n\n![Bảng 4.1 — Mô hình đo lường]({img})\n", encoding="utf-8")
    assert export_docx_basic(md, out)

    doc = Document(str(out))
    caption = next(i for i, p in enumerate(doc.paragraphs) if "Bảng 4.1" in p.text)
    assert caption < _picture_index(doc), "a table caption goes above the table"


def test_figure_image_caption_stays_below(tmp_path):
    img = _png(tmp_path / "model.png")
    md, out = tmp_path / "c3.md", tmp_path / "c3.docx"
    md.write_text(f"# Chương 3\n\n![Hình 3.1. Mô hình nghiên cứu]({img})\n", encoding="utf-8")
    assert export_docx_basic(md, out)

    doc = Document(str(out))
    caption = next(i for i, p in enumerate(doc.paragraphs) if "Hình 3.1" in p.text)
    assert _picture_index(doc) < caption, "a figure caption goes below the figure"


def test_a_table_image_is_captioned_exactly_once(tmp_path):
    """The alt text becomes the caption. Emitting a bold caption line as well
    printed it twice, once directly above the other."""
    img = _png(tmp_path / "hinh-04.png")
    md, out = tmp_path / "c4.md", tmp_path / "c4.docx"
    md.write_text(f"# Chương 4\n\n![Bảng 4.1 — Mô hình đo lường]({img})\n", encoding="utf-8")
    assert export_docx_basic(md, out)

    doc = Document(str(out))
    assert sum("Bảng 4.1" in p.text for p in doc.paragraphs) == 1


# --- the production path ----------------------------------------------------
#
# export_docx() uses Pandoc whenever it is installed and only falls back to
# export_docx_basic when it isn't, so the tests above cover the FALLBACK. These
# cover what actually ships. Both bugs they guard were invisible to the basic
# writer and only appeared end-to-end through Pandoc.

def test_pandoc_export_keeps_the_screenshot_captioned_above_it(tmp_path):
    """The renderer's own output, through the exporter production uses.

    Pandoc merges an image into the paragraph that follows it unless a blank
    line separates them, which demotes the image to an inline and drops it out
    of figure layout; and a non-empty alt becomes a caption BELOW the figure,
    where a table caption does not belong.
    """
    pytest.importorskip("PIL")
    import shutil
    if not shutil.which("pandoc"):
        pytest.skip("pandoc not installed — export_docx falls back to the basic writer")

    import os
    from PIL import Image

    from engine.utils.export_professional import export_docx
    from orchestrator.tools.results_render import render_results_tables, weave

    shot = tmp_path / "hinh-04.png"
    # Noisy so the PNG is big enough to survive any downstream size floor.
    Image.frombytes("RGB", (600, 300), os.urandom(600 * 300 * 3)).save(shot)

    ar = {"measurement_model": [{"construct": "ATT", "items": [], "cronbach_alpha": 0.878,
                                 "composite_reliability": 0.911, "ave": 0.671}],
          "hypothesis_tests": [{"id": "H1", "path": "ATT → INT",
                                "numbers": {"beta": 0.257, "t": 7.49, "p": "<0.001"},
                                "decision": "supported"}],
          "source_figures": {"measurement_model": str(shot)}}
    woven = weave("Mở đầu.\n\n[[DT:measurement_model]]\n\nKết luận.",
                  render_results_tables(ar, "vi"), drop_llm_tables=True)

    md, out = tmp_path / "c4.md", tmp_path / "c4.docx"
    md.write_text("# Chương 4\n\n" + woven + "\n", encoding="utf-8")
    assert export_docx(md, out)

    doc = Document(str(out))
    body = "\n".join(p.text for p in doc.paragraphs)
    assert "dt-rendered" not in body and "<!--" not in body
    # The screenshot really is in the package, as a picture.
    assert len([r for r in doc.part.rels.values() if "image" in r.reltype]) == 1
    caption = next(i for i, p in enumerate(doc.paragraphs) if "Bảng 4.1" in p.text)
    assert caption < _picture_index(doc), "a table caption goes above the table"
    # The block with no screenshot is still a real Word table, not an image.
    assert len(doc.tables) == 1
    assert any("Bảng 4.3" in p.text for p in doc.paragraphs)
