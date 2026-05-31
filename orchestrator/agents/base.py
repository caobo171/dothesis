"""ModuleAgent base — shared clarification loop for all 5 module nodes."""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import time
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ValidationError

from orchestrator.agents.widgets import CardGridHint, CardOption, ListEditorHint, ListItem
from orchestrator.message_utils import text_of
from orchestrator.state import OrchestratorState, get_module_slice

logger = logging.getLogger(__name__)


class BoundedInvokeTimeout(TimeoutError):
    """Raised when a bounded_invoke call exceeds its wall-clock budget."""


def bounded_invoke(llm, prompt, *, max_seconds: int = 60,
                   retries: int = 1, backoff_s: float = 1.0):
    """Wall-clock-bounded LLM invoke with bounded retries.

    Why this exists: Gemini's client occasionally takes 5+ minutes for a single
    invoke (its internal retries respect per-RPC timeouts but the wall-clock
    can blow out). LangChain's `timeout=N` on ChatGoogleGenerativeAI is
    request-level, not wall-clock — so a single agent step could hang for
    minutes, freezing the whole graph turn. This helper enforces a hard
    wall-clock cap via a ThreadPoolExecutor.future.result(timeout=...) and
    retries transient errors with exponential backoff before giving up.

    Trade-off note: on hard timeout the underlying worker thread is not killed
    (Python can't), so a stuck call leaks one thread for the rest of the
    process lifetime. For an HTTP-request-scoped graph turn this is acceptable;
    don't loop this in a long-lived daemon without bounding total threads.

    Raises BoundedInvokeTimeout on timeout, or the last exception after retries
    are exhausted. The caller is expected to catch and degrade gracefully (e.g.
    fall back to a templated response).
    """
    # Caller-aware label for the timing logs so we can tell which call site is
    # the slow one (supervisor.nav vs M1.ask_next vs M1.classify_intent etc).
    # Walks one frame up; cheap and only runs at the start of an LLM call.
    import inspect
    caller = inspect.stack()[1]
    label = f"{Path(caller.filename).name}:{caller.function}"

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        # NB: don't use `with executor:` — its __exit__ does shutdown(wait=True),
        # which blocks on any leaked worker (the whole point of the timeout is
        # to NOT wait for stuck threads). Explicit wait=False keeps the cap real.
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        t0 = time.time()
        logger.info("LLM.invoke[%s] start (cap=%ss attempt=%d prompt_chars=%d)",
                    label, max_seconds, attempt + 1, len(str(prompt)))
        try:
            future = ex.submit(llm.invoke, prompt)
            try:
                result = future.result(timeout=max_seconds)
                logger.info("LLM.invoke[%s] OK in %.2fs", label, time.time() - t0)
                return result
            except concurrent.futures.TimeoutError:
                last_err = BoundedInvokeTimeout(
                    f"bounded_invoke exceeded {max_seconds}s (attempt {attempt+1})")
                logger.warning("LLM.invoke[%s] TIMEOUT after %.2fs (cap=%ss)",
                               label, time.time() - t0, max_seconds)
                future.cancel()
            except Exception as e:  # noqa: BLE001 - retry transient + propagate
                last_err = e
                logger.warning("LLM.invoke[%s] ERROR after %.2fs: %s",
                               label, time.time() - t0, type(e).__name__)
        finally:
            ex.shutdown(wait=False)
        if attempt < retries:
            time.sleep(backoff_s * (2 ** attempt))
    assert last_err is not None
    raise last_err


@dataclass
class ModuleStepResult:
    """What a module's step() returns to the graph runner."""
    assistant_message: str
    context_patch: dict
    transition: bool                 # True → done; supervisor takes over
    needs_user_reply: bool = False
    tool_calls_json: dict | None = None    # SP3 — widget render hint, or None
    # SP5: additional AIMessages the graph node should emit after the primary
    # assistant_message. Used by M4 to stream per-step execution results.
    # Default empty list keeps SP3/SP4 callers untouched.
    extra_messages: list = field(default_factory=list)


