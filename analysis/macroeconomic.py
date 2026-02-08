"""Macroeconomic analysis: FRED data, regime detection, sector impact."""

import logging
from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.models import MacroDAO, StockDAO

logger = logging.getLogger("stock_model.analysis.macro")

# How sectors perform in different regimes
SECTOR_REGIME_SENSITIVITY = {
    # sector: {regime: impact_multiplier}
    "Technology": {"growth_high": 1.3, "growth_low": 0.7, "rate_rising": 0.6, "rate_falling": 1.4, "inflation_high": 0.8},
    "Information Technology": {"growth_high": 1.3, "growth_low": 0.7, "rate_rising": 0.6, "rate_falling": 1.4, "inflation_high": 0.8},
    "Healthcare": {"growth_high": 0.9, "growth_low": 1.1, "rate_rising": 1.0, "rate_falling": 1.0, "inflation_high": 1.0},
    "Health Care": {"growth_high": 0.9, "growth_low": 1.1, "rate_rising": 1.0, "rate_falling": 1.0, "inflation_high": 1.0},
    "Financials": {"growth_high": 1.2, "growth_low": 0.8, "rate_rising": 1.3, "rate_falling": 0.7, "inflation_high": 1.0},
    "Financial Services": {"growth_high": 1.2, "growth_low": 0.8, "rate_rising": 1.3, "rate_falling": 0.7, "inflation_high": 1.0},
    "Consumer Discretionary": {"growth_high": 1.4, "growth_low": 0.6, "rate_rising": 0.8, "rate_falling": 1.2, "inflation_high": 0.7},
    "Consumer Cyclical": {"growth_high": 1.4, "growth_low": 0.6, "rate_rising": 0.8, "rate_falling": 1.2, "inflation_high": 0.7},
    "Consumer Staples": {"growth_high": 0.7, "growth_low": 1.2, "rate_rising": 1.0, "rate_falling": 1.0, "inflation_high": 1.1},
    "Consumer Defensive": {"growth_high": 0.7, "growth_low": 1.2, "rate_rising": 1.0, "rate_falling": 1.0, "inflation_high": 1.1},
    "Energy": {"growth_high": 1.2, "growth_low": 0.9, "rate_rising": 1.1, "rate_falling": 0.9, "inflation_high": 1.4},
    "Industrials": {"growth_high": 1.3, "growth_low": 0.7, "rate_rising": 0.9, "rate_falling": 1.1, "inflation_high": 0.9},
    "Materials": {"growth_high": 1.2, "growth_low": 0.8, "rate_rising": 0.9, "rate_falling": 1.0, "inflation_high": 1.3},
    "Basic Materials": {"growth_high": 1.2, "growth_low": 0.8, "rate_rising": 0.9, "rate_falling": 1.0, "inflation_high": 1.3},
    "Utilities": {"growth_high": 0.6, "growth_low": 1.3, "rate_rising": 0.7, "rate_falling": 1.3, "inflation_high": 0.9},
    "Real Estate": {"growth_high": 1.0, "growth_low": 0.9, "rate_rising": 0.5, "rate_falling": 1.5, "inflation_high": 0.8},
    "Communication Services": {"growth_high": 1.1, "growth_low": 0.9, "rate_rising": 0.8, "rate_falling": 1.1, "inflation_high": 0.9},
}


