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
    s3_prefix: str = Field(alias="S3_PREFIX", default="opendraft/")
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
    opendraft_base_url: str = Field(alias="OPENDRAFT_BASE_URL", default="http://localhost:3000")
    opendraft_payments: str = Field(alias="OPENDRAFT_PAYMENTS", default="polar")
    mail_from: str = Field(alias="OPENDRAFT_MAIL_FROM", default="")
    mail_region: str = Field(alias="OPENDRAFT_MAIL_REGION", default="ap-southeast-1")
    opendraft_mail: str = Field(alias="OPENDRAFT_MAIL", default="")
    google_client_id: str = Field(alias="OPENDRAFT_GOOGLE_CLIENT_ID", default="")
    signup_bonus_credits: int = Field(alias="OPENDRAFT_SIGNUP_BONUS_CREDITS", default=100)

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
