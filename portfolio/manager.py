"""Portfolio manager: state tracking, holdings, sector exposure."""

import logging
from database.models import PortfolioDAO, StockDAO
from database.connection import get_connection
from utils.console import header, separator, ok, fail, neutral
from utils.helpers import format_currency, format_pct
from tabulate import tabulate

logger = logging.getLogger("stock_model.portfolio.manager")


class PortfolioManager:
    """Manages portfolio state and provides status views."""

    def __init__(self):
        self.portfolio_dao = PortfolioDAO()
        self.stock_dao = StockDAO()
        self.db = get_connection()

    def get_holdings(self) -> list[dict]:
        """Get current holdings as list of dicts."""
        rows = self.portfolio_dao.get_latest_holdings()
        return [dict(r) for r in rows] if rows else []

    def get_total_value(self) -> float:
        """Get total portfolio market value."""
        holdings = self.get_holdings()
        return sum(h.get("market_value", 0) or 0 for h in holdings)

    def get_sector_allocation(self) -> dict[str, float]:
        """Get sector weights as percentages."""
        holdings = self.get_holdings()
        total = self.get_total_value()
        if total == 0:
            return {}

        sectors = {}
        for h in holdings:
            sector = h.get("sector") or "Unknown"
            value = h.get("market_value", 0) or 0
            sectors[sector] = sectors.get(sector, 0) + (value / total * 100)

        return dict(sorted(sectors.items(), key=lambda x: -x[1]))

    def get_latest_snapshot(self) -> dict | None:
        """Get most recent portfolio snapshot."""
        row = self.db.execute_one(
            "SELECT * FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        )
        return dict(row) if row else None

    def print_status(self):
        """Print a comprehensive portfolio status report."""
        holdings = self.get_holdings()

        if not holdings:
            print(header("Portfolio Status"))
            print("\n  No holdings found. Run 'python main.py import-portfolio' first.")
            return

        snapshot = self.get_latest_snapshot()
        total_value = self.get_total_value()
        sectors = self.get_sector_allocation()

        # Header
        print(header("PORTFOLIO STATUS"))

        # Account summary
        if snapshot:
            print(f"\n  Total Equity:  {format_currency(snapshot.get('total_equity'))}")
            print(f"  Market Value:  {format_currency(total_value)}")
            print(f"  Cash:          {format_currency(snapshot.get('cash'))}")
            total_pl = snapshot.get("total_pl", 0) or 0
            total_pl_pct = snapshot.get("total_pl_pct", 0) or 0
            pl_fn = ok if total_pl >= 0 else fail
            print(f"  Unrealized P/L: {pl_fn(f'{format_currency(total_pl)} ({format_pct(total_pl_pct)})')}")
            print(f"  Positions:     {snapshot.get('num_positions', len(holdings))}")

        # Holdings table
        print(f"\n{separator()}")
        print("  HOLDINGS:")
        table_data = []
        for h in holdings:
            pl = h.get("unrealized_pl", 0) or 0
            pl_pct = h.get("unrealized_pl_pct", 0) or 0
            weight = (h.get("market_value", 0) or 0) / total_value * 100 if total_value else 0
            table_data.append([
                h["ticker"],
                f"{h.get('quantity', 0):.2f}",
                format_currency(h.get("average_cost")),
                format_currency(h.get("current_price")),
                format_currency(h.get("market_value")),
                f"{pl:+,.2f} ({pl_pct:+.1f}%)",
                f"{weight:.1f}%",
                h.get("sector", "")[:15],
            ])

        headers = ["Ticker", "Shares", "Avg Cost", "Price", "Value", "P/L", "Weight", "Sector"]
        print(tabulate(table_data, headers=headers, tablefmt="simple", stralign="right"))

        # Sector allocation
        print(f"\n{separator()}")
        print("  SECTOR ALLOCATION:")
        for sector, weight in sectors.items():
            bar_len = int(weight / 2)
            bar = "#" * bar_len
            print(f"    {sector:<25} {weight:5.1f}%  {bar}")

        # Risk checks
        print(f"\n{separator()}")
        print("  RISK CHECKS:")
        max_position = max((h.get("market_value", 0) or 0) / total_value * 100 for h in holdings) if holdings and total_value else 0
        max_sector = max(sectors.values()) if sectors else 0
        num_sectors = len(sectors)

        if max_position > 10:
            print(f"    {fail(f'Max position: {max_position:.1f}% (limit: 10%)')}")
        else:
            print(f"    {ok(f'Max position: {max_position:.1f}% (limit: 10%)')}")

        if max_sector > 30:
            print(f"    {fail(f'Max sector: {max_sector:.1f}% (limit: 30%)')}")
        else:
            print(f"    {ok(f'Max sector: {max_sector:.1f}% (limit: 30%)')}")

        if num_sectors < 3:
            print(f"    {fail(f'Sectors: {num_sectors} (min: 3)')}")
        else:
            print(f"    {ok(f'Sectors: {num_sectors} (min: 3)')}")

        print()
