"""Geopolitical analysis: GDELT risk scoring by country/sector."""

import logging
from analysis.base_analyzer import BaseAnalyzer, AnalysisResult, AnalysisFactor
from database.connection import get_connection
from database.models import StockDAO

logger = logging.getLogger("stock_model.analysis.geopolitical")

# Country revenue exposure for major US stocks (simplified mapping)
COUNTRY_EXPOSURE = {
    "Technology": {"US": 0.45, "China": 0.20, "Europe": 0.20, "Asia_Other": 0.15},
    "Information Technology": {"US": 0.45, "China": 0.20, "Europe": 0.20, "Asia_Other": 0.15},
    "Healthcare": {"US": 0.55, "Europe": 0.25, "China": 0.10, "Asia_Other": 0.10},
    "Health Care": {"US": 0.55, "Europe": 0.25, "China": 0.10, "Asia_Other": 0.10},
    "Financials": {"US": 0.65, "Europe": 0.20, "Asia_Other": 0.15},
    "Financial Services": {"US": 0.65, "Europe": 0.20, "Asia_Other": 0.15},
    "Consumer Discretionary": {"US": 0.50, "China": 0.15, "Europe": 0.20, "Asia_Other": 0.15},
    "Consumer Cyclical": {"US": 0.50, "China": 0.15, "Europe": 0.20, "Asia_Other": 0.15},
    "Energy": {"US": 0.40, "Middle_East": 0.20, "Europe": 0.20, "Asia_Other": 0.20},
    "Industrials": {"US": 0.50, "Europe": 0.25, "China": 0.15, "Asia_Other": 0.10},
    "Materials": {"US": 0.40, "China": 0.25, "Europe": 0.20, "Asia_Other": 0.15},
    "Basic Materials": {"US": 0.40, "China": 0.25, "Europe": 0.20, "Asia_Other": 0.15},
}

# Risk categories and their event type mappings
RISK_CATEGORIES = {
    "trade": ["trade", "tariff", "sanctions", "embargo"],
    "military": ["military", "conflict", "war", "attack"],
    "regulatory": ["regulation", "antitrust", "ban", "restriction"],
    "supply_chain": ["supply", "shortage", "disruption", "logistics"],
    "currency": ["currency", "devaluation", "forex", "exchange rate"],
}


