# Agent behaviour evals

These evals run scripted student turns against the **real model** and score what the agent did with deterministic checks.

They answer a question the unit tests can't. The unit tests script the model (`FakeChatModel`, `_get_llm` monkeypatches), so they prove the code around the model is correct. They can't tell you whether a new model, a prompt edit or a skill change makes the agent claim saves it didn't make or drop the `[OPTIONS]` marker. These evals can.

```bash
api/.venv/bin/python -m agent.evals --list
api/.venv/bin/python -m agent.evals                                  # all, once
api/.venv/bin/python -m agent.evals --case save-title-commits --repeat 3
api/.venv/bin/python -m agent.evals --tag incident --compare agent/evals/results/<earlier>.json
DOTHESIS_MODEL_ROUTE=native DOTHESIS_AGENT_MODEL=gemini-3-flash-preview api/.venv/bin/python -m agent.evals
```

Every run calls a paid model. The model comes from the same env as chat (`.env` is loaded).

## What a run is

Each scenario run does four things:
1. It seeds a fresh project directory with the scenario's state and files.
2. It builds the agent exactly as chat does: `build_agent` with the real tools, skills and middleware, plus an in-memory checkpointer.
3. It sends each turn through `stream_turn`.
4. It records the reply, every tool call and its result, any error events, token usage, and the project state before and after each turn.

The per-turn doctor and the honesty post-filters in `chat_v3` are **not** applied. They fix the reply after the model has spoken. Here we want to see what the model does without them.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Every scenario met its `min_pass_rate` (default 1.0). |
| `1` | At least one scenario fell short of its `min_pass_rate`. |
| `2` | A scenario's pass rate dropped against the `--compare` report. |

## Reports

Each run writes a JSON report to `agent/evals/results/`, which is gitignored. A report holds:
- the model route and id
- the git sha, plus whether the worktree had uncommitted changes
- hashes of `SYSTEM_PROMPT` and `skills/`
- per-scenario pass rates and per-check failures
- full transcripts

Only compare two reports that ran the same scenarios. A report from a dirty worktree is provisional.

## Writing a scenario

Add one JSON file to `scenarios/`. Its fields:

| Field | What it holds |
|---|---|
| `title` | One line saying what good behaviour looks like. |
| `incident` | The commit or bug this scenario pins, when there is one. |
| `tags` | Used with `--tag`, for example `incident`, `honesty`, `markers`. |
| `seed.state` | Merged onto an empty project state. Note that `contextStore` is **flat** (`research_title`, not `m1_topic.research_title`). |
| `seed.files` | Workspace files. The value is either the text itself or `{"from": "<repo-relative path>"}`. |
| `turns` | The student's messages, sent in order on one thread. |
| `checks` | See the next section. Each check is `critical` unless it sets `"critical": false`. A failed critical check fails the run. |
| `min_pass_rate` | Optional. Lets a scenario pass with some failed repeats when used with `--repeat`. |

### Check kinds

These are defined in `checks.py`.

| Kind | Passes when |
|---|---|
| `no_error` | The stream emitted no error events. |
| `tool_called` / `tool_not_called` | `tool` (a name or a list of names) was or wasn't called. `tool_called` also requires success, unless `"ok": false`. |
| `state_changed` / `state_unchanged` | The dotted `path` into the state differs, or doesn't, between the first turn's start and the last turn's end. |
| `claim_backed_by_tool` | Whenever a reply matches the `claim` regex, one of the `tool` calls succeeded in **that same turn**. |
| `claim_backed_by_change` | Whenever a reply matches `claim`, `path` changed in that same turn. |
| `reply_matches` / `reply_not_matches` | Regex `pattern` against the reply (case-insensitive). |
| `options_wellformed` | Every `[OPTIONS]` marker parses the way the UI parses it. With `"required": true`, at least one marker must be present. |
| `language` | Every reply reads as Vietnamese (`"value": "vi"`). |
| `max_tool_calls` | The total number of tool calls is at most `max`. |

Every production incident in agent behaviour should become a scenario. Replay the student's message and the state that triggered it, then add a check that fails on what went wrong.

`agent/tests/test_evals_harness.py` runs the harness offline with `FakeChatModel`. It shows that the checks fail a dishonest agent and pass an honest one. Run it whenever you add a check kind.
