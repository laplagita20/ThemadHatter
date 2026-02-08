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
    page_title="Mad Hatter v2 - Financial Advisor",
    page_icon="🎩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database
from config.settings import get_settings
from database.connection import get_connection
from database.schema import initialize_database

settings = get_settings()
db = get_connection(settings.db_path)
initialize_database(db)

# Auto-refresh (optional)
try:
    from streamlit_autorefresh import st_autorefresh
    # Refresh every 5 minutes
    st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh")
except ImportError:
    pass  # streamlit-autorefresh not installed, skip


# Sidebar navigation
st.sidebar.title("Mad Hatter v2")
st.sidebar.caption("Professional Financial Advisor")

page = st.sidebar.radio("Navigation", [
    "Portfolio",
    "Stock Analysis",
    "Risk Dashboard",
    "Macro & Market",
    "Stock Screener",
])

st.sidebar.divider()
st.sidebar.caption("System Status")

# Show data freshness
try:
    latest_decision = db.execute_one(
        "SELECT decided_at FROM decisions ORDER BY decided_at DESC LIMIT 1"
    )
    if latest_decision:
        st.sidebar.text(f"Last analysis: {latest_decision['decided_at'][:16]}")

    stock_count = db.execute_one("SELECT COUNT(*) as c FROM stocks WHERE is_active = 1")
    if stock_count:
        st.sidebar.text(f"Watchlist: {stock_count['c']} stocks")

    holding_count = db.execute_one(
        """SELECT COUNT(DISTINCT ticker) as c FROM portfolio_holdings
           WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM portfolio_holdings)"""
    )
    if holding_count:
        st.sidebar.text(f"Holdings: {holding_count['c']} positions")
except Exception:
    pass

st.sidebar.divider()
st.sidebar.caption("Quick Commands")
st.sidebar.code("python main.py analyze AAPL", language="bash")
st.sidebar.code("python main.py risk-report", language="bash")
st.sidebar.code("python main.py collect --source all", language="bash")

# Route to pages
if page == "Portfolio":
    from dashboard.pages.portfolio import render
    render()
elif page == "Stock Analysis":
    from dashboard.pages.analyzer import render
    render()
elif page == "Risk Dashboard":
    from dashboard.pages.risk import render
    render()
elif page == "Macro & Market":
    from dashboard.pages.macro import render
    render()
elif page == "Stock Screener":
    from dashboard.pages.screener import render
    render()
