"""backlog.tsv + the model -> seed JSON, gated in process, logged per row.

Resumable by design: one file per row, named from the row's priority and slug,
and a row whose file exists is skipped. That makes the run interruptible, which
matters more than throughput when a thousand posts are involved.

Each row gets at most two calls. The first writes the draft; if QA fails, the
second gets the failure list and repairs it. A second failure lands in
`rejected/` and the run continues, because one bad row must never stop the
batch. Read `rejected/` after every run: three rejects sharing a failure means
the prompt is wrong, not the model.
"""
from __future__ import annotations

import csv
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from . import repo_root
from .plan import read_backlog
from .prompts import build_prompt, build_repair_prompt
from .qa import check_post

LOG_COLUMNS = ("slug", "status", "attempts", "prompt_tokens", "output_tokens",
               "usd", "seconds", "failures")

STATUS_OK = "ok"
STATUS_REPAIRED = "repaired"
STATUS_REJECTED = "rejected"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def default_out_dir() -> str:
    return os.path.join(repo_root(), "api", "data", "blog-seeds", "vi", "posts")


def default_backlog_path() -> str:
    return os.path.join(repo_root(), "docs", "seo", "topic-bank", "backlog.tsv")


def seed_filename(row) -> str:
    return f"{row.priority:04d}-{row.slug}.json"


def parse_model_json(text: str) -> dict:
    """The model returns a json object. Tolerate a code fence around it."""
    cleaned = _FENCE_RE.sub("", (text or "").strip())
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("model returned json that is not an object")
    return data


def seed_from(row, produced: dict) -> dict:
    """Model output plus the pipeline's own fields.

    The pipeline fields are written from the backlog row, never from the model.
    A model that drifts on the slug or the category would otherwise corrupt the
    corpus in a way no reader would notice until the links broke.
    """
    return {
        "schema": "dothesis-blog-seed/1",
        "title": (produced.get("title") or "").strip(),
        "slug": row.slug,
        "locale": "vi",
        "meta_title": (produced.get("meta_title") or "").strip(),
        "meta_description": (produced.get("meta_description") or "").strip(),
        "focus_keyword": row.focus_keyword,
        "secondary_keywords": row.secondary_keywords,
        "focus_keyword_volume": row.search_volume,
        "excerpt": (produced.get("excerpt") or "").strip(),
        "category": row.category,
        "tags": [t for t in (produced.get("tags") or []) if isinstance(t, str)],
        "archetype": row.archetype,
        "family": row.family,
        "source_batch": "blog-content-engine",
        "gate_status": row.gate_status,
        "sibling_slugs": row.sibling_slugs,
        "images": [],
        "body": produced.get("body") or "",
    }


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)  # a killed run never leaves a half-written seed behind


