"""Discover Page — Merged Market Scanner, Top Picks, and Watchlist management."""

import json
import streamlit as st
import pandas as pd

from database.connection import get_connection
from database.models import StockDAO, UserWatchlistDAO
from dashboard.components.auth import get_current_user_id
from dashboard.views.recommendations import (
    STOCK_UNIVERSES, _render_recommendation_card, _action_color,
)


@st.cache_data(ttl=900, show_spinner="Scanning...")
def _cached_quick_screen(tickers: tuple) -> list[dict]:
    """Quick screen tickers via yfinance fast_info (cached 15 min)."""
    import yfinance as yf
    results = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).fast_info
            price = getattr(info, "last_price", None)
            prev = getattr(info, "previous_close", None)
            change = ((price - prev) / prev * 100) if price and prev else 0
            results.append({
                "Ticker": ticker,
                "Price": f"${price:,.2f}" if price else "N/A",
                "Change": f"{change:+.1f}%",
                "Market Cap": f"${getattr(info, 'market_cap', 0) / 1e9:.1f}B"
                if getattr(info, "market_cap", None) else "N/A",
            })
        except Exception:
            continue
    return results


@st.cache_data(ttl=600, show_spinner=False)
def _cached_top_picks() -> list[dict]:
    """Fetch top picks from last 7 days decisions (cached 10 min)."""
    db = get_connection()
    return list(db.execute(
        """SELECT * FROM decisions
           WHERE decided_at >= datetime('now', '-7 days')
           ORDER BY composite_score DESC"""
    ))


def _render_scanner_tab(user_id: int):
    """Market Scanner — scan curated universes for recommendations."""
    db = get_connection()

    st.markdown("Scan curated stock universes for buy/sell signals.")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        scan_source = st.selectbox("Stock Universe", list(STOCK_UNIVERSES.keys()),
                                   key="discover_universe")
    with col2:
        max_stocks = st.number_input("Max Stocks", 5, 50, 20, key="discover_max")
    with col3:
        quick_screen = st.checkbox("Quick Screen", value=True, key="discover_quick",
                                   help="Fetch basic info without full analysis")

    tickers_to_scan = STOCK_UNIVERSES.get(scan_source, [])[:max_stocks]

    if st.button("Scan Now", type="primary", key="discover_scan"):
        if quick_screen:
            # Quick screen — cached batch fetch
            results = _cached_quick_screen(tuple(tickers_to_scan))
            if results:
                st.dataframe(pd.DataFrame(results), hide_index=True, width="stretch")
        else:
            # Full analysis
            from engine.decision_engine import DecisionEngine
            engine = DecisionEngine()
            progress = st.progress(0)
            for i, ticker in enumerate(tickers_to_scan):
                with st.spinner(f"Analyzing {ticker}..."):
                    try:
                        engine.analyze(ticker)
                    except Exception:
                        pass
                progress.progress((i + 1) / len(tickers_to_scan))
            progress.empty()
            st.success("Scan complete! Check Top Picks tab for results.")

    # Show any existing results for scanned universe
    existing = []
    for ticker in tickers_to_scan[:30]:
        d = db.execute_one(
            "SELECT * FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT 1",
            (ticker,),
        )
        if d:
            existing.append(d)

    if existing:
        st.subheader(f"Existing Analysis ({len(existing)} stocks)")
        for d in sorted(existing, key=lambda x: x.get("composite_score", 0) or 0, reverse=True)[:10]:
            ext = {}
            if d.get("extended_data_json"):
                try:
                    ext = json.loads(d["extended_data_json"])
                except Exception:
                    pass
            _render_recommendation_card(d, ext)


def _render_top_picks_tab(user_id: int):
    """Top Picks — best current signals from database."""
    st.markdown("Strongest buy and sell signals from analyzed stocks.")

    # Get all recent decisions (cached)
    decisions = _cached_top_picks()

    if not decisions:
        st.info("No recent analysis data. Run a scan in the Market Scanner tab first.")
        return

    tab_buy, tab_sell = st.tabs(["Buy Signals", "Sell Signals"])

    with tab_buy:
        buys = [d for d in decisions
                if d.get("action", "").upper() in ("BUY", "STRONG_BUY")
                and (d.get("composite_score") or 0) > 0]
        if buys:
            for d in buys[:15]:
                ext = {}
                if d.get("extended_data_json"):
                    try:
                        ext = json.loads(d["extended_data_json"])
                    except Exception:
                        pass
                _render_recommendation_card(d, ext)
        else:
            st.info("No buy signals at this time.")

    with tab_sell:
        sells = [d for d in decisions
                 if d.get("action", "").upper() in ("SELL", "STRONG_SELL")
                 and (d.get("composite_score") or 0) < 0]
        if sells:
            for d in sells[:15]:
                ext = {}
                if d.get("extended_data_json"):
                    try:
                        ext = json.loads(d["extended_data_json"])
                    except Exception:
                        pass
                _render_recommendation_card(d, ext)
        else:
            st.info("No sell signals at this time.")


