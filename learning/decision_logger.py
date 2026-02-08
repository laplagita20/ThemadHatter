"""Decision logger: snapshot every decision with full data state."""

import json
import logging
from datetime import datetime

from database.connection import get_connection
from database.models import AnalysisResultDAO, PriceDAO, FundamentalsDAO

logger = logging.getLogger("stock_model.learning.decision_logger")


class DecisionLogger:
    """Captures full data snapshots at the time of each decision."""

    def __init__(self):
        self.db = get_connection()
        self.analysis_dao = AnalysisResultDAO()
        self.price_dao = PriceDAO()
        self.fund_dao = FundamentalsDAO()

    def snapshot_decision(self, decision_id: int, ticker: str):
        """Create a full data snapshot for a decision."""
        snapshot = {
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "price_at_decision": self._get_current_price(ticker),
            "analysis_results": self._get_analysis_snapshot(ticker),
            "fundamentals": self._get_fundamentals_snapshot(ticker),
            "recent_prices": self._get_recent_prices(ticker),
            "macro_regime": self._get_macro_snapshot(),
            "news_summary": self._get_news_snapshot(ticker),
        }

        self.db.execute_insert(
            """INSERT INTO decision_snapshots (decision_id, ticker, snapshot_data_json)
               VALUES (?, ?, ?)""",
            (decision_id, ticker, json.dumps(snapshot, default=str)),
        )
        logger.info("Captured snapshot for decision %d (%s)", decision_id, ticker)
        return snapshot

    def _get_current_price(self, ticker: str) -> float | None:
        return self.price_dao.get_latest_price(ticker)

    def _get_analysis_snapshot(self, ticker: str) -> list:
        results = self.analysis_dao.get_latest(ticker)
        if not results:
            return []
        return [
            {
                "analyzer": r["analyzer_name"],
                "score": r["score"],
                "confidence": r["confidence"],
                "signal": r["signal"],
                "summary": r["summary"],
            }
            for r in results
        ]

    def _get_fundamentals_snapshot(self, ticker: str) -> dict:
        fund = self.fund_dao.get_latest(ticker)
        if not fund:
            return {}
        return {
            "pe_ratio": fund["pe_ratio"],
            "profit_margin": fund["profit_margin"],
            "revenue_growth": fund["revenue_growth"],
            "debt_to_equity": fund["debt_to_equity"],
            "market_cap": fund["market_cap"],
        }

    def _get_recent_prices(self, ticker: str) -> list:
        prices = self.price_dao.get_history(ticker, days=30)
        return [{"date": p["date"], "close": p["close"]} for p in (prices or [])[:30]]

    def _get_macro_snapshot(self) -> dict:
        row = self.db.execute_one(
            "SELECT * FROM macro_regime ORDER BY date DESC LIMIT 1"
        )
        if row:
            return {
                "growth": row["growth_regime"],
                "inflation": row["inflation_regime"],
                "rate": row["rate_regime"],
                "risk": row["risk_regime"],
            }
        return {}

    def _get_news_snapshot(self, ticker: str) -> dict:
        articles = self.db.execute(
            """SELECT COUNT(*) as cnt,
                      AVG(sentiment_score) as avg_sentiment
               FROM news_articles
               WHERE ticker = ? AND published_at >= datetime('now', '-7 days')""",
            (ticker,),
        )
        if articles and articles[0]:
            return {
                "article_count_7d": articles[0]["cnt"],
                "avg_sentiment_7d": articles[0]["avg_sentiment"],
            }
        return {}
