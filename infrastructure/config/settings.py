"""Centralized configuration.

One Settings object, sourced from environment variables (and .env in
development), instead of constants scattered across run_live.py and
server/main.py. ENVIRONMENT selects the profile; a future cloud deployment
just sets ENVIRONMENT=production plus real env vars — no code changes.
"""

from enum import Enum
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT

    initial_capital: float = 100_000

    zerodha_config_file: str = "Data_ingestion/config.yaml"
    zerodha_stocks_file: str = "Data_ingestion/stocks.json"

    api_host: str = "127.0.0.1"
    api_port: int = 5000

    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Shown as a live ticker on the dashboard — a quick "is the app
    # actually receiving data" signal. Read from raw ticks, not the
    # indicator pipeline (indices report zero volume, so LiveEngine never
    # produces a snapshot for them).
    market_ticker_symbols: List[str] = ["NIFTY 50", "NIFTY BANK"]

    database_url: str = "sqlite:///./quantpulse.db"

    log_level: str = "INFO"

    # 24h "HH:MM" — when the background scheduler writes the end-of-day
    # trades/metrics report (backend/eod_report.py). Only fires while the
    # backend process is running at that time.
    eod_report_time: str = "15:35"
    eod_report_dir: str = "reports"

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Process-wide Settings singleton (cheap to call repeatedly)."""
    return Settings()
