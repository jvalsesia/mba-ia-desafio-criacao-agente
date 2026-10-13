import os
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "dados"
API_HOST = "127.0.0.1"
API_PORT = 8000

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_DATABASE_URL = "postgresql+asyncpg://aurora:aurora@localhost:5432/aurora"


class ConfigError(Exception):
    """Invalid or missing runtime configuration."""


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True, extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL

    @field_validator("database_url")
    @classmethod
    def _url_is_asyncpg(cls, value: str) -> str:
        try:
            url = make_url(value)
        except ArgumentError:
            raise ValueError("invalid") from None
        if url.drivername != "postgresql+asyncpg" or not url.host:
            raise ValueError("invalid")
        return value


class Settings(DatabaseSettings):
    google_api_key: str
    gemini_model_main: str = DEFAULT_MODEL
    gemini_model_specialists: str = DEFAULT_MODEL

    @field_validator("google_api_key")
    @classmethod
    def _key_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank")
        return value


INVALID_DATABASE_URL_MESSAGE = (
    "Configuração inválida: DATABASE_URL não é uma URL postgresql+asyncpg válida."
)


def load_database_url(env_file: str | Path | None = PROJECT_ROOT / ".env") -> str:
    try:
        return DatabaseSettings(_env_file=env_file).database_url  # type: ignore[call-arg]
    except ValidationError:
        raise ConfigError(INVALID_DATABASE_URL_MESSAGE) from None


def load_settings(env_file: str | Path | None = PROJECT_ROOT / ".env") -> Settings:
    try:
        settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        fields = {str(err["loc"][0]) for err in exc.errors() if err["loc"]}
        if "google_api_key" in fields:
            raise ConfigError(
                "Configuração inválida: defina GOOGLE_API_KEY no arquivo .env "
                "(copie .env.example para .env e preencha a chave do Google AI Studio)."
            ) from None
        if "database_url" in fields:
            raise ConfigError(INVALID_DATABASE_URL_MESSAGE) from None
        raise ConfigError("Configuração inválida.") from None
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    return settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()
