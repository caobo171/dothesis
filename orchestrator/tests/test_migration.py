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


def test_projects_has_focus_and_module_status_columns(alembic_env):
    # PR #1 of the target architecture (brief §1.4) — `focus` and
    # `module_status` are added to projects. Pinning them here so a
    # future migration can't silently drop them; the columns are the
    # foundation PR #2 (router) and PR #4 (memory) build on.
    _alembic(["downgrade", "base"])
    _alembic(["upgrade", "head"])
    eng = create_engine(alembic_env)
    insp = inspect(eng)
    cols = {c["name"]: c for c in insp.get_columns("projects")}
    assert "focus" in cols, "projects.focus missing"
    assert cols["focus"]["nullable"] is True, (
        "projects.focus must be nullable so dual-write window works "
        "(callers fall back to current_module when NULL)"
    )
    assert "module_status" in cols, "projects.module_status missing"
    assert cols["module_status"]["nullable"] is False, (
        "projects.module_status is non-null with default '{}' — "
        "compute_status_map output writes here on every turn"
    )


def test_focus_backfilled_from_current_module(alembic_env):
    # Existing projects keep working: focus seeded from current_module so
    # the dual-write window sees consistent routing data even before PR #2
    # cuts callers over to focus.
    _alembic(["downgrade", "base"])
    eng = create_engine(alembic_env)
    _alembic(["upgrade", "20260530_target01"])
    with eng.begin() as cx:
        cx.execute(text(
            "INSERT INTO users(id,email,username,password_hash) "
            "VALUES (gen_random_uuid(),'t2@x','tester2','x')"
        ))
        uid = cx.execute(text("SELECT id FROM users LIMIT 1")).scalar()
        # current_module='M3' simulates a live project mid-flow.
        cx.execute(text(
            "INSERT INTO projects(id,user_id,name,current_module) "
            "VALUES (gen_random_uuid(), :uid, 'p', 'M3')"
        ), {"uid": uid})

    _alembic(["upgrade", "head"])
    with eng.begin() as cx:
        row = cx.execute(text(
            "SELECT focus, module_status FROM projects LIMIT 1"
        )).one()
    assert row.focus == "M3", "focus must be backfilled from current_module"
    # module_status defaults to '{}' — recomputed by compute_status_map on
    # the next turn rather than mirrored in SQL.
    assert row.module_status == {}


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
