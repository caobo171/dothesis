"""Verifies the paper_uploads migration creates the right table."""
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

# parents[2]: orchestrator/tests -> orchestrator -> repo_root
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def alembic_env(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.chdir(REPO_ROOT / "api")
    return pg_url


def _alembic(args):
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True)


def test_paper_uploads_migration_up_down_up(alembic_env):
    _alembic(["downgrade", "base"])
    _alembic(["upgrade", "head"])
    eng = create_engine(alembic_env)
    insp = inspect(eng)
    assert "paper_uploads" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("paper_uploads")}
    for c in ("id", "project_id", "filename", "s3_uri", "size_bytes",
              "mime_type", "text_extracted_at", "text_extract_uri",
              "page_count", "uploaded_at"):
        assert c in cols, f"missing column {c}"

    # Downgrade to the revision BEFORE paper_uploads (explicit, not "-1", so this
    # stays correct as later migrations stack on top of head).
    _alembic(["downgrade", "20260526_orch01"])
    insp = inspect(eng)
    assert "paper_uploads" not in insp.get_table_names()

    _alembic(["upgrade", "head"])
