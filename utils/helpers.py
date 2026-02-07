"""Utility helpers: CIK lookup, date utils, formatting."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("stock_model.helpers")

# GICS sector ETF mappings
SECTOR_ETFS = {
    "Technology": "XLK",
    "Information Technology": "XLK",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Financial Services": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Cyclical": "XLY",
    "Consumer Staples": "XLP",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Communication": "XLC",
}

ALL_SECTOR_ETFS = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC"]


def format_currency(value: float | None, prefix: str = "$") -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 1e12:
        return f"{prefix}{value / 1e12:.2f}T"
    if abs(value) >= 1e9:
        return f"{prefix}{value / 1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"{prefix}{value / 1e6:.2f}M"
    return f"{prefix}{value:,.2f}"


def format_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def format_ratio(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def trading_days_ago(days: int) -> datetime:
    """Return datetime approximately N trading days ago."""
    # Rough approximation: 252 trading days per year
    calendar_days = int(days * 365 / 252)
    return datetime.now() - timedelta(days=calendar_days)


def is_market_hours() -> bool:
    """Check if US market is currently open (rough check, no holiday awareness)."""
    now = datetime.now()
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    # Market hours: 9:30 AM - 4:00 PM ET (approximate, not timezone-aware)
    market_open = now.replace(hour=9, minute=30, second=0)
    market_close = now.replace(hour=16, minute=0, second=0)
    return market_open <= now <= market_close


def get_sector_etf(sector: str) -> str | None:
    """Map a sector name to its SPDR ETF ticker."""
    return SECTOR_ETFS.get(sector)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))


def score_to_signal(score: float) -> str:
    """Convert a numeric score (-100 to +100) to a signal string."""
    if score >= 60:
        return "strong_buy"
    elif score >= 20:
        return "buy"
    elif score <= -60:
        return "strong_sell"
    elif score <= -20:
        return "sell"
    return "hold"
