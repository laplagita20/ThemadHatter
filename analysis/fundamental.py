"""Fundamental analysis: valuation, profitability, growth, balance sheet, cash flow."""

import logging
import yfinance as yf

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor

logger = logging.getLogger("stock_model.analysis.fundamental")


class FundamentalAnalyzer(BaseAnalyzer):
    """Fundamental analysis using yfinance data and SEC EDGAR XBRL when available."""

    name = "fundamental"

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running fundamental analysis for %s", ticker)
        factors = []
        score = 0.0
        confidence_count = 0
        data_points = 0

        # Get fundamentals from data dict or fetch directly
        info = (data or {}).get("info")
        if info is None:
            stock = yf.Ticker(ticker)
            info = stock.info

        if not info:
            return self._make_result(0, 0.1, [], "No fundamental data available")

        sector = info.get("sector", "Unknown")

        # --- VALUATION ---
        # P/E Ratio
        pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        if pe is not None:
            data_points += 1
            if pe < 0:
                impact = -15
                explanation = f"Negative P/E ({pe:.1f}) indicates losses"
            elif pe < 12:
                impact = 20
                explanation = f"Low P/E ratio ({pe:.1f}) suggests undervaluation"
            elif pe < 20:
                impact = 10
                explanation = f"Moderate P/E ratio ({pe:.1f}) - fairly valued"
            elif pe < 35:
                impact = -5
                explanation = f"High P/E ratio ({pe:.1f}) - growth priced in"
            else:
                impact = -15
                explanation = f"Very high P/E ratio ({pe:.1f}) - potentially overvalued"
            score += impact
            factors.append(AnalysisFactor("P/E Ratio", f"{pe:.1f}", impact, explanation))
            confidence_count += 1

        # Forward P/E (if available, compare to trailing)
        if forward_pe is not None and pe is not None and pe > 0 and forward_pe > 0:
            data_points += 1
            pe_improvement = ((pe - forward_pe) / pe) * 100
            if pe_improvement > 15:
                impact = 8
                explanation = f"Forward P/E ({forward_pe:.1f}) much lower than trailing ({pe:.1f}) - earnings growth expected"
            elif pe_improvement > 0:
                impact = 3
                explanation = f"Forward P/E ({forward_pe:.1f}) lower than trailing ({pe:.1f}) - modest growth"
            else:
                impact = -5
                explanation = f"Forward P/E ({forward_pe:.1f}) higher than trailing ({pe:.1f}) - earnings decline expected"
            score += impact
            factors.append(AnalysisFactor("Forward P/E", f"{forward_pe:.1f}", impact, explanation))

        # P/B Ratio
        pb = info.get("priceToBook")
        if pb is not None:
            data_points += 1
            if pb < 1:
                impact = 12
                explanation = f"P/B below 1 ({pb:.2f}) - trading below book value"
            elif pb < 3:
                impact = 5
                explanation = f"Reasonable P/B ratio ({pb:.2f})"
            elif pb > 10:
                impact = -8
                explanation = f"Very high P/B ratio ({pb:.2f})"
            else:
                impact = 0
                explanation = f"P/B ratio: {pb:.2f}"
            score += impact
            factors.append(AnalysisFactor("P/B Ratio", f"{pb:.2f}", impact, explanation))

        # P/S Ratio
        ps = info.get("priceToSalesTrailing12Months")
        if ps is not None:
            data_points += 1
            if ps < 1:
                impact = 10
                explanation = f"Low P/S ({ps:.2f}) - revenue not reflected in price"
            elif ps < 5:
                impact = 3
                explanation = f"Moderate P/S ratio ({ps:.2f})"
            elif ps > 15:
                impact = -10
                explanation = f"Very high P/S ({ps:.2f}) - priced for extreme growth"
            else:
                impact = -3
                explanation = f"Elevated P/S ratio ({ps:.2f})"
            score += impact
            factors.append(AnalysisFactor("P/S Ratio", f"{ps:.2f}", impact, explanation))

        # PEG Ratio
        peg = info.get("pegRatio")
        if peg is not None and peg > 0:
            data_points += 1
            if peg < 1:
                impact = 12
                explanation = f"PEG below 1 ({peg:.2f}) - growth at reasonable price"
            elif peg < 1.5:
                impact = 5
                explanation = f"Fair PEG ratio ({peg:.2f})"
            elif peg > 2.5:
                impact = -10
                explanation = f"High PEG ({peg:.2f}) - overpaying for growth"
            else:
                impact = -2
                explanation = f"PEG ratio: {peg:.2f}"
            score += impact
            factors.append(AnalysisFactor("PEG Ratio", f"{peg:.2f}", impact, explanation))

        # EV/EBITDA
        ev_ebitda = info.get("enterpriseToEbitda")
        if ev_ebitda is not None and ev_ebitda > 0:
            data_points += 1
            if ev_ebitda < 8:
                impact = 10
                explanation = f"Low EV/EBITDA ({ev_ebitda:.1f}) - potentially undervalued"
            elif ev_ebitda < 15:
                impact = 3
                explanation = f"Fair EV/EBITDA ({ev_ebitda:.1f})"
            elif ev_ebitda > 25:
                impact = -8
                explanation = f"High EV/EBITDA ({ev_ebitda:.1f})"
            else:
                impact = -2
                explanation = f"EV/EBITDA: {ev_ebitda:.1f}"
            score += impact
            factors.append(AnalysisFactor("EV/EBITDA", f"{ev_ebitda:.1f}", impact, explanation))

        # --- PROFITABILITY ---
        # Profit Margin
        margin = info.get("profitMargins")
        if margin is not None:
            data_points += 1
            margin_pct = margin * 100
            if margin > 0.25:
                impact = 15
                explanation = f"Excellent profit margin ({margin_pct:.1f}%)"
            elif margin > 0.10:
                impact = 8
                explanation = f"Good profit margin ({margin_pct:.1f}%)"
            elif margin > 0:
                impact = 2
                explanation = f"Thin profit margin ({margin_pct:.1f}%)"
            else:
                impact = -20
                explanation = f"Negative profit margin ({margin_pct:.1f}%) - company is losing money"
            score += impact
            factors.append(AnalysisFactor("Profit Margin", f"{margin_pct:.1f}%", impact, explanation))
            confidence_count += 1

        # Operating Margin
        op_margin = info.get("operatingMargins")
        if op_margin is not None:
            data_points += 1
            op_pct = op_margin * 100
            if op_margin > 0.25:
                impact = 8
            elif op_margin > 0.10:
                impact = 4
            elif op_margin > 0:
                impact = 0
            else:
                impact = -10
            score += impact
            factors.append(AnalysisFactor(
                "Operating Margin", f"{op_pct:.1f}%", impact,
                f"Operating margin: {op_pct:.1f}%"))

        # ROE
        roe = info.get("returnOnEquity")
        if roe is not None:
            data_points += 1
            roe_pct = roe * 100
            if roe > 0.20:
                impact = 10
                explanation = f"Strong ROE ({roe_pct:.1f}%) - efficient use of equity"
            elif roe > 0.10:
                impact = 5
                explanation = f"Decent ROE ({roe_pct:.1f}%)"
            elif roe > 0:
                impact = 0
                explanation = f"Low ROE ({roe_pct:.1f}%)"
            else:
                impact = -10
                explanation = f"Negative ROE ({roe_pct:.1f}%)"
            score += impact
            factors.append(AnalysisFactor("ROE", f"{roe_pct:.1f}%", impact, explanation))

        # ROA
        roa = info.get("returnOnAssets")
        if roa is not None:
            data_points += 1
            roa_pct = roa * 100
            if roa > 0.10:
                impact = 5
            elif roa > 0.05:
                impact = 2
            elif roa > 0:
                impact = 0
            else:
                impact = -5
            score += impact
            factors.append(AnalysisFactor(
                "ROA", f"{roa_pct:.1f}%", impact,
                f"Return on assets: {roa_pct:.1f}%"))

        # --- GROWTH ---
        # Revenue Growth
        rev_growth = info.get("revenueGrowth")
        if rev_growth is not None:
            data_points += 1
            rg_pct = rev_growth * 100
            if rev_growth > 0.25:
                impact = 15
                explanation = f"Strong revenue growth ({rg_pct:.1f}%)"
            elif rev_growth > 0.10:
                impact = 8
                explanation = f"Good revenue growth ({rg_pct:.1f}%)"
            elif rev_growth > 0:
                impact = 2
                explanation = f"Modest revenue growth ({rg_pct:.1f}%)"
            else:
                impact = -12
                explanation = f"Revenue declining ({rg_pct:.1f}%)"
            score += impact
            factors.append(AnalysisFactor("Revenue Growth", f"{rg_pct:.1f}%", impact, explanation))
            confidence_count += 1

        # Earnings Growth
        earn_growth = info.get("earningsGrowth")
        if earn_growth is not None:
            data_points += 1
            eg_pct = earn_growth * 100
            if earn_growth > 0.25:
                impact = 12
            elif earn_growth > 0.10:
                impact = 6
            elif earn_growth > 0:
                impact = 2
            else:
                impact = -10
            score += impact
            factors.append(AnalysisFactor(
                "Earnings Growth", f"{eg_pct:.1f}%", impact,
                f"Earnings growth: {eg_pct:.1f}%"))

        # --- BALANCE SHEET ---
        # Debt to Equity
        de = info.get("debtToEquity")
        if de is not None:
            data_points += 1
            de_val = de / 100 if de > 5 else de  # yfinance sometimes returns as percentage
            if de < 30:
                impact = 10
                explanation = f"Low debt-to-equity ({de:.0f}) - conservative balance sheet"
            elif de < 80:
                impact = 3
                explanation = f"Moderate debt-to-equity ({de:.0f})"
            elif de < 150:
                impact = -5
                explanation = f"Elevated debt-to-equity ({de:.0f})"
            else:
                impact = -12
                explanation = f"High debt-to-equity ({de:.0f}) - leverage risk"
            score += impact
            factors.append(AnalysisFactor("Debt/Equity", f"{de:.0f}", impact, explanation))
            confidence_count += 1

        # Current Ratio
        current_ratio = info.get("currentRatio")
        if current_ratio is not None:
            data_points += 1
            if current_ratio > 2:
                impact = 5
                explanation = f"Strong current ratio ({current_ratio:.2f}) - ample liquidity"
            elif current_ratio > 1:
                impact = 2
                explanation = f"Adequate current ratio ({current_ratio:.2f})"
            else:
                impact = -10
                explanation = f"Low current ratio ({current_ratio:.2f}) - liquidity concern"
            score += impact
            factors.append(AnalysisFactor("Current Ratio", f"{current_ratio:.2f}", impact, explanation))

        # --- CASH FLOW ---
        fcf = info.get("freeCashflow")
        market_cap = info.get("marketCap")
        if fcf is not None and market_cap is not None and market_cap > 0:
            data_points += 1
            fcf_yield = (fcf / market_cap) * 100
            if fcf_yield > 8:
                impact = 10
                explanation = f"High FCF yield ({fcf_yield:.1f}%) - strong cash generation"
            elif fcf_yield > 4:
                impact = 5
                explanation = f"Good FCF yield ({fcf_yield:.1f}%)"
            elif fcf_yield > 0:
                impact = 0
                explanation = f"Positive FCF yield ({fcf_yield:.1f}%)"
            else:
                impact = -8
                explanation = f"Negative FCF yield ({fcf_yield:.1f}%) - burning cash"
            score += impact
            factors.append(AnalysisFactor("FCF Yield", f"{fcf_yield:.1f}%", impact, explanation))

        # Dividend Yield
        div_yield = info.get("dividendYield")
        if div_yield is not None and div_yield > 0:
            data_points += 1
            dy_pct = div_yield * 100
            if dy_pct > 5:
                impact = 3
                explanation = f"High dividend yield ({dy_pct:.2f}%) - check sustainability"
            elif dy_pct > 2:
                impact = 5
                explanation = f"Attractive dividend yield ({dy_pct:.2f}%)"
            else:
                impact = 2
                explanation = f"Modest dividend yield ({dy_pct:.2f}%)"
            score += impact
            factors.append(AnalysisFactor("Dividend Yield", f"{dy_pct:.2f}%", impact, explanation))

        # Confidence based on data availability
        max_expected = 16
        confidence = min(1.0, (data_points / max_expected) * 0.8 + 0.2)
        if confidence_count >= 4:
            confidence = min(1.0, confidence + 0.1)

        # Normalize score to -100/+100 range
        if data_points > 0:
            max_possible = data_points * 15  # rough max per data point
            score = (score / max(max_possible, 1)) * 100
            score = max(-100, min(100, score))

        summary = self._build_summary(score, factors, sector)
        return self._make_result(score, confidence, factors, summary)

    def _build_summary(self, score: float, factors: list[AnalysisFactor], sector: str) -> str:
        if score > 20:
            outlook = "positive"
        elif score < -20:
            outlook = "negative"
        else:
            outlook = "neutral"

        bullish = [f for f in factors if f.impact > 5]
        bearish = [f for f in factors if f.impact < -5]

        parts = [f"Fundamental outlook is {outlook} for this {sector} company."]
        if bullish:
            strengths = ", ".join(f.name for f in bullish[:3])
            parts.append(f"Strengths: {strengths}.")
        if bearish:
            weaknesses = ", ".join(f.name for f in bearish[:3])
            parts.append(f"Concerns: {weaknesses}.")

        return " ".join(parts)
