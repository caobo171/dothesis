"""Drive M1 through its clarification loop."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.agents.m1_topic import M1Agent
from orchestrator.state import ContextStore

pytestmark = pytest.mark.integration


def test_m1_interactive_fills_all_fields_across_turns(fake_llm_factory, monkeypatch):
    """Simulate a user answering each clarifying question in sequence."""
    user_answers = [
        "Leadership and employee engagement in Vietnamese SMEs",  # research_title
        "Marketing", "quantitative", "SME employees", "Vietnam, 2026",
        "Identify TL→EE drivers", "Does TL affect EE?", "yes",
    ]

    llm_responses = ["What's your research title?"]
    fields = ["research_title", "field", "research_type", "target_population",
              "scope", "objectives", "research_questions"]
    for i, fname in enumerate(fields):
        value_repr = (f'["{user_answers[i]}"]'
                      if fname in {"objectives", "research_questions"}
                      else f'"{user_answers[i]}"')
        llm_responses.append(f'{{"field": "{fname}", "value": {value_repr}}}')
        next_q = "Confirm and move on?" if i == len(fields) - 1 else f"Next question about {fname}?"
        llm_responses.append(next_q)

    fake = fake_llm_factory(*llm_responses)
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    cs = ContextStore()
    msgs = [HumanMessage(content="start")]

    for turn_idx, user_msg in enumerate(user_answers):
        state = {
            "messages": msgs, "current_module": "M1",
            "context_store": cs, "mode": "interactive",
            "user_intent": None, "pending_confirmations": [],
        }
        result = agent.step(state)
        cs.m1_topic = result.context_patch
        msgs = msgs + [AIMessage(content=result.assistant_message),
                       HumanMessage(content=user_msg)]
        if result.transition:
            break
    else:
        # The loop appended user_msg after each step(), so "yes" landed in msgs
        # only after the last iteration finished without triggering `break`.
        # Run one final step so the agent sees the "yes" confirmation message.
        state = {
            "messages": msgs, "current_module": "M1",
            "context_store": cs, "mode": "interactive",
            "user_intent": None, "pending_confirmations": [],
        }
        result = agent.step(state)
        cs.m1_topic = result.context_patch

    assert result.transition is True
    assert cs.m1_topic.get("confirmed_at") is not None
    for required in ("research_title", "field", "research_type",
                     "target_population", "scope"):
        assert cs.m1_topic.get(required), f"missing {required}: {cs.m1_topic}"
