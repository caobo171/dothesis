"""Partner E2E: the WHOLE stack, with a REAL subprocess.

Every other partner test stops at a seam. test_partner_report.py's `_fake_spawn`
writes `meta_json` straight into the DB — it never spawns anything, so the
monitor, events.jsonl and `python -m app.headless_entry` are all assumed.
test_headless_runner.py drives `run_headless` in-process — no router, no Job, no
subprocess. test_partner_report.py's inheritance test reads SOURCE TEXT. Between
them, three seams were only ever pinned structurally:

  1. router -> job_runner.spawn_headless_run -> `python -m app.headless_entry`
     -> build_agent -> run_headless -> run_partner_export
  2. events.jsonl -> _monitor -> _ingest_event -> JobEvent.meta_json -> the
     endpoint response / the progress poll. job_runner.py:221 keeps every key
     except type/phase/agent/text, which is the ONLY reason run_partner_export's
     sections/chapters/artifact_keys reach the partner at all.
  3. that `python -m app.headless_entry` BOOTS. Only `--help` was ever proven,
     which exercises argparse and nothing else.

This test crosses all three for real: a real Popen of a real interpreter, real
events.jsonl, the real _monitor task, real Job/JobEvent/Project/Export rows.

NO REAL LLM CALLS — and that is enforced, not hoped for. Two different brains
run here and only ONE of them is covered by the documented mock hook:
  - the AGENT's completions go through agent/runtime._default_model, which
    returns FakeChatModel under DOTHESIS_E2E_MOCK=1;
  - the COMPOSE back half (compose_chapter) goes through orchestrator/llm.py,
    which DOTHESIS_E2E_MOCK does NOT cover. On a funded gateway that is real
    money, so the sitecustomize shim below stubs it in the child, together with
    run_export (pandoc + a real S3 put_object) — and then POISONS both real
    model factories so a missed path raises instead of billing.
Everything between the argv and those leaves is production code.
"""
from __future__ import annotations

import io
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Export, Job, JobEvent
from app.routers import partner_report as router_mod

TOKEN = "e2e-partner-secret"

# The agent script's entry. It matches headless_entry.KICKOFF_PROMPT — the
# entrypoint's OWN prompt, not one this test supplies. That coupling is
# deliberate: reword KICKOFF_PROMPT and this fails rather than drifting.
KICKOFF_ENTRY = "Generate the complete work"


def _module_steps(module, writes):
    # One roadmap-module turn = 2 completions: the tool_calls step, then the
    # post-ToolMessage wrap-up (FakeChatModel indexes steps by AI-message count).
    return [
        {"response": f"Working on {module}.",
         "tool_calls": [{"name": "commit_slice",
                         "args": {"module": module, "writes": writes,
                                  "reason": "partner e2e fixture",
                                  "confirm_done": True}}]},
        {"response": f"{module} committed."},
    ]


# depth=analysis_report -> required_modules_for(...) == {"M4","M5"}: intro /
# discussion / conclusion are M5-owned, results is M4-owned, and M1 owns no
# chapter. A run that respects its profile therefore finishes on M4 + M5 alone —
# so that is what this fixture does. Not a shortcut; the contract.
FIXTURE = {"scenario": "partner-e2e", "entry": KICKOFF_ENTRY, "steps": [
    *_module_steps("M4", {"analysis_outline": "Reliability, validity, paths"}),
    *_module_steps("M5", {"final_sections": [{"title": "Intro", "prose": "p"}]}),
]}

