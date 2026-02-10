"""The Mad Hatter v2 - Professional-Grade Financial Dashboard.

Open-source Bloomberg Terminal-inspired dashboard for stock analysis,
portfolio management, risk assessment, and macro regime detection.

Launch: streamlit run dashboard/app.py
  or:   python main.py dashboard
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st

# Page configuration - must be first Streamlit command
st.set_page_config(
    page_title="The Mad Hatter - Financial Intelligence",
    page_icon="🎩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject Mad Hatter theme
from dashboard.theme import inject_theme, mad_hatter_header
inject_theme()

# Initialize database
from config.settings import get_settings
from database.connection import get_connection
from database.schema import initialize_database

settings = get_settings()
db = get_connection(settings.db_path)
initialize_database(db)

# Auto-refresh (optional) - refreshes page every 60s to pick up live price changes
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60 * 1000, key="auto_refresh")
except ImportError:
    pass

# Start background data scheduler (runs once, safe to call on every rerun)
if not st.session_state.get("_scheduler_started"):
    try:
        from collectors.scheduler import start_background_scheduler
        sched = start_background_scheduler()
        if sched:
            st.session_state["_scheduler_started"] = True
    except Exception:
        pass  # Non-critical - dashboard works without scheduler

# Sidebar branding
mad_hatter_header()

# Learning Mode toggle
from dashboard.components.teach_me import teach_me_sidebar
teach_me_sidebar()

st.sidebar.divider()

page = st.sidebar.radio("Navigation", [
    "Portfolio",
    "Recommendations",
    "Stock Analysis",
    "News",
    "Risk Dashboard",
    "Macro & Market",
    "Stock Screener",
], captions=[
    "Holdings, P&L, DCA",
    "Buy/sell signals & reasoning",
    "Deep-dive single stock",
    "Market-moving headlines",
    "VaR, Monte Carlo, stress tests",
    "Economic regimes, yield curves",
    "Screen & filter stocks",
])

st.sidebar.divider()

# Quick Add to Watchlist
st.sidebar.caption("Quick Add to Watchlist")
new_ticker = st.sidebar.text_input("Ticker", placeholder="NVDA", key="sidebar_add_ticker", label_visibility="collapsed")
if st.sidebar.button("Add to Watchlist", key="sidebar_add_btn"):
    if new_ticker:
        try:
            from utils.validators import validate_ticker
            ticker_upper = validate_ticker(new_ticker)
        except ValueError as e:
            st.sidebar.error(str(e))
            ticker_upper = None
        if ticker_upper:
            try:
                import yfinance as yf
                from database.models import StockDAO
                stock_dao = StockDAO()
                stock = yf.Ticker(ticker_upper)
                info = stock.info
                stock_dao.upsert(
                    ticker=ticker_upper,
                    company_name=info.get("longName", info.get("shortName", "")),
                    sector=info.get("sector", ""),
                    industry=info.get("industry", ""),
                    market_cap=info.get("marketCap"),
                )
                st.sidebar.success(f"Added {ticker_upper}")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Failed: {e}")

st.sidebar.divider()
st.sidebar.caption("System Status")

# Show data freshness with relative timestamps
from datetime import datetime as _dt

def _relative_time(iso_str: str) -> str:
    """Convert an ISO timestamp to a relative 'X ago' string."""
    try:
        dt = _dt.fromisoformat(iso_str.replace("Z", "+00:00").replace("Z", ""))
        diff = _dt.now() - dt
        mins = int(diff.total_seconds() / 60)
        if mins < 1:
            return "just now"
        elif mins < 60:
            return f"{mins}m ago"
        elif mins < 1440:
            return f"{mins // 60}h ago"
        else:
            return f"{mins // 1440}d ago"
    except (ValueError, TypeError):
        return str(iso_str)[:16] if iso_str else "never"

def _freshness_badge(iso_str: str, fresh_hours: int = 6) -> str:
    """Return a colored freshness badge based on data age."""
    try:
        dt = _dt.fromisoformat(iso_str.replace("Z", "+00:00").replace("Z", ""))
        diff = _dt.now() - dt
        hours = diff.total_seconds() / 3600
        if hours < fresh_hours:
            return f":green[{_relative_time(iso_str)}]"
        elif hours < fresh_hours * 4:
            return f":orange[{_relative_time(iso_str)}]"
        else:
            return f":red[{_relative_time(iso_str)}]"
    except (ValueError, TypeError):
        return f":red[{iso_str or 'never'}]"

try:
    stock_count = db.execute_one("SELECT COUNT(*) as c FROM stocks WHERE is_active = 1")
    if stock_count:
        st.sidebar.text(f"Watchlist: {stock_count['c']} stocks")

    holding_count = db.execute_one(
        """SELECT COUNT(DISTINCT ticker) as c FROM portfolio_holdings
           WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM portfolio_holdings)"""
    )
    if holding_count:
        st.sidebar.text(f"Holdings: {holding_count['c']} positions")

    rec_count = db.execute_one(
        "SELECT COUNT(*) as c FROM recurring_investments WHERE is_active = 1"
    )
    if rec_count and rec_count["c"] > 0:
        st.sidebar.text(f"DCA Plans: {rec_count['c']} active")

    # Data freshness badges (green/yellow/red)
    last_decision = db.execute_one("SELECT decided_at FROM decisions ORDER BY decided_at DESC LIMIT 1")
    if last_decision and last_decision.get("decided_at"):
        st.sidebar.markdown(f"Analysis: {_freshness_badge(last_decision['decided_at'], 12)}")

    last_price = db.execute_one("SELECT MAX(date) as d FROM price_history")
    if last_price and last_price.get("d"):
        st.sidebar.markdown(f"Prices: {_freshness_badge(last_price['d'], 24)}")

    last_news = db.execute_one("SELECT MAX(fetched_at) as d FROM news_articles")
    if last_news and last_news.get("d"):
        st.sidebar.markdown(f"News: {_freshness_badge(last_news['d'], 6)}")

    last_macro = db.execute_one("SELECT MAX(date) as d FROM macro_indicators")
    if last_macro and last_macro.get("d"):
        st.sidebar.markdown(f"Macro: {_freshness_badge(last_macro['d'], 48)}")
except Exception:
    pass

st.sidebar.divider()
st.sidebar.caption("Quick Actions")
col_act1, col_act2 = st.sidebar.columns(2)
with col_act1:
    if st.button("Collect Data", key="collect_all_btn"):
        collection_status = st.sidebar.empty()
        sources = ["Yahoo Finance", "FRED", "News", "Alpha Vantage"]
        progress_bar = st.sidebar.progress(0)
        for i, source_name in enumerate(sources):
            collection_status.info(f"Collecting {source_name}...")
            progress_bar.progress((i + 1) / len(sources))
        try:
            from collectors.scheduler import run_collection
            run_collection(source="all")
            collection_status.success("Collection complete")
        except Exception as e:
            collection_status.error(f"Collection failed: {e}")
        progress_bar.empty()
with col_act2:
    if st.button("Refresh Prices", key="refresh_prices_btn"):
        # Clear cached prices to force immediate refresh
        for key in ["live_prices", "live_prices_ts"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

# Route to pages
if page == "Portfolio":
    from dashboard.views.portfolio import render
    render()
elif page == "Recommendations":
    from dashboard.views.recommendations import render
    render()
elif page == "Stock Analysis":
    from dashboard.views.analyzer import render
    render()
elif page == "News":
    from dashboard.views.news import render
    render()
elif page == "Risk Dashboard":
    from dashboard.views.risk import render
    render()
elif page == "Macro & Market":
    from dashboard.views.macro import render
    render()
elif page == "Stock Screener":
    from dashboard.views.screener import render
    render()
