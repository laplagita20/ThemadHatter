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

    sectors = set(h.get("sector", "Unknown") for h in holdings if h.get("sector"))
    winners = sum(1 for h in holdings if _safe_val(h.get("unrealized_pl")) > 0)
    best = max(holdings, key=lambda h: _safe_val(h.get("unrealized_pl_pct")), default=None)

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
    """Render AI-generated portfolio digest (full width)."""
    try:
        from analysis.ai_advisor import ClaudeAdvisor
        advisor = ClaudeAdvisor(user_id)

        if not advisor.is_available():
            # Actionable CTA
            st.markdown("""
            <div class="setup-card">
                <div style="font-size: 1.3rem; font-weight: 700; color: #f59e0b; margin-bottom: 8px;">
                    Unlock AI Insights
                </div>
                <div style="color: #94a3b8; margin-bottom: 16px;">
                    Get daily portfolio digests, trade ideas, and personalized analysis
                    powered by AI. Set up your free Groq API key to get started.
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Set Up AI in Settings", key="home_setup_ai", type="primary"):
                st.session_state["nav_target"] = "Settings"
                st.rerun()
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
            st.markdown(digest)
        else:
            st.info("Unable to generate insights right now. Try again later.")
    except Exception:
        st.info("AI insights unavailable. Add your API key in Settings to enable.")


def _render_smart_alerts(user_id: int):
    """Render smart alerts as compact strip."""
    try:
        from analysis.ai_advisor import ClaudeAdvisor
        advisor = ClaudeAdvisor(user_id)
        alerts = advisor.get_smart_alerts()
    except Exception:
        alerts = []

    if not alerts:
        return

    st.subheader("Smart Alerts")

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


def _render_quick_add(portfolio_dao, stock_dao, user_id: int):
    """Render a compact quick-add bar for holdings."""
    st.caption("Quick Add Holdings")
    col1, col2 = st.columns([5, 1])
    with col1:
        quick_text = st.text_input(
            "Add holdings",
            placeholder="AAPL 100 @ 150, MSFT 50",
            key="home_quick_add",
            label_visibility="collapsed",
        )
    with col2:
        add_btn = st.button("Add", key="home_quick_add_btn", type="primary")

    if add_btn and quick_text and quick_text.strip():
        from utils.portfolio_parser import parse_portfolio_text
        parsed = parse_portfolio_text(quick_text)
        if parsed:
            import yfinance as yf
            imported = 0
            for row in parsed:
                try:
                    from dashboard.views.portfolio import _fetch_and_build_holding, _merge_and_snapshot
                    holding = _fetch_and_build_holding(row["ticker"], row["shares"], row["cost"])
                    info = holding.pop("_info")
                    _merge_and_snapshot(portfolio_dao, holding, user_id)
                    stock_dao.upsert(
                        ticker=row["ticker"],
                        company_name=info.get("longName", info.get("shortName", "")),
                        sector=info.get("sector", ""),
                        industry=info.get("industry", ""),
                        market_cap=info.get("marketCap"),
                    )
                    imported += 1
                except Exception as e:
                    st.warning(f"Skipped {row['ticker']}: {e}")
            if imported:
                st.success(f"Added {imported} holding(s)")
                st.rerun()
        else:
            st.error("Could not parse. Use format: `AAPL 100 @ 150`")


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


def _render_empty_state(portfolio_dao, stock_dao, user_id: int):
    """Render the guided empty state with two setup cards."""
    st.markdown("""
    <div style="text-align: center; padding: 40px 20px 20px;">
        <div style="font-size: 3rem; margin-bottom: 12px;">&#127913;</div>
        <h2 style="color: #f59e0b; margin-bottom: 4px;">Welcome to The Mad Hatter</h2>
        <p style="color: #94a3b8; font-size: 1.05rem; max-width: 500px; margin: 0 auto;">
            Your AI-powered financial advisor. Let's get you set up.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div class="setup-card">
            <div style="font-size: 1.5rem; margin-bottom: 8px;">1&#65039;&#8419;</div>
            <div style="font-size: 1.1rem; font-weight: 700; color: #a78bfa; margin-bottom: 8px;">
                Add Your Portfolio
            </div>
            <div style="color: #94a3b8; font-size: 0.9rem;">
                Enter your holdings to get personalized insights and track performance.
            </div>
        </div>
        """, unsafe_allow_html=True)

        portfolio_text = st.text_area(
            "Enter holdings",
            placeholder="AAPL 100 @ 150\nMSFT 50 @ 380\nNVDA 20",
            height=120,
            key="home_empty_portfolio",
            label_visibility="collapsed",
        )
        if st.button("Add Holdings", type="primary", key="home_empty_add"):
            if portfolio_text and portfolio_text.strip():
                from utils.portfolio_parser import parse_portfolio_text
                parsed = parse_portfolio_text(portfolio_text)
                if parsed:
                    imported = 0
                    for row in parsed:
                        try:
                            from dashboard.views.portfolio import _fetch_and_build_holding, _merge_and_snapshot
                            holding = _fetch_and_build_holding(row["ticker"], row["shares"], row["cost"])
                            info = holding.pop("_info")
                            _merge_and_snapshot(portfolio_dao, holding, user_id)
                            stock_dao.upsert(
                                ticker=row["ticker"],
                                company_name=info.get("longName", info.get("shortName", "")),
                                sector=info.get("sector", ""),
                                industry=info.get("industry", ""),
                                market_cap=info.get("marketCap"),
                            )
                            imported += 1
                        except Exception as e:
                            st.warning(f"Skipped {row['ticker']}: {e}")
                    if imported:
                        st.success(f"Added {imported} holding(s)!")
                        st.rerun()
                else:
                    st.error("Could not parse. Use format: `AAPL 100 @ 150`")

    with col2:
        st.markdown("""
        <div class="setup-card">
            <div style="font-size: 1.5rem; margin-bottom: 8px;">2&#65039;&#8419;</div>
            <div style="font-size: 1.1rem; font-weight: 700; color: #a78bfa; margin-bottom: 8px;">
                Enable AI Insights
            </div>
            <div style="color: #94a3b8; font-size: 0.9rem;">
                Add your free Groq API key to unlock portfolio digests, trade ideas, and stock explanations.
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Set Up AI in Settings", key="home_empty_ai"):
            st.session_state["nav_target"] = "Settings"
            st.rerun()

        st.markdown("")
        st.caption("Or explore without AI:")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Discover Stocks", key="home_empty_discover"):
                st.session_state["nav_target"] = "Discover"
                st.rerun()
        with col_b:
            if st.button("Portfolio Page", key="home_empty_portfolio_page"):
                st.session_state["nav_target"] = "Portfolio"
                st.rerun()


def render():
    """Render the home dashboard."""
    user_id = get_current_user_id()
    if not user_id:
        st.warning("Please log in to view your dashboard.")
        return

    from database.models import StockDAO
    portfolio_dao = PortfolioDAO()
    stock_dao = StockDAO()
    holdings = list(portfolio_dao.get_latest_holdings(user_id))

    if not holdings:
        _render_empty_state(portfolio_dao, stock_dao, user_id)
        return

    # Refresh with live prices
    from dashboard.views.portfolio import _get_live_prices, _apply_live_prices
    tickers = [h["ticker"] for h in holdings]
    live_prices = _get_live_prices(tickers)
    if live_prices:
        holdings = _apply_live_prices(holdings, live_prices)

    # Portfolio Hero
    _render_portfolio_hero(holdings)

    st.divider()

    # Full-width AI insights
    st.subheader("AI Insights")
    _render_ai_insights(user_id)

    st.divider()

    # Smart alerts as compact strip
    _render_smart_alerts(user_id)

    # Quick-add bar + Holdings table
    st.divider()
    _render_quick_add(portfolio_dao, stock_dao, user_id)

    st.markdown("")
    _render_holdings_mini(holdings)
