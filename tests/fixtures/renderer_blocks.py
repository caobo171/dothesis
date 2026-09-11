"""Fixtures for the M5 renderer tests — plain dicts, no I/O."""

PLS_BLOCK = {
    "descriptives": {"n": 234, "by_item": [{"item": "LS1", "mean": 3.8, "sd": 0.9},
                                            {"item": "PI1", "mean": 4.1, "sd": 0.7}]},
    "measurement_model": [
        {"construct": "LS", "items": [{"item": "LS1", "loading": 0.81}, {"item": "LS2", "loading": 0.78}],
         "cronbach_alpha": 0.86, "composite_reliability": 0.90, "ave": 0.62},
        {"construct": "PI", "items": [{"item": "PI1", "loading": 0.80}, {"item": "PI2", "loading": 0.76}],
         "cronbach_alpha": 0.84, "composite_reliability": 0.88, "ave": 0.58}],
    "discriminant_validity": {"method": "HTMT", "matrix": [["LS", "PI"], [1.0, 0.42], [0.42, 1.0]]},
    "hypothesis_tests": [{"id": "H1", "path": "LS -> PI",
                          "numbers": {"beta": 0.34, "t": 7.01, "p": "<0.001", "f2": 0.18},
                          "decision": "supported"}],
    "structural_model": {"r2": {"PI": 0.56}, "q2": {"PI": 0.31}, "tool": "SmartPLS"},
}

CBSEM_BLOCK = {
    "measurement_model": [
        {"construct": "TRUST", "items": [{"item": "t1", "loading": 0.81}, {"item": "t2", "loading": 0.79}],
         "cronbach_alpha": 0.86, "composite_reliability": 0.90, "ave": 0.64}],
    "hypothesis_tests": [{"id": "H1", "path": "TRUST -> INT",
                          "numbers": {"beta": 0.45, "se": 0.10, "z": 4.5, "p": "<0.001"},
                          "decision": "supported"}],
    "structural_model": {"r2": {"INT": 0.42}, "cfi": 0.95, "tli": 0.94, "rmsea": 0.05,
                         "srmr": 0.05, "chi2_df": 2.1},
}

CBSEM_FIT_PAYLOAD = {  # op-payload variant carrying a `fit` sub-dict
    "measurement_model": [{"construct": "X", "items": [{"item": "x1", "loading": 0.8}],
                           "cronbach_alpha": 0.8, "composite_reliability": 0.85, "ave": 0.6}],
    "fit": {"cfi": 0.96, "tli": 0.95, "rmsea": 0.04, "srmr": 0.04, "chi2_df": 1.8},
}

REGRESSION_BLOCK = {
    "hypothesis_tests": [{"id": "H1", "path": "X -> Y", "numbers": {"beta": 0.4, "t": 3.2, "p": "0.002"},
                          "decision": "supported"}],
    "structural_model": {"r2": {"Y": 0.31}},
}

SCREENING_BLOCK = {
    "data_screening": {
        "narrative": "Of 260 responses, 14 were removed for straight-lining and 6 as multivariate "
                     "outliers (Mahalanobis, p<.001). Missingness was MCAR (Little's test, p=.42); "
                     "mean imputation was applied to the remaining 240 cases.",
        "n_before": 260, "n_after": 240, "careless_removed": 14, "outliers_removed": 6},
}

FREE_TEXT_BLOCK = "H1 was supported (beta=0.34, p<0.001)."
LEGACY_STEP_BLOCK = {"results": {"step1": {"op": "pls_sem", "beta": 0.3}}}
PARTIAL_BLOCK = {"measurement_model": [{"construct": "A", "items": [{"item": "a1", "loading": 0.7}],
                                        "cronbach_alpha": 0.8, "composite_reliability": 0.85, "ave": 0.6}]}
MALFORMED_BLOCK = {"measurement_model": ["not a dict", {"construct": "B", "items": "bad",
                                                        "ave": None}]}

# The shape the CHAT agent actually commits: a list of {id, source, results}
# step blocks, not the dict every consumer reads. skills/dothesis-m4-analysis
# declares `analysis_results: AnalysisResult[]` (an array) while showing a dict
# payload, and the agent followed the declaration. Values copied from project
# 4c5f769a-7d96-4056-9a5d-a4e3654116ac, whose Chapter 4 exported with a complete
# SmartPLS run behind it and not one table in it.
AGENT_LIST_BLOCK = [
    {"id": "measurement_model", "source": "user-provided SmartPLS report",
     "results": {
         "r2": {"DEC": 0.575, "INT": 0.527},
         "f2": {"ATT_to_INT": 0.137, "INT_to_DEC": 0.858},
         "htmt_max": 0.661,
         "vif_range": "1.000-1.025",
         "outer_loadings": "All reported indicators > 0.7",
         "reliability_validity": [
             {"construct": "ATT", "alpha": 0.878, "rho_A": 0.894, "CR": 0.911, "AVE": 0.671},
             {"construct": "DEC", "alpha": 0.911, "rho_A": 0.912, "CR": 0.933, "AVE": 0.737},
             {"construct": "INT", "alpha": 0.905, "rho_A": 0.906, "CR": 0.930, "AVE": 0.725},
         ]}},
    {"id": "hypothesis_tests", "source": "user-provided SmartPLS bootstrapping report",
     "results": [
         {"hypothesis": "H2", "path": "ATT → INT", "beta": 0.257, "t": 7.49,
          "sd": 0.034, "p": "<0.001", "decision": "supported"},
         {"hypothesis": "H7", "path": "INT → DEC", "beta": 0.606, "t": 13.367,
          "sd": 0.045, "p": "<0.001", "decision": "supported"},
     ]},
]

NESTED_CS_WEAK = {
    "m3_design": {"sample_plan": {"power_analysis": {"recommended_n": 200,
                  "justification": "inverse square root (Kock & Hadaya, 2018)"}}},
    "m4_analysis": {"analysis_results": {
        "descriptives": {"n": 140},
        "discriminant_validity": {"method": "HTMT", "matrix": [["A", "B"], [1.0, 0.87], [0.87, 1.0]]},
        "hypothesis_tests": [{"id": "H2", "path": "A -> B", "numbers": {"beta": 0.05, "p": "0.41"},
                              "decision": "not supported"}],
        "data_screening": {"careless_removed": 8, "outliers_removed": 3}}},
}
NESTED_CS_CLEAN = {
    "m3_design": {"sample_plan": {"power_analysis": {"recommended_n": 150, "justification": "x"}}},
    "m4_analysis": {"analysis_results": {"descriptives": {"n": 220},
        "hypothesis_tests": [{"id": "H1", "path": "A -> B", "numbers": {"beta": 0.4, "p": "0.001"},
                              "decision": "supported"}]}},
}
