"""Application settings loaded from .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    """Central configuration for the stock model system."""

    # Paths
    project_root: Path = field(default_factory=_project_root)
    db_path: Path = field(default=None)
    log_dir: Path = field(default=None)
    cache_dir: Path = field(default=None)

    # API Keys
    fred_api_key: str = ""
    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""
    sec_edgar_user_agent: str = ""

    # Robinhood
    robinhood_username: str = ""
    robinhood_password: str = ""
    robinhood_totp_secret: str = ""

    # Logging
    log_level: str = "INFO"

    # Analysis weights (default, can be overridden by optimizer)
    analysis_weights: dict = field(default_factory=lambda: {
        "technical": 0.18,
        "fundamental": 0.28,
        "macroeconomic": 0.15,
        "sentiment": 0.10,
        "geopolitical": 0.03,
        "sector": 0.10,
        "insider": 0.05,
        "institutional": 0.02,
        "risk": 0.09,
    })

    # Risk management defaults
    max_single_position_pct: float = 10.0
    max_single_sector_pct: float = 30.0
    min_sectors_held: int = 3
    trailing_stop_core_pct: float = 15.0
    trailing_stop_tactical_pct: float = 8.0
    hard_stop_pct: float = 25.0
    position_size_high_conviction: float = 8.0
    position_size_medium_conviction: float = 5.0
    position_size_low_conviction: float = 2.0

    def __post_init__(self):
        if self.db_path is None:
            self.db_path = self.project_root / "data" / "stock_model.db"
        if self.log_dir is None:
            self.log_dir = self.project_root / "data" / "logs"
        if self.cache_dir is None:
            self.cache_dir = self.project_root / "data" / "cache"

        # Ensure directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def _get_secret(key: str, default: str = "") -> str:
    """Read a secret from Streamlit Cloud secrets or environment variable."""
    # Streamlit Cloud injects secrets as st.secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


def get_settings() -> Settings:
    """Load settings from Streamlit secrets, .env, or environment."""
    global _settings
    if _settings is not None:
        return _settings

    root = _project_root()
    env_path = root / ".env"
    load_dotenv(env_path)

    _settings = Settings(
        fred_api_key=_get_secret("FRED_API_KEY"),
        finnhub_api_key=_get_secret("FINNHUB_API_KEY"),
        alpha_vantage_api_key=_get_secret("ALPHA_VANTAGE_API_KEY"),
        sec_edgar_user_agent=_get_secret("SEC_EDGAR_USER_AGENT"),
        robinhood_username=_get_secret("ROBINHOOD_USERNAME"),
        robinhood_password=_get_secret("ROBINHOOD_PASSWORD"),
        robinhood_totp_secret=_get_secret("ROBINHOOD_TOTP_SECRET"),
        log_level=_get_secret("LOG_LEVEL", "INFO"),
        db_path=Path(os.getenv("DB_PATH", root / "data" / "stock_model.db")),
        log_dir=Path(os.getenv("LOG_DIR", root / "data" / "logs")),
        cache_dir=Path(os.getenv("CACHE_DIR", root / "data" / "cache")),
    )
    return _settings
