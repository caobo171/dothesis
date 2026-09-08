"""`python -m app.blog.content.cli <command>` — the content engine's only entry point.

    expand   axes/*.tsv                  -> candidates.tsv
    gate     candidates.tsv + DataForSEO -> gate-{axis}.tsv, measured or not
    plan     harvest + gate survivors    -> backlog.tsv
    write    backlog.tsv + the model     -> seed JSON + write-log.tsv
    qa       seed dir                    -> pass/fail report, exit 1 on any FAIL
    images   seed dir + the library      -> hero per seed, one picture per scene
    report   everything above            -> counts, volume, spend, shortfall

Run it through the arch wrapper: `cd api && ./run.sh python -m app.blog.content.cli ...`.

Every handler imports its module lazily so that a command needing `openai` or
`httpx` cannot break `--help` (or the QA gate) on a machine that has neither.
"""
from __future__ import annotations

import argparse
import os
import sys

from . import load_env


def _cmd_expand(args) -> int:
    from .expand import run  # noqa: PLC0415

    counts = run(axes_dir=args.axes, out_path=args.out)
    total = sum(counts.values())
    for axis in sorted(counts, key=lambda a: -counts[a]):
        print(f"  {axis:26} {counts[axis]:5d} candidates")
    print(f"  {'total':26} {total:5d} candidates")
    return 0


def _cmd_gate(args) -> int:
    load_env()
    from .gate import probe, run  # noqa: PLC0415

    if args.probe:
        result = probe()
        print("gate probe (Vietnam, vi, Google Ads search volume)")
        for keyword, volume in result["volumes"].items():
            shown = "no data" if volume is None else f"{volume:,}"
            print(f"  {keyword:24} {shown:>10}")
        print(f"  API cost ${result['cost_usd']:.4f}")
        return 0
    run(source=args.source, candidates_path=args.candidates, measured_path=args.file,
        out_dir=args.out_dir, limit=args.limit, fill_unmeasured=args.fill_unmeasured)
    return 0


def _cmd_plan(args) -> int:
    from .plan import run  # noqa: PLC0415

    run(harvest_path=args.harvest, candidates_path=args.candidates, gate_dir=args.gate_dir,
        exclusions_path=args.exclusions, out_path=args.out,
        index_path=(None if args.no_index_check else "__default__"),
        folds_path=args.folds)
    return 0


def _cmd_write(args) -> int:
    load_env()
    from .writer import run  # noqa: PLC0415

    summary = run(backlog_path=args.backlog, out_dir=args.out, limit=args.limit,
                  workers=args.workers, model=args.model, budget_usd=args.budget_usd,
                  dry_run=args.dry_run, force=args.force)
    return 0 if summary["failed"] == 0 else 1


def _cmd_qa(args) -> int:
    from .qa import main  # noqa: PLC0415

    # The flag is forwarded rather than reimplemented: `qa.main` is also the
    # entry point the skill shim calls with plain python3, so both routes must
    # take the same arguments and give the same verdict.
    argv = [args.seed_dir]
    if args.corpus:
        argv.append("--corpus")
    if args.known_slugs:
        argv += ["--known-slugs", args.known_slugs]
    return main(argv)


def _cmd_images(args) -> int:
    load_env()
    from .images import run  # noqa: PLC0415
    from .writer import default_out_dir  # noqa: PLC0415

    # `--quality` and BLOG_IMAGE_QUALITY are two spellings of one setting, so
    # the flag writes the variable rather than threading a second argument
    # through generate/resolve/run that would mean the same thing.
    if args.quality:
        os.environ["BLOG_IMAGE_QUALITY"] = args.quality

    stats = run(seed_dir=args.dir or default_out_dir(), do_assign=args.assign,
                do_generate=args.generate, force=args.force,
                use_gemini=args.gemini, dry_run=args.dry_run)
    # A missing key is a mapping bug worth an exit code: the seed points at a
    # scene nobody wrote a prompt for, and that post ships with no hero.
    return 1 if stats.missing else 0


