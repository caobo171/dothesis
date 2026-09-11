

def test_rho_a_column_appears_only_when_the_study_has_it():
    """SmartPLS reports rho_A next to α and CR, and a PLS thesis is expected to
    show it. It stays OPTIONAL by construction: _table_pruned drops any column
    with no value, so a study without rho_A never sees the header."""
    with_rho = {**PLS_BLOCK, "measurement_model": [
        {**PLS_BLOCK["measurement_model"][0], "rho_a": 0.87}]}
    md = {b["kind"]: b for b in render_results_tables(with_rho, "vi")}["measurement_model"]["markdown"]
    assert "rho_A" in md and "0.87" in md

    # PLS_BLOCK itself carries no rho_a — no column, no dashes pretending to.
    plain = {b["kind"]: b for b in render_results_tables(PLS_BLOCK, "vi")}["measurement_model"]["markdown"]
    assert "rho_A" not in plain
