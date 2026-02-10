"""Stock Model - Portfolio Management System CLI."""

import argparse
import sys
import logging

from config.settings import get_settings
from config.logging_config import setup_logging
from database.connection import get_connection
from database.schema import initialize_database
from utils.console import header, separator


def cmd_analyze(args):
    """Analyze a single stock."""
    from utils.validators import validate_ticker
    from engine.decision_engine import DecisionEngine
    ticker = validate_ticker(args.ticker)
    engine = DecisionEngine()
    decision = engine.analyze(ticker)
    engine.print_decision(decision)


def cmd_analyze_portfolio(args):
    """Analyze all holdings in the portfolio."""
    from engine.decision_engine import DecisionEngine
    from database.models import PortfolioDAO

    dao = PortfolioDAO()
    holdings = dao.get_latest_holdings()
    if not holdings:
        print("No portfolio holdings found. Run 'import-portfolio' first.")
        return

    engine = DecisionEngine()
    for h in holdings:
        print(header(f"Analyzing {h['ticker']}"))
        decision = engine.analyze(h["ticker"])
        engine.print_decision(decision)


def cmd_import_portfolio(args):
    """Import portfolio from Robinhood."""
    from portfolio.importer import import_robinhood_portfolio
    import_robinhood_portfolio()


def cmd_portfolio_status(args):
    """Show current portfolio status."""
    from portfolio.manager import PortfolioManager
    mgr = PortfolioManager()
    mgr.print_status()


def cmd_performance(args):
    """Show portfolio performance metrics."""
    from portfolio.performance import PerformanceTracker
    tracker = PerformanceTracker()
    tracker.print_report(period=args.period)


def cmd_rebalance(args):
    """Generate rebalancing recommendations."""
    from portfolio.rebalancer import Rebalancer
    rebalancer = Rebalancer()
    rebalancer.print_recommendations()


def cmd_collect(args):
    """Run data collection for a specific source or all."""
    from collectors.scheduler import run_collection
    ticker = args.ticker
    if ticker:
        from utils.validators import validate_ticker
        ticker = validate_ticker(ticker)
    run_collection(source=args.source, ticker=ticker)


def cmd_track_outcomes(args):
    """Update outcome tracking for past decisions."""
    from learning.outcome_tracker import OutcomeTracker
    tracker = OutcomeTracker()
    tracker.update_all()


def cmd_accuracy_report(args):
    """Show analyzer accuracy report."""
    from learning.accuracy_tracker import AccuracyTracker
    tracker = AccuracyTracker()
    tracker.print_report()


def cmd_backtest(args):
    """Run backtest on historical data."""
    from learning.backtester import Backtester
    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    bt = Backtester()
    bt.run(tickers=tickers, start_date=args.start, end_date=args.end)


def cmd_optimize_weights(args):
    """Run weight optimization."""
    from learning.weight_optimizer import WeightOptimizer
    optimizer = WeightOptimizer()
    optimizer.optimize(auto_approve=args.auto)


def cmd_risk_report(args):
    """Generate comprehensive risk report."""
    from engine.risk_manager import RiskManager
    rm = RiskManager()
    rm.print_risk_report()


def cmd_dashboard(args):
    """Launch the Streamlit dashboard."""
    import subprocess
    import os
    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "app.py")
    print(f"Launching dashboard: streamlit run {dashboard_path}")
    subprocess.run(["streamlit", "run", dashboard_path], check=True)


