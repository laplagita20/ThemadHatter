"""Earnings Quality Analyzer: Accruals ratio, cash flow vs earnings, earnings consistency.

Combines accruals analysis, cash conversion, revenue quality, and earnings surprise patterns
to assess the quality and sustainability of reported earnings.
"""

import logging
import numpy as np
import yfinance as yf

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.connection import get_connection

logger = logging.getLogger("stock_model.analysis.earnings_quality")


class EarningsQualityAnalyzer(BaseAnalyzer):
    """Analyzes earnings quality through accruals, cash conversion, and consistency."""

    name = "earnings_quality"

    def __init__(self):
        self.db = get_connection()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running earnings quality analysis for %s", ticker)
        factors = []
        score = 0.0
        data_points = 0

        stock = yf.Ticker(ticker)

        # --- Accruals Ratio ---
        accruals = self._calculate_accruals(stock)
        if accruals is not None:
            data_points += 1
            if accruals["ratio"] < -0.05:
                impact = 10
                explanation = f"Low accruals ratio ({accruals['ratio']:.3f}) - cash-backed earnings, high quality"
            elif accruals["ratio"] < 0.05:
                impact = 5
                explanation = f"Moderate accruals ({accruals['ratio']:.3f}) - reasonable earnings quality"
            elif accruals["ratio"] < 0.10:
                impact = -5
                explanation = f"Elevated accruals ({accruals['ratio']:.3f}) - earnings quality concern"
            else:
                impact = -15
                explanation = f"High accruals ({accruals['ratio']:.3f}) - low quality earnings, potentially unsustainable"
            score += impact
            factors.append(AnalysisFactor("Accruals Ratio", f"{accruals['ratio']:.3f}", impact, explanation))

        # --- Cash Flow vs Earnings ---
        cash_quality = self._cash_flow_quality(stock)
        if cash_quality is not None:
            data_points += 1
            ratio = cash_quality["ocf_to_ni"]
            if ratio > 1.2:
                impact = 10
                explanation = f"Operating CF/Net Income = {ratio:.2f}x - cash generation exceeds earnings (high quality)"
            elif ratio > 0.8:
                impact = 5
                explanation = f"Operating CF/Net Income = {ratio:.2f}x - good cash conversion"
            elif ratio > 0.5:
                impact = -5
                explanation = f"Operating CF/Net Income = {ratio:.2f}x - weak cash conversion"
            else:
                impact = -12
                explanation = f"Operating CF/Net Income = {ratio:.2f}x - poor cash backing of earnings"
            score += impact
            factors.append(AnalysisFactor("Cash Conversion", f"{ratio:.2f}x", impact, explanation))

        # --- Earnings Surprise Pattern ---
        surprise = self._earnings_surprise_pattern(ticker)
        if surprise is not None:
            data_points += 1
            score += surprise["impact"]
            factors.append(AnalysisFactor(
                "Earnings Surprises",
                surprise["pattern"],
                surprise["impact"],
                surprise["explanation"],
            ))

        # --- Revenue Quality (Revenue Growth vs Receivables Growth) ---
        rev_quality = self._revenue_quality(stock)
        if rev_quality is not None:
            data_points += 1
            score += rev_quality["impact"]
            factors.append(AnalysisFactor(
                "Revenue Quality",
                rev_quality["label"],
                rev_quality["impact"],
                rev_quality["explanation"],
            ))

        if data_points == 0:
            return self._make_result(0, 0.15, [], "Insufficient data for earnings quality analysis")

        confidence = min(1.0, data_points / 4 * 0.7 + 0.2)

        if score > 10:
            summary = "Earnings quality is HIGH - cash-backed, consistent, genuine"
        elif score > 0:
            summary = "Earnings quality is acceptable with minor concerns"
        elif score > -10:
            summary = "Earnings quality has some concerns - monitor closely"
        else:
            summary = "Earnings quality is LOW - significant concerns about sustainability"

        return self._make_result(score, confidence, factors, summary)

    def _calculate_accruals(self, stock) -> dict | None:
        """Accruals Ratio = (Net Income - Operating Cash Flow) / Total Assets."""
        try:
            income_stmt = stock.income_stmt
            cashflow = stock.cashflow
            balance_sheet = stock.balance_sheet

            if any(df is None or df.empty for df in [income_stmt, cashflow, balance_sheet]):
                return None

            def _get(df, label, col_idx=0):
                if label in df.index:
                    val = df.iloc[df.index.get_loc(label), col_idx]
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return float(val)
                return None

            net_income = _get(income_stmt, "Net Income")
            ocf = _get(cashflow, "Operating Cash Flow")
            total_assets = _get(balance_sheet, "Total Assets")

            if not all([net_income, ocf, total_assets]) or total_assets == 0:
                return None

            ratio = (net_income - ocf) / total_assets
            return {"ratio": ratio, "net_income": net_income, "ocf": ocf}
        except Exception as e:
            logger.debug("Accruals calculation failed: %s", e)
            return None

    def _cash_flow_quality(self, stock) -> dict | None:
        """Operating Cash Flow / Net Income ratio."""
        try:
            income_stmt = stock.income_stmt
            cashflow = stock.cashflow

            if any(df is None or df.empty for df in [income_stmt, cashflow]):
                return None

            def _get(df, label, col_idx=0):
                if label in df.index:
                    val = df.iloc[df.index.get_loc(label), col_idx]
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return float(val)
                return None

            net_income = _get(income_stmt, "Net Income")
            ocf = _get(cashflow, "Operating Cash Flow")

            if net_income is None or ocf is None or net_income == 0:
                return None

            return {"ocf_to_ni": ocf / net_income}
        except Exception as e:
            logger.debug("Cash flow quality failed: %s", e)
            return None

    def _earnings_surprise_pattern(self, ticker: str) -> dict | None:
        """Analyze consecutive beats/misses from earnings history."""
        try:
            earnings = self.db.execute(
                """SELECT * FROM earnings_history
                   WHERE ticker = ?
                   ORDER BY fiscal_date DESC LIMIT 8""",
                (ticker,),
            )
            earnings = list(earnings)

            if not earnings or len(earnings) < 2:
                return None

            # Count consecutive beats/misses from most recent
            consecutive_beats = 0
            consecutive_misses = 0
            for e in earnings:
                surprise = e.get("surprise_pct") or e.get("surprise")
                if surprise is None:
                    break
                if surprise > 0:
                    if consecutive_misses > 0:
                        break
                    consecutive_beats += 1
                elif surprise < 0:
                    if consecutive_beats > 0:
                        break
                    consecutive_misses += 1
                else:
                    break

            # Average surprise magnitude
            surprises = [e["surprise_pct"] or e.get("surprise") or 0 for e in earnings if e.get("surprise_pct") is not None or e.get("surprise") is not None]
            avg_surprise = np.mean(surprises) if surprises else 0

            if consecutive_beats >= 4:
                impact = 10
                pattern = f"{consecutive_beats} consecutive beats"
                explanation = f"{consecutive_beats} consecutive earnings beats (avg surprise: {avg_surprise:.1f}%) - management consistently executing"
            elif consecutive_beats >= 2:
                impact = 5
                pattern = f"{consecutive_beats} consecutive beats"
                explanation = f"{consecutive_beats} consecutive earnings beats - positive trend"
            elif consecutive_misses >= 2:
                impact = -10
                pattern = f"{consecutive_misses} consecutive misses"
                explanation = f"{consecutive_misses} consecutive earnings misses (avg surprise: {avg_surprise:.1f}%) - credibility concerns"
            elif consecutive_misses >= 1:
                impact = -5
                pattern = "Recent miss"
                explanation = f"Recent earnings miss - watch next quarter"
            else:
                impact = 0
                pattern = "Mixed"
                explanation = f"Mixed earnings history (avg surprise: {avg_surprise:.1f}%)"

            return {"impact": impact, "pattern": pattern, "explanation": explanation}
        except Exception as e:
            logger.debug("Earnings surprise pattern failed: %s", e)
            return None

    def _revenue_quality(self, stock) -> dict | None:
        """Compare revenue growth vs receivables growth (detect channel stuffing)."""
        try:
            income_stmt = stock.income_stmt
            balance_sheet = stock.balance_sheet

            if any(df is None or df.empty for df in [income_stmt, balance_sheet]):
                return None
            if len(income_stmt.columns) < 2 or len(balance_sheet.columns) < 2:
                return None

            def _get(df, label, col_idx=0):
                if label in df.index:
                    val = df.iloc[df.index.get_loc(label), col_idx]
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return float(val)
                return None

            rev_curr = _get(income_stmt, "Total Revenue", 0)
            rev_prev = _get(income_stmt, "Total Revenue", 1)
            recv_curr = _get(balance_sheet, "Accounts Receivable", 0) or _get(balance_sheet, "Net Receivables", 0)
            recv_prev = _get(balance_sheet, "Accounts Receivable", 1) or _get(balance_sheet, "Net Receivables", 1)

            if not all([rev_curr, rev_prev, recv_curr, recv_prev]):
                return None
            if rev_prev == 0 or recv_prev == 0:
                return None

            rev_growth = (rev_curr - rev_prev) / abs(rev_prev) * 100
            recv_growth = (recv_curr - recv_prev) / abs(recv_prev) * 100

            # If receivables grow much faster than revenue -> potential channel stuffing
            if recv_growth > rev_growth + 15:
                impact = -8
                label = "Poor"
                explanation = f"Receivables growing faster than revenue ({recv_growth:.0f}% vs {rev_growth:.0f}%) - potential channel stuffing"
            elif recv_growth > rev_growth + 5:
                impact = -3
                label = "Watch"
                explanation = f"Receivables outpacing revenue ({recv_growth:.0f}% vs {rev_growth:.0f}%) - monitor"
            elif rev_growth > recv_growth:
                impact = 5
                label = "Good"
                explanation = f"Revenue growing faster than receivables ({rev_growth:.0f}% vs {recv_growth:.0f}%) - healthy collections"
            else:
                impact = 0
                label = "Neutral"
                explanation = f"Revenue and receivables growth in line ({rev_growth:.0f}% vs {recv_growth:.0f}%)"

            return {"impact": impact, "label": label, "explanation": explanation}
        except Exception as e:
            logger.debug("Revenue quality check failed: %s", e)
            return None
