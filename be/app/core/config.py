"""Application configuration loaded from environment variables / .env files.

Two files are read, in order (later wins):
  1. <repo root>/.env  — shared infrastructure (Supabase credentials)
  2. <be>/.env         — backend-local overrides
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BASE_DIR.parent

PLACEHOLDER_PASSWORD = "YOUR-PASSWORD"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Application
    PROJECT_NAME: str = "Annocollector API"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # CORS (JSON list in env: ["http://localhost:3000"])
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Supabase (repo-root .env)
    SUPABASE_HOST: str | None = None
    SUPABASE_PORT: int = 6543
    SUPABASE_DB: str = "postgres"
    SUPABASE_USER: str | None = None
    SUPABASE_PASSWORD: str | None = None
    SUPABASE_MIGRATION_PORT: int | None = None
    DB_SSL: bool = True

    # Explicit connection strings override the Supabase settings above.
    DATABASE_URL: str | None = None
    MIGRATION_DATABASE_URL: str | None = None

    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Create tables on startup (dev only, Alembic owns the schema otherwise)
    AUTO_CREATE_TABLES: bool = False

    # Auth (JWT access token + refresh token stored in DB)
    JWT_SECRET_KEY: str | None = None
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 7
    ACTIVATION_TOKEN_HOURS: int = 72
    REFRESH_COOKIE_SECURE: bool = True
    LOGIN_RATE_LIMIT: int = 10  # attempts per minute per ip + email
    FRONTEND_URL: str = "http://localhost:3000"

    # File storage: Cloudflare R2 when configured, otherwise a local folder (dev only).
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET: str | None = None
    LOCAL_STORAGE_DIR: str = str(BASE_DIR / ".storage")
    API_PUBLIC_URL: str = "http://localhost:8000"
    MAX_UPLOAD_MB: int = 100

    @property
    def r2_configured(self) -> bool:
        return all(
            (self.R2_ACCOUNT_ID, self.R2_ACCESS_KEY_ID, self.R2_SECRET_ACCESS_KEY, self.R2_BUCKET)
        ) and not any(
            "<" in (v or "")
            for v in (self.R2_ACCOUNT_ID, self.R2_ACCESS_KEY_ID, self.R2_SECRET_ACCESS_KEY)
        )

    @property
    def jwt_secret_key(self) -> str:
        if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY is missing or shorter than 32 characters. "
                "Set it in the repo-root .env (see .env.example)."
            )
        return self.JWT_SECRET_KEY

    @property
    def is_supabase(self) -> bool:
        return self.DATABASE_URL is None and self.SUPABASE_HOST is not None

    @property
    def is_sqlite(self) -> bool:
        if self.DATABASE_URL:
            return self.DATABASE_URL.startswith("sqlite")
        return self.SUPABASE_HOST is None

    @property
    def database_url(self) -> str | URL:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.SUPABASE_HOST:
            return self._supabase_url(self.SUPABASE_PORT)
        # Fallback so a fresh clone / the test suite works without credentials.
        return f"sqlite+aiosqlite:///{(BASE_DIR / 'app.db').as_posix()}"

    @property
    def migration_database_url(self) -> str | URL:
        """Alembic connection string.

        Supabase recommends the session pooler (5432) for DDL, so migrations
        can use a different port than the application.
        """
        if self.MIGRATION_DATABASE_URL:
            return self.MIGRATION_DATABASE_URL
        if self.is_supabase:
            return self._supabase_url(self.SUPABASE_MIGRATION_PORT or self.SUPABASE_PORT)
        return self.database_url

    def _supabase_url(self, port: int) -> URL:
        missing = [
            name
            for name, value in (
                ("SUPABASE_HOST", self.SUPABASE_HOST),
                ("SUPABASE_USER", self.SUPABASE_USER),
                ("SUPABASE_PASSWORD", self.SUPABASE_PASSWORD),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Supabase is not fully configured. Missing in .env: "
                + ", ".join(missing)
                + ". See .env.example."
            )
        if PLACEHOLDER_PASSWORD in (self.SUPABASE_PASSWORD or ""):
            raise RuntimeError(
                "SUPABASE_PASSWORD still contains the placeholder [YOUR-PASSWORD]. "
                "Put your real Supabase database password in the repo-root .env."
            )
        return URL.create(
            "postgresql+asyncpg",
            username=self.SUPABASE_USER,
            password=self.SUPABASE_PASSWORD,
            host=self.SUPABASE_HOST,
            port=port,
            database=self.SUPABASE_DB,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
