"""The screenshots Chapter 4 embeds have to outlive the machine that made them.

They used to live only in `var/jobs/…`, recorded in Postgres as an absolute
path. That path is meaningless on any other machine and `var/jobs` does not
survive a redeploy — and losing it is silent, because `_figure_body` just falls
back to a rebuilt markdown table.
"""
import os

import pytest

from orchestrator.tools import figure_store
from orchestrator.tools.figure_store import (
    exists, figure_key, figure_uri, localize, put_figure,
)

PNG = b"\x89PNG\r\n\x1a\n-fake-bytes"


class _FakeS3:
    """Just enough of the boto3 client surface for this module."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts = 0
        self.gets = 0

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.puts += 1
        self.objects[(Bucket, Key)] = Body

    def head_object(self, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.objects:
            raise KeyError("404")

    def get_object(self, Bucket, Key):  # noqa: N803
        self.gets += 1
        return {"Body": _Body(self.objects[(Bucket, Key)])}


class _Body:
    def __init__(self, data): self._data = data
    def read(self): return self._data


@pytest.fixture
def s3(monkeypatch, tmp_path):
    fake = _FakeS3()
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setattr(figure_store, "_client", lambda: fake)
    monkeypatch.setattr(figure_store, "_cache_dir", lambda: tmp_path)
    return fake


def test_the_key_is_derivable_from_the_relpath_alone():
    """Nothing extra is stored to find the object again: the sidecar already
    records the workspace-relative path, and the project id is known."""
    assert figure_key("p1", "uploads/_Result.docx.img/hinh-09.png") == (
        "projects/p1/figures/uploads/_Result.docx.img/hinh-09.png")
    # Leading slashes and backslashes must not produce a second key shape for
    # the same figure.
    assert figure_key("p1", "/uploads/a.img/x.png") == figure_key("p1", "uploads/a.img/x.png")
    assert figure_key("p1", "uploads\\a.img\\x.png") == figure_key("p1", "uploads/a.img/x.png")


def test_a_figure_survives_the_round_trip(s3):
    uri = put_figure("p1", "uploads/a.img/x.png", PNG)
    assert uri == "s3://test-bucket/projects/p1/figures/uploads/a.img/x.png"
    assert exists("p1", "uploads/a.img/x.png")

    path = localize(uri)
    assert path and open(path, "rb").read() == PNG


def test_the_second_read_does_not_go_back_to_s3(s3):
    uri = put_figure("p1", "uploads/a.img/x.png", PNG)
    first = localize(uri)
    assert s3.gets == 1
    assert localize(uri) == first
    assert s3.gets == 1, "an export renders several figures; each must fetch once"


def test_two_projects_with_the_same_filename_do_not_collide(s3):
    a = put_figure("p1", "uploads/a.img/hinh-09.png", b"AAAA")
    b = put_figure("p2", "uploads/a.img/hinh-09.png", b"BBBB")
    assert a != b
    assert open(localize(a), "rb").read() == b"AAAA"
    assert open(localize(b), "rb").read() == b"BBBB"


def test_a_plain_path_still_resolves_to_itself(tmp_path):
    """Every row written before this module holds an absolute local path, and
    must keep rendering exactly as it did."""
    f = tmp_path / "hinh-09.png"
    f.write_bytes(PNG)
    assert localize(str(f)) == str(f)


def test_a_path_that_no_longer_exists_resolves_to_nothing(tmp_path):
    """Which is the silent failure this module exists to end — the caller then
    falls back to the rebuilt table rather than emitting a broken image."""
    assert localize(str(tmp_path / "gone.png")) is None


def test_no_s3_configured_is_a_normal_state(monkeypatch):
    """Dev and tests run without a bucket; the callers keep using the local
    mirror exactly as before rather than failing an upload."""
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.delenv("AWS_S3_BUCKET", raising=False)
    assert figure_uri("p1", "uploads/a.img/x.png") is None
    assert put_figure("p1", "uploads/a.img/x.png", PNG) is None
    assert exists("p1", "uploads/a.img/x.png") is False


def test_an_upload_failure_does_not_raise(s3, monkeypatch):
    """A figure is a mirror of something already stored — losing it must never
    fail the student's upload."""
    def boom(**_kw):
        raise RuntimeError("s3 down")
    monkeypatch.setattr(s3, "put_object", boom)
    assert put_figure("p1", "uploads/a.img/x.png", PNG) is None


def test_a_missing_object_degrades_instead_of_raising(s3):
    assert localize("s3://test-bucket/projects/p1/figures/nope.png") is None
    assert localize("s3://") is None
    assert localize("") is None
