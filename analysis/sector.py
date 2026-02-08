"""Sector analysis: rotation, relative strength, peer ranking, business cycle."""

import logging
import yfinance as yf
import numpy as np
import pandas as pd

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.models import StockDAO
from database.connection import get_connection
from utils.helpers import SECTOR_ETFS, ALL_SECTOR_ETFS, get_sector_etf

logger = logging.getLogger("stock_model.analysis.sector")

# Business cycle phases and which sectors outperform
BUSINESS_CYCLE = {
    "early_expansion": {
        "description": "Economy recovering, rates low, earnings improving",
        "favored": ["Technology", "Consumer Discretionary", "Industrials", "Financials"],
        "unfavored": ["Utilities", "Consumer Staples", "Healthcare"],
    },
    "mid_expansion": {
        "description": "Strong growth, rising rates, broad earnings growth",
        "favored": ["Technology", "Industrials", "Materials", "Energy"],
        "unfavored": ["Utilities", "Real Estate"],
    },
    "late_expansion": {
        "description": "Peak growth, high rates, inflation rising",
        "favored": ["Energy", "Materials", "Consumer Staples"],
        "unfavored": ["Technology", "Consumer Discretionary", "Real Estate"],
    },
    "contraction": {
        "description": "Slowing growth, falling rates, defensive positioning",
        "favored": ["Utilities", "Healthcare", "Consumer Staples"],
        "unfavored": ["Financials", "Industrials", "Materials", "Consumer Discretionary"],
    },
}


