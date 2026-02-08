"""GDELT collector: geopolitical event monitoring."""

import logging
import requests
from datetime import datetime, timedelta

from collectors.base_collector import BaseCollector
from database.connection import get_connection

logger = logging.getLogger("stock_model.collectors.gdelt")

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


class GDELTCollector(BaseCollector):
    """Collects geopolitical events from GDELT DOC API."""

    name = "gdelt"
    rate_limit = 1.0
    rate_period = 5.0  # 1 request per 5 seconds

    def __init__(self):
        super().__init__()
        self.db = get_connection()

    def collect(self, ticker: str = None) -> dict:
        """Collect geopolitical events. Searches for country/sector keywords."""
        logger.info("Collecting GDELT geopolitical events")

        # Search terms for market-impacting events
        queries = [
            "trade war tariff sanctions",
            "military conflict war",
            "central bank interest rate",
            "supply chain disruption",
            "oil energy crisis",
            "regulation antitrust",
            "election political instability",
            "pandemic health emergency",
        ]

        all_events = []
        for query in queries:
            try:
                events = self._search_gdelt(query)
                all_events.extend(events)
            except Exception as e:
                logger.warning("GDELT query '%s' failed: %s", query, e)

        return {"events": all_events}

    def _search_gdelt(self, query: str) -> list[dict]:
        """Search GDELT DOC API for articles matching query."""
        cached = self._cache.get(f"gdelt_{query}")
        if cached:
            return cached

        params = {
            "query": query,
            "mode": "ArtList",
            "maxrecords": 50,
            "format": "json",
            "timespan": "7d",
        }

        def do_request():
            resp = requests.get(GDELT_DOC_API, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()

        data = self._rate_limited_call(do_request)
        articles = data.get("articles", [])

        events = []
        for article in articles:
            tone = article.get("tone", 0)
            if isinstance(tone, str):
                try:
                    tone = float(tone.split(",")[0])
                except (ValueError, IndexError):
                    tone = 0

            events.append({
                "event_date": article.get("seendate", "")[:10],
                "source_country": article.get("sourcecountry", ""),
                "target_country": "",
                "event_type": query.split()[0],
                "goldstein_scale": None,
                "tone": tone,
                "num_mentions": 1,
                "num_sources": 1,
                "risk_score": self._calculate_risk_score(tone, query),
                "description": article.get("title", "")[:500],
                "url": article.get("url", ""),
            })

        self._cache.set(f"gdelt_{query}", events, ttl_seconds=3600)
        return events

    def _calculate_risk_score(self, tone: float, query: str) -> float:
        """Calculate a risk score from 0-100 based on tone and event type."""
        # Higher risk for negative tone
        base_risk = max(0, min(100, 50 - tone * 5))

        # Adjust by event type severity
        severity_map = {
            "trade": 1.0,
            "military": 1.5,
            "central": 0.8,
            "supply": 1.2,
            "oil": 1.1,
            "regulation": 0.9,
            "election": 0.7,
            "pandemic": 1.4,
        }
        keyword = query.split()[0].lower()
        multiplier = severity_map.get(keyword, 1.0)

        return min(100, base_risk * multiplier)

    def store(self, data: dict):
        events = data.get("events", [])
        stored = 0
        for event in events:
            try:
                self.db.execute_insert(
                    """INSERT INTO geopolitical_events
                       (event_date, source_country, target_country, event_type,
                        goldstein_scale, tone, num_mentions, num_sources,
                        risk_score, description, url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event["event_date"], event["source_country"],
                        event["target_country"], event["event_type"],
                        event["goldstein_scale"], event["tone"],
                        event["num_mentions"], event["num_sources"],
                        event["risk_score"], event["description"],
                        event["url"],
                    ),
                )
                stored += 1
            except Exception as e:
                logger.debug("GDELT event insert error: %s", e)

        logger.info("Stored %d geopolitical events", stored)
