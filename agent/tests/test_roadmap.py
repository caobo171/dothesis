"""Pure-derivation tests for the coaching roadmap. Position is computed from
persisted artifacts (never model-narrated), so these assert the snap-to-nearest
milestone behavior directly, with no store or LLM."""
from agent.roadmap import ROADMAP, derive_substep


def _state(cs=None, status=None, focus="M1"):
    return {"contextStore": cs or {}, "status": status or {m: "locked" for m in ROADMAP},
            "focus": focus}


def test_m1_untouched_is_first_substep():
    assert derive_substep("M1", _state()) == "frame_topic"


def test_m1_title_only_advances_to_questions():
    assert derive_substep("M1", _state({"research_title": "T"})) == "derive_questions"


def test_m1_complete_returns_none():
    s = _state({"research_title": "T", "research_questions": ["Q"]})
    assert derive_substep("M1", s) is None


def test_m2_sources_but_no_gaps_is_find_gaps():
    assert derive_substep("M2", _state({"literature_sources": [{"title": "x"}]})) == "find_gaps"


def test_derived_substep_is_always_in_spine_or_none():
    for m in ROADMAP:
        sub = derive_substep(m, _state())
        assert sub is None or sub in ROADMAP[m]


# -- next_action (5-way precedence) ---------------------------------------
from agent.roadmap import next_action


def _full(status, cs=None, focus="M1"):
    return {"contextStore": cs or {}, "status": status, "focus": focus}


def test_open_blocker_wins():
    s = _full({"M1": "in_progress", "M2": "locked", "M3": "locked", "M4": "locked", "M5": "locked"},
              cs={"research_title": "T", "roadmap_tasks": [
                  {"id": "b1", "module": "M4", "substep": "interpret",
                   "title": "HTMT 0.91 fails", "why": "discriminant validity", "status": "open"}]},
              focus="M1")
    na = next_action(s)
    assert na["module"] == "M4" and "HTMT" in na["title"]


def test_needs_review_wins_over_advance():
    s = _full({"M1": "done", "M2": "needs_review", "M3": "locked", "M4": "locked", "M5": "locked"},
              cs={"research_title": "T", "research_questions": ["Q"]}, focus="M2")
    na = next_action(s)
    assert na["module"] == "M2" and "review" in na["why"].lower()


def test_advance_focus_when_clean():
    s = _full({"M1": "in_progress", "M2": "locked", "M3": "locked", "M4": "locked", "M5": "locked"},
              cs={"research_title": "T"}, focus="M1")
    na = next_action(s)
    assert na["module"] == "M1" and na["substep"] == "derive_questions"


def test_all_done_returns_none_or_export():
    s = _full({m: "done" for m in ["M1", "M2", "M3", "M4", "M5"]},
              cs={"final_sections": [{"x": 1}]}, focus="M5")
    na = next_action(s)
    assert na is None or na["substep"] == "export"


def test_null_safe_on_empty_state():
    # headless-produced state (no roadmap_tasks, minimal status) must not crash.
    assert next_action({"contextStore": {}, "status": {}, "focus": None}) is not None


def test_m5_has_review_before_export():
    from agent.roadmap import ROADMAP
    assert ROADMAP["M5"].index("review") < ROADMAP["M5"].index("export")


def test_all_done_offers_defense_prep():
    # F6: once everything is done, the terminal action leads into the mock
    # committee alongside export — the emotional peak, not just a file.
    from agent.roadmap import next_action
    s = {"contextStore": {"final_sections": [{"x": 1}]},
         "status": {m: "done" for m in ["M1", "M2", "M3", "M4", "M5"]}, "focus": "M5"}
    na = next_action(s)
    labels = " ".join(na.get("cta_options", [])).lower()
    assert "defense" in labels or "defence" in labels


def test_required_modules_skips_unordered_m4():
    # A 3-chapter order needs {M2, M3, M5}. When M1-M3 are done and the agent is
    # parked on M4, the roadmap must route to M5 (not keep grinding M4 analysis
    # the order never asked for — the wall-clock churn). Chat (required=None)
    # keeps the historical M4 behavior.
    from agent.roadmap import next_action
    st = {"focus": "M4", "contextStore": {},
          "status": {"M1": "done", "M2": "done", "M3": "done",
                     "M4": "in_progress", "M5": "locked"}}
    assert next_action(st)["module"] == "M4"                       # chat: unchanged
    assert next_action(st, required=frozenset({"M2", "M3", "M5"}))["module"] == "M5"
    # An order that DOES include Results still drives M4.
    assert next_action(st, required=frozenset({"M2", "M3", "M4", "M5"}))["module"] == "M4"


def test_required_modules_from_report_scope(monkeypatch):
    import agent.run_context as rc
    monkeypatch.setenv("DOTHESIS_REPORT_CHAPTERS", "intro,lit_review,methodology")
    rc.report_chapters.set(None)  # force the env-var path
    assert rc.required_modules() == frozenset({"M2", "M3", "M5"})
    monkeypatch.delenv("DOTHESIS_REPORT_CHAPTERS", raising=False)
    rc.report_chapters.set(None)
    assert rc.required_modules() is None
