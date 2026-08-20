from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 실행 디렉터리와 관계없이 실제 backend/.env만 읽는다.
        # .env.example은 Git에 올릴 형식 예시이며 런타임 설정 파일이 아니다.
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Global Meeting Communication Coach MVP API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/meeting_mvp"
    frontend_origin: str = "http://localhost:5173"
    public_app_url: str = "http://localhost:5173"
    daily_api_key: SecretStr = SecretStr("")
    daily_api_base_url: str = "https://api.daily.co/v1"
    daily_domain: str = "team.daily.co"
    daily_room_ttl_minutes: int = Field(default=180, ge=15, le=1440)
    daily_token_ttl_minutes: int = Field(default=120, ge=5, le=1440)
    daily_request_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_request_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    openai_max_retries: int = Field(default=3, ge=0, le=10)
    sql_echo: bool = False

    @field_validator("daily_api_base_url")
    @classmethod
    def daily_api_must_use_https(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("DAILY_API_BASE_URL은 HTTPS URL이어야 합니다.")
        return normalized

    @field_validator("daily_domain")
    @classmethod
    def daily_domain_must_be_hostname(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or "://" in normalized or "/" in normalized or "." not in normalized:
            raise ValueError("DAILY_DOMAIN에는 Daily 호스트 이름만 입력해주세요.")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
