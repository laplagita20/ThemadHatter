"""Portfolio rebalancer: risk-based and signal-based rebalancing recommendations."""

import logging
from database.models import PortfolioDAO, StockDAO
from database.connection import get_connection
from engine.risk_manager import RiskManager
from utils.console import header, separator, ok, fail, neutral
from utils.helpers import format_currency
from tabulate import tabulate

logger = logging.getLogger("stock_model.portfolio.rebalancer")


class Rebalancer:
    """Generates rebalancing recommendations based on risk rules and signals."""

    def __init__(self):
        self.portfolio_dao = PortfolioDAO()
        self.stock_dao = StockDAO()
        self.risk_manager = RiskManager()
        self.db = get_connection()

    def generate_recommendations(self) -> list[dict]:
        """Generate rebalancing recommendations."""
        holdings = self.portfolio_dao.get_latest_holdings()
        if not holdings:
            return []

        holdings = list(holdings)
        total_value = sum(h["market_value"] or 0 for h in holdings)
        if total_value == 0:
            return []

        recommendations = []
        priority = 0

        # Check position size limits
        for h in holdings:
            weight = ((h["market_value"] or 0) / total_value) * 100
            if weight > 10:
                excess_pct = weight - 10
                excess_value = (excess_pct / 100) * total_value
                shares_to_sell = excess_value / h["current_price"] if h["current_price"] else 0
                priority += 1
                recommendations.append({
                    "ticker": h["ticker"],
                    "action": "TRIM",
                    "current_weight": round(weight, 2),
                    "target_weight": 10.0,
                    "shares_to_trade": round(-shares_to_sell, 2),
                    "reason": f"Position exceeds 10% limit ({weight:.1f}% -> 10%)",
                    "priority": priority,
                })

        # Check sector concentration
        sector_weights = {}
        for h in holdings:
            sector = h.get("sector") or "Unknown"
            sector_weights[sector] = sector_weights.get(sector, 0) + ((h["market_value"] or 0) / total_value * 100)

        for sector, weight in sector_weights.items():
            if weight > 30:
                priority += 1
                # Find largest position in sector to trim
                sector_holdings = [h for h in holdings if (h.get("sector") or "Unknown") == sector]
                sector_holdings.sort(key=lambda x: x["market_value"] or 0, reverse=True)
                if sector_holdings:
                    top = sector_holdings[0]
                    recommendations.append({
                        "ticker": top["ticker"],
                        "action": "TRIM (sector)",
                        "current_weight": round((top["market_value"] or 0) / total_value * 100, 2),
                        "target_weight": None,
                        "shares_to_trade": None,
                        "reason": f"{sector} sector at {weight:.1f}% (limit: 30%). Trim largest holding.",
                        "priority": priority,
                    })

        # Check diversification
        num_sectors = len([s for s in sector_weights if sector_weights[s] > 0])
        if num_sectors < 3:
            priority += 1
            recommendations.append({
                "ticker": "PORTFOLIO",
                "action": "DIVERSIFY",
                "current_weight": None,
                "target_weight": None,
                "shares_to_trade": None,
                "reason": f"Only {num_sectors} sectors. Add positions in underrepresented sectors.",
                "priority": priority,
            })

        # Signal-based recommendations (check latest decisions)
        for h in holdings:
            decision = self.db.execute_one(
                """SELECT * FROM decisions WHERE ticker = ?
                   ORDER BY decided_at DESC LIMIT 1""",
                (h["ticker"],),
            )
            if decision:
                weight = ((h["market_value"] or 0) / total_value) * 100
                if decision["action"] in ("STRONG_SELL", "SELL") and weight > 2:
                    priority += 1
                    recommendations.append({
                        "ticker": h["ticker"],
                        "action": f"REDUCE ({decision['action']})",
                        "current_weight": round(weight, 2),
                        "target_weight": max(0, weight - 3),
                        "shares_to_trade": None,
                        "reason": f"Analysis signal: {decision['action']} (score: {decision['composite_score']:+.0f})",
                        "priority": priority,
                    })
                elif decision["action"] in ("STRONG_BUY", "BUY") and weight < 8:
                    target = min(8, decision.get("position_size_pct", 5) or 5)
                    if target > weight + 1:
                        priority += 1
                        recommendations.append({
                            "ticker": h["ticker"],
                            "action": f"INCREASE ({decision['action']})",
                            "current_weight": round(weight, 2),
                            "target_weight": round(target, 2),
                            "shares_to_trade": None,
                            "reason": f"Analysis signal: {decision['action']} (score: {decision['composite_score']:+.0f})",
                            "priority": priority,
                        })

        # Store recommendations
        for rec in recommendations:
            try:
                self.db.execute_insert(
                    """INSERT INTO rebalance_recommendations
                       (ticker, action, current_weight, target_weight,
                        shares_to_trade, reason, priority)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (rec["ticker"], rec["action"], rec.get("current_weight"),
                     rec.get("target_weight"), rec.get("shares_to_trade"),
                     rec["reason"], rec["priority"]),
                )
            except Exception:
                pass

        return sorted(recommendations, key=lambda x: x["priority"])

    def print_recommendations(self):
        """Print formatted rebalancing recommendations."""
        print(header("REBALANCING RECOMMENDATIONS"))

        recs = self.generate_recommendations()
        if not recs:
            print(f"\n  {ok('Portfolio is within all risk limits. No rebalancing needed.')}")
            return

        print(f"\n  Found {len(recs)} recommendation(s):\n")

        table_data = []
        for rec in recs:
            table_data.append([
                rec["priority"],
                rec["ticker"],
                rec["action"],
                f"{rec['current_weight']:.1f}%" if rec.get("current_weight") is not None else "-",
                f"{rec['target_weight']:.1f}%" if rec.get("target_weight") is not None else "-",
                rec["reason"],
            ])

        headers = ["#", "Ticker", "Action", "Current", "Target", "Reason"]
        print(tabulate(table_data, headers=headers, tablefmt="simple"))

        print(f"\n  Note: These are recommendations only. Review before executing trades.")
        print()
