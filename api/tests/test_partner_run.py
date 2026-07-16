"""Partner-as-headless-client plumbing (spec §3): system user, store seeding
through commit_slice (the ONLY write path), and the post-run export step."""
import pytest
from sqlalchemy.orm import Session

from app.agent_state import DbProjectStateStore
from app.db import get_engine
from app.models import Project
from app.partner_run import (
    ReportError,
    ensure_partner_user,
    mint_partner_token,
    resolve_chapters,
    run_partner_export,
    seed_partner_store,
)


def _partner_project(tmp_path):
    engine = get_engine()
    with Session(engine) as s:
        u = ensure_partner_user(s)
        p = Project(user_id=u.id, name="Partner report", language="vi")
        s.add(p)
        s.commit()
        pid = p.id
    return DbProjectStateStore(engine, pid, tmp_path), pid


def test_ensure_partner_user_is_idempotent():
    with Session(get_engine()) as s:
        a = ensure_partner_user(s)
        b = ensure_partner_user(s)
        assert a.id == b.id and a.credit == 0


def test_resolve_chapters():
    assert resolve_chapters("analysis_report", None) == ["intro", "results",
                                                         "discussion", "conclusion"]
    assert resolve_chapters("full_thesis", None)[0] == "intro"
    assert resolve_chapters("ignored", ["results", "bogus"]) == ["results"]
    with pytest.raises(ReportError):
        resolve_chapters("bad", None)
    with pytest.raises(ReportError):
        resolve_chapters("analysis_report", ["bogus_only"])


def test_seed_lands_in_owned_slices(tmp_path):
    store, pid = _partner_project(tmp_path)
    seed_partner_store(
        store,
        analysis_text="Cronbach alpha .87, AVE 0.62",
        m1={"research_title": "Given title", "objectives": "Aim",
            "not_a_real_key": "dropped"},
        m3={"conceptual_model": "TR -> PI"},
        notes="steer this way", language="vi",
    )
    st = DbProjectStateStore(get_engine(), pid, tmp_path).load()  # fresh DB read
    cs = st["contextStore"]
    assert cs["research_title"] == "Given title"
    assert cs["objectives"] == "Aim"          # M1 framing key now owned + persisted
    assert cs["language"] == "vi"
    assert cs["user_context"] == "steer this way"
    assert cs["conceptual_model"] == "TR -> PI"
    assert cs["analysis_results"].startswith("Cronbach")
    assert "not_a_real_key" not in cs          # unowned keys are dropped, not smuggled
    # Seeding must not trip needs_review anywhere (M1->M4 order = downstream
    # of every commit is still locked).
    assert "needs_review" not in st["status"].values()


def test_run_partner_export_composes_and_persists(tmp_path, monkeypatch):
    store, pid = _partner_project(tmp_path)
    seed_partner_store(store, analysis_text="AVE 0.62", language="en")

    import app.partner_run as pr
    monkeypatch.setattr(pr, "compose_sections",
                        lambda *a, **k: [{"title": "Chapter 5 — Conclusion",
                                          "prose": "p"}])
    monkeypatch.setattr(pr, "run_export",
                        lambda *a, **k: [{"kind": "docx", "s3_key": "k.docx"},
                                         {"kind": "pdf", "s3_key": "k.pdf"}])
    out = run_partner_export(store, pid, {"depth": "analysis_report",
                                          "language": "en"})
    assert out["artifact_keys"] == {"docx": "k.docx", "pdf": "k.pdf"}
    assert out["sections"] == ["Chapter 5 — Conclusion"]
    # artifacts persisted to the shared exports rows (what the presign reads)
    from app.models import Export
    with Session(get_engine()) as s:
        rows = s.query(Export).filter_by(project_id=pid).all()
        assert {r.s3_key for r in rows} == {"k.docx", "k.pdf"}
        assert all(r.scope == "partner" for r in rows)


