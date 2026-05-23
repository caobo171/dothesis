"""Helpers used by the subprocess entrypoint. Kept separate from __main__ for testability."""
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class JsonlAppender:
    """Append-only writer that flushes after each line so the API tailer sees writes immediately."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fp = path.open("a", encoding="utf-8", buffering=1)  # line-buffered

    def write(self, payload: dict) -> None:
        line = json.dumps(payload, default=str)
        self._fp.write(line + "\n")
        self._fp.flush()

    def close(self) -> None:
        try:
            self._fp.close()
        except Exception:
            pass


def _normalize_progress(progress_percent: float | int | None) -> float:
    if progress_percent is None:
        return 0.0
    return progress_percent / 100.0 if progress_percent > 1.0 else float(progress_percent)


class JobTracker:
    """Adapter matching the surface that `engine.draft_generator` and phase modules call on `ctx.tracker`.

    The real `engine.utils.progress_tracker.ProgressTracker` is Supabase-backed.
    We provide the same method signatures so the engine runs unmodified, and emit
    plain JSONL events that the API tails and persists/forwards over SSE.

    All methods are best-effort: any exception in tracker is swallowed and logged so
    a tracker hiccup never kills the pipeline.
    """

    def __init__(self, appender: JsonlAppender) -> None:
        self._a = appender

    # ---- helpers ----------------------------------------------------------

    def _safe_write(self, payload: dict) -> None:
        try:
            self._a.write(payload)
        except Exception:
            log.exception("tracker write failed for payload type=%s", payload.get("type"))

    # ---- cancellation / heartbeat (no-ops; API uses SIGTERM for cancel) ----

    def check_cancellation(self) -> None:
        return None

    def send_heartbeat(self) -> None:
        return None

    # ---- activity log ------------------------------------------------------

    def log_activity(self, message: str, event_type: str = "info",
                     phase: str | None = None, agent: str | None = None,
                     **meta: Any) -> None:
        self._safe_write({
            "type": "activity",
            "phase": phase,
            "agent": agent,
            "text": message,
            "event_type": event_type,
            **meta,
        })

    def log_source_found(self, title: str, authors: list[str] | None = None, year: int | None = None,
                         source_type: str = "paper", doi: str | None = None, url: str | None = None,
                         verified: bool = True, **_: Any) -> None:
        author_str = ", ".join(authors) if isinstance(authors, list) else (authors or "")
        text = f"Found source: {title}" + (f" ({year})" if year else "")
        self._safe_write({
            "type": "activity",
            "phase": "research",
            "agent": "Scout",
            "text": text,
            "event_type": "found",
            "source": {"title": title, "authors": author_str, "year": year,
                       "doi": doi, "url": url, "verified": verified, "type": source_type},
        })

    # ---- phase / progress updates -----------------------------------------

    def update_phase(self, phase: str, progress_percent: float | int = 0,
                     sources_count: int | None = None, chapters_count: int | None = None,
                     details: dict | None = None, **_: Any) -> None:
        active_agents = (details or {}).get("active_agents", []) if isinstance(details, dict) else []
        self._safe_write({
            "type": "phase_progress",
            "phase": phase,
            "progress": _normalize_progress(progress_percent),
            "active_agents": active_agents,
            "sources_count": sources_count,
            "chapters_count": chapters_count,
            "details": details,
        })

    def update_research(self, sources_count: int, phase_detail: str = "", **_: Any) -> None:
        self._safe_write({
            "type": "activity",
            "phase": "research",
            "agent": "Scout",
            "text": phase_detail or f"Discovered {sources_count} sources",
            "sources_count": sources_count,
        })

    def update_exporting(self, export_type: str = "", **_: Any) -> None:
        self._safe_write({
            "type": "activity",
            "phase": "export",
            "agent": "Compositor",
            "text": f"Exporting {export_type or 'draft'}",
        })

    # ---- terminal markers --------------------------------------------------

    def mark_completed(self, **_: Any) -> None:
        # The real `job_done` event (with exports list) is written by engine/__main__.py
        # after S3 upload. This marker is informational only.
        self._safe_write({
            "type": "activity",
            "phase": "export",
            "text": "Generation complete",
            "event_type": "milestone",
        })

    def mark_failed(self, error_message: str | None = None, **_: Any) -> None:
        # The real `error` event is written by engine/__main__.py from the exception handler.
        self._safe_write({
            "type": "activity",
            "phase": "export",
            "text": error_message or "Generation failed",
            "event_type": "error",
        })

    # ---- checkpoint marker -------------------------------------------------

    def checkpoint_saved(self, phase: str) -> None:
        """Tell the API that engine just wrote {workdir}/checkpoint.json after a phase."""
        self._safe_write({"type": "checkpoint", "phase": phase})

    # ---- introspection / reports (no-ops) ---------------------------------

    def to_json(self) -> dict:
        return {}

    def print_report(self) -> None:
        return None


class JobStreamer:
    """Adapter matching the surface the engine calls on `ctx.streamer`.

    The engine uses streamer both as a callable (`streamer("some message")`) and via
    `stream_chapter_complete`, `stream_outline_complete`, `stream_research_complete`.
    All paths funnel into a single activity event.
    """

    def __init__(self, appender: JsonlAppender) -> None:
        self._a = appender

    def _safe_write(self, payload: dict) -> None:
        try:
            self._a.write(payload)
        except Exception:
            log.exception("streamer write failed for payload type=%s", payload.get("type"))

    def __call__(self, message: str, **meta: Any) -> None:
        self._safe_write({"type": "activity", "text": message, **meta})

    def stream_outline_complete(self, outline: Any = None, **_: Any) -> None:
        self._safe_write({"type": "activity", "phase": "structure",
                          "agent": "Architect", "text": "Outline complete"})

    def stream_research_complete(self, sources_count: int | None = None, **_: Any) -> None:
        text = (f"Research complete — {sources_count} sources"
                if sources_count is not None else "Research complete")
        self._safe_write({"type": "activity", "phase": "research",
                          "agent": "Scout", "text": text})

    def stream_chapter_complete(self, chapter_name: str | None = None,
                                words: int | None = None, **_: Any) -> None:
        text = f"Chapter complete: {chapter_name or 'section'}"
        if words is not None:
            text += f" ({words} words)"
        self._safe_write({"type": "activity", "phase": "compose",
                          "agent": "Crafter", "text": text, "words": words})


def upload_artifacts(s3_client, workdir: Path, key_root: str) -> list[str]:
    """Upload everything under workdir/{exports,research,drafts} to S3. Returns list of export formats found."""
    found_exports: list[str] = []
    EXTS = {"pdf", "docx", "tex", "md", "zip"}
    for sub in ("exports", "research", "drafts"):
        base = workdir / sub
        if not base.exists():
            continue
        for fp in base.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(workdir).as_posix()
            full_key = f"{key_root}/{rel}"
            s3_client.put_file(full_key, str(fp))
            log.info("uploaded %s -> %s", rel, full_key)
            if sub == "exports":
                ext = fp.suffix.lstrip(".").lower()
                if ext in EXTS:
                    found_exports.append(ext)
    return sorted(set(found_exports))
