"""Sentiment analysis: VADER NLP with financial lexicon overlay,
material event detection, credibility weighting, and trend tracking."""

import logging
import re
from datetime import datetime, timedelta

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.models import NewsDAO

logger = logging.getLogger("stock_model.analysis.sentiment")

# Material event keywords that signal significant news (use word boundaries)
MATERIAL_KEYWORDS = {
    "positive": [
        "FDA approval", "FDA approved", "earnings beat", "revenue beat",
        "upgrade", "buy rating", "raised guidance", "raised outlook",
        "partnership", "acquisition complete", "dividend increase",
        "stock split", "buyback", "share repurchase", "record revenue",
        "breakthrough", "patent granted", "expansion", "new contract",
        "beat estimates", "strong quarter", "profit surge",
    ],
    "negative": [
        "FDA reject", "earnings miss", "revenue miss", "downgrade",
        "sell rating", "lowered guidance", "cut outlook", "lawsuit",
        "investigation", "SEC investigation", "data breach", "recall",
        "bankruptcy", "layoffs", "restructuring", "delisted",
        "fraud", "accounting irregularity", "default", "missed payment",
        "missed earnings", "profit warning", "going concern",
    ],
}

# Pre-compile word-boundary patterns for material events
_MATERIAL_PATTERNS = {
    polarity: [re.compile(r"\b" + re.escape(kw.lower()) + r"\b") for kw in kws]
    for polarity, kws in MATERIAL_KEYWORDS.items()
}

# Financial-specific VADER lexicon overlay
# These augment VADER's default lexicon with finance-domain terms
FINANCIAL_LEXICON = {
    # Positive
    "beat estimates": 0.8,
    "beat expectations": 0.8,
    "outperform": 0.6,
    "strong buy": 0.9,
    "upgrade": 0.7,
    "upgraded": 0.7,
    "raised guidance": 0.8,
    "raised outlook": 0.7,
    "dividend increase": 0.6,
    "buyback": 0.5,
    "share repurchase": 0.5,
    "record revenue": 0.8,
    "record earnings": 0.8,
    "all-time high": 0.5,
    "breakout": 0.5,
    "fda approved": 0.9,
    "fda approval": 0.9,
    "patent granted": 0.6,
    "profit surge": 0.7,
    "strong quarter": 0.6,
    "beat consensus": 0.7,
    "accretive": 0.5,
    "bullish": 0.6,
    "outperformance": 0.5,
    # Negative
    "missed earnings": -0.8,
    "missed estimates": -0.8,
    "miss expectations": -0.7,
    "underperform": -0.6,
    "downgrade": -0.7,
    "downgraded": -0.7,
    "lowered guidance": -0.8,
    "cut outlook": -0.7,
    "profit warning": -0.8,
    "going concern": -0.9,
    "lawsuit filed": -0.6,
    "sec investigation": -0.8,
    "data breach": -0.7,
    "product recall": -0.7,
    "bankruptcy": -0.9,
    "restructuring": -0.4,
    "layoffs": -0.5,
    "accounting irregularity": -0.8,
    "bearish": -0.6,
    "fraud": -0.9,
    "delisted": -0.9,
}


def _get_vader():
    """Lazy-init VADER with financial lexicon overlay."""
    try:
        import nltk
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
        sia = SentimentIntensityAnalyzer()
        # Inject financial terms
        sia.lexicon.update(FINANCIAL_LEXICON)
        return sia
    except ImportError:
        logger.warning("nltk not installed — falling back to keyword sentiment")
        return None


