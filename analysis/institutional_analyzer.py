"""Institutional Ownership Analyzer: 13-F hedge fund holdings analysis.

Analyzes SEC 13-F filings to detect institutional accumulation/distribution patterns.
"""

import logging

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.models import HedgeFundHoldingDAO

logger = logging.getLogger("stock_model.analysis.institutional")


class InstitutionalAnalyzer(BaseAnalyzer):
    """Analyzes institutional ownership trends from 13-F filings."""

    name = "institutional"

    def __init__(self):
        self.holding_dao = HedgeFundHoldingDAO()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running institutional ownership analysis for %s", ticker)
        factors = []
        score = 0.0

        # Get historical institutional holdings
        historical = list(self.holding_dao.get_historical(ticker))
        latest_holders = list(self.holding_dao.get_latest_reports(ticker))

        if not historical or len(historical) < 1:
            return self._make_result(0, 0.15, [], "No 13-F institutional holdings data available")

        # --- Number of Institutional Holders Trend ---
        if len(historical) >= 2:
            curr_holders = historical[0]["num_holders"]
            prev_holders = historical[1]["num_holders"]

            if curr_holders > prev_holders:
                change_pct = ((curr_holders - prev_holders) / max(prev_holders, 1)) * 100
                if change_pct > 20:
                    impact = 15
                    explanation = f"Institutional holders surging: {prev_holders} -> {curr_holders} (+{change_pct:.0f}%) - smart money accumulating"
                else:
                    impact = 10
                    explanation = f"Institutional holders increasing: {prev_holders} -> {curr_holders} (+{change_pct:.0f}%)"
                score += impact
                factors.append(AnalysisFactor("Holder Count Trend", f"{curr_holders}", impact, explanation))
            elif curr_holders < prev_holders:
                change_pct = ((prev_holders - curr_holders) / max(prev_holders, 1)) * 100
                if change_pct > 20:
                    impact = -10
                    explanation = f"Institutional holders dropping: {prev_holders} -> {curr_holders} (-{change_pct:.0f}%) - smart money exiting"
                else:
                    impact = -5
                    explanation = f"Institutional holders declining: {prev_holders} -> {curr_holders} (-{change_pct:.0f}%)"
                score += impact
                factors.append(AnalysisFactor("Holder Count Trend", f"{curr_holders}", impact, explanation))

        # --- Total Shares Held Trend ---
        if len(historical) >= 2:
            curr_shares = historical[0]["total_shares"] or 0
            prev_shares = historical[1]["total_shares"] or 0

            if prev_shares > 0 and curr_shares > 0:
                share_change = ((curr_shares - prev_shares) / prev_shares) * 100
                if share_change > 10:
                    impact = 10
                    explanation = f"Institutional shares increasing by {share_change:.0f}% - accumulation pattern"
                    score += impact
                    factors.append(AnalysisFactor("Share Accumulation", f"+{share_change:.0f}%", impact, explanation))
                elif share_change < -10:
                    impact = -8
                    explanation = f"Institutional shares decreasing by {abs(share_change):.0f}% - distribution pattern"
                    score += impact
                    factors.append(AnalysisFactor("Share Distribution", f"{share_change:.0f}%", impact, explanation))

        # --- Total Value Trend ---
        if len(historical) >= 2:
            curr_value = historical[0]["total_value"] or 0
            prev_value = historical[1]["total_value"] or 0

            if prev_value > 0 and curr_value > 0:
                value_change = ((curr_value - prev_value) / prev_value) * 100
                if value_change > 20:
                    impact = 5
                    explanation = f"Institutional value up {value_change:.0f}% (price appreciation + accumulation)"
                    score += impact
                    factors.append(AnalysisFactor("Institutional Value", f"+{value_change:.0f}%", impact, explanation))

        # --- Top Holders Concentration ---
        if latest_holders and len(latest_holders) >= 2:
            total_value = sum(h["value"] or 0 for h in latest_holders)
            if total_value > 0:
                top_10_value = sum(h["value"] or 0 for h in latest_holders[:10])
                concentration = (top_10_value / total_value) * 100

                top_names = [h["fund_name"] for h in latest_holders[:3] if h["fund_name"]]
                top_names_str = ", ".join(top_names[:3]) if top_names else "Unknown funds"

                if concentration > 60:
                    impact = -3
                    explanation = f"High concentration: top 10 holders own {concentration:.0f}% - concentrated ownership risk. Top: {top_names_str}"
                else:
                    impact = 3
                    explanation = f"Diversified ownership: top 10 holders own {concentration:.0f}%. Top: {top_names_str}"
                score += impact
                factors.append(AnalysisFactor("Ownership Concentration", f"{concentration:.0f}%", impact, explanation))

        # Confidence based on data quality
        if len(historical) >= 4:
            confidence = 0.7
        elif len(historical) >= 2:
            confidence = 0.5
        else:
            confidence = 0.3

        summary = self._build_summary(score, len(latest_holders), historical)
        return self._make_result(score, confidence, factors, summary)

    def _build_summary(self, score: float, num_holders: int, historical: list) -> str:
        if score > 10:
            trend = "bullish (accumulation)"
        elif score > 0:
            trend = "moderately positive"
        elif score < -5:
            trend = "bearish (distribution)"
        else:
            trend = "neutral"

        return f"Institutional ownership trend is {trend} with {num_holders} reported holders"
