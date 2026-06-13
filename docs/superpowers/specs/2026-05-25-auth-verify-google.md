# Auth: email verification + password reset + Google sign-in

**Date:** 2026-05-25
**Status:** Draft — pending user review

## Goal

Bring dothesis's auth in line with Survify: real email verification on signup, password reset by email, and a "Sign in with Google" button. Block login until verification, grant signup-bonus credits on first verified login, and auto-link Google accounts to existing email accounts when the email matches.

## Non-goals

- Magic-link passwordless login.
- Multi-factor (TOTP / SMS) — out of scope this round.
- Social providers beyond Google (Apple, GitHub, Facebook).
- Replacing the cookie-based session with JWT for app traffic. JWT-style tokens are introduced only for the email links (verify, reset).
- Marketing emails.

## Decisions (locked from brainstorming)

- **Email delivery:** AWS SESv2 via `boto3`, reusing the same `AWS_ACCESS_KEY`/`AWS_SECRET_KEY` already used for S3.
- **Verification gate:** block login until verified. Signup does NOT issue a session.
- **Token format:** signed JWT-style tokens via `itsdangerous.URLSafeTimedSerializer` (already vendored for session cookies). Verify TTL = 24h, reset TTL = 60min.
- **Signup bonus:** `DOTHESIS_SIGNUP_BONUS_CREDITS` (default 100), granted on first verified login (email path) or first Google sign-in.
- **Google flow:** Google Identity Services (GSI) first-party button; `id_token` posted to backend; backend verifies via `google-auth` Python lib.
- **Signup fields:** `username + email + password`. Username required and unique.

---

## Schema changes

One Alembic migration extending `users`:

```sql
-- Make username required + unique. Existing rows backfilled to
-- "<email-prefix><4-random-digits>" before applying NOT NULL.
ALTER TABLE users
    ALTER COLUMN username SET NOT NULL,
    ADD CONSTRAINT users_username_key UNIQUE (username);

ALTER TABLE users
    ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN google_id VARCHAR(64) UNIQUE,
    ADD COLUMN last_login TIMESTAMPTZ,
    ADD COLUMN last_verify_sent_at TIMESTAMPTZ;
```

The migration's `upgrade()` runs a one-time `UPDATE users SET username = ...` for any rows where `username IS NULL`, picking a unique value before the `NOT NULL` constraint lands.

## File structure

**API (`api/app/`):**
- New: `mail.py` — SESv2 client wrapper.
- New: `mail_templates/verify_email.html`, `mail_templates/reset_password.html`.
- New: `auth_tokens.py` — `make_verify_token`, `make_reset_token`, `decode_token`.
- New: `google_auth.py` — `verify_google_id_token`.
- Modify: `models.py` — add the four new columns; flip `username` to `mapped_column(String(64), unique=True, nullable=False)`.
- Modify: `routers/auth.py` — `signup`, `login` shape changes + new endpoints (`verify`, `resend-verification`, `forgot-password`, `reset-password`, `google`).
- Modify: `settings.py` — new env knobs: `mail_from`, `mail_region`, `google_client_id`, `signup_bonus_credits`.
- Modify: `pyproject.toml` — add `google-auth>=2.34`.
- New migration: `migrations/versions/<rev>_auth_verify_google.py`.

**API tests (`api/tests/`):**
- New: `test_auth_signup_verify.py`, `test_auth_login_gate.py`, `test_auth_resend.py`, `test_auth_password_reset.py`, `test_auth_google.py`, `test_mail_dummy_mode.py`.

**Web (`web/`):**
- Modify: `app/login/page.jsx`, `app/signup/page.jsx` — rewrite in Tailwind to match Survify auth pages, add Google button, handle `code === "unverified"` and `code === "use_google"`.
- New: `app/wait-verify/page.jsx`, `app/verify/page.jsx`, `app/forgot-password/page.jsx`, `app/reset-password/page.jsx`.
- New: `app/components/auth/GoogleSignInButton.tsx` — wraps Google's GSI script + callback.
- Modify: `proxy.ts` — add `/wait-verify`, `/verify`, `/forgot-password`, `/reset-password` to `PUBLIC_PATHS`.

