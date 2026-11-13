"""Run scenarios against the real agent and record what happened.

One scenario run = a fresh project directory seeded from the scenario, the
agent built exactly as chat builds it (build_agent with its real tools, skills
and middleware), an in-memory checkpointer, and each scripted student turn
driven through stream_turn. Only the model is chosen here: the real one from
env by default, or any chat model a caller passes (the offline tests pass the
scripted FakeChatModel).

What this deliberately does NOT include: chat_v3's per-turn doctor and its
honesty post-filters. Those patch the reply after the model has spoken. The
point of these evals is to see what the model does on its own, so a guard that
hides a regression in production cannot hide it here.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from agent.evals.checks import CheckResult, run_checks, tool_ok

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


# -- scenarios -------------------------------------------------------------

def load_scenarios(directory: Path = SCENARIOS_DIR) -> list[dict]:
    scenarios = []
    for path in sorted(directory.glob("*.json")):
        s = json.loads(path.read_text(encoding="utf-8"))
        s.setdefault("id", path.stem)
        if not s.get("turns") or not s.get("checks"):
            raise ValueError(f"{path.name}: a scenario needs turns and checks")
        scenarios.append(s)
    ids = [s["id"] for s in scenarios]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate scenario ids: {sorted(dupes)}")
    return scenarios


def select(scenarios: list[dict], cases: list[str] | None, tags: list[str] | None) -> list[dict]:
    out = scenarios
    if cases:
        unknown = set(cases) - {s["id"] for s in scenarios}
        if unknown:
            raise ValueError(f"unknown scenario(s): {sorted(unknown)}")
        out = [s for s in out if s["id"] in cases]
    if tags:
        out = [s for s in out if set(tags) & set(s.get("tags", []))]
    return out


def _merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def seed_project(project_dir: Path, seed: dict) -> None:
    """Write the scenario's starting state and workspace files."""
    from agent.state import ProjectStateStore, _empty_state  # noqa: PLC0415

    state = _merge(_empty_state(), seed.get("state") or {})
    ProjectStateStore(project_dir)._save(state)
    for rel, content in (seed.get("files") or {}).items():
        dest = project_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict):
            shutil.copyfile(REPO_ROOT / content["from"], dest)
        else:
            dest.write_text(content, encoding="utf-8")


# -- one run ---------------------------------------------------------------

async def _drive(agent: Any, store: Any, turns: list[str], thread_id: str) -> list[dict]:
    from agent.runtime import stream_turn  # noqa: PLC0415

    recorded = []
    for user_text in turns:
        before = store.load()
        started = time.monotonic()
        reply: list[str] = []
        tools: list[dict] = []
        pending: dict[str, list[dict]] = {}
        errors: list[str] = []
        usage = {"input_tokens": 0, "output_tokens": 0}
        served: set[str] = set()
        async for ev in stream_turn(agent, thread_id, user_text, store=store):
            kind = ev.get("type")
            if kind == "token":
                reply.append(ev.get("text") or "")
            elif kind == "tool_start":
                args = ev.get("args") or {}
                queue = pending.setdefault(ev["name"], [])
                # stream_turn announces each call twice: first from the
                # streamed chunk (args often still empty), then from the graph
                # update (full args). Fold the second into the first so a call
                # counts once and keeps its real arguments.
                twin = next((c for c in queue if not c["args"] or c["args"] == args), None)
                if twin is not None:
                    twin["args"] = twin["args"] or args
                    continue
                call = {"name": ev["name"], "args": args, "ok": False, "preview": ""}
                tools.append(call)
                queue.append(call)
            elif kind == "tool_end":
                queue = pending.get(ev["name"]) or []
                call = queue.pop(0) if queue else None
                if call is None:  # a result with no announced call; record it anyway
                    call = {"name": ev["name"], "args": {}, "ok": False, "preview": ""}
                    tools.append(call)
                call["preview"] = ev.get("preview") or ""
                call["ok"] = tool_ok(call["preview"])
            elif kind == "error":
                errors.append(ev.get("message") or "error")
            elif kind == "usage":
                usage["input_tokens"] += ev.get("input_tokens") or 0
                usage["output_tokens"] += ev.get("output_tokens") or 0
                if ev.get("model"):
                    served.add(ev["model"])
        for name, queue in pending.items():
            for call in queue:
                call["preview"] = "<no result recorded>"
        recorded.append({
            "user": user_text,
            "reply": "".join(reply),
            "tools": tools,
            "errors": errors,
            "usage": usage,
            "models_served": sorted(served),
            "seconds": round(time.monotonic() - started, 2),
            "state_before": before,
            "state_after": store.load(),
        })
    return recorded


