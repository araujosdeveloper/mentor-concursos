from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da API obtida do ambiente e de arquivos de secrets."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    app_env: str = "development"
    log_level: str = "INFO"
    service_name: str = "mentor-concursos-api"
    database_host: str = "mentor-concursos-postgres"
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = "mentor_concursos"
    database_user: str = "mentor_app"
    database_password: str = ""
    redis_host: str = "mentor-concursos-redis"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_password: str = ""
    readiness_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    service_token_file: Path = Path("/run/secrets/mentor_api_service_token")


@lru_cache
def get_settings() -> Settings:
    return Settings()