class SentimentAnalyzer(BaseAnalyzer):
    """Analyzes news sentiment using VADER NLP with financial lexicon overlay."""

    name = "sentiment"

    def __init__(self):
        self.news_dao = NewsDAO()
        self._vader = _get_vader()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running sentiment analysis for %s", ticker)
        factors = []
        score = 0.0

        # Get recent articles
        raw_articles = self.news_dao.get_recent(ticker, days=30, limit=200)

        if not raw_articles:
            return self._make_result(0, 0.15, [],
                "No recent news articles found. Run news collection first.")

        articles = [dict(a) for a in raw_articles]

        # NLP sentiment on all articles
        sentiment_scores = self._analyze_sentiment(articles)

        # Credibility-weighted average sentiment
        weighted_sent = sentiment_scores.get("weighted_avg", 0)
        if weighted_sent > 0.15:
            impact = 20
            explanation = f"News sentiment is positive (weighted avg: {weighted_sent:.3f})"
        elif weighted_sent > 0.05:
            impact = 10
            explanation = f"News sentiment is mildly positive ({weighted_sent:.3f})"
        elif weighted_sent < -0.15:
            impact = -20
            explanation = f"News sentiment is negative ({weighted_sent:.3f})"
        elif weighted_sent < -0.05:
            impact = -10
            explanation = f"News sentiment is mildly negative ({weighted_sent:.3f})"
        else:
            impact = 0
            explanation = f"News sentiment is neutral ({weighted_sent:.3f})"
        score += impact
        factors.append(AnalysisFactor("Weighted Sentiment", f"{weighted_sent:.3f}", impact, explanation))

        # Tier 1 vs Tier 3 sentiment comparison
        t1_sent = sentiment_scores.get("tier1_avg", 0)
        t3_sent = sentiment_scores.get("tier3_avg", 0)
        if t1_sent != 0 and t3_sent != 0:
            divergence = t1_sent - t3_sent
            if abs(divergence) > 0.15:
                impact = 5 if t1_sent > t3_sent else -5
                factors.append(AnalysisFactor(
                    "Source Quality Signal",
                    f"Tier1: {t1_sent:.3f} vs Tier3: {t3_sent:.3f}",
                    impact,
                    f"Premium sources are {'more positive' if divergence > 0 else 'more negative'} than lower-tier"
                ))
                score += impact

        # Volume anomaly (unusual news coverage)
        article_count = len(articles)
        volume_factor = self._assess_news_volume(articles)
        if volume_factor > 2.0:
            impact = -5  # High volume usually means volatility/concern
            factors.append(AnalysisFactor(
                "News Volume", f"{article_count} articles ({volume_factor:.1f}x normal)",
                impact, "Unusually high news volume - increased attention/volatility"))
            score += impact
        elif volume_factor < 0.3 and article_count < 3:
            factors.append(AnalysisFactor(
                "News Volume", f"{article_count} articles",
                0, "Very low news coverage"))

        # Sentiment trend (improving or deteriorating)
        trend = self._analyze_trend(articles)
        if trend > 0.1:
            impact = 10
            explanation = "Sentiment improving over the past 30 days"
        elif trend < -0.1:
            impact = -10
            explanation = "Sentiment deteriorating over the past 30 days"
        else:
            impact = 0
            explanation = "Sentiment stable over the past 30 days"
        score += impact
        factors.append(AnalysisFactor("Sentiment Trend", f"{trend:+.3f}", impact, explanation))

        # Material event detection (with word boundaries)
        material = self._detect_material_events(articles)
        if material["positive"]:
            impact = 15
            events_str = ", ".join(material["positive"][:3])
            factors.append(AnalysisFactor(
                "Material Events (+)", events_str, impact,
                f"Positive material events: {events_str}"))
            score += impact
        if material["negative"]:
            impact = -15
            events_str = ", ".join(material["negative"][:3])
            factors.append(AnalysisFactor(
                "Material Events (-)", events_str, impact,
                f"Negative material events: {events_str}"))
            score += impact

        confidence = min(0.9, 0.3 + (len(articles) / 50) * 0.4 + (1 if material["positive"] or material["negative"] else 0) * 0.1)
        summary = f"Sentiment is {'positive' if score > 10 else 'negative' if score < -10 else 'neutral'} based on {len(articles)} articles from {len(set(a['source'] for a in articles))} sources"
        return self._make_result(score, confidence, factors, summary)

    def _analyze_sentiment(self, articles: list) -> dict:
        """Run VADER NLP on article headlines with financial lexicon."""
        if not self._vader:
            return self._keyword_sentiment(articles)

        weighted_total = 0
        weight_sum = 0
        tier1_scores = []
        tier3_scores = []

        for article in articles:
            text = f"{article['title']} {article.get('summary') or ''}"

            # VADER compound score (-1 to 1)
            scores = self._vader.polarity_scores(text)
            compound = scores["compound"]

            # Skip purely factual/neutral articles (very low subjectivity)
            if abs(compound) < 0.02:
                continue

            credibility = article.get("credibility_weight", 0.7) or 0.7
            weighted_total += compound * credibility
            weight_sum += credibility

            if credibility >= 1.0:
                tier1_scores.append(compound)
            elif credibility <= 0.7:
                tier3_scores.append(compound)

        return {
            "weighted_avg": weighted_total / weight_sum if weight_sum > 0 else 0,
            "tier1_avg": sum(tier1_scores) / len(tier1_scores) if tier1_scores else 0,
            "tier3_avg": sum(tier3_scores) / len(tier3_scores) if tier3_scores else 0,
            "article_count": len(articles),
        }

    def _keyword_sentiment(self, articles: list) -> dict:
        """Fallback keyword-based sentiment when VADER isn't available."""
        positive_words = {"growth", "profit", "beat", "upgrade", "bullish", "strong", "surge", "gain", "rally", "record"}
        negative_words = {"loss", "miss", "downgrade", "bearish", "weak", "decline", "fall", "crash", "risk", "concern"}

        total_score = 0
        for article in articles:
            text = (article["title"] + " " + (article.get("summary") or "")).lower()
            pos = sum(1 for w in positive_words if w in text)
            neg = sum(1 for w in negative_words if w in text)
            total_score += (pos - neg) * (article.get("credibility_weight", 0.7) or 0.7)

        avg = total_score / len(articles) if articles else 0
        return {"weighted_avg": avg / 3, "tier1_avg": 0, "tier3_avg": 0, "article_count": len(articles)}

    def _assess_news_volume(self, articles: list) -> float:
        """Assess if news volume is unusual (returns ratio vs expected)."""
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        recent = 0
        older = 0
        for a in articles:
            pub = a.get("published_at", "")
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else now
                if pub_dt.replace(tzinfo=None) > week_ago:
                    recent += 1
                else:
                    older += 1
            except (ValueError, TypeError):
                recent += 1

        expected_weekly = older / 3.3 if older > 0 else 5  # ~23 days / 7 days
        return recent / expected_weekly if expected_weekly > 0 else 1.0

    def _analyze_trend(self, articles: list) -> float:
        """Compare recent sentiment vs older sentiment for trend detection."""
        now = datetime.now()
        two_weeks_ago = now - timedelta(days=14)

        recent_scores = []
        older_scores = []

        for a in articles:
            text = a["title"]
            if self._vader:
                polarity = self._vader.polarity_scores(text)["compound"]
            else:
                # Simple keyword fallback
                text_lower = text.lower()
                pos = sum(1 for w in ("growth", "profit", "beat", "strong", "surge") if w in text_lower)
                neg = sum(1 for w in ("loss", "miss", "weak", "decline", "crash") if w in text_lower)
                polarity = (pos - neg) / max(pos + neg, 1)

            pub = a.get("published_at", "")
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else now
                if pub_dt.replace(tzinfo=None) > two_weeks_ago:
                    recent_scores.append(polarity)
                else:
                    older_scores.append(polarity)
            except (ValueError, TypeError):
                recent_scores.append(polarity)

        recent_avg = sum(recent_scores) / len(recent_scores) if recent_scores else 0
        older_avg = sum(older_scores) / len(older_scores) if older_scores else 0

        return recent_avg - older_avg

    def _detect_material_events(self, articles: list) -> dict:
        """Detect material events using word-boundary regex patterns."""
        found = {"positive": set(), "negative": set()}

        for article in articles:
            text = (article["title"] + " " + (article.get("summary") or "")).lower()
            for pattern, keyword in zip(_MATERIAL_PATTERNS["positive"], MATERIAL_KEYWORDS["positive"]):
                if pattern.search(text):
                    found["positive"].add(keyword)
                    break
            for pattern, keyword in zip(_MATERIAL_PATTERNS["negative"], MATERIAL_KEYWORDS["negative"]):
                if pattern.search(text):
                    found["negative"].add(keyword)
                    break

        return {"positive": list(found["positive"]), "negative": list(found["negative"])}
