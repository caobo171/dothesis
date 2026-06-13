"""SESv2-backed transactional email with dummy mode for local dev."""
from __future__ import annotations

import logging
from pathlib import Path

import boto3

from .settings import get_settings

log = logging.getLogger(__name__)
_TEMPLATES_DIR = Path(__file__).parent / "mail_templates"
_client = None


def _ses():
    global _client
    if _client is None:
        s = get_settings()
        # Prefer SES-specific creds when set (Survify pattern); fall back to the
        # general AWS creds used by S3.
        access_key = s.aws_ses_access_key or s.aws_access_key
        secret_key = s.aws_ses_secret_key or s.aws_secret_key
        _client = boto3.client(
            "sesv2",
            region_name=s.mail_region or "ap-southeast-1",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
    return _client


def _render(template: str, vars: dict) -> str:
    path = _TEMPLATES_DIR / f"{template}.html"
    html = path.read_text(encoding="utf-8")
    for k, v in vars.items():
        html = html.replace("{{" + k + "}}", str(v))
    return html


def send_html(to: str, subject: str, html: str) -> bool:
    s = get_settings()
    if s.dothesis_mail == "dummy" or not s.mail_from:
        log.warning("mail dummy mode to=%s subject=%s body=%s",
                    to, subject, html[:400])
        return True
    try:
        _ses().send_email(
            FromEmailAddress=s.mail_from,
            Destination={"ToAddresses": [to]},
            Content={"Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
            }},
        )
        return True
    except Exception:
        log.exception("SES send failed for %s", to)
        return False


def send_template(to: str, template: str, vars: dict, subject: str) -> bool:
    html = _render(template, vars)
    return send_html(to, subject, html)
