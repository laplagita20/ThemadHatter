"""Decision engine: combines all analyzer scores into a justified recommendation."""

import logging
import json
from dataclasses import dataclass, field

from config.settings import get_settings
from analysis.technical import TechnicalAnalyzer
from analysis.fundamental import FundamentalAnalyzer
from analysis.base_analyzer import AnalysisResult
from database.models import AnalysisResultDAO, DecisionDAO, StockDAO
from utils.console import header, separator, ok, fail, neutral
from utils.helpers import format_pct, score_to_signal

logger = logging.getLogger("stock_model.engine")


@dataclass
class Decision:
    ticker: str
    action: str  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    composite_score: float
    confidence: float
    position_size_pct: float = 0.0
    stop_loss_pct: float = 15.0
    target_price: float | None = None
    time_horizon: str = "medium_term"
    reasoning: list[str] = field(default_factory=list)
    bull_case: str = ""
    bear_case: str = ""
    risk_warnings: str = ""
    analysis_breakdown: dict = field(default_factory=dict)


class DecisionEngine:
    """Combines all analysis scores into a single decision with reasoning."""

    def __init__(self):
        self.settings = get_settings()
        self.weights = dict(self.settings.analysis_weights)
        self.analyzers = self._init_analyzers()
        self.analysis_dao = AnalysisResultDAO()
        self.decision_dao = DecisionDAO()
        self.stock_dao = StockDAO()

    def _init_analyzers(self) -> dict:
        """Initialize available analyzers."""
        analyzers = {
            "technical": TechnicalAnalyzer(),
            "fundamental": FundamentalAnalyzer(),
        }

        # Try to load optional analyzers (available after later phases)
        try:
            from analysis.macroeconomic import MacroeconomicAnalyzer
            analyzers["macroeconomic"] = MacroeconomicAnalyzer()
        except ImportError:
            pass

        try:
            from analysis.sentiment import SentimentAnalyzer
            analyzers["sentiment"] = SentimentAnalyzer()
        except ImportError:
            pass

        try:
            from analysis.geopolitical import GeopoliticalAnalyzer
            analyzers["geopolitical"] = GeopoliticalAnalyzer()
        except ImportError:
            pass

        try:
            from analysis.sector import SectorAnalyzer
            analyzers["sector"] = SectorAnalyzer()
        except ImportError:
            pass

        return analyzers

    def analyze(self, ticker: str) -> Decision:
        """Run all available analyzers and produce a decision."""
        logger.info("Running full analysis for %s", ticker)

        # Ensure stock is in watchlist
        self.stock_dao.upsert(ticker=ticker)

        # Run each analyzer
        results: dict[str, AnalysisResult] = {}
        for name, analyzer in self.analyzers.items():
            try:
                result = analyzer.analyze(ticker)
                results[name] = result
                # Store result
                self.analysis_dao.insert(
                    ticker=ticker,
                    analyzer_name=name,
                    score=result.score,
                    confidence=result.confidence,
                    signal=result.signal,
                    factors=[f.__dict__ if hasattr(f, '__dict__') else f for f in result.factors],
                    summary=result.summary,
                )
            except Exception as e:
                logger.error("Analyzer %s failed for %s: %s", name, ticker, e, exc_info=True)

        if not results:
            return Decision(
                ticker=ticker, action="HOLD", composite_score=0,
                confidence=0, reasoning=["No analyzers produced results"])

        # Calculate confidence-adjusted weighted score
        composite_score, confidence = self._calculate_composite(results)

        # Determine action
        action = self._score_to_action(composite_score, confidence)

        # Build reasoning
        reasoning = self._build_reasoning(results, action)
        bull_case, bear_case = self._build_cases(results)
        risk_warnings = self._build_risk_warnings(results)

        # Position sizing
        position_size = self._calculate_position_size(composite_score, confidence)
        stop_loss = self._calculate_stop_loss(composite_score)

        decision = Decision(
            ticker=ticker,
            action=action,
            composite_score=composite_score,
            confidence=confidence,
            position_size_pct=position_size,
            stop_loss_pct=stop_loss,
            time_horizon=self._determine_horizon(results),
            reasoning=reasoning,
            bull_case=bull_case,
            bear_case=bear_case,
            risk_warnings=risk_warnings,
            analysis_breakdown={
                name: result.to_dict() for name, result in results.items()
            },
        )

        # Store decision
        self.decision_dao.insert({
            "ticker": ticker,
            "action": action,
            "composite_score": composite_score,
            "confidence": confidence,
            "position_size_pct": position_size,
            "stop_loss_pct": stop_loss,
            "time_horizon": decision.time_horizon,
            "reasoning": reasoning,
            "bull_case": bull_case,
            "bear_case": bear_case,
            "risk_warnings": risk_warnings,
            "analysis_breakdown": decision.analysis_breakdown,
        })

        return decision

    def _calculate_composite(self, results: dict[str, AnalysisResult]) -> tuple[float, float]:
        """Calculate confidence-adjusted weighted composite score."""
        weighted_sum = 0.0
        weight_total = 0.0

        for name, result in results.items():
            weight = self.weights.get(name, 0.05)
            adjusted_weight = weight * result.confidence
            weighted_sum += result.score * adjusted_weight
            weight_total += adjusted_weight

        if weight_total == 0:
            return 0.0, 0.0

        composite = weighted_sum / weight_total
        avg_confidence = sum(r.confidence for r in results.values()) / len(results)

        return round(composite, 2), round(avg_confidence, 3)

    def _score_to_action(self, score: float, confidence: float) -> str:
        """Convert score + confidence to an action."""
        if confidence < 0.3:
            return "HOLD"  # Low confidence = no action

        if score >= 50:
            return "STRONG_BUY"
        elif score >= 20:
            return "BUY"
        elif score <= -50:
            return "STRONG_SELL"
        elif score <= -20:
            return "SELL"
        return "HOLD"

    def _build_reasoning(self, results: dict[str, AnalysisResult], action: str) -> list[str]:
        """Build ordered list of key reasons for the decision."""
        reasons = []

        # Sort analyzers by absolute score impact
        sorted_results = sorted(
            results.items(),
            key=lambda x: abs(x[1].score * self.weights.get(x[0], 0.05)),
            reverse=True,
        )

        for name, result in sorted_results:
            direction = "bullish" if result.score > 0 else "bearish" if result.score < 0 else "neutral"
            weight_pct = self.weights.get(name, 0.05) * 100
            reasons.append(
                f"{name.title()} ({direction}, score: {result.score:+.0f}, "
                f"confidence: {result.confidence:.0%}, weight: {weight_pct:.0f}%): "
                f"{result.summary.split(chr(10))[0]}"
            )

        return reasons

    def _build_cases(self, results: dict[str, AnalysisResult]) -> tuple[str, str]:
        """Build bull and bear cases from analysis factors."""
        bull_factors = []
        bear_factors = []

        for result in results.values():
            for f in result.factors:
                if f.impact >= 8:
                    bull_factors.append(f"{f.name}: {f.explanation}")
                elif f.impact <= -8:
                    bear_factors.append(f"{f.name}: {f.explanation}")

        bull = "; ".join(bull_factors[:5]) if bull_factors else "No strong bullish factors identified"
        bear = "; ".join(bear_factors[:5]) if bear_factors else "No strong bearish factors identified"
        return bull, bear

    def _build_risk_warnings(self, results: dict[str, AnalysisResult]) -> str:
        """Identify key risk warnings."""
        warnings = []

        for name, result in results.items():
            if result.confidence < 0.4:
                warnings.append(f"Low confidence in {name} analysis ({result.confidence:.0%})")
            for f in result.factors:
                if f.impact <= -12:
                    warnings.append(f"{f.name}: {f.explanation}")

        return "; ".join(warnings[:5]) if warnings else "No significant risk warnings"

    def _calculate_position_size(self, score: float, confidence: float) -> float:
        """Determine position size based on conviction."""
        s = self.settings
        if abs(score) >= 50 and confidence >= 0.7:
            return s.position_size_high_conviction
        elif abs(score) >= 20 and confidence >= 0.5:
            return s.position_size_medium_conviction
        return s.position_size_low_conviction

    def _calculate_stop_loss(self, score: float) -> float:
        """Determine stop-loss percentage."""
        s = self.settings
        if abs(score) >= 50:
            return s.trailing_stop_tactical_pct  # Tighter stop for high conviction
        return s.trailing_stop_core_pct

    def _determine_horizon(self, results: dict[str, AnalysisResult]) -> str:
        """Determine recommended time horizon."""
        tech_score = results.get("technical", AnalysisResult(0, 0, "hold")).score
        fund_score = results.get("fundamental", AnalysisResult(0, 0, "hold")).score

        if abs(tech_score) > abs(fund_score):
            return "short_term"  # Technical-driven
        return "medium_term"  # Fundamental-driven

    def print_decision(self, d: Decision):
        """Print a formatted decision report."""
        print(header(f"ANALYSIS REPORT: {d.ticker}"))

        # Action with color hint
        action_symbols = {
            "STRONG_BUY": ok, "BUY": ok, "HOLD": neutral,
            "SELL": fail, "STRONG_SELL": fail,
        }
        symbol_fn = action_symbols.get(d.action, neutral)
        print(f"\n  RECOMMENDATION: {symbol_fn(d.action)}")
        print(f"  Composite Score: {d.composite_score:+.1f}/100")
        print(f"  Confidence: {d.confidence:.0%}")
        print(f"  Position Size: {d.position_size_pct:.1f}% of portfolio")
        print(f"  Stop-Loss: {d.stop_loss_pct:.1f}%")
        print(f"  Time Horizon: {d.time_horizon.replace('_', ' ').title()}")

        # Analysis breakdown
        print(f"\n{separator()}")
        print("  ANALYSIS BREAKDOWN:")
        for name, data in d.analysis_breakdown.items():
            score = data["score"]
            conf = data["confidence"]
            signal = data["signal"]
            fn = ok if score > 0 else fail if score < 0 else neutral
            print(f"    {fn(f'{name.title():<16} Score: {score:>+6.1f}  Confidence: {conf:.0%}  Signal: {signal}')}")

        # Reasoning
        print(f"\n{separator()}")
        print("  KEY REASONING:")
        for i, reason in enumerate(d.reasoning, 1):
            print(f"    {i}. {reason}")

        # Bull / Bear cases
        print(f"\n{separator()}")
        print(f"  BULL CASE: {d.bull_case}")
        print(f"  BEAR CASE: {d.bear_case}")

        # Risk warnings
        if d.risk_warnings and d.risk_warnings != "No significant risk warnings":
            print(f"\n  RISK WARNINGS: {d.risk_warnings}")

        print(f"\n{'=' * 60}\n")
