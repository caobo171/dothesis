"""Thesis simulator — drive M1->M5 end-to-end for easy testing.

ONE unified harness for both modes:
  - auto:        silent, fast, generates a full thesis non-interactively
  - interactive: an LLM "student" drives the chat using a brief

Features for low-friction testing:
  - Custom topic via --topic, or a full custom brief via --brief brief.yml
  - Live progress bar:  [M1 v] [M2 ...] [M3 _] [M4 _] [M5 _]  -> M2 (32s)
  - Per-turn SIGALRM timeout + 1 retry — kills the Gemini-stall problem (a
    single API hiccup no longer freezes the sim for 10 minutes)
  - Stubs S3 export + M2 DB session so the sim runs without AWS / live API
  - Persists to a viewable project under caotest171 with clean UI URLs
  - --no-persist for a dry run

Usage:
    set -a && source ../.env && set +a   # from the project root
    api/.venv/bin/python -m orchestrator.evals.sim_thesis            # auto, default brief
    api/.venv/bin/python -m orchestrator.evals.sim_thesis --interactive
    api/.venv/bin/python -m orchestrator.evals.sim_thesis --topic "AI ethics in healthcare"
    api/.venv/bin/python -m orchestrator.evals.sim_thesis --brief my_brief.yml
    api/.venv/bin/python -m orchestrator.evals.sim_thesis --no-persist

Implementation notes:
  - SIGALRM-based turn timeout is Unix-only (fine on macOS/Linux dev boxes).
  - Real-LLM E2E is non-deterministic — re-run if a single turn fails. The
    retry-once + bail behavior keeps total wall-time bounded.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Optional

sys.path.insert(0, os.path.join(os.getcwd(), "api"))
sys.path.insert(0, os.getcwd())

from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

# -----------------------------------------------------------------------------
# Default brief — override per-field via --brief file or override the topic
# alone via --topic. Designed so the sim runs end-to-end out of the box.
# -----------------------------------------------------------------------------
DEFAULT_BRIEF = {
    "name": "[SIM] TikTok x Gen Z purchase intention",
    "topic": ("The impact of TikTok short-form video engagement on Gen Z purchase "
              "intention for fashion brands in Vietnam"),
    "field": "Marketing",
    "research_type": "quantitative",
    "target_population": "Gen Z consumers aged 18-25 in Vietnam",
    "scope": "National, focusing on Hanoi and Ho Chi Minh City",
    "objectives": [
        "Measure the effect of TikTok engagement on Gen Z purchase intention",
        "Identify which engagement dimensions matter most",
    ],
    "research_questions": [
        "Does TikTok engagement affect Gen Z purchase intention?",
        "Which content types have the strongest effect?",
    ],
    "paradigm": "quantitative",
    "design": "PLS-SEM",
    "tool": "SmartPLS",
    "sampling_strategy": "convenience",
    "target_sample_size": 250,
    # M4 expects pasted statistical output. Realistic SmartPLS results so the
    # analysis step parses + the chapters have real data to discuss.
    "data_paste": (
        "SmartPLS 4 PLS-SEM Results (N=250)\n"
        "Measurement Model: TikTok Engagement (ENG) CR=0.89 AVE=0.67 (ENG1-5 loadings 0.78-0.86); "
        "Purchase Intention (PI) CR=0.91 AVE=0.72 (PI1-5 loadings 0.80-0.88). HTMT all <0.85.\n"
        "Structural Model: ENG -> PI beta=0.45 t=7.2 p<0.001 (supported). R^2(PI)=0.38. Q^2(PI)=0.27."
    ),
}

MODULE_FIELD = {"M1": "m1_topic", "M2": "m2_literature", "M3": "m3_design",
                "M4": "m4_analysis", "M5": "m5_writing"}
CAOTEST171 = "e503e789-74f9-4524-abe4-59115a08d0a3"


# -----------------------------------------------------------------------------
# Brief loading
# -----------------------------------------------------------------------------
def load_brief(brief_path: Optional[str], topic_override: Optional[str]) -> dict:
    brief = dict(DEFAULT_BRIEF)
    if brief_path:
        import yaml  # only needed when --brief is used
        with open(brief_path) as f:
            brief.update(yaml.safe_load(f) or {})
    if topic_override:
        brief["topic"] = topic_override
        brief["name"] = f"[SIM] {topic_override[:60]}"
    return brief


# -----------------------------------------------------------------------------
# Test seams — stub the things that need AWS / a live API server
# -----------------------------------------------------------------------------
def stub_external_tools() -> None:
    """Make the sim runnable without AWS S3 + without M2's PaperUpload DB.

    Keep every LLM call REAL so the test exercises the actual orchestrator.
    Also tighten M2's scout to a single topic variant (production default = 3)
    so the sim's M2 phase runs in ~2 min instead of ~6 min — the headline
    end-to-end speedup. Override with M2_SCOUT_TOPIC_COUNT before running.
    """
    os.environ.setdefault("M2_SCOUT_TOPIC_COUNT", "1")

    import orchestrator.agents.m2.agent as m2a

    class _FakeDb:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def query(self, *a, **k):
            m = MagicMock()
            m.filter_by.return_value.all.return_value = []
            return m
    m2a._open_db_session = lambda: _FakeDb()

    import orchestrator.agents.m5_writing as m5
    for tool, ext in (("export_docx", "docx"), ("compile_pdf", "pdf")):
        fk = MagicMock()
        fk.invoke.return_value = {
            "s3_key": f"dev/stub/thesis.{ext}",
            "download_url": f"/dev/stub/thesis.{ext}",
            "size_bytes": 12_000,
        }
        setattr(m5, tool, fk)


# -----------------------------------------------------------------------------
# Per-turn timeout (the headline reliability fix)
# -----------------------------------------------------------------------------
class TurnTimeout(Exception):
    """Raised when a single agent turn exceeds the configured wall-clock budget."""


@contextmanager
def turn_timeout(seconds: int):
    """SIGALRM-based hard timeout for a single agent turn.

    Real-LLM end-to-end is non-deterministic — individual Gemini calls
    occasionally stall past the orchestrator's internal 20s per-call timeout.
    A hard turn-level guard keeps a single stuck call from freezing the entire
    sim for 10 minutes. Unix-only; fine on macOS/Linux dev boxes.
    """
    def _on_alarm(signum, frame):
        raise TurnTimeout(f"turn exceeded {seconds}s wall-clock budget")
    prev = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev)


# -----------------------------------------------------------------------------
# Live progress bar
# -----------------------------------------------------------------------------
def _fmt(seconds: int) -> str:
    m, s = divmod(max(0, seconds), 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


class Progress:
    """Per-module status [_, ..., v] + elapsed total + time-in-current-module."""

    def __init__(self) -> None:
        self.t0 = time.time()
        self.status = {m: "_" for m in MODULE_FIELD}
        self.current = "M1"
        self._mod_start = self.t0

    def update(self, cs) -> None:
        for m, f in MODULE_FIELD.items():
            slice_ = getattr(cs, f, None) or {}
            if slice_.get("confirmed_at"):
                self.status[m] = "v"
            elif slice_:
                self.status[m] = "..."

    def set_current(self, mod: str) -> None:
        if mod in self.status and mod != self.current:
            self.current = mod
            self._mod_start = time.time()

    def bar(self) -> str:
        total = int(time.time() - self.t0)
        in_mod = int(time.time() - self._mod_start)
        parts = " ".join(f"[{m} {self.status[m]}]" for m in MODULE_FIELD)
        return f"{parts}  -> {self.current} ({_fmt(in_mod)}, total {_fmt(total)})"


class Heartbeat:
    """Background daemon that re-prints the progress bar every N seconds, so
    long-running phases (M2's 7-minute scout, M5's per-chapter composition)
    don't go silent. No production-code changes — pure test infrastructure.

    Also re-syncs Progress from the graph state on each tick so the bar reflects
    the CURRENT module (the stream event for a supervisor->module transition
    doesn't always carry a module-named node, so set_current via stream events
    alone lags; reading state["current_module"] catches the truth)."""

    def __init__(self, prog: Progress, interval_s: int = 30,
                 state_provider=None) -> None:
        self._prog = prog
        self._interval = interval_s
        self._provider = state_provider  # callable -> dict|None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        if self._interval > 0:
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_state_provider(self, fn) -> None:
        self._provider = fn

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                if self._provider:
                    st = self._provider()
                    if st:
                        cur = st.get("current_module")
                        if cur and cur in MODULE_FIELD:
                            self._prog.set_current(cur)
                        cs = st.get("context_store")
                        if cs is not None:
                            self._prog.update(cs)
            except Exception:
                pass
            print(f"  ... heartbeat: {self._prog.bar()}", flush=True)


# -----------------------------------------------------------------------------
# Auto mode — silent end-to-end
# -----------------------------------------------------------------------------
def run_auto(brief: dict, prog: Progress,
             heartbeat: Optional["Heartbeat"] = None) -> tuple[str, Optional[dict], list]:
    from orchestrator.graph import build_graph
    from orchestrator.state import ContextStore

    g = build_graph(interactive=False, checkpointer=MemorySaver())
    proj_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": proj_id}, "recursion_limit": 60}
    print(f"\nAUTO MODE  project={proj_id}")
    print(f"topic: {brief['topic']}\n")

    # Let the heartbeat sync from the live graph state so the bar reflects the
    # CURRENT module even between stream-emitted node events (M2 in particular
    # spends minutes inside a scout call with no intermediate node events).
    if heartbeat is not None:
        heartbeat.set_state_provider(lambda: g.get_state(cfg).values)

    final = None
    try:
        for ev in g.stream({
            "messages": [HumanMessage(content=brief["topic"])],
            "current_module": "M1",
            "context_store": ContextStore(),
            "mode": "auto",
            "project_id": uuid.UUID(proj_id),
            "user_intent": None,
            "pending_confirmations": [],
        }, config=cfg, stream_mode="updates"):
            for node, _payload in ev.items():
                if node in MODULE_FIELD:
                    prog.set_current(node)
                    try:
                        prog.update(g.get_state(cfg).values["context_store"])
                    except Exception:
                        pass
                    print(f"  >  {prog.bar()}", flush=True)
        final = g.get_state(cfg).values
    except Exception as e:
        print(f"  !! {type(e).__name__}: {e}", flush=True)
        try:
            final = g.get_state(cfg).values
        except Exception:
            pass
    return proj_id, final, []  # auto mode has no chat transcript


# -----------------------------------------------------------------------------
# Interactive mode — LLM "student" drives the chat
# -----------------------------------------------------------------------------
def make_student(brief: dict):
    """Return a `respond(agent_msg) -> reply` function backed by Gemini.

    Reads the brief + the agent's latest message and replies as a real student
    would — answer the question, confirm a summary, paste data when asked.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3, timeout=15)
    brief_lines = "\n".join(
        f"- {k}: {v}" for k, v in brief.items() if k not in ("data_paste", "name")
    )
    smartpls = brief.get("data_paste", "")

    def respond(agent_msg: str) -> str:
        prompt = (
            "You are role-playing a graduate student using an AI thesis assistant. "
            "Reply AS THE STUDENT in 1-2 sentences. Always move forward.\n"
            "RULES:\n"
            "- Answer the assistant's question using your BRIEF values.\n"
            "- For confirm/approve/lock-in/'looks good?' prompts: say 'Yes, looks good, continue.'\n"
            "- For data paste requests (SPSS / SmartPLS / output): paste the SmartPLS RESULTS verbatim.\n"
            "- Never ask the assistant a question. Never go off-topic.\n\n"
            f"YOUR BRIEF:\n{brief_lines}\n\n"
            f"SMARTPLS RESULTS (paste when asked for data):\n{smartpls}\n\n"
            f"ASSISTANT JUST SAID:\n{agent_msg}\n\n"
            "YOUR REPLY:"
        )
        try:
            return llm.invoke(prompt).content.strip()
        except Exception:
            return "Yes, looks good — please continue."

    return respond


