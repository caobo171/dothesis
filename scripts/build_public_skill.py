#!/usr/bin/env python
"""Zip the free humanizer skill into web/public/ so students can download it.

The .zip is what claude.ai's Settings → Skills → "Upload a skill" accepts, and
the folder INSIDE it becomes the skill name — so the archive must contain
`dothesis-humanizer/SKILL.md`, not a bare `SKILL.md`.

Built into web/public/skills/ rather than served by the API on purpose: it is a
static file with no auth, no per-user content and no billing, so Next serves it
directly and there is one less endpoint to reason about.

Run after editing anything under skills-public/:

    python scripts/build_public_skill.py
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "skills-public" / "dothesis-humanizer"
OUT = ROOT / "web" / "public" / "skills" / "dothesis-humanizer.zip"

# Anything that would ship someone's junk to a stranger's Claude.
SKIP = {".DS_Store", "__pycache__", ".pyc"}


def main() -> int:
    if not (SRC / "SKILL.md").exists():
        print(f"no SKILL.md under {SRC}", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p for p in SRC.rglob("*")
        if p.is_file() and not any(s in p.parts or p.name.endswith(s) for s in SKIP)
    )
    # Deterministic archive: fixed timestamps so rebuilding an unchanged skill
    # produces an identical file rather than a spurious diff in git.
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            arc = Path(SRC.name) / path.relative_to(SRC)
            info = zipfile.ZipInfo(str(arc), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())

    print(f"built {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
    for path in files:
        print(f"  {Path(SRC.name) / path.relative_to(SRC)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
