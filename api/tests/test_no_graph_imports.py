"""Nothing may import the deleted graph layer.

The pool that chat depends on used to live in orchestrator.graph; this guard
is what stops it (or anything else) drifting back there.
"""
import json
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


def test_langgraph_json_points_at_the_deep_agent():
    # Studio's config is a .json pointer, invisible to the *.py scan above —
    # this is what actually caught the Task 10 regression (langgraph.json
    # still named the deleted orchestrator/studio.py after the graph layer
    # was removed). Assert both the shape (deepagent, not orchestrator)...
    cfg = json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))
    assert "deepagent" in cfg["graphs"]
    assert "orchestrator" not in cfg["graphs"]


def test_langgraph_json_entrypoint_file_exists():
    # ...and the substance: the file half of "path:factory" must actually be
    # on disk. A test that only checked the key name ("deepagent" present)
    # would NOT have caught a stale/typo'd path — the exact failure mode this
    # task exists to fix (langgraph.json pointed at a deleted studio.py and
    # nothing but a manual `langgraph dev` run would have noticed).
    cfg = json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))
    for target in cfg["graphs"].values():
        module_path, _, _factory_name = target.partition(":")
        assert module_path.startswith("./"), f"unexpected graph path shape: {target}"
        resolved = ROOT / module_path[2:]
        assert resolved.is_file(), f"langgraph.json points at a missing file: {resolved}"


def test_studio_factory_takes_no_arguments():
    # `langgraph dev` calls the factory with zero arguments; a signature that
    # requires anything would fail at Studio boot, not at import time.
    import inspect

    from agent import studio

    assert inspect.signature(studio.get_studio_graph).parameters == {}