---

## Backend

### `mail.py` (SESv2 wrapper)

Single class `Mailer` with two static methods:

- `send_html(to: str, subject: str, html: str) -> bool` — builds a SESv2 `SendEmailCommand` (Simple content, HTML body, UTF-8). From address is `settings.mail_from` (e.g. `DoThesis <noreply@dothesis.app>`). Returns `True` on success, `False` and logs on failure (never raises — auth flows should not break on a flaky email).
- `send_template(to: str, template: str, vars: dict, subject: str) -> bool` — loads `mail_templates/<template>.html`, substitutes `{{key}}` for each var, calls `send_html`.

**Dummy mode**: when `settings.mail_from` is empty OR `settings.dothesis_mail` is `"dummy"`, the wrapper logs the rendered HTML and returns `True` without touching SES. Lets local dev work without AWS creds.

```python
# api/app/mail.py (sketch)
import boto3, logging
from pathlib import Path
from .settings import get_settings

log = logging.getLogger(__name__)
_TEMPLATES_DIR = Path(__file__).parent / "mail_templates"
_client = None

def _ses():
    global _client
    if _client is None:
        s = get_settings()
        _client = boto3.client(
            "sesv2",
            region_name=s.mail_region or "ap-southeast-1",
            aws_access_key_id=s.aws_access_key,
            aws_secret_access_key=s.aws_secret_key,
        )
    return _client

def _render(template: str, vars: dict) -> str:
    html = (_TEMPLATES_DIR / f"{template}.html").read_text(encoding="utf-8")
    for k, v in vars.items():
        html = html.replace("{{" + k + "}}", str(v))
    return html

def send_template(to: str, template: str, vars: dict, subject: str) -> bool:
    s = get_settings()
    html = _render(template, vars)
    if s.dothesis_mail == "dummy" or not s.mail_from:
        log.warning("mail dummy mode → %s: %s\n%s", to, subject, html[:400])
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
```

### `auth_tokens.py`

`URLSafeTimedSerializer(secret=settings.session_secret, salt="auth-token")`. Two helpers:

```python
def make_verify_token(user_id: uuid.UUID) -> str:
    return _s.dumps({"uid": str(user_id), "kind": "verify"})

def make_reset_token(user_id: uuid.UUID) -> str:
    return _s.dumps({"uid": str(user_id), "kind": "reset"})

def decode_token(token: str, kind: str, max_age: int) -> uuid.UUID:
    """Raises ValueError on bad/expired/wrong-kind. Returns user_id on success."""
    data = _s.loads(token, max_age=max_age)
    if not isinstance(data, dict) or data.get("kind") != kind:
        raise ValueError("token_mismatch")
    return uuid.UUID(data["uid"])
```

TTL constants: `VERIFY_TTL = 24 * 3600`, `RESET_TTL = 60 * 60`.

### `google_auth.py`

```python
from google.oauth2 import id_token as gid
from google.auth.transport import requests as g_requests

def verify_google_id_token(id_token_str: str) -> dict:
    """Returns {email, google_id (=sub), name}. Raises ValueError if invalid."""
    s = get_settings()
    info = gid.verify_oauth2_token(id_token_str, g_requests.Request(), s.google_client_id)
    return {
        "email": info["email"].lower(),
        "google_id": info["sub"],
        "name": info.get("name") or info["email"].split("@")[0],
    }
```

### Endpoints (`routers/auth.py`)

