"""run_headless over the real deepagents brain with the scripted FakeChatModel:
loop, stall detection, budgets, options auto-decide (spec §1/§5). Only the
completion is fake — tools, store writes, and the [OPTIONS] parser are real.

Budget tests assert the run STOPS (fails). A budget bug only ever surfaces as
a test that asserts failure — asserting completion would pass right through it.
"""
import asyncio
import json

from agent.headless import RunProfile, run_headless
from agent.state import MODULES, ProjectStateStore


def _module_steps(module, writes):
    # One roadmap-module turn = 2 completions: the tool_calls step, then the
    # post-ToolMessage wrap-up (FakeChatModel steps index by AI-message count).
    return [
        {"response": f"Working on {module}.",
         "tool_calls": [{"name": "commit_slice",
                         "args": {"module": module, "writes": writes,
                                  "reason": "headless fixture", "confirm_done": True}}]},
        {"response": f"{module} committed."},
    ]


HAPPY = {"scenario": "headless-happy", "entry": "continue", "steps": [
    *_module_steps("M1", {"research_title": "T", "research_questions": ["RQ1"]}),
    *_module_steps("M2", {"literature_sources": [{"title": "P", "year": 2024}]}),
    *_module_steps("M3", {"conceptual_model": "CM", "hypotheses": ["H1"],
                          "methodology": "PLS-SEM"}),
    *_module_steps("M4", {"analysis_outline": "O", "analysis_results": "R"}),
    *_module_steps("M5", {"final_sections": [{"title": "Intro", "prose": "p"}]}),
]}


def _build(tmp_path, fixture):
    fx = tmp_path / "fixtures"
    fx.mkdir()
    (fx / "run.json").write_text(json.dumps(fixture), encoding="utf-8")
    from langgraph.checkpoint.memory import InMemorySaver

    from agent.runtime import build_agent
    from agent.testing.fake_model import FakeChatModel
    proj = tmp_path / "proj"
    store = ProjectStateStore(proj)
    agent = build_agent(proj, model=FakeChatModel.from_fixtures_dir(str(fx)),
                        checkpointer=InMemorySaver(), store=store)
    return agent, store


def test_happy_path_runs_to_done(tmp_path):
    agent, store = _build(tmp_path, HAPPY)
    result = asyncio.run(run_headless(agent, store, RunProfile(max_turns=10)))
    assert result.status == "done" and result.reason == "roadmap_done"
    st = store.load()
    assert all(st["status"][m] == "done" for m in MODULES)


def test_required_modules_subset_finishes_without_the_rest(tmp_path):
    # A caller that only needs SOME modules (partner's analysis_report asks for
    # chapters M2/M3 never feed) must not be forced to drive a full M1-M5 run to
    # get a non-failure. "Done enough for THIS request" is data on the profile.
    agent, store = _build(tmp_path, HAPPY)
    result = asyncio.run(run_headless(
        agent, store, RunProfile(max_turns=10, required_modules=frozenset({"M1"}))))
    assert result.status == "done" and result.reason == "roadmap_done"
    assert result.turns == 1
    # The modules nobody asked for were never touched — no busywork, no cost.
    assert store.load()["status"]["M5"] == "locked"


def test_required_modules_defaults_to_every_module(tmp_path):
    # Default profile = today's behaviour for every existing caller: one module
    # done is not a done run.
    agent, store = _build(tmp_path, HAPPY)
    assert RunProfile().required_modules is None
    result = asyncio.run(run_headless(agent, store, RunProfile(max_turns=1)))
    assert result.status == "failed" and result.reason == "max_turns"


def test_stall_fixture_fails_at_max_stalls(tmp_path):
    # A model that neither commits nor asks: store bytes never change, no
    # [OPTIONS] — deterministic stall regardless of WHY (missing marker,
    # off-script model, silent tool failure). The run must FAIL, loudly.
    stall = {"scenario": "stall", "entry": "continue", "steps": [
        {"response": "Hmm, let me think."},
        {"response": "Still thinking."},
        {"response": "Thinking harder."},
    ]}
    agent, store = _build(tmp_path, stall)
    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(max_stalls=3, max_turns=10)))
    assert result.status == "failed" and result.reason == "max_stalls"
    assert result.turns == 3


def test_looping_fixture_fails_at_turn_cap(tmp_path):
    # Progress every turn, completion never: the turn budget is the only thing
    # standing between this and infinite spend.
    steps = []
    for i in range(6):
        steps += [
            {"response": "Revising.",
             "tool_calls": [{"name": "commit_slice",
                             "args": {"module": "M1",
                                      "writes": {"research_title": f"T{i}"},
                                      "reason": "loop fixture"}}]},
            {"response": "Revised."},
        ]
    agent, store = _build(tmp_path, {"scenario": "loop", "entry": "continue",
                                     "steps": steps})
    result = asyncio.run(run_headless(agent, store, RunProfile(max_turns=4)))
    assert result.status == "failed" and result.reason == "max_turns"
    assert result.turns == 4
    # partial state preserved — budget exhaustion is failure WITH the work kept
    assert store.load()["contextStore"]["research_title"] == "T3"


def test_wall_clock_fails_run(tmp_path):
    agent, store = _build(tmp_path, {"scenario": "slow", "entry": "continue",
                                     "steps": [{"response": "ok"},
                                               {"response": "ok again"}]})
    t = {"now": 0.0}

    def clock():  # each budget check advances fake time 400s
        t["now"] += 400.0
        return t["now"]

    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(wall_clock_s=600), _clock=clock))
    assert result.status == "failed" and result.reason == "wall_clock"


OPTIONS_FIX = {"scenario": "opts", "entry": "continue", "steps": [
    {"response": "Chọn cách tiếp cận:\n\n[OPTIONS:paradigm] Định lượng | Định tính"},
    {"expect_user": "Định lượng",
     "response": "Committing the pick.",
     "tool_calls": [{"name": "commit_slice",
                     "args": {"module": "M1", "writes": {"research_title": "T"},
                              "reason": "picked"}}]},
    {"response": "Done for now."},
]}


def test_options_auto_decided_and_recorded(tmp_path):
    agent, store = _build(tmp_path, OPTIONS_FIX)
    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(max_turns=3, max_stalls=1)))
    # The fixture never reaches all-done: the run must STOP as a failure,
    # never report success on a hollow project.
    assert result.status == "failed"
    assert result.decisions and result.decisions[0]["choice"] == "Định lượng"
    st = store.load()
    assert st["contextStore"]["decisions"][0]["choice"] == "Định lượng"
    assert st["contextStore"]["research_title"] == "T"  # the reply drove the agent


def test_on_options_ask_stops_and_surfaces(tmp_path):
    agent, store = _build(tmp_path, OPTIONS_FIX)
    result = asyncio.run(run_headless(agent, store,
                                      RunProfile(on_options="ask", max_turns=3)))
    assert result.status == "needs_input" and result.reason == "awaiting_options"
    assert result.pending_options == ["Định lượng", "Định tính"]
    assert not store.load()["contextStore"].get("decisions")  # nothing auto-recorded
