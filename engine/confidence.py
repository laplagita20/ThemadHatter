"""Confidence breakdown and reasoning chain for decisions."""

import logging
from analysis.base_analyzer import AnalysisResult

logger = logging.getLogger("stock_model.engine.confidence")


class ConfidenceAnalyzer:
    """Analyzes and explains the confidence level of a decision."""

    def explain_confidence(self, results: dict[str, AnalysisResult],
                           composite_score: float) -> dict:
        """Break down what drives confidence up or down."""
        boosters = []
        reducers = []

        # Check analyzer agreement
        signals = [r.signal for r in results.values()]
        bullish_count = sum(1 for s in signals if s in ("buy", "strong_buy"))
        bearish_count = sum(1 for s in signals if s in ("sell", "strong_sell"))
        total = len(signals)

        if total > 0:
            agreement = max(bullish_count, bearish_count) / total
            if agreement >= 0.8:
                boosters.append(f"High analyzer agreement ({agreement:.0%} aligned)")
            elif agreement <= 0.4:
                reducers.append(f"Low analyzer agreement (mixed signals)")

        # Check individual confidences
        low_conf = [name for name, r in results.items() if r.confidence < 0.4]
        high_conf = [name for name, r in results.items() if r.confidence > 0.8]

        if high_conf:
            boosters.append(f"High confidence in: {', '.join(high_conf)}")
        if low_conf:
            reducers.append(f"Low confidence in: {', '.join(low_conf)}")

        # Score magnitude
        if abs(composite_score) > 50:
            boosters.append(f"Strong composite score ({composite_score:+.0f})")
        elif abs(composite_score) < 15:
            reducers.append(f"Weak composite score ({composite_score:+.0f})")

        # Data coverage
        if len(results) >= 4:
            boosters.append(f"Broad coverage ({len(results)} analyzers)")
        elif len(results) <= 2:
            reducers.append(f"Limited coverage (only {len(results)} analyzers)")

        return {
            "boosters": boosters,
            "reducers": reducers,
            "summary": self._summarize(boosters, reducers),
        }

    def _summarize(self, boosters: list[str], reducers: list[str]) -> str:
        net = len(boosters) - len(reducers)
        if net >= 2:
            return "Confidence is well-supported by multiple factors"
        elif net <= -2:
            return "Confidence is undermined by several concerns"
        return "Confidence is moderate with both supporting and limiting factors"