# Injected into the SUBPROCESS via PYTHONPATH — Python auto-imports
# `sitecustomize` at interpreter startup. The argv is built by real product code
# (job_runner.spawn_headless_run), so the parent's monkeypatch has no reach into
# the child; short of faking the spawn — which is exactly what this test exists
# to stop doing — this is the only way in.
#
# It patches `m5_writing` BEFORE compose_export / partner_run are imported, so
# their module-level `from .m5_writing import compose_chapter / run_export` binds
# to the stub. Same two leaves the golden test stubs in-process.
#
# The marker file is the PROOF this ran. Without it, a shim that silently failed
# to load would leave the test passing against the real compose path — i.e. the
# no-spend claim would be unfalsifiable, which is the failure mode this whole
# task exists to avoid.
#
# `_run_export` also dumps the sections it was handed, because the response
# CANNOT distinguish a real compose from a padded one: compose_sections catches
# every compose_chapter exception and substitutes _fallback_section, which
# produces the SAME chapter titles. Asserting on `sections` titles alone passes
# with compose_chapter deleted outright (verified). The prose is the only
# evidence, and only run_export ever sees it.
_SITECUSTOMIZE = '''
import json
import os

_marker = os.getenv("DOTHESIS_E2E_SHIM_MARKER")
if _marker:
    from orchestrator.tools import m5_writing

    class _Compose:
        @staticmethod
        def invoke(payload):
            return {"prose": "PROSE[%s]" % payload["chapter_name"]}

    def _run_export(sections, project_id, references=None, language="en"):
        out = os.getenv("DOTHESIS_E2E_SECTIONS_OUT")
        if out:
            with open(out, "w") as fh:
                json.dump(sections, fh)
        return [
            {"kind": "docx", "s3_key": "projects/%s/exports/report.docx" % project_id,
             "size_bytes": 111},
            {"kind": "pdf", "s3_key": "projects/%s/exports/report.pdf" % project_id,
             "size_bytes": 222},
        ]

    m5_writing.compose_chapter = _Compose()
    m5_writing.run_export = _run_export

    # Belt and braces: the Ofox gateway has a real funded balance, so "no path
    # we thought of builds a real model" is not good enough. Make it impossible.
    def _forbidden(*a, **k):
        raise AssertionError(
            "partner E2E tried to build a REAL LLM client — this test must never "
            "reach a billed gateway")

    import agent.model_factory
    import orchestrator.llm
    agent.model_factory.make_model = _forbidden
    orchestrator.llm.get_orchestrator_llm = _forbidden

    with open(_marker, "w") as fh:
        fh.write("loaded")
'''


class _FakeS3:
    """Presigning is a boto3-local signature, not a seam this test owns — the
    endpoint's own suite covers it. Stubbed in the PARENT only."""

    def generate_presigned_url(self, op, Params=None, ExpiresIn=None):
        return f"https://signed.example/{Params['Key']}"


@pytest.fixture
def e2e(monkeypatch, tmp_path):
    """A client whose /partner/report really spawns `python -m app.headless_entry`."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "run.json").write_text(json.dumps(FIXTURE), encoding="utf-8")

    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    marker = tmp_path / "shim-loaded"
    sections_out = tmp_path / "composed-sections.json"

    monkeypatch.setenv("PARTNER_API_TOKEN", TOKEN)
    # One root for both processes: the router resolves workspace_dir() from it,
    # spawn_headless_run puts the workdir (params.json + events.jsonl) under it,
    # and the child resolves the SAME workspace off the same env var.
    monkeypatch.setenv("JOB_WORKDIR_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("S3_BUCKET", "e2e-bucket")
    # spawn_headless_run does os.environ.copy(), so everything set here reaches
    # the child — including the model guard and the shim.
    monkeypatch.setenv("DOTHESIS_E2E_MOCK", "1")
    monkeypatch.setenv("DOTHESIS_E2E_FIXTURES_DIR", str(fixtures))
    monkeypatch.setenv("DOTHESIS_E2E_SHIM_MARKER", str(marker))
    monkeypatch.setenv("DOTHESIS_E2E_SECTIONS_OUT", str(sections_out))
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join([str(shim), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    # Budgets that bound the TEST, not the fixture: the script needs 2 turns.
    monkeypatch.setenv("PARTNER_MAX_TURNS", "6")
    monkeypatch.setenv("PARTNER_WALL_CLOCK_S", "180")
    monkeypatch.setenv("PARTNER_REPORT_TIMEOUT_S", "240")

    from app.settings import reset_settings
    reset_settings()
    monkeypatch.setattr(router_mod, "s3_from_env", lambda: _FakeS3())

    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api/v1")
    with TestClient(app) as client:
        client.shim_marker = marker
        client.sections_out = sections_out
        yield client


_ANALYSIS = ("Cronbach alpha 0.87 AVE 0.62 HTMT 0.71 R square 0.44 "
             "p value 0.001 beta 0.38", 3)

_M1 = {"research_title": "Trust and Purchase Intention",
       "research_questions": ["Does trust drive purchase intention?"]}
_M2 = {"literature_sources": [{"title": "Trust in e-commerce",
                               "authors": ["Gefen"], "year": 2003}]}


def _post(client, **extra):
    data = {"depth": "analysis_report", "title": "Trust and Purchase Intention",
            "language": "en", **extra}
    return client.post(
        "/api/v1/partner/report",
        headers={"X-Partner-Token": TOKEN},
        files={"file": ("analysis.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        data=data,
    )


def _job_events(job_id):
    with Session(get_engine()) as s:
        return s.scalars(select(JobEvent).where(JobEvent.job_id == job_id)
                         .order_by(JobEvent.id)).all()


def _dump_run(job_id):
    """Everything needed to debug a child that died. The child's stderr reaches
    the pytest process's stderr, but events.jsonl is the contract."""
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        wd = job.workdir if job else None
        lines = [f"job.status={job.status!r} error_text={job.error_text!r}"] if job else []
    if wd:
        p = os.path.join(wd, "events.jsonl")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                lines += ["events.jsonl:"] + [ln.rstrip() for ln in f]
    return "\n".join(lines)


