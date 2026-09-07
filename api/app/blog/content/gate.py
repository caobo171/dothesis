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

`--fill-unmeasured` adds the second fallback the design allows (§5) for the
case we are actually in: DataForSEO is out of balance and OpenSEO can only
afford a sample of the 1,584 candidates. A candidate absent from the measured
TSV is judged on its family's sample instead of on itself, and it too is
stamped `family-inferred`, so an unmeasured page can only ever be a draft.
Without the flag an unmeasured candidate stays a `no volume returned` drop:
inventing demand by default is the failure this whole module exists to prevent.
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

# The family-sample rule for unmeasured candidates. Three measured siblings is
# the smallest sample where "half of them pass" is a fact rather than a coin
# toss, and the same aggregate floor applies as to the thin-keyword rule, so
# the two fallbacks cannot disagree about which families carry weight.
FAMILY_SAMPLE_MIN = 3
UNMEASURED_REASON_PREFIX = "unmeasured; "

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


def passes_on_its_own(row: Measured) -> bool:
    """The cut rules with no family help. This is the vote a sample row casts."""
    if not row.search_volume or row.search_volume < MIN_VOLUME:
        return False
    return row.kd is None or row.kd <= MAX_DIFFICULTY


def family_samples(rows: list[Measured],
                   measured_keywords: set[str]) -> dict[str, tuple[int, int, int]]:
    """{family: (measured rows, of which pass on their own, aggregate volume)}.

    Membership of the sample is presence in the measured TSV, not having volume:
    a measured 0 is evidence about the family and has to count, or a family
    would look stronger the fewer of its duds we bothered to measure.
    """
    out: dict[str, tuple[int, int, int]] = {}
    for row in rows:
        if row.keyword not in measured_keywords:
            continue
        size, passing, volume = out.get(row.family, (0, 0, 0))
        out[row.family] = (size + 1,
                           passing + (1 if passes_on_its_own(row) else 0),
                           volume + (row.search_volume or 0))
    return out


def _unmeasured_verdict(row: Measured, sample: tuple[int, int, int]) -> Verdict:
    size, passing, volume = sample
    reason = (f"{UNMEASURED_REASON_PREFIX}family {row.family!r} sample "
              f"{passing}/{size} pass, aggregate {volume:,}")
    carried = (size >= FAMILY_SAMPLE_MIN
               and passing * 2 >= size
               and volume >= FAMILY_AGGREGATE_FLOOR)
    if carried:
        return Verdict(row.keyword, None, "pass", reason, row.axis, row.family,
                       "family-inferred")
    return Verdict(row.keyword, None, "drop", reason, row.axis, row.family)


def apply_cuts(rows: list[Measured],
               measured_keywords: set[str] | None = None) -> list[Verdict]:
    """Verdicts for every row.

    `measured_keywords` is the set of keywords the measurement source actually
    answered for. Pass it (that is what `--fill-unmeasured` does) to judge the
    rest on their family's sample; leave it None and an unmeasured row falls
    through the ordinary `no volume returned` drop.
    """
    aggregate: dict[str, int] = {}
    for row in rows:
        if row.search_volume:
            aggregate[row.family] = aggregate.get(row.family, 0) + row.search_volume
    samples = family_samples(rows, measured_keywords) if measured_keywords is not None else {}

    out: list[Verdict] = []
    for row in rows:
        if measured_keywords is not None and row.keyword not in measured_keywords:
            out.append(_unmeasured_verdict(row, samples.get(row.family, (0, 0, 0))))
            continue
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
                    # Both fallbacks name themselves in the reason: the thin-keyword
                    # rule cites the family "aggregate", the unmeasured fill says
                    # "unmeasured". Either one is a draft, never a scheduled page.
                    inferred = "aggregate" in reason or "unmeasured" in reason
                    status = "family-inferred" if inferred else "measured"
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
        client=None, limit: int | None = None,
        fill_unmeasured: bool = False) -> dict:
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
    # The set of keywords the source actually answered for, which is what the
    # fill rule needs; without the flag it is not computed, so nothing changes.
    verdicts = apply_cuts(rows, set(measured) if fill_unmeasured else None)
    write_gate_files(verdicts, out_dir)

    filled = [v for v in verdicts
              if v.verdict == "pass" and v.reason.startswith(UNMEASURED_REASON_PREFIX)]
    summary = {
        "measured": len(candidates),
        "unmeasured": sum(1 for c in candidates if c.keyword not in measured),
        "pass": sum(1 for v in verdicts if v.verdict == "pass"),
        "drop": sum(1 for v in verdicts if v.verdict == "drop"),
        "defer": sum(1 for v in verdicts if v.verdict == "defer"),
        "pass_measured": sum(1 for v in verdicts if v.gate_status == "measured"),
        # `family_inferred` stays the thin-keyword rule's count so the number
        # keeps meaning what it did before the fill existed.
        "family_inferred": sum(1 for v in verdicts
                               if v.gate_status == "family-inferred") - len(filled),
        "unmeasured_filled": len(filled),
        "volume_total": sum(v.search_volume or 0 for v in verdicts if v.verdict == "pass"),
        "cost_usd": cost,
    }
    print(f"gate: {summary['measured']} keywords measured via {source}")
    print(f"      {summary['pass']} pass ({summary['pass_measured']} measured, "
          f"{summary['family_inferred']} family-inferred, "
          f"{summary['unmeasured_filled']} unmeasured-filled), "
          f"{summary['drop']} drop, {summary['defer']} defer")
    print(f"      passing volume {summary['volume_total']:,}/month")
    print(f"      API cost ${summary['cost_usd']:.4f}")
    return summary
