from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr = Field(alias="BOT_TOKEN")
    admin_id: int = Field(alias="ADMIN_ID")
    database_url: str = Field(alias="DATABASE_URL")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_api_key: SecretStr | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-5-mini", alias="LLM_MODEL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    reminder_hour: int = Field(default=20, alias="REMINDER_HOUR", ge=0, le=23)
    timezone: str = Field(default="Asia/Yekaterinburg", alias="TIMEZONE")
    upload_dir: Path = Field(default=Path("uploads"), alias="UPLOAD_DIR")


@lru_cache
def get_settings() -> Settings:
    return Settings()
