"""Brief §3 — three module-handler shapes (Wizard / PhaseChat / Pipeline).

Today every module subclasses `ModuleAgent` and runs the same
clarification chat loop. The brief is explicit that this is wrong for
M1, M3, M5 (wizards — one structured-output call) and for M4 (pipeline
— actually run statistics on raw data). Only M2 wants the chat loop.

This module introduces the three shape **base classes** that PR #5
ships:

  - WizardAgent      — M1, M3, M5. One structured-output call per turn.
  - PhaseChatAgent   — M2. The existing phase-machine pattern, lifted
                       out of the generic ModuleAgent.
  - PipelineAgent    — M4. detect → outline → execute steps. Stats
                       execution goes through the sandboxed DSL (brief
                       §8) — NOT free-form Python.

PR #5 ships the **shapes** (base classes + tests) WITHOUT migrating the
five existing module agents. Migration of each module is incremental and
flag-gated (`M1_SHAPE=wizard`, etc.) so we can promote one module at a
time and validate against live traffic before flipping the next.

Why shapes-only first: M2/M4 keep their existing internal flows
unchanged in this PR — only their base class identity changes when we
flip the flag. M1/M3/M5 wizard migration is a real refactor (drop the
clarification loop, write a single structured-output prompt per module);
landing the bases first lets that refactor be a fresh PR each.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from orchestrator.agents.base import ModuleAgent
from orchestrator.state import ModuleKey

logger = logging.getLogger(__name__)


# Brief §3 — the contract every shape implements. We define it as an
# abstract base rather than a Protocol so the type system gives us a
# clean place to put shared helpers (slice access, prompt formatting)
# and so the existing ModuleAgent (which the M1..M5 classes already
# subclass) can be promoted to one of the three shapes by changing
# its declared base.
class ModuleHandler:
    """The shape-agnostic module-handler contract (brief §3 / §6).

    Properties (all set by subclasses as class-level attributes):
      module_key:  "M1".."M5"
      slice_field: the ContextStore field this module owns

    Methods (by convention — NOT declared abstract so multi-inheritance
    with the legacy ModuleAgent finds its concrete step() via MRO without
    a no-op shadowing layer here):
      step(state) → ModuleStepResult  — one turn of work.
      read(slice, message) → str       — brief §1.5 read intent. The
        default delegates to read_handler.read_slice; modules can
        override for a richer slice-quoting style.

    The marker-mixin shape (no abstractmethod step) is what lets
    M2Agent(PhaseChatAgent, ModuleAgent) keep ModuleAgent's concrete
    step() while still being isinstance(_, PhaseChatAgent). Adding
    @abstractmethod step here would shadow ModuleAgent.step in the MRO
    and break the legacy implementations during the dual-write window.
    """
    module_key: ModuleKey
    slice_field: str

    def read(self, slice: dict, message: str) -> str:
        """Default read implementation — delegates to read_handler.
        Per-module overrides can format slices more nicely (e.g. M2
        wants citations rendered as a list, not raw JSON)."""
        # Imported lazily to break a potential cycle (read_handler
        # imports from orchestrator.state, which this module also
        # touches; staying lazy keeps initialisation order tame).
        from orchestrator.agents.read_handler import read_slice
        from orchestrator.state import ContextStore as CS
        # Build a single-slice ContextStore so read_slice's slice
        # accessor finds the data. This is the cheapest way to keep
        # read_slice's signature uniform.
        cs = CS(**{self.slice_field: slice})
        return read_slice(self.module_key, message, cs)


class WizardAgent(ModuleHandler):
    """M1, M3, M5 (brief §3). ONE structured-output LLM call per turn.

    The user has typed their answer; the wizard sends one Gemini call
    with `with_structured_output(schema)` and either writes a complete,
    validated slice or surfaces a validation error message. There is NO
    clarification loop, NO `_awaiting_field` walk; the wizard owns the
    whole module decision in a single round trip.

    PR #5 ships the marker mixin so the SHAPE is pinned (isinstance
    checks pass, future router code can branch on shape). The actual
    one-shot-structured-output refactor of M1Agent/M3Agent/M5Agent is
    PR #5b — each module has custom widget/validation glue that can't
    be lifted into a base class wholesale. Until then the wizard
    declaration coexists with the legacy ModuleAgent clarification
    step() via MRO.

    Subclasses set `schema: type[BaseModel]` to the Pydantic schema for
    their module (M1Output, M3Output, M5Output).
    """
    schema: type[BaseModel]


class PhaseChatAgent(ModuleHandler):
    """M2 (brief §3). The phase machine pattern, formalised.

    M2 walks four phases: familiarization → research_state → gap_analysis
    → output_gen. Each phase IS a chat loop with its
    own prompt; transitions happen on the agent's signal (not user input).

    This class is a marker — M2Agent's existing step() (which delegates
    to the m2/graph.py sub-graph) implements the contract. Future shape-
    aware router logic ("PhaseChat handlers can be interrupted mid-phase
    by a cross-module read") can isinstance() on this without dropping
    a probe on `class.__name__`.
    """


class PipelineAgent(ModuleHandler):
    """M4 (brief §3 + §8). Real computation — not LLM-only interpretation.

    The pipeline: detect data type → propose analysis outline → user
    confirms → execute each step. Execution MUST call a whitelisted DSL
    (Sobel mediation, t-test, regression, …) inside the Python sandbox
    described in brief §8 — NOT free-form Python generated by the LLM,
    which would be a prompt-injection-to-arbitrary-code surface.

    PR #5 ships the marker; the actual sandbox lives in a separate PR
    (brief §7 polyglot worker). Until then M4Agent stays on its current
    paste-text-parser implementation under this marker (so the SHAPE is
    correct, the underlying execution is still LLM-only).
    """

    # Placeholder for the DSL — the sandbox PR will define a real
    # AnalysisDSL protocol with whitelisted methods (t_test, sobel, …).
    # Today it's typed as Any so M4Agent can subclass without claiming
    # support it doesn't yet have.
    dsl: Any = None


# ---------------------------------------------------------------------------
# Mapping from declared shape → concrete base class.
# Lets the migration PRs flip a module's shape via a single line in its
# subclass declaration (e.g. `class M1Agent(WizardAgent, ModuleAgent)` to
# adopt the wizard contract while still using ModuleAgent helpers during
# the transition).
# ---------------------------------------------------------------------------
SHAPE_BY_NAME: dict[str, type[ModuleHandler]] = {
    "wizard": WizardAgent,
    "phase_chat": PhaseChatAgent,
    "pipeline": PipelineAgent,
}


def declared_shape(agent: ModuleAgent) -> str:
    """Return the shape name an agent has been promoted to, or 'legacy'
    if it still subclasses the generic ModuleAgent only.

    Diagnostic — used in tests to assert the migration of each module:
        assert declared_shape(M1Agent()) == 'wizard'
    """
    for name, cls in SHAPE_BY_NAME.items():
        if isinstance(agent, cls):
            return name
    return "legacy"
