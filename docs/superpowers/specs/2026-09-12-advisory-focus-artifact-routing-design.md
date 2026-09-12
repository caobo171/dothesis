# Advisory Focus and Artifact Routing Design

## Problem

Before this change, `focus` acted as both a UI position and an implicit write router. A
terse follow-up such as “save it” can therefore write a questionnaire into M5
when focus is M5, even though questionnaires are owned by M3. The agent did
call `commit_slice`, but the successful call targeted `M5.final_sections`;
`M3.instrument.items` remained empty.

## Design

Focus is advisory context only. It indicates the latest area of work and may
guide an otherwise context-free “continue”, but it never overrides an artifact
named by the user or inherited from the immediately preceding conversation.

The agent remains free to choose any available tool, tool order, and modules to
read or mutate. State writes keep their deterministic boundary:

- topic and research questions → M1
- literature and research gaps → M2
- methodology, model, hypotheses, questionnaire → M3
- analysis and results → M4
- thesis chapters and closing prose → M5

The API resolves a conservative write target from the current message. For a
save-like pronoun follow-up, it inherits the nearest unambiguous artifact from
recent user and assistant messages. It injects a machine-only `[WRITE TARGET]`
marker into the agent turn.

A tool middleware validates only `commit_slice` calls when a write target is
present. It does not choose tools or force a workflow. A mismatched module or
missing owned key returns a tool error with the canonical destination, allowing
the agent loop to retry correctly. Turns without an unambiguous target remain
fully agent-directed.

The final response may claim an artifact was saved only when a successful
`commit_slice` result matches the requested module and key.

## Compatibility

Headless runs and ordinary turns without a `[WRITE TARGET]` marker are
unchanged. Existing slice ownership, downstream staleness propagation,
statistics validation, and coherence gates remain authoritative.

## Tests

- Explicit questionnaire request resolves to `M3.instrument`.
- “Save it” inherits questionnaire from recent dialogue.
- A new explicit artifact overrides inherited context.
- Middleware permits arbitrary non-state tools.
- Middleware rejects questionnaire writes to M5.
- Middleware accepts questionnaire writes to M3 containing `instrument`.
- Saved-claim validation requires the matching module and key.
- Existing chat intent, M3 contract, and state-tool tests continue to pass.
