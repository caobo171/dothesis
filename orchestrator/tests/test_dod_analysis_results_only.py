"""Chapter 4 does not require raw data — a results export is enough.

The product rule: if the student uploads SmartPLS/SPSS output, there is nothing
left to collect and nothing left to compute. Results ARE the definition of
done, and demanding a raw dataset on top of a finished analysis asks them to
redo work their supervisor already accepted.

This pins the rule so a future tightening of `dod_analysis` cannot quietly
reintroduce a raw-data precondition.
"""
from orchestrator.artifacts import dod_analysis


def test_results_parsed_from_an_upload_satisfy_the_dod_without_raw_data():
    # Shape the doctor commits after parsing uploads/_Result.docx.txt. There is
    # no dataset anywhere in this slice, and there does not need to be.
    got = dod_analysis({
        "data_type_detected": "SmartPLS",
        "analysis_outline": {"research_design": "Định lượng, PLS-SEM"},
        "results": {
            "outer_loadings": [{"label": "ATT_1", "values": [0.854]}],
            "discriminant_validity": [{"label": "DEC", "values": [0.266]}],
        },
    })
    assert got.done is True, got.gaps


def test_an_empty_results_dict_is_still_not_done():
    got = dod_analysis({"data_type_detected": "SmartPLS",
                        "analysis_outline": {"research_design": "Định lượng"},
                        "results": {}})
    assert got.done is False
    assert "results is empty" in got.gaps


def test_results_is_an_m4_owned_key_so_the_doctor_can_persist_it():
    """The doctor writes `results` through commit_slice.

    `dod_analysis`'s docstring used to claim `results` and `data_type_detected`
    were "not M4-owned", which would have meant commit_slice silently dropping
    every number the doctor parsed. They are owned; this asserts it so the
    claim cannot drift back.
    """
    from agent.state import SLICE_OWNERSHIP
    assert "results" in SLICE_OWNERSHIP["M4"]
    assert "data_type_detected" in SLICE_OWNERSHIP["M4"]
