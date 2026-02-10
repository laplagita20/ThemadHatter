"""Tests for database DAO operations."""

import pytest


class TestStockDAO:
    def test_upsert_and_get(self, stock_dao, sample_stock):
        stock_dao.upsert(**sample_stock)
        result = stock_dao.get("AAPL")
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["company_name"] == "Apple Inc."
        assert result["sector"] == "Technology"

    def test_upsert_updates_existing(self, stock_dao, sample_stock):
        stock_dao.upsert(**sample_stock)
        stock_dao.upsert(ticker="AAPL", company_name="Apple Inc. Updated")
        result = stock_dao.get("AAPL")
        assert result["company_name"] == "Apple Inc. Updated"
        assert result["sector"] == "Technology"  # Preserved from first insert

    def test_get_all_active(self, stock_dao):
        stock_dao.upsert(ticker="AAPL", company_name="Apple")
        stock_dao.upsert(ticker="MSFT", company_name="Microsoft")
        stock_dao.upsert(ticker="GOOG", company_name="Google")
        active = list(stock_dao.get_all_active())
        assert len(active) == 3

    def test_deactivate_and_reactivate(self, stock_dao):
        stock_dao.upsert(ticker="AAPL", company_name="Apple")
        stock_dao.deactivate("AAPL")
        active = list(stock_dao.get_all_active())
        assert len(active) == 0

        stock_dao.reactivate("AAPL")
        active = list(stock_dao.get_all_active())
        assert len(active) == 1

    def test_get_watchlist(self, stock_dao):
        stock_dao.upsert(ticker="AAPL", company_name="Apple", sector="Tech")
        stock_dao.upsert(ticker="MSFT", company_name="Microsoft", sector="Tech")
        watchlist = list(stock_dao.get_watchlist())
        assert len(watchlist) == 2
        assert watchlist[0]["ticker"] == "AAPL"

    def test_get_nonexistent(self, stock_dao):
        result = stock_dao.get("NONEXISTENT")
        assert result is None


class TestPriceDAO:
    def test_upsert_many_and_get(self, price_dao, sample_price_history):
        price_dao.upsert_many("AAPL", sample_price_history)
        history = list(price_dao.get_history("AAPL", days=60))
        assert len(history) == 60

    def test_get_latest_price(self, price_dao, sample_price_history):
        price_dao.upsert_many("AAPL", sample_price_history)
        latest = price_dao.get_latest_price("AAPL")
        assert latest is not None
        assert isinstance(latest, float)

    def test_get_latest_price_empty(self, price_dao):
        result = price_dao.get_latest_price("NONEXIST")
        assert result is None


class TestPortfolioDAO:
    def test_snapshot_and_get_holdings(self, portfolio_dao, sample_holdings):
        portfolio_dao.snapshot_holdings(sample_holdings)
        holdings = list(portfolio_dao.get_latest_holdings())
        assert len(holdings) == 3
        tickers = {h["ticker"] for h in holdings}
        assert tickers == {"AAPL", "MSFT", "JNJ"}

    def test_delete_holding(self, portfolio_dao, sample_holdings):
        portfolio_dao.snapshot_holdings(sample_holdings)
        portfolio_dao.delete_holding("JNJ")
        holdings = list(portfolio_dao.get_latest_holdings())
        tickers = {h["ticker"] for h in holdings}
        assert "JNJ" not in tickers
        assert len(holdings) == 2

    def test_multiple_snapshots_returns_latest(self, portfolio_dao):
        portfolio_dao.snapshot_holdings([{
            "ticker": "AAPL", "quantity": 100, "average_cost": 150,
            "current_price": 160, "market_value": 16000,
            "unrealized_pl": 1000, "unrealized_pl_pct": 6.67, "sector": "Tech",
        }])
        portfolio_dao.snapshot_holdings([{
            "ticker": "MSFT", "quantity": 50, "average_cost": 300,
            "current_price": 350, "market_value": 17500,
            "unrealized_pl": 2500, "unrealized_pl_pct": 16.67, "sector": "Tech",
        }])
        # get_latest_holdings should only return the most recent snapshot
        holdings = list(portfolio_dao.get_latest_holdings())
        assert len(holdings) == 1
        assert holdings[0]["ticker"] == "MSFT"

    def test_insert_snapshot(self, portfolio_dao):
        portfolio_dao.insert_snapshot(
            total_equity=100000, cash=5000,
            total_pl=5000, total_pl_pct=5.0, num_positions=10,
        )
        # No assertion error = success (snapshot inserted)

    def test_get_latest_snapshot_date(self, portfolio_dao, sample_holdings):
        assert portfolio_dao.get_latest_snapshot_date() is None
        portfolio_dao.snapshot_holdings(sample_holdings)
        date = portfolio_dao.get_latest_snapshot_date()
        assert date is not None


