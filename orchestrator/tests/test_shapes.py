"""Brief §3 — module handler shape declarations.

PR #5 ships the shape MARKERS (Wizard/PhaseChat/Pipeline). Each module
agent is declared as one of the three shapes. The shape is a marker
mixin — it pins the contract and supports isinstance-based dispatch in
shape-aware router/UI logic, without changing today's behavior.

The wizard refactor (M1/M3/M5 → one structured-output call per turn)
and the M4 sandbox DSL are follow-ups; this PR only asserts the shape
hierarchy is in place.
"""
from orchestrator.agents.m1_topic import M1Agent
from orchestrator.agents.m2 import M2Agent
from orchestrator.agents.m3_design import M3Agent
from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.agents.shapes import (
    PhaseChatAgent, PipelineAgent, WizardAgent, declared_shape,
)


def test_m1_is_wizard():
    assert isinstance(M1Agent(), WizardAgent)
    assert declared_shape(M1Agent()) == "wizard"


def test_m2_is_phase_chat():
    assert isinstance(M2Agent(), PhaseChatAgent)
    assert declared_shape(M2Agent()) == "phase_chat"


def test_m3_is_wizard():
    assert isinstance(M3Agent(), WizardAgent)
    assert declared_shape(M3Agent()) == "wizard"


def test_m4_is_pipeline():
    assert isinstance(M4Agent(), PipelineAgent)
    assert declared_shape(M4Agent()) == "pipeline"


def test_m5_is_wizard():
    assert isinstance(M5Agent(), WizardAgent)
    assert declared_shape(M5Agent()) == "wizard"


def test_modules_carry_slice_field_per_brief_section6():
    # Brief §6 — ModuleHandler.slice_field is part of the contract. The
    # router uses it to write the module's writes back to the right
    # ContextStore field; today's _MODULE_FIELD dict in graph.py /
    # graph_v2.py duplicates this, but the contract lives on the agent.
    assert M1Agent().slice_field == "m1_topic"
    assert M2Agent().slice_field == "m2_literature"
    assert M3Agent().slice_field == "m3_design"
    assert M4Agent().slice_field == "m4_analysis"
    assert M5Agent().slice_field == "m5_writing"


def test_step_still_resolves_to_module_agent_concrete():
    # Critical MRO test: declaring WizardAgent BEFORE ModuleAgent must
    # NOT shadow ModuleAgent's concrete step(). If WizardAgent ever adds
    # an abstract step() back, instantiation would fail OR step would
    # raise NotImplementedError — this test catches both regressions.
    m1 = M1Agent()
    # method resolves to a concrete callable, NOT to a raising stub
    assert callable(m1.step)
    # Walk the MRO and confirm ModuleAgent.step is what we'd dispatch to.
    from orchestrator.agents.base import ModuleAgent
    assert M1Agent.step is ModuleAgent.step
