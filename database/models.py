"""Data access objects (DAOs) for database operations."""

import json
import logging
from datetime import datetime
from database.connection import get_connection

logger = logging.getLogger("stock_model.models")


class StockDAO:
    """Data access for the stocks watchlist table."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def upsert(self, ticker: str, company_name: str = None, sector: str = None,
               industry: str = None, cik: str = None, country: str = "US",
               market_cap: float = None):
        self.db.execute_insert(
            """INSERT INTO stocks (ticker, company_name, sector, industry, cik, country, market_cap)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(ticker) DO UPDATE SET
                 company_name=COALESCE(excluded.company_name, company_name),
                 sector=COALESCE(excluded.sector, sector),
                 industry=COALESCE(excluded.industry, industry),
                 cik=COALESCE(excluded.cik, cik),
                 country=COALESCE(excluded.country, country),
                 market_cap=COALESCE(excluded.market_cap, market_cap)""",
            (ticker, company_name, sector, industry, cik, country, market_cap),
        )

    def get(self, ticker: str):
        return self.db.execute_one("SELECT * FROM stocks WHERE ticker = ?", (ticker,))

    def get_all_active(self):
        return self.db.execute("SELECT * FROM stocks WHERE is_active = 1")

    def get_watchlist(self):
        return self.db.execute(
            "SELECT ticker, company_name, sector FROM stocks WHERE is_active = 1 ORDER BY ticker"
        )


class PriceDAO:
    """Data access for price history."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def upsert_many(self, ticker: str, rows: list[dict]):
        params = [
            (ticker, r["date"], r.get("open"), r.get("high"), r.get("low"),
             r["close"], r.get("volume"), r.get("adj_close"))
            for r in rows
        ]
        self.db.execute_many(
            """INSERT OR REPLACE INTO price_history
               (ticker, date, open, high, low, close, volume, adj_close)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            params,
        )

    def get_history(self, ticker: str, days: int = 365):
        return self.db.execute(
            """SELECT * FROM price_history WHERE ticker = ?
               ORDER BY date DESC LIMIT ?""",
            (ticker, days),
        )

    def get_latest_price(self, ticker: str):
        row = self.db.execute_one(
            "SELECT close FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker,),
        )
        return row["close"] if row else None


class FundamentalsDAO:
    """Data access for stock fundamentals."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def insert(self, ticker: str, data: dict):
        self.db.execute_insert(
            """INSERT INTO stock_fundamentals
               (ticker, pe_ratio, forward_pe, pb_ratio, ps_ratio, ev_ebitda,
                peg_ratio, profit_margin, operating_margin, gross_margin,
                roe, roa, roic, revenue_growth, earnings_growth,
                debt_to_equity, current_ratio, quick_ratio, free_cash_flow,
                dividend_yield, beta, market_cap, enterprise_value, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker,
                data.get("pe_ratio"), data.get("forward_pe"),
                data.get("pb_ratio"), data.get("ps_ratio"),
                data.get("ev_ebitda"), data.get("peg_ratio"),
                data.get("profit_margin"), data.get("operating_margin"),
                data.get("gross_margin"), data.get("roe"), data.get("roa"),
                data.get("roic"), data.get("revenue_growth"),
                data.get("earnings_growth"), data.get("debt_to_equity"),
                data.get("current_ratio"), data.get("quick_ratio"),
                data.get("free_cash_flow"), data.get("dividend_yield"),
                data.get("beta"), data.get("market_cap"),
                data.get("enterprise_value"),
                json.dumps(data.get("raw", {}), default=str),
            ),
        )

    def get_latest(self, ticker: str):
        return self.db.execute_one(
            """SELECT * FROM stock_fundamentals WHERE ticker = ?
               ORDER BY fetched_at DESC LIMIT 1""",
            (ticker,),
        )


class AnalysisResultDAO:
    """Data access for analysis results."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def insert(self, ticker: str, analyzer_name: str, score: float,
               confidence: float, signal: str, factors: list, summary: str):
        self.db.execute_insert(
            """INSERT INTO analysis_results
               (ticker, analyzer_name, score, confidence, signal, factors_json, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ticker, analyzer_name, score, confidence, signal,
             json.dumps(factors, default=str), summary),
        )

    def get_latest(self, ticker: str, analyzer_name: str = None):
        if analyzer_name:
            return self.db.execute_one(
                """SELECT * FROM analysis_results
                   WHERE ticker = ? AND analyzer_name = ?
                   ORDER BY analyzed_at DESC LIMIT 1""",
                (ticker, analyzer_name),
            )
        return self.db.execute(
            """SELECT * FROM analysis_results WHERE ticker = ?
               AND analyzed_at = (SELECT MAX(analyzed_at) FROM analysis_results WHERE ticker = ?)""",
            (ticker, ticker),
        )


class DecisionDAO:
    """Data access for decisions."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def insert(self, decision: dict) -> int:
        return self.db.execute_insert(
            """INSERT INTO decisions
               (ticker, action, composite_score, confidence,
                position_size_pct, stop_loss_pct, target_price, time_horizon,
                reasoning_json, bull_case, bear_case, risk_warnings,
                analysis_breakdown_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision["ticker"], decision["action"],
                decision["composite_score"], decision["confidence"],
                decision.get("position_size_pct"),
                decision.get("stop_loss_pct"),
                decision.get("target_price"),
                decision.get("time_horizon"),
                json.dumps(decision.get("reasoning", []), default=str),
                decision.get("bull_case"),
                decision.get("bear_case"),
                decision.get("risk_warnings"),
                json.dumps(decision.get("analysis_breakdown", {}), default=str),
            ),
        )

    def get_latest(self, ticker: str):
        return self.db.execute_one(
            "SELECT * FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT 1",
            (ticker,),
        )

    def get_pending_outcomes(self):
        return self.db.execute(
            """SELECT * FROM decisions
               WHERE outcome_1w IS NULL OR outcome_1m IS NULL
               ORDER BY decided_at DESC"""
        )

    def update_outcome(self, decision_id: int, period: str, value: float):
        col = f"outcome_{period}"
        self.db.execute(
            f"UPDATE decisions SET {col} = ? WHERE id = ?",
            (value, decision_id),
        )


class NewsDAO:
    """Data access for news articles."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def insert(self, article: dict):
        try:
            self.db.execute_insert(
                """INSERT OR IGNORE INTO news_articles
                   (title, summary, source, url, published_at, ticker,
                    credibility_weight, sentiment_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    article["title"], article.get("summary"),
                    article["source"], article.get("url"),
                    article.get("published_at"), article.get("ticker"),
                    article.get("credibility_weight", 0.7),
                    article.get("sentiment_score"),
                ),
            )
        except Exception as e:
            logger.debug("News insert skipped (likely duplicate): %s", e)

    def get_recent(self, ticker: str = None, days: int = 30, limit: int = 100):
        if ticker:
            return self.db.execute(
                """SELECT * FROM news_articles
                   WHERE ticker = ? AND published_at >= datetime('now', ?)
                   ORDER BY published_at DESC LIMIT ?""",
                (ticker, f"-{days} days", limit),
            )
        return self.db.execute(
            """SELECT * FROM news_articles
               WHERE published_at >= datetime('now', ?)
               ORDER BY published_at DESC LIMIT ?""",
            (f"-{days} days", limit),
        )


class MacroDAO:
    """Data access for macroeconomic indicators."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def upsert(self, series_id: str, series_name: str, date: str, value: float):
        self.db.execute_insert(
            """INSERT OR REPLACE INTO macro_indicators
               (series_id, series_name, date, value)
               VALUES (?, ?, ?, ?)""",
            (series_id, series_name, date, value),
        )

    def get_series(self, series_id: str, limit: int = 120):
        return self.db.execute(
            """SELECT * FROM macro_indicators
               WHERE series_id = ? ORDER BY date DESC LIMIT ?""",
            (series_id, limit),
        )

    def get_latest(self, series_id: str):
        return self.db.execute_one(
            "SELECT * FROM macro_indicators WHERE series_id = ? ORDER BY date DESC LIMIT 1",
            (series_id,),
        )


class PortfolioDAO:
    """Data access for portfolio data."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def snapshot_holdings(self, holdings: list[dict]):
        now = datetime.now().isoformat()
        for h in holdings:
            self.db.execute_insert(
                """INSERT INTO portfolio_holdings
                   (ticker, quantity, average_cost, current_price,
                    market_value, unrealized_pl, unrealized_pl_pct, sector, snapshot_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    h["ticker"], h["quantity"], h.get("average_cost"),
                    h.get("current_price"), h.get("market_value"),
                    h.get("unrealized_pl"), h.get("unrealized_pl_pct"),
                    h.get("sector"), now,
                ),
            )

    def get_latest_holdings(self):
        return self.db.execute(
            """SELECT * FROM portfolio_holdings
               WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM portfolio_holdings)
               ORDER BY market_value DESC"""
        )

    def insert_snapshot(self, total_equity: float, cash: float,
                        total_pl: float, total_pl_pct: float, num_positions: int):
        self.db.execute_insert(
            """INSERT INTO portfolio_snapshots
               (total_equity, cash, total_pl, total_pl_pct, num_positions)
               VALUES (?, ?, ?, ?, ?)""",
            (total_equity, cash, total_pl, total_pl_pct, num_positions),
        )