def _loaded_state(project_id):
    from app.agent_state import DbProjectStateStore
    from app.workspace import workspace_dir
    return DbProjectStateStore(get_engine(), project_id, workspace_dir(project_id)).load()


def test_partner_report_end_to_end_through_a_real_subprocess(e2e, monkeypatch):
    """seed -> REAL spawn -> real headless_entry -> real agent loop -> real
    run_partner_export -> events.jsonl -> _monitor -> JobEvent -> 200.

    The only fakes are the model/renderer LEAVES. If this passes, the argv, the
    module boot, the profile derivation, the event pipe, the meta_json
    passthrough at job_runner.py:221 and the response mapping are all real.
    """
    monkeypatch.setattr(router_mod.prun, "_extract_text", lambda b, f: _ANALYSIS)

    r = _post(e2e, m1=json.dumps(_M1), m2=json.dumps(_M2))

    with Session(get_engine()) as s:
        job = s.scalars(select(Job)).one()
        job_id, project_id = job.id, job.project_id
    assert r.status_code == 200, f"{r.text}\n{_dump_run(job_id)}"
    body = r.json()

    # The no-spend guarantee, proven rather than asserted: the child really did
    # load the shim, so compose_chapter was the stub and both real model
    # factories were poisoned for the whole run.
    assert e2e.shim_marker.exists(), "the subprocess never loaded the leaf shim"

    # --- seam 1: the run really executed the deep agent in another process ----
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        assert job.status == "done"
        assert job.pid and job.pid != os.getpid(), "no subprocess was spawned"
        assert job.mode == "partner"
    # The agent's OWN tool writes landed in Postgres from the child.
    st = _loaded_state(project_id)
    assert st["status"]["M4"] == "done" and st["status"]["M5"] == "done"
    assert st["contextStore"]["analysis_outline"] == "Reliability, validity, paths"
    # The seeded payload survived the whole run.
    assert st["contextStore"]["analysis_results"].startswith("Cronbach")
    # M2 stayed untouched: required_modules_for(analysis_report) == {M4, M5}, so
    # the run was never driven through a literature review nobody asked for.
    assert st["status"]["M2"] != "done"

    # --- seam 2: events.jsonl -> _monitor -> JobEvent.meta_json --------------
    events = _job_events(job_id)
    types = [e.type for e in events]
    assert "phase_progress" in types, types   # headless_entry's per-turn hook fired
    assert "job_done" in types, types
    done_ev = next(e for e in events if e.type == "job_done")
    # job_runner.py:221 keeps every key but type/phase/agent/text — the only
    # reason run_partner_export's return value reaches the partner at all.
    assert set(done_ev.meta_json) >= {"sections", "chapters", "artifact_keys"}
    assert done_ev.meta_json["artifact_keys"]["pdf"].endswith("report.pdf")
    # Written by the monitor off a phase_progress event, not by anyone's hand.
    assert job.progress == 1.0

    # --- seam 3 + the response contract --------------------------------------
    assert body["chapters"] == ["intro", "results", "discussion"]  # post-merge
    assert body["sections"] == ["Chapter 1 — Introduction", "Chapter 4 — Results",
                                "Chapter 5 — Conclusion"]
    assert body["pdf_url"].endswith("report.pdf")
    assert body["docx_url"].endswith("report.docx")
    assert body["pages"] == 3
    assert len(body["progress_token"]) >= 32

    # The chapters were really COMPOSED, not padded. compose_sections turns any
    # compose_chapter failure into _fallback_section, which emits the same titles
    # — so every assertion above this line also passes with compose_chapter
    # removed entirely (verified by deleting it: still green). Prose is the only
    # thing that tells the two apart, and run_export is the only place it is
    # visible, hence the dump. Without this, "the shared compose path ran" would
    # be exactly the kind of claim this task exists to stop making.
    composed = json.loads(e2e.sections_out.read_text())
    assert [s["title"] for s in composed] == body["sections"]
    assert all(s["prose"].startswith("PROSE[") for s in composed), composed

    # run_partner_export persisted the partner-scoped export rows.
    with Session(get_engine()) as s:
        kinds = {e.kind for e in s.scalars(
            select(Export).where(Export.project_id == project_id,
                                 Export.scope == "partner")).all()}
    assert kinds == {"pdf", "docx"}

    # The progress poll reads the same Job the monitor wrote — the token round
    # trip a partner actually makes, against a real run.
    p = e2e.post("/api/v1/partner/report/progress",
                 headers={"X-Partner-Token": TOKEN},
                 json={"progress_token": body["progress_token"]})
    assert p.status_code == 200
    assert p.json()["status"] == "done"
    # `current` comes from an activity event the child emitted per tool call.
    assert (p.json()["current"] or "").startswith("tool: ")