class MacroeconomicAnalyzer(BaseAnalyzer):
    """Analyzes macroeconomic conditions and their impact on a stock's sector."""

    name = "macroeconomic"

    def __init__(self):
        self.macro_dao = MacroDAO()
        self.stock_dao = StockDAO()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running macroeconomic analysis for %s", ticker)
        factors = []
        score = 0.0

        # Get stock sector
        stock = self.stock_dao.get(ticker)
        sector = stock["sector"] if stock and stock["sector"] else "Unknown"

        # Detect macro regimes
        regimes = self._detect_regimes()

        if not regimes:
            return self._make_result(0, 0.2, [], "Insufficient macro data for analysis")

        # Score based on each regime and sector sensitivity
        sensitivity = SECTOR_REGIME_SENSITIVITY.get(sector, {})

        # Growth regime
        growth = regimes.get("growth")
        if growth:
            multiplier = sensitivity.get(f"growth_{growth}", 1.0)
            if growth == "high":
                regime_score = 15 * multiplier
                explanation = f"GDP growth is strong - {'favorable' if multiplier > 1 else 'neutral'} for {sector}"
            elif growth == "low":
                regime_score = -15 * multiplier
                explanation = f"GDP growth is weak - {'challenging' if multiplier < 1 else 'defensive'} for {sector}"
            else:
                regime_score = 0
                explanation = f"GDP growth is moderate"
            score += regime_score
            factors.append(AnalysisFactor("Growth Regime", growth, regime_score, explanation))

        # Interest rate regime
        rate = regimes.get("rate")
        if rate:
            multiplier = sensitivity.get(f"rate_{rate}", 1.0)
            if rate == "rising":
                regime_score = -10 * (2 - multiplier)
                explanation = f"Rising rates - {'headwind' if multiplier < 1 else 'tailwind'} for {sector}"
            elif rate == "falling":
                regime_score = 10 * multiplier
                explanation = f"Falling rates - {'tailwind' if multiplier > 1 else 'neutral'} for {sector}"
            else:
                regime_score = 0
                explanation = "Rates are stable"
            score += regime_score
            factors.append(AnalysisFactor("Rate Regime", rate, regime_score, explanation))

        # Inflation regime
        inflation = regimes.get("inflation")
        if inflation:
            multiplier = sensitivity.get("inflation_high", 1.0)
            if inflation == "high":
                regime_score = -10 * (2 - multiplier)
                explanation = f"High inflation - {'pressure' if multiplier < 1 else 'hedge'} for {sector}"
            elif inflation == "low":
                regime_score = 5
                explanation = "Low inflation - generally supportive"
            else:
                regime_score = 0
                explanation = "Inflation is moderate"
            score += regime_score
            factors.append(AnalysisFactor("Inflation Regime", inflation, regime_score, explanation))

        # Yield curve
        yield_curve = regimes.get("yield_curve")
        if yield_curve is not None:
            if yield_curve < 0:
                impact = -20
                explanation = f"Yield curve inverted ({yield_curve:.2f}%) - recession signal"
            elif yield_curve < 0.5:
                impact = -10
                explanation = f"Yield curve flat ({yield_curve:.2f}%) - slowdown risk"
            else:
                impact = 5
                explanation = f"Yield curve normal ({yield_curve:.2f}%) - healthy signal"
            score += impact
            factors.append(AnalysisFactor("Yield Curve", f"{yield_curve:.2f}%", impact, explanation))

        # VIX (fear gauge)
        vix = regimes.get("vix")
        if vix is not None:
            if vix > 30:
                impact = -15
                explanation = f"VIX elevated at {vix:.1f} - high fear/uncertainty"
            elif vix > 20:
                impact = -5
                explanation = f"VIX moderate at {vix:.1f} - some caution"
            else:
                impact = 5
                explanation = f"VIX low at {vix:.1f} - calm markets"
            score += impact
            factors.append(AnalysisFactor("VIX", f"{vix:.1f}", impact, explanation))

        # Unemployment
        unemployment = regimes.get("unemployment")
        if unemployment is not None:
            if unemployment > 6:
                impact = -10
                explanation = f"High unemployment ({unemployment:.1f}%) - weak economy"
            elif unemployment < 4:
                impact = 5
                explanation = f"Low unemployment ({unemployment:.1f}%) - strong labor market"
            else:
                impact = 0
                explanation = f"Unemployment at {unemployment:.1f}%"
            score += impact
            factors.append(AnalysisFactor("Unemployment", f"{unemployment:.1f}%", impact, explanation))

        # Consumer Sentiment
        sentiment = regimes.get("consumer_sentiment")
        if sentiment is not None:
            if sentiment > 80:
                impact = 8
                explanation = f"Consumer confidence high ({sentiment:.0f})"
            elif sentiment < 60:
                impact = -8
                explanation = f"Consumer confidence low ({sentiment:.0f})"
            else:
                impact = 0
                explanation = f"Consumer confidence neutral ({sentiment:.0f})"
            score += impact
            factors.append(AnalysisFactor("Consumer Sentiment", f"{sentiment:.0f}", impact, explanation))

        confidence = min(1.0, len(factors) / 7 * 0.8 + 0.2)
        summary = f"Macro environment is {'favorable' if score > 10 else 'challenging' if score < -10 else 'neutral'} for {sector} stocks"
        return self._make_result(score, confidence, factors, summary)

    def _detect_regimes(self) -> dict:
        """Detect current macro regimes from FRED data."""
        regimes = {}

        # GDP Growth
        gdp = self.macro_dao.get_series("GDP", limit=8)
        if len(gdp) >= 2:
            latest = gdp[0]["value"]
            prev = gdp[1]["value"]
            growth_rate = ((latest - prev) / prev) * 100 if prev else 0
            if growth_rate > 2.5:
                regimes["growth"] = "high"
            elif growth_rate < 0:
                regimes["growth"] = "low"
            else:
                regimes["growth"] = "moderate"

        # Fed Funds Rate direction
        rates = self.macro_dao.get_series("FEDFUNDS", limit=6)
        if len(rates) >= 3:
            recent_avg = sum(r["value"] for r in rates[:3]) / 3
            older_avg = sum(r["value"] for r in rates[3:6]) / max(1, len(rates[3:6]))
            if recent_avg > older_avg + 0.25:
                regimes["rate"] = "rising"
            elif recent_avg < older_avg - 0.25:
                regimes["rate"] = "falling"
            else:
                regimes["rate"] = "stable"

        # Inflation (CPI YoY)
        cpi = self.macro_dao.get_series("CPIAUCSL", limit=13)
        if len(cpi) >= 13:
            current = cpi[0]["value"]
            year_ago = cpi[12]["value"]
            inflation_rate = ((current - year_ago) / year_ago) * 100 if year_ago else 0
            if inflation_rate > 4:
                regimes["inflation"] = "high"
            elif inflation_rate < 2:
                regimes["inflation"] = "low"
            else:
                regimes["inflation"] = "moderate"

        # Yield curve (10Y - 2Y)
        spread = self.macro_dao.get_latest("T10Y2Y")
        if spread:
            regimes["yield_curve"] = spread["value"]

        # VIX
        vix = self.macro_dao.get_latest("VIXCLS")
        if vix:
            regimes["vix"] = vix["value"]

        # Unemployment
        unemp = self.macro_dao.get_latest("UNRATE")
        if unemp:
            regimes["unemployment"] = unemp["value"]

        # Consumer Sentiment
        sent = self.macro_dao.get_latest("UMCSENT")
        if sent:
            regimes["consumer_sentiment"] = sent["value"]

        return regimes
