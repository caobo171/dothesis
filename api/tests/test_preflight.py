"""Methods pre-flight (F8 Task 3): the advisory M3->M4 readiness audit.

preflight_check is pure and must tolerate BOTH context-store shapes the codebase
uses: the agent's FLAT store (M3-owned keys at top level, per load()) and the
NESTED {m3_design: {...}} view the rubric / load_full_context_store expose. Both
are exercised below so the F0 store-shape correction can't regress silently."""
from agent.preflight import preflight_check


def test_flags_missing_sample_and_reverse_coded():
    # Nested shape (as the rubric passes it): methodology + an empty instrument.
    cs = {"m3_design": {"methodology": "PLS-SEM", "instrument": {"items": []}}}
    missing = preflight_check(cs)
    assert any("sample" in m.lower() for m in missing)


def test_complete_m3_is_ready():
    cs = {"m3_design": {"methodology": "PLS-SEM",
                        "instrument": {"items": [{"reverse_coded": True}]},
                        "sample_plan": {"target_n": 200}, "cmb_plan": "Harman",
                        "missing_data_plan": "listwise"}}
    assert preflight_check(cs) == []


def test_flat_store_shape_is_read():
    # The agent's flat contextStore keeps M3-owned keys at the TOP level (no
    # m3_design wrapper). preflight_check must read them there too (F0 correction).
    flat_ready = {"methodology": "PLS-SEM",
                  "instrument": {"items": [{"reverse_coded": True}]},
                  "sample_plan": {"target_n": 150}, "cmb_plan": "marker variable",
                  "missing_data_plan": "pairwise"}
    assert preflight_check(flat_ready) == []
    # Drop the sample plan -> the flat read still flags it.
    del flat_ready["sample_plan"]
    assert any("sample" in m.lower() for m in preflight_check(flat_ready))


def test_missing_method_and_instrument_flagged():
    assert any("method" in m.lower() for m in preflight_check({}))
    assert any("instrument" in m.lower() for m in preflight_check({}))
