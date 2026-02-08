"""Insider Trading Analyzer: Form 4 insider trading pattern analysis.

Analyzes SEC Form 4 filings (insider trades) already collected by SEC EDGAR collector.
Signals: cluster buying, executive purchases, sell patterns, buy/sell ratio.
"""

import logging
from datetime import datetime, timedelta

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.models import InsiderTradeDAO

logger = logging.getLogger("stock_model.analysis.insider")


class InsiderAnalyzer(BaseAnalyzer):
    """Analyzes insider trading patterns from Form 4 filings."""

    name = "insider"

    def __init__(self):
        self.insider_dao = InsiderTradeDAO()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running insider trading analysis for %s", ticker)
        factors = []
        score = 0.0

        # Get insider trades from database (last 365 days for full picture)
        all_trades = list(self.insider_dao.get_all_recent(ticker, days=365))
        recent_trades = list(self.insider_dao.get_recent(ticker, days=90))

        if not all_trades:
            return self._make_result(0, 0.2, [], "No insider trading data available")

        # --- Cluster Buying (3+ insiders buying within 30 days) ---
        recent_30d = [t for t in all_trades
                      if t["transaction_date"] and
                      t["transaction_date"] >= (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")]
        buyers_30d = [t for t in recent_30d if self._is_buy(t)]
        unique_buyers_30d = len(set(t["filer_name"] for t in buyers_30d if t["filer_name"]))

        if unique_buyers_30d >= 3:
            impact = 20
            explanation = f"Cluster buying: {unique_buyers_30d} insiders purchased in last 30 days - strong bullish signal"
            score += impact
            factors.append(AnalysisFactor("Cluster Buying", str(unique_buyers_30d), impact, explanation))
        elif unique_buyers_30d >= 2:
            impact = 10
            explanation = f"{unique_buyers_30d} insiders buying in last 30 days"
            score += impact
            factors.append(AnalysisFactor("Insider Buying", str(unique_buyers_30d), impact, explanation))

        # --- CEO/CFO Buying ---
        exec_titles = {"ceo", "chief executive", "cfo", "chief financial", "president"}
        exec_buyers = [t for t in recent_trades
                       if self._is_buy(t) and t["filer_title"]
                       and any(title in t["filer_title"].lower() for title in exec_titles)]
        if exec_buyers:
            total_exec_value = sum(abs(t["total_value"] or 0) for t in exec_buyers)
            impact = 15
            explanation = f"C-suite insider buying: {len(exec_buyers)} executive purchases (${total_exec_value:,.0f} total) - they know the business best"
            score += impact
            factors.append(AnalysisFactor("Executive Buying", f"${total_exec_value:,.0f}", impact, explanation))

        # --- Large Insider Selling ---
        sellers_90d = [t for t in recent_trades if self._is_sell(t)]
        large_sells = [t for t in sellers_90d if (t["total_value"] or 0) > 1_000_000]
        if large_sells:
            total_sell_value = sum(abs(t["total_value"] or 0) for t in large_sells)
            # Check if it might be 10b5-1 planned sales (we note uncertainty)
            impact = -10
            explanation = f"Large insider selling: {len(large_sells)} sales > $1M (${total_sell_value:,.0f} total) - could be planned 10b5-1 or bearish signal"
            score += impact
            factors.append(AnalysisFactor("Large Insider Selling", f"${total_sell_value:,.0f}", impact, explanation))

        # --- Buy/Sell Ratio (90 days) ---
        buys_90d = [t for t in recent_trades if self._is_buy(t)]
        sells_90d = [t for t in recent_trades if self._is_sell(t)]
        total_buy_value = sum(abs(t["total_value"] or 0) for t in buys_90d)
        total_sell_value = sum(abs(t["total_value"] or 0) for t in sells_90d)

        if total_buy_value + total_sell_value > 0:
            buy_ratio = total_buy_value / (total_buy_value + total_sell_value)
            if buy_ratio > 0.7:
                impact = 10
                explanation = f"Insider buy/sell ratio {buy_ratio:.0%} - overwhelmingly buying (${total_buy_value:,.0f} bought vs ${total_sell_value:,.0f} sold)"
            elif buy_ratio > 0.5:
                impact = 5
                explanation = f"Insider buy/sell ratio {buy_ratio:.0%} - net buying"
            elif buy_ratio < 0.2:
                impact = -8
                explanation = f"Insider buy/sell ratio {buy_ratio:.0%} - heavy selling (${total_sell_value:,.0f} sold vs ${total_buy_value:,.0f} bought)"
            else:
                impact = -3
                explanation = f"Insider buy/sell ratio {buy_ratio:.0%} - net selling"
            score += impact
            factors.append(AnalysisFactor("Buy/Sell Ratio", f"{buy_ratio:.0%}", impact, explanation))

        # --- Dollar-Weighted Insider Sentiment ---
        net_insider_flow = total_buy_value - total_sell_value
        if abs(net_insider_flow) > 100_000:
            if net_insider_flow > 0:
                impact = 5
                explanation = f"Net insider buying: ${net_insider_flow:,.0f} over 90 days"
            else:
                impact = -5
                explanation = f"Net insider selling: ${abs(net_insider_flow):,.0f} over 90 days"
            score += impact
            factors.append(AnalysisFactor("Net Insider Flow", f"${net_insider_flow:,.0f}", impact, explanation))

        # Confidence based on data volume
        trade_count = len(all_trades)
        if trade_count >= 10:
            confidence = 0.8
        elif trade_count >= 5:
            confidence = 0.6
        elif trade_count >= 2:
            confidence = 0.4
        else:
            confidence = 0.25

        summary = self._build_summary(score, len(buys_90d), len(sells_90d))
        return self._make_result(score, confidence, factors, summary)

    def _is_buy(self, trade) -> bool:
        tx_type = (trade.get("transaction_type") or "").upper()
        return tx_type in ("P", "BUY", "PURCHASE", "P-PURCHASE", "A-AWARD")

    def _is_sell(self, trade) -> bool:
        tx_type = (trade.get("transaction_type") or "").upper()
        return tx_type in ("S", "SELL", "SALE", "S-SALE", "D-DISPOSITION")

    def _build_summary(self, score: float, buys: int, sells: int) -> str:
        if score > 15:
            sentiment = "strongly bullish"
        elif score > 5:
            sentiment = "moderately bullish"
        elif score < -10:
            sentiment = "bearish"
        elif score < -5:
            sentiment = "cautious"
        else:
            sentiment = "neutral"
        return f"Insider sentiment is {sentiment} ({buys} buys, {sells} sells in 90 days)"