class ModuleAgent(ABC):
    """Shared clarification loop. Subclasses override schema/prompt/tools/module_key."""

    schema: type[BaseModel]
    module_key: str
    system_prompt: str
    tools: list[Any]

    # Set of schema fields that should render as a card grid when asked.
    # The card options are generated dynamically per turn via an LLM call
    # seeded from the already-filled partial state, so suggestions adapt
    # to context (e.g. when research_title="AI in education" is filled, the
    # `field` cards lean toward EdTech / Pedagogy / AI Ethics instead of
    # the generic Marketing / Management list). Subclasses opt in by setting
    # this and `card_field_titles`. Empty = no cards (free-text input).
    card_fields: set[str] = set()

    # Human-readable card-grid headers per field. Falls back to a generic
    # "Which <field name> fits best?" when a field isn't listed here.
    card_field_titles: dict[str, str] = {}

    # Set of schema fields that should render as an editable list (vs single
    # card pick). Initial items are LLM-suggested per turn — seeded from the
    # partial state — so the user gets a usable starting list they edit in
    # place. Right widget for `list[str]` schema fields like objectives /
    # research_questions where the user wants 2-5 items rather than a single
    # choice. Empty = no list editors.
    list_fields: set[str] = set()

    # Human-readable list-editor headers per field. Falls back to a generic
    # title when a field isn't listed here.
    list_field_titles: dict[str, str] = {}

    def _get_llm(self):
        # Per-call timeout caps how long a single Gemini request can hang.
        # Without it, a stalled API call wedges the whole conversation —
        # observed when intent classification + _is_affirmative + next-question
        # generation all queued behind a slow upstream. 20s is the conservative
        # ceiling: Gemini 2.5 Flash typically returns in 1-3s, anything past
        # ~10s is the API being unhealthy and we'd rather fail fast and let
        # the caller's except-fallback path run.
        return ChatGoogleGenerativeAI(
            model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
            temperature=0.4,
            timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
        )

    @staticmethod
    def _llm_max_seconds() -> int:
        """Wall-clock cap for one LLM invoke from a hot-path method.

        Used with bounded_invoke so a Gemini stall never blocks the whole
        graph turn. The request-level timeout=20 on _get_llm alone isn't
        enough — Gemini's internal retries can stretch wall-clock past it.

        12s default: Gemini 2.5 Flash normally answers a short prompt in 1-3s.
        Going much past 8-10s is a sign the API is unhealthy and the user
        is better served by a templated fallback than a long wait.
        """
        return int(os.getenv("ORCHESTRATOR_LLM_MAX_SECONDS", "12"))

    def _bounded(self, prompt, *, retries: int = 0):
        """Wall-clock-bounded shorthand for an LLM .invoke(prompt) call.

        Used everywhere in the hot path so a Gemini stall in ANY interactive-
        turn LLM call (classify intent, extract answer, ask next question,
        is_affirmative, generate cards/lists, explain/anchor) cannot freeze
        the whole graph turn — every caller already has an except-block that
        catches BoundedInvokeTimeout (subclass of Exception) and falls back.
        """
        return bounded_invoke(
            self._get_llm(), prompt,
            max_seconds=self._llm_max_seconds(),
            retries=retries,
        )

    def render_hint_for_field(self, field_name: str, partial: dict | None = None) -> dict | None:
        """Return a widget render hint for the next question, or None for free-text.

        Two declarative opt-ins in subclasses:
          - `card_fields`: single-choice card grid, LLM-generated options
            grounded in `partial`.
          - `list_fields`: editable multi-item list, LLM-seeded initial items
            grounded in `partial`. Right widget for `list[str]` schema slots.

        Falls back to None (free-text input) when LLM generation fails or
        yields nothing — the clarification loop still works without a widget.
        Subclasses override only for bespoke widget shapes (M3's themes /
        interview_guide use tool-driven list editors with nested sub_items).
        """
        if field_name in self.list_fields:
            items = self._generate_list_items(field_name, partial or {})
            if not items:
                return None
            title = self.list_field_titles.get(
                field_name,
                f"{field_name.replace('_', ' ').title()} — edit and confirm",
            )
            list_items = [
                ListItem(id=f"{field_name[:3]}_{i}", text=s)
                for i, s in enumerate(items)
            ]
            return ListEditorHint(
                field_name=field_name,
                title=title,
                initial_items=list_items,
                allow_nested=False,
            ).model_dump()

        if field_name not in self.card_fields:
            return None
        options = self._generate_card_options(field_name, partial or {})
        if not options:
            # Reported bug: M1 said 'Pick one of the cards below, or type your
            # own' but no cards rendered because the dynamic LLM call had
            # failed/timed out. Static fallback for literal-bounded fields
            # guarantees something always renders; if the subclass doesn't
            # define one for this field we still return None.
            options = self._static_card_options(field_name, partial or {})
            if not options:
                return None
        title = self.card_field_titles.get(
            field_name,
            f"Which {field_name.replace('_', ' ')} fits best?",
        )
        return CardGridHint(
            field_name=field_name,
            title=title,
            options=options,
            columns=3,
        ).model_dump()

    def _generate_list_items(self, field_name: str, partial: dict) -> list[str]:
        """Ask the LLM for 3-4 suggested string items for a list-shaped field.

        Seeded with the schema field description + partial state so the
        suggestions reflect what the user has already filled (e.g. an
        `objectives` list anchored on the research_title + research_type).
        Returns [] on LLM/parse failure so render_hint_for_field falls back
        to free-text input — the clarification loop still works without items.
        The user edits the suggested list in place (add / remove / change)
        before clicking Confirm in the list_editor widget — zero-typing path.
        """
        desc = self._field_description(field_name)
        context = json.dumps(
            {k: v for k, v in partial.items() if not k.startswith("_")},
            default=str, ensure_ascii=False,
        )
        prompt = (
            f"{self.system_prompt}\n\n"
            f"Generate 3 to 4 distinct, contextually relevant suggested items "
            f"for the schema list-field '{field_name}'.\n"
            f"Field description: {desc}\n\n"
            f"Already-filled fields for context:\n{context}\n\n"
            f"Rules:\n"
            f"- Each item must be a single concise sentence (under 30 words).\n"
            f"- For 'objectives'-shaped fields: lead with an action verb "
            f"(Measure, Examine, Compare, Identify, Evaluate, Investigate).\n"
            f"- For 'research_questions'-shaped fields: phrase each as a "
            f"question ending with '?'.\n"
            f"- All items must be coherent with the already-filled context.\n"
            f"- The user will edit the list in place — give them a strong "
            f"starting point, not exhaustive coverage.\n\n"
            f"Respond with ONLY a JSON array of strings. No prose, no markdown."
        )
        try:
            raw = self._bounded(prompt).content
            data = json.loads(_strip_code_fence(raw))
            if isinstance(data, list):
                return [str(x).strip() for x in data if x]
        except Exception:  # noqa: BLE001 - LLM/JSON failure is best-effort
            logger.exception(
                "%s list-item suggestion failed for %s",
                self.module_key, field_name,
            )
        return []

    def _static_card_options(self, field_name: str, partial: dict) -> list[CardOption]:
        """Deterministic fallback options used when the LLM card generator
        fails (timeout / non-JSON output / no schema-valid entries).

        Subclasses override for literal-bounded fields (e.g. research_type)
        where the option set is fixed and shouldn't depend on a flaky LLM
        call. Default returns [] — caller falls back to free-text input.
        """
        return []

    def _generate_card_options(self, field_name: str, partial: dict) -> list[CardOption]:
        """Ask the LLM for contextually relevant card options for `field_name`.

        Seeded with the schema field description + the partial state already
        filled by the user. Returns [] when the LLM call or parse fails so the
        caller can fall back to free-text input. Always asks the LLM to include
        an `Other / Specify` escape hatch so the user can type a custom value
        even when none of the cards fit.
        """
        desc = self._field_description(field_name)
        context = json.dumps(
            {k: v for k, v in partial.items() if not k.startswith("_")},
            default=str, ensure_ascii=False,
        )
        prompt = (
            f"{self.system_prompt}\n\n"
            f"Generate 5 to 7 distinct, contextually relevant card options to "
            f"help the user pick a value for the schema field '{field_name}'.\n"
            f"Field description: {desc}\n\n"
            f"Already-filled fields for context:\n{context}\n\n"
            f"Rules:\n"
            f"- Each card MUST be coherent with the already-filled context.\n"
            f"- value: short identifier <=30 chars (snake_case or PascalCase OK).\n"
            f"- label: human-readable display name <=30 chars.\n"
            f"- description: one short sentence explaining why this option fits "
            f"the user's situation specifically.\n"
            f"- Always include one final card with value='Other' and "
            f"label='Other / Specify' so the user can type a custom value.\n\n"
            f"Respond with ONLY a JSON array of "
            f"{{\"value\": str, \"label\": str, \"description\": str}} objects. "
            f"No prose, no markdown."
        )
        try:
            raw = self._bounded(prompt).content
            data = json.loads(_strip_code_fence(raw))
            if not isinstance(data, list):
                return []
            options: list[CardOption] = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                try:
                    options.append(CardOption(**entry))
                except ValidationError:
                    continue
            return options
        except Exception:  # noqa: BLE001 - LLM/JSON failure is best-effort
            logger.exception(
                "%s dynamic card generation failed for %s",
                self.module_key, field_name,
            )
            return []

    def step(self, state: OrchestratorState) -> ModuleStepResult:
        mode = state.get("mode", "interactive")
        partial = dict(get_module_slice(state["context_store"], self.module_key))

        if mode == "auto":
            return self._auto_fill(state, partial)

        # Interactive: check if we're awaiting a final confirmation from the user.
        if partial.pop("_awaiting_confirm", False):
            if self._is_affirmative(state["messages"]):
                # User confirmed — stamp confirmed_at and transition to next module.
                partial["confirmed_at"] = datetime.now(timezone.utc).isoformat()
                return ModuleStepResult(
                    assistant_message=f"Confirmed {self.module_key}. Moving on.",
                    context_patch=partial,
                    transition=True,
                )
            # User did not confirm — treat as a correction and re-ask missing fields.
            return self._ask_next_question(partial)

        # Interactive: check if we were waiting for the user to fill a specific field.
        awaiting_field = partial.pop("_awaiting_field", None)
        delegated_notice: str | None = None
        if awaiting_field:
            # Single LLM call (gemini-2.5-flash, ~$0.0001/turn) classifies the
            # user's intent + extracts the answer when applicable. Replaces
            # the previous keyword heuristics that were tripping on user
            # content: a labeled research_questions answer containing the
            # substring "what is" matched _CLARIFICATION_KEYWORDS and looped
            # the conversation forever. The LLM understands context.
            classification = self._classify_user_intent(state, awaiting_field, partial)
            intent = classification.get("intent", "answer")
            value = classification.get("value")

            if intent == "clarification":
                explanation = self._explain_and_reask(awaiting_field, partial)
                partial["_awaiting_field"] = awaiting_field
                return ModuleStepResult(
                    assistant_message=explanation,
                    context_patch=partial,
                    transition=False,
                    needs_user_reply=True,
                    tool_calls_json=self.render_hint_for_field(awaiting_field, partial),
                )

            if intent in {"off_topic", "meta", "frustration"}:
                # Concierge: address the digression like a human, then steer back
                # to the SAME field. Re-attach the field's widget so returning is
                # one click. The field stays pending — we captured no value.
                # Replaces the old behavior where off_topic silently re-asked with
                # no acknowledgement of what the user just said (cold/robotic).
                message = self._answer_and_anchor(state, intent, awaiting_field, partial)
                partial["_awaiting_field"] = awaiting_field
                return ModuleStepResult(
                    assistant_message=message,
                    context_patch=partial,
                    transition=False,
                    needs_user_reply=True,
                    tool_calls_json=self.render_hint_for_field(awaiting_field, partial),
                )

            if intent == "delegation":
                # User asked the agent to pick. Generate a reasonable value
                # and stash a notice for the next assistant message.
                suggested = self._suggest_field_value(awaiting_field, partial)
                if suggested is not None:
                    partial[awaiting_field] = suggested
                    delegated_notice = (
                        f"Got it — I'll go with **{suggested}** for "
                        f"`{awaiting_field}`. We can refine that later."
                    )
            elif intent == "answer":
                # Classifier already extracted the value when it was clear.
                # If it returned null but classified as "answer", fall back to
                # the dedicated extractor (tighter, field-specific prompt).
                if value is None:
                    value = self._extract_answer(state, awaiting_field)
                if value is not None:
                    partial[awaiting_field] = value
            # navigation: supervisor will re-route on the next graph tick.
            # off_topic / meta / frustration are handled above (answer-then-anchor).

        # Continue clarification: find the next missing field or summarize for confirm.
        result = self._ask_next_question(partial)
        if delegated_notice:
            # Prepend the notice so the user sees what was auto-filled BEFORE
            # the agent moves on to the next question.
            result.extra_messages = [AIMessage(content=delegated_notice)] + list(result.extra_messages or [])
        return result

    def _auto_fill(self, state, partial: dict) -> ModuleStepResult:
        """In auto mode, ask the LLM to fill all required fields at once silently."""
        seed = " ".join(
            text_of(m) for m in state["messages"]
            if isinstance(m, HumanMessage)
        )
        required = self._required_field_names()
        prompt = (
            f"{self.system_prompt}\n\n"
            f"You are operating in fully-silent auto-mode. Fill ALL fields of this schema "
            f"with reasonable best-guess defaults derived from the topic. Respond with ONLY "
            f"a JSON object matching this schema (no prose, no markdown).\n\n"
            f"Required fields: {required}\nTopic: {seed}\n"
            f"Already filled (do not change): "
            f"{json.dumps({k:v for k,v in partial.items() if k in required}, default=str)}"
        )
        resp = self._bounded(prompt).content
        try:
            filled = json.loads(_strip_code_fence(resp))
        except (json.JSONDecodeError, TypeError):
            logger.warning("%s auto-fill returned non-JSON: %r", self.module_key, resp[:200])
            filled = {}
        merged = {**partial, **filled,
                  "confirmed_at": datetime.now(timezone.utc).isoformat()}
        try:
            self.schema.model_validate(merged)
        except ValidationError as e:
            logger.warning("%s auto-fill validation: %s", self.module_key, e)
        return ModuleStepResult(
            assistant_message=f"[auto] Filled {self.module_key} from topic.",
            context_patch=merged,
            transition=True,
        )

    def _ask_next_question(self, partial: dict) -> ModuleStepResult:
        """Find the next missing required field and ask for it, or summarize for confirm."""
        missing = self._next_missing_field(partial)
        if missing is None:
            # All required fields filled — summarize and ask for user confirmation.
            summary = self._summarize_for_confirm(partial)
            partial["_awaiting_confirm"] = True
            # Attach a confirm-button widget so the user can one-click move on
            # instead of typing "yes" — and a "Let me edit" escape hatch for
            # corrections. The frontend synthesizes the click into a HumanMessage
            # whose content lands in `_is_affirmative`'s allow-list.
            confirm_hint = CardGridHint(
                field_name="_confirm",
                title=f"Ready to lock in {self.module_key}?",
                options=[
                    CardOption(
                        value="yes",
                        label="Confirm & continue",
                        description=f"Save {self.module_key} and start the next step.",
                    ),
                    CardOption(
                        value="no",
                        label="Let me edit",
                        description="Tell me what to change in your next message.",
                    ),
                ],
                columns=2,
            ).model_dump()
            return ModuleStepResult(
                assistant_message=f"Here's what we have:\n\n{summary}\n\nReady to move on?",
                context_patch=partial,
                transition=False,
                needs_user_reply=True,
                tool_calls_json=confirm_hint,
            )

        # Mark which field we're waiting on so the next step can extract the answer.
        partial["_awaiting_field"] = missing
        prompt = (
            f"{self.system_prompt}\n\n"
            f"You need the user to provide a value for the schema field '{missing}'. "
            f"Ask a single targeted question in friendly, plain language. Don't ask "
            f"for multiple fields at once. Don't restate the whole schema. Already "
            f"filled: {json.dumps({k:v for k,v in partial.items() if not k.startswith('_')}, default=str)[:1000]}"
        )
        # Wall-clock-bounded: a stalled Gemini call here used to hang the
        # whole turn (the "simple Hello hangs forever" live bug). On timeout
        # we fall back to a deterministic templated question so the user
        # always sees a prompt, never an infinite spinner.
        try:
            msg = bounded_invoke(
                self._get_llm(), prompt,
                max_seconds=self._llm_max_seconds(), retries=0,
            ).content.strip()
        except (BoundedInvokeTimeout, Exception):  # noqa: BLE001
            logger.exception("%s _ask_next_question LLM stalled/failed; "
                             "using templated question", self.module_key)
            human = str(missing).replace("_", " ")
            msg = f"What's your {human}?"
        # SP3: call the hook so subclasses can attach a widget render hint.
        # Pass `partial` so the default LLM card generator can ground its
        # suggestions in what the user has already filled.
        hint = self.render_hint_for_field(missing, partial)
        return ModuleStepResult(
            assistant_message=msg, context_patch=partial,
            transition=False, needs_user_reply=True,
            tool_calls_json=hint,
        )

    def _extract_answer(self, state, field_name: str) -> Any:
        """Ask the LLM to extract the field value from the user's latest message."""
        last_user = next(
            (text_of(m) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if not last_user:
            return None
        prompt = (
            f"Extract the value of '{field_name}' from this user reply. The schema "
            f"field type is described as: {self._field_description(field_name)}. "
            f"Respond with ONLY a JSON object {{\"field\": \"{field_name}\", "
            f"\"value\": <the value>}}. If the user answer is not a usable value, "
            f"respond with {{\"field\": \"{field_name}\", \"value\": null}}.\n\n"
            f"User reply: {last_user}"
        )
        try:
            data = json.loads(_strip_code_fence(self._bounded(prompt).content))
            return data.get("value")
        except (json.JSONDecodeError, TypeError):
            # Fall back to using the raw user message as the value.
            return last_user

    def _recent_dialogue(self, messages: list[BaseMessage], max_msgs: int = 8) -> str:
        """Compact transcript of the last few turns, for reference resolution.

        The conversation layer (intent classifier, concierge) needs recent
        context — "the second one", "yes", "like I said" are meaningless from a
        single message. We pass a WINDOW (last `max_msgs`), never the whole
        thread, to cap cost and avoid the LLM latching onto stale instructions.
        The AUTHORITATIVE task state still comes from the structured partial, not
        from this transcript.
        """
        recent = [m for m in messages if isinstance(m, (HumanMessage, AIMessage))][-max_msgs:]
        lines = []
        for m in recent:
            role = "User" if isinstance(m, HumanMessage) else "Assistant"
            lines.append(f"{role}: {text_of(m)}")
        return "\n".join(lines)

    def _classify_user_intent(self, state, field_name: str, partial: dict) -> dict:
        """One LLM call to classify the user's intent + extract the answer.

        Returns {"intent": str, "value": Any | None}. intent ∈ {answer,
        clarification, delegation, navigation, off_topic}.

        Replaces the previous keyword heuristics — those tripped on user
        content: a research_questions answer with bullets like "What is the
        average daily time..." substring-matched _CLARIFICATION_KEYWORDS
        ("what is") and looped the conversation forever. The LLM
        understands the difference between an answer that mentions a
        keyword and a question asking what the field means.

        Falls back to {"intent": "answer", "value": None} on LLM/parse
        failure so the caller's dedicated _extract_answer can still try.

        Cost note: one Gemini 2.5 Flash call per user turn (~$0.0001).
        Replaces the dedicated _extract_answer call in the happy path, so
        total LLM calls per turn is unchanged (1 classify+extract, then 1
        for next-question generation).
        """
        last_user = next(
            (text_of(m) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            "",
        )
        if not last_user:
            return {"intent": "off_topic", "value": None}

        desc = self._field_description(field_name)
        context = json.dumps(
            {k: v for k, v in partial.items() if not k.startswith("_")},
            default=str, ensure_ascii=False,
        )
        prompt = (
            f"You are classifying a user's reply during a research-project intake.\n"
            f"The user was asked to provide a value for the field '{field_name}'.\n"
            f"Field type/description: {desc}\n"
            f"Already-filled fields (context):\n{context}\n\n"
            f"Recent conversation (for resolving references like 'the first one', "
            f"'yes', 'like I said'):\n"
            f"{self._recent_dialogue(state.get('messages') or [])}\n\n"
            f"User's reply (the message to classify):\n{last_user}\n\n"
            f"Classify the user's intent. Return ONLY a JSON object:\n"
            f'  {{"intent": "<one of>", "value": <extracted value if intent="answer", else null>}}\n\n'
            f"Intent options (pick the SINGLE best match):\n"
            f'- "answer": the user is providing the value. Extract it matching the\n'
            f"  field type. For list fields return a list of strings; for string\n"
            f"  fields return a string. Strip labels like \"My objectives are:\" —\n"
            f"  keep only the actual content.\n"
            f'- "clarification": the user is asking what the field means or for\n'
            f'  an example (e.g. "what is scope?", "explain please", bare "?").\n'
            f'- "delegation": the user wants you to pick for them (e.g. "you\n'
            f'  decide", "I don\'t have a preference", "surprise me", "tùy bạn").\n'
            f'- "navigation": user wants to go back / skip / redo / jump elsewhere.\n'
            f'- "off_topic": user is asking about something unrelated to the field.\n'
            f'- "meta": the user is asking about the PROCESS itself — how long this\n'
            f"  will take, what you're doing, how many steps remain, whether they\n"
            f"  can save and come back.\n"
            f'- "frustration": the user is venting, stressed, anxious, or expressing\n'
            f"  doubt/overwhelm rather than answering the question.\n\n"
            f"CRITICAL: a long multi-item reply that happens to contain words\n"
            f'like "what is" or "for example" inside the answer content is\n'
            f'STILL "answer" — those keywords are part of the user\'s content.\n\n'
            f"No prose. No markdown. JSON only."
        )
        try:
            raw = self._bounded(prompt).content
            data = json.loads(_strip_code_fence(raw))
            intent = data.get("intent")
            if intent in {"answer", "clarification", "delegation",
                          "navigation", "off_topic", "meta", "frustration"}:
                return {"intent": intent, "value": data.get("value")}
        except Exception:  # noqa: BLE001 - classifier failure is best-effort
            logger.exception(
                "%s intent classification failed for %s",
                self.module_key, field_name,
            )
        return {"intent": "answer", "value": None}

    def _answer_and_anchor(self, state, intent: str, field_name: str, partial: dict) -> str:
        """Concierge reply: address the user's digression, then steer back.

        Handles off_topic / meta / frustration the human way — never ignore,
        never just re-ask. One LLM call produces: a brief acknowledgement/answer
        suited to the intent, a bridge, and a re-ask of the pending field. The
        caller re-attaches the field's widget so returning is a one-click action.

        Decision: previously off_topic fell straight through to _ask_next_question,
        which re-asked the field with NO acknowledgement of what the user said —
        cold and robotic. Answering first (then anchoring) is what makes the agent
        feel human while still keeping the task on track.
        """
        desc = self._field_description(field_name)
        context = json.dumps(
            {k: v for k, v in partial.items() if not k.startswith("_")},
            default=str, ensure_ascii=False,
        )
        recent = self._recent_dialogue(state.get("messages") or [])
        guidance = {
            "off_topic": (
                "The user asked something off-topic. Answer it in ONE short "
                "sentence (or say you'll handle it automatically later if it's a "
                "downstream concern), then gently bring them back."
            ),
            "meta": (
                "The user asked a process/meta question (how long, what are you "
                "doing, how many steps left). Answer briefly and reassuringly "
                "from the context, then bring them back."
            ),
            "frustration": (
                "The user sounds frustrated or anxious. Reply with brief, genuine "
                "empathy and remind them you can do the heavy lifting (offer to "
                "draft or pick sensible defaults so it's low-effort), then gently "
                "bring them back."
            ),
        }.get(intent, "Acknowledge briefly, then bring them back to the question.")
        prompt = (
            f"{self.system_prompt}\n\n"
            f"You are guiding a student through a research-project intake and are "
            f"currently waiting for them to provide the field '{field_name}' "
            f"({desc}).\n"
            f"Recent conversation:\n{recent}\n\n"
            f"Already-filled context:\n{context}\n\n"
            f"{guidance}\n\n"
            f"Write a SHORT, warm, human reply (2-3 sentences max). End by "
            f"re-asking for '{field_name}' in one friendly line. Match the user's "
            f"language (English or Vietnamese). Prose only — no markdown headers "
            f"or bullets."
        )
        return self._bounded(prompt).content.strip()

    def _explain_and_reask(self, field_name: str, partial: dict) -> str:
        """Produce a friendly explanation of `field_name` + re-ask the question.

        One LLM call returns BOTH the explanation and the re-asked question so
        the assistant message reads as a single coherent turn. The prompt is
        seeded with the partial state so the explanation references what the
        user already filled (e.g. "since your topic is X, scope here means…"),
        and asks for concrete examples grounded in that context — far more
        useful than a generic dictionary definition.
        """
        desc = self._field_description(field_name)
        context = json.dumps(
            {k: v for k, v in partial.items() if not k.startswith("_")},
            default=str, ensure_ascii=False,
        )
        prompt = (
            f"{self.system_prompt}\n\n"
            f"The user just asked for clarification about the schema field "
            f"'{field_name}'.\n"
            f"Field description: {desc}\n\n"
            f"Already-filled fields for context:\n{context}\n\n"
            f"Write a friendly 2-3 sentence explanation of what '{field_name}' "
            f"means in the context of THEIR research (reference the already-filled "
            f"fields). Then re-ask the question with 1-2 concrete examples "
            f"specific to their topic. Match the language of the user's most "
            f"recent message (English or Vietnamese). Respond with prose only — "
            f"no markdown headers, no bullets."
        )
        return self._bounded(prompt).content.strip()

    def _suggest_field_value(self, field_name: str, partial: dict):
        """User asked the agent to choose. Generate one reasonable value via LLM.

        Uses already-filled fields as context so the suggestion is coherent
        (e.g., research_title aligned with field and research_type).
        """
        context_summary = json.dumps(
            {k: v for k, v in partial.items() if not k.startswith("_")},
            default=str, ensure_ascii=False,
        )
        prompt = (
            f"{self.system_prompt}\n\n"
            f"The user has asked you to choose a value for the schema field "
            f"'{field_name}'. Generate ONE concrete, sensible value. The "
            f"schema field is described as: {self._field_description(field_name)}\n\n"
            f"Already-filled fields for context:\n{context_summary}\n\n"
            f"Respond with ONLY a JSON object: {{\"value\": <the value>}}."
        )
        try:
            data = json.loads(_strip_code_fence(self._bounded(prompt).content))
            return data.get("value")
        except (json.JSONDecodeError, TypeError):
            return None

    def _is_affirmative(self, messages: list[BaseMessage]) -> bool:
        """LLM-based affirmative check for the summary confirmation step.

        Replaces the hardcoded keyword set that missed natural phrasings like
        "yeah", "sure", "looks good", "yep go". Fast path: literal "yes"/"y"/
        "no"/"n" (what the Confirm button widget sends) skips the LLM call
        entirely. Everything else asks gemini-2.5-flash. Falls back to the
        old keyword set if the LLM call/parse fails so a bad API turn never
        wedges the conversation.
        """
        last_user = next(
            (text_of(m) for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )
        trivial = last_user.strip().lower()
        if not trivial:
            return False
        # Fast path — skip the LLM for unambiguous single-word confirms /
        # rejections. Covers the Confirm button widget (sends literal "yes"/"no")
        # AND every short phrasing real users type ("go", "ok", "sure", etc.).
        # Latency win + removes Gemini as a wedge point when it stalls.
        if trivial in {
            "yes", "y", "ok", "okay", "confirm", "go", "continue", "yep",
            "yeah", "sure", "alright", "lgtm", "looks good",
            "đồng ý", "ok rồi", "tiếp tục", "tốt rồi",
        }:
            return True
        if trivial in {"no", "n", "nope", "không"}:
            return False
        prompt = (
            f"The user was shown a summary of their research setup and asked "
            f"'Ready to move on?'.\n"
            f"User reply: {last_user}\n\n"
            f"Is this an affirmative confirmation (yes / sure / lock it in / "
            f"approve / go ahead — in any language)? Or is it a non-confirmation "
            f"(no / not yet / I want to change something)?\n\n"
            f'Respond with ONLY a JSON object: {{"confirm": true|false}}.'
        )
        try:
            raw = self._bounded(prompt).content
            data = json.loads(_strip_code_fence(raw))
            return bool(data.get("confirm"))
        except Exception:  # noqa: BLE001 - LLM/JSON failure is best-effort
            logger.exception("affirmative classification failed")
        # Fallback to the original allow-list so the conversation never wedges.
        return trivial in {
            "yes", "y", "ok", "okay", "confirm", "go", "continue", "yep",
            "đồng ý", "ok rồi", "tiếp tục",
        }

    def _summarize_for_confirm(self, partial: dict) -> str:
        """Build a human-readable bullet list of filled fields for the confirm
        prompt.

        Y: the previous implementation slammed `json.dumps(v)[:200]` on every
        value — strings got JSON quotes ("Identi" survived from a slice of a
        nested list), and lists got JSON brackets + commas that ate the
        budget so the second item truncated mid-word ("What are t"). Per-type
        rendering instead: strings plain, lists as their own bullets, dicts
        as key:value lines, and only very long strings get a word-boundary
        ellipsis. The user sees an actual readable summary.
        """
        lines: list[str] = []
        for k, v in partial.items():
            if k.startswith("_"):
                continue
            lines.append(f"- **{k}**: {self._format_summary_value(v)}")
        return "\n".join(lines)

    _SUMMARY_VALUE_MAX = 400  # generous: most M1 fields are 1-3 sentences

    def _format_summary_value(self, v) -> str:
        if isinstance(v, str):
            return self._truncate_on_word_boundary(v, self._SUMMARY_VALUE_MAX)
        if isinstance(v, list):
            if not v:
                return "(none)"
            if all(isinstance(item, str) for item in v):
                bullets = "\n".join(
                    f"  - {self._truncate_on_word_boundary(s, self._SUMMARY_VALUE_MAX)}"
                    for s in v
                )
                return "\n" + bullets
            # List of dicts (e.g. supporting_papers): render compact one-line each.
            bullets = "\n".join(
                f"  - {self._format_summary_value(item)}" for item in v
            )
            return "\n" + bullets
        if isinstance(v, dict):
            inner = ", ".join(
                f"{ik}: {self._format_summary_value(iv)}" for ik, iv in v.items()
            )
            return inner
        # Numbers, bools, dates — plain str() never truncates.
        return str(v)

    @staticmethod
    def _truncate_on_word_boundary(s: str, max_len: int) -> str:
        """Cut at the last whitespace before max_len and append … so the
        rendered text never ends mid-word. Falls back to a hard cut only if
        the entire string is one word longer than max_len (unlikely for
        natural-language M1 fields)."""
        if len(s) <= max_len:
            return s
        cut = s.rfind(" ", 0, max_len)
        if cut == -1:
            cut = max_len
        return s[:cut].rstrip() + "…"

    def _required_field_names(self) -> list[str]:
        """Return schema field names that are required, excluding confirmed_at (has a default)."""
        return [
            name for name, field in self.schema.model_fields.items()
            if field.is_required() and name != "confirmed_at"
        ]

    def _next_missing_field(self, partial: dict) -> str | None:
        """Return the first required field that is not yet filled, or None if all filled."""
        for name in self._required_field_names():
            v = partial.get(name)
            if v is None or v == "" or v == []:
                return name
        return None

    def _field_description(self, field_name: str) -> str:
        f = self.schema.model_fields.get(field_name)
        if f is None:
            return field_name
        return f"{f.annotation} — {f.description or 'no description'}"


def _strip_code_fence(s: str) -> str:
    """Remove leading/trailing markdown code fences from LLM responses."""
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()
