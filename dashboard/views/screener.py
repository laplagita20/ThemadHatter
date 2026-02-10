"""Stock Screener Dashboard Page."""

import streamlit as st
import pandas as pd
import yfinance as yf

from database.connection import get_connection
from database.models import StockDAO


def render():
    """Render the stock screener page."""
    st.header("Stock Screener")

    db = get_connection()
    stock_dao = StockDAO()

    # --- Watchlist Management ---
    with st.expander("Manage Watchlist", expanded=False):
        col_add, col_remove = st.columns(2)

        with col_add:
            st.markdown("**Add Tickers**")
            add_input = st.text_input("Tickers (comma-separated)", placeholder="AAPL, MSFT, NVDA", key="wl_add")
            if st.button("Add to Watchlist", key="wl_add_btn"):
                if add_input:
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
                            st.success(f"Added {t} ({info.get('longName', '')})")
                        except Exception as e:
                            st.error(f"Failed to add {t}: {e}")
                    st.rerun()

        with col_remove:
            st.markdown("**Remove Tickers**")
            all_stocks = list(db.execute("SELECT ticker FROM stocks WHERE is_active = 1 ORDER BY ticker"))
            tickers_to_remove = st.multiselect("Select to remove", [s["ticker"] for s in all_stocks], key="wl_remove")
            if st.button("Remove Selected", key="wl_remove_btn"):
                for t in tickers_to_remove:
                    stock_dao.deactivate(t)
                st.success(f"Removed {len(tickers_to_remove)} ticker(s)")
                st.rerun()

    # Get all stocks with computed scores
    stocks = list(db.execute(
        "SELECT ticker, company_name, sector, industry, market_cap FROM stocks WHERE is_active = 1 ORDER BY ticker"
    ))

    if not stocks:
        st.warning("No stocks in watchlist. Use 'Manage Watchlist' above to add tickers.")
        return

    # Filters
    st.subheader("Filters")
    col1, col2, col3 = st.columns(3)

    with col1:
        sectors = sorted(set(s["sector"] for s in stocks if s.get("sector")))
        selected_sectors = st.multiselect("Sectors", sectors, default=sectors)

    with col2:
        min_piotroski = st.slider("Min Piotroski F-Score", 0, 9, 0)

    with col3:
        sort_by = st.selectbox("Sort By", [
            "Composite Score", "Piotroski", "Altman Z", "DCF Margin of Safety", "Ticker"
        ])

    # Build screener data
    screener_data = []
    for s in stocks:
        if selected_sectors and s.get("sector") not in selected_sectors:
            continue

        ticker = s["ticker"]
        row = {
            "Ticker": ticker,
            "Company": s.get("company_name", "")[:30],
            "Sector": s.get("sector", "N/A"),
        }

        # Get latest decision
        decision = db.execute_one(
            "SELECT composite_score, confidence, action FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT 1",
            (ticker,),
        )
        if decision:
            row["Score"] = decision["composite_score"]
            row["Action"] = decision["action"]
            row["Confidence"] = f"{decision['confidence']:.0%}" if decision.get("confidence") else "N/A"
        else:
            row["Score"] = None
            row["Action"] = "N/A"
            row["Confidence"] = "N/A"

        # Get computed scores
        scores = list(db.execute(
            """SELECT score_type, score_value FROM computed_scores
               WHERE ticker = ? AND computed_at = (
                   SELECT MAX(computed_at) FROM computed_scores WHERE ticker = ? AND score_type = computed_scores.score_type
               )""",
            (ticker, ticker),
        ))

        score_map = {s["score_type"]: s["score_value"] for s in scores}
        row["Piotroski"] = score_map.get("piotroski")
        row["Altman Z"] = score_map.get("altman_z")
        row["Beneish M"] = score_map.get("beneish_m")

        # DCF margin of safety
        dcf = db.execute_one(
            "SELECT margin_of_safety FROM dcf_valuations WHERE ticker = ? ORDER BY computed_at DESC LIMIT 1",
            (ticker,),
        )
        row["DCF MoS %"] = dcf["margin_of_safety"] if dcf and dcf.get("margin_of_safety") else None

        # Apply filters
        if min_piotroski > 0 and (row["Piotroski"] is None or row["Piotroski"] < min_piotroski):
            continue

        screener_data.append(row)

    if not screener_data:
        st.info("No stocks match the current filters. Try adjusting criteria or running analysis first.")
        return

    # Sort
    sort_key_map = {
        "Composite Score": "Score",
        "Piotroski": "Piotroski",
        "Altman Z": "Altman Z",
        "DCF Margin of Safety": "DCF MoS %",
        "Ticker": "Ticker",
    }
    sort_key = sort_key_map.get(sort_by, "Score")

    if sort_key == "Ticker":
        screener_data.sort(key=lambda x: x.get(sort_key, ""))
    else:
        screener_data.sort(key=lambda x: x.get(sort_key) if x.get(sort_key) is not None else -999, reverse=True)

    # Display
    st.subheader(f"Results ({len(screener_data)} stocks)")

    df = pd.DataFrame(screener_data)

    # Format numeric columns
    for col in ["Score", "Piotroski", "Altman Z", "Beneish M", "DCF MoS %"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:.2f}" if x is not None else "N/A")

    st.dataframe(df, width="stretch", hide_index=True, height=500)

    # Export to CSV
    st.divider()
    col_export, _ = st.columns([1, 3])
    with col_export:
        csv = df.to_csv(index=False)
        st.download_button(
            "Export to CSV",
            csv,
            "screener_results.csv",
            "text/csv",
        )

    # Bulk analyze
    st.divider()
    st.subheader("Bulk Analysis")
    tickers_to_analyze = st.text_input(
        "Tickers to analyze (comma-separated)",
        placeholder="AAPL, MSFT, NVDA, MU"
    )
    if st.button("Run Bulk Analysis"):
        if tickers_to_analyze:
            tickers = [t.strip().upper() for t in tickers_to_analyze.split(",")]
            progress = st.progress(0)
            from engine.decision_engine import DecisionEngine
            engine = DecisionEngine()
            for i, t in enumerate(tickers):
                with st.spinner(f"Analyzing {t}..."):
                    try:
                        decision = engine.analyze(t)
                        st.success(f"{t}: {decision.action} (Score: {decision.composite_score:+.1f})")
                    except Exception as e:
                        st.error(f"{t}: {e}")
                progress.progress((i + 1) / len(tickers))
            st.rerun()