def test_analysis_report_without_literature_runs_to_done_then_is_refused(e2e, monkeypatch):
    """THE required_modules / export-gate question, settled: the gap is REAL.

    `required_modules_for(["intro","results","discussion","conclusion"])` is
    {"M4","M5"} — M2 is NOT required. partner_run.run_partner_export's comment
    claims the gate "is already required_modules-aware by construction — a
    chapter-specific check is owned by exactly the module required_modules_for
    derives from that chapter". That is true only of the CHAPTER-SCOPED checks.
    assess_export_readiness also has owner-ANY checks (research title, research
    questions, literature sources) which fire for EVERY chapter set, and no ANY
    check's module is ever in required_modules — M2 only gets there via
    lit_review, M1 via nothing at all.

    So a partner that omits `m2` gets a run that ends `done` (it did everything
    its profile asked) and is then REFUSED at export for work nobody required.
    The mitigation on record — "in practice the roadmap walks M1->M5 so M2
    populates" — is a hope about model behaviour, not a mechanism: it needs the
    model to exceed its own profile. This fixture is a model that does exactly
    what it was told, and the partner burns a full agent run for a 422.

    Pinned rather than fixed: the fix (require the ANY-checks' modules, or scope
    the gate to required_modules) is a behaviour change outside this task. The
    422 is at least honest — the alternative was billing for a fallback-padded
    report — but the run should never have been paid for.
    """
    monkeypatch.setattr(router_mod.prun, "_extract_text", lambda b, f: _ANALYSIS)

    # m1 supplied, m2 NOT — the shape required_modules_for's own docstring calls
    # typical ("payloads rarely carry literature").
    r = _post(e2e, m1=json.dumps(_M1))

    with Session(get_engine()) as s:
        job_id = s.scalars(select(Job.id)).one()
    assert r.status_code == 422, f"{r.status_code} {r.text}\n{_dump_run(job_id)}"
    err = r.json()["detail"]["error"]
    assert err["code"] == "needs_data"
    assert "M2 — literature sources" in err["message"]

    # The run reached `done` on its own terms first — the refusal is the GATE,
    # not a budget failure. Both modules it was actually asked for are done.
    with Session(get_engine()) as s:
        project_id = s.get(Job, job_id).project_id
    st = _loaded_state(project_id)
    assert st["status"]["M4"] == "done" and st["status"]["M5"] == "done"

    # ReportError.code rode out of the SUBPROCESS on the error event's meta_json
    # — the only path a stable code has to the endpoint (there is no in-process
    # exception to catch). Seam 2 on the refusal branch.
    err_ev = next(e for e in _job_events(job_id) if e.type == "error")
    assert err_ev.meta_json["code"] == "needs_data"
