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
# Caption LABELS, without a number. The number is decided at render time —
# see _caption / renumber_from.
_CAPTIONS = {
    "en": {"measurement_model": "Measurement model: reliability and convergent validity",
           "scale_reliability": "Scale reliability",
           "discriminant_validity": "Discriminant validity",
           "model_fit": "Model fit indices",
           "structural_paths": "Structural model: hypothesis tests",
           "descriptives": "Sample descriptives",
           "r2_q2": "Explanatory and predictive power (R² / Q²)",
           "data_cleaning": "Data screening summary"},
    "vi": {"measurement_model": "Mô hình đo lường: độ tin cậy và giá trị hội tụ",
           "scale_reliability": "Độ tin cậy thang đo",
           "discriminant_validity": "Giá trị phân biệt",
           "model_fit": "Các chỉ số độ phù hợp mô hình",
           "structural_paths": "Mô hình cấu trúc: kiểm định giả thuyết",
           "descriptives": "Thống kê mô tả mẫu",
           "r2_q2": "Năng lực giải thích và dự báo (R² / Q²)",
           "data_cleaning": "Tóm tắt sàng lọc dữ liệu"},
}
# Fallback numbering, used when nothing tells us what the host chapter already
# contains — a chapter we composed ourselves starts at 4.0.
_DEFAULT_NUMBER = {"descriptives": "4.0", "measurement_model": "4.1",
                   "scale_reliability": "4.1", "discriminant_validity": "4.2",
                   "model_fit": "4.2", "structural_paths": "4.3", "r2_q2": "4.4",
                   "data_cleaning": "3.1"}
_TABLE_WORD = {"en": "Table", "vi": "Bảng"}

# "Bảng 4.14", "Table 4.3:", "Bang 4.2 -" … at the start of a line or after the
# bold marker a caption uses.
_TABLE_NUM_RE = re.compile(r"(?:Bảng|Bang|Table)\s+(\d+)\.(\d+)", re.IGNORECASE)


def _caption(kind: str, language: str, number: str | None = None) -> str:
    caps = _CAPTIONS.get(language, _CAPTIONS["en"])
    word = _TABLE_WORD["vi"] if str(language).lower().startswith("vi") else _TABLE_WORD["en"]
    return f"{word} {number or _DEFAULT_NUMBER[kind]} — {caps[kind]}"


def next_table_number(prose: str, default: str) -> str:
    """The number the NEXT table in `prose` should carry.

    A rendered table captioned "Bảng 4.1" dropped into a chapter the student
    wrote — one that already runs to Bảng 4.14 — gives the document two Bảng 4.1
    and a supervisor a reason to send it back. Continue their sequence instead:
    read the highest number already in the chapter and take the next one, in the
    chapter they are numbered under, not ours.

    Falls back to `default` when the prose has no numbered table (a chapter we
    composed, which is the case the fixed numbers were written for).
    """
    found = _TABLE_NUM_RE.findall(prose or "")
    if not found:
        return default
    chapter = max(int(c) for c, _ in found)
    highest = max(int(i) for c, i in found if int(c) == chapter)
    return f"{chapter}.{highest + 1}"


_SOURCE_LINE = {"en": "*Source: rendered from persisted analysis results (DoThesis).*",
                "vi": "*Nguồn: kết xuất từ kết quả phân tích đã lưu (DoThesis).*"}
_FIT_THRESHOLDS = {"cfi": "≥ 0.90", "tli": "≥ 0.90", "rmsea": "≤ 0.08",
                   "srmr": "≤ 0.08", "chi2_df": "≤ 3"}


# --- formatting -------------------------------------------------------------

_EMPTY = "—"


def _fmt(v: Any) -> str:
    if v is None:
        return _EMPTY
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


