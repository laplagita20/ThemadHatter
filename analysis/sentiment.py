"""Sentiment analysis: NLP on news headlines, volume anomaly, trend detection."""

import logging
import re
from datetime import datetime, timedelta

from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.models import NewsDAO

logger = logging.getLogger("stock_model.analysis.sentiment")

# Material event keywords that signal significant news
MATERIAL_KEYWORDS = {
    "positive": [
        "FDA approval", "FDA approved", "earnings beat", "revenue beat",
        "upgrade", "buy rating", "raised guidance", "raised outlook",
        "partnership", "acquisition complete", "dividend increase",
        "stock split", "buyback", "share repurchase", "record revenue",
        "breakthrough", "patent granted", "expansion", "new contract",
    ],
    "negative": [
        "FDA reject", "earnings miss", "revenue miss", "downgrade",
        "sell rating", "lowered guidance", "cut outlook", "lawsuit",
        "investigation", "SEC investigation", "data breach", "recall",
        "bankruptcy", "layoffs", "restructuring", "delisted",
        "fraud", "accounting irregularity", "default", "missed payment",
    ],
}


class SentimentAnalyzer(BaseAnalyzer):
    """Analyzes news sentiment using TextBlob NLP and credibility weighting."""

    name = "sentiment"

    def __init__(self):
        self.news_dao = NewsDAO()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running sentiment analysis for %s", ticker)
        factors = []
        score = 0.0

        # Get recent articles
        articles = self.news_dao.get_recent(ticker, days=30, limit=200)

        if not articles:
            return self._make_result(0, 0.15, [],
                "No recent news articles found. Run news collection first.")

        articles = list(articles)

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

        # Material event detection
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
        """Run TextBlob NLP on article headlines."""
        try:
            from textblob import TextBlob
        except ImportError:
            logger.warning("TextBlob not installed, using keyword-based sentiment")
            return self._keyword_sentiment(articles)

        weighted_total = 0
        weight_sum = 0
        tier1_scores = []
        tier3_scores = []

        for article in articles:
            text = f"{article['title']} {article['summary'] or ''}"
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity  # -1 to 1

            credibility = article.get("credibility_weight", 0.7) or 0.7
            weighted_total += polarity * credibility
            weight_sum += credibility

            if credibility >= 1.0:
                tier1_scores.append(polarity)
            elif credibility <= 0.7:
                tier3_scores.append(polarity)

        return {
            "weighted_avg": weighted_total / weight_sum if weight_sum > 0 else 0,
            "tier1_avg": sum(tier1_scores) / len(tier1_scores) if tier1_scores else 0,
            "tier3_avg": sum(tier3_scores) / len(tier3_scores) if tier3_scores else 0,
            "article_count": len(articles),
        }

    def _keyword_sentiment(self, articles: list) -> dict:
        """Fallback keyword-based sentiment when TextBlob isn't available."""
        positive_words = {"growth", "profit", "beat", "upgrade", "bullish", "strong", "surge", "gain", "rally", "record"}
        negative_words = {"loss", "miss", "downgrade", "bearish", "weak", "decline", "fall", "crash", "risk", "concern"}

        total_score = 0
        for article in articles:
            text = (article["title"] + " " + (article["summary"] or "")).lower()
            pos = sum(1 for w in positive_words if w in text)
            neg = sum(1 for w in negative_words if w in text)
            total_score += (pos - neg) * (article.get("credibility_weight", 0.7) or 0.7)

        avg = total_score / len(articles) if articles else 0
        return {"weighted_avg": avg / 3, "tier1_avg": 0, "tier3_avg": 0, "article_count": len(articles)}

    def _assess_news_volume(self, articles: list) -> float:
        """Assess if news volume is unusual (returns ratio vs expected)."""
        # Simple: compare last 7 days vs prior 23 days
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
        try:
            from textblob import TextBlob
        except ImportError:
            return 0.0

        now = datetime.now()
        two_weeks_ago = now - timedelta(days=14)

        recent_scores = []
        older_scores = []

        for a in articles:
            text = a["title"]
            polarity = TextBlob(text).sentiment.polarity
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
        """Detect material events from article headlines."""
        found = {"positive": [], "negative": []}

        for article in articles:
            text = (article["title"] + " " + (article["summary"] or "")).lower()
            for keyword in MATERIAL_KEYWORDS["positive"]:
                if keyword.lower() in text:
                    found["positive"].append(keyword)
                    break
            for keyword in MATERIAL_KEYWORDS["negative"]:
                if keyword.lower() in text:
                    found["negative"].append(keyword)
                    break

        # Deduplicate
        found["positive"] = list(set(found["positive"]))
        found["negative"] = list(set(found["negative"]))
        return found
