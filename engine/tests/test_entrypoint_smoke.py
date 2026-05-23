import json
import subprocess
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def env_with_s3(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("S3_BUCKET", "smoke-bucket")
    monkeypatch.setenv("S3_PREFIX", "opendraft/")
    monkeypatch.setenv("AWS_ACCESS_KEY", "x")
    monkeypatch.setenv("AWS_SECRET_KEY", "y")


@pytest.mark.skip("subprocess test — depends on real or stub S3 reachable from subprocess; covered by test_job_io")
def test_subprocess_writes_events_and_uploads(tmp_path: Path, env_with_s3):
    workdir = tmp_path / "job"
    workdir.mkdir()
    (workdir / "brief.json").write_text(json.dumps({
        "topic": "t", "academic_level": "master", "language": "en", "citation_style": "apa"
    }))

    fake_module = tmp_path / "draft_generator.py"
    fake_module.write_text(
        "def generate_draft(*, tracker, streamer, output_dir, **kw):\n"
        "    tracker.update_phase('research', progress_percent=10)\n"
        "    tracker.log_activity('found a thing', phase='research', agent='Scout')\n"
        "    (output_dir / 'exports').mkdir(parents=True, exist_ok=True)\n"
        "    (output_dir / 'exports' / 'draft.md').write_text('# T\\n')\n"
    )

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="smoke-bucket")

        proc = subprocess.run(
            [sys.executable, "-m", "engine",
             "--job-id", "00000000-0000-0000-0000-000000000001",
             "--paper-id", "00000000-0000-0000-0000-000000000002",
             "--user-id", "00000000-0000-0000-0000-000000000003",
             "--workdir", str(workdir),
             "--brief-json", str(workdir / "brief.json")],
            cwd=str(Path(__file__).resolve().parents[2]),
            env={**__import__("os").environ, "PYTHONPATH": str(tmp_path)},
            capture_output=True, text=True,
        )

    assert proc.returncode == 0, proc.stderr
    events = [json.loads(l) for l in (workdir / "events.jsonl").read_text().splitlines()]
    types = [e["type"] for e in events]
    assert "phase_progress" in types
    assert "activity" in types
    assert types[-1] == "job_done"