def _table_pruned(headers: List[str], rows: List[List[str]]) -> str:
    """`_table`, minus any column that has no value in any row.

    A fixed column list describes the richest study the renderer can handle, and
    every other study gets the difference as em-dashes. On a real SPSS
    regression the measurement table came out with four of six columns empty —
    including CR and AVE, which are PLS metrics the study never computed and a
    supervisor would ask where they came from. The structural table carried an
    equally empty f².

    An absent statistic should be an absent column, not a column of dashes
    claiming the statistic exists and is unknown. The first column is the row
    label and is always kept.
    """
    if not rows:
        return _table(headers, rows)
    width = len(headers)
    keep = [i for i in range(width)
            if i == 0 or any(str(r[i]).strip() not in ("", _EMPTY)
                             for r in rows if i < len(r))]
    if len(keep) == width:
        return _table(headers, rows)
    return _table([headers[i] for i in keep],
                  [[r[i] for i in keep if i < len(r)] for r in rows])


def _H(language: str) -> dict:
    return _HEADERS.get(language, _HEADERS["en"])


# --- family detection -------------------------------------------------------
#
# Matched against the methodology text AND the tool/method recorded on the
# results. Deliberately software names plus the few method phrases that are
# unambiguous in both languages — a guess from a construct count is what got
# an SPSS study labelled PLS-SEM in the first place.
_CB_MARKERS = ("cb-sem", "cbsem", "amos", "lisrel", "mplus", "covariance")
_PLS_MARKERS = ("pls-sem", "plssem", "smartpls", "pls sem", "partial least")
_REGRESSION_MARKERS = ("spss", "stata", "eviews", "jamovi", "jasp",
                       "regression", "hồi quy", "ols", "anova")


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

        # Read the tool/method off the RESULTS too, not just the caller's
        # `methodology`. The only caller (render_results_tables) has no
        # methodology to pass and never passes one, so every branch keyed on it
        # was dead — and _infer_analysis_results already parks the software the
        # student actually used in structural_model.tool ("SPSS") and .method
        # ("hồi quy tuyến tính đa biến…"). The evidence was in the argument the
        # function already had.
        sm_text = " ".join(str((sm or {}).get(k) or "") for k in ("tool", "method")) \
            if isinstance(sm, dict) else ""
        m = f"{methodology or ''} {sm_text}".lower()
        if has_fit:
            return "cb_sem"
        if any(k in m for k in _CB_MARKERS) and (has_measure or has_disc):
            return "cb_sem"
        if any(k in m for k in _PLS_MARKERS) and (has_measure or has_disc):
            return "pls_sem"
        # A named regression package is decisive. Without this, ANY study with a
        # measurement_model fell through to pls_sem — and an SPSS reliability
        # table (constructs + Cronbach's α, nothing else) was rendered as a PLS
        # measurement model with CR and AVE columns the study never computed.
        if any(k in m for k in _REGRESSION_MARKERS) and not has_disc:
            return "regression"
        if has_measure or has_disc:
            return "pls_sem"
        if has_hyp or has_r2:
            return "regression"
        return None
    except Exception:
        logger.debug("detect_family failed", exc_info=True)
        return None


# --- results tables ---------------------------------------------------------

def _measurement_block(ar, family, language, num=None):
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
    # "…reliability and convergent validity" is a claim about AVE. With no CR
    # and no AVE this is a Cronbach's α table and nothing more, and captioning
    # it as convergent validity asserts a check the study never ran.
    has_convergent = any(isinstance(c, dict) and (c.get("ave") is not None
                                                  or c.get("composite_reliability") is not None)
                         for c in mm)
    caption = _caption("measurement_model" if has_convergent else "scale_reliability",
                       language, num)
    body = f"**{caption}**\n\n" + _table_pruned(
        [H["construct"], H["item"], loading_hdr, H["alpha"], H["cr"], H["ave"]], rows)
    return _wrap("measurement_model", mm, body, language)


def _discriminant_block(ar, language, num=None):
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
    caption = _caption("discriminant_validity", language, num)
    title = f"**{caption}" + (f" ({method})" if method else "") + "**"
    body = title + "\n\n" + _table([""] + [_fmt(l) for l in labels], rows)
    return _wrap("discriminant_validity", dv, body, language)


