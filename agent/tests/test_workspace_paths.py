"""Boundary hardening (gap 1a): the pure workspace path resolver."""
import os

import pytest

from agent.tools.workspace_paths import WorkspaceEscapeError, resolve_data_path


def test_relative_path_resolves_under_root(tmp_path):
    (tmp_path / "uploads").mkdir()
    r = resolve_data_path("uploads/data.csv", tmp_path)
    assert r == (tmp_path / "uploads" / "data.csv").resolve()
    assert os.path.isabs(str(r))


def test_absolute_path_inside_root_accepted(tmp_path):
    (tmp_path / "uploads").mkdir()
    p = tmp_path / "uploads" / "d.csv"
    assert resolve_data_path(str(p), tmp_path) == p.resolve()


def test_absolute_path_outside_root_rejected(tmp_path):
    with pytest.raises(WorkspaceEscapeError):
        resolve_data_path("/etc/passwd", tmp_path)


def test_dotdot_traversal_rejected(tmp_path):
    (tmp_path / "uploads").mkdir()
    with pytest.raises(WorkspaceEscapeError):
        resolve_data_path("uploads/../../secrets.txt", tmp_path)


def test_symlink_escape_rejected(tmp_path):
    (tmp_path / "uploads").mkdir()
    outside = tmp_path.parent / f"outside_{tmp_path.name}.csv"
    outside.write_text("secret")
    link = tmp_path / "uploads" / "link.csv"
    os.symlink(outside, link)
    with pytest.raises(WorkspaceEscapeError):
        resolve_data_path("uploads/link.csv", tmp_path)


def test_symlink_inside_root_accepted(tmp_path):
    (tmp_path / "uploads").mkdir()
    target = tmp_path / "uploads" / "real.csv"
    target.write_text("x")
    link = tmp_path / "uploads" / "alias.csv"
    os.symlink(target, link)
    assert resolve_data_path("uploads/alias.csv", tmp_path) == target.resolve()


def test_empty_or_none_rejected(tmp_path):
    for bad in ("", None):
        with pytest.raises(ValueError):
            resolve_data_path(bad, tmp_path)


def test_root_itself_and_nested_dirs_ok(tmp_path):
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    assert resolve_data_path("top.csv", tmp_path) == (tmp_path / "top.csv").resolve()
    assert resolve_data_path("a/b/c/deep.csv", tmp_path) == (tmp_path / "a/b/c/deep.csv").resolve()


def test_missing_file_inside_root_still_resolves(tmp_path):
    # resolver does NOT require existence (existence errors stay at _load_df)
    r = resolve_data_path("uploads/nope.csv", tmp_path)
    assert r == (tmp_path / "uploads" / "nope.csv").resolve()


def test_must_exist_flag(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_data_path("uploads/nope.csv", tmp_path, must_exist=True)
