"""Research-model diagram tool — promoted from the partner service (spec §3).

Why a tool and not a pipeline step: partner's _render_model_diagram lived
behind a hardcoded nvm node path (partner_report_service._NODE_BIN) whose
failure was swallowed, so every partner report silently shipped without its
diagram. As a tool bound to the agent, ALL THREE surfaces get it — chat
students want a research-model figure in their methodology too — and node is
discovered via shutil.which instead of a user-specific path.

The agent supplies constructs/paths from the M3 slice it already committed —
small structured data it legitimately knows, not model-supplied file bytes
(the banned defect class is models inventing state/bytes, not models
describing their own conceptual model).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_MERMAID_DIR = Path(__file__).resolve().parents[2] / "engine" / "tools" / "mermaid_cli"


def _mermaid_source(constructs: list[dict], paths: list[dict]) -> str | None:
    """Pure mermaid-text builder, split out so the diagram grammar is testable
    without node/mmdc. Dangling paths (to undeclared constructs) are dropped —
    rendering model noise as edges would fabricate relationships."""
    labels = {
        str(c["id"]): str(c.get("label") or c["id"])
        for c in (constructs or []) if isinstance(c, dict) and c.get("id")
    }
    edges = [
        (str(p.get("from")), str(p.get("to")))
        for p in (paths or [])
        if isinstance(p, dict) and str(p.get("from")) in labels and str(p.get("to")) in labels
    ]
    if not labels or not edges:
        return None
    lines = ["flowchart LR"]
    for cid, label in labels.items():
        lines.append(f'  {cid}["{label.replace(chr(34), chr(39))}"]')
    for a, b in edges:
        lines.append(f"  {a} --> {b}")
    return "\n".join(lines)


@tool
def render_model_diagram(constructs: list[dict], paths: list[dict]) -> str:
    """Render the study's conceptual/structural research model as a PNG figure.

    Pass the constructs and directed paths from the project's M3 design —
    constructs as [{"id": "TR", "label": "Trust"}, ...] (short ascii ids) and
    paths as [{"from": "TR", "to": "PI"}, ...]. On success returns
    {"ok": true, "image_markdown": "![Research model](data:image/png;base64,…)"}.
    Embed `image_markdown` (with your own caption line) into the methodology
    prose you commit, so the figure ships inside the exported document.
    """
    mmd = _mermaid_source(constructs, paths)
    if mmd is None:
        return json.dumps({"error": "empty_model",
                           "hint": "provide at least two constructs and one path "
                                   "between declared construct ids"})
    mmdc = _MERMAID_DIR / "node_modules" / ".bin" / "mmdc"
    cfg = _MERMAID_DIR / "puppeteer.json"
    if not mmdc.exists():
        # Fail soft with a stable code: a missing renderer must degrade the
        # figure, never the turn (the swallowed-failure lesson, made loud).
        logger.warning("render_model_diagram: mmdc not installed at %s", mmdc)
        return json.dumps({"error": "mmdc_unavailable",
                           "hint": "mermaid CLI is not installed on this host; "
                                   "describe the model in prose or a ```mermaid``` block instead"})
    try:
        d = Path(tempfile.mkdtemp(prefix="model_"))
        mmd_path, png_path = d / "model.mmd", d / "model.png"
        mmd_path.write_text(mmd, encoding="utf-8")
        env = dict(os.environ)
        # Node discovery via shutil.which replaces the hardcoded _NODE_BIN —
        # the exact prod bug this promotion exists to kill.
        node = shutil.which("node")
        extra = ([str(Path(node).parent)] if node else []) + ["/opt/homebrew/bin"]
        env["PATH"] = ":".join(extra + [env.get("PATH", "")])
        subprocess.run(
            [str(mmdc), "-i", str(mmd_path), "-o", str(png_path),
             "-c", str(cfg), "-b", "white", "-w", "1100"],
            check=True, capture_output=True, timeout=120, env=env,
            cwd=str(_MERMAID_DIR),
        )
        if not png_path.exists():
            return json.dumps({"error": "render_failed", "hint": "mmdc produced no PNG"})
        b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
        # data URI so the image embeds in BOTH the WeasyPrint PDF and the
        # pandoc DOCX with no external file alive at render time.
        return json.dumps({"ok": True,
                           "image_markdown": f"![Research model](data:image/png;base64,{b64})"})
    except Exception as e:
        # Unlike the partner original (which returned None and left prod blind),
        # the failure detail reaches the model so it can retry or fall back.
        logger.exception("render_model_diagram failed")
        return json.dumps({"error": "render_failed", "detail": str(e)})