class _Log:
    """write-log.tsv, appended under a lock so parallel workers do not interleave."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8", newline="") as fh:
                csv.writer(fh, delimiter="\t", lineterminator="\n").writerow(LOG_COLUMNS)

    def append(self, **row) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8", newline="") as fh:
            csv.writer(fh, delimiter="\t", lineterminator="\n").writerow(
                [row.get(c, "") for c in LOG_COLUMNS])


def run(backlog_path: str | None = None, out_dir: str | None = None,
        limit: int | None = None, workers: int = 6, model: str | None = None,
        budget_usd: float = 40.0, dry_run: bool = False, force: bool = False,
        client=None, log_path: str | None = None,
        skills_dir: str | None = None) -> dict:
    backlog_path = backlog_path or default_backlog_path()
    out_dir = out_dir or default_out_dir()
    rows = read_backlog(backlog_path)
    titles = {r.slug: r.focus_keyword for r in rows}
    known = {r.slug for r in rows}
    rejected_dir = os.path.join(out_dir, "rejected")
    log_path = log_path or os.path.join(os.path.dirname(os.path.abspath(out_dir)),
                                        "write-log.tsv")

    todo = []
    skipped = 0
    for row in rows:
        if os.path.isfile(os.path.join(out_dir, seed_filename(row))) and not force:
            skipped += 1
            continue
        todo.append(row)
        if limit and len(todo) >= limit:
            break

    if dry_run:
        prompts = [build_prompt(r, titles, skills_dir) for r in todo]
        chars = sum(len(p) for p in prompts)
        # ~3 characters per token for mixed Vietnamese and markdown, and about
        # 3,500 output tokens for a 2,000-word post. An estimate, printed as one.
        est_in = chars // 3
        est_out = 3500 * len(todo)
        from .llm import usd_for  # noqa: PLC0415

        summary = {"planned": len(todo), "skipped": skipped, "written": 0, "repaired": 0,
                   "rejected": 0, "errors": 0, "failed": 0, "usd": 0.0,
                   "estimated_usd": usd_for(est_in, est_out), "stopped_on_budget": False}
        print(f"write --dry-run: {len(todo)} rows to write, {skipped} already on disk")
        print(f"      prompt is {len(prompts[0]) if prompts else 0:,} chars for the first row")
        print(f"      estimated ${summary['estimated_usd']:.2f} at "
              f"{est_in:,} in / {est_out:,} out tokens")
        return summary

    if client is None:
        from .llm import LunaClient  # noqa: PLC0415 — openai stays off the qa import path

        client = LunaClient(model=model)

    log = _Log(log_path)
    state = {"usd": 0.0, "written": 0, "repaired": 0, "rejected": 0, "errors": 0,
             "stopped_on_budget": False}
    lock = threading.Lock()

    def budget_left() -> bool:
        with lock:
            if state["usd"] >= budget_usd:
                state["stopped_on_budget"] = True
                return False
            return True

    def write_one(row) -> None:
        attempts = 0
        spent = 0.0
        seconds = 0.0
        prompt_tokens = output_tokens = 0
        produced: dict = {}
        failures: list[str] = []
        try:
            prompt = build_prompt(row, titles, skills_dir)
            for attempt in range(2):
                completion = client.complete_json(prompt)
                attempts += 1
                spent += completion.usd
                seconds += completion.seconds
                prompt_tokens += completion.prompt_tokens
                output_tokens += completion.output_tokens
                produced = parse_model_json(completion.text)
                seed = seed_from(row, produced)
                failures, _warns, _stats = check_post(seed, known)
                if not failures:
                    _write_json(os.path.join(out_dir, seed_filename(row)), seed)
                    with lock:
                        state["usd"] += spent
                        if attempt == 0:
                            state["written"] += 1
                        else:
                            state["repaired"] += 1
                    log.append(slug=row.slug,
                               status=STATUS_OK if attempt == 0 else STATUS_REPAIRED,
                               attempts=attempts, prompt_tokens=prompt_tokens,
                               output_tokens=output_tokens, usd=f"{spent:.5f}",
                               seconds=f"{seconds:.1f}", failures="")
                    return
                if attempt == 0:
                    prompt = build_repair_prompt(row, produced, failures, titles, skills_dir)

            _write_json(os.path.join(rejected_dir, seed_filename(row)),
                        seed_from(row, produced))
            with lock:
                state["usd"] += spent
                state["rejected"] += 1
            log.append(slug=row.slug, status=STATUS_REJECTED, attempts=attempts,
                       prompt_tokens=prompt_tokens, output_tokens=output_tokens,
                       usd=f"{spent:.5f}", seconds=f"{seconds:.1f}",
                       failures=" | ".join(failures))
        except Exception as exc:  # noqa: BLE001 — one bad row must not stop the batch
            with lock:
                state["usd"] += spent
                state["errors"] += 1
            log.append(slug=row.slug, status=STATUS_ERROR, attempts=attempts,
                       prompt_tokens=prompt_tokens, output_tokens=output_tokens,
                       usd=f"{spent:.5f}", seconds=f"{seconds:.1f}",
                       failures=f"{type(exc).__name__}: {exc}")

    if workers <= 1:
        for row in todo:
            if not budget_left():
                break
            write_one(row)
    else:
        # Submitted in waves of `workers` so the budget is re-checked between
        # waves. A single pool submission would spend the whole backlog before
        # the first result came back.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, len(todo), workers):
                if not budget_left():
                    break
                list(pool.map(write_one, todo[start:start + workers]))

    summary = {
        "planned": len(todo),
        "skipped": skipped,
        "written": state["written"],
        "repaired": state["repaired"],
        "rejected": state["rejected"],
        "errors": state["errors"],
        "failed": state["rejected"] + state["errors"],
        "usd": state["usd"],
        "stopped_on_budget": state["stopped_on_budget"],
    }
    print(f"write: {summary['written']} written, {summary['repaired']} repaired, "
          f"{summary['rejected']} rejected, {summary['errors']} errors, "
          f"{summary['skipped']} skipped")
    print(f"       spent ${summary['usd']:.2f} of ${budget_usd:.2f}"
          + (" (stopped on budget)" if summary["stopped_on_budget"] else ""))
    print(f"       log: {log_path}")
    if summary["rejected"]:
        print(f"       read {rejected_dir}: three rejects sharing a failure means the "
              f"prompt is wrong, not the model")
    return summary
