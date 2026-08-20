"""Nothing may import the deleted graph layer.

The pool that chat depends on used to live in orchestrator.graph; this guard
is what stops it (or anything else) drifting back there.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
# `(?!_guard)` after the bare `orchestrator\.graph` alternatives is deliberate:
# orchestrator.graph_guard is a SURVIVING module (deterministic conceptual-
# model repair, unrelated to the deleted LangGraph state machine) and is
# still imported by agent/tools/state_tools.py and its own
# orchestrator/tests/test_graph_guard.py. Without the lookahead, the plain
# substring match on "orchestrator.graph" would flag those live imports as
# if they referenced the deleted graph.py.
BANNED = re.compile(r"from orchestrator\.graph(?!_guard)|import orchestrator\.graph(?!_guard)|"
                    r"orchestrator\.graph_v2|orchestrator\.studio")


def test_no_module_imports_the_graph_layer():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", "node_modules", "__pycache__"} for part in path.parts):
            continue
        if BANNED.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"graph layer still referenced by: {offenders}"
