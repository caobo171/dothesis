"""Agent behaviour evals against the real model.

    python -m agent.evals --list
    python -m agent.evals                       # every scenario, once
    python -m agent.evals --case save-title-commits --repeat 3
    python -m agent.evals --tag incident --compare agent/evals/results/<earlier>.json
    DOTHESIS_AGENT_MODEL=gemini-3-flash-preview DOTHESIS_MODEL_ROUTE=native python -m agent.evals

Reads the model from the same env as chat (DOTHESIS_MODEL_ROUTE,
DOTHESIS_AGENT_MODEL, ...; .env is loaded). Every run calls a paid model.
Exit code: 0 when every scenario meets its pass rate, 1 otherwise, 2 on a
regression against --compare.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent.evals import runner


def _print_run(scenario_id: str, i: int, run: dict) -> None:
    mark = "FAIL" if run["hard_fail"] else "pass"
    print(f"  {scenario_id} #{i + 1}: {mark} ({run['seconds']}s)", flush=True)
    for c in run["checks"]:
        if not c["passed"]:
            level = "critical" if c["critical"] else "soft"
            print(f"      x {c['id']} [{level}] {c['detail']}", flush=True)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(runner.REPO_ROOT / ".env")
    p = argparse.ArgumentParser(prog="python -m agent.evals", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", action="append", help="scenario id (repeatable)")
    p.add_argument("--tag", action="append", help="only scenarios with this tag (repeatable)")
    p.add_argument("--repeat", type=int, default=1, help="runs per scenario (default 1)")
    p.add_argument("--list", action="store_true", help="list scenarios and exit")
    p.add_argument("--compare", type=Path, help="earlier report to compare pass rates against")
    p.add_argument("--no-write", action="store_true", help="do not write a report file")
    args = p.parse_args(argv)

    scenarios = runner.select(runner.load_scenarios(), args.case, args.tag)
    if args.list:
        for s in scenarios:
            tags = ",".join(s.get("tags", []))
            print(f"{s['id']:<36} {tags:<22} {s.get('title', '')}")
        return 0
    if not scenarios:
        print("no scenarios selected", file=sys.stderr)
        return 1

    from agent.model_factory import make_model, spec_from_env  # noqa: PLC0415

    spec = spec_from_env()
    model_info = {"route": spec.route, "model": spec.model}
    print(f"model {spec.route}/{spec.model}, {len(scenarios)} scenario(s) x {args.repeat}",
          flush=True)
    report = runner.run_suite(scenarios, make_model, repeat=args.repeat,
                              model_info=model_info, on_run=_print_run)

    print()
    for row in report["scenarios"]:
        status = "ok  " if row["ok"] else "FAIL"
        print(f"{status} {row['id']:<36} pass {row['pass_rate']:.2f} "
              f"(need {row['min_pass_rate']:.2f})  {row['seconds']}s  "
              f"tokens {row['tokens']['input']}/{row['tokens']['output']}")

    exit_code = 0 if report["ok"] else 1
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        rows = runner.compare(report, baseline)
        report["compared_to"] = {"file": str(args.compare), "rows": rows}
        print(f"\ncompared to {args.compare.name} "
              f"({baseline.get('model', {}).get('model')}, {baseline.get('build', {}).get('git_sha')})")
        for r in rows:
            before = "new" if r["before"] is None else f"{r['before']:.2f}"
            flag = "  REGRESSED" if r["regressed"] else ""
            print(f"  {r['id']:<36} {before} -> {r['now']:.2f}{flag}")
        if any(r["regressed"] for r in rows):
            exit_code = 2
    if report["build"]["git_dirty"]:
        print("\nnote: uncommitted changes, so this report is provisional")
    if not args.no_write:
        print(f"\nreport: {runner.write_report(report)}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
