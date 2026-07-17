"""Advisory M3->M4 readiness check — the 'before you run SmartPLS' audit.

Pure, like assess_export_readiness: returns human-readable missing items (empty
list = ready). NEVER blocks M4 (Global Constraint: advisory, not a gate) — the
caller decides what to do with the findings.

Store-shape (F0 correction): the agent's contextStore is FLAT — the M3-owned
keys (`methodology`, `instrument`, `sample_plan`, `cmb_plan`, `missing_data_plan`)
live at the TOP level of load()["contextStore"]. The rubric and
load_full_context_store instead expose a NESTED {m3_design: {...}} view. We read
whichever shape we're handed by unwrapping an `m3_design` wrapper when present,
so the same function serves the agent tool AND the F3 rubric criterion without a
translation layer at each call site.
"""
from __future__ import annotations


def preflight_check(context_store: dict) -> list[str]:
    cs = context_store or {}
    # Accept both shapes: a nested {m3_design: {...}} view (rubric /
    # load_full_context_store) or the agent's flat store (M3 keys at top level).
    m3 = cs.get("m3_design")
    if not isinstance(m3, dict):
        m3 = cs
    inst = m3.get("instrument") or {}
    items = inst.get("items") or []
    missing: list[str] = []
    if not m3.get("methodology"):
        missing.append("M3 — analysis method not chosen (consult the design-test matrix).")
    if not items:
        missing.append("M3 — no questionnaire instrument yet.")
    _plan = m3.get("sample_plan") or {}
    if not _plan.get("target_n"):
        missing.append("Sample size not planned — run `sampling_plan` (it computes an a-priori "
                       "power analysis, not just a rule of thumb).")
    elif not _plan.get("power_analysis"):
        # A target_n from the heuristic alone can't answer "why n?" at the defense.
        missing.append("Sample size is planned but not power-justified — re-run `sampling_plan` "
                       "(or run_stats op=power) to get the a-priori N and its justification.")
    # A questionnaire with zero reverse-coded items usually means careless-
    # responding checks weren't designed in — flag it only once there ARE items.
    if items and not any(i.get("reverse_coded") for i in items):
        missing.append("No reverse-coded items flagged — check for careless responding.")
    # Method-vs-data advisability (roadmap #7): design-time conflict only (no
    # data here). Pure + fail-open; a mismatch is advisory, not a hard gap.
    if m3.get("methodology") and m3.get("conceptual_model"):
        try:
            from agent.method_advisor import advise, model_profile, normalize_method  # noqa: PLC0415
            chosen = normalize_method(m3.get("methodology"))
            adv = advise(profile=model_profile(m3["conceptual_model"], inst),
                         n=(m3.get("sample_plan") or {}).get("target_n"),
                         power_analysis=(m3.get("sample_plan") or {}).get("power_analysis"),
                         chosen=chosen, mode="design")
            if adv.get("conflict_with_choice"):
                missing.append("Chosen method may not fit the model — run "
                               "`run_stats(op='method_advice')`: " + adv["conflict_with_choice"]["sentence"])
        except Exception:
            pass  # advisory + pure; never let it break preflight
    if not m3.get("cmb_plan"):
        missing.append("No common-method-bias plan (e.g. Harman / marker variable).")
    if not m3.get("missing_data_plan"):
        missing.append("No missing-data handling plan — `run_stats(op='screening')` computes the "
                       "missingness profile, Little's MCAR test, and a recommended treatment.")
    return missing


def make_preflight_tool(store) -> "object":
    """Wrap preflight_check as a LangChain tool bound to a ProjectStateStore.

    Factory (closes over `store`) mirrors make_state_tools: the pure check lives
    above and is unit-tested; the tool just feeds it the project's live flat
    contextStore and shapes the result for the agent. Registered in
    agent/runtime.py's tool list so M4 can run it before analysis.
    """
    import json

    from langchain_core.tools import tool

    @tool
    def methods_preflight() -> str:
        """Run the M3->M4 methods pre-flight audit before any M4 analysis.

        Checks the design is analysis-ready: method chosen, instrument built,
        sample size planned, reverse-coded items present, common-method-bias and
        missing-data plans set. Returns the list of missing items (empty = ready).
        Advisory only — surface what's missing and offer to fix; never refuse M4.
        """
        cs = (store.load() or {}).get("contextStore") or {}
        missing = preflight_check(cs)
        return json.dumps({"ready": not missing, "missing": missing}, ensure_ascii=False)

    return methods_preflight