class SectorAnalyzer(BaseAnalyzer):
    """Analyzes sector rotation, relative strength, and peer positioning."""

    name = "sector"

    def __init__(self):
        self.stock_dao = StockDAO()
        self.db = get_connection()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running sector analysis for %s", ticker)
        factors = []
        score = 0.0

        stock = self.stock_dao.get(ticker)
        sector = stock["sector"] if stock and stock["sector"] else None

        if not sector:
            # Try to get sector from yfinance
            try:
                info = yf.Ticker(ticker).info
                sector = info.get("sector", "Unknown")
                if sector and sector != "Unknown":
                    self.stock_dao.upsert(ticker=ticker, sector=sector)
            except Exception:
                sector = "Unknown"

        if sector == "Unknown":
            return self._make_result(0, 0.15, [], "Cannot determine sector for this stock")

        sector_etf = get_sector_etf(sector)

        # 1. Sector momentum / relative strength
        sector_rs = self._analyze_sector_strength(sector_etf)
        if sector_rs:
            rs_score = sector_rs["relative_strength"]
            if rs_score > 1.1:
                impact = 15
                explanation = f"{sector} sector outperforming SPY (RS: {rs_score:.2f})"
            elif rs_score > 1.0:
                impact = 5
                explanation = f"{sector} sector slightly outperforming (RS: {rs_score:.2f})"
            elif rs_score < 0.9:
                impact = -15
                explanation = f"{sector} sector underperforming SPY (RS: {rs_score:.2f})"
            elif rs_score < 1.0:
                impact = -5
                explanation = f"{sector} sector slightly underperforming (RS: {rs_score:.2f})"
            else:
                impact = 0
                explanation = f"{sector} sector in line with market (RS: {rs_score:.2f})"
            score += impact
            factors.append(AnalysisFactor(
                "Sector Relative Strength", f"{rs_score:.2f}", impact, explanation))

            # Sector returns
            for period, ret in sector_rs.get("returns", {}).items():
                factors.append(AnalysisFactor(
                    f"Sector Return ({period})", f"{ret:+.1f}%", 0,
                    f"{sector} ETF ({sector_etf}) {period} return: {ret:+.1f}%"))

        # 2. Sector rotation ranking
        rotation = self._get_sector_rotation_ranking()
        if rotation and sector_etf:
            rank = next((i+1 for i, (etf, _) in enumerate(rotation) if etf == sector_etf), None)
            total = len(rotation)
            if rank:
                if rank <= 3:
                    impact = 12
                    explanation = f"{sector} ranked #{rank}/{total} in sector rotation (top quartile)"
                elif rank <= total // 2:
                    impact = 5
                    explanation = f"{sector} ranked #{rank}/{total} in sector rotation (above median)"
                elif rank > total - 3:
                    impact = -12
                    explanation = f"{sector} ranked #{rank}/{total} in sector rotation (bottom quartile)"
                else:
                    impact = -5
                    explanation = f"{sector} ranked #{rank}/{total} in sector rotation (below median)"
                score += impact
                factors.append(AnalysisFactor(
                    "Sector Rotation Rank", f"#{rank}/{total}", impact, explanation))

        # 3. Stock vs sector performance
        stock_vs_sector = self._stock_vs_sector(ticker, sector_etf)
        if stock_vs_sector is not None:
            if stock_vs_sector > 10:
                impact = 15
                explanation = f"{ticker} outperforming {sector} sector by {stock_vs_sector:+.1f}% (3M)"
            elif stock_vs_sector > 0:
                impact = 5
                explanation = f"{ticker} slightly outperforming sector ({stock_vs_sector:+.1f}% 3M)"
            elif stock_vs_sector < -10:
                impact = -15
                explanation = f"{ticker} underperforming sector by {stock_vs_sector:.1f}% (3M)"
            else:
                impact = -5
                explanation = f"{ticker} slightly underperforming sector ({stock_vs_sector:+.1f}% 3M)"
            score += impact
            factors.append(AnalysisFactor(
                "Stock vs Sector", f"{stock_vs_sector:+.1f}%", impact, explanation))

        # 4. Business cycle alignment
        cycle_phase = self._estimate_business_cycle()
        if cycle_phase:
            phase_info = BUSINESS_CYCLE[cycle_phase]
            # Check various sector name formats
            sector_names_to_check = [sector]
            # Add alternate names
            alt_map = {
                "Information Technology": "Technology",
                "Technology": "Information Technology",
                "Financial Services": "Financials",
                "Financials": "Financial Services",
                "Consumer Cyclical": "Consumer Discretionary",
                "Consumer Discretionary": "Consumer Cyclical",
                "Consumer Defensive": "Consumer Staples",
                "Consumer Staples": "Consumer Defensive",
                "Health Care": "Healthcare",
                "Healthcare": "Health Care",
                "Basic Materials": "Materials",
                "Materials": "Basic Materials",
            }
            if sector in alt_map:
                sector_names_to_check.append(alt_map[sector])

            is_favored = any(s in phase_info["favored"] for s in sector_names_to_check)
            is_unfavored = any(s in phase_info["unfavored"] for s in sector_names_to_check)

            if is_favored:
                impact = 10
                explanation = f"{sector} favored in {cycle_phase.replace('_', ' ')} phase: {phase_info['description']}"
            elif is_unfavored:
                impact = -10
                explanation = f"{sector} unfavored in {cycle_phase.replace('_', ' ')} phase: {phase_info['description']}"
            else:
                impact = 0
                explanation = f"{sector} neutral in {cycle_phase.replace('_', ' ')} phase"
            score += impact
            factors.append(AnalysisFactor(
                "Business Cycle", cycle_phase.replace("_", " ").title(),
                impact, explanation))

        confidence = min(0.8, 0.3 + len(factors) / 6 * 0.4)
        summary = f"Sector analysis for {ticker} in {sector}: {'favorable' if score > 10 else 'unfavorable' if score < -10 else 'neutral'} positioning"
        return self._make_result(score, confidence, factors, summary)

    def _analyze_sector_strength(self, sector_etf: str) -> dict | None:
        """Calculate sector ETF relative strength vs SPY."""
        if not sector_etf:
            return None
        try:
            sector_data = yf.Ticker(sector_etf).history(period="6mo")
            spy_data = yf.Ticker("SPY").history(period="6mo")

            if sector_data.empty or spy_data.empty:
                return None

            # Calculate returns for different periods
            returns = {}
            for label, days in [("1W", 5), ("1M", 21), ("3M", 63)]:
                if len(sector_data) > days and len(spy_data) > days:
                    s_ret = (sector_data["Close"].iloc[-1] / sector_data["Close"].iloc[-days] - 1) * 100
                    returns[label] = round(s_ret, 2)

            # Relative strength: sector return / SPY return over 3 months
            if len(sector_data) > 63 and len(spy_data) > 63:
                s_3m = sector_data["Close"].iloc[-1] / sector_data["Close"].iloc[-63]
                spy_3m = spy_data["Close"].iloc[-1] / spy_data["Close"].iloc[-63]
                rs = s_3m / spy_3m if spy_3m != 0 else 1.0
            else:
                rs = 1.0

            return {"relative_strength": round(rs, 3), "returns": returns}
        except Exception as e:
            logger.warning("Sector strength analysis failed: %s", e)
            return None

    def _get_sector_rotation_ranking(self) -> list[tuple[str, float]] | None:
        """Rank all sectors by 3-month momentum."""
        try:
            rankings = []
            for etf in ALL_SECTOR_ETFS:
                data = yf.Ticker(etf).history(period="3mo")
                if len(data) > 10:
                    ret = (data["Close"].iloc[-1] / data["Close"].iloc[0] - 1) * 100
                    rankings.append((etf, ret))
            rankings.sort(key=lambda x: x[1], reverse=True)
            return rankings
        except Exception as e:
            logger.warning("Sector rotation ranking failed: %s", e)
            return None

    def _stock_vs_sector(self, ticker: str, sector_etf: str) -> float | None:
        """Calculate stock's outperformance vs its sector over 3 months."""
        if not sector_etf:
            return None
        try:
            stock_data = yf.Ticker(ticker).history(period="3mo")
            sector_data = yf.Ticker(sector_etf).history(period="3mo")

            if stock_data.empty or sector_data.empty or len(stock_data) < 10:
                return None

            stock_ret = (stock_data["Close"].iloc[-1] / stock_data["Close"].iloc[0] - 1) * 100
            sector_ret = (sector_data["Close"].iloc[-1] / sector_data["Close"].iloc[0] - 1) * 100
            return round(stock_ret - sector_ret, 2)
        except Exception as e:
            logger.warning("Stock vs sector comparison failed: %s", e)
            return None

    def _estimate_business_cycle(self) -> str | None:
        """Estimate current business cycle phase from macro data."""
        try:
            # Check macro_indicators table
            gdp_rows = self.db.execute(
                "SELECT value FROM macro_indicators WHERE series_id='GDP' ORDER BY date DESC LIMIT 4"
            )
            rate_rows = self.db.execute(
                "SELECT value FROM macro_indicators WHERE series_id='FEDFUNDS' ORDER BY date DESC LIMIT 6"
            )
            unemp_rows = self.db.execute(
                "SELECT value FROM macro_indicators WHERE series_id='UNRATE' ORDER BY date DESC LIMIT 2"
            )

            if not gdp_rows or not rate_rows:
                return None

            # GDP trend
            if len(gdp_rows) >= 2:
                gdp_growing = gdp_rows[0]["value"] > gdp_rows[1]["value"]
            else:
                gdp_growing = True

            # Rate trend
            if len(rate_rows) >= 4:
                recent_rate = sum(r["value"] for r in rate_rows[:2]) / 2
                older_rate = sum(r["value"] for r in rate_rows[2:4]) / 2
                rates_rising = recent_rate > older_rate + 0.1
                rates_falling = recent_rate < older_rate - 0.1
            else:
                rates_rising = False
                rates_falling = False

            # Unemployment trend
            unemp_low = unemp_rows[0]["value"] < 5 if unemp_rows else True

            if gdp_growing and rates_falling and not unemp_low:
                return "early_expansion"
            elif gdp_growing and not rates_rising and unemp_low:
                return "mid_expansion"
            elif gdp_growing and rates_rising:
                return "late_expansion"
            elif not gdp_growing:
                return "contraction"
            return "mid_expansion"
        except Exception as e:
            logger.debug("Business cycle estimation failed: %s", e)
            return None