#### POST /signup
Body: `{username, email, password}` (Pydantic `SignupRequest`).
- Validate `username` matches `^[a-zA-Z0-9_]{3,32}$`. 422 otherwise.
- Look up by email AND by username; either taken → 409.
- Hash password. Insert user with `email_verified=False, credit=0, username=username.lower()`.
- Generate verify token. Build `verify_url = f"{settings.web_origin}/verify?token={token}"`.
- `send_template(email, "verify_email", {username, verify_url, expires_hours: 24}, "Confirm your DoThesis email")`.
- Set `last_verify_sent_at = now()`.
- Return 201 `{ok: true, email}`. No session cookie.

#### POST /login
Existing endpoint. Two changes:
- After password check, if `user.email_verified is False`, raise 403 `{error: {code: "unverified", message: "Please verify your email", email: user.email}}`.
- If `user.google_id` is set AND password check fails, raise 401 `{error: {code: "use_google", message: "This email is linked to Google. Use the Google button."}}`.
- On success, set `user.last_login = now()`, issue cookie as before.

#### POST /verify
Body: `{token}`.
- Decode with `kind="verify", max_age=VERIFY_TTL`. ValueError → 400 `{code: "token_invalid"|"token_expired"}`.
- Load user. If already verified, return 200 `{ok: true, already_verified: true}`. Idempotent — no double credit grant.
- Set `email_verified=True`. Grant signup bonus via existing `credit_ledger.credit(...)` with `reason="signup_bonus", ref_type="user", ref_id=user.id`.
- Issue session cookie now so the user is logged in immediately after verifying.
- Return 200 with the user object.

#### POST /resend-verification
Body: `{email}`.
- Find user by email. If not found OR already verified → return 200 `{ok: true}` (no enumeration).
- If `last_verify_sent_at` < 60 seconds ago → 429 `{code: "throttled", retry_in: <seconds>}`.
- Mint a fresh token, send the email, update `last_verify_sent_at`.
- Return 200 `{ok: true}`.

#### POST /forgot-password
Body: `{email}`.
- Find user. Whether or not found → return 200 `{ok: true}`.
- If found, mint reset token, send via `reset_password` template with `reset_url = f"{web_origin}/reset-password?token={token}"`, `expires_minutes: 60`.

#### POST /reset-password
Body: `{token, new_password}`.
- `new_password` validated `min_length=8`.
- Decode `kind="reset", max_age=RESET_TTL`. Bad → 400.
- Update `user.password_hash`. Delete all `Session` rows for that user (forced logout of any active sessions).
- Return 200 `{ok: true}`. Frontend redirects to `/login` with a success banner.

#### POST /google
Body: `{id_token}`.
- `verify_google_id_token(id_token)` → `{email, google_id, name}`. ValueError → 401 `{code: "bad_google_token"}`.
- Look up by `google_id`. Else by `email` and link (set `google_id`, set `email_verified=True`). Else create new:
  - Generate username `f"{emailPrefix}{4-digit-rand}"`, ensuring uniqueness with a retry loop.
  - `password_hash` = bcrypt of a random 32-byte secret (unusable for password login).
  - `email_verified=True, google_id=google_id, credit=settings.signup_bonus_credits`.
  - Insert a `credit_transactions` row with `reason="signup_bonus"`.
- `last_login = now()`. Issue session cookie. Return user.

---

## Frontend

### `GoogleSignInButton.tsx`

```tsx
"use client";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/app/lib/api";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

export function GoogleSignInButton({ onError }: { onError?: (m: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (!CLIENT_ID) return;
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true; s.defer = true;
    document.body.appendChild(s);
    s.onload = () => {
      // @ts-expect-error gsi global
      window.google?.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: async (resp: any) => {
          try {
            await apiFetch("/auth/google", { method: "POST", body: { id_token: resp.credential } });
            router.push("/");
          } catch (e: any) {
            onError?.(e?.body?.error?.message || "Google sign-in failed");
          }
        },
      });
      // @ts-expect-error gsi global
      window.google?.accounts.id.renderButton(ref.current, { theme: "outline", size: "large", width: 320 });
    };
    return () => { s.remove(); };
  }, [router, onError]);

  if (!CLIENT_ID) {
    return (
      <button disabled className="opacity-50 cursor-not-allowed rounded-xl border border-ink-200 px-4 py-2 text-sm">
        Google sign-in (not configured)
      </button>
    );
  }
  return <div ref={ref} />;
}
```