class GeopoliticalAnalyzer(BaseAnalyzer):
    """Analyzes geopolitical risks and their impact on specific stocks."""

    name = "geopolitical"

    def __init__(self):
        self.db = get_connection()
        self.stock_dao = StockDAO()

    def analyze(self, ticker: str, data: dict = None) -> AnalysisResult:
        logger.info("Running geopolitical analysis for %s", ticker)
        factors = []
        score = 0.0

        stock = self.stock_dao.get(ticker)
        sector = stock["sector"] if stock and stock["sector"] else "Unknown"
        country = stock["country"] if stock and stock["country"] else "US"

        # Get recent geopolitical events
        events = self.db.execute(
            """SELECT * FROM geopolitical_events
               WHERE event_date >= date('now', '-30 days')
               ORDER BY risk_score DESC LIMIT 200"""
        )

        if not events:
            return self._make_result(0, 0.2, [],
                "No recent geopolitical events in database. Run GDELT collection first.")

        events = list(events)

        # Get country exposure for this sector
        exposure = COUNTRY_EXPOSURE.get(sector, {"US": 0.70, "Europe": 0.15, "Asia_Other": 0.15})

        # Analyze events by risk category
        category_risks = {}
        for category, keywords in RISK_CATEGORIES.items():
            cat_events = [
                e for e in events
                if any(kw in (e["event_type"] or "").lower() or kw in (e["description"] or "").lower()
                       for kw in keywords)
            ]
            if cat_events:
                avg_risk = sum(e["risk_score"] or 0 for e in cat_events) / len(cat_events)
                avg_tone = sum(e["tone"] or 0 for e in cat_events) / len(cat_events)
                category_risks[category] = {
                    "count": len(cat_events),
                    "avg_risk": avg_risk,
                    "avg_tone": avg_tone,
                }

        # Score each risk category
        for category, risk_data in category_risks.items():
            avg_risk = risk_data["avg_risk"]
            count = risk_data["count"]

            # Weight by relevance to sector
            sector_weight = self._get_sector_risk_weight(sector, category)

            if avg_risk > 70:
                impact = -15 * sector_weight
                level = "high"
            elif avg_risk > 50:
                impact = -8 * sector_weight
                level = "moderate"
            elif avg_risk > 30:
                impact = -3 * sector_weight
                level = "low"
            else:
                impact = 0
                level = "minimal"

            impact = round(impact)
            if impact != 0:
                score += impact
                factors.append(AnalysisFactor(
                    f"{category.replace('_', ' ').title()} Risk",
                    f"{level} ({count} events, avg risk: {avg_risk:.0f})",
                    impact,
                    f"{category.replace('_', ' ').title()} risk is {level} with {count} recent events (sector weight: {sector_weight:.1f}x)"
                ))

        # Overall global risk level
        if events:
            global_avg_risk = sum(e["risk_score"] or 0 for e in events) / len(events)
            global_avg_tone = sum(e["tone"] or 0 for e in events) / len(events)

            if global_avg_risk > 60:
                impact = -10
                explanation = f"Global risk elevated (avg: {global_avg_risk:.0f}, tone: {global_avg_tone:.1f})"
            elif global_avg_risk > 40:
                impact = -3
                explanation = f"Global risk moderate (avg: {global_avg_risk:.0f})"
            else:
                impact = 5
                explanation = f"Global risk low (avg: {global_avg_risk:.0f}) - stable environment"

            score += impact
            factors.append(AnalysisFactor(
                "Global Risk Level", f"{global_avg_risk:.0f}/100",
                impact, explanation))

        # Country-specific risk (based on exposure)
        for region, weight in exposure.items():
            if weight < 0.1:
                continue
            region_events = [
                e for e in events
                if region.lower() in (e["source_country"] or "").lower()
                or region.lower() in (e["description"] or "").lower()
            ]
            if region_events:
                region_risk = sum(e["risk_score"] or 0 for e in region_events) / len(region_events)
                if region_risk > 60 and weight > 0.15:
                    impact = round(-8 * weight)
                    score += impact
                    factors.append(AnalysisFactor(
                        f"{region} Exposure Risk",
                        f"{weight*100:.0f}% revenue, risk: {region_risk:.0f}",
                        impact,
                        f"Elevated risk in {region} where {sector} has {weight*100:.0f}% revenue exposure"
                    ))

        confidence = min(0.7, 0.2 + len(events) / 100 * 0.3 + len(factors) / 5 * 0.2)
        summary = f"Geopolitical risk is {'elevated' if score < -15 else 'moderate' if score < -5 else 'low'} for {sector} stocks"
        return self._make_result(score, confidence, factors, summary)

    def _get_sector_risk_weight(self, sector: str, category: str) -> float:
        """How sensitive is this sector to this risk category."""
        weights = {
            "Technology": {"trade": 1.5, "military": 0.5, "regulatory": 1.3, "supply_chain": 1.4, "currency": 0.8},
            "Information Technology": {"trade": 1.5, "military": 0.5, "regulatory": 1.3, "supply_chain": 1.4, "currency": 0.8},
            "Energy": {"trade": 1.2, "military": 1.5, "regulatory": 1.0, "supply_chain": 1.3, "currency": 1.2},
            "Financials": {"trade": 0.8, "military": 0.7, "regulatory": 1.5, "supply_chain": 0.3, "currency": 1.4},
            "Financial Services": {"trade": 0.8, "military": 0.7, "regulatory": 1.5, "supply_chain": 0.3, "currency": 1.4},
            "Industrials": {"trade": 1.3, "military": 0.8, "regulatory": 0.8, "supply_chain": 1.5, "currency": 1.0},
            "Healthcare": {"trade": 0.7, "military": 0.3, "regulatory": 1.5, "supply_chain": 1.0, "currency": 0.6},
            "Health Care": {"trade": 0.7, "military": 0.3, "regulatory": 1.5, "supply_chain": 1.0, "currency": 0.6},
        }
        sector_weights = weights.get(sector, {})
        return sector_weights.get(category, 1.0)
