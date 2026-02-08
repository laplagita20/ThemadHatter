"""Risk manager: position sizing, diversification, stop-loss enforcement."""

import logging
from config.settings import get_settings
from database.models import PortfolioDAO

logger = logging.getLogger("stock_model.engine.risk")


class RiskManager:
    """Enforces portfolio risk management rules."""

    def __init__(self):
        self.settings = get_settings()
        self.portfolio_dao = PortfolioDAO()

    def check_position_size(self, ticker: str, proposed_pct: float) -> dict:
        """Check if a proposed position size violates risk rules."""
        max_pct = self.settings.max_single_position_pct
        if proposed_pct > max_pct:
            return {
                "allowed": False,
                "adjusted_pct": max_pct,
                "reason": f"Position size {proposed_pct:.1f}% exceeds max {max_pct:.1f}%",
            }
        return {"allowed": True, "adjusted_pct": proposed_pct, "reason": "Within limits"}

    def check_sector_concentration(self, sector: str) -> dict:
        """Check if adding to a sector would exceed concentration limits."""
        holdings = self.portfolio_dao.get_latest_holdings()
        if not holdings:
            return {"allowed": True, "current_pct": 0, "reason": "No existing holdings"}

        total_value = sum(h["market_value"] or 0 for h in holdings)
        if total_value == 0:
            return {"allowed": True, "current_pct": 0, "reason": "No portfolio value"}

        sector_value = sum(
            h["market_value"] or 0 for h in holdings
            if (h["sector"] or "").lower() == sector.lower()
        )
        sector_pct = (sector_value / total_value) * 100

        max_pct = self.settings.max_single_sector_pct
        if sector_pct >= max_pct:
            return {
                "allowed": False,
                "current_pct": sector_pct,
                "reason": f"Sector {sector} at {sector_pct:.1f}% (max {max_pct:.1f}%)",
            }
        return {"allowed": True, "current_pct": sector_pct, "reason": "Within limits"}

    def check_diversification(self) -> dict:
        """Check if portfolio meets minimum diversification requirements."""
        holdings = self.portfolio_dao.get_latest_holdings()
        if not holdings:
            return {"meets_minimum": False, "num_sectors": 0, "reason": "No holdings"}

        sectors = set(h["sector"] for h in holdings if h["sector"])
        num_sectors = len(sectors)
        min_sectors = self.settings.min_sectors_held

        return {
            "meets_minimum": num_sectors >= min_sectors,
            "num_sectors": num_sectors,
            "sectors": list(sectors),
            "reason": f"{num_sectors} sectors (min {min_sectors})",
        }

    def calculate_stop_loss(self, entry_price: float, conviction: str) -> dict:
        """Calculate stop-loss levels based on conviction."""
        s = self.settings
        if conviction == "high":
            trailing_pct = s.trailing_stop_tactical_pct
        else:
            trailing_pct = s.trailing_stop_core_pct

        return {
            "trailing_stop_pct": trailing_pct,
            "trailing_stop_price": entry_price * (1 - trailing_pct / 100),
            "hard_stop_pct": s.hard_stop_pct,
            "hard_stop_price": entry_price * (1 - s.hard_stop_pct / 100),
        }

    def get_portfolio_risk_summary(self) -> dict:
        """Calculate overall portfolio risk metrics."""
        holdings = self.portfolio_dao.get_latest_holdings()
        if not holdings:
            return {"status": "no_holdings"}

        total_value = sum(h["market_value"] or 0 for h in holdings)
        if total_value == 0:
            return {"status": "no_value"}

        # Position concentrations
        positions = []
        for h in holdings:
            pct = ((h["market_value"] or 0) / total_value) * 100
            positions.append({"ticker": h["ticker"], "weight_pct": pct})

        positions.sort(key=lambda x: x["weight_pct"], reverse=True)

        # Sector concentrations
        sector_weights = {}
        for h in holdings:
            sector = h["sector"] or "Unknown"
            sector_weights[sector] = sector_weights.get(sector, 0) + ((h["market_value"] or 0) / total_value * 100)

        # HHI concentration index
        hhi = sum(p["weight_pct"] ** 2 for p in positions) / 10000

        return {
            "status": "ok",
            "total_value": total_value,
            "num_positions": len(holdings),
            "num_sectors": len(sector_weights),
            "top_positions": positions[:5],
            "sector_weights": dict(sorted(sector_weights.items(), key=lambda x: -x[1])),
            "max_position_pct": positions[0]["weight_pct"] if positions else 0,
            "max_sector_pct": max(sector_weights.values()) if sector_weights else 0,
            "hhi": hhi,
        }