def _model_fit_block(ar, language, num=None):
    sm = ar.get("structural_model") if isinstance(ar.get("structural_model"), dict) else {}
    fit = ar.get("fit") if isinstance(ar.get("fit"), dict) else {}
    src = {k: (fit.get(k) if fit.get(k) is not None else sm.get(k)) for k in _FIT_KEYS}
    if not any(isinstance(v, (int, float)) for v in src.values()):
        return None
    H = _H(language)
    rows = [[k.upper() if k != "chi2_df" else "χ²/df", _fmt(src[k]), _FIT_THRESHOLDS[k]]
            for k in _FIT_KEYS if isinstance(src[k], (int, float))]
    caption = _caption("model_fit", language, num)
    body = f"**{caption}**\n\n" + _table([H["index"], H["value"], H["threshold"]], rows)
    return _wrap("model_fit", src, body, language)


def _structural_block(ar, family, language, num=None):
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
    caption = _caption("structural_paths", language, num)
    body = f"**{caption}**\n\n" + _table_pruned(headers, rows)
    return _wrap("structural_paths", tests, body, language)


def _r2q2_block(ar, family, language, num=None):
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
    caption = _caption("r2_q2", language, num)
    # The caption is fixed text promising "(R² / Q²)". On every study without a
    # Q² — every regression, which is most of them — it announced a predictive
    # metric that is not in the table and was never computed. Say what is there.
    if not show_q2:
        caption = caption.replace(" / Q²", "")
    body = f"**{caption}**\n\n" + _table(headers, rows)
    return _wrap("r2_q2", {"r2": r2, "q2": q2 if show_q2 else {}}, body, language)


def _descriptives_block(ar, language, num=None):
    d = ar.get("descriptives")
    if not (isinstance(d, dict) and isinstance(d.get("by_item"), list) and d["by_item"]):
        return None
    H = _H(language)
    rows = [[_fmt(r.get("item")), _fmt(r.get("mean")), _fmt(r.get("sd"))]
            for r in d["by_item"] if isinstance(r, dict)]
    if not rows:
        return None
    caption = _caption("descriptives", language, num)
    n = d.get("n")
    ncap = f" (n = {_fmt(n)})" if isinstance(n, (int, float)) else ""
    body = f"**{caption}{ncap}**\n\n" + _table([H["item"], H["mean"], H["sd"]], rows)
    return _wrap("descriptives", d, body, language)


def render_results_tables(analysis_results: Any, language: str = "en",
                          host_prose: str | None = None) -> List[dict]:
    """The Chapter 4 tables.

    `host_prose` is the chapter these blocks are going INTO, when the caller
    knows it. Its only use is numbering: a chapter the student wrote already
    numbers its own tables, and dropping a "Bảng 4.1" into one that runs to
    Bảng 4.14 hands the document two tables with the same number.
    """
    try:
        ar = analysis_results
        if not isinstance(ar, dict):
            return []
        fam = detect_family(ar)
        if fam is None:
            return []
        # Sequential numbering continuing the host chapter, or the fixed
        # defaults when there is no host to continue.
        seq = None
        if host_prose:
            start = next_table_number(host_prose, "")
            if start:
                chapter, idx = start.split(".")
                seq = (int(chapter), int(idx))

        blocks = []

        def _emit(build):
            """Number a block only if it turns out to exist — several of these
            return None for a study that lacks the data, and consuming a number
            for one of them would leave a hole in the chapter's sequence."""
            nonlocal seq
            n = f"{seq[0]}.{seq[1]}" if seq else None
            b = build(n)
            if b:
                blocks.append(b)
                if seq:
                    seq = (seq[0], seq[1] + 1)

        _emit(lambda n: _descriptives_block(ar, language, n))
        _emit(lambda n: _measurement_block(ar, fam, language, n))
        if fam == "pls_sem":
            _emit(lambda n: _discriminant_block(ar, language, n))
        if fam == "cb_sem":
            _emit(lambda n: _model_fit_block(ar, language, n))
        _emit(lambda n: _structural_block(ar, fam, language, n))
        _emit(lambda n: _r2q2_block(ar, fam, language, n))
        return blocks
    except Exception:
        logger.debug("render_results_tables failed", exc_info=True)
        return []


# --- cleaning section -------------------------------------------------------

