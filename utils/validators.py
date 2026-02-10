"""Shared input validation utilities.

All data boundaries should validate through these helpers so that invalid data
(NaN, garbage tickers, negative prices) never silently poisons scores.
"""

import math
import re
import logging

logger = logging.getLogger("stock_model.validators")

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def validate_ticker(raw: str) -> str:
    """Normalise and validate a stock ticker symbol.

    Returns the uppercased/stripped ticker or raises ValueError.
    """
    if not isinstance(raw, str):
        raise ValueError(f"Ticker must be a string, got {type(raw).__name__}")
    cleaned = raw.strip().upper()
    if not _TICKER_RE.match(cleaned):
        raise ValueError(
            f"Invalid ticker '{raw}': must be 1-5 uppercase letters"
        )
    return cleaned


def validate_price(value) -> float | None:
    """Validate a price value: finite, non-negative. Returns None for missing."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v < 0:
        return None
    return v


def validate_date(raw: str) -> str:
    """Validate an ISO-format date string (YYYY-MM-DD). Raises ValueError."""
    if not isinstance(raw, str):
        raise ValueError(f"Date must be a string, got {type(raw).__name__}")
    cleaned = raw.strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned):
        raise ValueError(f"Invalid date '{raw}': expected YYYY-MM-DD")
    return cleaned


def validate_amount(value) -> float:
    """Validate a monetary amount: positive, finite. Raises ValueError."""
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Amount must be numeric, got {value!r}") from exc
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"Amount must be positive and finite, got {v}")
    return v


def guard_nan(score, default: float = 0.0) -> float:
    """Clamp NaN / inf to *default*. Safe for None inputs too."""
    if score is None:
        return default
    try:
        v = float(score)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        logger.warning("NaN/inf score clamped to %s", default)
        return default
    return v
