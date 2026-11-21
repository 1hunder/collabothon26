from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://fq:fq@localhost:5432/financequest"
    anthropic_api_key: str = ""
    google_genai_api_key: str = ""
    model_id: str = "claude-opus-5-5"
    guessers_per_attempt: int = 3
    web_search_max_uses: int = 12
    max_attempts: int = 3
    check_concurrency: int = 4
    db_pool_size: int = 5
    db_max_overflow: int = 5
    cache_dir: str = ".cache/prices"
    data_dir: str = "data"
    demo_mode: bool = False
    # Personal quests: in demo mode the daily quest is the pre-created scenario below (or the
    # newest generated one, else the sample pack) instead of a live generation.
    demo_scenario_id: str = ""
    generation_concurrency: int = 2
    art_model: str = "gemini-2.5-flash-image"
    tts_model: str = "gemini-2.5-flash-preview-tts"
    tts_voice_dm: str = "Charon"
    tts_voice_buddy: str = "Puck"
    art_timeout_s: float = 60.0
    art_retries: int = 1
    fake_llm: bool = False
    cors_origins: str = "http://localhost:5173,https://*.vercel.app"
    log_level: str = "INFO"

    # Thresholds (recorded into each check run)
    start_window_months: int = 3
    start_confidence_pct: int = 30
    min_readability: int = 3
    jitter_pct: int = 30
    display_cap: int = 10_000

    @field_validator("database_url")
    @classmethod
    def _normalise(cls, v: str) -> str:
        return normalize_database_url(v)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        """Wildcard origins (e.g. https://*.vercel.app) become a regex."""
        import re

        wild = [o for o in self.cors_origin_list if "*" in o]
        if not wild:
            return None
        return "|".join(re.escape(o).replace(r"\*", "[A-Za-z0-9-]+") for o in wild)

    def thresholds(self) -> dict[str, int]:
        return {
            "start_window_months": self.start_window_months,
            "start_confidence_pct": self.start_confidence_pct,
            "min_readability": self.min_readability,
            "jitter_pct": self.jitter_pct,
            "display_cap": self.display_cap,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
