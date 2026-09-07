#!/usr/bin/env python3
"""QA gate for DoThesis blog seed JSON files.

Thin shim. The rules live in `api/app/blog/content/qa.py` so that the writer can
run the identical checks in-process before it ever writes a file; this script is
the same code reached from the skill, from a shell, and from a pre-publish check.

Deliberately importable by a bare `python3` with no virtualenv: `qa.py` is
stdlib-only for exactly this reason, and the seed dir is usually inspected by
someone who has not activated `api/.venv`.

    python3 .claude/skills/dothesis-content-pipeline/scripts/qa_seeds.py [seed-dir] \
        [--known-slugs FILE]

`--known-slugs` is a file of slugs, one per line, that internal links may resolve
to on top of the seed dir and `backlog.tsv`. Without it nothing changes.

Exit code 1 if any file FAILs.
"""
import os
import sys

# .../<repo>/.claude/skills/dothesis-content-pipeline/scripts/qa_seeds.py -> <repo>
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", "..", ".."))
API_DIR = os.path.join(REPO_ROOT, "api")

if not os.path.isdir(os.path.join(API_DIR, "app", "blog", "content")):
    sys.exit(f"qa_seeds.py: cannot find app/blog/content under {API_DIR}")

sys.path.insert(0, API_DIR)

from app.blog.content.qa import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
