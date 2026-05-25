"""Verify Google ID tokens via the google-auth library."""
from __future__ import annotations

from google.auth.transport import requests as g_requests
from google.oauth2 import id_token as gid

from .settings import get_settings


def verify_google_id_token(id_token_str: str) -> dict:
    """Returns {email, google_id, name}. Raises ValueError if invalid."""
    s = get_settings()
    if not s.google_client_id:
        raise ValueError("google_not_configured")
    try:
        info = gid.verify_oauth2_token(id_token_str, g_requests.Request(), s.google_client_id)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(str(e))
    email = info.get("email")
    sub = info.get("sub")
    if not email or not sub:
        raise ValueError("missing_fields")
    return {
        "email": email.lower(),
        "google_id": str(sub),
        "name": info.get("name") or email.split("@")[0],
    }
