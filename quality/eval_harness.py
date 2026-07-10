"""CI regression gate: score every fixture context_store and fail if any overall
drops below its recorded baseline. Run on prompt/model changes to catch quality
regressions (e.g. a Gemini<->Claude swap) before they ship."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from quality.rubric import score_thesis


def run_harness(fixtures_dir: str, baselines: dict[str, float],
                tolerance: float = 0.03) -> tuple[int, list[dict]]:
    # Decision: sort fixtures for deterministic output; a fixture with no
    # recorded baseline is scored + reported but never regresses (baseline None).
    rows: list[dict] = []
    regressed_any = False
    for fp in sorted(Path(fixtures_dir).glob("*.json")):
        if fp.name == "baselines.json":  # the manifest, not a thesis fixture
            continue
        cs = json.loads(fp.read_text(encoding="utf-8"))
        overall = score_thesis(cs)["overall"]
        base = baselines.get(fp.name)
        regressed = base is not None and overall < base - tolerance
        regressed_any = regressed_any or regressed
        rows.append({"fixture": fp.name, "overall": overall, "baseline": base,
                     "regressed": regressed})
    return (1 if regressed_any else 0), rows


if __name__ == "__main__":  # pragma: no cover
    here = Path(__file__).parent / "fixtures"
    base = json.loads((here / "baselines.json").read_text()) if (here / "baselines.json").exists() else {}
    code, rows = run_harness(str(here), base)
    for r in rows:
        print(f"{r['fixture']:<30} {r['overall']:.3f} (base {r['baseline']})"
              f"{'  ! REGRESSED' if r['regressed'] else ''}")
    sys.exit(code)
