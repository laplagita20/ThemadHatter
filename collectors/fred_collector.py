"""FRED collector: Federal Reserve Economic Data - macro indicators."""

import logging
import math
from datetime import datetime, timedelta

from collectors.base_collector import BaseCollector
from database.models import MacroDAO

logger = logging.getLogger("stock_model.collectors.fred")

# Key FRED series for macro analysis
FRED_SERIES = {
    "GDP": ("Gross Domestic Product", "quarterly"),
    "CPIAUCSL": ("Consumer Price Index", "monthly"),
    "FEDFUNDS": ("Federal Funds Rate", "monthly"),
    "DGS10": ("10-Year Treasury Yield", "daily"),
    "DGS2": ("2-Year Treasury Yield", "daily"),
    "T10Y2Y": ("10Y-2Y Treasury Spread", "daily"),
    "UNRATE": ("Unemployment Rate", "monthly"),
    "VIXCLS": ("CBOE Volatility Index (VIX)", "daily"),
    "M2SL": ("M2 Money Supply", "monthly"),
    "UMCSENT": ("Consumer Sentiment", "monthly"),
    "HOUST": ("Housing Starts", "monthly"),
    "RSXFS": ("Retail Sales ex Food Services", "monthly"),
    "INDPRO": ("Industrial Production Index", "monthly"),
    "DCOILWTICO": ("Crude Oil Price (WTI)", "daily"),
    "DEXUSEU": ("USD/EUR Exchange Rate", "daily"),
    # Phase 7E: New macro series for Dalio-style analysis
    "BAMLH0A0HYM2": ("ICE BofA High Yield Spread", "daily"),
    "T10YIE": ("10-Year Breakeven Inflation Rate", "daily"),
    "ICSA": ("Initial Jobless Claims", "weekly"),
    "PERMIT": ("Building Permits", "monthly"),
    "ACDGNO": ("New Orders Durable Goods", "monthly"),
    "STLFSI4": ("St. Louis Fed Financial Stress Index", "weekly"),
    "DTWEXBGS": ("Trade Weighted US Dollar Index", "daily"),
}


class FREDCollector(BaseCollector):
    """Collects macroeconomic data from Federal Reserve FRED API."""

    name = "fred"
    rate_limit = 2.0  # 120/min but be conservative
    rate_period = 1.0

    def __init__(self):
        super().__init__()
        self.macro_dao = MacroDAO()
        self._api = None

    def _get_api(self):
        """Lazy-init FRED API client."""
        if self._api is None:
            api_key = self.settings.fred_api_key
            if not api_key:
                raise ValueError("FRED_API_KEY not set in .env")
            from fredapi import Fred
            self._api = Fred(api_key=api_key)
        return self._api

    def collect(self, ticker: str = None) -> dict:
        """Collect all FRED series. Ticker parameter is ignored."""
        logger.info("Collecting FRED macroeconomic data")
        results = {}

        fred = self._get_api()
        start = datetime.now() - timedelta(days=365 * 3)

        for series_id, (name, freq) in FRED_SERIES.items():
            ttl = 3600 if freq == "daily" else 86400  # 1hr daily, 24hr monthly
            try:
                data = self._cached_call(
                    f"fred_{series_id}",
                    lambda sid=series_id: fred.get_series(
                        sid, observation_start=start.strftime("%Y-%m-%d")
                    ),
                    ttl=ttl,
                )
                if data is not None:
                    # Convert pandas Series to dict
                    records = []
                    for date, value in data.items():
                        if value is not None and str(value) != "." and str(value) != "nan":
                            try:
                                fval = float(value)
                                if not math.isfinite(fval):
                                    continue
                                records.append({
                                    "date": date.strftime("%Y-%m-%d"),
                                    "value": fval,
                                })
                            except (ValueError, TypeError):
                                continue
                    results[series_id] = {
                        "name": name,
                        "frequency": freq,
                        "records": records,
                    }
            except Exception as e:
                logger.warning("Failed to fetch FRED series %s: %s", series_id, e)

        return results

    def store(self, data: dict):
        count = 0
        for series_id, series_data in data.items():
            name = series_data["name"]
            for record in series_data["records"]:
                self.macro_dao.upsert(
                    series_id=series_id,
                    series_name=name,
                    date=record["date"],
                    value=record["value"],
                )
                count += 1
        logger.info("Stored %d FRED data points across %d series", count, len(data))
