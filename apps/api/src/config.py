from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração não secreta da API obtida exclusivamente do ambiente."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    app_env: str = "development"
    log_level: str = "INFO"
    service_name: str = "mentor-concursos-api"
    database_host: str = "mentor-concursos-postgres"
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str | None = None
    database_user: str | None = None
    database_password: str | None = None
    redis_host: str = "mentor-concursos-redis"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_password: str | None = None
    readiness_timeout_seconds: float = Field(default=1.0, gt=0, le=10)


@lru_cache
def get_settings() -> Settings:
    return Settings()