def run_once(scenario: dict, model_factory: Callable[[], Any],
             workdir: Path | None = None) -> dict:
    """Run one scenario once. Returns the transcript plus check results."""
    from langgraph.checkpoint.memory import InMemorySaver  # noqa: PLC0415

    from agent.runtime import build_agent  # noqa: PLC0415
    from agent.state import ProjectStateStore  # noqa: PLC0415

    tmp = Path(tempfile.mkdtemp(prefix=f"dothesis-eval-{scenario['id']}-", dir=workdir))
    project_dir = tmp / "project"
    seed_project(project_dir, scenario.get("seed") or {})
    store = ProjectStateStore(project_dir)
    agent = build_agent(project_dir, model=model_factory(),
                        checkpointer=InMemorySaver(), store=store)
    started = time.monotonic()
    try:
        turns = asyncio.run(_drive(agent, store, scenario["turns"], f"eval-{scenario['id']}"))
        crash = None
    except Exception as e:  # a crash is a result, not a reason to stop the suite
        turns, crash = [], f"{type(e).__name__}: {e}"
    run = {"turns": turns, "crash": crash, "seconds": round(time.monotonic() - started, 2)}
    if crash:
        checks = [CheckResult("run", "crash", False, True, crash)]
    else:
        checks = run_checks(run, scenario["checks"])
    run["checks"] = [asdict(c) for c in checks]
    run["hard_fail"] = any(not c.passed and c.critical for c in checks)
    shutil.rmtree(tmp, ignore_errors=True)
    return run


# -- a suite ---------------------------------------------------------------

def summarize(scenario: dict, runs: list[dict]) -> dict:
    n = len(runs)
    passed = sum(1 for r in runs if not r["hard_fail"])
    per_check: dict[str, dict] = {}
    for r in runs:
        for c in r["checks"]:
            row = per_check.setdefault(c["id"], {"kind": c["kind"], "critical": c["critical"],
                                                 "passed": 0, "runs": 0, "failures": []})
            row["runs"] += 1
            if c["passed"]:
                row["passed"] += 1
            else:
                row["failures"].append(c["detail"])
    min_rate = scenario.get("min_pass_rate", 1.0)
    return {
        "id": scenario["id"],
        "title": scenario.get("title", ""),
        "incident": scenario.get("incident"),
        "tags": scenario.get("tags", []),
        "pass_rate": round(passed / n, 3) if n else 0.0,
        "min_pass_rate": min_rate,
        "ok": n > 0 and passed / n >= min_rate,
        "checks": per_check,
        "tokens": {
            "input": sum(t["usage"]["input_tokens"] for r in runs for t in r["turns"]),
            "output": sum(t["usage"]["output_tokens"] for r in runs for t in r["turns"]),
        },
        "seconds": round(sum(r["seconds"] for r in runs), 1),
    }


def fingerprint() -> dict:
    """What the agent was built from, so two reports can be compared fairly."""
    from agent.runtime import SYSTEM_PROMPT  # noqa: PLC0415

    skills = hashlib.sha256()
    for p in sorted((REPO_ROOT / "skills").rglob("*.md")):
        skills.update(p.relative_to(REPO_ROOT).as_posix().encode())
        skills.update(p.read_bytes())
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                                    capture_output=True, text=True).stdout.strip())
    except Exception:
        sha, dirty = "unknown", True
    return {
        "git_sha": sha,
        "git_dirty": dirty,
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:16],
        "skills_sha256": skills.hexdigest()[:16],
    }


def run_suite(scenarios: list[dict], model_factory: Callable[[], Any], *,
              repeat: int = 1, model_info: dict | None = None,
              on_run: Callable[[str, int, dict], None] | None = None) -> dict:
    report: dict = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": model_info or {},
        "build": fingerprint(),
        "repeat": repeat,
        "scenarios": [],
        "runs": {},
    }
    for s in scenarios:
        runs = []
        for i in range(repeat):
            run = run_once(s, model_factory)
            runs.append(run)
            if on_run:
                on_run(s["id"], i, run)
        report["scenarios"].append(summarize(s, runs))
        report["runs"][s["id"]] = runs
    report["ok"] = all(row["ok"] for row in report["scenarios"])
    return report


def write_report(report: dict, directory: Path = RESULTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def compare(report: dict, baseline: dict) -> list[dict]:
    """Per-scenario pass-rate change against an earlier report."""
    base = {row["id"]: row for row in baseline.get("scenarios", [])}
    rows = []
    for row in report["scenarios"]:
        old = base.get(row["id"])
        rows.append({
            "id": row["id"],
            "now": row["pass_rate"],
            "before": old["pass_rate"] if old else None,
            "regressed": bool(old) and row["pass_rate"] < old["pass_rate"],
        })
    return rows
