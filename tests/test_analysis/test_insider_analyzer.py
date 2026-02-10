"""Tests for the insider trading analyzer."""

import pytest
from datetime import datetime, timedelta


class TestInsiderAnalyzer:
    @pytest.fixture
    def analyzer(self, test_db):
        from analysis.insider_analyzer import InsiderAnalyzer
        a = InsiderAnalyzer()
        a.insider_dao.db = test_db
        return a

    def test_no_data_returns_zero(self, analyzer):
        result = analyzer.analyze("NONEXIST")
        assert result.score == 0
        assert result.confidence <= 0.25

    def test_cluster_buying_bullish(self, analyzer, insider_trade_dao):
        """3+ insiders buying in 30 days should trigger cluster buying signal."""
        today = datetime.now().strftime("%Y-%m-%d")
        for i, name in enumerate(["CEO Alice", "CFO Bob", "COO Carol"]):
            insider_trade_dao.insert({
                "ticker": "AAPL",
                "filer_name": name,
                "filer_title": name.split()[0],
                "transaction_date": today,
                "transaction_type": "P",
                "shares": 5000,
                "price_per_share": 175.0,
                "total_value": 875000,
                "shares_owned_after": None,
            })
        analyzer.insider_dao = insider_trade_dao
        result = analyzer.analyze("AAPL")
        assert result.score > 15  # Cluster buying should give strong positive score
        assert any("cluster" in f.name.lower() or "cluster" in f.explanation.lower()
                    for f in result.factors)

    def test_executive_buying_bullish(self, analyzer, insider_trade_dao):
        """CEO/CFO buying should give positive signal."""
        today = datetime.now().strftime("%Y-%m-%d")
        insider_trade_dao.insert({
            "ticker": "AAPL",
            "filer_name": "Tim Cook",
            "filer_title": "Chief Executive Officer",
            "transaction_date": today,
            "transaction_type": "P",
            "shares": 10000,
            "price_per_share": 175.0,
            "total_value": 1750000,
            "shares_owned_after": 50000,
        })
        analyzer.insider_dao = insider_trade_dao
        result = analyzer.analyze("AAPL")
        assert result.score > 0

    def test_large_selling_bearish(self, analyzer, insider_trade_dao):
        """Large insider selling (>$1M) should give negative signal."""
        today = datetime.now().strftime("%Y-%m-%d")
        insider_trade_dao.insert({
            "ticker": "AAPL",
            "filer_name": "Big Seller",
            "filer_title": "Director",
            "transaction_date": today,
            "transaction_type": "S",
            "shares": 50000,
            "price_per_share": 175.0,
            "total_value": 8750000,
            "shares_owned_after": 10000,
        })
        analyzer.insider_dao = insider_trade_dao
        result = analyzer.analyze("AAPL")
        assert result.score < 0

    def test_score_bounded(self, analyzer, insider_trade_dao, sample_insider_trades):
        for trade in sample_insider_trades:
            insider_trade_dao.insert(trade)
        analyzer.insider_dao = insider_trade_dao
        result = analyzer.analyze("AAPL")
        assert -100 <= result.score <= 100
        assert 0.0 <= result.confidence <= 1.0

    def test_confidence_scales_with_data(self, analyzer, insider_trade_dao):
        """More trades should increase confidence."""
        today = datetime.now().strftime("%Y-%m-%d")
        # Insert many trades
        for i in range(12):
            insider_trade_dao.insert({
                "ticker": "AAPL",
                "filer_name": f"Insider {i}",
                "filer_title": "Officer",
                "transaction_date": today,
                "transaction_type": "P",
                "shares": 1000,
                "price_per_share": 175.0,
                "total_value": 175000,
                "shares_owned_after": None,
            })
        analyzer.insider_dao = insider_trade_dao
        result = analyzer.analyze("AAPL")
        assert result.confidence >= 0.6  # 10+ trades should give decent confidence
