"""Today — Morning Brief page.

Pre-market report with ratings, movers, events, portfolio P&L, and AI digest.
"""

import streamlit as st
import pandas as pd

from dashboard.components.auth import get_current_user_id
from dashboard.data.market_data import (
    get_market_indices, get_fear_greed, get_market_status,
    get_earnings_today, get_economic_events_today,
    get_overnight_news, get_all_latest_decisions,
)


def _safe_val(v, default=0):
    """Safely convert to float."""
    try:
        import math
        f = float(v) if v is not None else default
        return default if math.isnan(f) else f
    except (ValueError, TypeError):
        return default


def _render_market_pulse():
    """Section 1: Market Pulse — indices + fear/greed + status."""
    indices = get_market_indices()

    if indices:
        cols = st.columns(len(indices))
        for i, (symbol, data) in enumerate(indices.items()):
            with cols[i]:
                change_pct = data["change_pct"]
                delta_color = "normal" if symbol != "VIX" else "inverse"
                st.metric(
                    symbol,
                    f"${data['price']:,.2f}",
                    delta=f"{change_pct:+.2f}%",
                    delta_color=delta_color,
                )

    # Fear & Greed + Market Status
    col_fg, col_status = st.columns([3, 1])
    with col_fg:
        fg = get_fear_greed()
        if fg:
            value = fg["value"]
            desc = fg["description"]
            if value <= 25:
                color = "#EF5350"
            elif value <= 45:
                color = "#FF9800"
            elif value <= 55:
                color = "#787B86"
            elif value <= 75:
                color = "#26A69A"
            else:
                color = "#26A69A"

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;">'
                f'<span style="color:#787B86;font-size:0.8rem;">Fear & Greed</span>'
                f'<span style="color:{color};font-size:1.5rem;font-weight:700;">{value}</span>'
                f'<span style="color:#787B86;font-size:0.85rem;">{desc}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("Fear & Greed: unavailable")

    with col_status:
        status = get_market_status()
        status_class = status.lower().replace(" ", "-")
        st.markdown(
            f'<div style="text-align:right;padding-top:4px;">'
            f'<span class="market-status {status_class}">{status}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _render_portfolio_summary(user_id: int):
    """Section 2: Portfolio summary — value, P&L, top movers."""
    from database.models import PortfolioDAO
    from dashboard.views.portfolio import _get_live_prices, _apply_live_prices

    portfolio_dao = PortfolioDAO()
    holdings = list(portfolio_dao.get_latest_holdings(user_id))

    if not holdings:
        st.info("No portfolio holdings. Add positions in the Portfolio page to see your daily P&L here.")
        return

    tickers = [h["ticker"] for h in holdings]
    live_prices = _get_live_prices(tickers)
    if live_prices:
        holdings = _apply_live_prices(holdings, live_prices)

    total_value = sum(_safe_val(h.get("market_value")) for h in holdings)
    total_cost = sum(_safe_val(h.get("average_cost", 0)) * _safe_val(h.get("quantity", 0))
                     for h in holdings)
    total_pl = sum(_safe_val(h.get("unrealized_pl")) for h in holdings)
    total_pl_pct = (total_pl / total_cost * 100) if total_cost > 0 else 0
    daily_change = sum(_safe_val(h.get("_daily_change", 0)) * _safe_val(h.get("quantity", 0))
                       for h in holdings)

    # Large metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Portfolio Value", f"${total_value:,.0f}",
              delta=f"${daily_change:+,.0f} today" if daily_change else None)
    c2.metric("Daily P&L", f"${daily_change:+,.0f}" if daily_change else "$0")
    c3.metric("Total P&L", f"${total_pl:+,.0f}", delta=f"{total_pl_pct:+.1f}%")

    # Top winners and losers
    sorted_by_daily = sorted(holdings,
                             key=lambda h: _safe_val(h.get("_daily_change_pct")),
                             reverse=True)
    winners = [h for h in sorted_by_daily if _safe_val(h.get("_daily_change_pct")) > 0][:5]
    losers = [h for h in reversed(sorted_by_daily) if _safe_val(h.get("_daily_change_pct")) < 0][:5]

    if winners or losers:
        col_w, col_l = st.columns(2)
        with col_w:
            if winners:
                st.markdown("**Top Winners**")
                for h in winners:
                    pct = _safe_val(h.get("_daily_change_pct"))
                    st.markdown(f':green[{h["ticker"]}  {pct:+.1f}%]')
        with col_l:
            if losers:
                st.markdown("**Top Losers**")
                for h in losers:
                    pct = _safe_val(h.get("_daily_change_pct"))
                    st.markdown(f':red[{h["ticker"]}  {pct:+.1f}%]')