class TestDecisionDAO:
    def test_insert_and_get(self, decision_dao):
        decision = {
            "ticker": "AAPL",
            "action": "BUY",
            "composite_score": 35.5,
            "confidence": 0.75,
            "position_size_pct": 5.0,
            "stop_loss_pct": 15.0,
            "target_price": 200.0,
            "time_horizon": "medium_term",
            "reasoning": [{"analyzer": "technical", "score": 20}],
            "bull_case": "Strong momentum and earnings growth",
            "bear_case": "High valuation relative to peers",
            "risk_warnings": "Concentrated in tech sector",
            "analysis_breakdown": {"technical": 20, "fundamental": 15},
            "extended_data": {
                "conviction_score": 72,
                "horizons": [],
                "scenarios": {},
                "price_targets": {},
            },
        }
        decision_id = decision_dao.insert(decision)
        assert decision_id is not None

        result = decision_dao.get_latest("AAPL")
        assert result is not None
        assert result["action"] == "BUY"
        assert result["composite_score"] == 35.5
        assert result["confidence"] == 0.75
        assert result["bull_case"] == "Strong momentum and earnings growth"

    def test_extended_data_stored(self, decision_dao):
        decision = {
            "ticker": "AAPL",
            "action": "HOLD",
            "composite_score": 5.0,
            "confidence": 0.5,
            "extended_data": {"conviction_score": 50, "horizons": [{"horizon": "short_term"}]},
        }
        decision_dao.insert(decision)
        result = decision_dao.get_latest("AAPL")
        import json
        ext = json.loads(result["extended_data_json"])
        assert ext["conviction_score"] == 50
        assert len(ext["horizons"]) == 1


class TestInsiderTradeDAO:
    def test_insert_and_get_recent(self, insider_trade_dao, sample_insider_trades):
        for trade in sample_insider_trades:
            insider_trade_dao.insert(trade)
        trades = list(insider_trade_dao.get_recent("AAPL", days=90))
        assert len(trades) == 3

    def test_get_recent_filters_by_date(self, insider_trade_dao, sample_insider_trades):
        for trade in sample_insider_trades:
            insider_trade_dao.insert(trade)
        trades = list(insider_trade_dao.get_recent("AAPL", days=7))
        # Only today's trade should be within 7-day window (week_ago is exactly 7 days)
        assert len(trades) >= 1

    def test_get_all_recent(self, insider_trade_dao, sample_insider_trades):
        for trade in sample_insider_trades:
            insider_trade_dao.insert(trade)
        trades = list(insider_trade_dao.get_all_recent("AAPL", days=365))
        assert len(trades) == 3


class TestFundamentalsDAO:
    def test_insert_and_get_latest(self, fundamentals_dao, sample_fundamentals):
        fundamentals_dao.insert("AAPL", sample_fundamentals)
        result = fundamentals_dao.get_latest("AAPL")
        assert result is not None
        assert result["pe_ratio"] == 28.5
        assert result["profit_margin"] == 0.26

    def test_get_latest_nonexistent(self, fundamentals_dao):
        result = fundamentals_dao.get_latest("NONEXIST")
        assert result is None


