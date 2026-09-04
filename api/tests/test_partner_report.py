"""Partner endpoint = create project -> seed -> spawn headless Job -> await ->
presign (convergence spec §3). Heavy pieces (extraction, the subprocess itself,
S3) are monkeypatched; project/job/event rows are real (conftest Postgres).

The old service-layer tests are gone with the service: chapter selection, the
Discussion+Conclusion merge, seeding and the export step are now
partner_run's, and are covered by test_partner_run.py.
"""
from __future__ import annotations

import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.runtime import build_agent
from app import job_runner
from app.db import get_engine
from app.models import Job, JobEvent, Project
from app.routers import partner_report as router_mod

TOKEN = "test-partner-secret"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("PARTNER_API_TOKEN", TOKEN)
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path))  # workspace mirror target
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    from app.settings import reset_settings
    reset_settings()
    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api/v1")
    return TestClient(app)


def _post(client, *, token=TOKEN, depth="analysis_report", body=b"%PDF-1.4 fake",
          **extra):
    headers = {"X-Partner-Token": token} if token is not None else {}
    data = {"depth": depth, "title": "My Study", "language": "en", **extra}
    return client.post(
        "/api/v1/partner/report",
        headers=headers,
        files={"file": ("analysis.pdf", io.BytesIO(body), "application/pdf")},
        data=data,
    )


def _analysis_text(*a):
    return ("cronbach 0.9 ave 0.6 " + "0.1 " * 10, 3)


def test_missing_token_is_401(client):
    assert _post(client, token=None).status_code == 401


def test_wrong_token_is_401(client):
    assert _post(client, token="nope").status_code == 401


def test_empty_file_is_422(client):
    assert _post(client, body=b"").status_code == 422


