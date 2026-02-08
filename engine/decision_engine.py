"""Decision engine: combines all analyzer scores into justified multi-horizon recommendations.

Phase 7D: Multi-horizon recommendations, price targets, scenario analysis,
conviction scoring, and peer comparison.
"""

import logging
import json
from dataclasses import dataclass, field

import yfinance as yf

from config.settings import get_settings
from analysis.technical import TechnicalAnalyzer
from analysis.fundamental import FundamentalAnalyzer
from analysis.base_analyzer import AnalysisResult
from database.models import AnalysisResultDAO, DecisionDAO, StockDAO
from database.connection import get_connection
from utils.console import header, separator, ok, fail, neutral
from utils.helpers import format_pct, format_currency, score_to_signal

logger = logging.getLogger("stock_model.engine")


@dataclass
class HorizonRecommendation:
    """Recommendation for a specific time horizon."""
    horizon: str  # "3_month", "6_month", "12_month"
    action: str
    score: float
    confidence: float
    price_target: float | None = None
    upside_pct: float | None = None


@dataclass
class ScenarioAnalysis:
    """Bull/base/bear scenario with probability."""
    bull_price: float | None = None
    bull_probability: float = 0.30
    base_price: float | None = None
    base_probability: float = 0.50
    bear_price: float | None = None
    bear_probability: float = 0.20
    bull_reasoning: str = ""
    base_reasoning: str = ""
    bear_reasoning: str = ""


@dataclass
class Decision:
    ticker: str
    action: str  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    composite_score: float
    confidence: float
    conviction_score: float = 0.0  # Separate from confidence: how SURE are we
    position_size_pct: float = 0.0
    stop_loss_pct: float = 15.0
    target_price: float | None = None
    time_horizon: str = "medium_term"
    reasoning: list[str] = field(default_factory=list)
    bull_case: str = ""
    bear_case: str = ""
    risk_warnings: str = ""
    analysis_breakdown: dict = field(default_factory=dict)
    # Phase 7D additions
    horizons: list[HorizonRecommendation] = field(default_factory=list)
    scenarios: ScenarioAnalysis = field(default_factory=ScenarioAnalysis)
    price_targets: dict = field(default_factory=dict)
    peer_comparison: list[dict] = field(default_factory=list)


