"""Provenance ledger for computed statistics (roadmap #12, phase 2).

Pure + tiny-I/O. At the run_stats boundary the wrapper appends one JSONL row per
successful op to a workspace-local `stats_provenance.jsonl` sidecar (same posture
as the screening op's `_screened.csv`). At the M4 commit gate, deterministic code
matches the committed numbers against those rows and writes an
`analysis_provenance` summary — so the certificate can say WHICH numbers DoThesis
computed (and pinned to a dataset hash) versus which the student pasted.

No LangChain, no LLM. Reuses `claims_from_run_stats` for the value index so the
validator and the ledger can never disagree about what a result "contains". The
matcher only ever UPGRADES a claim's tier (computed > validated > unchecked), so
a tampered sidecar can at worst overstate the compute share — it can never
launder an impossible number past the hard validation gate. Fail-open
everywhere: capture/matching failures never break a commit or an export.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SIDECAR = "stats_provenance.jsonl"
_MAX_ROWS = 1000
_MAX_VALUES = 400
_VALUE_ONLY_FORBIDDEN = {"p", "n", "df", "bootstrap_samples"}   # too collision-prone


# --- dataset fingerprint ----------------------------------------------------

def dataset_fingerprint(path: str, rows: Optional[int] = None,
                        cols: Optional[int] = None) -> Optional[dict]:
    """Streamed sha256 over the raw file bytes. None (never raises) on any error."""
    try:
        p = Path(path)
        if not p.is_file():
            return None
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        out = {"file": str(path), "sha256": h.hexdigest()}
        if rows is not None:
            out["rows"] = int(rows)
        if cols is not None:
            out["cols"] = int(cols)
        return out
    except Exception:
        logger.debug("dataset_fingerprint failed for %s", path, exc_info=True)
        return None


# --- row builder ------------------------------------------------------------

def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _sha12(obj: Any) -> str:
    return hashlib.sha256(_canon(obj).encode()).hexdigest()[:12]


def _unit_label(unit: dict) -> Optional[str]:
    if not isinstance(unit, dict):
        return None
    return unit.get("path") or unit.get("construct") or unit.get("item")


def _value_triples(op: str, summary: dict) -> List[list]:
    from agent.stats_validation import claims_from_run_stats  # noqa: PLC0415
    triples: List[list] = []
    try:
        for c in claims_from_run_stats(op, summary):
            v = c.get("value")
            if not isinstance(v, (int, float)):
                continue
            triples.append([c.get("metric"), round(float(v), 4), _unit_label(c.get("unit") or {})])
            if len(triples) >= _MAX_VALUES:
                break
    except Exception:
        logger.debug("value-triple extraction failed for op=%s", op, exc_info=True)
    return triples


def _attest(op: str, params: dict, summary: dict) -> dict:
    """Small op-typed extract (design §4.3), bounded."""
    s = summary if isinstance(summary, dict) else {}
    if op == "power":
        return {k: s.get(k) for k in ("mode", "analysis", "required_n", "achieved_power")
                if s.get(k) is not None} | (
            {"justification": str(s["justification"])[:300]} if s.get("justification") else {})
    if op == "screening":
        out = {k: s.get(k) for k in ("n_before", "n_after", "mcar_p", "derived_file")
               if s.get(k) is not None}
        if isinstance(s.get("applied"), dict):
            out["applied"] = {k: bool(v) for k, v in s["applied"].items()}
        return out
    if op == "method_advice":
        rec = s.get("recommendation") or []
        return {"top": rec[0] if rec else None,
                "conflicts": len((s.get("conflict_with_choice") or {}).get("reasons") or [])
                if s.get("conflict_with_choice") else 0,
                "inputs_fingerprint": s.get("inputs_fingerprint")}
    if op == "mga":
        return {"comparison_defensible": s.get("comparison_defensible")}
    # pls_sem / others — nothing beyond digests; numbers live in `values`
    return {k: s.get(k) for k in ("bootstrap_samples",) if s.get(k) is not None} | {
        "q2": bool(s.get("q2"))}


def build_ledger_row(op: str, params: dict, summary: dict, dataset: Optional[dict],
                     seq: int) -> dict:
    from datetime import datetime, timezone  # noqa: PLC0415
    val = (summary.get("validation") if isinstance(summary, dict) else None) or None
    validation = {"passed": None}
    if isinstance(val, dict):
        validation = {"passed": val.get("passed"), "hard": val.get("hard", 0),
                      "soft": val.get("soft", 0)}
    engine = "unknown"
    try:
        import thesis_stats  # noqa: PLC0415
        engine = f"thesis_stats {thesis_stats.__version__}"
    except Exception:
        pass
    # exclude the attached validation block from the result digest (it is meta)
    result_for_digest = {k: v for k, v in (summary or {}).items() if k != "validation"}
    return {"seq": seq,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "op": op, "dataset": dataset,
            "params_fp": _sha12(params or {}), "result_digest": _sha12(result_for_digest),
            "values": _value_triples(op, summary or {}),
            "attest": _attest(op, params or {}, summary or {}),
            "validation": validation, "engine": engine}


# --- sidecar I/O ------------------------------------------------------------

def _sidecar_path(data_file_path: str) -> Path:
    return Path(data_file_path).with_name(_SIDECAR)


def _read_rows(path: Path) -> List[dict]:
    rows: List[dict] = []
    try:
        if not path.is_file():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue   # skip corrupt lines, keep the valid ones
    except Exception:
        logger.debug("sidecar read failed: %s", path, exc_info=True)
    return rows


def append_ledger_row(data_file_path: str, row: dict) -> bool:
    """Append `row` to the sidecar beside the data file, assigning seq = prev max
    + 1 and enforcing the 1000-row cap (newest kept). Fail-open → False."""
    try:
        path = _sidecar_path(data_file_path)
        existing = _read_rows(path)
        seq = (max((r.get("seq", 0) for r in existing), default=0) + 1)
        row = {**row, "seq": seq}
        combined = existing + [row]
        if len(combined) > _MAX_ROWS:
            combined = combined[-_MAX_ROWS:]   # prune oldest; min(seq) > 1 signals it
        path.write_text("\n".join(_canon(r) for r in combined) + "\n", encoding="utf-8")
        return True
    except Exception:
        logger.debug("append_ledger_row failed for %s", data_file_path, exc_info=True)
        return False


def load_ledger_rows(project_dir: str, *, max_files: int = 20, max_depth: int = 3) -> List[dict]:
    """Discover sidecars under project_dir (bounded rglob), merged + seq-sorted
    per file. Fail-open → []."""
    rows: List[dict] = []
    try:
        base = Path(project_dir)
        if not base.is_dir():
            return rows
        seen = 0
        for p in base.rglob(_SIDECAR):
            try:
                rel_depth = len(p.relative_to(base).parts)
            except Exception:
                rel_depth = max_depth + 1
            if rel_depth > max_depth:
                continue
            seen += 1
            if seen > max_files:
                break
            rows.extend(sorted(_read_rows(p), key=lambda r: r.get("seq", 0)))
    except Exception:
        logger.debug("load_ledger_rows failed for %s", project_dir, exc_info=True)
    return rows


def ledger_pruned(rows: List[dict]) -> bool:
    seqs = [r.get("seq", 0) for r in rows if isinstance(r.get("seq"), int)]
    return bool(seqs) and min(seqs) > 1


# --- matcher ----------------------------------------------------------------

def _norm(label: Optional[str]) -> Optional[str]:
    if label is None:
        return None
    from agent.stats_validation import _norm_path  # noqa: PLC0415
    return _norm_path(label) or str(label).strip()


def _index_ledger(rows: List[dict]):
    """(metric, norm_unit) -> set of rounded values ; plus per-seq value presence."""
    idx: Dict[tuple, List[tuple]] = {}
    for r in rows:
        seq = r.get("seq")
        for triple in (r.get("values") or []):
            if not isinstance(triple, list) or len(triple) != 3:
                continue
            metric, value, unit = triple
            if not isinstance(value, (int, float)):
                continue
            idx.setdefault((metric, _norm(unit)), []).append((round(float(value), 4), seq))
    return idx


def match_claims(claims: List[dict], ledger_rows: List[dict]) -> dict:
    """Classify each claim into computed | validated | unchecked and summarize
    (design §5). Never raises; matcher only upgrades tiers."""
    try:
        idx = _index_ledger(ledger_rows)
        coverage = {"computed": 0, "validated": 0, "unchecked": 0}
        by_table: Dict[str, Dict[str, int]] = {}
        seqs_matched: set = set()
        unmatched: List[str] = []
        ops_seen: Dict[str, int] = {}
        for r in ledger_rows:
            op = r.get("op")
            if op:
                ops_seen[op] = ops_seen.get(op, 0) + 1

        for c in claims:
            metric = c.get("metric")
            value = c.get("value")
            table = c.get("table") or (c.get("unit") or {}).get("table") or "other"
            unit_label = _unit_label(c.get("unit") or {})
            crashed = bool(c.get("crashed")) or c.get("source") == "free_text"
            tier = "validated"  # committed structured claim = internally consistent
            if crashed or not isinstance(value, (int, float)):
                tier = "unchecked"
            else:
                rv = round(float(value), 4)
                norm_unit = _norm(unit_label)
                matched = None
                # A unit-less claim can only be identified by value, so matching
                # it is "value-only" even via the direct lookup — forbid that for
                # the collision-prone metrics (a bare 0.05 must not become a p).
                unit_less_forbidden = norm_unit is None and metric in _VALUE_ONLY_FORBIDDEN
                if not unit_less_forbidden:
                    # unit-matched lookup first (required when the claim carries a unit)
                    for lv, seq in idx.get((metric, norm_unit), []):
                        if abs(lv - rv) < 5e-4 or _prec_match(lv, rv):
                            matched = seq
                            break
                # value-only fallback: only for unit-less, non-forbidden metrics
                if matched is None and norm_unit is None and metric not in _VALUE_ONLY_FORBIDDEN:
                    for (m, u), vals in idx.items():
                        if m != metric:
                            continue
                        for lv, seq in vals:
                            if abs(lv - rv) < 5e-4 or _prec_match(lv, rv):
                                matched = seq
                                break
                        if matched is not None:
                            break
                if matched is not None:
                    tier = "computed"
                    if isinstance(matched, int):
                        seqs_matched.add(matched)
            coverage[tier] += 1
            bt = by_table.setdefault(table, {"computed": 0, "validated": 0, "unchecked": 0})
            bt[tier] += 1
            if tier != "computed" and len(unmatched) < 10:
                lbl = f"{metric} {unit_label}" if unit_label else str(metric)
                unmatched.append(lbl)

        total = sum(coverage.values())
        datasets = []
        seen_hashes = set()
        for r in ledger_rows:
            ds = r.get("dataset")
            if isinstance(ds, dict) and ds.get("sha256") and ds["sha256"] not in seen_hashes:
                seen_hashes.add(ds["sha256"])
                datasets.append({"file": ds.get("file"), "sha256_12": ds["sha256"][:12],
                                 "rows": ds.get("rows"), "cols": ds.get("cols")})
        return {"coverage": {**coverage, "total": total}, "by_table": by_table,
                "datasets": datasets[:20],
                "ledger": {"rows_seen": len(ledger_rows),
                           "seqs_matched": sorted(seqs_matched)[:50],
                           "pruned": ledger_pruned(ledger_rows)},
                "ops_seen": ops_seen,
                "unmatched": unmatched[:10]}
    except Exception:
        logger.exception("match_claims failed")
        return {"coverage": {"computed": 0, "validated": 0, "unchecked": 0, "total": 0},
                "by_table": {}, "datasets": [], "ledger": {"rows_seen": 0, "seqs_matched": [],
                "pruned": False}, "ops_seen": {}, "unmatched": []}


def _prec_match(ledger_val: float, claim_val: float) -> bool:
    """A 2dp parsed claim matches a 4dp ledger value after rounding the ledger
    side to the claim's apparent precision."""
    for dp in (2, 3):
        if round(ledger_val, dp) == round(claim_val, dp):
            return True
    return False
