"""Tests for the fundamental analyzer."""

import pytest


class TestFundamentalAnalyzer:
    @pytest.fixture
    def analyzer(self, test_db):
        from analysis.fundamental import FundamentalAnalyzer
        return FundamentalAnalyzer()

    def test_no_data_returns_low_confidence(self, analyzer):
        result = analyzer.analyze("NONEXIST")
        assert result.confidence <= 0.3

    def test_with_fundamentals(self, analyzer, fundamentals_dao, sample_fundamentals):
        fundamentals_dao.insert("AAPL", sample_fundamentals)
        result = analyzer.analyze("AAPL")
        assert -100 <= result.score <= 100
        assert result.confidence > 0.3

    def test_score_bounded(self, analyzer, fundamentals_dao, sample_fundamentals):
        fundamentals_dao.insert("AAPL", sample_fundamentals)
        result = analyzer.analyze("AAPL")
        assert -100 <= result.score <= 100
        assert 0.0 <= result.confidence <= 1.0

    def test_has_factors_with_data(self, analyzer, fundamentals_dao, sample_fundamentals):
        fundamentals_dao.insert("AAPL", sample_fundamentals)
        result = analyzer.analyze("AAPL")
        assert len(result.factors) > 0
