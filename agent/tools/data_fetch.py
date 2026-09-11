"""Pull a dataset straight off a Google Sheets link into the project workspace.

Vietnamese students collect thesis data with Google Forms, so the data lives in
a Sheet and the LINK is what they paste into chat. Every data tool in this
package takes a workspace-relative path (`run_stats`, `parse_results`), and
nothing turned a URL into a file — so the agent told students to download and
re-upload, and phrased it as its own inability to "read the link".

Scope is deliberately narrow, and both limits are load-bearing:

  - HOST ALLOWLIST, checked before any connection. The URL arrives in a chat
    message; that is untrusted input, and it can be planted by a prompt
    injection inside a document the student uploaded. An unrestricted fetcher
    running server-side is an SSRF hole aimed at the API on localhost:7100 and
    at the cloud metadata endpoint. Judging a host after connecting is too
    late — the connection is the vulnerability.
  - CONTENT SNIFF, not status code. A sheet that is not shared publicly answers
    an anonymous export with HTTP 404 and ~8 KB of `text/html` (verified
    against a real student link, 2026-09-11). Saving that as the dataset is the
    same silent-garbage failure that `.xlsx`-as-UTF-8 and `.docx`-as-ZIP already
    cost this project — the file looks present, and the numbers are markup.

Reading a student's PRIVATE sheet is out of scope and needs Drive OAuth, which
is a subsystem rather than a tool. This reports the permission problem precisely
instead of pretending the link is unreadable.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx  # module-level so tests can monkeypatch data_fetch.httpx
from langchain_core.tools import tool

from agent.tools.workspace_paths import WorkspaceEscapeError, resolve_data_path

logger = logging.getLogger(__name__)

# Google only. Every other host — including anything on this machine — is
# refused before a socket is opened. See the module docstring.
_ALLOWED_HOSTS = {"docs.google.com", "drive.google.com"}

# 25 MB. A thesis dataset is a few hundred KB; this is a runaway guard, not a
# budget, and it is well under the 50 MB upload cap so the two paths can never
# disagree about what fits.
_MAX_BYTES = 25 * 1024 * 1024
_TIMEOUT = 30.0

_SHEET_ID = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")


def _sheet_ref(url: str) -> tuple[str, str | None]:
    """(sheet_id, gid) from a pasted Sheets URL. Raises ValueError if it is not
    a spreadsheet link.

    `gid` identifies the TAB the student was looking at. A thesis workbook
    routinely has several — raw form responses, cleaned data, a codebook — and
    dropping the gid exports the first one, which is usually the raw responses
    rather than the sheet they meant.
    """
    parsed = urlparse(url)
    m = _SHEET_ID.search(parsed.path)
    if not m:
        raise ValueError("not a spreadsheet URL")
    gid = None
    # Query first (`?gid=N`), then the fragment (`#gid=N`) — Google writes both,
    # and copying from the address bar usually carries the fragment.
    q = parse_qs(parsed.query).get("gid")
    if q:
        gid = q[0]
    elif parsed.fragment:
        f = parse_qs(parsed.fragment).get("gid")
        if f:
            gid = f[0]
    return m.group(1), gid


def _filename(headers, sheet_id: str, gid: str | None) -> str:
    """A safe `.csv` name, preferring the one Google supplies.

    The remote server chooses `Content-Disposition`, so this is attacker-
    influenced input: everything but the basename is dropped and the result is
    still resolved through `resolve_data_path` below. A name is a convenience;
    the confinement is the guarantee.
    """
    raw = ""
    cd = (headers.get("content-disposition") or "") if headers else ""
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    if m:
        raw = m.group(1).strip()
    raw = raw.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    raw = re.sub(r"[^\w\s.\-()]+", "", raw, flags=re.UNICODE).strip()
    if not raw or raw in {".", ".."}:
        raw = f"sheet_{sheet_id[:12]}" + (f"_{gid}" if gid else "")
    if not raw.lower().endswith(".csv"):
        raw += ".csv"
    return raw


def _looks_like_html(body: bytes, headers) -> bool:
    ctype = ((headers.get("content-type") or "") if headers else "").lower()
    if ctype.startswith("text/html"):
        return True
    return body[:200].lstrip().lower().startswith((b"<!doctype", b"<html"))


_NOT_PUBLIC = {
    "error": "sheet_not_public",
    "message": ("Link Google Sheets này chưa mở quyền xem công khai, nên không "
                "tải được dữ liệu (Google trả về trang 'Không tìm thấy')."),
    "how_to_fix": [
        "Mở Sheet → Share → General access → đổi thành 'Anyone with the link' "
        "– Viewer, rồi gửi lại link.",
        "Hoặc: File → Download → Microsoft Excel (.xlsx) hoặc "
        "Comma-separated values (.csv), rồi đính kèm file vào chat.",
    ],
}


def _fetch_impl(url: str, root) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        # Before any connection — see the module docstring.
        return json.dumps({
            "error": "host_not_allowed",
            "message": (f"Chỉ hỗ trợ link Google Sheets/Drive "
                        f"({', '.join(sorted(_ALLOWED_HOSTS))}); host '{host}' không được phép."),
            "how_to_fix": ["Tải dữ liệu về máy rồi đính kèm file vào chat."],
        }, ensure_ascii=False)

    try:
        sheet_id, gid = _sheet_ref(url)
    except ValueError:
        return json.dumps({
            "error": "not_a_spreadsheet",
            "message": "Link này không phải Google Sheets (chỉ đọc được bảng tính).",
            "how_to_fix": ["Gửi link Google Sheets, hoặc đính kèm file .xlsx/.csv/.sav."],
        }, ensure_ascii=False)

    export = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    if gid:
        export += f"&gid={gid}"

    try:
        r = httpx.get(export, follow_redirects=True, timeout=_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — a dead network is a message, not a crash
        logger.warning("sheets fetch failed for %s: %s", sheet_id, e)
        return json.dumps({
            "error": "fetch_failed",
            "message": f"Không tải được dữ liệu từ link ({type(e).__name__}).",
            "how_to_fix": ["Thử lại, hoặc tải file về và đính kèm vào chat."],
        }, ensure_ascii=False)

    body = r.content or b""
    # Content decides, not the status code: a consent or interstitial page can
    # come back 200 with markup in it.
    if _looks_like_html(body, r.headers) or r.status_code != 200:
        if _looks_like_html(body, r.headers) or r.status_code in (401, 403, 404):
            return json.dumps(_NOT_PUBLIC, ensure_ascii=False)
        return json.dumps({
            "error": "fetch_failed",
            "message": f"Google trả về HTTP {r.status_code}.",
            "how_to_fix": ["Thử lại, hoặc tải file về và đính kèm vào chat."],
        }, ensure_ascii=False)

    if len(body) > _MAX_BYTES:
        return json.dumps({
            "error": "too_large",
            "message": f"Bảng dữ liệu vượt quá {_MAX_BYTES // (1024 * 1024)} MB.",
            "how_to_fix": ["Lọc bớt cột/dòng không dùng rồi gửi lại."],
        }, ensure_ascii=False)

    name = _filename(r.headers, sheet_id, gid)
    rel = f"uploads/{name}"
    try:
        dest = resolve_data_path(rel, root, must_exist=False)
    except (WorkspaceEscapeError, ValueError):
        # The name came off a remote header; if it will not resolve inside the
        # workspace, fall back to one we generated rather than refusing the data.
        rel = f"uploads/sheet_{sheet_id[:12]}.csv"
        dest = resolve_data_path(rel, root, must_exist=False)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)

    from agent.data_profile import profile_dataset  # noqa: PLC0415 — pandas is heavy

    return json.dumps({
        "ok": True,
        "file": rel,
        "profile": profile_dataset(body, name),
        "source_url": url,
        "note": f"Đã tải dữ liệu vào {rel}. Dùng đường dẫn này cho run_stats.",
    }, ensure_ascii=False)


def make_data_fetch_tools(project_dir) -> list:
    """Build `fetch_data_url` bound to one project's workspace root.

    Same bound-factory shape as `make_stats_tools`: the model names a URL, never
    a destination, so the file can only ever land inside this project.
    """
    from pathlib import Path as _Path  # noqa: PLC0415

    _root = _Path(project_dir).resolve(strict=False)

    @tool
    def fetch_data_url(url: str) -> str:
        """Tải dữ liệu từ một link Google Sheets vào workspace của dự án.

        Dùng NGAY khi sinh viên gửi link Google Sheets chứa dữ liệu khảo sát —
        đừng bảo họ tải file về trước khi thử tool này.

        Trả JSON. Khi thành công: {"ok": true, "file": "uploads/<tên>.csv",
        "profile": "<các cột + vài dòng đầu>"} — đưa `file` cho run_stats.
        Khi thất bại: {"error": ..., "message": ..., "how_to_fix": [...]} —
        đọc `how_to_fix` cho sinh viên, đừng nói chung chung là không đọc được.

        Chỉ nhận link docs.google.com / drive.google.com.
        """
        return _fetch_impl(url, _root)

    return [fetch_data_url]
