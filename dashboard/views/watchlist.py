"""Watchlist Page — Dedicated stock tracking and screening."""

import streamlit as st
import pandas as pd

from database.connection import get_connection
from database.models import StockDAO, UserWatchlistDAO
from dashboard.components.auth import get_current_user_id


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_watchlist_prices(tickers: tuple) -> dict:
    """Batch fetch live prices for watchlist tickers (cached 5 min)."""
    import math
    if not tickers:
        return {}

    try:
        import yfinance as yf
        ticker_str = " ".join(tickers)
        data = yf.download(ticker_str, period="5d", interval="1d",
                           progress=False, threads=True)
        if data.empty:
            return {}

        prices = {}
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    close_series = data["Close"].dropna()
                else:
                    close_series = data["Close"][ticker].dropna()

                if close_series is not None and len(close_series) > 0:
                    current = float(close_series.iloc[-1])
                    prev = float(close_series.iloc[-2]) if len(close_series) > 1 else current
                    if math.isnan(current) or math.isnan(prev):
                        continue
                    change = current - prev
                    change_pct = (change / prev * 100) if prev else 0

                    # 7-day sparkline data
                    spark = [float(v) for v in close_series.tail(7).values
                             if not math.isnan(float(v))]

                    prices[ticker] = {
                        "price": current,
                        "change": change,
                        "change_pct": change_pct,
                        "sparkline": spark,
                    }
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return prices
    except Exception:
        return {}


def render():
    """Render the watchlist page."""
    st.header("Watchlist")

    user_id = get_current_user_id()
    if not user_id:
        st.warning("Please log in.")
        return

    db = get_connection()
    stock_dao = StockDAO()
    wl_dao = UserWatchlistDAO()

    # Add/remove controls
    col_add, col_remove = st.columns(2)

    with col_add:
        add_input = st.text_input("Add tickers (comma-separated)",
                                  placeholder="AAPL, MSFT, NVDA", key="wl_add")
        if st.button("Add", key="wl_add_btn", type="primary"):
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
        user_tickers = wl_dao.get_tickers(user_id)
        tickers_to_remove = st.multiselect("Remove tickers", user_tickers, key="wl_remove")
        if st.button("Remove Selected", key="wl_remove_btn"):
            for t in tickers_to_remove:
                wl_dao.remove(user_id, t)
            st.success(f"Removed {len(tickers_to_remove)} ticker(s)")
            st.rerun()

    st.divider()

    # Watchlist table
    user_tickers = wl_dao.get_tickers(user_id)
    if not user_tickers:
        st.info("Your watchlist is empty. Add some tickers above to get started.")
        return

    # Fetch stock info
    placeholders = ",".join("?" for _ in user_tickers)
    stocks = list(db.execute(
        f"""SELECT ticker, company_name, sector, industry, market_cap
            FROM stocks WHERE ticker IN ({placeholders}) ORDER BY ticker""",
        tuple(user_tickers),
    ))
    stocks_by_ticker = {s["ticker"]: s for s in stocks}

    # Filters
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        sectors = sorted(set(s["sector"] for s in stocks if s.get("sector")))
        selected_sectors = st.multiselect("Filter by Sector", sectors, default=sectors,
                                          key="wl_sector_filter")
    with col2:
        sort_by = st.selectbox("Sort By", ["Score", "Change", "Ticker", "Sector"], key="wl_sort")
    with col3:
        st.markdown("")  # spacer

    # Fetch live prices
    live_prices = _fetch_watchlist_prices(tuple(user_tickers))

    # Build screener data
    screener_data = []
    for t in user_tickers:
        s = stocks_by_ticker.get(t, {})
        if selected_sectors and s.get("sector") and s["sector"] not in selected_sectors:
            continue

        row = {
            "Ticker": t,
            "Company": (s.get("company_name") or "")[:25],
            "Sector": s.get("sector", ""),
        }

        # Live price data
        lp = live_prices.get(t)
        if lp:
            row["Price"] = f"${lp['price']:,.2f}"
            row["Change"] = f"{lp['change_pct']:+.1f}%"
            row["_change_val"] = lp["change_pct"]
        else:
            row["Price"] = "N/A"
            row["Change"] = "N/A"
            row["_change_val"] = 0

        # Decision data
        decision = db.execute_one(
            "SELECT composite_score, confidence, action FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT 1",
            (t,),
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

    # Sort
    if sort_by == "Score":
        screener_data.sort(key=lambda x: x.get("Score") if x.get("Score") is not None else -999, reverse=True)
    elif sort_by == "Change":
        screener_data.sort(key=lambda x: x.get("_change_val", 0), reverse=True)
    elif sort_by == "Ticker":
        screener_data.sort(key=lambda x: x.get("Ticker", ""))
    else:
        screener_data.sort(key=lambda x: x.get("Sector", ""))

    st.subheader(f"Watchlist ({len(screener_data)} stocks)")

    # Format for display
    display_data = []
    for row in screener_data:
        display_data.append({
            "Ticker": row["Ticker"],
            "Company": row["Company"],
            "Price": row["Price"],
            "Change": row["Change"],
            "Score": f"{row['Score']:+.1f}" if row["Score"] is not None else "N/A",
            "Action": row["Action"],
            "Confidence": row["Confidence"],
            "Sector": row["Sector"],
        })

    df = pd.DataFrame(display_data)
    st.dataframe(df, width="stretch", hide_index=True, height=min(400, 50 + len(df) * 35))

    # Action buttons
    st.divider()
    col_analyze, col_navigate = st.columns(2)
    with col_analyze:
        if st.button("Analyze All Watchlist", key="wl_bulk_analyze", type="primary"):
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