def run_interactive(brief: dict, prog: Progress,
                    max_turns: int, per_turn_s: int,
                    heartbeat: Optional["Heartbeat"] = None) -> tuple[str, Optional[dict], list]:
    from orchestrator.graph import build_graph
    from orchestrator.state import ContextStore

    g = build_graph(interactive=True, checkpointer=MemorySaver())
    proj_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": proj_id}, "recursion_limit": 40}
    g.update_state(cfg, {
        "context_store": ContextStore(), "mode": "interactive",
        "current_module": "M1", "project_id": uuid.UUID(proj_id),
    })
    if heartbeat is not None:
        heartbeat.set_state_provider(lambda: g.get_state(cfg).values)
    print(f"\nINTERACTIVE MODE  project={proj_id}  max_turns={max_turns}  per_turn={per_turn_s}s")
    print(f"topic: {brief['topic']}\n")

    student = make_student(brief)
    transcript: list = []
    user_msg = f"Hi! I want to start my thesis: {brief['topic']}"

    def _run_one_turn(msg: str) -> list[str]:
        agent_said: list[str] = []
        for ev in g.stream({"messages": [HumanMessage(content=msg)],
                            "mode": "interactive"},
                           config=cfg, stream_mode="updates"):
            for node, payload in ev.items():
                if not isinstance(payload, dict):
                    continue
                if node in MODULE_FIELD:
                    prog.set_current(node)
                for m in (payload.get("messages") or []):
                    content = getattr(m, "content", "")
                    if content:
                        transcript.append(("assistant", content,
                                           node if node in MODULE_FIELD else None))
                        agent_said.append(content)
                        print(f"  agent[{node}] {content[:120]}", flush=True)
        return agent_said

    for turn in range(max_turns):
        transcript.append(("user", user_msg, None))
        print(f"\n[T{turn:02d}] {prog.bar()}")
        print(f"  user      {user_msg[:120]}", flush=True)
        agent_said: list[str] = []
        try:
            with turn_timeout(per_turn_s):
                agent_said = _run_one_turn(user_msg)
        except TurnTimeout as e:
            print(f"  !! {e} — retrying once", flush=True)
            try:
                with turn_timeout(per_turn_s):
                    agent_said = _run_one_turn(user_msg)
            except TurnTimeout:
                print(f"  XX second stall — bailing", flush=True)
                break
        except Exception as e:
            print(f"  !! {type(e).__name__}: {e}", flush=True)
            break

        state = g.get_state(cfg).values
        prog.update(state["context_store"])
        if state.get("current_module") == "DONE":
            print(f"\n  ✓ all modules confirmed", flush=True)
            break

        # Generate the student's next reply (also under timeout).
        try:
            with turn_timeout(20):
                user_msg = student("\n".join(agent_said) or "(no response)")
        except TurnTimeout:
            print(f"  !! student stalled — using fallback", flush=True)
            user_msg = "Yes, looks good — please continue."

    return proj_id, g.get_state(cfg).values, transcript


