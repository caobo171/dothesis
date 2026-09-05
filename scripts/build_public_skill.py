#!/usr/bin/env python
"""Zip the free humanizer skill into web/public/ so students can download it.

The .zip is what claude.ai's Settings → Skills → "Upload a skill" accepts, and
the folder INSIDE it becomes the skill name — so the archive must contain
`dothesis-humanizer/SKILL.md`, not a bare `SKILL.md`.

Built into web/public/skills/ rather than served by the API on purpose: it is a
static file with no auth, no per-user content and no billing, so Next serves it
directly and there is one less endpoint to reason about.

It also syncs the shared pattern library into the internal skill, so the agent
that students pay for and the skill they download read the same file.

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

# The pattern library is written once, in the public skill, and copied into the
# internal one the deep agent reads. Two copies rather than a symlink because a
# symlink does not survive zipfile, and the file has to arrive intact on a
# stranger's machine. `tests/test_public_skill.py` fails if they drift.
SHARED = Path("references") / "ai-patterns.md"
INTERNAL_SKILL = Path("skills") / "dothesis-humanize"

# Anything that would ship someone's junk to a stranger's Claude.
SKIP = {".DS_Store", "__pycache__", ".pyc"}


def source_files(src: Path = SRC) -> list[tuple[Path, Path]]:
    """(archive name, source path) for everything that belongs in the zip.

    Shared with the test that checks the committed zip still matches its
    sources, so there is one definition of what ships.
    """
    return [
        (Path(src.name) / p.relative_to(src), p)
        for p in sorted(src.rglob("*"))
        if p.is_file() and not any(s in p.parts or p.name.endswith(s) for s in SKIP)
    ]


def sync_internal(root: Path = ROOT) -> bool:
    """Copy the pattern library into the internal skill. True if it changed."""
    source = root / "skills-public" / "dothesis-humanizer" / SHARED
    if not source.exists():
        return False
    dest = root / INTERNAL_SKILL / SHARED
    data = source.read_bytes()
    if dest.exists() and dest.read_bytes() == data:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def main() -> int:
    if not (SRC / "SKILL.md").exists():
        print(f"no SKILL.md under {SRC}", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if sync_internal():
        print(f"synced {(INTERNAL_SKILL / SHARED)}")

    files = source_files()
    # Deterministic archive: fixed timestamps so rebuilding an unchanged skill
    # produces an identical file rather than a spurious diff in git.
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, path in files:
            info = zipfile.ZipInfo(str(arc), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())

    print(f"built {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
    for arc, _ in files:
        print(f"  {arc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
