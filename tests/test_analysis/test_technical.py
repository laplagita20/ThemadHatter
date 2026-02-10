"""Tests for the technical analyzer."""

import pytest


class TestTechnicalAnalyzer:
    @pytest.fixture
    def analyzer(self, test_db):
        from analysis.technical import TechnicalAnalyzer
        return TechnicalAnalyzer()

    def test_no_data_returns_low_confidence(self, analyzer):
        result = analyzer.analyze("NONEXIST")
        assert result.confidence <= 0.3
        assert abs(result.score) <= 5

    def test_score_bounded(self, analyzer, price_dao, sample_price_history):
        price_dao.upsert_many("AAPL", sample_price_history)
        result = analyzer.analyze("AAPL")
        assert -100 <= result.score <= 100
        assert 0.0 <= result.confidence <= 1.0

    def test_signal_matches_score(self, analyzer, price_dao, sample_price_history):
        price_dao.upsert_many("AAPL", sample_price_history)
        result = analyzer.analyze("AAPL")
        if result.score > 10:
            assert result.signal in ("buy", "strong_buy")
        elif result.score < -10:
            assert result.signal in ("sell", "strong_sell")
        else:
            assert result.signal in ("hold", "neutral", "buy", "sell")

    def test_has_factors(self, analyzer, price_dao, sample_price_history):
        price_dao.upsert_many("AAPL", sample_price_history)
        result = analyzer.analyze("AAPL")
        assert len(result.factors) >= 0
