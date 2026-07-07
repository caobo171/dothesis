from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(alias="DATABASE_URL")
    aws_region: str = Field(alias="AWS_REGION")
    s3_bucket: str = Field(alias="S3_BUCKET")
    s3_prefix: str = Field(alias="S3_PREFIX", default="dothesis/")
    aws_access_key: str = Field(alias="AWS_ACCESS_KEY")
    aws_secret_key: str = Field(alias="AWS_SECRET_KEY")
    session_secret: str = Field(alias="SESSION_SECRET")
    gemini_api_key: str | None = Field(alias="GEMINI_API_KEY", default=None)
    openai_api_key: str | None = Field(alias="OPENAI_API_KEY", default=None)
    anthropic_api_key: str | None = Field(alias="ANTHROPIC_API_KEY", default=None)
    job_workdir_root: Path = Field(alias="JOB_WORKDIR_ROOT", default=Path("./var/jobs"))
    api_port: int = Field(alias="API_PORT", default=7100)
    web_origin: str = Field(alias="WEB_ORIGIN", default="http://localhost:3000")
    polar_access_token: str = Field(alias="POLAR_ACCESS_TOKEN", default="")
    polar_webhook_secret: str = Field(alias="POLAR_WEBHOOK_SECRET", default="")
    polar_server: str = Field(alias="POLAR_SERVER", default="sandbox")
    dothesis_base_url: str = Field(alias="DOTHESIS_BASE_URL", default="http://localhost:3000")
    # Comma-separated providers offered to users (e.g. "polar,paypal"). SePay is
    # always added on top for UTC+7 users when configured. "dummy" forces every
    # provider into no-real-API stub mode for local dev / tests.
    dothesis_payments: str = Field(alias="DOTHESIS_PAYMENTS", default="polar")
    # PayPal (raw REST via httpx — no SDK).
    paypal_client_id: str = Field(alias="PAYPAL_CLIENT_ID", default="")
    paypal_secret: str = Field(alias="PAYPAL_SECRET", default="")
    paypal_mode: str = Field(alias="PAYPAL_MODE", default="sandbox")  # sandbox|production
    paypal_webhook_id: str = Field(alias="PAYPAL_WEBHOOK_ID", default="")
    # SePay (Vietnamese VietQR bank transfer). Offered to UTC+7 users only.
    sepay_api_key: str = Field(alias="SEPAY_API_KEY", default="")
    sepay_account_number: str = Field(alias="SEPAY_ACCOUNT_NUMBER", default="")
    sepay_bank_code: str = Field(alias="SEPAY_BANK_CODE", default="")
    sepay_memo_prefix: str = Field(alias="SEPAY_MEMO_PREFIX", default="DT")
    # Fixed USD→VND rate for SePay package prices. Update when FX drifts.
    usd_to_vnd: int = Field(alias="USD_TO_VND", default=25000)
    mail_from: str = Field(alias="DOTHESIS_MAIL_FROM", default="")
    mail_region: str = Field(alias="DOTHESIS_MAIL_REGION", default="ap-southeast-1")
    dothesis_mail: str = Field(alias="DOTHESIS_MAIL", default="")
    # Optional SES-specific credentials. Survify uses dedicated SES keys distinct from S3.
    # When unset, mail.py falls back to aws_access_key / aws_secret_key.
    aws_ses_access_key: str = Field(alias="AWS_SES_ACCESS_KEY", default="")
    aws_ses_secret_key: str = Field(alias="AWS_SES_SECRET_KEY", default="")
    google_client_id: str = Field(alias="DOTHESIS_GOOGLE_CLIENT_ID", default="")
    signup_bonus_credits: int = Field(alias="DOTHESIS_SIGNUP_BONUS_CREDITS", default=100)
    orchestrator_enabled: bool = Field(alias="ORCHESTRATOR_ENABLED", default=False)
    # Shared secret for the service-to-service partner report endpoint
    # (POST /api/v1/partner/report). Set on both DoThesis and the calling
    # partner (e.g. Fillform). Empty disables the endpoint (401 on every call).
    partner_api_token: str = Field(alias="PARTNER_API_TOKEN", default="")
    langsmith_api_key: str | None = Field(alias="LANGSMITH_API_KEY", default=None)
    orchestrator_pg_pool_max: int = Field(alias="ORCHESTRATOR_PG_POOL_MAX", default=10)

    @field_validator("s3_prefix", mode="before")
    @classmethod
    def _ensure_trailing_slash(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        return v if v.endswith("/") else v + "/"

    @field_validator("job_workdir_root", mode="after")
    @classmethod
    def _resolve_workdir_absolute(cls, v: Path) -> Path:
        # The API and the engine subprocess run with different cwds.
        # Resolve once at settings-load time so both sides agree on the same absolute path.
        return v.expanduser().resolve()


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Force the next get_settings() call to re-read from environment.

    Useful in tests that monkeypatch env vars before calling create_app().
    """
    global _settings
    _settings = None
