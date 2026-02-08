"""Robinhood collector: portfolio holdings, positions, account info."""

import logging
from datetime import datetime

from collectors.base_collector import BaseCollector
from database.models import PortfolioDAO
from database.connection import get_connection

logger = logging.getLogger("stock_model.collectors.robinhood")


class RobinhoodCollector(BaseCollector):
    """Collects portfolio data from Robinhood via robin_stocks."""

    name = "robinhood"
    rate_limit = 1.0
    rate_period = 1.0

    def __init__(self):
        super().__init__()
        self.portfolio_dao = PortfolioDAO()
        self.db = get_connection()
        self._logged_in = False

    def _login(self):
        """Authenticate with Robinhood."""
        if self._logged_in:
            return

        import robin_stocks.robinhood as rh

        username = self.settings.robinhood_username
        password = self.settings.robinhood_password
        totp = self.settings.robinhood_totp_secret

        if not username or not password:
            raise ValueError("Robinhood credentials not set in .env")

        if totp:
            import pyotp
            totp_code = pyotp.TOTP(totp).now()
            rh.login(username, password, mfa_code=totp_code)
        else:
            rh.login(username, password)

        self._logged_in = True
        logger.info("Logged in to Robinhood")

    def collect(self, ticker: str = None) -> dict:
        """Collect all portfolio data from Robinhood."""
        logger.info("Collecting Robinhood portfolio data")
        self._login()

        import robin_stocks.robinhood as rh

        # Get holdings
        holdings_raw = self._cached_call(
            "rh_holdings",
            lambda: rh.build_holdings(),
            ttl=300,
        )

        # Get account info
        account = self._cached_call(
            "rh_account",
            lambda: rh.load_portfolio_profile(),
            ttl=300,
        )

        # Get order history
        orders = self._cached_call(
            "rh_orders",
            lambda: rh.get_all_stock_orders(),
            ttl=600,
        )

        # Parse holdings
        holdings = []
        for ticker_sym, data in (holdings_raw or {}).items():
            holdings.append({
                "ticker": ticker_sym,
                "quantity": float(data.get("quantity", 0)),
                "average_cost": float(data.get("average_buy_price", 0)),
                "current_price": float(data.get("price", 0)),
                "market_value": float(data.get("equity", 0)),
                "unrealized_pl": float(data.get("equity_change", 0)),
                "unrealized_pl_pct": float(data.get("percent_change", 0)),
                "sector": data.get("sector", ""),
            })

        # Parse account
        account_data = {}
        if account:
            account_data = {
                "total_equity": float(account.get("equity", 0)),
                "cash": float(account.get("withdrawable_amount", 0)),
                "market_value": float(account.get("market_value", 0)),
            }

        # Parse recent orders
        transactions = []
        for order in (orders or [])[:100]:
            if order.get("state") != "filled":
                continue
            for exec_data in order.get("executions", []):
                transactions.append({
                    "ticker": order.get("symbol", ""),
                    "side": order.get("side", ""),
                    "quantity": float(exec_data.get("quantity", 0)),
                    "price": float(exec_data.get("price", 0)),
                    "total": float(exec_data.get("quantity", 0)) * float(exec_data.get("price", 0)),
                    "executed_at": exec_data.get("timestamp"),
                    "order_type": order.get("type", ""),
                })

        return {
            "holdings": holdings,
            "account": account_data,
            "transactions": transactions,
        }

    def store(self, data: dict):
        holdings = data.get("holdings", [])
        account = data.get("account", {})
        transactions = data.get("transactions", [])

        if holdings:
            self.portfolio_dao.snapshot_holdings(holdings)
            logger.info("Stored %d portfolio holdings", len(holdings))

        if account:
            total_pl = sum(h.get("unrealized_pl", 0) for h in holdings)
            total_equity = account.get("total_equity", 0)
            total_pl_pct = (total_pl / total_equity * 100) if total_equity else 0

            self.portfolio_dao.insert_snapshot(
                total_equity=total_equity,
                cash=account.get("cash", 0),
                total_pl=total_pl,
                total_pl_pct=total_pl_pct,
                num_positions=len(holdings),
            )

        for tx in transactions:
            try:
                self.db.execute_insert(
                    """INSERT OR IGNORE INTO portfolio_transactions
                       (ticker, side, quantity, price, total, executed_at, order_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (tx["ticker"], tx["side"], tx["quantity"], tx["price"],
                     tx["total"], tx["executed_at"], tx["order_type"]),
                )
            except Exception as e:
                logger.debug("Transaction insert skipped: %s", e)

        if transactions:
            logger.info("Stored %d transactions", len(transactions))
