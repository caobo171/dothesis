"""The demand gate: no page without measured volume for its own primary query.

The cut rules are WELE's, unchanged, because the failure mode they prevent is
the same one: a batch of pages nobody searches for is what Google's spam policy
calls scaled content abuse, and the policy covers human-written pages too.

  * no volume returned          -> drop
  * volume under 10             -> drop, unless the family aggregate clears 500
  * difficulty above 40         -> defer
  * otherwise                   -> pass

The family exception is the only way a thin keyword survives, and a row that
survives on it is stamped `family-inferred` so `plan` can insert it as a draft
that is never scheduled until it is measured on its own.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from . import topic_bank_dir
from .expand import read_candidates

MIN_VOLUME = 10
FAMILY_AGGREGATE_FLOOR = 500
MAX_DIFFICULTY = 40

GATE_COLUMNS = ("keyword", "search_volume", "verdict", "reason")

# The five head terms measured through OpenSEO on 2026-09-07, used as the probe
# so the numbers can be compared against measured-heads-2026-09-07.tsv before
# any bulk spend.
PROBE_KEYWORDS = ("spss", "cronbach alpha", "thang đo likert",
                  "hồi quy tuyến tính", "mô hình nghiên cứu")


@dataclass(frozen=True)
class Measured:
    keyword: str
    search_volume: int | None
    family: str
    axis: str = ""
    kd: int | None = None


@dataclass(frozen=True)
class Verdict:
    keyword: str
    search_volume: int | None
    verdict: str  # pass | drop | defer
    reason: str
    axis: str = ""
    family: str = ""
    gate_status: str = ""  # measured | family-inferred, only meaningful on a pass


def apply_cuts(rows: list[Measured]) -> list[Verdict]:
    aggregate: dict[str, int] = {}
    for row in rows:
        if row.search_volume:
            aggregate[row.family] = aggregate.get(row.family, 0) + row.search_volume

    out: list[Verdict] = []
    for row in rows:
        volume = row.search_volume
        if not volume:  # None or 0
            out.append(Verdict(row.keyword, volume, "drop", "no volume returned",
                               row.axis, row.family))
            continue
        if row.kd is not None and row.kd > MAX_DIFFICULTY:
            out.append(Verdict(row.keyword, volume, "defer",
                               f"difficulty {row.kd} above {MAX_DIFFICULTY}",
                               row.axis, row.family))
            continue
        if volume < MIN_VOLUME:
            family_total = aggregate.get(row.family, 0)
            if family_total >= FAMILY_AGGREGATE_FLOOR:
                out.append(Verdict(row.keyword, volume, "pass",
                                   f"volume {volume} under {MIN_VOLUME}, family "
                                   f"'{row.family}' aggregate {family_total}",
                                   row.axis, row.family, "family-inferred"))
            else:
                out.append(Verdict(row.keyword, volume, "drop",
                                   f"volume {volume} under {MIN_VOLUME}, family "
                                   f"'{row.family}' aggregate {family_total} under "
                                   f"{FAMILY_AGGREGATE_FLOOR}",
                                   row.axis, row.family))
            continue
        out.append(Verdict(row.keyword, volume, "pass", f"volume {volume}",
                           row.axis, row.family, "measured"))
    return out


def read_measured_tsv(path: str) -> dict[str, tuple[int | None, int | None]]:
    """{keyword: (volume, kd)} from a TSV measured somewhere else (OpenSEO)."""
    out: dict[str, tuple[int | None, int | None]] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            keyword = (row.get("keyword") or "").strip()
            if not keyword:
                continue
            raw_volume = (row.get("search_volume") or "").strip()
            raw_kd = (row.get("kd") or "").strip()
            out[keyword] = (int(raw_volume) if raw_volume.isdigit() else None,
                            int(raw_kd) if raw_kd.isdigit() else None)
    return out


def write_gate_files(verdicts: list[Verdict], out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    by_axis: dict[str, list[Verdict]] = {}
    for v in verdicts:
        by_axis.setdefault(v.axis or "harvest", []).append(v)
    written = []
    for axis, rows in sorted(by_axis.items()):
        path = os.path.join(out_dir, f"gate-{axis}.tsv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            writer.writerow(GATE_COLUMNS)
            for r in rows:
                writer.writerow([r.keyword,
                                 "" if r.search_volume is None else r.search_volume,
                                 r.verdict, r.reason])
        written.append(path)
    return written


def read_gate_files(out_dir: str) -> dict[str, Verdict]:
    """Every gate verdict on disk, keyed by keyword. Used by `plan`."""
    out: dict[str, Verdict] = {}
    if not os.path.isdir(out_dir):
        return out
    for name in sorted(os.listdir(out_dir)):
        if not (name.startswith("gate-") and name.endswith(".tsv")):
            continue
        axis = name[len("gate-"):-len(".tsv")]
        with open(os.path.join(out_dir, name), encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                raw = (row.get("search_volume") or "").strip()
                volume = int(raw) if raw.isdigit() else None
                reason = row.get("reason") or ""
                verdict = row.get("verdict") or ""
                status = ""
                if verdict == "pass":
                    status = "family-inferred" if "aggregate" in reason else "measured"
                out[row["keyword"]] = Verdict(row["keyword"], volume, verdict, reason,
                                              axis, "", status)
    return out


def probe(client=None) -> dict:
    """Measure the five known head terms and report the cost. Nothing is written."""
    from .dataforseo import DataForSEOClient  # noqa: PLC0415 — httpx stays lazy

    client = client or DataForSEOClient()
    volumes, cost = client.search_volume(list(PROBE_KEYWORDS))
    return {"volumes": {k: volumes.get(k) for k in PROBE_KEYWORDS}, "cost_usd": cost}


def run(source: str = "dataforseo", candidates_path: str | None = None,
        measured_path: str | None = None, out_dir: str | None = None,
        client=None, limit: int | None = None) -> dict:
    """Measure candidates.tsv, cut, write gate-{axis}.tsv, report the spend."""
    candidates_path = candidates_path or os.path.join(topic_bank_dir(), "candidates.tsv")
    out_dir = out_dir or topic_bank_dir()
    candidates = read_candidates(candidates_path)
    if limit:
        candidates = candidates[:limit]

    cost = 0.0
    if source == "dataforseo":
        from .dataforseo import DataForSEOClient  # noqa: PLC0415

        client = client or DataForSEOClient()
        volumes, cost = client.search_volume([c.keyword for c in candidates])
        measured = {k: (v, None) for k, v in volumes.items()}
    elif source == "tsv":
        if not measured_path:
            raise ValueError("--source tsv needs --file pointing at the measured rows")
        measured = read_measured_tsv(measured_path)
    else:
        raise ValueError(f"unknown gate source {source!r}, expected dataforseo or tsv")

    rows = [Measured(keyword=c.keyword,
                     search_volume=measured.get(c.keyword, (None, None))[0],
                     kd=measured.get(c.keyword, (None, None))[1],
                     family=c.family, axis=c.axis)
            for c in candidates]
    verdicts = apply_cuts(rows)
    write_gate_files(verdicts, out_dir)

    summary = {
        "measured": len(candidates),
        "pass": sum(1 for v in verdicts if v.verdict == "pass"),
        "drop": sum(1 for v in verdicts if v.verdict == "drop"),
        "defer": sum(1 for v in verdicts if v.verdict == "defer"),
        "family_inferred": sum(1 for v in verdicts if v.gate_status == "family-inferred"),
        "volume_total": sum(v.search_volume or 0 for v in verdicts if v.verdict == "pass"),
        "cost_usd": cost,
    }
    print(f"gate: {summary['measured']} keywords measured via {source}")
    print(f"      {summary['pass']} pass ({summary['family_inferred']} family-inferred), "
          f"{summary['drop']} drop, {summary['defer']} defer")
    print(f"      passing volume {summary['volume_total']:,}/month")
    print(f"      API cost ${summary['cost_usd']:.4f}")
    return summary
