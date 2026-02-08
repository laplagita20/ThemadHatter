"""Macroeconomic analysis: FRED data, Dalio's economic machine, regime detection.

Phase 7E: Dalio 4-quadrant model, credit spread monitor, financial stress index,
recession probability model.
"""

import logging
import numpy as np
from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.models import MacroDAO, StockDAO

logger = logging.getLogger("stock_model.analysis.macro")

# How sectors perform in different regimes
SECTOR_REGIME_SENSITIVITY = {
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

# Dalio quadrant -> sector recommendations
DALIO_SECTOR_MAP = {
    "goldilocks": ["Technology", "Consumer Discretionary", "Financials", "Industrials"],
    "disinflation_boom": ["Technology", "Consumer Discretionary", "Real Estate", "Utilities"],
    "stagflation": ["Energy", "Materials", "Consumer Staples", "Healthcare"],
    "deflation": ["Utilities", "Consumer Staples", "Healthcare", "Real Estate"],
}


class MacroeconomicAnalyzer(BaseAnalyzer):
    """Analyzes macroeconomic conditions using Dalio's economic machine framework."""

    name = "macroeconomic"

    def __init__(self):
        self.macro_dao = MacroDAO()
        self.stock_dao = StockDAO()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running macroeconomic analysis for %s", ticker)
        factors = []
        score = 0.0

        stock = self.stock_dao.get(ticker)
        sector = stock["sector"] if stock and stock["sector"] else "Unknown"
        regimes = self._detect_regimes()

        if not regimes:
            return self._make_result(0, 0.2, [], "Insufficient macro data for analysis")

        sensitivity = SECTOR_REGIME_SENSITIVITY.get(sector, {})

        # --- Original Regime Analysis ---
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
                explanation = "GDP growth is moderate"
            score += regime_score
            factors.append(AnalysisFactor("Growth Regime", growth, regime_score, explanation))

        # Rate regime
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

        # VIX
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

        # =====================================================================
        # PHASE 7E: DALIO-STYLE ECONOMIC MACHINE
        # =====================================================================

        # --- Dalio 4-Quadrant Detection ---
        dalio = self._detect_dalio_quadrant(regimes)
        if dalio:
            quadrant = dalio["quadrant"]
            favored = DALIO_SECTOR_MAP.get(quadrant, [])
            is_favored = sector in favored or any(s in sector for s in favored)

            if is_favored:
                impact = 10
                explanation = f"Dalio Quadrant: {dalio['label']} - {sector} is FAVORED in this regime"
            else:
                impact = -5
                explanation = f"Dalio Quadrant: {dalio['label']} - {sector} is not favored (prefer: {', '.join(favored[:3])})"

            score += impact
            factors.append(AnalysisFactor("Dalio Quadrant", dalio["label"], impact, explanation))

        # --- Credit Spread Monitor ---
        credit_spread = regimes.get("credit_spread")
        if credit_spread is not None:
            credit_history = regimes.get("credit_spread_trend")
            if credit_spread > 5:
                impact = -15
                explanation = f"High yield spread at {credit_spread:.2f}% - significant credit stress, risk-off"
            elif credit_spread > 4:
                impact = -10
                explanation = f"Elevated high yield spread ({credit_spread:.2f}%) - credit stress building"
            elif credit_history == "widening":
                impact = -8
                explanation = f"High yield spread widening ({credit_spread:.2f}%) - credit conditions deteriorating"
            elif credit_history == "narrowing":
                impact = 8
                explanation = f"High yield spread narrowing ({credit_spread:.2f}%) - risk-on signal"
            else:
                impact = 3
                explanation = f"Credit spreads normal ({credit_spread:.2f}%)"
            score += impact
            factors.append(AnalysisFactor("Credit Spread", f"{credit_spread:.2f}%", impact, explanation))

        # --- Financial Stress Index ---
        fsi = regimes.get("financial_stress_index")
        if fsi is not None:
            if fsi > 2:
                impact = -25
                explanation = f"St. Louis FSI at {fsi:.2f} - CRISIS level financial stress"
            elif fsi > 0:
                impact = -10
                explanation = f"St. Louis FSI at {fsi:.2f} - above-normal financial stress"
            elif fsi > -1:
                impact = 5
                explanation = f"St. Louis FSI at {fsi:.2f} - calm financial conditions"
            else:
                impact = 8
                explanation = f"St. Louis FSI at {fsi:.2f} - very calm financial conditions"
            score += impact
            factors.append(AnalysisFactor("Financial Stress", f"{fsi:.2f}", impact, explanation))

        # --- Recession Probability ---
        recession_prob = self._calculate_recession_probability(regimes)
        if recession_prob is not None:
            if recession_prob > 50:
                impact = -20
                explanation = f"Recession probability {recession_prob:.0f}% - defensive posture recommended"
            elif recession_prob > 30:
                impact = -10
                explanation = f"Recession probability {recession_prob:.0f}% - elevated risk"
            elif recession_prob > 15:
                impact = -3
                explanation = f"Recession probability {recession_prob:.0f}% - moderate"
            else:
                impact = 5
                explanation = f"Recession probability {recession_prob:.0f}% - expansion likely"
            score += impact
            factors.append(AnalysisFactor("Recession Probability", f"{recession_prob:.0f}%", impact, explanation))

        # --- Breakeven Inflation ---
        breakeven = regimes.get("breakeven_inflation")
        if breakeven is not None:
            if breakeven > 3:
                impact = -5
                explanation = f"Breakeven inflation {breakeven:.2f}% - market expects high inflation"
            elif breakeven < 1.5:
                impact = -3
                explanation = f"Breakeven inflation {breakeven:.2f}% - deflation risk"
            else:
                impact = 3
                explanation = f"Breakeven inflation {breakeven:.2f}% - stable expectations"
            score += impact
            factors.append(AnalysisFactor("Inflation Expectations", f"{breakeven:.2f}%", impact, explanation))

        # --- Jobless Claims Trend ---
        jobless = regimes.get("jobless_claims")
        jobless_trend = regimes.get("jobless_claims_trend")
        if jobless is not None:
            if jobless > 300000:
                impact = -8
                explanation = f"Initial claims elevated at {jobless:,.0f} - labor market weakening"
            elif jobless_trend == "rising":
                impact = -5
                explanation = f"Initial claims rising ({jobless:,.0f}) - early warning"
            elif jobless < 200000:
                impact = 5
                explanation = f"Initial claims low ({jobless:,.0f}) - strong labor market"
            else:
                impact = 0
                explanation = f"Initial claims at {jobless:,.0f}"
            score += impact
            factors.append(AnalysisFactor("Jobless Claims", f"{jobless:,.0f}", impact, explanation))

        confidence = min(1.0, len(factors) / 10 * 0.8 + 0.2)
        summary = f"Macro environment is {'favorable' if score > 10 else 'challenging' if score < -10 else 'neutral'} for {sector} stocks"

        if dalio:
            summary += f". Dalio regime: {dalio['label']}"

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
            regimes["gdp_growth_rate"] = growth_rate
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
            regimes["inflation_rate"] = inflation_rate
            if inflation_rate > 4:
                regimes["inflation"] = "high"
            elif inflation_rate < 2:
                regimes["inflation"] = "low"
            else:
                regimes["inflation"] = "moderate"

        # Yield curve
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

        # --- Phase 7E: New FRED series ---

        # High Yield Credit Spread
        hy_spread = self.macro_dao.get_series("BAMLH0A0HYM2", limit=30)
        if hy_spread:
            regimes["credit_spread"] = hy_spread[0]["value"]
            if len(hy_spread) >= 5:
                recent = np.mean([r["value"] for r in hy_spread[:5]])
                older = np.mean([r["value"] for r in hy_spread[5:15]]) if len(hy_spread) >= 15 else recent
                if recent > older + 0.3:
                    regimes["credit_spread_trend"] = "widening"
                elif recent < older - 0.3:
                    regimes["credit_spread_trend"] = "narrowing"
                else:
                    regimes["credit_spread_trend"] = "stable"

        # Breakeven Inflation
        bei = self.macro_dao.get_latest("T10YIE")
        if bei:
            regimes["breakeven_inflation"] = bei["value"]

        # Initial Jobless Claims
        claims = self.macro_dao.get_series("ICSA", limit=8)
        if claims:
            regimes["jobless_claims"] = claims[0]["value"]
            if len(claims) >= 4:
                recent = np.mean([c["value"] for c in claims[:4]])
                older = np.mean([c["value"] for c in claims[4:8]]) if len(claims) >= 8 else recent
                if recent > older * 1.10:
                    regimes["jobless_claims_trend"] = "rising"
                elif recent < older * 0.90:
                    regimes["jobless_claims_trend"] = "falling"
                else:
                    regimes["jobless_claims_trend"] = "stable"

        # Financial Stress Index
        fsi = self.macro_dao.get_latest("STLFSI4")
        if fsi:
            regimes["financial_stress_index"] = fsi["value"]

        # Industrial Production (for recession model)
        indpro = self.macro_dao.get_series("INDPRO", limit=13)
        if len(indpro) >= 13:
            ip_growth = ((indpro[0]["value"] - indpro[12]["value"]) / indpro[12]["value"]) * 100
            regimes["industrial_production_yoy"] = ip_growth

        return regimes

    def _detect_dalio_quadrant(self, regimes: dict) -> dict | None:
        """Detect Dalio's 4-quadrant economic regime.

        Growth Rising + Inflation Rising = Goldilocks
        Growth Rising + Inflation Falling = Disinflation Boom
        Growth Falling + Inflation Rising = Stagflation
        Growth Falling + Inflation Falling = Deflation
        """
        growth = regimes.get("growth")
        inflation = regimes.get("inflation")

        if not growth or not inflation:
            return None

        growth_rising = growth in ("high", "moderate")
        inflation_rising = inflation in ("high",)

        if growth_rising and inflation_rising:
            return {"quadrant": "goldilocks", "label": "Goldilocks (Growth Up, Inflation Up)",
                    "stocks": "up", "bonds": "down", "commodities": "up"}
        elif growth_rising and not inflation_rising:
            return {"quadrant": "disinflation_boom", "label": "Disinflation Boom (Growth Up, Inflation Down)",
                    "stocks": "up", "bonds": "up", "commodities": "neutral"}
        elif not growth_rising and inflation_rising:
            return {"quadrant": "stagflation", "label": "Stagflation (Growth Down, Inflation Up)",
                    "stocks": "down", "bonds": "down", "commodities": "up"}
        else:
            return {"quadrant": "deflation", "label": "Deflation (Growth Down, Inflation Down)",
                    "stocks": "down", "bonds": "up", "commodities": "down"}

    def _calculate_recession_probability(self, regimes: dict) -> float | None:
        """Simple recession probability model combining leading indicators."""
        signals = []

        # Yield curve (most reliable predictor)
        yc = regimes.get("yield_curve")
        if yc is not None:
            if yc < -0.5:
                signals.append(0.8)
            elif yc < 0:
                signals.append(0.5)
            elif yc < 0.5:
                signals.append(0.3)
            else:
                signals.append(0.1)

        # Credit spreads
        cs = regimes.get("credit_spread")
        if cs is not None:
            if cs > 6:
                signals.append(0.8)
            elif cs > 4.5:
                signals.append(0.5)
            elif cs > 3.5:
                signals.append(0.3)
            else:
                signals.append(0.1)

        # Jobless claims
        jc = regimes.get("jobless_claims")
        if jc is not None:
            if jc > 350000:
                signals.append(0.7)
            elif jc > 250000:
                signals.append(0.4)
            else:
                signals.append(0.1)

        # Consumer sentiment
        cs_sent = regimes.get("consumer_sentiment")
        if cs_sent is not None:
            if cs_sent < 55:
                signals.append(0.6)
            elif cs_sent < 65:
                signals.append(0.3)
            else:
                signals.append(0.1)

        # Industrial production
        ip = regimes.get("industrial_production_yoy")
        if ip is not None:
            if ip < -2:
                signals.append(0.7)
            elif ip < 0:
                signals.append(0.4)
            else:
                signals.append(0.1)

        # Financial stress
        fsi = regimes.get("financial_stress_index")
        if fsi is not None:
            if fsi > 2:
                signals.append(0.8)
            elif fsi > 0:
                signals.append(0.4)
            else:
                signals.append(0.1)

        if not signals:
            return None

        # Weighted average with yield curve getting highest weight
        weights = [0.25, 0.20, 0.15, 0.15, 0.15, 0.10][:len(signals)]
        total_weight = sum(weights)
        weighted_prob = sum(s * w for s, w in zip(signals, weights)) / total_weight

        return round(weighted_prob * 100, 1)
