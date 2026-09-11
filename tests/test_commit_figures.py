"""source_figures must be resolved by code and contained in the workspace.

A path is the one piece of state a model supplies that a later step OPENS, so
it is resolved and containment-checked at the commit rather than trusted by the
renderer downstream.
"""
from agent.tools.state_tools import _resolve_source_figures


def _png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


def test_relative_path_resolves_under_the_workspace(tmp_path):
    png = _png(tmp_path / "uploads" / "r.docx.img" / "hinh-04.png")
    out = _resolve_source_figures(
        {"measurement_model": "uploads/r.docx.img/hinh-04.png"}, str(tmp_path))
    assert out == {"measurement_model": str(png)}


def test_escaping_path_is_dropped(tmp_path):
    assert _resolve_source_figures(
        {"measurement_model": "../../../etc/passwd"}, str(tmp_path)) == {}


def test_absolute_path_outside_the_workspace_is_dropped(tmp_path):
    assert _resolve_source_figures(
        {"measurement_model": "/etc/hosts"}, str(tmp_path)) == {}


def test_missing_file_is_dropped(tmp_path):
    assert _resolve_source_figures(
        {"measurement_model": "uploads/nope.png"}, str(tmp_path)) == {}


def test_no_project_dir_drops_everything(tmp_path):
    assert _resolve_source_figures({"measurement_model": "uploads/x.png"}, None) == {}


def test_junk_never_raises(tmp_path):
    assert _resolve_source_figures(None, str(tmp_path)) == {}
    assert _resolve_source_figures({"k": None}, str(tmp_path)) == {}
    assert _resolve_source_figures({"k": 7}, str(tmp_path)) == {}


def test_one_bad_path_does_not_drop_the_good_ones(tmp_path):
    png = _png(tmp_path / "uploads" / "r.img" / "hinh-01.png")
    out = _resolve_source_figures(
        {"measurement_model": "uploads/r.img/hinh-01.png",
         "structural_paths": "../outside.png"}, str(tmp_path))
    assert out == {"measurement_model": str(png)}
