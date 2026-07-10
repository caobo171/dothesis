"""Shared sample-size power logic (F7 sampling_plan + F8 preflight).

Guidance rules, NOT a power-analysis engine — there's no effect-size / alpha /
power triplet here, just the rule-of-thumb minimums a supervisor expects a
quantitative thesis to defend (Hair et al. for PLS, Kline for CB-SEM, the
cases-per-predictor heuristic for regression). Defining them once means F7's
sampling_plan tool and F8's methods pre-flight can never quote different numbers.
"""
from __future__ import annotations


def target_sample_n(method: str, n_paths: int, n_indicators: int) -> tuple[int, str]:
    """Return (target_n, human-readable rule) for the chosen analysis method.

    - CB-SEM/AMOS: ≥200 and ≥10× indicators (Kline).
    - PLS-SEM: 10× the largest number of arrows into a construct (Hair et al.),
      floored at 60 so a tiny model still gets a defensible minimum.
    - Regression (default): ≥15 cases per predictor, floored at 50.
    """
    m = (method or "").lower()
    if "cb-sem" in m or "amos" in m:
        return max(200, 10 * n_indicators), "CB-SEM: >=200 and >=10x indicators (Kline)."
    if "pls" in m:
        return (max(60, 10 * max(1, n_paths)),
                "PLS-SEM: 10x the largest number of arrows into a construct (Hair et al.).")
    return max(50, 15 * max(1, n_paths)), "Regression: >=15 cases per predictor."
