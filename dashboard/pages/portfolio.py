"""Portfolio Overview Dashboard Page."""

import streamlit as st
from database.models import PortfolioDAO, DecisionDAO
from database.connection import get_connection
from dashboard.components.charts import create_sector_pie_chart, create_performance_chart
from dashboard.components.tables import holdings_table, decisions_table


def render():
    """Render the portfolio overview page."""
    st.header("Portfolio Overview")

    portfolio_dao = PortfolioDAO()
    decision_dao = DecisionDAO()
    db = get_connection()

    holdings = list(portfolio_dao.get_latest_holdings())

    if not holdings:
        st.warning("No portfolio data found. Run `python main.py import-portfolio` first.")
        return

    # Key metrics
    total_value = sum(h["market_value"] or 0 for h in holdings)
    total_pl = sum(h["unrealized_pl"] or 0 for h in holdings)
    num_positions = len(holdings)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Portfolio Value", f"${total_value:,.2f}")
    col2.metric("Unrealized P&L", f"${total_pl:+,.2f}",
                delta=f"{(total_pl / max(total_value - total_pl, 1)) * 100:+.1f}%")
    col3.metric("Positions", str(num_positions))

    sectors = set(h["sector"] for h in holdings if h.get("sector"))
    col4.metric("Sectors", str(len(sectors)))

    st.divider()

    # Two-column layout
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Holdings")
        holdings_table(holdings)

    with right:
        # Sector allocation pie chart
        sector_weights = {}
        for h in holdings:
            sector = h.get("sector") or "Unknown"
            sector_weights[sector] = sector_weights.get(sector, 0) + (h["market_value"] or 0)

        if sector_weights and total_value > 0:
            sector_pcts = {k: v / total_value * 100 for k, v in sector_weights.items()}
            fig = create_sector_pie_chart(sector_pcts)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Performance chart
    st.subheader("Portfolio Performance")
    snapshots = list(db.execute(
        """SELECT snapshot_date, total_equity FROM portfolio_snapshots
           WHERE total_equity IS NOT NULL
           ORDER BY snapshot_date ASC LIMIT 365"""
    ))

    if len(snapshots) >= 2:
        dates = [s["snapshot_date"][:10] for s in snapshots]
        values = [s["total_equity"] for s in snapshots]
        fig = create_performance_chart(dates, values)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Insufficient snapshot data for performance chart. Data accumulates over time.")

    # Recent decisions
    st.divider()
    st.subheader("Recent Decisions")
    recent = list(db.execute(
        """SELECT ticker, action, composite_score, confidence,
                  position_size_pct, decided_at
           FROM decisions ORDER BY decided_at DESC LIMIT 10"""
    ))
    decisions_table(recent)
