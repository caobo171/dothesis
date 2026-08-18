"""Safe user-facing HTTP headers shared by downloads and previews."""
from __future__ import annotations

import unicodedata
from urllib.parse import quote


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    """RFC 5987 Content-Disposition with an ASCII-compatible fallback.

    S3 validates response header overrides as ISO-8859-1 before serving a
    presigned GET. Vietnamese filenames therefore cannot appear literally in
    ``filename=``; the real UTF-8 value belongs in percent-encoded ``filename*``.
    """
    safe = str(filename or "download").replace("\r", "").replace("\n", "")
    ascii_name = unicodedata.normalize("NFKD", safe).encode("ascii", "ignore").decode()
    fallback = (ascii_name or "download").replace('"', "'").replace("\\", "_")
    kind = disposition if disposition in {"attachment", "inline"} else "attachment"
    return f'{kind}; filename="{fallback}"; filename*=UTF-8\'\'{quote(safe, safe="")}'
