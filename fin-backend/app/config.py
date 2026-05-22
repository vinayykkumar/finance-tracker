from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://finance:finance@localhost:5432/finance"
    secret_key: str = "change-me"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url_sync(self) -> str:
        """Alembic / sync tools: use psycopg3 (installed) instead of default psycopg2."""
        u = self.database_url
        if "+asyncpg" in u:
            return u.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        return u


@lru_cache
def get_settings() -> Settings:
    return Settings()
