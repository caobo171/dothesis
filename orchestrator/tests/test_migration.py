"""Verifies the orchestrator migration runs up/down/up cleanly."""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def alembic_env(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.chdir(REPO_ROOT / "api")
    return pg_url


def _alembic(args: list[str]) -> None:
    subprocess.run(["alembic", *args], check=True)


def test_migration_up_down_up_clean(alembic_env):
    # Start from a clean DB so the test is order-independent.
    _alembic(["downgrade", "base"])
    _alembic(["upgrade", "head"])
    eng = create_engine(alembic_env)
    insp = inspect(eng)
    for t in ("projects", "threads", "messages", "context_store"):
        assert t in insp.get_table_names(), f"missing table {t}"
    job_cols = {c["name"] for c in insp.get_columns("jobs")}
    for c in ("project_id", "thread_id", "mode", "langgraph_thread_id"):
        assert c in job_cols, f"jobs missing column {c}"

    # Downgrade to the revision directly before the orchestrator migration using
    # its explicit ID. Using -1 is fragile: if a newer migration sits on top of
    # 20260526_orch01 (e.g. 20260527_uploads01), downgrade -1 would only undo
    # that newer migration, leaving the orchestrator tables in place.
    _alembic(["downgrade", "cbab05df531a"])
    insp = inspect(eng)
    for t in ("projects", "threads", "messages", "context_store"):
        assert t not in insp.get_table_names(), f"{t} should be gone after downgrade"

    _alembic(["upgrade", "head"])  # re-up must be idempotent


def test_papers_backfill_into_projects(alembic_env):
    _alembic(["downgrade", "base"])
    eng = create_engine(alembic_env)
    # Upgrade to the revision directly before the orchestrator migration.
    # Using the explicit revision ID is more reliable than relative "-1" from base.
    _alembic(["upgrade", "cbab05df531a"])
    with eng.begin() as cx:
        cx.execute(text(
            "INSERT INTO users(id,email,username,password_hash) "
            "VALUES (gen_random_uuid(),'t@x','tester','x')"
        ))
        uid = cx.execute(text("SELECT id FROM users LIMIT 1")).scalar()
        cx.execute(text(
            "INSERT INTO papers(id,user_id,topic,academic_level,language,citation_style,model) "
            "VALUES (gen_random_uuid(), :uid, 'Test topic', 'master', 'en', 'apa', 'gemini')"
        ), {"uid": uid})

    _alembic(["upgrade", "head"])
    with eng.begin() as cx:
        n_projects = cx.execute(text("SELECT COUNT(*) FROM projects")).scalar()
        n_threads = cx.execute(text("SELECT COUNT(*) FROM threads")).scalar()
        n_ctx = cx.execute(text("SELECT COUNT(*) FROM context_store")).scalar()
    assert n_projects == 1
    assert n_threads == 1
    assert n_ctx == 1
