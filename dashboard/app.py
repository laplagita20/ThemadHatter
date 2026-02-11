"""The Mad Hatter v3 - AI-Powered Financial Advisor.

Robinhood-inspired dashboard with AI insights, portfolio management,
risk assessment, and macro regime detection.

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
    page_title="The Mad Hatter - AI Financial Advisor",
    page_icon="\U0001f3a9",
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

# Auth gate - must login before accessing anything
from dashboard.components.auth import login_register_page, logout_button, get_current_user_id

if not login_register_page():
    st.stop()

# Onboarding gate — new users must complete onboarding first
_uid = get_current_user_id()
if _uid:
    from database.models import UserPreferencesDAO as _PrefDAO
    _prefs = _PrefDAO().get(_uid)
    if not _prefs.get("onboarding_completed"):
        from dashboard.views.onboarding import render as _onboarding_render
        _onboarding_render()
        st.stop()

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

# Logout button + user info
logout_button()

st.sidebar.divider()

# Navigation — 6 pages (reduced from 8)
PAGES = [
    "Home",
    "Advisor",
    "Portfolio",
    "Discover",
    "Analysis",
    "Settings",
]
PAGE_CAPTIONS = [
    "AI insights & portfolio overview",
    "Chat with AI, stock explainer",
    "Holdings, P&L, DCA",
    "Scanner, top picks, watchlist, news",
    "Stock deep-dive, risk & macro",
    "Preferences & API keys",
]

# Handle nav_target from quick action buttons
default_idx = 0
nav_target = st.session_state.pop("nav_target", None)
if nav_target and nav_target in PAGES:
    default_idx = PAGES.index(nav_target)

page = st.sidebar.radio("Navigation", PAGES, captions=PAGE_CAPTIONS, index=default_idx)

st.sidebar.divider()

# Collapsed System section
with st.sidebar.expander("System", expanded=False):
    # Data freshness with relative timestamps
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
        from database.models import UserWatchlistDAO as _UWL
        _wl_count = len(_UWL().get_tickers(_uid)) if _uid else 0
        st.text(f"Watchlist: {_wl_count} stocks")

        holding_count = db.execute_one(
            """SELECT COUNT(DISTINCT ticker) as c FROM portfolio_holdings
               WHERE user_id = ? AND snapshot_date = (
                   SELECT MAX(snapshot_date) FROM portfolio_holdings WHERE user_id = ?
               )""",
            (_uid, _uid),
        )
        if holding_count:
            st.text(f"Holdings: {holding_count['c']} positions")

        last_decision = db.execute_one("SELECT decided_at FROM decisions ORDER BY decided_at DESC LIMIT 1")
        if last_decision and last_decision.get("decided_at"):
            st.markdown(f"Analysis: {_freshness_badge(last_decision['decided_at'], 12)}")

        last_price = db.execute_one("SELECT MAX(date) as d FROM price_history")
        if last_price and last_price.get("d"):
            st.markdown(f"Prices: {_freshness_badge(last_price['d'], 24)}")

        last_news = db.execute_one("SELECT MAX(fetched_at) as d FROM news_articles")
        if last_news and last_news.get("d"):
            st.markdown(f"News: {_freshness_badge(last_news['d'], 6)}")
    except Exception:
        pass

    st.divider()

    col_act1, col_act2 = st.columns(2)
    with col_act1:
        if st.button("Collect Data", key="collect_all_btn"):
            collection_status = st.empty()
            sources = ["Yahoo Finance", "FRED", "News", "Alpha Vantage"]
            progress_bar = st.progress(0)
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
            for key in ["live_prices", "live_prices_ts"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

# Route to pages
if page == "Home":
    from dashboard.views.home import render
    render()
elif page == "Advisor":
    from dashboard.views.advisor import render
    render()
elif page == "Portfolio":
    from dashboard.views.portfolio import render
    render()
elif page == "Discover":
    from dashboard.views.discover import render
    render()
elif page == "Analysis":
    # Combined: Stock Deep Dive, Risk Dashboard, Macro & Market
    tab_stock, tab_risk, tab_macro = st.tabs([
        "Stock Deep Dive", "Risk Dashboard", "Macro & Market"
    ])
    with tab_stock:
        from dashboard.views.analyzer import render as analyzer_render
        analyzer_render()
    with tab_risk:
        from dashboard.views.risk import render as risk_render
        risk_render()
    with tab_macro:
        from dashboard.views.macro import render as macro_render
        macro_render()
elif page == "Settings":
    from dashboard.views.settings import render
    render()
