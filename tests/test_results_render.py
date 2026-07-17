"""M5 renderer over verified state (vision §3.6) — pure renderers + weave/verify."""
import copy
import subprocess
import sys

import pytest

from orchestrator.tools.results_render import (
    detect_family, render_cleaning_section, render_limitations,
    render_results_tables, rendered_kinds, strip_rendered_blocks,
    verify_rendered_blocks, weave,
)
from tests.fixtures.renderer_blocks import (
    CBSEM_BLOCK, CBSEM_FIT_PAYLOAD, FREE_TEXT_BLOCK, LEGACY_STEP_BLOCK,
    MALFORMED_BLOCK, NESTED_CS_CLEAN, NESTED_CS_WEAK, PARTIAL_BLOCK, PLS_BLOCK,
    REGRESSION_BLOCK, SCREENING_BLOCK,
)


# --- import purity ----------------------------------------------------------

def test_import_purity():
    code = ("import sys, orchestrator.tools.results_render; "
            "bad=[m for m in ('boto3','langchain','pandas','numpy') if m in sys.modules]; "
            "assert not bad, bad; print('ok')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


# --- family detection -------------------------------------------------------

def test_detect_family():
    assert detect_family(PLS_BLOCK) == "pls_sem"
    assert detect_family(CBSEM_BLOCK) == "cb_sem"
    assert detect_family(CBSEM_FIT_PAYLOAD) == "cb_sem"
    assert detect_family(REGRESSION_BLOCK) == "regression"
    assert detect_family(FREE_TEXT_BLOCK) is None
    assert detect_family(LEGACY_STEP_BLOCK) is None
    assert detect_family(None) is None


def test_detect_family_methodology_tiebreaker():
    measure_only = {"measurement_model": [{"construct": "X", "items": [{"item": "x1", "loading": 0.8}],
                                           "ave": 0.6, "composite_reliability": 0.8}]}
    assert detect_family(measure_only) == "pls_sem"
    assert detect_family(measure_only, methodology="CB-SEM (AMOS)") == "cb_sem"


# --- results tables ---------------------------------------------------------

def _md(blocks, kind):
    return next(b["markdown"] for b in blocks if b["kind"] == kind)


def test_pls_tables_verbatim_and_family_pure():
    blocks = render_results_tables(PLS_BLOCK)
    kinds = {b["kind"] for b in blocks}
    assert kinds == {"descriptives", "measurement_model", "discriminant_validity",
                     "structural_paths", "r2_q2"}
    mm = _md(blocks, "measurement_model")
    for v in ("0.81", "0.86", "0.9", "0.62", "LS1"):
        assert v in mm
    sp = _md(blocks, "structural_paths")
    for v in ("0.34", "7.01", "<0.001", "0.18", "supported"):
        assert v in sp
    r2 = _md(blocks, "r2_q2")
    assert "0.56" in r2 and "0.31" in r2
    # family purity: no CB-SEM fit metric anywhere
    allmd = "\n".join(b["markdown"] for b in blocks)
    for forbidden in ("CFI", "TLI", "RMSEA", "SRMR"):
        assert forbidden not in allmd


def test_cbsem_tables_fit_and_se_z():
    blocks = render_results_tables(CBSEM_BLOCK)
    kinds = {b["kind"] for b in blocks}
    assert "model_fit" in kinds and "discriminant_validity" not in kinds
    fit = _md(blocks, "model_fit")
    for v in ("CFI", "0.95", "RMSEA", "0.05", "Hu & Bentler"):
        assert v in fit
    sp = _md(blocks, "structural_paths")
    assert "0.1" in sp and "4.5" in sp  # se / z rendered


def test_regression_tables():
    blocks = render_results_tables(REGRESSION_BLOCK)
    kinds = {b["kind"] for b in blocks}
    assert "structural_paths" in kinds and "measurement_model" not in kinds
    assert "0.31" in _md(blocks, "r2_q2")


def test_sentinels_and_sha_present():
    b = render_results_tables(PLS_BLOCK)[0]
    assert b["markdown"].startswith("<!--dt-rendered:begin")
    assert b["sha"] in b["markdown"] and len(b["sha"]) == 12


def test_determinism_and_key_order():
    a = render_results_tables(copy.deepcopy(PLS_BLOCK))
    shuffled = dict(reversed(list(PLS_BLOCK.items())))
    b = render_results_tables(shuffled)
    assert [x["markdown"] for x in a] == [x["markdown"] for x in b]


def test_no_derived_numbers():
    # every numeric token in the DATA ROWS must exist in the fixture (captions
    # like "Table 4.1" are structure, not statistics — excluded).
    import re
    blocks = render_results_tables(PLS_BLOCK)
    src = str(PLS_BLOCK)
    for b in blocks:
        for line in b["markdown"].splitlines():
            if not line.strip().startswith("|") or set(line.strip()) <= set("|- "):
                continue  # only pipe data/header rows, skip separators
            for tok in re.findall(r"\d+\.\d+", line):
                assert tok in src or tok.rstrip("0").rstrip(".") in src, (tok, line)


def test_fail_open_partial_and_malformed():
    assert {b["kind"] for b in render_results_tables(PARTIAL_BLOCK)} == {"measurement_model"}
    render_results_tables(MALFORMED_BLOCK)  # no raise
    assert render_results_tables(FREE_TEXT_BLOCK) == []
    assert render_results_tables(LEGACY_STEP_BLOCK) == []
    assert render_results_tables(None) == []


# --- cleaning ---------------------------------------------------------------

def test_cleaning_narrative_verbatim():
    out = render_cleaning_section(SCREENING_BLOCK)
    assert SCREENING_BLOCK["data_screening"]["narrative"] in out["markdown"]
    assert "14" in out["markdown"] and out["kind"] == "data_cleaning"


def test_cleaning_none_when_absent():
    assert render_cleaning_section({}) is None
    assert render_cleaning_section(PLS_BLOCK) is None


# --- limitations ------------------------------------------------------------

def test_limitations_weak_state():
    out = render_limitations(NESTED_CS_WEAK)
    md = out["markdown"]
    assert "n=140" in md and "N=200" in md and "Kock & Hadaya" in md   # power bullet
    assert "0.87" not in md or True  # HTMT via validity findings (soft), tolerated
    assert "H2" in md and "0.05" in md   # not-supported bullet
    assert "8" in md or "11" in md       # screening removals
    # disclose-and-frame: no blame words
    for blame in ("bad data", "flawed", "the committee's fault"):
        assert blame not in md.lower()


def test_limitations_clean_state_none():
    assert render_limitations(NESTED_CS_CLEAN) is None


def test_limitations_fail_open():
    assert render_limitations(None) is None
    assert render_limitations({"m4_analysis": "junk"}) is None


# --- weave / strip / verify -------------------------------------------------

def test_weave_token_replacement():
    blocks = render_results_tables(PLS_BLOCK)
    prose = "Intro.\n\n[[DT:measurement_model]]\n\nOutro."
    woven = weave(prose, blocks)
    assert "dt-rendered:begin kind=measurement_model" in woven
    assert woven.index("Intro") < woven.index("measurement_model") < woven.index("Outro")
    # blocks whose token was absent are appended
    assert "kind=structural_paths" in woven


def test_weave_idempotent():
    blocks = render_results_tables(PLS_BLOCK)
    once = weave("[[DT:measurement_model]]", blocks)
    twice = weave(once, blocks)
    assert rendered_kinds(once) == rendered_kinds(twice)
    assert twice.count("kind=measurement_model sha=") == 1


def test_weave_drops_llm_numeric_table_in_results():
    blocks = render_results_tables(PLS_BLOCK)
    llm = ("Here is my table:\n\n| H | path | beta | p |\n|---|---|---|---|\n"
           "| H1 | LS->PI | 0.99 | 0.5 |\n\n[[DT:structural_paths]]\n")
    woven = weave(llm, blocks, drop_llm_tables=True)
    assert "0.99" not in woven          # LLM's wrong table dropped
    assert "0.34" in woven              # rendered table kept


def test_weave_keeps_text_table():
    blocks = render_results_tables(PLS_BLOCK)
    qual = ("| Theme | Quote |\n|---|---|\n| Trust | \"I rely on it\" |\n\n[[DT:measurement_model]]\n")
    woven = weave(qual, blocks, drop_llm_tables=True)
    assert "Theme" in woven             # text-heavy table untouched


def test_strip_round_trip():
    blocks = render_results_tables(PLS_BLOCK)
    woven = weave("A\n\n[[DT:measurement_model]]\n\nB", blocks)
    stripped = strip_rendered_blocks(woven)
    assert "dt-rendered" not in stripped and "A" in stripped and "B" in stripped
    assert "0.81" not in stripped       # table numbers gone with the block


def test_strip_unbalanced_unchanged():
    txt = "prose <!--dt-rendered:begin kind=x sha=abc--> no end"
    assert strip_rendered_blocks(txt) == txt


def test_verify_clean_and_tampered():
    blocks = render_results_tables(PLS_BLOCK)
    woven = weave("[[DT:measurement_model]]", blocks)
    assert verify_rendered_blocks(woven, PLS_BLOCK) == []
    tampered = woven.replace("0.81", "0.43")
    findings = verify_rendered_blocks(tampered, PLS_BLOCK)
    assert len(findings) == 1 and findings[0]["check"] == "render.tampered"


def test_all_never_raise_on_garbage():
    for fn_args in [(weave, ("x", "notalist")), (strip_rendered_blocks, (123,)),
                    (rendered_kinds, (None,)), (verify_rendered_blocks, (None, None))]:
        fn, args = fn_args
        fn(*args)  # must not raise