def render_cleaning_section(analysis_results: Any, language: str = "en",
                            num: str | None = None) -> Optional[dict]:
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
            caption = _caption("data_cleaning", language, num)
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
            # A placement token is renderer-internal syntax, never thesis
            # content. When the requested verified block has no source data
            # (e.g. Chapter 3 exported before M4), remove the token instead of
            # leaking ``[[DT:data_cleaning]]`` into Word/PDF.
            return _TOKEN_RE.sub("", prose)
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


_TITLE_CHAPTER = [
    # Ordering matters only as the LAST tie-break, when a title matches several
    # needles AND its chapter number agrees with none of them (see
    # `_chapter_of`). Closing-chapter needles lead, because a title that mixes
    # the two vocabularies without a number ("Thảo luận kết quả") is far more
    # often the closing chapter than the results chapter.
    ("discussion", "conclusion"), ("thảo luận", "conclusion"),
    ("limitation", "conclusion"), ("hạn chế", "conclusion"),
    ("result", "results"), ("methodolog", "methodology"),
    ("data collect", "methodology"), ("conclusion", "conclusion"),
    # Vietnamese. Without these the title map matched nothing on a
    # Vietnamese thesis — "CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU" hit no
    # needle — so ensure_rendered, the export-time safety net, has
    # never once fired for the market this product is built for.
    # "kết quả" is listed before "kết luận" here; they are distinct strings
    # and cannot both match, so their relative order carries no meaning.
    ("kết quả", "results"), ("phương pháp", "methodology"),
    ("thu thập dữ liệu", "methodology"), ("kết luận", "conclusion"),
]
# Note the needles for "discussion"/"thảo luận"/"hạn chế" are kept — a
# student's imported thesis may still title a section that way, and it must
# map to the one chapter (conclusion) that now holds that material.

# An explicit chapter NUMBER is the one signal that separates "Chương 4: Kết
# quả nghiên cứu VÀ THẢO LUẬN" (a very common Vietnamese Chapter 4 title) from
# "Chương 5: Thảo luận kết quả" — the substrings alone cannot, because each
# title contains both vocabularies. 5 AND 6 both land on `conclusion`: a legacy
# six-chapter thesis numbered its discussion 5 and its conclusion 6, and that
# material now belongs to the single Chapter 5.
_NUMBER_CHAPTER = {1: "intro", 2: "lit_review", 3: "methodology",
                   4: "results", 5: "conclusion", 6: "conclusion"}
_CHAPTER_NUMBER_RE = re.compile(r"(?i)\b(?:chương|chapter)\s*0*(\d+)")

_RENDERABLE_CHAPTERS = {"results", "methodology", "conclusion"}


def _chapter_of(title: str) -> Optional[str]:
    """Which chapter a heading names, disambiguated by its chapter number.

    The number DECIDES among the needles the title actually matched, rather than
    overriding them: a thesis that numbers its chapters unusually ("Chapter 3 —
    Results") is still read by its words. When the title matches no needle at
    all, the number stands on its own; when there is no number, first needle
    wins, as before.
    """
    t = (title or "").lower()
    matched: list[str] = []
    for needle, chapter in _TITLE_CHAPTER:
        if needle in t and chapter not in matched:
            matched.append(chapter)
    m = _CHAPTER_NUMBER_RE.search(t)
    if m:
        numbered = _NUMBER_CHAPTER.get(int(m.group(1)))
        if numbered and (not matched or numbered in matched):
            return numbered
    return matched[0] if matched else None


# Retired key -> canonical, mirroring m5_writing.LEGACY_CHAPTER_ALIASES. Only a
# fallback for the (in-repo, so effectively impossible) case where the lazy
# import below fails; the same duplication quality/similarity.py carries, and
# for the same reason — this module must stay import-light.
_RETIRED_CHAPTERS = {"discussion": "conclusion"}


def _canonical_chapter(name: Any) -> Optional[str]:
    """`m5_writing.canonical_chapter`, imported lazily so the module contract
    at the top of this file (no m5_writing at import time — it pulls in
    boto3/langchain, and coherence.py imports us) still holds. Fail-open onto
    the mirrored alias map above."""
    try:
        from orchestrator.tools.m5_writing import canonical_chapter  # noqa: PLC0415
        return canonical_chapter(name)
    except Exception:
        logger.debug("canonical_chapter unavailable; using local aliases", exc_info=True)
        key = str(name or "").strip()
        key = _RETIRED_CHAPTERS.get(key, key)
        return key if key in _NUMBER_CHAPTER.values() else None


