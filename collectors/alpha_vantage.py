"""Alpha Vantage collector: earnings calendar, earnings surprises, overview data."""

import logging
import requests
from datetime import datetime

from collectors.base_collector import BaseCollector
from database.connection import get_connection

logger = logging.getLogger("stock_model.collectors.alpha_vantage")

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageCollector(BaseCollector):
    """Collects earnings data and company overview from Alpha Vantage."""

    name = "alpha_vantage"
    rate_limit = 1.0  # free tier: 25 requests/day, 1 per second
    rate_period = 2.0  # one request per 2 seconds minimum

    def __init__(self):
        super().__init__()
        self.api_key = self.settings.alpha_vantage_api_key
        if not self.api_key:
            logger.warning("No Alpha Vantage API key configured")
        self.db = get_connection()

    def _get(self, params: dict) -> dict | None:
        """Rate-limited GET request to Alpha Vantage."""
        params["apikey"] = self.api_key

        def do_request():
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            # Alpha Vantage returns error messages in JSON
            if "Error Message" in data:
                logger.error("Alpha Vantage error: %s", data["Error Message"])
                return None
            if "Note" in data:
                logger.warning("Alpha Vantage rate limit: %s", data["Note"])
                return None
            if "Information" in data:
                logger.warning("Alpha Vantage info: %s", data["Information"])
                return None
            return data

        return self._rate_limited_call(do_request)

    def collect(self, ticker: str = None) -> dict:
        if not ticker:
            return {}
        if not self.api_key:
            logger.warning("Skipping Alpha Vantage - no API key")
            return {}

        logger.info("Collecting Alpha Vantage data for %s", ticker)
        result = {"ticker": ticker}

        # Company Overview (fundamentals not covered by Yahoo)
        overview = self._cached_call(
            f"overview_{ticker}",
            lambda: self._get({
                "function": "OVERVIEW",
                "symbol": ticker,
            }),
            ttl=86400,
        )
        if overview:
            result["overview"] = self._parse_overview(overview, ticker)

        # Earnings (quarterly EPS actual vs estimate)
        earnings = self._cached_call(
            f"earnings_{ticker}",
            lambda: self._get({
                "function": "EARNINGS",
                "symbol": ticker,
            }),
            ttl=86400,
        )
        if earnings:
            result["earnings"] = self._parse_earnings(earnings, ticker)

        return result

    def _parse_overview(self, data: dict, ticker: str) -> dict:
        """Parse company overview into key metrics."""
        return {
            "ticker": ticker,
            "name": data.get("Name", ""),
            "sector": data.get("Sector", ""),
            "industry": data.get("Industry", ""),
            "market_cap": _safe_float(data.get("MarketCapitalization")),
            "pe_ratio": _safe_float(data.get("PERatio")),
            "forward_pe": _safe_float(data.get("ForwardPE")),
            "peg_ratio": _safe_float(data.get("PEGRatio")),
            "book_value": _safe_float(data.get("BookValue")),
            "dividend_yield": _safe_float(data.get("DividendYield")),
            "eps": _safe_float(data.get("EPS")),
            "revenue_per_share": _safe_float(data.get("RevenuePerShareTTM")),
            "profit_margin": _safe_float(data.get("ProfitMargin")),
            "operating_margin": _safe_float(data.get("OperatingMarginTTM")),
            "roe": _safe_float(data.get("ReturnOnEquityTTM")),
            "roa": _safe_float(data.get("ReturnOnAssetsTTM")),
            "revenue_growth_yoy": _safe_float(data.get("QuarterlyRevenueGrowthYOY")),
            "earnings_growth_yoy": _safe_float(data.get("QuarterlyEarningsGrowthYOY")),
            "beta": _safe_float(data.get("Beta")),
            "52_week_high": _safe_float(data.get("52WeekHigh")),
            "52_week_low": _safe_float(data.get("52WeekLow")),
            "50_day_ma": _safe_float(data.get("50DayMovingAverage")),
            "200_day_ma": _safe_float(data.get("200DayMovingAverage")),
            "analyst_target": _safe_float(data.get("AnalystTargetPrice")),
            "analyst_rating": data.get("AnalystRatingStrongBuy", ""),
        }

    def _parse_earnings(self, data: dict, ticker: str) -> list[dict]:
        """Parse quarterly earnings data."""
        rows = []
        quarterly = data.get("quarterlyEarnings", [])

        for entry in quarterly[:12]:  # last 12 quarters (3 years)
            reported_eps = _safe_float(entry.get("reportedEPS"))
            estimated_eps = _safe_float(entry.get("estimatedEPS"))
            surprise = _safe_float(entry.get("surprise"))
            surprise_pct = _safe_float(entry.get("surprisePercentage"))

            rows.append({
                "ticker": ticker,
                "fiscal_date": entry.get("fiscalDateEnding", ""),
                "reported_date": entry.get("reportedDate", ""),
                "reported_eps": reported_eps,
                "estimated_eps": estimated_eps,
                "surprise": surprise,
                "surprise_pct": surprise_pct,
            })

        return rows

    def store(self, data: dict):
        ticker = data.get("ticker")

        # Store overview data as supplementary fundamentals
        overview = data.get("overview")
        if overview:
            analyst_target = overview.get("analyst_target")
            if analyst_target:
                try:
                    self.db.execute_insert(
                        """INSERT OR REPLACE INTO alpha_vantage_overview
                           (ticker, analyst_target, beta, revenue_growth_yoy,
                            earnings_growth_yoy, profit_margin, operating_margin,
                            roe, roa, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (ticker, analyst_target, overview.get("beta"),
                         overview.get("revenue_growth_yoy"),
                         overview.get("earnings_growth_yoy"),
                         overview.get("profit_margin"),
                         overview.get("operating_margin"),
                         overview.get("roe"), overview.get("roa")),
                    )
                except Exception as e:
                    logger.debug("Overview insert skipped: %s", e)
            logger.info("Stored overview for %s", ticker)

        # Store earnings
        earnings = data.get("earnings", [])
        for row in earnings:
            try:
                self.db.execute_insert(
                    """INSERT OR REPLACE INTO earnings_history
                       (ticker, fiscal_date, reported_date, reported_eps,
                        estimated_eps, surprise, surprise_pct)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (row["ticker"], row["fiscal_date"], row["reported_date"],
                     row["reported_eps"], row["estimated_eps"],
                     row["surprise"], row["surprise_pct"]),
                )
            except Exception as e:
                logger.debug("Earnings insert skipped: %s", e)

        if earnings:
            logger.info("Stored %d earnings records for %s", len(earnings), ticker)


def _safe_float(val) -> float | None:
    """Safely convert a value to float, returning None for invalid values."""
    if val is None or val == "None" or val == "-":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