def _render_ratings_signals():
    """Section 3 left: Ratings & signals from latest decisions."""
    decisions = get_all_latest_decisions()
    if not decisions:
        st.info("No analysis data. Run analysis on stocks to see ratings here.")
        return

    # Group by action
    groups = {}
    for d in decisions:
        action = d.get("action", "HOLD")
        groups.setdefault(action, []).append(d)

    order = ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"]
    for action in order:
        group = groups.get(action, [])
        if not group:
            continue

        if action in ("STRONG_BUY", "BUY"):
            color = "green"
        elif action in ("SELL", "STRONG_SELL"):
            color = "red"
        else:
            color = "gray"

        label = action.replace("_", " ").title()
        st.markdown(f"**{label}** ({len(group)})")
        for d in group[:8]:
            score = d.get("composite_score", 0)
            ticker = d.get("ticker", "")
            reason = ""
            if d.get("bull_case") and action in ("STRONG_BUY", "BUY"):
                reason = d["bull_case"][:60]
            elif d.get("bear_case") and action in ("SELL", "STRONG_SELL"):
                reason = d["bear_case"][:60]
            st.markdown(f":{color}[**{ticker}** {score:+.0f}] {reason}")


def _render_events_today():
    """Section 3 right: Earnings + economic events today."""
    # Earnings
    earnings = get_earnings_today()
    if earnings:
        st.markdown("**Earnings Today**")
        rows = []
        for e in earnings[:10]:
            rows.append({
                "Symbol": e["symbol"],
                "Time": e.get("hour", "").replace("bmo", "Pre-Mkt").replace("amc", "After-Hrs"),
                "EPS Est": f"${e['eps_estimate']:.2f}" if e.get("eps_estimate") else "N/A",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.caption("No earnings scheduled today.")

    st.markdown("")

    # Economic events
    events = get_economic_events_today()
    if events:
        st.markdown("**Economic Calendar**")
        rows = []
        for e in events[:10]:
            rows.append({
                "Event": e["event"][:40],
                "Est": str(e.get("estimate", "")) if e.get("estimate") else "N/A",
                "Prior": str(e.get("prev", "")) if e.get("prev") else "N/A",
                "Impact": e.get("impact", "").title(),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.caption("No economic events today.")


def _render_smart_alerts(user_id: int):
    """Section 4: Smart alerts."""
    try:
        from analysis.ai_advisor import ClaudeAdvisor
        advisor = ClaudeAdvisor(user_id)
        alerts = advisor.get_smart_alerts()
    except Exception:
        alerts = []

    if not alerts:
        return

    for alert in alerts[:6]:
        severity = alert.get("severity", "info")
        if severity == "success":
            st.success(f"**{alert['title']}** — {alert['detail']}")
        elif severity == "warning":
            st.warning(f"**{alert['title']}** — {alert['detail']}")
        elif severity == "error":
            st.error(f"**{alert['title']}** — {alert['detail']}")
        else:
            st.info(f"**{alert['title']}** — {alert['detail']}")


def _render_overnight_news():
    """Section 5: Overnight news (collapsible)."""
    articles = get_overnight_news()
    if not articles:
        st.caption("No recent news articles.")
        return

    for article in articles[:10]:
        title = article.get("title", "Untitled")
        source = article.get("source", "")
        published = article.get("published_at", "")[:16]
        sentiment = article.get("sentiment_score")

        # Sentiment badge
        if sentiment is not None:
            try:
                s = float(sentiment)
                if s > 0.1:
                    sent_badge = ":green[Bullish]"
                elif s < -0.1:
                    sent_badge = ":red[Bearish]"
                else:
                    sent_badge = ":gray[Neutral]"
            except (ValueError, TypeError):
                sent_badge = ""
        else:
            sent_badge = ""

        ticker = article.get("ticker", "")
        st.markdown(f"**{title}**  \n{source} | {published} | {ticker} {sent_badge}")


def _render_ai_digest(user_id: int):
    """Section 6: AI morning digest (collapsible)."""
    try:
        from analysis.ai_advisor import ClaudeAdvisor
        advisor = ClaudeAdvisor(user_id)

        if not advisor.is_available():
            st.caption("Set up your Groq API key in Settings to enable AI digest.")
            return

        with st.spinner("Generating morning digest..."):
            digest = advisor.get_portfolio_digest()

        if digest:
            st.markdown(digest)
            if st.button("Ask follow-up in Advisor", key="today_to_advisor"):
                st.session_state["nav_target"] = "AI Advisor"
                st.rerun()
        else:
            st.caption("Unable to generate digest right now.")
    except Exception:
        st.caption("AI digest unavailable.")


def render():
    """Render the Today / Morning Brief page."""
    user_id = get_current_user_id()
    if not user_id:
        st.warning("Please log in.")
        return

    st.header("Today")

    # Section 1: Market Pulse
    _render_market_pulse()
    st.divider()

    # Section 2: Portfolio Summary
    _render_portfolio_summary(user_id)
    st.divider()

    # Section 3: Two columns — Ratings & Events
    col_left, col_right = st.columns([3, 2])
    with col_left:
        st.subheader("Ratings & Signals")
        _render_ratings_signals()
    with col_right:
        st.subheader("Events Today")
        _render_events_today()

    st.divider()

    # Section 4: Smart Alerts
    _render_smart_alerts(user_id)

    # Section 5: Overnight News (collapsible)
    with st.expander("Overnight News", expanded=False):
        _render_overnight_news()

    # Section 6: AI Morning Digest (collapsible)
    with st.expander("AI Morning Digest", expanded=False):
        _render_ai_digest(user_id)
