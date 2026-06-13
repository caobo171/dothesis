import logging
from unittest.mock import patch

from app.mail import send_template


def test_dummy_mode_when_mail_from_blank(monkeypatch, caplog):
    monkeypatch.setenv("DOTHESIS_MAIL_FROM", "")
    from app import settings as settings_mod
    settings_mod._settings = None

    from pathlib import Path
    tpl_dir = Path(settings_mod.__file__).parent / "mail_templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    sample = tpl_dir / "_test_dummy.html"
    sample.write_text("<p>Hi {{username}}</p>", encoding="utf-8")
    try:
        with caplog.at_level(logging.WARNING):
            ok = send_template("alice@e.com", "_test_dummy",
                               {"username": "alice"}, "Test")
        assert ok is True
        assert any("alice@e.com" in r.message for r in caplog.records)
    finally:
        sample.unlink(missing_ok=True)


def test_real_mode_calls_ses(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MAIL_FROM", "DoThesis <noreply@x.com>")
    monkeypatch.setenv("DOTHESIS_MAIL", "")
    from app import settings as settings_mod
    settings_mod._settings = None
    # Also reset the cached ses client so it picks up the new region/creds for this test
    from app import mail as mail_mod
    mail_mod._client = None

    from pathlib import Path
    tpl_dir = Path(settings_mod.__file__).parent / "mail_templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    sample = tpl_dir / "_test_real.html"
    sample.write_text("<p>Hi {{username}}</p>", encoding="utf-8")
    try:
        with patch("app.mail._ses") as ses_factory:
            client = ses_factory.return_value
            client.send_email.return_value = {"MessageId": "fake-123"}
            ok = send_template("alice@e.com", "_test_real",
                               {"username": "alice"}, "Test")
            assert ok is True
            client.send_email.assert_called_once()
            kwargs = client.send_email.call_args.kwargs
            assert kwargs["FromEmailAddress"] == "DoThesis <noreply@x.com>"
            assert kwargs["Destination"]["ToAddresses"] == ["alice@e.com"]
            assert "Hi alice" in kwargs["Content"]["Simple"]["Body"]["Html"]["Data"]
    finally:
        sample.unlink(missing_ok=True)