def _section_chapter(sec: dict) -> Optional[str]:
    """Which chapter a section is, preferring the canonical name over its title.

    `chapter_name` is set by the composer and by the import, is language-neutral,
    and is exactly the signal a title reverse-lookup keeps missing.

    A STATED identity beats a substring guess, so the name is honoured whenever
    it resolves to a chapter at all — not only when it is one of the three this
    module renders for. Testing renderability here cost both directions: a
    legacy `discussion` (the retired key `canonical_chapter` maps onto
    `conclusion`) was discarded, and a section whose title carried no needle
    then resolved to None and lost its limitations disclosure — the exact cohort
    the five-chapter collapse exists to protect. In the other direction a
    Chapter 2 titled "tổng quan tài liệu về kết quả nghiên cứu trước đây"
    matches the results needle, so overriding its stated `lit_review` wove the
    Chapter 4 result tables into the literature review. The title is consulted
    only when there is no usable name.
    """
    name = _canonical_chapter(sec.get("chapter_name"))
    if name:
        return name
    return _chapter_of(sec.get("title") or sec.get("name") or "")


def ensure_rendered(sections: list, nested_cs: dict, language: str = "en") -> list:
    """Export-time safety net: for each section whose title maps to a
    results/methodology/conclusion chapter, weave in any renderer block
    NOT already present (by kind). Idempotent, pure, fail-open — a section that
    already carries its rendered tables (composed via compose_chapter) is
    unchanged. Covers sections that reached export without compose (chat-committed
    final_sections, editor PATCHes)."""
    try:
        if not isinstance(sections, list):
            return sections
        cs = nested_cs if isinstance(nested_cs, dict) else {}
        ar = ((cs.get("m4_analysis") or {}).get("analysis_results")
              if isinstance(cs.get("m4_analysis"), dict) else None)
        m3 = cs.get("m3_design") if isinstance(cs.get("m3_design"), dict) else {}
        out = []
        for sec in sections:
            if not isinstance(sec, dict):
                out.append(sec)
                continue
            # The student's own imported chapter is left alone. This net exists
            # for prose WE produced that reached export without composition;
            # an imported Chapter 4 already carries the student's 17 tables, and
            # appending our three renderings of the same numbers underneath them
            # is duplication, not a safety net.
            if sec.get("source") == "import":
                out.append(sec)
                continue
            chapter = _section_chapter(sec)
            prose = sec.get("prose") or sec.get("content")
            # Only the three chapters this module can actually render for are
            # let through. The branch below ends in an `else`, so ANY other
            # answer — `intro` and `lit_review` are the two `_chapter_of` can
            # now give — falls into the limitations disclosure and welds it onto
            # Chapter 1 or Chapter 2 of every export. Testing membership here
            # rather than pruning the number map keeps `_chapter_of` a general
            # title→chapter reader (it is also the reverse lookup for a section
            # whose `chapter_name` is missing) and makes "the else is
            # conclusion-only" true by construction, whatever it learns to
            # answer next.
            if chapter not in _RENDERABLE_CHAPTERS or not isinstance(prose, str):
                out.append(sec)
                continue
            have = rendered_kinds(prose)
            if chapter == "results":
                blocks = [b for b in render_results_tables(ar, language, host_prose=prose)
                          if b["kind"] not in have]
            elif chapter == "methodology":
                b = render_cleaning_section(ar, language,
                                            num=next_table_number(prose, "") or None)
                blocks = [b] if b and b["kind"] not in have else []
            else:
                nested = {"m3_design": m3, "m4_analysis": {"analysis_results": ar}}
                b = render_limitations(nested, language=language)
                blocks = [b] if b and b["kind"] not in have else []
            if blocks:
                woven = weave(prose, blocks, drop_llm_tables=(chapter == "results"))
                new = dict(sec)
                new["prose" if sec.get("prose") is not None else "content"] = woven
                out.append(new)
            else:
                out.append(sec)
        return out
    except Exception:
        logger.debug("ensure_rendered failed", exc_info=True)
        return sections
