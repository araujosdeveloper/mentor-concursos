from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
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
    rate_limit_requests: int = Field(default=60, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    embeddings_url: str = "http://mentor-concursos-embeddings:8090"
    external_url: str = "http://mentor-concursos-external:8091"
    service_token_file: Path = Path("/run/secrets/mentor_api_service_token")
    context_hmac_key_file: Path = Path("/run/secrets/hermes_context_hmac_key")
    require_signed_context: bool = False
    signed_context_max_age_seconds: int = Field(default=60, ge=1, le=300)
    signed_context_replay_ttl_seconds: int = Field(default=120, ge=60, le=600)

    @model_validator(mode="after")
    def production_requires_signed_context(self) -> "Settings":
        if self.app_env.lower() == "production" and not self.require_signed_context:
            raise ValueError("REQUIRE_SIGNED_CONTEXT must be enabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