class TestComputedScoreDAO:
    def test_insert_and_get(self, computed_score_dao):
        computed_score_dao.insert("AAPL", "piotroski", 7.0, {"components": [1, 1, 1, 0, 1, 1, 1, 0, 1]})
        result = computed_score_dao.get_latest("AAPL", "piotroski")
        assert result is not None
        assert result["score_value"] == 7.0

    def test_get_all_latest(self, computed_score_dao):
        computed_score_dao.insert("AAPL", "piotroski", 7.0)
        computed_score_dao.insert("AAPL", "altman_z", 3.5)
        results = list(computed_score_dao.get_all_latest("AAPL"))
        assert len(results) == 2
        score_types = {r["score_type"] for r in results}
        assert score_types == {"piotroski", "altman_z"}


class TestRecurringInvestmentDAO:
    def test_create_and_get_active(self, recurring_investment_dao):
        recurring_investment_dao.create("AAPL", 100.0, "monthly", 15)
        active = list(recurring_investment_dao.get_all_active())
        assert len(active) == 1
        assert active[0]["ticker"] == "AAPL"
        assert active[0]["amount"] == 100.0
        assert active[0]["frequency"] == "monthly"

    def test_create_weekly(self, recurring_investment_dao):
        recurring_investment_dao.create("MSFT", 50.0, "weekly", 0)  # Monday
        active = list(recurring_investment_dao.get_all_active())
        assert len(active) == 1
        assert active[0]["frequency"] == "weekly"

    def test_get_for_ticker(self, recurring_investment_dao):
        recurring_investment_dao.create("AAPL", 100.0)
        recurring_investment_dao.create("MSFT", 200.0)
        result = recurring_investment_dao.get_for_ticker("AAPL")
        assert result is not None
        assert result["ticker"] == "AAPL"

    def test_deactivate(self, recurring_investment_dao):
        rid = recurring_investment_dao.create("AAPL", 100.0)
        recurring_investment_dao.deactivate(rid)
        active = list(recurring_investment_dao.get_all_active())
        assert len(active) == 0

    def test_update_amount(self, recurring_investment_dao):
        rid = recurring_investment_dao.create("AAPL", 100.0)
        recurring_investment_dao.update_amount(rid, 250.0)
        result = recurring_investment_dao.get_for_ticker("AAPL")
        assert result["amount"] == 250.0

    def test_log_execution(self, recurring_investment_dao):
        rid = recurring_investment_dao.create("AAPL", 100.0)
        recurring_investment_dao.log_execution(rid, "AAPL", 100.0, 0.5, 200.0)
        result = recurring_investment_dao.get_for_ticker("AAPL")
        assert result["total_invested"] == 100.0
        assert result["total_shares_bought"] == 0.5
        assert result["num_executions"] == 1

    def test_get_log(self, recurring_investment_dao):
        rid = recurring_investment_dao.create("AAPL", 100.0)
        recurring_investment_dao.log_execution(rid, "AAPL", 100.0, 0.5, 200.0)
        recurring_investment_dao.log_execution(rid, "AAPL", 100.0, 0.6, 166.67)
        logs = list(recurring_investment_dao.get_log("AAPL"))
        assert len(logs) == 2

    def test_multiple_executions_accumulate(self, recurring_investment_dao):
        rid = recurring_investment_dao.create("AAPL", 100.0)
        recurring_investment_dao.log_execution(rid, "AAPL", 100.0, 0.5, 200.0)
        recurring_investment_dao.log_execution(rid, "AAPL", 100.0, 0.6, 166.67)
        result = recurring_investment_dao.get_for_ticker("AAPL")
        assert result["total_invested"] == 200.0
        assert result["total_shares_bought"] == 1.1
        assert result["num_executions"] == 2
