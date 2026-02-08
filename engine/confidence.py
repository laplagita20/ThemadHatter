"""Confidence breakdown, conviction scoring, and reasoning chain for decisions."""

import logging
from analysis.base_analyzer import AnalysisResult
from database.connection import get_connection

logger = logging.getLogger("stock_model.engine.confidence")


class ConfidenceAnalyzer:
    """Analyzes and explains the confidence and conviction level of a decision."""

    def __init__(self):
        self.db = get_connection()

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
                reducers.append("Low analyzer agreement (mixed signals)")

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
        if len(results) >= 7:
            boosters.append(f"Excellent coverage ({len(results)} analyzers)")
        elif len(results) >= 4:
            boosters.append(f"Broad coverage ({len(results)} analyzers)")
        elif len(results) <= 2:
            reducers.append(f"Limited coverage (only {len(results)} analyzers)")

        # Professional scoring models present
        scoring_models = []
        for r in results.values():
            for f in r.factors:
                if f.name in ("Piotroski F-Score", "Altman Z-Score", "Beneish M-Score",
                              "DCF Intrinsic Value", "DuPont Analysis", "Owner Earnings"):
                    scoring_models.append(f.name)
        if len(scoring_models) >= 3:
            boosters.append(f"Professional models active: {', '.join(scoring_models[:3])}")
        elif len(scoring_models) >= 1:
            boosters.append(f"Scoring models: {', '.join(scoring_models)}")

        # Check for critical risk flags
        critical_risks = []
        for r in results.values():
            for f in r.factors:
                if f.impact <= -20:
                    critical_risks.append(f.name)
        if critical_risks:
            reducers.append(f"Critical risk flags: {', '.join(critical_risks[:3])}")

        # Historical accuracy context
        try:
            accuracy = self.db.execute_one(
                """SELECT
                     COUNT(*) as total,
                     SUM(CASE WHEN action_was_correct = 1 THEN 1 ELSE 0 END) as correct
                   FROM decision_outcomes
                   WHERE action_was_correct IS NOT NULL"""
            )
            if accuracy and accuracy["total"] and accuracy["total"] >= 10:
                acc_rate = accuracy["correct"] / accuracy["total"]
                if acc_rate > 0.65:
                    boosters.append(f"Historical accuracy: {acc_rate:.0%} ({accuracy['total']} decisions)")
                elif acc_rate < 0.45:
                    reducers.append(f"Historical accuracy only {acc_rate:.0%} ({accuracy['total']} decisions)")
        except Exception:
            pass

        return {
            "boosters": boosters,
            "reducers": reducers,
            "net_conviction": len(boosters) - len(reducers),
            "summary": self._summarize(boosters, reducers),
        }

    def _summarize(self, boosters: list[str], reducers: list[str]) -> str:
        net = len(boosters) - len(reducers)
        if net >= 3:
            return "Confidence is strongly supported by multiple factors"
        elif net >= 2:
            return "Confidence is well-supported by multiple factors"
        elif net <= -2:
            return "Confidence is undermined by several concerns"
        return "Confidence is moderate with both supporting and limiting factors"
