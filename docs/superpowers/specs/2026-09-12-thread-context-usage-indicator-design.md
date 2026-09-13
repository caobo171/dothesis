# Thread Context Usage Indicator Design

## Goal

Show a Claude/Codex-style context indicator below the chat composer:

`Context 88K · compact in 82K · 52%`

The value describes the active LangGraph thread's model context, not credits and
not the sum of billable tokens spent over multiple model calls.

## Existing behavior

`create_deep_agent` already installs automatic conversation summarization.
Deepagents triggers at 85% of `model.profile.max_input_tokens`; when that model
profile is unavailable it uses a fixed 170,000-token trigger. The app currently
receives `input_tokens` and `output_tokens` for each model step but sums them
only for turn billing and persists only `total_tokens`.

## Design

### Backend accounting

Add a pure helper that derives `compact_at_tokens` from the same rules as the
pinned deepagents runtime:

- integer `model.profile.max_input_tokens` → `floor(limit * 0.85)`
- absent/invalid profile → `170_000`

Each runtime `usage` event carries the threshold alongside provider-reported
input/output tokens. `chat_v3` continues summing every step for billing, while
separately replacing `context_tokens` with the latest step's `input_tokens`.
The final step is the best available measurement of the thread context that
will feed the next model call; summing steps would overstate occupancy.

Persist `context_tokens` and `compact_at_tokens` on each assistant `Message`,
and include both in the SSE `done` event. Legacy rows default to zero. No token
count is fabricated when the provider reports no usage.

### Frontend

`useChat` exposes the latest valid context snapshot, preferring the live `done`
event and falling back to the newest persisted assistant message after reload.
`ChatPane` passes it to `ChatInput`.

Below the composer actions, render a compact, muted status line:

- normal: `Context 88K · compact in 82K · 52%`
- at/over threshold: `Context 170K · compacting automatically…`
- unavailable/zero: hidden

Percentage is progress toward the compaction trigger, not the provider's entire
context window. Remaining tokens are clamped at zero. Formatting uses compact
`K`/`M` units and localized English/Vietnamese labels.

The indicator is informational only: no manual compact button and no changes
to automatic summarization behavior.

## Data model and migration

Add non-null integer columns with server default zero:

- `messages.context_tokens`
- `messages.compact_at_tokens`

The values are thread-specific snapshots carried by assistant messages, so no
project-level state or new endpoint is required.

## Failure handling

- Missing usage metadata: omit the snapshot and keep the last persisted value.
- Unknown model profile: use the exact 170K deepagents fallback.
- A compaction between model calls naturally lowers the latest input count; the
  next `done` event updates the indicator.
- Billing remains based only on accumulated input + output tokens.

## Tests

- Pure threshold helper: profiled model, malformed profile, fallback.
- Chat finalization: billing sums all steps while context uses only the last
  input count; SSE and persisted message carry both values.
- Frontend formatting and states: normal, threshold reached, unavailable.
- Hook selection: live `done` snapshot overrides persisted snapshot; reload
  restores the persisted values.
- Migration upgrade/downgrade and production TypeScript build.
