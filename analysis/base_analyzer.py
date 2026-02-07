"""Base analyzer interface and AnalysisResult dataclass."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from utils.helpers import score_to_signal


@dataclass
class AnalysisFactor:
    """A single factor contributing to an analysis score."""
    name: str
    value: float | str | None
    impact: float  # contribution to score
    explanation: str


@dataclass
class AnalysisResult:
    """Standardized output from any analyzer."""
    score: float  # -100 to +100
    confidence: float  # 0.0 to 1.0
    signal: str  # strong_buy / buy / hold / sell / strong_sell
    factors: list[AnalysisFactor] = field(default_factory=list)
    summary: str = ""
    analyzer_name: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "signal": self.signal,
            "factors": [
                {"name": f.name, "value": f.value, "impact": f.impact, "explanation": f.explanation}
                for f in self.factors
            ],
            "summary": self.summary,
            "analyzer_name": self.analyzer_name,
        }


class BaseAnalyzer(ABC):
    """Abstract base for all analyzers."""

    name: str = "base"

    @abstractmethod
    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        """Run analysis and return an AnalysisResult."""
        ...

    def _make_result(self, score: float, confidence: float,
                     factors: list[AnalysisFactor], summary: str) -> AnalysisResult:
        """Helper to create a properly clamped AnalysisResult."""
        score = max(-100, min(100, score))
        confidence = max(0.0, min(1.0, confidence))
        return AnalysisResult(
            score=score,
            confidence=confidence,
            signal=score_to_signal(score),
            factors=factors,
            summary=summary,
            analyzer_name=self.name,
        )
