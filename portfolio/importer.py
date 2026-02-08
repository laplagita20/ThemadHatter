"""Portfolio importer: Robinhood import via robin_stocks."""

import logging
from database.models import PortfolioDAO, StockDAO
from config.settings import get_settings
from utils.console import ok, fail, header

logger = logging.getLogger("stock_model.portfolio.importer")


def import_robinhood_portfolio():
    """Authenticate and import portfolio from Robinhood."""
    settings = get_settings()
    print(header("Importing Robinhood Portfolio"))

    if not settings.robinhood_username or not settings.robinhood_password:
        print(fail("Robinhood credentials not set in .env file"))
        print("  Set ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD in your .env file")
        return

    try:
        import robin_stocks.robinhood as rh
    except ImportError:
        print(fail("robin_stocks not installed. Run: pip install robin-stocks"))
        return

    # Login
    print("  Authenticating with Robinhood...")
    try:
        if settings.robinhood_totp_secret:
            import pyotp
            totp = pyotp.TOTP(settings.robinhood_totp_secret).now()
            rh.login(settings.robinhood_username, settings.robinhood_password, mfa_code=totp)
        else:
            rh.login(settings.robinhood_username, settings.robinhood_password)
        print(ok("Authenticated successfully"))
    except Exception as e:
        print(fail(f"Authentication failed: {e}"))
        return

    portfolio_dao = PortfolioDAO()
    stock_dao = StockDAO()

    # Import holdings
    print("\n  Fetching holdings...")
    try:
        holdings_raw = rh.build_holdings()
        holdings = []
        for ticker, data in holdings_raw.items():
            holding = {
                "ticker": ticker,
                "quantity": float(data.get("quantity", 0)),
                "average_cost": float(data.get("average_buy_price", 0)),
                "current_price": float(data.get("price", 0)),
                "market_value": float(data.get("equity", 0)),
                "unrealized_pl": float(data.get("equity_change", 0)),
                "unrealized_pl_pct": float(data.get("percent_change", 0)),
                "sector": data.get("sector", ""),
            }
            holdings.append(holding)

            # Also add to stocks watchlist
            stock_dao.upsert(
                ticker=ticker,
                company_name=data.get("name", ""),
                sector=data.get("sector", ""),
            )
            print(f"    {ok(ticker)}: {holding['quantity']} shares @ ${holding['average_cost']:.2f} "
                  f"(${holding['market_value']:.2f}, {holding['unrealized_pl_pct']:+.1f}%)")

        portfolio_dao.snapshot_holdings(holdings)
        print(f"\n  {ok(f'Imported {len(holdings)} holdings')}")
    except Exception as e:
        print(fail(f"Failed to fetch holdings: {e}"))
        logger.error("Holdings import failed: %s", e, exc_info=True)

    # Import account summary
    print("\n  Fetching account info...")
    try:
        profile = rh.load_portfolio_profile()
        total_equity = float(profile.get("equity", 0))
        cash = float(profile.get("withdrawable_amount", 0))
        market_value = float(profile.get("market_value", 0))

        total_pl = sum(h.get("unrealized_pl", 0) for h in holdings) if holdings else 0
        total_pl_pct = (total_pl / total_equity * 100) if total_equity else 0

        portfolio_dao.insert_snapshot(
            total_equity=total_equity,
            cash=cash,
            total_pl=total_pl,
            total_pl_pct=total_pl_pct,
            num_positions=len(holdings) if holdings else 0,
        )
        print(f"    Total Equity: ${total_equity:,.2f}")
        print(f"    Cash: ${cash:,.2f}")
        print(f"    Market Value: ${market_value:,.2f}")
        print(f"    Unrealized P/L: ${total_pl:,.2f} ({total_pl_pct:+.1f}%)")
    except Exception as e:
        print(fail(f"Failed to fetch account info: {e}"))

    # Import order history
    print("\n  Fetching order history...")
    try:
        orders = rh.get_all_stock_orders()
        from database.connection import get_connection
        db = get_connection()
        count = 0
        for order in (orders or []):
            if order.get("state") != "filled":
                continue
            for exc in order.get("executions", []):
                try:
                    db.execute_insert(
                        """INSERT OR IGNORE INTO portfolio_transactions
                           (ticker, side, quantity, price, total, executed_at, order_type)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            order.get("symbol", ""),
                            order.get("side", ""),
                            float(exc.get("quantity", 0)),
                            float(exc.get("price", 0)),
                            float(exc.get("quantity", 0)) * float(exc.get("price", 0)),
                            exc.get("timestamp"),
                            order.get("type", ""),
                        ),
                    )
                    count += 1
                except Exception:
                    pass
        print(f"    {ok(f'Imported {count} transactions')}")
    except Exception as e:
        print(fail(f"Failed to fetch orders: {e}"))

    print(f"\n{ok('Portfolio import complete!')}")
    try:
        rh.logout()
    except Exception:
        pass
