"""Cross-chapter coherence (M3 ↔ M4 ↔ M5) — pure, offline, never raises.

Builds a hypothesis registry (derived at check time, never persisted) and runs
deterministic agreement checks: coverage (extends #1's X2), direction, decision,
and — the only HARD check — prose numbers that contradict the persisted
analysis_results. Everything word-shaped or structural is soft (natural-language
polarity/decision wording and machine-defaulted M3 directions are not provable;
#1's bar: only provably-wrong blocks). The HARD number check covers prose
sentences, HAND-TYPED markdown-table cells (extract_table_claims), and "N% of
variance" R² renderings (percent_variance_findings) — rendered tables are exempt
(they ARE the state). Deferred to a future LLM-judge: semantic coherence.

stdlib re/unicodedata only; reuses #1's pure helpers from agent.stats_validation.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Optional

from agent.stats_validation import _agg, _norm_path, _p_value

logger = logging.getLogger(__name__)

# The chapters whose prose reports and interprets results. `discussion` is gone
# with the five-chapter collapse — the discussion of findings is written inside
# the conclusion chapter.
_RESULT_CHAPTERS = ("results", "conclusion")


# --- id normalization -------------------------------------------------------

def normalize_hypothesis_id(x) -> Optional[str]:
    if isinstance(x, dict):
        for k in ("id", "label", "statement", "hypothesis", "text"):
            r = normalize_hypothesis_id(x.get(k))
            if r:
                return r
        return None
    if not isinstance(x, str):
        return None
    s = x.strip().lower()
    m = re.search(r"\bh[-\s]?(\d{1,2})\b", s)
    if m:
        return f"H{int(m.group(1))}"
    m = re.search(r"(?:hypothesis|giả thuyết|gt)\s*[:#-]?\s*(\d{1,2})", s)
    if m:
        return f"H{int(m.group(1))}"
    return None


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).lower() if isinstance(s, str) else ""


def _finding(check, severity, message, *, hypothesis=None, chapter=None,
             sentence=None, observed=None, expected=None, tolerance=None,
             source="prose") -> dict:
    """`sentence` is the offending text, so the student can FIND it.

    A finding that names only a chapter is not actionable: a results chapter is
    thousands of words, and "a paragraph states that ..." leaves the reader
    hunting. Carrying the sentence means the report can quote something
    searchable.
    """
    return {"check": check, "severity": severity, "message": message,
            "location": {"table": None, "construct": None, "item": None, "path": None,
                         "hypothesis": hypothesis, "chapter": chapter,
                         "sentence": sentence},
            "observed": observed, "expected": expected, "tolerance": tolerance, "source": source}


# --- prose extraction -------------------------------------------------------

def segment_sentences(prose: str) -> list[str]:
    if not isinstance(prose, str):
        return []
    # split on newlines and on [.!?] + whitespace + non-digit (keep decimals intact)
    parts = re.split(r"(?<=[.!?])\s+(?=\D)|\n+", prose)
    return [p.strip() for p in parts if p and p.strip()]


_ANCHOR = re.compile(r"\bh\s?-?\s?\d{1,2}\b|(?:hypothesis|giả thuyết)\s*\d{1,2}", re.I)


def _anchors(sentence: str) -> list[str]:
    ids = []
    for m in _ANCHOR.finditer(sentence):
        hid = normalize_hypothesis_id(m.group(0))
        if hid:
            ids.append(hid)
    return ids


_POS = ["tác động tích cực", "thuận chiều", "cùng chiều", "positively", "positive", "increases", "increase", "tăng"]
_NEG = ["tác động tiêu cực", "nghịch chiều", "ngược chiều", "negatively", "negative", "decreases", "decrease", "giảm"]
_NOT_SUP = ["không được ủng hộ", "không được chấp nhận", "bị bác bỏ", "not supported", "not accepted", "rejected"]
_SUP = ["được ủng hộ", "được chấp nhận", "supported", "accepted"]
_NOT_SIG = ["không có ý nghĩa thống kê", "không đáng kể", "no significant", "not significant", "non-significant"]
_SIG = ["có ý nghĩa thống kê", "significant"]


def _polarity(sentence: str) -> Optional[str]:
    s = _nfc(sentence)
    pos = any(w in s for w in _POS)
    neg = any(w in s for w in _NEG)
    if pos and not neg:
        return "positive"
    if neg and not pos:
        return "negative"
    return None


def _decision_word(sentence: str) -> Optional[str]:
    s = _nfc(sentence)
    not_sup = any(w in s for w in _NOT_SUP)
    sup = any(w in s for w in _SUP) and not not_sup
    not_sig = any(w in s for w in _NOT_SIG)
    sig = any(w in s for w in _SIG) and not not_sig
    if not_sup or not_sig:
        if sup or sig:
            return None
        return "not_supported"
    if sup or sig:
        return "supported"
    return None


_NUM = re.compile(
    r"(?P<metric>β|ß|\bbeta\b|hệ số\s*(?:hồi quy|đường dẫn|tác động)?|r²|r\^?2|\bt\b|f²|f\^?2|\bp\b)"
    r"\s*(?P<op>[<>=≤≥]?)\s*(?P<val>[-−–]?\s*\d*[.,]?\d+)", re.I)


def _metric_of(raw: str) -> Optional[str]:
    r = raw.lower().strip()
    if r in ("β", "ß", "beta") or r.startswith("hệ số"):
        return "beta"
    if r.startswith("r"):
        return "r2"
    if r == "t":
        return "t"
    if r.startswith("f"):
        return "f2"
    if r == "p":
        return "p"
    return None


def _parse_num(raw: str) -> tuple[Optional[float], int]:
    s = raw.replace("−", "-").replace("–", "-").replace(" ", "").replace(",", ".")
    if s.startswith("."):
        s = "0" + s
    elif s.startswith("-."):
        s = "-0" + s[1:]
    try:
        val = float(s)
    except ValueError:
        return None, 0
    dec = len(s.split(".")[-1]) if "." in s else 0
    return val, dec


def extract_number_claims(sentence: str) -> list[dict]:
    out = []
    for m in _NUM.finditer(sentence):
        metric = _metric_of(m.group("metric"))
        if metric is None:
            continue
        val, dec = _parse_num(m.group("val"))
        if val is None:
            continue
        claim = {"kind": "number", "metric": metric, "value": val, "decimals": dec,
                 "sentence": sentence[:160]}
        if metric == "p" and m.group("op") in ("<", "≤"):
            claim["threshold"] = True
        out.append(claim)
    return out


_TABLE_METRIC_HDR = {
    "beta": ("β", "ß", "beta", "hệ số", "path coef", "coefficient", "estimate", "std"),
    "t": ("t-value", "t value", "t-stat", "t stat", "|t|", " t "),
    "p": ("p-value", "p value", "p-val", "sig", " p "),
    "f2": ("f²", "f2", "f-squared"),
    "r2": ("r²", "r2", "r-squared"),
}


def _table_metric_of(header_cell: str) -> Optional[str]:
    h = f" {str(header_cell).strip().lower()} "
    for metric, needles in _TABLE_METRIC_HDR.items():
        if any(n in h for n in needles):
            return metric
    # bare single-letter headers
    b = h.strip()
    if b in ("β", "ß", "b"):
        return "beta"
    if b == "t":
        return "t"
    if b == "p":
        return "p"
    return None


def extract_table_claims(prose: str) -> list[dict]:
    """Number claims from HAND-TYPED markdown tables (gap 4): a `| H | β | t | p |`
    table row is a place a wrong number can hide from the sentence extractor.
    Rendered (sentinel-wrapped) tables are already stripped upstream, so only the
    LLM's own tables reach here. Emits the same claim shape as
    extract_number_claims, tagged with the row's hypothesis id. A row with no
    single identifiable H-id yields nothing (unchecked beats guessed)."""
    out: list[dict] = []
    if not isinstance(prose, str) or "|" not in prose:
        return out
    lines = [ln for ln in prose.splitlines() if ln.strip().startswith("|")]
    i = 0
    while i < len(lines) - 1:
        header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        sep = lines[i + 1].strip()
        if set(sep.replace("|", "").replace(" ", "")) <= set(":-") and "-" in sep:
            metric_cols = {j: _table_metric_of(h) for j, h in enumerate(header)}
            metric_cols = {j: m for j, m in metric_cols.items() if m}
            for row_line in lines[i + 2:]:
                if not row_line.strip().startswith("|"):
                    break
                cells = [c.strip() for c in row_line.strip().strip("|").split("|")]
                anchors = set()
                for c in cells:
                    hid = normalize_hypothesis_id(c)
                    if hid and _ANCHOR.search(c):
                        anchors.add(hid)
                if len(anchors) != 1:
                    continue           # ambiguous / anchorless row → skip
                hid = next(iter(anchors))
                for j, metric in metric_cols.items():
                    if j >= len(cells):
                        continue
                    val, dec = _parse_num(cells[j])
                    if val is None:
                        continue
                    out.append({"kind": "number", "metric": metric, "value": val,
                                "decimals": dec, "hid": hid,
                                "sentence": f"(table) {header} | {cells}"[:160]})
            i += 2
        else:
            i += 1
    return out


# --- registry ---------------------------------------------------------------

def _edges(cm: dict) -> list[dict]:
    return cm.get("edges") or cm.get("paths") or []


def _node_labels(cm: dict) -> dict:
    labels = {}
    for n in (cm.get("nodes") or []):
        if isinstance(n, dict):
            labels[n.get("id")] = n.get("label") or n.get("id")
    return labels


def build_registry(hypotheses, conceptual_model, analysis_results, m5) -> list[dict]:
    cm = conceptual_model if isinstance(conceptual_model, dict) else {}
    labels = _node_labels(cm)
    edge_by_id = {}
    for e in _edges(cm):
        if isinstance(e, dict):
            hid = normalize_hypothesis_id(e.get("id"))
            if hid:
                edge_by_id[hid] = e

    entries: dict[str, dict] = {}

    def _entry(hid):
        return entries.setdefault(hid, {"id": hid, "in_m3": False, "statement": None,
                                        "direction": None, "direction_source": None,
                                        "edge": None, "m4": {"present": False}, "m5": {"mentioned_in": [], "claims": []}})

    for h in (hypotheses or []):
        hid = normalize_hypothesis_id(h)
        if not hid:
            continue
        e = _entry(hid)
        e["in_m3"] = True
        if isinstance(h, str):
            e["statement"] = re.sub(r"^\s*h\d{1,2}\s*[:.-]?\s*", "", h, flags=re.I).strip() or None
        elif isinstance(h, dict):
            e["statement"] = h.get("statement") or h.get("text") or h.get("hypothesis")

    for hid, e in list(entries.items()):
        edge = edge_by_id.get(hid)
        if edge:
            et = str(edge.get("effect_type") or edge.get("effectType") or "").lower()
            if et in ("positive", "negative"):
                e["direction"], e["direction_source"] = et, "edge_effect_type"
            src, tgt = edge.get("source"), edge.get("target")
            e["edge"] = {"source": labels.get(src, src), "target": labels.get(tgt, tgt)}
            if not e["statement"] and edge.get("hypothesis"):
                e["statement"] = edge["hypothesis"]
        if e["direction"] is None and e["statement"]:
            e["direction"] = _polarity(e["statement"])
            if e["direction"]:
                e["direction_source"] = "statement_wording"

    # M4 side.
    block = analysis_results if isinstance(analysis_results, dict) else {}
    superseded: dict[str, int] = {}
    for ht in (block.get("hypothesis_tests") or []):
        if not isinstance(ht, dict):
            continue
        hid = normalize_hypothesis_id(ht.get("hypothesis")) or normalize_hypothesis_id(ht.get("id"))
        if not hid:
            continue
        e = _entry(hid)
        superseded[hid] = superseded.get(hid, 0) + 1
        nums = ht.get("numbers") or {}
        pv, thr = _p_value(nums.get("p")) if "p" in nums else (None, False)
        decision = ht.get("decision")
        e["m4"] = {
            "present": True, "result_id": ht.get("id"), "path": _norm_path(ht.get("path")),
            "decision": decision,
            "decision_supported": None if decision is None else str(decision).lower().startswith("support"),
            "significant": (pv is not None and pv < 0.05),
            "numbers": {"beta": nums.get("beta"), "t": nums.get("t"), "p": pv,
                        "p_is_threshold": thr, "f2": nums.get("f2")},
        }
    for hid, c in superseded.items():
        if c > 1:
            entries[hid]["m4"]["superseded_count"] = c - 1

    # structural R² by construct.
    r2_by_con = {}
    sm = block.get("structural_model") or {}
    for con, v in (sm.get("r2") or {}).items():
        if isinstance(v, (int, float)):
            r2_by_con[str(con).lower()] = float(v)

    # M5 side.
    chapters = _resolve_chapters(m5)
    for chap in _RESULT_CHAPTERS:
        prose = chapters.get(chap)
        if not prose or _is_stub(prose):
            continue
        for sent in segment_sentences(prose):
            anchors = _anchors(sent)
            for hid in set(anchors):
                if hid in entries and chap not in entries[hid]["m5"]["mentioned_in"]:
                    entries[hid]["m5"]["mentioned_in"].append(chap)
            if len(set(anchors)) == 1:
                hid = anchors[0]
                if hid not in entries:
                    continue
                for nc in extract_number_claims(sent):
                    nc.update({"chapter": chap, "attribution": "strong"})
                    entries[hid]["m5"]["claims"].append(nc)
                pol = _polarity(sent)
                if pol:
                    entries[hid]["m5"]["claims"].append({"kind": "direction", "value": pol,
                                                         "chapter": chap, "attribution": "strong", "sentence": sent[:160]})
                dec = _decision_word(sent)
                if dec:
                    entries[hid]["m5"]["claims"].append({"kind": "decision", "value": dec,
                                                        "chapter": chap, "attribution": "strong", "sentence": sent[:160]})
        # Hand-typed markdown tables in this chapter (gap 4) — route each row's
        # cells to the hypothesis the row names, feeding the same _number_checks.
        for tc in extract_table_claims(prose):
            hid = tc.pop("hid")
            if hid in entries:
                tc.update({"chapter": chap, "attribution": "strong"})
                entries[hid]["m5"]["claims"].append(tc)
    return list(entries.values())


def _strip_rendered(text):
    """Remove DoThesis-rendered table blocks (roadmap M5 renderer) before the
    coherence check reads numbers: a rendered block IS a byte-projection of the
    persisted state, so it cannot disagree with state — re-litigating it would be
    a false positive. The narrative AROUND the block stays fully checked. Lazy +
    fail-open: the renderer module must never break the gate."""
    if not isinstance(text, str) or "dt-rendered:begin" not in text:
        return text
    try:
        from orchestrator.tools.results_render import strip_rendered_blocks  # noqa: PLC0415
        return strip_rendered_blocks(text)
    except Exception:
        return text


def _canonical_chapters(items: dict) -> dict:
    """Chapter key -> prose, with retired keys resolved to canonical ones.

    Keys used to pass through verbatim, so a legacy project whose closing
    chapter is stored under `discussion` had no `conclusion` entry at all:
    `present` came out False, _co3 short-circuited, and the traceability check
    on that chapter could never fire — for exactly the in-flight projects the
    aliasing work exists to rescue. Non-chapter keys are left alone.

    Lazy + fail-open: coherence must never break because an import failed.
    """
    plain = {str(k).lower(): (v.get("prose") if isinstance(v, dict) else v)
             for k, v in items.items()}
    try:
        from orchestrator.tools.m5_writing import (  # noqa: PLC0415
            canonical_chapter, merge_chapter_prose)
    except Exception:
        return plain
    out = {k: v for k, v in plain.items() if canonical_chapter(k) is None}
    # merge_chapter_prose owns the both-closing-chapters rule (concatenate,
    # discussion first) so this reader sees the same Chapter 5 the export ships.
    out.update(merge_chapter_prose(plain.items()))
    return out


def _resolve_chapters(m5) -> dict:
    def _s(d):
        return {k: _strip_rendered(v) for k, v in d.items()}
    if isinstance(m5, dict) and any(k in m5 for k in ("results", "discussion", "conclusion", "intro")):
        # chapter values may be plain strings or {prose: ...} dicts (auto-mode).
        return _s(_canonical_chapters(m5))
    if isinstance(m5, list):
        try:
            from orchestrator.tools.m5_writing import chapters_from_final_sections  # noqa: PLC0415
            ch = chapters_from_final_sections(m5)
            if isinstance(ch, dict):
                return _s(_canonical_chapters(ch))
        except Exception:
            pass
        out = {}
        for s in m5:
            if isinstance(s, dict):
                out[str(s.get("title") or s.get("name") or "").lower()] = s.get("prose") or s.get("content")
        return _s(out)
    return {}


def _is_stub(prose) -> bool:
    if not isinstance(prose, str) or len(prose.strip()) < 20:
        return True
    low = prose.lower()
    return any(x in low for x in ("todo", "to be filled", "placeholder", "[unreadable]", "needs to be"))


# --- check catalogue --------------------------------------------------------

def coverage_findings(hypotheses, analysis_results) -> list[dict]:
    """CO1 (kept as xtable.hypothesis_coverage) + CO2 orphan_result. Normalized
    id matching (the shipped X2 used exact strings)."""
    if not isinstance(analysis_results, dict):
        # Free-text block: #1 already emits structure.unstructured; only M3-side
        # coverage misses matter and require a dict to compare — skip here.
        analysis_results = {}
    covered = set()
    for ht in (analysis_results.get("hypothesis_tests") or []):
        if isinstance(ht, dict):
            hid = normalize_hypothesis_id(ht.get("hypothesis")) or normalize_hypothesis_id(ht.get("id"))
            if hid:
                covered.add(hid)
    findings = []
    m3_ids = []
    for h in (hypotheses or []):
        hid = normalize_hypothesis_id(h)
        if hid and hid not in m3_ids:
            m3_ids.append(hid)
    for hid in m3_ids:
        if hid not in covered:
            findings.append({
                "check": "xtable.hypothesis_coverage", "severity": "soft",
                "message": f"Hypothesis {hid} has no result entry in the analysis.",
                "location": {"table": "hypothesis_tests", "construct": None, "item": None, "path": None},
                "observed": {"hypothesis": hid}, "expected": "a result for every hypothesis",
                "tolerance": None, "source": "parsed"})
    for hid in covered:
        if hid not in m3_ids:
            findings.append(_finding("coherence.orphan_result", "soft",
                                     f"Result entry {hid} has no matching hypothesis in M3.",
                                     hypothesis=hid, source="parsed"))
    return findings


def _eps(decimals: int) -> float:
    return 0.5 * (10 ** (-decimals))


def _number_checks(entry) -> list[dict]:
    out = []
    nums = (entry["m4"].get("numbers") or {}) if entry["m4"].get("present") else {}
    for claim in entry["m5"]["claims"]:
        if claim.get("kind") != "number":
            continue
        metric = claim["metric"]
        stored = nums.get(metric)
        if stored is None:
            continue
        eps = _eps(claim["decimals"])
        hard = claim.get("attribution") == "strong"
        check = "coherence.number_mismatch" if hard else "coherence.number_mismatch_weak"
        sev = "hard" if hard else "soft"
        if metric == "p":
            ok = _p_agrees(claim, stored, nums.get("p_is_threshold"))
            if not ok:
                out.append(_finding(check, sev,
                                    f"{entry['id']}: prose quotes p {'<' if claim.get('threshold') else '='} "
                                    f"{claim['value']} but the persisted p is {stored}.",
                                    hypothesis=entry["id"], chapter=claim.get("chapter"),
                                    observed={"sentence": claim["sentence"], "value": claim["value"]},
                                    expected=stored, tolerance=eps))
            continue
        if abs(float(stored) - claim["value"]) > eps:
            out.append(_finding(check, sev,
                                f"{entry['id']}: prose quotes {metric} = {claim['value']} but the persisted "
                                f"value is {stored}.", hypothesis=entry["id"], chapter=claim.get("chapter"),
                                observed={"sentence": claim["sentence"], "value": claim["value"]},
                                expected=stored, tolerance=eps))
    return out


def _p_agrees(claim, stored, stored_is_threshold) -> bool:
    if claim.get("threshold"):  # prose "p < X"
        thr = claim["value"]
        return float(stored) < thr + _eps(claim["decimals"])
    # prose "p = X" exact
    return abs(float(stored) - claim["value"]) <= _eps(claim["decimals"])


def _direction_checks(entry) -> list[dict]:
    out = []
    beta = (entry["m4"].get("numbers") or {}).get("beta") if entry["m4"].get("present") else None
    # DI1: M3 direction vs β sign.
    if entry.get("direction") in ("positive", "negative") and isinstance(beta, (int, float)) and beta != 0:
        sign = "positive" if beta > 0 else "negative"
        if sign != entry["direction"]:
            supp = entry["m4"].get("decision_supported")
            msg = (f"{entry['id']}: hypothesized a {entry['direction']} effect but β = {beta} is {sign}"
                   + (" — a negative β cannot support a positive-effect hypothesis; flip the hypothesis "
                      "direction or the decision." if supp else "."))
            out.append(_finding("coherence.direction_m3_m4", "soft", msg, hypothesis=entry["id"],
                                observed={"beta": beta}, expected=f"{entry['direction']} β", source="parsed"))
    # DI2: prose direction word vs β sign.
    if isinstance(beta, (int, float)) and beta != 0:
        bsign = "positive" if beta > 0 else "negative"
        for c in entry["m5"]["claims"]:
            if c.get("kind") == "direction" and c["value"] != bsign:
                out.append(_finding("coherence.direction_prose", "soft",
                                    f"{entry['id']}: prose describes a {c['value']} effect but the persisted "
                                    f"β = {beta} is {bsign}.", hypothesis=entry["id"], chapter=c.get("chapter"),
                                    observed={"sentence": c["sentence"]}, expected=f"{bsign} β"))
    return out


def _decision_checks(entry) -> list[dict]:
    out = []
    if not entry["m4"].get("present"):
        return out
    supp = entry["m4"].get("decision_supported")
    for c in entry["m5"]["claims"]:
        if c.get("kind") != "decision":
            continue
        prose_sup = c["value"] == "supported"
        if supp is not None and prose_sup != supp:
            out.append(_finding("coherence.decision_prose", "soft",
                                f"{entry['id']}: prose says {'supported' if prose_sup else 'not supported'} "
                                f"but the recorded decision is {'supported' if supp else 'not supported'}.",
                                hypothesis=entry["id"], chapter=c.get("chapter"),
                                observed={"sentence": c["sentence"]},
                                expected=f"decision_supported={supp}"))
    return out


def _co3(entry, chapters_present) -> list[dict]:
    if not (entry["m4"].get("present") and chapters_present):
        return []
    # `mentioned_in` is populated from _RESULT_CHAPTERS (results, conclusion) —
    # this set must match it or a hypothesis discussed only in the conclusion
    # chapter (where the discussion of findings now lives) would be wrongly
    # flagged as undiscussed on every five-chapter thesis.
    if not set(entry["m5"]["mentioned_in"]) & {"results", "conclusion"}:
        return [_finding("coherence.undiscussed_hypothesis", "soft",
                         f"{entry['id']} has an analysis result but is not discussed in the Results or "
                         "Conclusion chapter.", hypothesis=entry["id"], source="parsed")]
    return []


def check_coherence(registry, m3_hypotheses=None, analysis_results=None, chapters_present=False) -> list[dict]:
    findings = []
    if m3_hypotheses is not None or analysis_results is not None:
        findings += coverage_findings(m3_hypotheses, analysis_results)
    for e in registry:
        findings += _co3(e, chapters_present)
        findings += _direction_checks(e)
        findings += _decision_checks(e)
        findings += _number_checks(e)
    return findings


# --- entry points (never raise) ---------------------------------------------

def validate_m5_sections(final_sections, flat_context: dict) -> dict:
    try:
        hyps = flat_context.get("hypotheses")
        cm = flat_context.get("conceptual_model")
        ar = flat_context.get("analysis_results")
        registry = build_registry(hyps, cm, ar, final_sections)
        chapters = _resolve_chapters(final_sections)
        present = bool((chapters.get("results") and not _is_stub(chapters.get("results")))
                       and (chapters.get("conclusion") and not _is_stub(chapters.get("conclusion"))))
        findings = check_coherence(registry, hyps, ar, present)
        findings += percent_variance_findings(chapters, ar)   # gap 4: percent R²
        return _agg(findings)
    except Exception:
        logger.exception("validate_m5_sections crashed")
        return _agg([], crashed=True)


_CITE_RE = re.compile(r"\([^)]*\b(?:1[89]|20)\d{2}[a-z]?\b[^)]*\)|\[\d+\]")
_STOPWORDS = frozenset("the a an of to and or in on for with by is are be as that this "
                       "between effect affect impact influence relationship among their its "
                       "how what does do can will has have not no more less than".split())


def _keywords(text) -> set:
    return {w for w in re.findall(r"[a-zà-ỹ]{4,}", str(text or "").lower())
            if w not in _STOPWORDS}


def traceability_findings(m2: dict, m3: dict, chapters: dict) -> list[dict]:
    """§3.2/§3.8a: every M3 hypothesis should trace to an M2 research gap, and
    every M5 discussion paragraph about a hypothesis should cite the literature it
    confirms/contradicts. All SOFT/advisory (linkage can be implicit); deterministic
    token overlap + citation presence; never raises."""
    out: list[dict] = []
    try:
        m2 = m2 or {}
        # Only meaningful once the project has a literature base — otherwise we
        # can't judge gap-grounding or citability, and shouldn't nag early work.
        if not m2.get("literature_sources"):
            return out
        # This is a public entry point, and not every caller comes through
        # `_resolve_chapters` — resolve here too so a raw legacy slice
        # ({"discussion": …}) reaches the check below instead of matching
        # nothing. Idempotent on already-resolved input.
        chapters = _canonical_chapters(chapters or {})
        gaps = m2.get("research_gaps") or []
        hyps = (m3 or {}).get("hypotheses") or []
        gap_kw = set()
        for g in gaps:
            gap_kw |= _keywords(g.get("gap") or g.get("description") or g.get("text") if isinstance(g, dict) else g)
        if hyps and not gaps:
            out.append(_finding("traceability.no_gaps", "soft",
                                "No M2 research gaps are recorded, so the hypotheses have nothing to "
                                "trace back to. Add the gap(s) each hypothesis addresses.", chapter="framework"))
        elif hyps and gap_kw:
            ungrounded = []
            for h in hyps:
                stmt = h if isinstance(h, str) else (h.get("statement") or h.get("text") or h.get("hypothesis"))
                hid = normalize_hypothesis_id(h)
                if stmt and not (_keywords(stmt) & gap_kw):
                    ungrounded.append(hid or (stmt[:24] + "…"))
            for label in ungrounded[:5]:
                out.append(_finding("traceability.hypothesis_gap", "soft",
                                    f"Hypothesis {label} does not visibly connect to any stated research "
                                    "gap — make the gap→hypothesis link explicit.", hypothesis=label,
                                    chapter="framework"))

        # The discussion of findings lives in the conclusion chapter (5.2).
        disc = chapters.get("conclusion")
        if isinstance(disc, str) and not _is_stub(disc):
            for para in re.split(r"\n\s*\n", disc):
                if _ANCHOR.search(para) and not _CITE_RE.search(para):
                    hid = normalize_hypothesis_id(_ANCHOR.search(para).group(0))
                    # Finding id and `chapter` label stay "discussion": they are
                    # a stable identifier for stored feedback, not a chapter key.
                    out.append(_finding("traceability.discussion_uncited", "soft",
                                        f"The discussion of {hid or 'a hypothesis'} does not cite the "
                                        "literature it confirms or contradicts — tie the result back to a "
                                        "source.", hypothesis=hid, chapter="discussion"))
                    if sum(1 for f in out if f["check"] == "traceability.discussion_uncited") >= 5:
                        break
    except Exception:
        logger.debug("traceability_findings failed", exc_info=True)
    return out


# Wording that makes a percentage the COMPLEMENT of R² — the share left over,
# not the share explained.
#
# Without this the check read "Phần còn lại 28.4% biến thiên của PB do các yếu
# tố ngoài mô hình quyết định" ("the remaining 28.4% ... is determined by
# factors outside the model") as a claim that 28.4% was explained, and reported
# a hard, blocking contradiction against a perfectly correct sentence — in the
# student's OWN imported chapter. Stating the unexplained remainder is standard
# practice in a results chapter, so this is the common case, not an edge case.
_COMPLEMENT_RE = re.compile(
    r"còn\s*lại|chưa\s*được\s*giải\s*thích|không\s*được\s*giải\s*thích|"
    r"ngoài\s*mô\s*hình|remaining|unexplained|not\s+explained|"
    r"outside\s+the\s+model|other\s+factors|rest\s+of\s+the",
    re.IGNORECASE,
)

_PERCENT_VAR_RE = re.compile(
    r"(\d{1,3}(?:[.,]\d+)?)\s*%[^.]*?(?:variance|variation|phương sai|biến thiên)", re.I)


def percent_variance_findings(chapters: dict, analysis_results) -> list[dict]:
    """Gap 4: catch a prose R² written as a percent that contradicts the persisted
    structural_model.r2 (e.g. 'explains 56% of the variance in PI' vs stored 0.31).
    Hard ONLY when exactly one persisted construct is named in the sentence
    (unchecked beats guessed). Soft/none otherwise. Never raises."""
    out: list[dict] = []
    try:
        sm = (analysis_results or {}).get("structural_model") if isinstance(analysis_results, dict) else {}
        r2 = (sm or {}).get("r2") if isinstance(sm, dict) else {}
        if not isinstance(r2, dict) or not r2:
            return out
        con_r2 = {str(c).lower(): float(v) for c, v in r2.items() if isinstance(v, (int, float))}
        for chap in _RESULT_CHAPTERS:
            prose = chapters.get(chap)
            if not isinstance(prose, str) or _is_stub(prose):
                continue
            for sent in segment_sentences(_strip_rendered(prose)):
                m = _PERCENT_VAR_RE.search(sent)
                if not m:
                    continue
                pct, _ = _parse_num(m.group(1))
                if pct is None:
                    continue
                named = [c for c in con_r2 if c in sent.lower()]
                if len(named) != 1:
                    continue        # ambiguous → don't guess
                stored = con_r2[named[0]]
                # "The remaining 28.4%" states 1 - R², so compare it against the
                # complement. Checking it as if it were R² turned a correct,
                # conventional sentence into a hard blocking finding.
                complement = bool(_COMPLEMENT_RE.search(sent))
                claimed = (1.0 - pct / 100.0) if complement else (pct / 100.0)
                if abs(claimed - stored) > 0.015:   # ~1.5pt display tolerance
                    # Say WHERE and quote the sentence. "A paragraph states
                    # that 28.4% ..." sent the student hunting through a
                    # chapter of several thousand words with nothing to search
                    # for; the quote is the whole difference between a report
                    # they can act on and one they cannot.
                    quoted = " ".join(sent.split())[:200]
                    said = (f"says {m.group(1)}% of the variance in {named[0].upper()} is left "
                            f"UNexplained, which means R² would be {claimed:.3f}") if complement else (
                            f"says {m.group(1)}% of the variance in {named[0].upper()} is explained, "
                            f"i.e. R² = {claimed:.3f}")
                    out.append(_finding("coherence.number_mismatch", "hard",
                        f"In the {chap} chapter, this sentence {said} — but the computed R² for "
                        f"{named[0].upper()} is {stored} ({stored*100:.1f}% explained). "
                        f"Sentence: “{quoted}”",
                        chapter=chap, sentence=quoted))
        return out
    except Exception:
        logger.debug("percent_variance_findings failed", exc_info=True)
        return out


def validate_coherence(nested: dict) -> dict:
    try:
        def _d(k):
            v = nested.get(k)
            return v if isinstance(v, dict) else {}
        m2, m3, m4, m5 = _d("m2_literature"), _d("m3_design"), _d("m4_analysis"), _d("m5_writing")
        ar = m4.get("analysis_results")
        m5src = m5.get("final_sections") or m5.get("chapters") or {}
        registry = build_registry(m3.get("hypotheses"), m3.get("conceptual_model"), ar, m5src)
        chapters = _resolve_chapters(m5src)
        present = bool((chapters.get("results") and not _is_stub(chapters.get("results")))
                       and (chapters.get("conclusion") and not _is_stub(chapters.get("conclusion"))))
        findings = check_coherence(registry, m3.get("hypotheses"), ar, present)
        findings += traceability_findings(m2, m3, chapters)
        findings += percent_variance_findings(chapters, ar)   # gap 4: percent R²
        return _agg(findings)
    except Exception:
        logger.exception("validate_coherence crashed")
        return _agg([], crashed=True)


def m4_commit_findings(analysis_results, flat_context: dict) -> dict:
    """Soft-only DI1/CO2 for the M4 commit gate (no prose yet)."""
    try:
        registry = build_registry(flat_context.get("hypotheses"),
                                  flat_context.get("conceptual_model"), analysis_results, None)
        findings = []
        for e in registry:
            findings += _direction_checks(e)
        return _agg([f for f in findings if f["severity"] == "soft"])
    except Exception:
        logger.exception("m4_commit_findings crashed")
        return _agg([], crashed=True)
