"""Drive the interactive flow 0 -> full thesis with an LLM-based "student".

A Gemini "student" reads each agent message + a thesis brief and replies as a
real user would — answering questions, confirming, pasting data — so the
conversation drives M1->M5 regardless of how the agent phrases things (which a
fixed answer-map can't). Persists the conversation + context_store to a viewable
project under caotest171 so the chat + editor are inspectable in the UI.

Run:
    set -a && source .env && set +a && \\
    SIM_MAX_TURNS=25 api/.venv/bin/python -u -m orchestrator.evals.interactive_conversation_sim

Notes:
- Real-LLM end-to-end runs are non-deterministic — a single thesis pass typically
  burns 30-60 LLM calls + several Crossref lookups; some calls can stall on
  Gemini's side. Re-run if a single turn hangs > 90s.
- This is a tool for testing the live system, NOT a unit test.
- The S3 export tools are stubbed so a missing AWS bucket doesn't block the run;
  every other call (M1 cards, M2 scout, M3 design, M4 analysis, M5 chapters) is
  real LLM.
"""
import os, sys, uuid
sys.path.insert(0, os.path.join(os.getcwd(), "api")); sys.path.insert(0, os.getcwd())

from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver

import orchestrator.agents.m2.agent as m2agent
class _FakeDb:
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def query(self,*a,**k):
        m=MagicMock(); m.filter_by.return_value.all.return_value=[]; return m
m2agent._open_db_session = lambda: _FakeDb()
import orchestrator.agents.m5_writing as m5
for _t,_e in (("export_docx","docx"),("compile_pdf","pdf")):
    fk=MagicMock(); fk.invoke.return_value={"s3_key":f"dev/stub/thesis.{_e}","download_url":"/dev","size_bytes":1000}
    setattr(m5,_t,fk)

from orchestrator.graph import build_graph
from orchestrator.state import ContextStore

MODULE_FIELD = {"M1":"m1_topic","M2":"m2_literature","M3":"m3_design","M4":"m4_analysis","M5":"m5_writing"}

SMARTPLS = (
    "SmartPLS 4 PLS-SEM Results (N = 250)\n"
    "Measurement Model: TikTok Engagement (ENG) CR=0.89 AVE=0.67 (ENG1-5 loadings 0.78-0.86); "
    "Purchase Intention (PI) CR=0.91 AVE=0.72 (PI1-5 loadings 0.80-0.88). HTMT all < 0.85.\n"
    "Structural Model: ENG -> PI beta=0.45 t=7.2 p<0.001 (supported). R^2(PI)=0.38. Q^2(PI)=0.27."
)
BRIEF = f"""Working title: The impact of TikTok short-form video engagement on Gen Z purchase
intention for fashion brands in Vietnam
Field: Marketing. Research type: Quantitative.
Target population: Gen Z consumers aged 18-25 in Vietnam.
Scope: National, focusing on major cities (Hanoi and Ho Chi Minh City).
Objectives: (1) Measure the effect of TikTok engagement on Gen Z purchase intention for
fashion brands; (2) Identify which engagement dimensions matter most.
Research questions: RQ1 Does TikTok engagement affect purchase intention? RQ2 Which content
types have the strongest effect?
No papers to upload — use AI search for citations.
Design: PLS-SEM. Software: SmartPLS. Sampling: convenience. Target sample size: 250.
Data already collected. SmartPLS results to paste when asked for data:
{SMARTPLS}
"""

USER_LLM = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3,
                                  timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT","20")))

def simulate_user(agent_msg: str) -> str:
    prompt = (
        "You are role-playing a graduate student using an AI thesis-writing assistant. "
        "Read the assistant's latest message and reply AS THE STUDENT — concretely and "
        "briefly (1-2 sentences), always moving the thesis forward.\n\n"
        "RULES:\n"
        "- Answer exactly what is asked, using your brief.\n"
        "- If asked to confirm / approve / pick / choose / lock in — say 'Yes, looks good, "
        "let's continue.'\n"
        "- If it offers a default or to decide for you — accept it and continue.\n"
        "- If asked to paste data / SPSS / SmartPLS output — paste the SmartPLS results "
        "from your brief VERBATIM.\n"
        "- NEVER ask the assistant a question. NEVER go off-topic. NEVER say you don't know.\n\n"
        f"YOUR BRIEF:\n{BRIEF}\n\n"
        f"ASSISTANT JUST SAID:\n{agent_msg}\n\n"
        "YOUR REPLY (student only, no preamble):"
    )
    try:
        return USER_LLM.invoke(prompt).content.strip()
    except Exception:
        return "Yes, looks good — let's continue."