def _cmd_report(args) -> int:
    from .report import run  # noqa: PLC0415

    run(backlog_path=args.backlog, seed_dir=args.seed_dir, log_path=args.log)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.blog.content.cli",
                                     description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("expand", help="cross axis units with their phrasing templates")
    p.add_argument("--axes", default=None, help="axes directory (default: docs/seo/topic-bank/axes)")
    p.add_argument("--out", default=None, help="candidates.tsv path")
    p.set_defaults(func=_cmd_expand)

    p = sub.add_parser("gate",
                       help="measure candidates and record what the source knows "
                            "(nothing is cut; volume sets priority order)")
    p.add_argument("--source", default="dataforseo", choices=("dataforseo", "tsv"))
    p.add_argument("--file", default=None, help="measured rows TSV, for --source tsv")
    p.add_argument("--candidates", default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--limit", type=int, default=None, help="measure only the first N candidates")
    p.add_argument("--probe", action="store_true",
                   help="measure five known head terms and print the cost, write nothing")
    # Deprecated 2026-09-08, kept so a committed script or doc that passes it
    # does not break. It asked for what the gate now does by default.
    p.add_argument("--fill-unmeasured", action="store_true",
                   help="deprecated no-op: an unmeasured candidate passes on its own")
    p.set_defaults(func=_cmd_gate)

    p = sub.add_parser("plan", help="merge harvest and gate survivors into backlog.tsv")
    p.add_argument("--harvest", default=None)
    p.add_argument("--candidates", default=None)
    p.add_argument("--gate-dir", default=None)
    p.add_argument("--exclusions", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--no-index-check", action="store_true",
                   help="do not subtract slugs already listed in docs/blog-index.md")
    p.add_argument("--folds", default=None,
                   help="category folds TSV (default: topic-bank/category-folds.tsv)")
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("write", help="write seed JSON for backlog rows")
    p.add_argument("--backlog", default=None)
    p.add_argument("--out", default=None, help="seed output directory")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--model", default=None)
    p.add_argument("--budget-usd", type=float, default=40.0)
    p.add_argument("--dry-run", action="store_true",
                   help="build every prompt and report the estimate, call nothing")
    p.add_argument("--force", action="store_true", help="rewrite rows whose seed exists")
    p.set_defaults(func=_cmd_write)

    p = sub.add_parser("qa", help="run the mechanical gate over a seed directory")
    p.add_argument("seed_dir")
    p.add_argument("--corpus", action="store_true",
                   help="also compare every body against every other and fail near duplicates")
    p.add_argument("--known-slugs", default=None,
                   help="file of slugs that internal links may point at, one per line")
    p.set_defaults(func=_cmd_qa)

    p = sub.add_parser("images",
                       help="point seeds at the shared illustration library and "
                            "fill the keys that have no picture yet")
    p.add_argument("--dir", default=None, help="seed directory (default: the write output dir)")
    p.add_argument("--assign", action="store_true",
                   help="give every seed a hero pointing at a library key")
    p.add_argument("--generate", action="store_true",
                   help="generate the keys that have no image yet, and only those")
    p.add_argument("--force", action="store_true",
                   help="regenerate keys that already have an image (once per run, not once per post)")
    p.add_argument("--gemini", action="store_true",
                   help="generate with gemini-2.5-flash-image instead of gpt-image-2")
    p.add_argument("--quality", default=None, choices=("low", "medium", "high"),
                   help="gpt-image-2 quality tier (default: medium)")
    p.add_argument("--dry-run", action="store_true",
                   help="report what is missing and what it would cost, write nothing")
    p.set_defaults(func=_cmd_images)

    p = sub.add_parser("report", help="counts, volume, spend and the shortfall against 1,000")
    p.add_argument("--backlog", default=None)
    p.add_argument("--seed-dir", default=None)
    p.add_argument("--log", default=None)
    p.set_defaults(func=_cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