def cmd_watchlist(args):
    """Manage the stock watchlist."""
    from database.models import StockDAO
    from utils.validators import validate_ticker
    dao = StockDAO()

    if args.add:
        import yfinance as yf
        for ticker in args.add:
            ticker = validate_ticker(ticker)
            stock = yf.Ticker(ticker)
            info = stock.info
            dao.upsert(
                ticker=ticker,
                company_name=info.get("longName", info.get("shortName", "")),
                sector=info.get("sector", ""),
                industry=info.get("industry", ""),
                market_cap=info.get("marketCap"),
            )
            print(f"Added {ticker} ({info.get('longName', 'Unknown')})")
    elif args.remove:
        for ticker in args.remove:
            ticker = validate_ticker(ticker)
            db = get_connection()
            db.execute("UPDATE stocks SET is_active = 0 WHERE ticker = ?", (ticker,))
            print(f"Removed {ticker} from watchlist")
    else:
        stocks = dao.get_watchlist()
        if not stocks:
            print("Watchlist is empty. Add stocks with: python main.py watchlist --add AAPL MSFT")
            return
        print(header("Watchlist"))
        for s in stocks:
            print(f"  {s['ticker']:<8} {s['company_name'] or '':<30} {s['sector'] or ''}")


def main():
    settings = get_settings()
    logger = setup_logging(settings.log_dir, settings.log_level)

    # Initialize database
    db = get_connection(settings.db_path)
    initialize_database(db)

    parser = argparse.ArgumentParser(
        prog="stock_model",
        description="Portfolio Management System - Professional stock analysis and portfolio management",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze a stock")
    p_analyze.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL)")
    p_analyze.set_defaults(func=cmd_analyze)

    # analyze-portfolio
    p_ap = subparsers.add_parser("analyze-portfolio", help="Analyze all portfolio holdings")
    p_ap.set_defaults(func=cmd_analyze_portfolio)

    # import-portfolio
    p_imp = subparsers.add_parser("import-portfolio", help="Import Robinhood portfolio")
    p_imp.set_defaults(func=cmd_import_portfolio)

    # portfolio-status
    p_ps = subparsers.add_parser("portfolio-status", help="Show portfolio status")
    p_ps.set_defaults(func=cmd_portfolio_status)

    # performance
    p_perf = subparsers.add_parser("performance", help="Show performance metrics")
    p_perf.add_argument("--period", default="3M", help="Time period (1M, 3M, 6M, 1Y)")
    p_perf.set_defaults(func=cmd_performance)

    # rebalance
    p_reb = subparsers.add_parser("rebalance", help="Generate rebalancing recommendations")
    p_reb.set_defaults(func=cmd_rebalance)

    # collect
    p_col = subparsers.add_parser("collect", help="Run data collection")
    p_col.add_argument("--source", default="all", help="Data source (yahoo, sec, fred, news, robinhood, gdelt, alpha_vantage, all)")
    p_col.add_argument("--ticker", help="Specific ticker to collect for")
    p_col.set_defaults(func=cmd_collect)

    # watchlist
    p_wl = subparsers.add_parser("watchlist", help="Manage stock watchlist")
    p_wl.add_argument("--add", nargs="+", help="Add tickers to watchlist")
    p_wl.add_argument("--remove", nargs="+", help="Remove tickers from watchlist")
    p_wl.set_defaults(func=cmd_watchlist)

    # track-outcomes
    p_to = subparsers.add_parser("track-outcomes", help="Update outcome tracking")
    p_to.set_defaults(func=cmd_track_outcomes)

    # accuracy-report
    p_ar = subparsers.add_parser("accuracy-report", help="Show analyzer accuracy")
    p_ar.set_defaults(func=cmd_accuracy_report)

    # backtest
    p_bt = subparsers.add_parser("backtest", help="Run backtest")
    p_bt.add_argument("--tickers", required=True, help="Comma-separated tickers")
    p_bt.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    p_bt.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    p_bt.set_defaults(func=cmd_backtest)

    # optimize-weights
    p_ow = subparsers.add_parser("optimize-weights", help="Run weight optimization")
    p_ow.add_argument("--auto", action="store_true", help="Auto-approve (skip confirmation)")
    p_ow.set_defaults(func=cmd_optimize_weights)

    # risk-report
    p_rr = subparsers.add_parser("risk-report", help="Generate comprehensive risk report")
    p_rr.set_defaults(func=cmd_risk_report)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Launch Streamlit web dashboard")
    p_dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        logger.error("Command failed: %s", e, exc_info=True)
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