g = build_graph(interactive=True, checkpointer=MemorySaver())
proj_id = str(uuid.uuid4())
cfg = {"configurable": {"thread_id": proj_id}, "recursion_limit": 40}
g.update_state(cfg, {"context_store": ContextStore(), "mode": "interactive",
                     "current_module": "M1", "project_id": uuid.UUID(proj_id)})

transcript = []
user_msg = "Hi! I want to start my thesis: " + BRIEF.splitlines()[0]
print(f">>> project {proj_id}\n", flush=True)
last_progress = 0

import time
MAX_TURNS = int(os.getenv("SIM_MAX_TURNS", "20"))
t0 = time.time()
for turn in range(MAX_TURNS):
    transcript.append(("user", user_msg, None))
    print(f"\n[{time.time()-t0:5.0f}s][T{turn:02d}] 👤 {user_msg[:140]}", flush=True)
    agent_said = []
    try:
        for ev in g.stream({"messages": [HumanMessage(content=user_msg)], "mode": "interactive"},
                           config=cfg, stream_mode="updates"):
            for node, payload in ev.items():
                if not isinstance(payload, dict): continue
                for m in (payload.get("messages") or []):
                    c = getattr(m, "content", "")
                    if c:
                        tag = node if node in MODULE_FIELD else None
                        transcript.append(("assistant", c, tag))
                        agent_said.append(c)
                        print(f"[{time.time()-t0:5.0f}s] 🤖 [{node}] {c[:140]}", flush=True)
    except Exception as e:
        print(f"  !! {type(e).__name__}: {e}", flush=True); break

    state = g.get_state(cfg).values
    cur = state.get("current_module")
    if cur == "DONE":
        print("\n>>> ✅ DONE — thesis complete", flush=True); break
    # progress watchdog: bail if no new module confirmed in 12 turns
    nconf = sum(1 for mm in MODULE_FIELD if (getattr(state["context_store"], MODULE_FIELD[mm]) or {}).get("confirmed_at"))
    if nconf > last_progress: last_progress = nconf; stuck = 0
    else: stuck = locals().get("stuck", 0) + 1
    if stuck > 12:
        print("\n>>> ⚠️ no module progress in 12 turns — bailing", flush=True); break
    user_msg = simulate_user("\n".join(agent_said) or "(no response)")

final = g.get_state(cfg).values; cs = final["context_store"]
done = [m for m in ("M1","M2","M3","M4","M5") if (getattr(cs, MODULE_FIELD[m]) or {}).get("confirmed_at")]
print(f"\n>>> confirmed modules: {done}", flush=True)

from app.db import get_session_factory
from app.models import Project, ContextStore as DbCS, Thread, Message
sf = get_session_factory()
with sf() as db:
    p = Project(id=uuid.UUID(proj_id), user_id=uuid.UUID("e503e789-74f9-4524-abe4-59115a08d0a3"),
                name="[LLM CONVO] TikTok × Gen Z (interactive)", field="Marketing",
                language="en", citation_style="apa", current_module=final.get("current_module","M1"), status="draft")
    db.add(p); db.flush()
    tid = uuid.uuid4()
    db.add(Thread(id=tid, project_id=p.id, name="Main", langgraph_thread_id=str(uuid.uuid4())))
    db.flush()
    for role, content, tag in transcript:
        db.add(Message(thread_id=tid, role=role, content=content, module_tag=tag))
    db.add(DbCS(project_id=p.id, m1_topic=cs.m1_topic, m2_literature=cs.m2_literature,
                m3_design=cs.m3_design, m4_analysis=cs.m4_analysis, m5_writing=cs.m5_writing))
    db.commit()
print(f">>> DONE. {len(transcript)} messages. Project {proj_id} (caotest171).", flush=True)