def test_run_partner_export_merges_conclusion_into_discussion(tmp_path, monkeypatch):
    """Discussion+Conclusion merge is an export ARGUMENT (Task 8), not a fork —
    partner must pass merge_conclusion=True or the old service's two merge sites
    (chapter-key drop + retitle) silently vanish with the pipeline."""
    store, pid = _partner_project(tmp_path)
    seed_partner_store(store, analysis_text="AVE 0.62", language="en")

    import app.partner_run as pr
    seen: dict = {}

    def _capture(context_store, chapters, language, **kwargs):
        seen.update(kwargs, chapters=chapters, language=language)
        return [{"title": "Chapter 5 — Conclusion", "prose": "p"}]

    monkeypatch.setattr(pr, "compose_sections", _capture)
    monkeypatch.setattr(pr, "run_export", lambda *a, **k: [])
    run_partner_export(store, pid, {"depth": "analysis_report", "language": "en"})
    assert seen["merge_conclusion"] is True


def test_run_partner_export_raises_when_compose_yields_nothing(tmp_path, monkeypatch):
    """A hollow report is worse than an error (spec §1): no sections = a clean
    failure code, never an empty DOCX handed to the partner."""
    store, pid = _partner_project(tmp_path)
    seed_partner_store(store, analysis_text="AVE 0.62", language="en")

    import app.partner_run as pr
    monkeypatch.setattr(pr, "compose_sections", lambda *a, **k: [])
    monkeypatch.setattr(pr, "run_export", lambda *a, **k: [])
    with pytest.raises(ReportError) as e:
        run_partner_export(store, pid, {"depth": "analysis_report"})
    assert e.value.code == "compose_failed"


def test_mint_partner_token_is_unique_and_server_side():
    """Task 9 made jobs.partner_token UNIQUE while the router still accepted a
    CALLER-supplied value under one shared partner secret — two callers picking
    the same string would collide at insert. Tokens are minted here instead."""
    tokens = {mint_partner_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(t) >= 32 for t in tokens)


def test_spawn_headless_run_mints_the_token_on_the_job_row(tmp_path, monkeypatch):
    """The spawner is the floor: whatever the router does, a headless run leaves
    with a unique server-minted token, so the UNIQUE index can't be tripped by
    two callers sharing the one partner secret."""
    from app import job_runner
    from app.models import Job

    store, pid = _partner_project(tmp_path)
    monkeypatch.setattr(job_runner, "get_settings",
                        lambda: type("S", (), {
                            "job_workdir_root": tmp_path, "aws_region": "r",
                            "s3_bucket": "b", "s3_prefix": "p",
                            "aws_access_key": "k", "aws_secret_key": "s",
                            "gemini_api_key": None, "openai_api_key": None,
                            "anthropic_api_key": None,
                        })())
    monkeypatch.setattr(job_runner.subprocess, "Popen",
                        lambda *a, **k: type("P", (), {"pid": 4242})())
    monkeypatch.setattr(job_runner, "start_monitor", lambda _id: None)

    with Session(get_engine()) as s:
        run = Job(project_id=pid, mode="partner", status="queued")
        s.add(run)
        s.commit()
        job_runner.spawn_headless_run(s, run, {"depth": "analysis_report"})
        assert run.partner_token and len(run.partner_token) >= 32
        assert run.pid == 4242 and run.status == "running"

        # A caller that already holds a token keeps it — this is a floor, not
        # an override (a re-spawn must not invalidate a token already handed out).
        run2 = Job(project_id=pid, mode="partner", status="queued",
                   partner_token="pre-minted-elsewhere")
        s.add(run2)
        s.commit()
        job_runner.spawn_headless_run(s, run2, {})
        assert run2.partner_token == "pre-minted-elsewhere"


def test_pdf_looks_like_analysis():
    """Moved verbatim from partner_report_service — the ingest gate that stops
    a proposal PDF from being tabulated as if it were SmartPLS output."""
    from app.partner_run import pdf_looks_like_analysis

    assert pdf_looks_like_analysis(
        "Cronbach's alpha 0.87 composite reliability 0.91 AVE 0.62 "
        "HTMT 0.71 R square 0.44 p value 0.001"
    )
    assert not pdf_looks_like_analysis("This proposal explores customer loyalty.")
