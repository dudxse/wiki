from __future__ import annotations

import os
from functools import lru_cache, partial

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_required(name: str) -> str:
    """Return a required environment variable or raise a clear error."""

    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_optional(name: str, default: str) -> str:
    """Return an environment variable value or a safe default."""

    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_optional_bool(name: str, default: bool) -> bool:
    """Return a boolean environment variable value or a safe default."""

    value = os.getenv(name)
    if value is None or value == "":
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise RuntimeError(f"Invalid boolean value for {name}: {value}")


def _env_optional_float(name: str, default: float) -> float:
    """Return a float environment variable value or a safe default."""

    value = os.getenv(name)
    if value is None or value == "":
        return default

    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid float value for {name}: {value}") from exc


def _env_optional_int(name: str, default: int) -> int:
    """Return an integer environment variable value or a safe default."""

    value = os.getenv(name)
    if value is None or value == "":
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer value for {name}: {value}") from exc


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_user: str = Field(
        default="postgres", alias="POSTGRES_USER", description="Postgres username."
    )
    postgres_password: str = Field(
        default="postgres", alias="POSTGRES_PASSWORD", description="Postgres password."
    )
    postgres_db: str = Field(
        default="summaries", alias="POSTGRES_DB", description="Postgres database name."
    )
    postgres_host: str = Field(default="db", alias="POSTGRES_HOST", description="Postgres host.")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT", description="Postgres port.")

    @property
    def database_url(self) -> str:
        """Construct database URL from env var or components."""
        if url := os.getenv("DATABASE_URL"):
            return url

        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    openai_api_key: str = Field(
        default_factory=partial(_env_required, "OPENAI_API_KEY"),
        alias="OPENAI_API_KEY",
        description="OpenAI API key used by LangChain.",
    )
    openai_model: str = Field(
        default_factory=partial(_env_required, "OPENAI_MODEL"),
        alias="OPENAI_MODEL",
        description="OpenAI model name used for summarization.",
    )
    openai_fallback_model: str = Field(
        default_factory=partial(_env_optional, "OPENAI_FALLBACK_MODEL", ""),
        alias="OPENAI_FALLBACK_MODEL",
        description="Fallback OpenAI model name used when the primary model fails.",
    )
    log_level: str = Field(
        default_factory=partial(_env_required, "LOG_LEVEL"),
        alias="LOG_LEVEL",
        description="Application log level.",
    )
    log_debug_enabled: bool = Field(
        default_factory=partial(_env_optional_bool, "LOG_DEBUG_ENABLED", True),
        alias="LOG_DEBUG_ENABLED",
        description="Enable DEBUG logs when true.",
    )
    log_info_enabled: bool = Field(
        default_factory=partial(_env_optional_bool, "LOG_INFO_ENABLED", True),
        alias="LOG_INFO_ENABLED",
        description="Enable INFO logs when true.",
    )
    log_warning_enabled: bool = Field(
        default_factory=partial(_env_optional_bool, "LOG_WARNING_ENABLED", True),
        alias="LOG_WARNING_ENABLED",
        description="Enable WARNING logs when true.",
    )
    log_error_enabled: bool = Field(
        default_factory=partial(_env_optional_bool, "LOG_ERROR_ENABLED", True),
        alias="LOG_ERROR_ENABLED",
        description="Enable ERROR logs when true.",
    )
    log_critical_enabled: bool = Field(
        default_factory=partial(_env_optional_bool, "LOG_CRITICAL_ENABLED", True),
        alias="LOG_CRITICAL_ENABLED",
        description="Enable CRITICAL logs when true.",
    )
    http_timeout_seconds: float = Field(
        default_factory=partial(_env_optional_float, "HTTP_TIMEOUT_SECONDS", 10.0),
        alias="HTTP_TIMEOUT_SECONDS",
        description="Timeout for Wikipedia HTTP requests in seconds.",
    )
    llm_timeout_seconds: float = Field(
        default_factory=partial(_env_optional_float, "LLM_TIMEOUT_SECONDS", 30.0),
        alias="LLM_TIMEOUT_SECONDS",
        description="Timeout for LLM requests in seconds.",
    )
    wikipedia_user_agent: str = Field(
        default_factory=partial(_env_required, "WIKIPEDIA_USER_AGENT"),
        alias="WIKIPEDIA_USER_AGENT",
        description="User-Agent header used for Wikipedia requests.",
    )
    wikipedia_min_article_words: int = Field(
        default_factory=partial(_env_optional_int, "WIKIPEDIA_MIN_ARTICLE_WORDS", 50),
        alias="WIKIPEDIA_MIN_ARTICLE_WORDS",
        description="Minimum number of extracted words required to summarize.",
    )
    wikipedia_max_content_bytes: int = Field(
        default_factory=partial(_env_optional_int, "WIKIPEDIA_MAX_CONTENT_BYTES", 2_000_000),
        alias="WIKIPEDIA_MAX_CONTENT_BYTES",
        description="Maximum number of bytes allowed when downloading Wikipedia content.",
    )
    wikipedia_max_redirects: int = Field(
        default_factory=partial(_env_optional_int, "WIKIPEDIA_MAX_REDIRECTS", 5),
        alias="WIKIPEDIA_MAX_REDIRECTS",
        description="Maximum number of redirects allowed for Wikipedia requests.",
    )
    summary_word_count_max: int = Field(
        default_factory=partial(_env_optional_int, "SUMMARY_WORD_COUNT_MAX", 500),
        alias="SUMMARY_WORD_COUNT_MAX",
        description="Maximum allowed word_count value for summaries.",
    )
    enable_portuguese_translation: bool = Field(
        default_factory=partial(_env_optional_bool, "ENABLE_PORTUGUESE_TRANSLATION", True),
        alias="ENABLE_PORTUGUESE_TRANSLATION",
        description="Enable Portuguese translation when true.",
    )

    rate_limit_enabled: bool = Field(
        default_factory=partial(_env_optional_bool, "RATE_LIMIT_ENABLED", True),
        alias="RATE_LIMIT_ENABLED",
        description="Enable rate limiting when true.",
    )
    rate_limit_redis_url: str = Field(
        default_factory=partial(_env_optional, "RATE_LIMIT_REDIS_URL", "redis://redis:6379/0"),
        alias="RATE_LIMIT_REDIS_URL",
        description="Redis URL used for rate limiting storage.",
    )
    rate_limit_trust_proxy_headers: bool = Field(
        default_factory=partial(_env_optional_bool, "RATE_LIMIT_TRUST_PROXY_HEADERS", False),
        alias="RATE_LIMIT_TRUST_PROXY_HEADERS",
        description="Trust X-Forwarded-For/X-Real-IP headers when determining client IP.",
    )
    rate_limit_default: str = Field(
        default_factory=partial(_env_optional, "RATE_LIMIT_DEFAULT", "120/minute"),
        alias="RATE_LIMIT_DEFAULT",
        description="Default generous rate limit applied globally.",
    )
    rate_limit_post_summaries: str = Field(
        default_factory=partial(_env_optional, "RATE_LIMIT_POST_SUMMARIES", "30/minute"),
        alias="RATE_LIMIT_POST_SUMMARIES",
        description="Generous rate limit for POST /summaries.",
    )
    rate_limit_get_summaries: str = Field(
        default_factory=partial(_env_optional, "RATE_LIMIT_GET_SUMMARIES", "300/minute"),
        alias="RATE_LIMIT_GET_SUMMARIES",
        description="Generous rate limit for GET /summaries.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()
