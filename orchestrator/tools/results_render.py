"""M5 renderer over verified state (vision §3.6) — pure, stdlib-only, fail-open.

Turns the persisted, self-validated `analysis_results` / `data_screening` blocks
into the Chapter 4 tables, the Chapter 3 data-cleaning paragraph, and the
Chapter 5 limitations bullets — so every number in the thesis IS the computed
number, rendered verbatim from state, never retyped by the LLM.

The split: the renderer owns every statistic (marked with sentinels so the
coherence/similarity checkers treat it as authoritative), the LLM owns every
connective sentence. The LLM sees the real numbers as read-only context and
emits `[[DT:kind]]` placement tokens; `weave()` splices the real bytes in.

MUST NOT import m5_writing / boto3 / langchain / pandas / numpy — this module is
imported (lazily, fail-open) by agent/coherence.py and quality/similarity.py.
Every public function is try/except → log + return empty/None/input-unchanged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BEGIN = "<!--dt-rendered:begin kind={kind} sha={sha}-->"
_END = "<!--dt-rendered:end kind={kind}-->"
_SENTINEL_RE = re.compile(
    r"<!--dt-rendered:begin kind=(?P<kind>[a-z0-9_]+) sha=(?P<sha>[0-9a-f]+)-->"
    r".*?<!--dt-rendered:end kind=(?P=kind)-->", re.DOTALL)
_TOKEN_RE = re.compile(r"^[ \t]*\[\[DT:(?P<kind>[a-z0-9_]+)\]\][ \t]*$", re.MULTILINE)
_FIT_KEYS = ("cfi", "tli", "rmsea", "srmr", "chi2_df")

_HEADERS = {
    "en": {"construct": "Construct", "item": "Item", "loading": "Loading",
           "alpha": "Cronbach's α", "cr": "CR", "ave": "AVE", "path": "Path",
           "beta": "β", "t": "t", "p": "p", "f2": "f²", "decision": "Decision",
           "hyp": "H", "r2": "R²", "q2": "Q²", "index": "Index", "value": "Value",
           "threshold": "Threshold (Hu & Bentler)", "se": "SE", "z": "z",
           "mean": "Mean", "sd": "SD", "n": "n", "stage": "Stage", "removed": "Removed"},
    "vi": {"construct": "Khái niệm", "item": "Biến quan sát", "loading": "Hệ số tải",
           "alpha": "Cronbach's α", "cr": "CR", "ave": "AVE", "path": "Quan hệ",
           "beta": "β", "t": "t", "p": "p", "f2": "f²", "decision": "Kết luận",
           "hyp": "GT", "r2": "R²", "q2": "Q²", "index": "Chỉ số", "value": "Giá trị",
           "threshold": "Ngưỡng (Hu & Bentler)", "se": "SE", "z": "z",
           "mean": "Trung bình", "sd": "Độ lệch chuẩn", "n": "n", "stage": "Bước",
           "removed": "Loại bỏ"},
}
_CAPTIONS = {
    "en": {"measurement_model": "Table 4.1 — Measurement model: reliability and convergent validity",
           "discriminant_validity": "Table 4.2 — Discriminant validity",
           "model_fit": "Table 4.2 — Model fit indices",
           "structural_paths": "Table 4.3 — Structural model: hypothesis tests",
           "descriptives": "Table 4.0 — Sample descriptives",
           "r2_q2": "Table 4.4 — Explanatory and predictive power (R² / Q²)",
           "data_cleaning": "Table 3.1 — Data screening summary"},
    "vi": {"measurement_model": "Bảng 4.1 — Mô hình đo lường: độ tin cậy và giá trị hội tụ",
           "discriminant_validity": "Bảng 4.2 — Giá trị phân biệt",
           "model_fit": "Bảng 4.2 — Các chỉ số độ phù hợp mô hình",
           "structural_paths": "Bảng 4.3 — Mô hình cấu trúc: kiểm định giả thuyết",
           "descriptives": "Bảng 4.0 — Thống kê mô tả mẫu",
           "r2_q2": "Bảng 4.4 — Năng lực giải thích và dự báo (R² / Q²)",
           "data_cleaning": "Bảng 3.1 — Tóm tắt sàng lọc dữ liệu"},
}
_SOURCE_LINE = {"en": "*Source: rendered from persisted analysis results (DoThesis).*",
                "vi": "*Nguồn: kết xuất từ kết quả phân tích đã lưu (DoThesis).*"}
_FIT_THRESHOLDS = {"cfi": "≥ 0.90", "tli": "≥ 0.90", "rmsea": "≤ 0.08",
                   "srmr": "≤ 0.08", "chi2_df": "≤ 3"}


# --- formatting -------------------------------------------------------------

def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") or "0"
    return str(v)


def _sha12(sub: Any) -> str:
    return hashlib.sha256(
        json.dumps(sub, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def _wrap(kind: str, source_sub: Any, body: str, language: str) -> dict:
    sha = _sha12(source_sub)
    md = (_BEGIN.format(kind=kind, sha=sha) + "\n" + body.rstrip() + "\n"
          + _SOURCE_LINE.get(language, _SOURCE_LINE["en"]) + "\n"
          + _END.format(kind=kind))
    return {"kind": kind, "markdown": md, "sha": sha, "token": f"[[DT:{kind}]]"}


def _table(headers: List[str], rows: List[List[str]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join([line, sep, body])


def _H(language: str) -> dict:
    return _HEADERS.get(language, _HEADERS["en"])


# --- family detection -------------------------------------------------------

def detect_family(analysis_results: Any, methodology: Optional[str] = None) -> Optional[str]:
    try:
        ar = analysis_results
        if not isinstance(ar, dict):
            return None
        sm = ar.get("structural_model")
        has_fit = isinstance(sm, dict) and any(isinstance(sm.get(k), (int, float)) for k in _FIT_KEYS)
        has_fit = has_fit or isinstance(ar.get("fit"), dict)
        mm = ar.get("measurement_model")
        has_measure = isinstance(mm, list) and any(isinstance(c, dict) for c in mm)
        has_disc = isinstance(ar.get("discriminant_validity"), dict)
        has_hyp = isinstance(ar.get("hypothesis_tests"), list) and ar["hypothesis_tests"]
        has_r2 = isinstance(sm, dict) and isinstance(sm.get("r2"), dict)

        m = (methodology or "").lower()
        if has_fit:
            return "cb_sem"
        if "cb-sem" in m or "cbsem" in m or "amos" in m or "covariance" in m:
            if has_measure or has_disc:
                return "cb_sem"
        if has_measure or has_disc:
            return "pls_sem"
        if has_hyp or has_r2:
            return "regression"
        return None
    except Exception:
        logger.debug("detect_family failed", exc_info=True)
        return None


# --- results tables ---------------------------------------------------------

def _measurement_block(ar, family, language):
    mm = ar.get("measurement_model")
    if not (isinstance(mm, list) and mm):
        return None
    H = _H(language)
    loading_hdr = H["loading"]
    rows = []
    for con in mm:
        if not isinstance(con, dict):
            continue
        name = _fmt(con.get("construct"))
        items = con.get("items") or []
        alpha = _fmt(con.get("cronbach_alpha"))
        cr = _fmt(con.get("composite_reliability"))
        ave = _fmt(con.get("ave"))
        first = True
        if not items:
            rows.append([name, "—", "—", alpha, cr, ave])
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append([name, _fmt(it.get("item")), _fmt(it.get("loading")),
                         alpha if first else "", cr if first else "", ave if first else ""])
            first = False
    if not rows:
        return None
    caption = _CAPTIONS.get(language, _CAPTIONS["en"])["measurement_model"]
    body = f"**{caption}**\n\n" + _table(
        [H["construct"], H["item"], loading_hdr, H["alpha"], H["cr"], H["ave"]], rows)
    return _wrap("measurement_model", mm, body, language)


def _discriminant_block(ar, language):
    dv = ar.get("discriminant_validity")
    if not (isinstance(dv, dict) and isinstance(dv.get("matrix"), list) and dv["matrix"]):
        return None
    matrix = dv["matrix"]
    labels = matrix[0]
    if not isinstance(labels, list):
        return None
    rows = []
    for i, r in enumerate(matrix[1:]):
        if not isinstance(r, list):
            continue
        label = _fmt(labels[i]) if i < len(labels) else "—"
        rows.append([label] + [_fmt(c) for c in r])
    method = dv.get("method", "")
    caption = _CAPTIONS.get(language, _CAPTIONS["en"])["discriminant_validity"]
    title = f"**{caption}" + (f" ({method})" if method else "") + "**"
    body = title + "\n\n" + _table([""] + [_fmt(l) for l in labels], rows)
    return _wrap("discriminant_validity", dv, body, language)


def _model_fit_block(ar, language):
    sm = ar.get("structural_model") if isinstance(ar.get("structural_model"), dict) else {}
    fit = ar.get("fit") if isinstance(ar.get("fit"), dict) else {}
    src = {k: (fit.get(k) if fit.get(k) is not None else sm.get(k)) for k in _FIT_KEYS}
    if not any(isinstance(v, (int, float)) for v in src.values()):
        return None
    H = _H(language)
    rows = [[k.upper() if k != "chi2_df" else "χ²/df", _fmt(src[k]), _FIT_THRESHOLDS[k]]
            for k in _FIT_KEYS if isinstance(src[k], (int, float))]
    caption = _CAPTIONS.get(language, _CAPTIONS["en"])["model_fit"]
    body = f"**{caption}**\n\n" + _table([H["index"], H["value"], H["threshold"]], rows)
    return _wrap("model_fit", src, body, language)


def _structural_block(ar, family, language):
    tests = ar.get("hypothesis_tests")
    if not (isinstance(tests, list) and tests):
        return None
    H = _H(language)
    dedup = {}
    for t in tests:
        if isinstance(t, dict):
            dedup[t.get("id") or t.get("hypothesis") or _fmt(t.get("path"))] = t
    is_cb = family == "cb_sem"
    third = H["se"] + "/" + H["z"] if is_cb else H["t"]
    headers = [H["hyp"], H["path"], H["beta"], third, H["p"]]
    if not is_cb:
        headers.append(H["f2"])
    headers.append(H["decision"])
    rows = []
    for hid, t in dedup.items():
        nums = t.get("numbers") or {}
        row = [_fmt(hid), _fmt(t.get("path")), _fmt(nums.get("beta"))]
        if is_cb:
            se, z = nums.get("se"), nums.get("z") or nums.get("t")
            row.append(f"{_fmt(se)} / {_fmt(z)}")
        else:
            row.append(_fmt(nums.get("t")))
        row.append(_fmt(nums.get("p")))
        if not is_cb:
            row.append(_fmt(nums.get("f2")))
        row.append(_fmt(t.get("decision")))
        rows.append(row)
    caption = _CAPTIONS.get(language, _CAPTIONS["en"])["structural_paths"]
    body = f"**{caption}**\n\n" + _table(headers, rows)
    return _wrap("structural_paths", tests, body, language)


def _r2q2_block(ar, family, language):
    sm = ar.get("structural_model") if isinstance(ar.get("structural_model"), dict) else {}
    r2 = sm.get("r2") if isinstance(sm.get("r2"), dict) else {}
    q2 = sm.get("q2") if isinstance(sm.get("q2"), dict) else {}
    if not r2 and not q2:
        return None
    H = _H(language)
    cons = list(dict.fromkeys(list(r2) + list(q2)))
    show_q2 = bool(q2) and family == "pls_sem"
    headers = [H["construct"], H["r2"]] + ([H["q2"]] if show_q2 else [])
    rows = [[_fmt(c), _fmt(r2.get(c))] + ([_fmt(q2.get(c))] if show_q2 else []) for c in cons]
    caption = _CAPTIONS.get(language, _CAPTIONS["en"])["r2_q2"]
    body = f"**{caption}**\n\n" + _table(headers, rows)
    return _wrap("r2_q2", {"r2": r2, "q2": q2 if show_q2 else {}}, body, language)


def _descriptives_block(ar, language):
    d = ar.get("descriptives")
    if not (isinstance(d, dict) and isinstance(d.get("by_item"), list) and d["by_item"]):
        return None
    H = _H(language)
    rows = [[_fmt(r.get("item")), _fmt(r.get("mean")), _fmt(r.get("sd"))]
            for r in d["by_item"] if isinstance(r, dict)]
    if not rows:
        return None
    caption = _CAPTIONS.get(language, _CAPTIONS["en"])["descriptives"]
    n = d.get("n")
    ncap = f" (n = {_fmt(n)})" if isinstance(n, (int, float)) else ""
    body = f"**{caption}{ncap}**\n\n" + _table([H["item"], H["mean"], H["sd"]], rows)
    return _wrap("descriptives", d, body, language)


def render_results_tables(analysis_results: Any, language: str = "en") -> List[dict]:
    try:
        ar = analysis_results
        if not isinstance(ar, dict):
            return []
        fam = detect_family(ar)
        if fam is None:
            return []
        blocks = []
        for b in (_descriptives_block(ar, language),
                  _measurement_block(ar, fam, language),
                  _discriminant_block(ar, language) if fam == "pls_sem" else None,
                  _model_fit_block(ar, language) if fam == "cb_sem" else None,
                  _structural_block(ar, fam, language),
                  _r2q2_block(ar, fam, language)):
            if b:
                blocks.append(b)
        return blocks
    except Exception:
        logger.debug("render_results_tables failed", exc_info=True)
        return []


# --- cleaning section -------------------------------------------------------

def render_cleaning_section(analysis_results: Any, language: str = "en") -> Optional[dict]:
    try:
        ar = analysis_results if isinstance(analysis_results, dict) else {}
        ds = ar.get("data_screening")
        if not isinstance(ds, dict):
            return None
        parts = []
        narrative = ds.get("narrative")
        if isinstance(narrative, str) and narrative.strip():
            parts.append(narrative.strip())     # verbatim — never re-typed
        # optional summary table from present count fields
        H = _H(language)
        rows = []
        for label, key in (("Careless / straight-lining", "careless_removed"),
                           ("Outliers (Mahalanobis)", "outliers_removed"),
                           ("Missing (listwise)", "missing_removed")):
            v = ds.get(key)
            if isinstance(v, (int, float)):
                rows.append([label, _fmt(v)])
        if isinstance(ds.get("n_before"), (int, float)) and isinstance(ds.get("n_after"), (int, float)):
            rows.append(["n retained", f"{_fmt(ds['n_after'])} of {_fmt(ds['n_before'])}"])
        if rows:
            caption = _CAPTIONS.get(language, _CAPTIONS["en"])["data_cleaning"]
            parts.append(f"**{caption}**\n\n" + _table([H["stage"], H["removed"]], rows))
        if not parts:
            return None
        return _wrap("data_cleaning", ds, "\n\n".join(parts), language)
    except Exception:
        logger.debug("render_cleaning_section failed", exc_info=True)
        return None


# --- limitations ------------------------------------------------------------

def render_limitations(nested_cs: dict, *, rubric_findings: Optional[list] = None,
                       language: str = "en") -> Optional[dict]:
    try:
        cs = nested_cs if isinstance(nested_cs, dict) else {}
        m3 = cs.get("m3_design") if isinstance(cs.get("m3_design"), dict) else {}
        m4 = cs.get("m4_analysis") if isinstance(cs.get("m4_analysis"), dict) else {}
        ar = m4.get("analysis_results") if isinstance(m4.get("analysis_results"), dict) else {}
        bullets: List[tuple] = []  # (severity_rank, text)

        # power shortfall
        sp = m3.get("sample_plan") if isinstance(m3.get("sample_plan"), dict) else {}
        pa = sp.get("power_analysis") if isinstance(sp.get("power_analysis"), dict) else {}
        req = pa.get("recommended_n") or pa.get("required_n")
        n = (ar.get("descriptives") or {}).get("n") if isinstance(ar.get("descriptives"), dict) else None
        if isinstance(req, (int, float)) and isinstance(n, (int, float)) and n < req:
            just = str(pa.get("justification") or "").strip()
            bullets.append((0, f"The achieved sample (n={_fmt(n)}) fell below the a-priori required "
                            f"N={_fmt(req)}"
                            + (f" ({just})" if just else "")
                            + ". This is disclosed as a boundary condition; findings should be "
                            "read with the corresponding caution and re-tested at scale in future work."))

        # not-supported hypotheses
        for t in (ar.get("hypothesis_tests") or []):
            if isinstance(t, dict) and str(t.get("decision") or "").lower().startswith(("not", "rejected")):
                nums = t.get("numbers") or {}
                bullets.append((1, f"{_fmt(t.get('id') or t.get('hypothesis'))} "
                                f"({_fmt(t.get('path'))}, β={_fmt(nums.get('beta'))}, "
                                f"p={_fmt(nums.get('p'))}) was not supported — a substantive finding "
                                "discussed theoretically above, not a data artifact."))

        # screening removals
        ds = ar.get("data_screening") if isinstance(ar.get("data_screening"), dict) else {}
        rem = sum(v for k in ("careless_removed", "outliers_removed", "missing_removed")
                  for v in [ds.get(k)] if isinstance(v, (int, float)))
        if rem:
            bullets.append((2, f"{_fmt(rem)} response(s) were removed in data screening; while this "
                            "improves data quality, it slightly reduces the effective sample and is "
                            "disclosed for transparency."))

        # soft validity findings (lazy, fail-open)
        try:
            from agent.stats_validation import validate_analysis_results  # noqa: PLC0415
            agg = validate_analysis_results(ar)
            for f in (agg.get("findings") or []):
                if f.get("severity") == "soft":
                    bullets.append((3, f"A borderline measurement result was flagged and is disclosed: "
                                    f"{f.get('summary') or f.get('check')}."))
        except Exception:
            logger.debug("render_limitations: validity findings skipped", exc_info=True)

        for f in (rubric_findings or []):
            if isinstance(f, dict) and f.get("issue"):
                bullets.append((3 if f.get("severity") != "hard" else 0,
                                f"{f['issue']} — disclosed and addressed as noted."))

        if not bullets:
            return None
        bullets.sort(key=lambda b: b[0])
        bullets = bullets[:8]
        body = "\n".join(f"- {t}" for _, t in bullets)
        return _wrap("limitations", [t for _, t in bullets], body, language)
    except Exception:
        logger.debug("render_limitations failed", exc_info=True)
        return None


# --- weave / strip / verify -------------------------------------------------

def rendered_kinds(prose: str) -> set:
    try:
        return {m.group("kind") for m in _SENTINEL_RE.finditer(prose or "")}
    except Exception:
        return set()


def strip_rendered_blocks(prose: str) -> str:
    try:
        if not isinstance(prose, str) or "dt-rendered:begin" not in prose:
            return prose if isinstance(prose, str) else ""
        return _SENTINEL_RE.sub("", prose)
    except Exception:
        logger.debug("strip_rendered_blocks failed", exc_info=True)
        return prose if isinstance(prose, str) else ""


def _is_numeric_table(segment: str) -> bool:
    lines = [l for l in segment.strip().splitlines() if l.strip().startswith("|")]
    if len(lines) < 3:
        return False
    data = lines[2:]
    cells, numeric = 0, 0
    for l in data:
        for c in [c.strip() for c in l.strip().strip("|").split("|")]:
            if not c:
                continue
            cells += 1
            if re.search(r"\d", c):
                numeric += 1
    return cells > 0 and numeric >= cells / 2


def weave(prose: str, blocks: List[dict], *, drop_llm_tables: bool = False) -> str:
    try:
        if not isinstance(prose, str):
            prose = ""
        blocks = [b for b in (blocks or []) if isinstance(b, dict) and b.get("markdown")]
        if not blocks:
            return prose
        already = rendered_kinds(prose)
        by_kind = {}
        for b in blocks:
            by_kind.setdefault(b["kind"], b)

        # 1+3: replace token lines (dedup: only first token per kind, drop rest)
        used = set(already)

        def repl(m):
            kind = m.group("kind")
            b = by_kind.get(kind)
            if b is None or kind in used:
                return ""      # unknown or duplicate token → remove
            used.add(kind)
            return b["markdown"]
        woven = _TOKEN_RE.sub(repl, prose)

        # 4: results-only drop of unmarked numeric pipe tables (only if we wove ≥1)
        if drop_llm_tables and (used - already):
            woven = _drop_unmarked_numeric_tables(woven)

        # 2: append blocks whose token never appeared
        missing = [b for b in blocks if b["kind"] not in used]
        if missing:
            woven = woven.rstrip() + "\n\n" + "\n\n".join(b["markdown"] for b in missing)
        return woven
    except Exception:
        logger.debug("weave failed", exc_info=True)
        return prose if isinstance(prose, str) else ""


def _drop_unmarked_numeric_tables(prose: str) -> str:
    # protect sentinel spans, then drop bare numeric pipe-table blocks
    spans = [(m.start(), m.end()) for m in _SENTINEL_RE.finditer(prose)]

    def protected(pos):
        return any(s <= pos < e for s, e in spans)
    out_lines = []
    block: List[str] = []
    block_start = 0
    pos = 0
    for line in prose.splitlines(keepends=True):
        is_table_line = line.strip().startswith("|")
        if is_table_line and not block:
            block_start = pos
        if is_table_line:
            block.append(line)
        else:
            if block:
                seg = "".join(block)
                if protected(block_start) or not _is_numeric_table(seg):
                    out_lines.append(seg)
                block = []
            out_lines.append(line)
        pos += len(line)
    if block:
        seg = "".join(block)
        if protected(block_start) or not _is_numeric_table(seg):
            out_lines.append(seg)
    return "".join(out_lines)


def verify_rendered_blocks(prose: str, analysis_results: Any) -> List[dict]:
    """Re-render each block from state and compare against the block as it appears
    in the prose — catches a hand-edited cell (which leaves state, and thus the
    sha, unchanged) by comparing the full rendered body. Soft findings only."""
    try:
        if not isinstance(prose, str) or "dt-rendered:begin" not in prose:
            return []
        current = {b["kind"]: b["markdown"] for b in render_results_tables(analysis_results)}
        cleaning = render_cleaning_section(analysis_results)
        if cleaning:
            current[cleaning["kind"]] = cleaning["markdown"]
        findings = []
        for m in _SENTINEL_RE.finditer(prose):
            kind = m.group("kind")
            expected = current.get(kind)
            actual = m.group(0)
            if expected is not None and _norm_ws(expected) != _norm_ws(actual):
                findings.append({"check": "render.tampered", "severity": "soft", "kind": kind,
                                 "summary": f"Rendered table '{kind}' no longer matches the persisted "
                                 "analysis results — it may have been hand-edited."})
        return findings
    except Exception:
        logger.debug("verify_rendered_blocks failed", exc_info=True)
        return []


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()