# -----------------------------------------------------------------------------
# Persist + summary
# -----------------------------------------------------------------------------
def persist(proj_id: str, brief: dict, final: dict, transcript: list) -> None:
    from app.db import get_session_factory
    from app.models import Project, ContextStore as DbCS, Thread, Message

    cs = final["context_store"]
    sf = get_session_factory()
    with sf() as db:
        p = Project(
            id=uuid.UUID(proj_id), user_id=uuid.UUID(CAOTEST171),
            name=brief["name"], field=brief.get("field"),
            language="en", citation_style="apa",
            current_module=final.get("current_module", "M1"), status="draft",
        )
        db.add(p); db.flush()
        tid = uuid.uuid4()
        db.add(Thread(id=tid, project_id=p.id, name="Main",
                      langgraph_thread_id=str(uuid.uuid4())))
        db.flush()  # FK: messages need the thread row present
        for role, content, tag in transcript:
            db.add(Message(thread_id=tid, role=role, content=content, module_tag=tag))
        db.add(DbCS(project_id=p.id, m1_topic=cs.m1_topic,
                    m2_literature=cs.m2_literature, m3_design=cs.m3_design,
                    m4_analysis=cs.m4_analysis, m5_writing=cs.m5_writing))
        db.commit()


def print_summary(proj_id: str, final: dict, transcript: list,
                  t0: float, persisted: bool) -> None:
    cs = final["context_store"]
    elapsed = int(time.time() - t0)
    print("\n" + "=" * 70)
    print(f"  SUMMARY  ({elapsed}s, {len(transcript)} messages)")
    print("=" * 70)
    for m, f in MODULE_FIELD.items():
        s = getattr(cs, f, None) or {}
        mark = "v" if s.get("confirmed_at") else ("..." if s else "_")
        fields = ", ".join(
            k for k in s if not k.startswith("_") and k != "confirmed_at"
        )[:60]
        print(f"  [{m} {mark:>3}]  {fields}")

    chapters = (cs.m5_writing or {}).get("chapters") or {}
    if chapters:
        print("\n  chapters:")
        for name, ch in chapters.items():
            n = len((ch or {}).get("prose", ""))
            print(f"    {name:14s} {n:>6,} chars")

    citations = len((cs.m2_literature or {}).get("citation_list") or [])
    if citations:
        print(f"\n  citations: {citations}")

    if persisted:
        print(f"\n  view:   http://localhost:3000/chat/projects/{proj_id}")
        print(f"  editor: http://localhost:3000/chat/projects/{proj_id}/editor")
    print("=" * 70 + "\n")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m orchestrator.evals.sim_thesis",
        description="End-to-end thesis simulator (auto + interactive).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--mode", choices=["auto", "interactive"], default="auto",
                   help="auto: silent full-thesis gen (default). "
                        "interactive: an LLM 'student' drives the chat.")
    p.add_argument("--brief", help="YAML file overriding default brief fields.")
    p.add_argument("--topic", help="Override only the topic (keeps other defaults).")
    p.add_argument("--max-turns", type=int, default=25,
                   help="Cap interactive turns (default 25).")
    p.add_argument("--per-turn-timeout", type=int, default=120,
                   help="Kill a stuck turn after N seconds, retry once (default 120).")
    p.add_argument("--no-persist", action="store_true",
                   help="Skip DB write (just print summary).")
    p.add_argument("--heartbeat", type=int, default=30,
                   help="Re-print the progress bar every N seconds during silent "
                        "phases like M2's scout. 0 to disable (default 30).")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    brief = load_brief(args.brief, args.topic)
    stub_external_tools()

    t0 = time.time()
    prog = Progress()
    heartbeat = Heartbeat(prog, interval_s=args.heartbeat)
    heartbeat.start()
    try:
        if args.mode == "auto":
            proj_id, final, transcript = run_auto(brief, prog, heartbeat=heartbeat)
        else:
            proj_id, final, transcript = run_interactive(
                brief, prog, args.max_turns, args.per_turn_timeout, heartbeat=heartbeat)
    finally:
        heartbeat.stop()

    if not final:
        print("\nXX no final state — run failed early", flush=True)
        sys.exit(1)

    persisted = False
    if not args.no_persist:
        try:
            persist(proj_id, brief, final, transcript)
            persisted = True
        except Exception as e:
            print(f"\n!! persist failed: {type(e).__name__}: {e}", flush=True)

    print_summary(proj_id, final, transcript, t0, persisted)


if __name__ == "__main__":
    main()
