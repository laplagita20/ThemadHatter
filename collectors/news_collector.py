"""News collector: RSS feeds from 10+ sources + Finnhub API."""

import logging
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from collectors.base_collector import BaseCollector
from database.models import NewsDAO

logger = logging.getLogger("stock_model.collectors.news")

# RSS feed sources with credibility tiers
RSS_FEEDS = {
    # Tier 1 (weight 1.0): Reuters, AP, Bloomberg, WSJ, The Economist
    "Reuters": {
        "url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
        "weight": 1.0,
        "tier": 1,
    },
    "AP News": {
        "url": "https://rsshub.app/apnews/topics/business",
        "weight": 1.0,
        "tier": 1,
    },
    "Bloomberg": {
        "url": "https://feeds.bloomberg.com/markets/news.rss",
        "weight": 1.0,
        "tier": 1,
    },
    "WSJ Markets": {
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "weight": 1.0,
        "tier": 1,
    },
    "The Economist": {
        "url": "https://www.economist.com/finance-and-economics/rss.xml",
        "weight": 1.0,
        "tier": 1,
    },
    # Tier 2 (weight 0.85): CNBC, MarketWatch, Forbes, TheStreet
    "CNBC": {
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "weight": 0.85,
        "tier": 2,
    },
    "MarketWatch": {
        "url": "https://feeds.marketwatch.com/marketwatch/topstories/",
        "weight": 0.85,
        "tier": 2,
    },
    "Forbes": {
        "url": "https://www.forbes.com/business/feed/",
        "weight": 0.85,
        "tier": 2,
    },
    "TheStreet": {
        "url": "https://www.thestreet.com/feeds/rss/stock-market",
        "weight": 0.85,
        "tier": 2,
    },
    # Tier 3 (weight 0.7): Yahoo Finance, Motley Fool
    "Yahoo Finance": {
        "url": "https://finance.yahoo.com/news/rssindex",
        "weight": 0.7,
        "tier": 3,
    },
    "Motley Fool": {
        "url": "https://www.fool.com/feeds/index.aspx",
        "weight": 0.7,
        "tier": 3,
    },
}


class NewsCollector(BaseCollector):
    """Collects news from RSS feeds and Finnhub API."""

    name = "news"
    rate_limit = 60.0  # Finnhub: 60/min
    rate_period = 60.0

    def __init__(self):
        super().__init__()
        self.news_dao = NewsDAO()
        self._finnhub = None

    def _get_finnhub(self):
        if self._finnhub is None:
            api_key = self.settings.finnhub_api_key
            if api_key:
                import finnhub
                self._finnhub = finnhub.Client(api_key=api_key)
        return self._finnhub

    def collect(self, ticker: str = None) -> dict:
        """Collect news from all sources."""
        logger.info("Collecting news%s", f" for {ticker}" if ticker else "")
        articles = []

        # RSS feeds (no rate limit needed)
        for source_name, config in RSS_FEEDS.items():
            try:
                feed_articles = self._collect_rss(source_name, config, ticker)
                articles.extend(feed_articles)
            except Exception as e:
                logger.warning("RSS feed %s failed: %s", source_name, e)

        # Finnhub API
        if ticker:
            try:
                finnhub_articles = self._collect_finnhub(ticker)
                articles.extend(finnhub_articles)
            except Exception as e:
                logger.warning("Finnhub news collection failed: %s", e)

        logger.info("Collected %d articles total", len(articles))
        return {"articles": articles, "ticker": ticker}

    def _collect_rss(self, source_name: str, config: dict, ticker: str = None) -> list[dict]:
        """Parse a single RSS feed."""
        articles = []
        cached = self._cache.get(f"rss_{source_name}")
        if cached:
            return cached

        try:
            feed = feedparser.parse(config["url"])
        except Exception as e:
            logger.debug("Feed parse error for %s: %s", source_name, e)
            return []

        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))

            # If ticker specified, check relevance
            if ticker and ticker.upper() not in (title + " " + summary).upper():
                continue

            # Parse date
            published = None
            for date_field in ("published_parsed", "updated_parsed"):
                t = entry.get(date_field)
                if t:
                    try:
                        published = datetime(*t[:6]).isoformat()
                    except Exception:
                        pass
                    break
            if not published:
                published = datetime.now(timezone.utc).isoformat()

            url = entry.get("link", "")
            # Basic URL validation
            if url and not url.startswith(("http://", "https://")):
                url = ""
            # Clamp credibility to [0, 1]
            cred = max(0.0, min(1.0, config.get("weight", 0.7)))

            articles.append({
                "title": title[:500],
                "summary": summary[:1000] if summary else None,
                "source": source_name,
                "url": url,
                "published_at": published,
                "ticker": ticker,
                "credibility_weight": cred,
            })

        # Cache for 30 min
        self._cache.set(f"rss_{source_name}", articles, ttl_seconds=1800)
        return articles

    def _collect_finnhub(self, ticker: str) -> list[dict]:
        """Collect company news from Finnhub API."""
        client = self._get_finnhub()
        if not client:
            return []

        end = datetime.now()
        start = end - timedelta(days=7)

        news = self._cached_call(
            f"finnhub_news_{ticker}",
            lambda: client.company_news(
                ticker,
                _from=start.strftime("%Y-%m-%d"),
                to=end.strftime("%Y-%m-%d"),
            ),
            ttl=1800,
        )

        articles = []
        for item in (news or [])[:50]:
            articles.append({
                "title": item.get("headline", "")[:500],
                "summary": item.get("summary", "")[:1000],
                "source": f"Finnhub ({item.get('source', 'unknown')})",
                "url": item.get("url", ""),
                "published_at": datetime.fromtimestamp(
                    item.get("datetime", 0), tz=timezone.utc
                ).isoformat() if item.get("datetime") else None,
                "ticker": ticker,
                "credibility_weight": 0.7,
            })

        return articles

    def store(self, data: dict):
        articles = data.get("articles", [])
        stored = 0
        for article in articles:
            self.news_dao.insert(article)
            stored += 1
        logger.info("Stored %d news articles", stored)
