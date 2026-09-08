"""The demand gate: measure what can be measured, record it, cut nothing.

Rewritten 2026-09-08 on the product owner's decision. The old rule was WELE's —
no page without measured volume for its own primary query — and it threw away
four candidates in five. Measured volume no longer has a veto; it only sets
priority order. A page is allowed to exist when it has real content, is
genuinely useful to a Vietnamese student doing a quantitative thesis, and does
not duplicate something already in the bank. Those three are quality questions
and `qa.py` answers them; this module now answers one question only: what does
the measurement source know about this keyword?

  * volume >= 10        -> pass, measured,   "volume N"
  * volume 0..9         -> pass, measured,   "volume N, thin"
  * no volume returned  -> pass, unmeasured, "no volume returned; quality gates decide"
  * difficulty over 40  -> still a pass, with "deprioritised" noted in the reason

Nothing drops and nothing defers any more. What used to be a cut is an ordering
input instead: `plan._round_robin` puts measured rows in the earliest tranches
because a page whose demand is known pays back sooner, and the QA gate holds an
unmeasured page to twice the distinctness bar, because for such a page quality
is the only thing standing between the bank and Google's scaled-content-abuse
policy. The verdict column stays because the gate files are a record: an
`unmeasured` row is a page we chose to write without evidence of demand, and
six months from now someone will want to know which ones those were.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from . import topic_bank_dir
from .expand import read_candidates

MIN_VOLUME = 10
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
    # `pass` is the only verdict this module writes now. `drop` and `defer`
    # still appear in the gate files committed before 2026-09-08, and
    # `read_gate_files` keeps reading them, so `plan` does not silently promote
    # a row an earlier run rejected.
    verdict: str
    reason: str
    axis: str = ""
    family: str = ""
    gate_status: str = ""  # measured | unmeasured


def classify(rows: list[Measured]) -> list[Verdict]:
    """A verdict for every row. Every row passes; the verdict records what is known.

    Named `classify` rather than the old `apply_cuts` because there are no cuts
    left to apply — keeping that name would have promised a filter this function
    no longer is.
    """
    out: list[Verdict] = []
    for row in rows:
        volume = row.search_volume
        if volume is None:
            # Absent from the source's answer. Not evidence of no demand — the
            # Google Ads endpoint simply returns nothing for long-tail Vietnamese
            # phrasings — so it is recorded as unknown, not as zero.
            reason = "no volume returned; quality gates decide"
            status = "unmeasured"
        else:
            # A measured 0 counts as measured: we asked and the number came
            # back. It is the thinnest thing in the bank and the volume sort in
            # `plan` already puts it last, so it needs no special case here.
            reason = f"volume {volume}" if volume >= MIN_VOLUME else f"volume {volume}, thin"
            status = "measured"
        if row.kd is not None and row.kd > MAX_DIFFICULTY:
            # Difficulty is advisory now. It used to defer the row; nothing
            # defers, so it rides along in the reason where the ordering and a
            # human reading gate-*.tsv can both see it.
            reason += f"; difficulty {row.kd} above {MAX_DIFFICULTY}, deprioritised"
        out.append(Verdict(row.keyword, volume, "pass", reason, row.axis, row.family,
                           status))
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
                # The volume column is the whole test: a pass with a number was
                # measured, a pass without one was not. That reads the files
                # written before 2026-09-08 correctly too — their family-carried
                # passes carry a number, their unmeasured fills do not — so no
                # reason-string parsing is needed any more.
                status = ""
                if verdict == "pass":
                    status = "measured" if volume is not None else "unmeasured"
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
    """Measure candidates.tsv, record the evidence, write gate-{axis}.tsv."""
    if fill_unmeasured:
        # Kept as a no-op so the committed pipeline scripts and skill docs that
        # pass it do not crash. It asked for exactly what now happens by default.
        print("gate: --fill-unmeasured is deprecated and does nothing. Since "
              "2026-09-08 an unmeasured candidate passes on its own.")
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
    verdicts = classify(rows)
    write_gate_files(verdicts, out_dir)

    summary = {
        "candidates": len(candidates),
        "pass": sum(1 for v in verdicts if v.verdict == "pass"),
        "measured": sum(1 for v in verdicts if v.gate_status == "measured"),
        "unmeasured": sum(1 for v in verdicts if v.gate_status == "unmeasured"),
        "thin": sum(1 for v in verdicts if v.reason.startswith("volume ")
                    and ", thin" in v.reason),
        "deprioritised": sum(1 for v in verdicts if "deprioritised" in v.reason),
        "volume_total": sum(v.search_volume or 0 for v in verdicts),
        "cost_usd": cost,
    }
    print(f"gate: {summary['candidates']} candidates through {source}, "
          f"{summary['pass']} pass (nothing is cut)")
    print(f"      {summary['measured']} measured ({summary['thin']} thin), "
          f"{summary['unmeasured']} unmeasured "
          f"({summary['deprioritised']} deprioritised on difficulty)")
    print(f"      passing volume {summary['volume_total']:,}/month")
    print(f"      API cost ${summary['cost_usd']:.4f}")
    return summary