def _render_watchlist_tab(user_id: int):
    """My Watchlist — add/remove tickers with screening filters."""
    db = get_connection()
    stock_dao = StockDAO()
    wl_dao = UserWatchlistDAO()

    # Watchlist management
    col_add, col_remove = st.columns(2)

    with col_add:
        st.markdown("**Add Tickers**")
        add_input = st.text_input("Tickers (comma-separated)",
                                  placeholder="AAPL, MSFT, NVDA", key="disc_wl_add")
        if st.button("Add", key="disc_wl_add_btn", type="primary"):
            if add_input:
                import yfinance as yf
                tickers = [t.strip().upper() for t in add_input.split(",") if t.strip()]
                for t in tickers:
                    try:
                        stock = yf.Ticker(t)
                        info = stock.info
                        stock_dao.upsert(
                            ticker=t,
                            company_name=info.get("longName", info.get("shortName", "")),
                            sector=info.get("sector", ""),
                            industry=info.get("industry", ""),
                            market_cap=info.get("marketCap"),
                        )
                        wl_dao.add(user_id, t)
                        st.success(f"Added {t}")
                    except Exception as e:
                        st.error(f"Failed to add {t}: {e}")
                st.rerun()

    with col_remove:
        st.markdown("**Remove Tickers**")
        user_tickers = wl_dao.get_tickers(user_id)
        tickers_to_remove = st.multiselect("Select to remove", user_tickers, key="disc_wl_remove")
        if st.button("Remove Selected", key="disc_wl_remove_btn"):
            for t in tickers_to_remove:
                wl_dao.remove(user_id, t)
            st.success(f"Removed {len(tickers_to_remove)} ticker(s)")
            st.rerun()

    st.divider()

    # Screener view of watchlist
    user_tickers = wl_dao.get_tickers(user_id)
    if not user_tickers:
        st.info("Your watchlist is empty. Add some tickers above or use the sidebar.")
        return

    placeholders = ",".join("?" for _ in user_tickers)
    stocks = list(db.execute(
        f"""SELECT ticker, company_name, sector, industry, market_cap
            FROM stocks WHERE ticker IN ({placeholders}) ORDER BY ticker""",
        tuple(user_tickers),
    ))

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        sectors = sorted(set(s["sector"] for s in stocks if s.get("sector")))
        selected_sectors = st.multiselect("Filter by Sector", sectors, default=sectors,
                                          key="disc_sector_filter")
    with col2:
        sort_by = st.selectbox("Sort By", ["Score", "Ticker", "Sector"], key="disc_sort")

    # Build screener data
    screener_data = []
    for s in stocks:
        if selected_sectors and s.get("sector") not in selected_sectors:
            continue

        ticker = s["ticker"]
        row = {
            "Ticker": ticker,
            "Company": (s.get("company_name") or "")[:30],
            "Sector": s.get("sector", "N/A"),
        }

        decision = db.execute_one(
            "SELECT composite_score, confidence, action FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT 1",
            (ticker,),
        )
        if decision:
            row["Score"] = decision.get("composite_score")
            row["Action"] = decision.get("action", "N/A")
            row["Confidence"] = f"{decision['confidence']:.0%}" if decision.get("confidence") else "N/A"
        else:
            row["Score"] = None
            row["Action"] = "Not analyzed"
            row["Confidence"] = "N/A"

        screener_data.append(row)

    if sort_by == "Score":
        screener_data.sort(key=lambda x: x.get("Score") if x.get("Score") is not None else -999, reverse=True)
    elif sort_by == "Ticker":
        screener_data.sort(key=lambda x: x.get("Ticker", ""))
    else:
        screener_data.sort(key=lambda x: x.get("Sector", ""))

    st.subheader(f"Watchlist ({len(screener_data)} stocks)")
    df = pd.DataFrame(screener_data)
    for col in ["Score"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:.2f}" if x is not None else "N/A")
    st.dataframe(df, width="stretch", hide_index=True, height=400)

    # Bulk analyze
    st.divider()
    if st.button("Analyze All Watchlist Stocks", key="disc_bulk_analyze"):
        from engine.decision_engine import DecisionEngine
        engine = DecisionEngine()
        progress = st.progress(0)
        for i, t in enumerate(user_tickers):
            with st.spinner(f"Analyzing {t}..."):
                try:
                    engine.analyze(t)
                except Exception as e:
                    st.error(f"{t}: {e}")
            progress.progress((i + 1) / len(user_tickers))
        st.rerun()


def _render_news_tab(user_id: int):
    """Market News tab — imports from news.py rendering logic."""
    from dashboard.views.news import (
        _fetch_yfinance_news, _store_articles, _dedupe_and_sort,
        _render_article_card, _is_credible, MARKET_TICKERS,
    )

    db = get_connection()

    col1, col2 = st.columns([3, 1])
    with col1:
        credible_only = st.toggle("Credible Sources Only", value=True,
                                   key="disc_news_credible")
    with col2:
        refresh = st.button("Refresh News", key="disc_news_refresh")

    if refresh:
        with st.spinner("Fetching market headlines..."):
            for ticker in MARKET_TICKERS:
                articles = _fetch_yfinance_news(ticker)
                _store_articles(articles)

    # Load from DB
    market_articles = []
    for ticker in MARKET_TICKERS:
        articles = list(db.execute(
            """SELECT * FROM news_articles
               WHERE ticker = ? ORDER BY published_at DESC LIMIT 15""",
            (ticker,),
        ))
        market_articles.extend(articles)

    if credible_only:
        market_articles = [a for a in market_articles if _is_credible(a.get("source", ""))]

    market_articles = _dedupe_and_sort(market_articles)

    if market_articles:
        for article in market_articles[:20]:
            _render_article_card(article, show_credibility=True)
    else:
        st.info("No market news cached yet. Click 'Refresh News' to fetch headlines.")


def render():
    """Render the discover page (scanner + top picks + news)."""
    st.header("Market Scanner")

    user_id = get_current_user_id()
    if not user_id:
        st.warning("Please log in.")
        return

    tab_scanner, tab_picks, tab_news = st.tabs([
        "Scanner", "Top Picks", "Market News"
    ])

    with tab_scanner:
        _render_scanner_tab(user_id)

    with tab_picks:
        _render_top_picks_tab(user_id)

    with tab_news:
        _render_news_tab(user_id)