def test_unextractable_file_is_422(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text", lambda b, f: ("", 0))
    r = _post(client)
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "no_extractable_text"


def test_non_analysis_pdf_is_422(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text",
                        lambda b, f: ("just an essay, no statistics", 2))
    r = _post(client)  # analysis_report includes "results" -> sniff applies
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "insufficient_m4_data"


def test_bad_depth_is_422(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    r = _post(client, depth="bogus")
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "bad_depth"


def test_bad_module_json_is_422(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    r = _post(client, m1="not json")
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "bad_module_json"


def test_bad_input_creates_no_rows(client, monkeypatch):
    """A 422 must fail BEFORE any row exists — an orphan project/job per bad
    upload is how a partner integration bug turns into unbounded table growth."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    assert _post(client, depth="bogus").status_code == 422
    with Session(get_engine()) as s:
        assert s.scalars(select(Project)).all() == []
        assert s.scalars(select(Job)).all() == []


class _FakeS3:
    def generate_presigned_url(self, op, Params=None, ExpiresIn=None):
        return f"https://signed.example/{Params['Key']}"


def _fake_spawn(db: Session, run: Job, params: dict) -> None:
    # Stand-in for the subprocess: mark done + write the job_done event the
    # real headless_entry would emit.
    run.status = "done"
    run.workdir = "/tmp/x"
    db.add(JobEvent(job_id=run.id, type="job_done",
                    meta_json={"sections": ["Chapter 5 — Conclusion"],
                               "chapters": ["intro", "results", "conclusion"],
                               "artifact_keys": {"pdf": "p/k.pdf",
                                                 "docx": "p/k.docx"}}))
    db.commit()


def test_happy_path_creates_project_job_and_presigns(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    r = _post(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pdf_url"].endswith("p/k.pdf")
    assert body["docx_url"].endswith("p/k.docx")
    assert body["pdf_key"] == "p/k.pdf"
    assert body["sections"] == ["Chapter 5 — Conclusion"]
    assert body["chapters"] == ["intro", "results", "conclusion"]
    assert body["pages"] == 3
    assert body["powered_by"] == "DoThesis"
    # The progress token is MINTED here and handed back — the caller no longer
    # supplies one (jobs.partner_token is UNIQUE under one shared secret).
    assert len(body["progress_token"]) >= 32

    with Session(get_engine()) as s:
        job = s.scalar(select(Job).where(Job.partner_token == body["progress_token"]))
        assert job is not None and job.mode == "partner" and job.status == "done"
        proj = s.get(Project, job.project_id)
        assert proj is not None  # a REAL project row — chat handoff is possible
        # the store was seeded before spawn
        from app.agent_state import DbProjectStateStore
        st = DbProjectStateStore(get_engine(), proj.id, "/tmp/x").load()
        assert st["contextStore"]["analysis_results"].startswith("cronbach")


def test_caller_supplied_progress_token_is_ignored(client, monkeypatch):
    """Partner auth is ONE global shared secret with no partner identity, so a
    caller-chosen token is a collision (500 on the UNIQUE index) and a read
    capability for anyone who guesses it. The form field is gone; a caller that
    still sends one gets a server-minted token instead of theirs."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    r = _post(client, progress_token="ptok-i-chose")
    assert r.status_code == 200, r.text
    assert r.json()["progress_token"] != "ptok-i-chose"
    with Session(get_engine()) as s:
        assert s.scalar(select(Job).where(Job.partner_token == "ptok-i-chose")) is None


def test_modules_are_seeded_from_the_payload(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    r = _post(client, m1=json.dumps({"research_questions": ["RQ1"]}),
              m3=json.dumps({"conceptual_model": "TR -> PI"}))
    assert r.status_code == 200, r.text
    with Session(get_engine()) as s:
        job = s.scalar(select(Job).where(Job.partner_token == r.json()["progress_token"]))
        from app.agent_state import DbProjectStateStore
        cs = DbProjectStateStore(get_engine(), job.project_id, "/tmp/x").load()["contextStore"]
    assert cs["research_questions"] == ["RQ1"]
    assert cs["conceptual_model"] == "TR -> PI"
    assert cs["research_title"] == "My Study"  # the typed title still wins


def test_upload_is_mirrored_into_the_workspace(client, monkeypatch, tmp_path):
    """Agent tools (read_file / parse_reference) open the raw upload off disk —
    seeding the text alone would leave the file the run was given unreachable."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    r = _post(client, body=b"%PDF-1.4 mirrored")
    assert r.status_code == 200, r.text
    with Session(get_engine()) as s:
        job = s.scalar(select(Job).where(Job.partner_token == r.json()["progress_token"]))
        pid = job.project_id
    from app.workspace import workspace_dir
    assert (workspace_dir(pid) / "uploads" / "analysis.pdf").read_bytes() == b"%PDF-1.4 mirrored"


def test_chapters_fallback_reports_the_resolved_chapters(client, monkeypatch):
    """The fallback for a job_done event without `chapters` falls back to
    `chapter_keys` (the resolved request). Task 2 deleted the merge, so —
    unlike before — the resolved request IS what got composed; there is no
    pre-/post-merge split left for the two branches to disagree on."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    def spawn_without_chapters(db, run, params):
        run.status = "done"
        db.add(JobEvent(job_id=run.id, type="job_done",
                        meta_json={"sections": ["Chapter 5 — Conclusion"],
                                   "artifact_keys": {"pdf": "p/k.pdf"}}))
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", spawn_without_chapters)
    r = _post(client, depth="analysis_report")
    assert r.status_code == 200, r.text
    assert r.json()["chapters"] == ["intro", "results", "conclusion"]


def test_done_run_with_no_sections_is_502_not_an_empty_200(client, monkeypatch):
    """run_partner_export raises rather than return nothing, so a `done` run with
    no sections is the plumbing failing. Defaulting to [] shipped a 200 with
    sections:[] and pdf_url:null — the hollow-report-shaped success the old
    engine refused with compose_failed."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    def spawn_without_job_done(db, run, params):
        run.status = "done"  # done, but the job_done event never landed
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", spawn_without_job_done)
    r = _post(client)
    assert r.status_code == 502
    assert r.json()["detail"]["error"]["code"] == "compose_failed"


def test_failed_run_is_502(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)

    def failing_spawn(db, run, params):
        run.status = "failed"
        run.error_text = "headless run failed: max_stalls after 3 turns"
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", failing_spawn)
    r = _post(client)
    assert r.status_code == 502
    assert r.json()["detail"]["error"]["code"] == "report_failed"


def test_needs_data_run_is_422_not_a_generic_502(client, monkeypatch):
    """The readiness gate's refusal must reach the partner as the SPECIFIC code
    the old service returned. `needs_data` names what to send next; a blanket
    report_failed just invites a retry of the same doomed payload. The gate runs
    in the subprocess, so the code rides out on the error event's meta_json.
    """
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)

    def needs_data_spawn(db, run, params):
        run.status = "failed"
        db.add(JobEvent(job_id=run.id, type="error",
                        text="missing required data: M1 — research questions",
                        meta_json={"code": "needs_data"}))
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", needs_data_spawn)
    r = _post(client)
    assert r.status_code == 422
    err = r.json()["detail"]["error"]
    assert err["code"] == "needs_data"
    assert "research questions" in err["message"]


def _async_return(value):
    async def _f(*a, **k):
        return value
    return _f


def test_progress_reads_job(client, monkeypatch):
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)

    def running_then_done(db, run, params):
        run.status = "running"
        run.phase = "M3"
        run.progress = 0.4
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", running_then_done)
    monkeypatch.setattr(router_mod, "_wait_for_job",
                        _async_return("failed"))  # don't actually wait 35min
    r = _post(client)
    assert r.status_code == 502  # the run never finished; we only want the token
    with Session(get_engine()) as s:
        token = s.scalar(select(Job.partner_token))

    r = client.post("/api/v1/partner/report/progress",
                    headers={"X-Partner-Token": TOKEN},
                    json={"progress_token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "processing" and body["phase"] == "M3"
    assert body["done"] == 2 and body["total"] == 5  # 0.4 * 5 modules

    r = client.post("/api/v1/partner/report/progress",
                    headers={"X-Partner-Token": TOKEN},
                    json={"progress_token": "unknown-token"})
    assert r.json()["status"] == "unknown"


def test_progress_reports_what_the_run_is_currently_doing(client, monkeypatch):
    """`current` was hardcoded None, so the field the old contract used to fill
    with the chapter being written became permanently dead — a silent
    breaking change on a documented response. The chapter titles are gone (the
    run is an agent working a roadmap, not a fixed compose loop), but the live
    activity IS available: headless_entry already emits one per tool call.
    A field this endpoint still advertises must carry the best truth it has.
    """
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)

    def running(db, run, params):
        run.status = "running"
        run.phase = "M2"
        run.progress = 0.2
        db.add(JobEvent(job_id=run.id, type="activity", text="tool: quick_sources"))
        db.add(JobEvent(job_id=run.id, type="activity", text="tool: research_scout"))
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", running)
    monkeypatch.setattr(router_mod, "_wait_for_job", _async_return("failed"))
    _post(client)
    with Session(get_engine()) as s:
        token = s.scalar(select(Job.partner_token))

    r = client.post("/api/v1/partner/report/progress",
                    headers={"X-Partner-Token": TOKEN},
                    json={"progress_token": token})
    # The LATEST activity, not the first — "what is it doing now".
    assert r.json()["current"] == "tool: research_scout"


def test_progress_requires_the_partner_token(client):
    r = client.post("/api/v1/partner/report/progress",
                    json={"progress_token": "whatever"})
    assert r.status_code == 401


class _FakeModel(BaseChatModel):
    """A model that cannot reach the network. build_agent(model=...) is the seam
    that keeps this test off the Ofox gateway — which is FUNDED, so a stray
    _default_model() here would bill real tokens on every CI run. Never invoked:
    the assertions read the bound tool list, they don't take a turn."""

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
        raise AssertionError("the inheritance test must never call a model")


def test_partner_runs_the_deep_agent_not_a_private_pipeline(tmp_path):
    """The POINT of the switch: partner had ZERO tools and ZERO skills because
    it ran its own straight-line pipeline. It inherits them structurally — not
    by being handed a list — by going through build_agent like every other
    surface. Pin each hop, because a shortcut at any one of them silently
    restores the third engine this task deleted.
    """
    import inspect

    from app import headless_entry
    from app.routers import partner_report

    # 1. the endpoint spawns a headless Job (no local compose loop)
    src = inspect.getsource(partner_report.create_partner_report)
    assert "job_runner.spawn_headless_run" in src
    assert "compose_sections" not in src  # composing here = a fourth engine

    # 2. the spawner launches the headless entrypoint
    assert '"app.headless_entry"' in inspect.getsource(job_runner.spawn_headless_run)

    # 3. which builds THE agent — every tool and skill comes from here
    assert "build_agent(" in inspect.getsource(headless_entry.main)

    # 4. and build_agent really does bind the tools this convergence added.
    import agent.runtime as runtime
    assert runtime.SKILLS_DIR.is_dir()

    # Off the COMPILED graph, not off the source text. `"research_scout" in
    # inspect.getsource(runtime)` — what this asserted before — is satisfied by
    # the import line at the top of the module, so it passed with the binding
    # commented out of the tool list entirely: it proved the string exists, never
    # that the tool is reachable. The report's real evidence was the bound tool
    # list read off the graph by hand; this is that check, committed.
    agent = build_agent(tmp_path, model=_FakeModel())
    bound = set(agent.nodes["tools"].bound.tools_by_name)

    # render_model_diagram (Task 6 — a swallowed hardcoded nvm path in the
    # deleted service) and research_scout (Task 7) are what this convergence
    # added; commit_slice is the only write path a headless run has.
    assert {"render_model_diagram", "research_scout", "commit_slice"} <= bound
    # The breadth IS the point of the switch — partner ran a straight-line
    # pipeline with zero tools. A number that only ever moves up.
    assert len(bound) >= 33, sorted(bound)


# ---------------------------------------------------------------------------
# Golden pin — the deleted pipeline's exact output.
#
# Before partner_report_service was removed, a differential harness ran BOTH
# engines over the same payload with only the leaves stubbed (compose_chapter =
# the LLM, run_export = the renderer, _extract_text, the S3 client) and diffed
# the response bytes. 7/7 shapes came back byte-identical. The old engine is
# gone, so the values it produced are pinned HERE instead: this is the only
# remaining evidence that the switch preserved the partner contract, and the
# only thing that will fail if a later change quietly moves it.
#
# One divergence was found and accepted deliberately (see the task report):
#   1. `progress_token` is new (server-minted; was a caller-supplied form field).
# A second divergence used to live here, about chapters=[...,"discussion"]
# keeping the Discussion title under the old conditional-merge behavior. Task 2
# deleted the merge entirely — `discussion` is retired as a canonical chapter
# name (M5_CHAPTER_ORDER collapsed to five) — so that divergence no longer
# applies: `conclusion` is now the one and only final chapter, always.
# ---------------------------------------------------------------------------

_GOLDEN = {
    ("analysis_report", "en"): {
        "chapters": ["intro", "results", "conclusion"],
        "sections": ["Chapter 1 — Introduction", "Chapter 4 — Results",
                     "Chapter 5 — Conclusions and Recommendations"],
    },
    ("analysis_report", "vi"): {
        "chapters": ["intro", "results", "conclusion"],
        "sections": ["Chương 1 — Giới thiệu", "Chương 4 — Kết quả",
                     "Chương 5 — Kết luận và Kiến nghị"],
    },
    ("full_thesis", "en"): {
        "chapters": ["intro", "lit_review", "methodology", "results", "conclusion"],
        "sections": ["Chapter 1 — Introduction", "Chapter 2 — Literature Review",
                     "Chapter 3 — Methodology", "Chapter 4 — Results",
                     "Chapter 5 — Conclusions and Recommendations"],
    },
}


@pytest.mark.parametrize("depth,language", sorted(_GOLDEN))
def test_output_matches_the_deleted_pipeline_golden(client, monkeypatch, depth, language):
    import orchestrator.tools.compose_export as ce
    from app.agent_state import DbProjectStateStore
    from app.partner_run import run_partner_export
    from app.workspace import workspace_dir

    class _Compose:
        @staticmethod
        def invoke(payload):
            return {"prose": f"PROSE[{payload['chapter_name']}]"}

    monkeypatch.setattr(ce, "compose_chapter", _Compose())
    monkeypatch.setattr("app.partner_run.run_export",
                        lambda *a, **k: [{"kind": "docx", "s3_key": "projects/FIXED/report.docx"},
                                         {"kind": "pdf", "s3_key": "projects/FIXED/report.pdf"}])
    monkeypatch.setattr(router_mod.prun, "_extract_text",
                        lambda b, f: ("Cronbach alpha 0.87 AVE 0.62 HTMT 0.71 "
                                      "R square 0.44 p value 0.001 beta 0.38", 3))
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    def _inline_run(db, run, params):
        # What headless_entry runs once the agent loop finishes: the SHARED
        # compose/export back half. The agent turn loop is what fills the store,
        # and the store is seeded here, so this pins the report contract.
        store = DbProjectStateStore(get_engine(), run.project_id,
                                    workspace_dir(run.project_id))
        out = run_partner_export(store, run.project_id, params)
        run.status = "done"
        db.add(JobEvent(job_id=run.id, type="job_done", meta_json=out))
        db.commit()

    monkeypatch.setattr(job_runner, "spawn_headless_run", _inline_run)

    # A payload complete enough to pass the export readiness gate. `_inline_run`
    # stands in for a FINISHED agent loop, so the store it exports from has to
    # look like one the run left behind — RQs and literature included. Seeding
    # them here rather than weakening the gate keeps this test about the report
    # contract (chapter keys, section titles, artifact keys) instead of quietly
    # re-asserting that ungated composition is allowed.
    r = _post(client, depth=depth, language=language,
              m1=json.dumps({"research_title": "Trust and Purchase Intention",
                             "objectives": "Examine how trust drives purchase intention.",
                             "research_questions": ["Does trust drive purchase intention?"]}),
              m2=json.dumps({"literature_sources": [
                  {"title": "Trust in e-commerce", "authors": ["Gefen"], "year": 2003}]}),
              m3=json.dumps({"conceptual_model": "TR -> PI"}))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chapters"] == _GOLDEN[(depth, language)]["chapters"]
    assert body["sections"] == _GOLDEN[(depth, language)]["sections"]
    assert body["pdf_key"] == "projects/FIXED/report.pdf"
    assert body["docx_key"] == "projects/FIXED/report.docx"
    assert body["pages"] == 3
    assert body["depth"] == depth


def _post_multi(client, docs, *, token=TOKEN, depth="analysis_report", **extra):
    """Post several files under the repeated `files` field, as a browser would."""
    headers = {"X-Partner-Token": token} if token is not None else {}
    data = {"depth": depth, "title": "My Study", "language": "en", **extra}
    files = [("files", (name, io.BytesIO(body), "application/pdf")) for name, body in docs]
    return client.post("/api/v1/partner/report", headers=headers, files=files, data=data)


def test_multiple_files_are_all_mirrored(client, monkeypatch, tmp_path):
    """A report is routinely built from an đề cương PLUS an SPSS output (and
    SmartPLS emits several exports). Every one has to reach the workspace, or
    the agent writes chapters 4+5 without the data it was given."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    r = _post_multi(client, [
        ("de-cuong.docx", b"%PDF-1.4 outline"),
        ("output-spss.pdf", b"%PDF-1.4 spss"),
        ("smartpls.pdf", b"%PDF-1.4 pls"),
    ])
    assert r.status_code == 200, r.text
    with Session(get_engine()) as s:
        job = s.scalar(select(Job).where(Job.partner_token == r.json()["progress_token"]))
        pid = job.project_id
    from app.workspace import workspace_dir
    up = workspace_dir(pid) / "uploads"
    assert (up / "de-cuong.docx").read_bytes() == b"%PDF-1.4 outline"
    assert (up / "output-spss.pdf").read_bytes() == b"%PDF-1.4 spss"
    assert (up / "smartpls.pdf").read_bytes() == b"%PDF-1.4 pls"


def test_same_named_files_do_not_overwrite_each_other(client, monkeypatch):
    """Two exports both called output.pdf must both survive — silently keeping
    one would drop half the analysis with no error anywhere."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    r = _post_multi(client, [("output.pdf", b"%PDF-1.4 first"), ("output.pdf", b"%PDF-1.4 second")])
    assert r.status_code == 200, r.text
    with Session(get_engine()) as s:
        job = s.scalar(select(Job).where(Job.partner_token == r.json()["progress_token"]))
        pid = job.project_id
    from app.workspace import workspace_dir
    up = workspace_dir(pid) / "uploads"
    assert (up / "output.pdf").read_bytes() == b"%PDF-1.4 first"
    assert (up / "output-2.pdf").read_bytes() == b"%PDF-1.4 second"


def test_directory_components_in_filenames_cannot_escape_the_workspace(client, monkeypatch):
    """A filename is attacker-controlled; ../ in it must not write outside uploads/."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    r = _post_multi(client, [("../../escaped.pdf", b"%PDF-1.4 evil")])
    assert r.status_code == 200, r.text
    with Session(get_engine()) as s:
        job = s.scalar(select(Job).where(Job.partner_token == r.json()["progress_token"]))
        pid = job.project_id
    from app.workspace import workspace_dir
    ws = workspace_dir(pid)
    assert (ws / "uploads" / "escaped.pdf").read_bytes() == b"%PDF-1.4 evil"
    assert not (ws.parent / "escaped.pdf").exists()


def test_legacy_single_file_field_still_works(client, monkeypatch):
    """Fillform deploys separately from this API — an older build still sending
    `file` must keep working through the rollout."""
    monkeypatch.setattr(router_mod.prun, "_extract_text", _analysis_text)
    monkeypatch.setattr(job_runner, "spawn_headless_run", _fake_spawn)
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    assert _post(client, body=b"%PDF-1.4 legacy").status_code == 200


def test_no_files_at_all_is_422(client):
    headers = {"X-Partner-Token": TOKEN}
    r = client.post("/api/v1/partner/report", headers=headers,
                    data={"depth": "analysis_report", "language": "en"})
    assert r.status_code == 422
