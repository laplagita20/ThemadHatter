"""Scheduler for orchestrating data collection via APScheduler."""

import logging
from datetime import datetime

from collectors.yahoo_finance import YahooFinanceCollector
from collectors.sec_edgar import SECEdgarCollector
from collectors.fred_collector import FREDCollector
from collectors.news_collector import NewsCollector
from collectors.robinhood_collector import RobinhoodCollector
from collectors.gdelt_collector import GDELTCollector
from collectors.alpha_vantage import AlphaVantageCollector
from database.models import StockDAO

logger = logging.getLogger("stock_model.collectors.scheduler")

COLLECTORS = {
    "yahoo": YahooFinanceCollector,
    "sec": SECEdgarCollector,
    "fred": FREDCollector,
    "news": NewsCollector,
    "robinhood": RobinhoodCollector,
    "gdelt": GDELTCollector,
    "alpha_vantage": AlphaVantageCollector,
}


def run_collection(source: str = "all", ticker: str = None):
    """Run data collection for specified source(s)."""
    if source == "all":
        sources = list(COLLECTORS.keys())
    else:
        sources = [source]

    # Get tickers from watchlist if none specified
    tickers = [ticker] if ticker else []
    if not tickers:
        dao = StockDAO()
        stocks = dao.get_all_active()
        tickers = [s["ticker"] for s in stocks]

    for src in sources:
        if src not in COLLECTORS:
            logger.warning("Unknown collector: %s", src)
            continue

        collector_cls = COLLECTORS[src]
        try:
            collector = collector_cls()
            print(f"Running {src} collector...")

            if src in ("fred", "gdelt"):
                # These don't need a ticker
                collector.collect_and_store()
            elif src == "robinhood":
                collector.collect_and_store()
            else:
                for t in tickers:
                    print(f"  Collecting {src} data for {t}...")
                    collector.collect_and_store(t)

            print(f"  {src} collection complete.")
        except Exception as e:
            logger.error("Collector %s failed: %s", src, e, exc_info=True)
            print(f"  {src} collection failed: {e}")


def start_scheduler():
    """Start the APScheduler for continuous data collection (blocking mode for CLI)."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install APScheduler")
        return

    scheduler = BlockingScheduler()
    _add_scheduler_jobs(scheduler, IntervalTrigger, CronTrigger)

    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    print("Data collection scheduler started. Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("Scheduler stopped.")


# Global reference so the background scheduler isn't garbage-collected
_background_scheduler = None


def start_background_scheduler():
    """Start a non-blocking background scheduler (for use inside Streamlit/dashboard).

    Returns the scheduler instance, or None if APScheduler is not installed.
    Safe to call multiple times - only starts once.
    """
    global _background_scheduler
    if _background_scheduler is not None:
        return _background_scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning("APScheduler not installed - background scheduler disabled")
        return None

    _background_scheduler = BackgroundScheduler()
    _add_scheduler_jobs(_background_scheduler, IntervalTrigger, CronTrigger)
    _background_scheduler.start()
    logger.info("Background scheduler started with %d jobs",
                len(_background_scheduler.get_jobs()))
    return _background_scheduler


def _add_scheduler_jobs(scheduler, IntervalTrigger, CronTrigger):
    """Add standard collection jobs to a scheduler instance."""
    # Market hours: prices every 15min
    scheduler.add_job(
        run_collection, IntervalTrigger(minutes=15),
        kwargs={"source": "yahoo"},
        id="yahoo_prices",
        name="Yahoo Finance prices",
    )

    # News every 30min
    scheduler.add_job(
        run_collection, IntervalTrigger(minutes=30),
        kwargs={"source": "news"},
        id="news_feed",
        name="News collection",
    )

    # GDELT every 2hrs
    scheduler.add_job(
        run_collection, IntervalTrigger(hours=2),
        kwargs={"source": "gdelt"},
        id="gdelt_events",
        name="GDELT events",
    )

    # FRED daily at 8am
    scheduler.add_job(
        run_collection, CronTrigger(hour=8, minute=0),
        kwargs={"source": "fred"},
        id="fred_daily",
        name="FRED macro data",
    )

    # SEC daily at 8pm
    scheduler.add_job(
        run_collection, CronTrigger(hour=20, minute=0),
        kwargs={"source": "sec"},
        id="sec_filings",
        name="SEC filings",
    )
