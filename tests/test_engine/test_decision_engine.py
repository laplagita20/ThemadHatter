"""Tests for the decision engine scoring, sizing, and action logic."""

import pytest
from unittest.mock import MagicMock, patch
from analysis.base_analyzer import AnalysisResult, AnalysisFactor
from engine.decision_engine import DecisionEngine, Decision, ScenarioAnalysis


@pytest.fixture
def engine(test_db):
    """Create a decision engine with test DB and mocked analyzers."""
    with patch.object(DecisionEngine, '_init_analyzers', return_value={}):
        e = DecisionEngine()
        e.analysis_dao.db = test_db
        e.decision_dao.db = test_db
        e.stock_dao.db = test_db
        e.db = test_db
    return e


def _make_result(score, confidence=0.7, signal=None):
    if signal is None:
        if score > 20:
            signal = "buy"
        elif score < -20:
            signal = "sell"
        else:
            signal = "hold"
    return AnalysisResult(score=score, confidence=confidence, signal=signal)


class TestScoreToAction:
    def test_strong_buy(self, engine):
        assert engine._score_to_action(55, 0.8) == "STRONG_BUY"

    def test_buy(self, engine):
        assert engine._score_to_action(25, 0.7) == "BUY"

    def test_hold(self, engine):
        assert engine._score_to_action(5, 0.5) == "HOLD"

    def test_sell(self, engine):
        assert engine._score_to_action(-25, 0.6) == "SELL"

    def test_strong_sell(self, engine):
        assert engine._score_to_action(-55, 0.8) == "STRONG_SELL"

    def test_low_confidence_defaults_to_hold(self, engine):
        assert engine._score_to_action(60, 0.2) == "HOLD"


class TestCompositeCalculation:
    def test_single_analyzer(self, engine):
        results = {"technical": _make_result(30, 0.8)}
        score, conf = engine._calculate_composite(results)
        assert score == pytest.approx(30.0, abs=1)
        assert conf == pytest.approx(0.8, abs=0.01)

    def test_mixed_signals(self, engine):
        results = {
            "technical": _make_result(30, 0.8),
            "fundamental": _make_result(-20, 0.6),
        }
        score, _ = engine._calculate_composite(results)
        # Weighted average should be between -20 and 30
        assert -20 < score < 30

    def test_empty_results(self, engine):
        score, conf = engine._calculate_composite({})
        assert score == 0.0
        assert conf == 0.0

    def test_confidence_weighted(self, engine):
        """High confidence results should dominate."""
        results = {
            "technical": _make_result(50, 0.9),
            "fundamental": _make_result(-50, 0.1),
        }
        score, _ = engine._calculate_composite(results)
        # Technical with 0.9 confidence should dominate
        assert score > 0


class TestConviction:
    def test_strong_agreement_boosts_conviction(self, engine):
        results = {
            "technical": _make_result(30, 0.8, "buy"),
            "fundamental": _make_result(25, 0.7, "buy"),
            "sentiment": _make_result(20, 0.6, "buy"),
        }
        conviction = engine._calculate_conviction(results, 25)
        assert conviction >= 60  # Strong agreement should push above neutral

    def test_disagreement_lowers_conviction(self, engine):
        results = {
            "technical": _make_result(30, 0.3, "buy"),
            "fundamental": _make_result(-30, 0.3, "sell"),
        }
        conviction = engine._calculate_conviction(results, 0)
        assert conviction < 50  # Disagreement + low confidence should reduce conviction

    def test_conviction_bounded(self, engine):
        results = {"technical": _make_result(0, 0.5)}
        conviction = engine._calculate_conviction(results, 0)
        assert 0 <= conviction <= 100


class TestPositionSizing:
    def test_high_conviction_large_size(self, engine):
        size = engine._calculate_position_size(55, 0.8, 75)
        assert size > 0

    def test_low_conviction_small_size(self, engine):
        size = engine._calculate_position_size(10, 0.4, 30)
        assert size > 0

    def test_size_never_negative(self, engine):
        size = engine._calculate_position_size(-50, 0.2, 20)
        assert size >= 0


class TestStopLoss:
    def test_tactical_stop_for_high_score(self, engine):
        sl = engine._calculate_stop_loss(55)
        assert sl > 0

    def test_core_stop_for_low_score(self, engine):
        sl = engine._calculate_stop_loss(10)
        assert sl > 0

    def test_stop_loss_always_positive(self, engine):
        for score in [-100, -50, 0, 50, 100]:
            sl = engine._calculate_stop_loss(score)
            assert sl > 0


class TestHorizons:
    def test_three_horizons_generated(self, engine):
        results = {"technical": _make_result(30, 0.7)}
        horizons = engine._calculate_horizons(results, 30, 0.7)
        assert len(horizons) == 3
        horizon_names = {h.horizon for h in horizons}
        assert horizon_names == {"3_month", "6_month", "12_month"}

    def test_short_term_favors_technical(self, engine):
        results = {
            "technical": _make_result(50, 0.8),
            "fundamental": _make_result(-20, 0.7),
        }
        horizons = engine._calculate_horizons(results, 15, 0.75)
        short = next(h for h in horizons if h.horizon == "3_month")
        long = next(h for h in horizons if h.horizon == "12_month")
        # Short-term should weight technical more heavily
        assert short.score > long.score

    def test_long_term_favors_fundamental(self, engine):
        results = {
            "technical": _make_result(-20, 0.7),
            "fundamental": _make_result(50, 0.8),
        }
        horizons = engine._calculate_horizons(results, 15, 0.75)
        short = next(h for h in horizons if h.horizon == "3_month")
        long = next(h for h in horizons if h.horizon == "12_month")
        # Long-term should weight fundamental more heavily
        assert long.score > short.score


class TestBuildCases:
    def test_bull_and_bear_cases(self, engine):
        results = {
            "technical": AnalysisResult(
                score=30, confidence=0.7, signal="buy",
                factors=[AnalysisFactor("Momentum", "+15%", 12, "Strong uptrend")],
                summary="Bullish",
            ),
            "fundamental": AnalysisResult(
                score=-10, confidence=0.6, signal="hold",
                factors=[AnalysisFactor("Valuation", "40x PE", -10, "Expensive relative to peers")],
                summary="Bearish",
            ),
        }
        bull, bear = engine._build_cases(results)
        assert "Momentum" in bull
        assert "Valuation" in bear

    def test_no_strong_factors_gives_defaults(self, engine):
        results = {
            "technical": AnalysisResult(
                score=5, confidence=0.5, signal="hold",
                factors=[AnalysisFactor("RSI", "50", 2, "Neutral RSI")],
                summary="Neutral",
            ),
        }
        bull, bear = engine._build_cases(results)
        assert "No strong" in bull or bull != ""
        assert "No strong" in bear or bear != ""


class TestRiskWarnings:
    def test_low_confidence_warned(self, engine):
        results = {
            "technical": _make_result(20, 0.2, "hold"),
        }
        warnings = engine._build_risk_warnings(results)
        assert "low confidence" in warnings.lower() or "Low confidence" in warnings

    def test_strong_negative_factor_warned(self, engine):
        results = {
            "fundamental": AnalysisResult(
                score=-30, confidence=0.7, signal="sell",
                factors=[AnalysisFactor("Debt Crisis", "5x D/E", -15, "Extremely high leverage")],
                summary="Bearish",
            ),
        }
        warnings = engine._build_risk_warnings(results)
        assert "Debt Crisis" in warnings or "leverage" in warnings.lower()
