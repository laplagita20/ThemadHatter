"""Home Dashboard — AI-powered portfolio overview and insights."""

import streamlit as st
import pandas as pd

from database.models import PortfolioDAO, DecisionDAO, UserWatchlistDAO
from dashboard.components.auth import get_current_user_id


def _safe_val(v, default=0):
    """Safely convert to float, returning default if None/NaN."""
    try:
        import math
        f = float(v) if v is not None else default
        return default if math.isnan(f) else f
    except (ValueError, TypeError):
        return default


def _render_portfolio_hero(holdings: list[dict]):
    """Render the large portfolio value hero section."""
    total_value = sum(_safe_val(h.get("market_value")) for h in holdings)
    total_cost = sum(_safe_val(h.get("average_cost", 0)) * _safe_val(h.get("quantity", 0))
                     for h in holdings)
    total_pl = sum(_safe_val(h.get("unrealized_pl")) for h in holdings)
    total_pl_pct = (total_pl / total_cost * 100) if total_cost > 0 else 0

    # Count sectors
    sectors = set(h.get("sector", "Unknown") for h in holdings if h.get("sector"))
    winners = sum(1 for h in holdings if _safe_val(h.get("unrealized_pl")) > 0)
    best = max(holdings, key=lambda h: _safe_val(h.get("unrealized_pl_pct")), default=None)

    # Hero value
    pl_color = "#10b981" if total_pl >= 0 else "#ef4444"
    pl_arrow = "+" if total_pl >= 0 else ""

    st.markdown(f"""
    <div style="text-align: center; padding: 20px 0 10px 0;">
        <div style="font-size: 0.9rem; color: #94a3b8; text-transform: uppercase;
                    letter-spacing: 2px; margin-bottom: 8px;">Portfolio Value</div>
        <div style="font-size: 3rem; font-weight: 800; color: #f59e0b;
                    line-height: 1.1;">${total_value:,.0f}</div>
        <div style="font-size: 1.2rem; color: {pl_color}; margin-top: 4px;">
            {pl_arrow}${total_pl:,.0f} ({pl_arrow}{total_pl_pct:.1f}%) all-time
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Mini metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Positions", len(holdings))
    with col2:
        st.metric("Sectors", len(sectors))
    with col3:
        st.metric("Winners", f"{winners}/{len(holdings)}")
    with col4:
        if best:
            st.metric("Best", best["ticker"],
                      delta=f"{_safe_val(best.get('unrealized_pl_pct')):+.1f}%")


def _render_ai_insights(user_id: int):
    """Render AI-generated portfolio digest."""
    st.subheader("AI Insights")

    try:
        from analysis.ai_advisor import ClaudeAdvisor
        advisor = ClaudeAdvisor(user_id)

        if not advisor.is_available():
            st.info("Add your Anthropic API key in Settings to unlock AI-powered insights.")
            return

        col1, col2 = st.columns([6, 1])
        with col2:
            refresh = st.button("Refresh", key="refresh_digest")

        if refresh:
            from database.models import AIAdviceCacheDAO
            AIAdviceCacheDAO().invalidate(user_id, "portfolio_digest")

        with st.spinner("Generating insights..."):
            digest = advisor.get_portfolio_digest()

        if digest:
            st.markdown(f"""<div style="background: linear-gradient(135deg, rgba(45, 27, 105, 0.3), rgba(6, 182, 212, 0.1));
                border: 1px solid rgba(124, 58, 237, 0.3); border-radius: 12px; padding: 20px;">
                {_md_to_safe_html(digest)}
            </div>""", unsafe_allow_html=True)
            # Fallback for markdown rendering
            st.markdown(digest)
        else:
            st.info("Unable to generate insights right now. Try again later.")
    except Exception as e:
        st.info("AI insights unavailable. Add your API key in Settings to enable.")


def _md_to_safe_html(md_text: str) -> str:
    """Minimal markdown-to-html for display inside styled divs."""
    # Just return empty - we use st.markdown below for actual rendering
    return ""


def _render_smart_alerts(user_id: int):
    """Render smart alerts (rule-based, no AI needed)."""
    try:
        from analysis.ai_advisor import ClaudeAdvisor
        advisor = ClaudeAdvisor(user_id)
        alerts = advisor.get_smart_alerts()
    except Exception:
        alerts = []

    if not alerts:
        return

    st.subheader("Smart Alerts")

    severity_icons = {
        "success": "checkmark",
        "warning": "warning",
        "info": "information",
        "error": "error",
    }

    for alert in alerts[:8]:
        severity = alert.get("severity", "info")
        if severity == "success":
            st.success(f"**{alert['title']}** — {alert['detail']}")
        elif severity == "warning":
            st.warning(f"**{alert['title']}** — {alert['detail']}")
        elif severity == "error":
            st.error(f"**{alert['title']}** — {alert['detail']}")
        else:
            st.info(f"**{alert['title']}** — {alert['detail']}")


def _render_quick_actions():
    """Render quick action buttons."""
    st.subheader("Quick Actions")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("Analyze Portfolio", key="qa_analyze", type="primary",
                      use_container_width=True):
            st.session_state["nav_target"] = "Portfolio"
            st.rerun()
    with col2:
        if st.button("Add Holding", key="qa_add_holding",
                      use_container_width=True):
            st.session_state["nav_target"] = "Portfolio"
            st.rerun()
    with col3:
        if st.button("Ask AI", key="qa_ask_ai",
                      use_container_width=True):
            st.session_state["nav_target"] = "Advisor"
            st.rerun()
    with col4:
        if st.button("Discover Stocks", key="qa_discover",
                      use_container_width=True):
            st.session_state["nav_target"] = "Discover"
            st.rerun()


def _render_holdings_mini(holdings: list[dict]):
    """Render a compact holdings table."""
    if not holdings:
        return

    st.subheader("Holdings")
    rows = []
    for h in holdings[:15]:
        pl = _safe_val(h.get("unrealized_pl"))
        pl_pct = _safe_val(h.get("unrealized_pl_pct"))
        rows.append({
            "Ticker": h["ticker"],
            "Shares": f"{_safe_val(h.get('quantity')):.1f}",
            "Price": f"${_safe_val(h.get('current_price')):,.2f}",
            "Value": f"${_safe_val(h.get('market_value')):,.0f}",
            "P&L": f"${pl:+,.0f}",
            "P&L %": f"{pl_pct:+.1f}%",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch")


def render():
    """Render the home dashboard."""
    user_id = get_current_user_id()
    if not user_id:
        st.warning("Please log in to view your dashboard.")
        return

    portfolio_dao = PortfolioDAO()
    holdings = list(portfolio_dao.get_latest_holdings(user_id))

    if not holdings:
        # Empty state
        st.markdown("""
        <div style="text-align: center; padding: 60px 20px;">
            <div style="font-size: 3rem; margin-bottom: 16px;">&#127913;</div>
            <h2 style="color: #f59e0b;">Welcome to The Mad Hatter</h2>
            <p style="color: #94a3b8; font-size: 1.1rem; max-width: 500px; margin: 0 auto;">
                Your AI-powered financial advisor. Add your portfolio holdings to get
                personalized insights, trade ideas, and smart alerts.
            </p>
        </div>
        """, unsafe_allow_html=True)

        _render_quick_actions()
        return

    # Portfolio Hero
    _render_portfolio_hero(holdings)

    st.divider()

    # Two column layout: AI insights + Alerts
    col_left, col_right = st.columns([3, 2])

    with col_left:
        _render_ai_insights(user_id)

    with col_right:
        _render_smart_alerts(user_id)

    st.divider()

    _render_quick_actions()

    st.divider()

    _render_holdings_mini(holdings)
