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


class ComputedScoreDAO:
    """Data access for computed scoring models (Piotroski, Altman, Beneish, etc.)."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def insert(self, ticker: str, score_type: str, score_value: float, details: dict = None):
        self.db.execute_insert(
            """INSERT INTO computed_scores (ticker, score_type, score_value, details_json)
               VALUES (?, ?, ?, ?)""",
            (ticker, score_type, score_value,
             json.dumps(details, default=str) if details else None),
        )

    def get_latest(self, ticker: str, score_type: str):
        return self.db.execute_one(
            """SELECT * FROM computed_scores
               WHERE ticker = ? AND score_type = ?
               ORDER BY computed_at DESC LIMIT 1""",
            (ticker, score_type),
        )

    def get_all_latest(self, ticker: str):
        return self.db.execute(
            """SELECT cs.* FROM computed_scores cs
               INNER JOIN (
                   SELECT ticker, score_type, MAX(computed_at) as max_at
                   FROM computed_scores WHERE ticker = ?
                   GROUP BY ticker, score_type
               ) latest ON cs.ticker = latest.ticker
                   AND cs.score_type = latest.score_type
                   AND cs.computed_at = latest.max_at""",
            (ticker,),
        )


class DCFValuationDAO:
    """Data access for DCF valuation models."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def insert(self, ticker: str, valuation: dict):
        self.db.execute_insert(
            """INSERT INTO dcf_valuations
               (ticker, intrinsic_value, current_price, margin_of_safety,
                free_cash_flow, growth_rate, discount_rate, terminal_growth_rate,
                shares_outstanding, projection_years, inputs_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker,
                valuation.get("intrinsic_value"),
                valuation.get("current_price"),
                valuation.get("margin_of_safety"),
                valuation.get("free_cash_flow"),
                valuation.get("growth_rate"),
                valuation.get("discount_rate"),
                valuation.get("terminal_growth_rate"),
                valuation.get("shares_outstanding"),
                valuation.get("projection_years", 10),
                json.dumps(valuation.get("inputs", {}), default=str),
            ),
        )

    def get_latest(self, ticker: str):
        return self.db.execute_one(
            """SELECT * FROM dcf_valuations WHERE ticker = ?
               ORDER BY computed_at DESC LIMIT 1""",
            (ticker,),
        )


class InsiderTradeDAO:
    """Data access for insider trades."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def get_recent(self, ticker: str, days: int = 90):
        return self.db.execute(
            """SELECT * FROM insider_trades
               WHERE ticker = ? AND transaction_date >= date('now', ?)
               ORDER BY transaction_date DESC""",
            (ticker, f"-{days} days"),
        )

    def get_all_recent(self, ticker: str, days: int = 365):
        return self.db.execute(
            """SELECT * FROM insider_trades
               WHERE ticker = ? AND transaction_date >= date('now', ?)
               ORDER BY transaction_date DESC""",
            (ticker, f"-{days} days"),
        )


class HedgeFundHoldingDAO:
    """Data access for 13-F hedge fund holdings."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def get_for_ticker(self, ticker: str, limit: int = 50):
        return self.db.execute(
            """SELECT * FROM hedge_fund_holdings
               WHERE ticker = ?
               ORDER BY report_date DESC LIMIT ?""",
            (ticker, limit),
        )

    def get_latest_reports(self, ticker: str):
        """Get most recent 13-F reports mentioning this ticker."""
        return self.db.execute(
            """SELECT fund_name, fund_cik, shares, value, report_date
               FROM hedge_fund_holdings
               WHERE ticker = ? AND report_date = (
                   SELECT MAX(report_date) FROM hedge_fund_holdings WHERE ticker = ?
               )
               ORDER BY value DESC""",
            (ticker, ticker),
        )

    def get_historical(self, ticker: str):
        """Get historical holding snapshots to detect accumulation/distribution."""
        return self.db.execute(
            """SELECT report_date,
                      COUNT(DISTINCT fund_cik) as num_holders,
                      SUM(shares) as total_shares,
                      SUM(value) as total_value
               FROM hedge_fund_holdings
               WHERE ticker = ?
               GROUP BY report_date
               ORDER BY report_date DESC
               LIMIT 8""",
            (ticker,),
        )


class RiskSimulationDAO:
    """Data access for risk simulation results."""

    def __init__(self, db=None):
        self.db = db or get_connection()

    def insert(self, simulation: dict):
        self.db.execute_insert(
            """INSERT INTO risk_simulations
               (simulation_type, portfolio_value, var_95, var_99, cvar_95,
                monte_carlo_json, parameters_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                simulation["simulation_type"],
                simulation.get("portfolio_value"),
                simulation.get("var_95"),
                simulation.get("var_99"),
                simulation.get("cvar_95"),
                json.dumps(simulation.get("monte_carlo"), default=str) if simulation.get("monte_carlo") else None,
                json.dumps(simulation.get("parameters"), default=str) if simulation.get("parameters") else None,
            ),
        )

    def get_latest(self, simulation_type: str = None):
        if simulation_type:
            return self.db.execute_one(
                """SELECT * FROM risk_simulations
                   WHERE simulation_type = ?
                   ORDER BY computed_at DESC LIMIT 1""",
                (simulation_type,),
            )
        return self.db.execute(
            "SELECT * FROM risk_simulations ORDER BY computed_at DESC LIMIT 10"
        )