class DecisionEngine:
    """Combines all analysis scores into a single decision with reasoning."""

    def __init__(self):
        self.settings = get_settings()
        self.weights = dict(self.settings.analysis_weights)
        self.analyzers = self._init_analyzers()
        self.analysis_dao = AnalysisResultDAO()
        self.decision_dao = DecisionDAO()
        self.stock_dao = StockDAO()
        self.db = get_connection()

    def _init_analyzers(self) -> dict:
        """Initialize available analyzers."""
        analyzers = {
            "technical": TechnicalAnalyzer(),
            "fundamental": FundamentalAnalyzer(),
        }

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

        try:
            from analysis.insider_analyzer import InsiderAnalyzer
            analyzers["insider"] = InsiderAnalyzer()
        except ImportError:
            pass

        try:
            from analysis.institutional_analyzer import InstitutionalAnalyzer
            analyzers["institutional"] = InstitutionalAnalyzer()
        except ImportError:
            pass

        try:
            from analysis.earnings_quality import EarningsQualityAnalyzer
            analyzers["earnings_quality"] = EarningsQualityAnalyzer()
        except ImportError:
            pass

        return analyzers

    def analyze(self, ticker: str) -> Decision:
        """Run all available analyzers and produce a multi-horizon decision."""
        logger.info("Running full analysis for %s", ticker)

        self.stock_dao.upsert(ticker=ticker)

        # Run each analyzer
        results: dict[str, AnalysisResult] = {}
        for name, analyzer in self.analyzers.items():
            try:
                result = analyzer.analyze(ticker)
                results[name] = result
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

        # Calculate composite
        composite_score, confidence = self._calculate_composite(results)

        # Multi-horizon recommendations
        horizons = self._calculate_horizons(results, composite_score, confidence)

        # Primary action (6-month horizon = balanced)
        action = self._score_to_action(composite_score, confidence)

        # Conviction score
        conviction = self._calculate_conviction(results, composite_score)

        # Price targets
        price_targets = self._calculate_price_targets(ticker, results)

        # Scenario analysis
        scenarios = self._calculate_scenarios(ticker, results, price_targets)

        # Peer comparison
        peer_comparison = self._peer_comparison(ticker)

        # Build reasoning
        reasoning = self._build_reasoning(results, action)
        bull_case, bear_case = self._build_cases(results)
        risk_warnings = self._build_risk_warnings(results)

        # Position sizing (Kelly-aware)
        position_size = self._calculate_position_size(composite_score, confidence, conviction)
        stop_loss = self._calculate_stop_loss(composite_score)

        decision = Decision(
            ticker=ticker,
            action=action,
            composite_score=composite_score,
            confidence=confidence,
            conviction_score=conviction,
            position_size_pct=position_size,
            stop_loss_pct=stop_loss,
            target_price=price_targets.get("blended"),
            time_horizon=self._determine_horizon(results),
            reasoning=reasoning,
            bull_case=bull_case,
            bear_case=bear_case,
            risk_warnings=risk_warnings,
            analysis_breakdown={
                name: result.to_dict() for name, result in results.items()
            },
            horizons=horizons,
            scenarios=scenarios,
            price_targets=price_targets,
            peer_comparison=peer_comparison,
        )

        # Store decision
        self.decision_dao.insert({
            "ticker": ticker,
            "action": action,
            "composite_score": composite_score,
            "confidence": confidence,
            "position_size_pct": position_size,
            "stop_loss_pct": stop_loss,
            "target_price": price_targets.get("blended"),
            "time_horizon": decision.time_horizon,
            "reasoning": reasoning,
            "bull_case": bull_case,
            "bear_case": bear_case,
            "risk_warnings": risk_warnings,
            "analysis_breakdown": decision.analysis_breakdown,
        })

        return decision

    def _calculate_composite(self, results: dict[str, AnalysisResult]) -> tuple[float, float]:
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
        if confidence < 0.3:
            return "HOLD"
        if score >= 50:
            return "STRONG_BUY"
        elif score >= 20:
            return "BUY"
        elif score <= -50:
            return "STRONG_SELL"
        elif score <= -20:
            return "SELL"
        return "HOLD"

    # =========================================================================
    # Multi-Horizon Recommendations
    # =========================================================================
    def _calculate_horizons(self, results: dict[str, AnalysisResult],
                            composite_score: float, confidence: float) -> list[HorizonRecommendation]:
        """Generate 3-month, 6-month, 12-month recommendations with different weightings."""

        # Horizon-specific weight adjustments
        horizon_weights = {
            "3_month": {
                "technical": 1.5, "sentiment": 1.5, "insider": 1.3,
                "fundamental": 0.7, "macroeconomic": 0.7,
            },
            "6_month": {},  # Use default weights
            "12_month": {
                "fundamental": 1.5, "macroeconomic": 1.3, "institutional": 1.3,
                "technical": 0.5, "sentiment": 0.5,
            },
        }

        horizons = []
        for horizon, adjustments in horizon_weights.items():
            weighted_sum = 0.0
            weight_total = 0.0

            for name, result in results.items():
                base_weight = self.weights.get(name, 0.05)
                multiplier = adjustments.get(name, 1.0)
                adjusted_weight = base_weight * multiplier * result.confidence
                weighted_sum += result.score * adjusted_weight
                weight_total += adjusted_weight

            if weight_total > 0:
                horizon_score = weighted_sum / weight_total
            else:
                horizon_score = composite_score

            action = self._score_to_action(horizon_score, confidence)

            horizons.append(HorizonRecommendation(
                horizon=horizon,
                action=action,
                score=round(horizon_score, 2),
                confidence=round(confidence, 3),
            ))

        return horizons

    # =========================================================================
    # Price Targets
    # =========================================================================
    def _calculate_price_targets(self, ticker: str, results: dict[str, AnalysisResult]) -> dict:
        """Calculate blended price target from DCF, technical, and analyst consensus."""
        targets = {}

        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")

            if not current_price:
                return targets

            targets["current_price"] = current_price

            # 1. DCF target (from fundamental analyzer's DCF calculation)
            try:
                dcf_row = self.db.execute_one(
                    "SELECT intrinsic_value FROM dcf_valuations WHERE ticker = ? ORDER BY computed_at DESC LIMIT 1",
                    (ticker,),
                )
                if dcf_row and dcf_row["intrinsic_value"]:
                    targets["dcf"] = round(dcf_row["intrinsic_value"], 2)
            except Exception:
                pass

            # 2. Analyst consensus target
            analyst_target = info.get("targetMeanPrice")
            if analyst_target:
                targets["analyst_consensus"] = round(analyst_target, 2)

            analyst_high = info.get("targetHighPrice")
            analyst_low = info.get("targetLowPrice")
            if analyst_high:
                targets["analyst_high"] = round(analyst_high, 2)
            if analyst_low:
                targets["analyst_low"] = round(analyst_low, 2)

            # 3. Technical target (based on 52-week range and momentum)
            fifty_two_high = info.get("fiftyTwoWeekHigh")
            fifty_two_low = info.get("fiftyTwoWeekLow")
            if fifty_two_high and fifty_two_low:
                tech_score = results.get("technical", AnalysisResult(0, 0, "hold")).score
                if tech_score > 20:
                    # Bullish: target near 52-week high + some extension
                    targets["technical"] = round(fifty_two_high * 1.05, 2)
                elif tech_score < -20:
                    # Bearish: target below midpoint
                    midpoint = (fifty_two_high + fifty_two_low) / 2
                    targets["technical"] = round(midpoint * 0.95, 2)
                else:
                    targets["technical"] = round((fifty_two_high + fifty_two_low) / 2, 2)

            # 4. Blended target (weighted average of available targets)
            available_targets = []
            target_weights = {"dcf": 0.40, "analyst_consensus": 0.35, "technical": 0.25}
            total_weight = 0

            for key, weight in target_weights.items():
                if key in targets:
                    available_targets.append((targets[key], weight))
                    total_weight += weight

            if available_targets and total_weight > 0:
                blended = sum(t * w for t, w in available_targets) / total_weight
                targets["blended"] = round(blended, 2)
                targets["upside_pct"] = round((blended / current_price - 1) * 100, 1)

        except Exception as e:
            logger.warning("Price target calculation failed for %s: %s", ticker, e)

        return targets

    # =========================================================================
    # Scenario Analysis
    # =========================================================================
    def _calculate_scenarios(self, ticker: str, results: dict[str, AnalysisResult],
                             price_targets: dict) -> ScenarioAnalysis:
        """Calculate bull/base/bear scenarios with probabilities."""
        try:
            current_price = price_targets.get("current_price")
            if not current_price:
                return ScenarioAnalysis()

            confidence = sum(r.confidence for r in results.values()) / max(len(results), 1)
            composite = sum(r.score * self.weights.get(n, 0.05) for n, r in results.items()) / max(sum(self.weights.get(n, 0.05) for n in results), 0.01)

            # Bull case: best fundamental + positive sentiment + sector tailwind
            bull_factors = [r.score for r in results.values() if r.score > 10]
            bull_uplift = 1 + max(0.10, min(0.50, len(bull_factors) * 0.08))
            bull_price = round(current_price * bull_uplift, 2)

            # Bear case: worst fundamentals + negative sentiment
            bear_factors = [r.score for r in results.values() if r.score < -10]
            bear_decline = 1 - max(0.10, min(0.40, len(bear_factors) * 0.08))
            bear_price = round(current_price * bear_decline, 2)

            # Base case: blend of targets or small drift from current
            base_price = price_targets.get("blended") or round(current_price * (1 + composite / 200), 2)

            # Use analyst targets if available
            if "analyst_high" in price_targets:
                bull_price = max(bull_price, price_targets["analyst_high"])
            if "analyst_low" in price_targets:
                bear_price = min(bear_price, price_targets["analyst_low"])

            # Adjust probabilities based on confidence and composite direction
            if composite > 20:
                bull_prob, base_prob, bear_prob = 0.35, 0.45, 0.20
            elif composite < -20:
                bull_prob, base_prob, bear_prob = 0.15, 0.45, 0.40
            else:
                bull_prob, base_prob, bear_prob = 0.25, 0.50, 0.25

            # Build reasoning
            bull_analyzers = [n for n, r in results.items() if r.score > 15]
            bear_analyzers = [n for n, r in results.items() if r.score < -15]

            bull_reasoning = f"Positive drivers: {', '.join(bull_analyzers[:3]) or 'momentum continuation'}"
            bear_reasoning = f"Risk factors: {', '.join(bear_analyzers[:3]) or 'broad market downturn'}"
            base_reasoning = "Current trajectory maintained with normal volatility"

            return ScenarioAnalysis(
                bull_price=bull_price,
                bull_probability=bull_prob,
                base_price=base_price,
                base_probability=base_prob,
                bear_price=bear_price,
                bear_probability=bear_prob,
                bull_reasoning=bull_reasoning,
                base_reasoning=base_reasoning,
                bear_reasoning=bear_reasoning,
            )
        except Exception as e:
            logger.warning("Scenario analysis failed for %s: %s", ticker, e)
            return ScenarioAnalysis()

    # =========================================================================
    # Conviction Score
    # =========================================================================
    def _calculate_conviction(self, results: dict[str, AnalysisResult],
                               composite_score: float) -> float:
        """Calculate conviction: how SURE we are (separate from bullish/bearish)."""
        conviction = 50.0  # Start neutral

        # Analyzer agreement boosts conviction
        signals = [r.signal for r in results.values()]
        bullish = sum(1 for s in signals if s in ("buy", "strong_buy"))
        bearish = sum(1 for s in signals if s in ("sell", "strong_sell"))
        total = len(signals)

        if total > 0:
            agreement = max(bullish, bearish) / total
            if agreement >= 0.8:
                conviction += 20
            elif agreement >= 0.6:
                conviction += 10
            elif agreement <= 0.3:
                conviction -= 15

        # High individual confidences boost
        high_conf = sum(1 for r in results.values() if r.confidence > 0.7)
        low_conf = sum(1 for r in results.values() if r.confidence < 0.3)
        conviction += high_conf * 5
        conviction -= low_conf * 8

        # Score magnitude
        if abs(composite_score) > 50:
            conviction += 10
        elif abs(composite_score) < 10:
            conviction -= 10

        # Data freshness (more analyzers = more data = higher conviction)
        if len(results) >= 7:
            conviction += 10
        elif len(results) >= 5:
            conviction += 5
        elif len(results) <= 2:
            conviction -= 15

        # Historical accuracy for this stock
        try:
            accuracy = self.db.execute_one(
                """SELECT AVG(CASE WHEN action_was_correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy
                   FROM decision_outcomes
                   WHERE ticker = ? AND action_was_correct IS NOT NULL""",
                (results and list(results.keys())[0] if results else "",),
            )
            if accuracy and accuracy["accuracy"] is not None:
                hist_acc = accuracy["accuracy"]
                if hist_acc > 0.7:
                    conviction += 10
                elif hist_acc < 0.4:
                    conviction -= 10
        except Exception:
            pass

        return max(0, min(100, conviction))

    # =========================================================================
    # Peer Comparison
    # =========================================================================
    def _peer_comparison(self, ticker: str, max_peers: int = 5) -> list[dict]:
        """Compare key metrics against sector/industry peers."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            sector = info.get("sector")
            industry = info.get("industry")

            if not sector:
                return []

            # Key metrics for comparison
            metrics = {
                "P/E": info.get("trailingPE"),
                "P/B": info.get("priceToBook"),
                "ROE": info.get("returnOnEquity"),
                "Profit Margin": info.get("profitMargins"),
                "Revenue Growth": info.get("revenueGrowth"),
                "Debt/Equity": info.get("debtToEquity"),
            }

            # Try to get peers from yfinance recommendations or sector ETF
            comparisons = []
            for metric_name, value in metrics.items():
                if value is None:
                    continue

                # Get sector median from Alpha Vantage overview if available
                try:
                    sector_data = self.db.execute(
                        """SELECT AVG(CASE WHEN ? = 'P/E' THEN pe_ratio
                                    WHEN ? = 'P/B' THEN pb_ratio
                                    WHEN ? = 'ROE' THEN roe
                                    WHEN ? = 'Profit Margin' THEN profit_margin
                                    WHEN ? = 'Revenue Growth' THEN revenue_growth
                                    WHEN ? = 'Debt/Equity' THEN debt_to_equity
                               END) as sector_avg
                           FROM stock_fundamentals sf
                           JOIN stocks s ON sf.ticker = s.ticker
                           WHERE s.sector = ? AND sf.ticker != ?
                           AND sf.fetched_at = (SELECT MAX(fetched_at) FROM stock_fundamentals WHERE ticker = sf.ticker)""",
                        (metric_name, metric_name, metric_name, metric_name,
                         metric_name, metric_name, sector, ticker),
                    )
                    sector_avg = sector_data[0]["sector_avg"] if sector_data and sector_data[0]["sector_avg"] else None
                except Exception:
                    sector_avg = None

                if metric_name in ("ROE", "Profit Margin", "Revenue Growth") and value is not None:
                    display_value = f"{value * 100:.1f}%"
                    display_avg = f"{sector_avg * 100:.1f}%" if sector_avg else "N/A"
                elif metric_name == "Debt/Equity" and value is not None:
                    display_value = f"{value:.0f}"
                    display_avg = f"{sector_avg:.0f}" if sector_avg else "N/A"
                else:
                    display_value = f"{value:.1f}" if value else "N/A"
                    display_avg = f"{sector_avg:.1f}" if sector_avg else "N/A"

                better = None
                if sector_avg is not None and value is not None:
                    if metric_name in ("P/E", "P/B", "Debt/Equity"):
                        better = value < sector_avg  # Lower is better
                    else:
                        better = value > sector_avg  # Higher is better

                comparisons.append({
                    "metric": metric_name,
                    "value": display_value,
                    "sector_avg": display_avg,
                    "sector": sector,
                    "better_than_sector": better,
                })

            return comparisons
        except Exception as e:
            logger.debug("Peer comparison failed for %s: %s", ticker, e)
            return []

    # =========================================================================
    # Position Sizing & Stop Loss
    # =========================================================================
    def _calculate_position_size(self, score: float, confidence: float, conviction: float) -> float:
        """Determine position size based on conviction, with Kelly awareness."""
        s = self.settings

        # Try Kelly Criterion first
        try:
            from engine.risk_manager import RiskManager
            rm = RiskManager()
            kelly = rm.kelly_criterion()
            if kelly.get("recommended_pct") is not None:
                # Adjust Kelly by conviction
                kelly_size = kelly["recommended_pct"] * (conviction / 100)
                return min(kelly_size, s.max_single_position_pct)
        except Exception:
            pass

        # Fallback to conviction-based sizing
        if abs(score) >= 50 and confidence >= 0.7 and conviction >= 70:
            return s.position_size_high_conviction
        elif abs(score) >= 20 and confidence >= 0.5:
            return s.position_size_medium_conviction
        return s.position_size_low_conviction

    def _calculate_stop_loss(self, score: float) -> float:
        s = self.settings
        if abs(score) >= 50:
            return s.trailing_stop_tactical_pct
        return s.trailing_stop_core_pct

    def _determine_horizon(self, results: dict[str, AnalysisResult]) -> str:
        tech_score = results.get("technical", AnalysisResult(0, 0, "hold")).score
        fund_score = results.get("fundamental", AnalysisResult(0, 0, "hold")).score

        if abs(tech_score) > abs(fund_score):
            return "short_term"
        return "medium_term"

    # =========================================================================
    # Reasoning Builders
    # =========================================================================
    def _build_reasoning(self, results: dict[str, AnalysisResult], action: str) -> list[str]:
        reasons = []
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
        warnings = []

        for name, result in results.items():
            if result.confidence < 0.4:
                warnings.append(f"Low confidence in {name} analysis ({result.confidence:.0%})")
            for f in result.factors:
                if f.impact <= -12:
                    warnings.append(f"{f.name}: {f.explanation}")

        return "; ".join(warnings[:5]) if warnings else "No significant risk warnings"

    # =========================================================================
    # Print Decision Report
    # =========================================================================
    def print_decision(self, d: Decision):
        """Print a comprehensive formatted decision report."""
        print(header(f"ANALYSIS REPORT: {d.ticker}"))

        action_symbols = {
            "STRONG_BUY": ok, "BUY": ok, "HOLD": neutral,
            "SELL": fail, "STRONG_SELL": fail,
        }
        symbol_fn = action_symbols.get(d.action, neutral)
        print(f"\n  RECOMMENDATION: {symbol_fn(d.action)}")
        print(f"  Composite Score: {d.composite_score:+.1f}/100")
        print(f"  Confidence: {d.confidence:.0%}")
        print(f"  Conviction: {d.conviction_score:.0f}/100")
        print(f"  Position Size: {d.position_size_pct:.1f}% of portfolio")
        print(f"  Stop-Loss: {d.stop_loss_pct:.1f}%")
        print(f"  Time Horizon: {d.time_horizon.replace('_', ' ').title()}")

        # Multi-Horizon Recommendations
        if d.horizons:
            print(f"\n{separator()}")
            print("  MULTI-HORIZON OUTLOOK:")
            for h in d.horizons:
                fn = action_symbols.get(h.action, neutral)
                label = h.horizon.replace("_", " ").title()
                print(f"    {label:<12} {fn(f'{h.action:<12}')} Score: {h.score:+.1f}")

        # Price Targets
        if d.price_targets:
            print(f"\n{separator()}")
            print("  PRICE TARGETS:")
            if "current_price" in d.price_targets:
                print(f"    Current Price:    ${d.price_targets['current_price']:.2f}")
            if "dcf" in d.price_targets:
                print(f"    DCF Fair Value:   ${d.price_targets['dcf']:.2f}")
            if "analyst_consensus" in d.price_targets:
                print(f"    Analyst Target:   ${d.price_targets['analyst_consensus']:.2f}")
            if "technical" in d.price_targets:
                print(f"    Technical Target: ${d.price_targets['technical']:.2f}")
            if "blended" in d.price_targets:
                upside = d.price_targets.get("upside_pct", 0)
                blended_val = d.price_targets["blended"]
                fn = ok if upside > 0 else fail
                print(f"    Blended Target:   {fn(f'${blended_val:.2f} ({upside:+.1f}%)')}")

        # Scenario Analysis
        if d.scenarios.base_price:
            print(f"\n{separator()}")
            print("  SCENARIO ANALYSIS (12-month):")
            print(f"    Bull Case:  ${d.scenarios.bull_price:.2f} ({d.scenarios.bull_probability:.0%} probability)")
            print(f"      {d.scenarios.bull_reasoning}")
            print(f"    Base Case:  ${d.scenarios.base_price:.2f} ({d.scenarios.base_probability:.0%} probability)")
            print(f"      {d.scenarios.base_reasoning}")
            print(f"    Bear Case:  ${d.scenarios.bear_price:.2f} ({d.scenarios.bear_probability:.0%} probability)")
            print(f"      {d.scenarios.bear_reasoning}")

        # Analysis breakdown
        print(f"\n{separator()}")
        print("  ANALYSIS BREAKDOWN:")
        for name, data in d.analysis_breakdown.items():
            score = data["score"]
            conf = data["confidence"]
            signal = data["signal"]
            fn = ok if score > 0 else fail if score < 0 else neutral
            print(f"    {fn(f'{name.title():<20} Score: {score:>+6.1f}  Confidence: {conf:.0%}  Signal: {signal}')}")

        # Reasoning
        print(f"\n{separator()}")
        print("  KEY REASONING:")
        for i, reason in enumerate(d.reasoning[:6], 1):
            print(f"    {i}. {reason}")

        # Bull / Bear cases
        print(f"\n{separator()}")
        print(f"  BULL CASE: {d.bull_case}")
        print(f"  BEAR CASE: {d.bear_case}")

        # Peer Comparison
        if d.peer_comparison:
            print(f"\n{separator()}")
            print("  PEER COMPARISON:")
            for p in d.peer_comparison:
                if p.get("better_than_sector") is True:
                    fn = ok
                elif p.get("better_than_sector") is False:
                    fn = fail
                else:
                    fn = neutral
                metric = p["metric"]
                value = p["value"]
                sector_avg = p["sector_avg"]
                print(f"    {fn(f'{metric:<16} {value:>10}  vs sector avg: {sector_avg:>10}')}")

        # Risk warnings
        if d.risk_warnings and d.risk_warnings != "No significant risk warnings":
            print(f"\n  RISK WARNINGS: {d.risk_warnings}")

        print(f"\n{'=' * 60}\n")
