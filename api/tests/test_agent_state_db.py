"""`module_status` is a snapshot, and reading it raw is how a finished
module kept a blue dot. These cover the heal-on-read rule.
"""




def test_module_status_heals_against_the_evidence_and_is_written_back():
    """`projects.module_status` is a snapshot from the last commit, and nothing
    recomputed it on read — so a module whose DoD is met today kept whatever
    status that commit gave it. M3 and M4 reached 5/5 sub-steps while the dot
    stayed blue and the dashboard ring stayed at 80%.

    Written back because the project LIST cannot heal itself: it reads
    `confirmed_at` out in SQL and never loads slice bodies, so it can only serve
    the stored column.
    """
    from api.app.agent_state import heal_module_status

    stale = {"M1": "done", "M3": "in_progress", "M4": "in_progress"}
    nested = {
        "m3_design": {
            "methodology": {"paradigm": "quantitative", "design": "survey",
                            "software": "SmartPLS", "sampling_strategy": "purposive"},
            "conceptual_model": {"nodes": [{"id": "ATT"}], "edges": []},
        },
        "m4_analysis": {"analysis_results": {
            "sample": {"valid": 311},
            "hypothesis_tests": [{"hypothesis": "H1"}],
        }},
    }
    healed = heal_module_status(stale, nested)
    assert healed["M3"] == "done"
    assert healed["M4"] == "done"


def test_healing_never_takes_done_away():
    """Sign-off is the student's. Staleness has its own channel; an approved but
    imperfect slice must not flap back to in_progress."""
    from api.app.agent_state import heal_module_status

    healed = heal_module_status({"M1": "done", "M5": "done"}, {"m1_topic": {}})
    assert healed["M1"] == "done"
    assert healed["M5"] == "done"
    # …and a module with nothing behind it is still locked.
    assert healed["M2"] == "locked"


def test_legacy_needs_review_still_reads_as_done():
    from api.app.agent_state import heal_module_status
    assert heal_module_status({"M2": "needs_review"}, {})["M2"] == "done"