### Pages

All five auth pages share a layout: centered card on the `ink-50` page background, brand mark up top, max-width 420px card with `border border-ink-100 rounded-2xl shadow-sm p-8 bg-white`. Tailwind only.

- **`login/page.jsx`** — Google button, "or" divider, email+password form. On 403 `unverified` → inline banner: "Please verify your email" + "Resend email" button. On 401 `use_google` → banner: "This account uses Google sign-in" + arrow pointing at the Google button.
- **`signup/page.jsx`** — Google button, divider, username+email+password form. Client-side username regex check. On success → `router.push("/wait-verify?email=" + encodeURIComponent(email))`.
- **`wait-verify/page.jsx`** — Big "Check your email" heading, the email address. "Resend email" button calling `/resend-verification` — disabled for 60s after each click with a countdown. Below: "Wrong address? [Go back]".
- **`verify/page.jsx`** — On mount reads `?token=...`, POSTs `/verify`. Three states:
  - Pending: spinner + "Verifying…"
  - Success: green check + "You're in!" + auto-redirect to `/` after 2s.
  - Error: red X + error message + "Resend email" button.
- **`forgot-password/page.jsx`** — Email field. After submit: "If that email exists in our system, we sent a reset link. Check your inbox."
- **`reset-password/page.jsx`** — Reads `?token=...`. New password + confirm. On success → `/login?reset=success`.

### Middleware (`proxy.ts`)

Add `/wait-verify`, `/verify`, `/forgot-password`, `/reset-password` to `PUBLIC_PATHS`. The existing list already has `/login`, `/signup`, `/_next`, `/favicon.ico`.

---

## Email templates

Two files in `api/app/mail_templates/`. Pure HTML with inline CSS. No web fonts (Gmail strips them); use system stacks. Variables wrapped in `{{name}}` for `str.replace` substitution.

**Template structure** (shared):
- 600px-wide centered table (the only reliable layout primitive across mail clients).
- Brand row with the DoThesis logo (linked PNG hosted at `web_origin/static/logo-email.png`).
- White card with the heading, greeting, CTA button (primary blue `#1c2eff`, white text, 12px border-radius), fallback URL line, expiry notice.
- Footer with `© 2026 DoThesis` and an unsub-not-applicable hint.

**Variables:**
- `verify_email.html`: `{{username}}`, `{{verify_url}}`, `{{expires_hours}}`.
- `reset_password.html`: `{{username}}`, `{{reset_url}}`, `{{expires_minutes}}`.

---

## Google flow (end-to-end)

```
Browser                              dothesis API                 Google
   │                                                                 │
   │ click "Sign in with Google"                                     │
   ├──── GSI popup ─────────────────────────────────────────────────►│
   │ id_token + email + name                                         │
   │◄────────────────────────────────────────────────────────────────┤
   │
   │ POST /api/v1/auth/google {id_token}
   ├────────────────────────────►│ verify id_token via google-auth lib
   │                             │ (audience check = DOTHESIS_GOOGLE_CLIENT_ID)
   │                             │   ├─ look up by google_id
   │                             │   ├─ else look up by email (link, auto-verify)
   │                             │   └─ else create new (verified, +bonus credits)
   │                             │ issue dothesis_session cookie
   │                             │ update last_login
   │ user object                 │
   │◄────────────────────────────┤
   │ router.push("/")
```

### Account linking edge cases

1. **Email signup → later Google with same email** → existing row found by email, `google_id` attached, `email_verified` set true if not already, session issued. No duplicate user.
2. **Google signup → later tries email/password login** → 401 `{code: "use_google"}`. UI shows "This email is linked to Google — use the Google button."
3. **Two Google accounts collide on `google_id`** → impossible (Google `sub` is globally unique).
4. **Existing account has both a Google id AND a usable password** (user signed up email-first, verified, then linked Google) → both paths work.

---

## Settings (`api/app/settings.py` additions)

```python
mail_from: str = ""                  # e.g. "DoThesis <noreply@dothesis.app>"
mail_region: str = "ap-southeast-1"
dothesis_mail: str = ""             # "" | "dummy"
google_client_id: str = ""
signup_bonus_credits: int = 100
```

Web env:
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` — same value, surfaced to the browser for GSI.

---

## Testing strategy

### Backend (pytest)

All Mailer calls are patched (`unittest.mock.patch("app.mail.send_template")`) so nothing actually hits SES. One narrow `test_mail.py` exercises the real SES client only when `DOTHESIS_RUN_SES_LIVE_TESTS=1` (off in CI).

- `test_auth_signup_verify.py` — signup returns 201 + no cookie + `email_verified=False`. `/verify` flips the flag, grants bonus. Second `/verify` is idempotent. Expired token → 400.
- `test_auth_login_gate.py` — login on unverified → 403 `unverified`. Login on verified → 200 + cookie + bonus already granted (so balance reflects it).
- `test_auth_resend.py` — first call mails, second within 60s → 429. After 60s another call works.
- `test_auth_password_reset.py` — `/forgot-password` for unknown email → 200 (no enumeration). For known email → mails token. `/reset-password` updates `password_hash` + invalidates sessions. Expired → 400.
- `test_auth_google.py` — `/google` with mocked `verify_oauth2_token` returns session. First call creates user with `email_verified=True` and bonus. Existing email account found and linked. Existing `google_id` just logs in.
- `test_mail_dummy_mode.py` — when `mail_from` blank, `send_template` returns True without raising; logs the body.

### Frontend (manual)

No automated tests this round. Manual smoke checklist in the implementation plan:

1. Signup → wait-verify → click email link → dashboard with 100 credits.
2. Signup → wait → resend → second link works → dashboard.
3. Forgot password → email → reset → login → success.
4. Google → dashboard.
5. Login on unverified account → 403 with resend CTA.
6. Email-password user later clicks Google with same email → no duplicate row, both paths work next time.

---

## Migration order (informational — actual plan in next phase)

1. Alembic migration (schema + username backfill).
2. `mail.py` + templates + `auth_tokens.py` + `google_auth.py` modules with unit tests.
3. Update `routers/auth.py`: signup/login changes + new endpoints with their tests.
4. Update frontend pages + add `GoogleSignInButton`.
5. Update `proxy.ts` PUBLIC_PATHS.
6. Manual smoke pass with dummy-mail mode (no SES creds yet).
7. (Deploy-time) add real `DOTHESIS_MAIL_FROM`, AWS SES verified identity, and `DOTHESIS_GOOGLE_CLIENT_ID`.

## Risks / open questions

- **SES sandbox mode**: a new AWS account starts SES in sandbox where you can only send to verified addresses. The first real-traffic deploy will need an SES production-access request (24-72h). Until then dummy mode keeps things flowing.
- **Username collisions on backfill**: the migration generates `<email_prefix><4 digits>` and retries on collision. With <1000 existing users the worst case is ~10 retries.
- **Sessions invalidation on password reset**: deletes Session rows but doesn't notify other devices. Acceptable for now.
- **Bonus credit fraud**: a user could re-create accounts to farm 100 credits each. Mitigated by email verification (verified emails per-domain are limited) but not eliminated. Acceptable for an MVP.

## Out of scope

- Per-device sessions, "Sign out everywhere", session listing.
- Apple Sign In, Magic Links, WebAuthn.
- Marketing emails / list management.
- Username changes after signup.
