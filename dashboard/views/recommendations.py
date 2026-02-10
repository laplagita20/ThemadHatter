"""Stock Recommendations Page - AI-driven buy/sell/hold recommendations with reasoning.

Scans the full market, not just the watchlist. Uses curated stock universes
(S&P 500, popular growth, dividends, etc.) and yfinance screening.
"""

import json
import streamlit as st
import pandas as pd

from database.connection import get_connection
from database.models import StockDAO
from dashboard.components.teach_me import teach_if_enabled, teach_me

# Curated stock universes for market-wide scanning
STOCK_UNIVERSES = {
    "S&P 500 - Top 50": [
        "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "BRK-B", "TSLA", "UNH", "JNJ",
        "XOM", "JPM", "V", "PG", "MA", "HD", "CVX", "ABBV", "MRK", "LLY",
        "AVGO", "PEP", "KO", "COST", "TMO", "MCD", "WMT", "CSCO", "ACN", "ABT",
        "CRM", "DHR", "NKE", "TXN", "LIN", "NEE", "PM", "UNP", "ORCL", "AMD",
        "INTC", "RTX", "LOW", "AMGN", "UPS", "CAT", "BA", "GS", "SPGI", "BLK",
    ],
    "Growth & Tech": [
        "NVDA", "TSLA", "AMD", "PLTR", "SOFI", "SNOW", "CRWD", "NET", "DDOG", "ZS",
        "SHOP", "SQ", "COIN", "MELI", "SE", "GRAB", "NU", "RBLX", "U", "TTD",
        "ENPH", "SEDG", "FSLR", "PLUG", "ARM", "SMCI", "MRVL", "ON", "ANET", "PANW",
    ],
    "Dividend Aristocrats": [
        "JNJ", "PG", "KO", "PEP", "MMM", "ABT", "ABBV", "MCD", "WMT", "T",
        "XOM", "CVX", "CL", "ED", "GPC", "SWK", "EMR", "ITW", "ADP", "BDX",
        "WBA", "LOW", "SHW", "CINF", "TGT", "AFL", "APD", "MKC", "CTAS", "ROP",
    ],
    "ETFs & Market Indices": [
        "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "ARKK", "XLF", "XLK", "XLE",
        "XLV", "XLI", "XLP", "XLU", "XLB", "XLRE", "GLD", "SLV", "TLT", "HYG",
    ],
    "Value Picks": [
        "BRK-B", "JPM", "BAC", "WFC", "C", "GM", "F", "VZ", "T", "INTC",
        "BMY", "GILD", "MO", "PM", "KHC", "WBA", "DVN", "HAL", "CF", "OXY",
        "DAL", "UAL", "LUV", "MGM", "WYNN", "HBI", "NUE", "CLF", "AA", "X",
    ],
    "Small Cap Movers": [
        "IONQ", "RGTI", "QUBT", "QBTS", "SOUN", "BBAI", "BFLY", "JOBY", "LILM", "ACHR",
        "DNA", "NKLA", "GOEV", "LAZR", "VLDR", "OUST", "ASTS", "MNTS", "ASTR", "SPCE",
        "OPEN", "WISH", "CLOV", "SOFI", "HOOD", "UPST", "AFRM", "BILL", "LMND", "ROOT",
    ],
}


def _action_color(action: str) -> str:
    """Return the theme color for an action."""
    a = action.upper()
    if a in ("STRONG_BUY", "BUY"):
        return "#10b981"
    elif a in ("STRONG_SELL", "SELL"):
        return "#ef4444"
    return "#f59e0b"


def _render_recommendation_card(decision: dict, extended: dict):
    """Render a detailed recommendation card for a single stock."""
    ticker = decision["ticker"]
    action = decision["action"]
    score = decision.get("composite_score", 0)
    confidence = decision.get("confidence", 0)
    conviction = extended.get("conviction_score", 0)
    position_size = decision.get("position_size_pct", 0)
    bull_case = decision.get("bull_case", "")
    bear_case = decision.get("bear_case", "")
    risk_warnings = decision.get("risk_warnings", "")
    stop_loss = decision.get("stop_loss_pct", 15)
    time_horizon = decision.get("time_horizon", "medium_term")
    company = decision.get("company_name", "")

    color = _action_color(action)

    # Card header
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(45, 27, 105, 0.4), rgba(30, 20, 70, 0.6));
                border: 1px solid {color}40; border-radius: 12px;
                padding: 20px; margin-bottom: 16px;
                border-left: 4px solid {color};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div>
                <span style="font-size: 1.5rem; font-weight: 800; color: #f59e0b;">{ticker}</span>
                {"<span style='color: #94a3b8; font-size: 0.9rem; margin-left: 8px;'>" + company[:30] + "</span>" if company else ""}
                <span style="color: {color}; font-weight: 700; font-size: 1.1rem; margin-left: 12px;
                             background: {color}20; padding: 4px 12px; border-radius: 6px;">
                    {action.replace("_", " ")}
                </span>
            </div>
            <div style="text-align: right;">
                <div style="color: #94a3b8; font-size: 0.75rem; text-transform: uppercase;">Score</div>
                <div style="color: {color}; font-size: 1.3rem; font-weight: 700;">{score:+.1f}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Metrics row
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Confidence", f"{confidence:.0%}" if confidence else "N/A")
    m2.metric("Conviction", f"{conviction:.0f}/100" if conviction else "N/A")
    m3.metric("Position Size", f"{position_size:.1f}%" if position_size else "N/A")
    m4.metric("Stop Loss", f"{stop_loss:.0f}%")
    m5.metric("Horizon", time_horizon.replace("_", " ").title())

    # Bull / Bear case
    if bull_case or bear_case:
        c1, c2 = st.columns(2)
        with c1:
            if bull_case:
                st.success(f"**Why it could go up:** {bull_case}")
        with c2:
            if bear_case:
                st.error(f"**Why it could go down:** {bear_case}")

    # Price targets
    targets = extended.get("price_targets", {})
    if targets and targets.get("blended"):
        current = targets.get("current_price", 0)
        blended = targets.get("blended", 0)
        upside = ((blended / current) - 1) * 100 if current else 0
        t1, t2, t3 = st.columns(3)
        t1.metric("Current Price", f"${current:,.2f}" if current else "N/A")
        t2.metric("Target Price", f"${blended:,.2f}" if blended else "N/A")
        t3.metric("Potential Upside", f"{upside:+.1f}%" if current else "N/A")

    # Scenario analysis
    scenarios = extended.get("scenarios", {})
    if scenarios and scenarios.get("base_price"):
        with st.expander("Scenario Analysis"):
            for case in ["bull", "base", "bear"]:
                price = scenarios.get(f"{case}_price")
                prob = scenarios.get(f"{case}_probability", 0)
                reasoning = scenarios.get(f"{case}_reasoning", "")
                if price:
                    case_color = {"bull": "#10b981", "base": "#f59e0b", "bear": "#ef4444"}[case]
                    st.markdown(
                        f"**:{case_color[1:]}[{case.title()} Case]** "
                        f"(${price:,.2f}, {prob:.0%} probability): {reasoning}"
                    )

    # Horizons
    horizons = extended.get("horizons", [])
    if horizons:
        with st.expander("Multi-Horizon Outlook"):
            teach_if_enabled("composite_score", inline=True)
            df = pd.DataFrame([{
                "Horizon": h["horizon"].replace("_", " ").title(),
                "Action": h["action"],
                "Score": f"{h['score']:+.1f}",
                "Confidence": f"{h['confidence']:.0%}" if h.get("confidence") else "N/A",
            } for h in horizons])
            st.dataframe(df, width="stretch", hide_index=True)

    # Risk warnings
    if risk_warnings:
        with st.expander("Risk Warnings"):
            for w in risk_warnings.split("; "):
                if w.strip():
                    st.warning(w.strip())

    # Analysis breakdown
    if decision.get("analysis_breakdown_json"):
        try:
            breakdown = json.loads(decision["analysis_breakdown_json"])
            if breakdown:
                with st.expander("Analysis Breakdown"):
                    for analyzer, score_val in breakdown.items():
                        bar_color = "green" if score_val > 0 else "red" if score_val < 0 else "gray"
                        st.markdown(f"**{analyzer.title()}**: :{bar_color}[{score_val:+.1f}]")
        except (json.JSONDecodeError, TypeError):
            pass

    st.divider()


def render():
    """Render the stock recommendations page."""
    st.header("Stock Recommendations")

    db = get_connection()
    stock_dao = StockDAO()

    # Teach Me section at the top
    teach_if_enabled("buy_recommendation")

    # === SCAN SOURCE ===
    st.subheader("Market Scanner")
    scan_col1, scan_col2 = st.columns([2, 1])
    with scan_col1:
        scan_source = st.selectbox(
            "Scan stocks from",
            ["Previously Analyzed", "S&P 500 - Top 50", "Growth & Tech",
             "Dividend Aristocrats", "ETFs & Market Indices", "Value Picks",
             "Small Cap Movers", "Custom Tickers", "My Watchlist"],
            key="scan_source",
        )
    with scan_col2:
        max_stocks = st.selectbox("Max stocks to scan", [10, 20, 30, 50], index=1, key="max_scan")

    # Custom ticker input
    custom_tickers = []
    if scan_source == "Custom Tickers":
        custom_input = st.text_input(
            "Enter tickers (comma-separated)",
            placeholder="AAPL, NVDA, TSLA, AMZN, MSFT",
            key="custom_tickers",
        )
        if custom_input:
            custom_tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()]

    # Scan buttons
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
    with btn_col1:
        run_scan = st.button("Scan & Analyze", type="primary")
    with btn_col2:
        quick_screen = st.button("Quick Screen (no analysis)")

    # Determine tickers to scan
    if scan_source == "My Watchlist":
        tickers_to_scan = [s["ticker"] for s in stock_dao.get_all_active()]
    elif scan_source == "Custom Tickers":
        tickers_to_scan = custom_tickers
    elif scan_source == "Previously Analyzed":
        tickers_to_scan = []  # Will pull from DB
    else:
        tickers_to_scan = STOCK_UNIVERSES.get(scan_source, [])[:max_stocks]

    # Quick screen - just fetch basic info without full analysis
    if quick_screen and tickers_to_scan:
        with st.spinner(f"Screening {len(tickers_to_scan)} stocks..."):
            import yfinance as yf
            screen_data = []
            progress = st.progress(0)
            for i, ticker in enumerate(tickers_to_scan):
                try:
                    stock = yf.Ticker(ticker)
                    info = stock.info
                    price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                    change = info.get("regularMarketChangePercent", 0)
                    mc = info.get("marketCap", 0)
                    pe = info.get("trailingPE")
                    target = info.get("targetMeanPrice")
                    upside = ((target / price) - 1) * 100 if target and price else None
                    rec = info.get("recommendationKey", "N/A")

                    screen_data.append({
                        "Ticker": ticker,
                        "Company": (info.get("longName") or info.get("shortName", ""))[:25],
                        "Price": f"${price:,.2f}" if price else "N/A",
                        "Change %": f"{change:+.2f}%" if change else "N/A",
                        "Market Cap": f"${mc / 1e9:,.1f}B" if mc > 1e9 else f"${mc / 1e6:,.0f}M" if mc else "N/A",
                        "P/E": f"{pe:.1f}" if pe else "N/A",
                        "Analyst Target": f"${target:,.2f}" if target else "N/A",
                        "Upside": f"{upside:+.1f}%" if upside else "N/A",
                        "Analyst View": rec.replace("_", " ").title() if rec else "N/A",
                        "Sector": info.get("sector", "N/A"),
                    })
                    # Upsert into stocks table for future use
                    stock_dao.upsert(
                        ticker=ticker,
                        company_name=info.get("longName", info.get("shortName", "")),
                        sector=info.get("sector", ""),
                        industry=info.get("industry", ""),
                        market_cap=mc,
                    )
                except Exception:
                    pass
                progress.progress((i + 1) / len(tickers_to_scan))

            if screen_data:
                st.dataframe(pd.DataFrame(screen_data), width="stretch", hide_index=True)
            else:
                st.warning("Could not fetch data for any tickers.")

    # Full scan & analyze
    if run_scan and tickers_to_scan:
        with st.spinner(f"Collecting data & analyzing {len(tickers_to_scan)} stocks (this may take a few minutes)..."):
            progress = st.progress(0)
            from engine.decision_engine import DecisionEngine
            from collectors.yahoo_finance import YahooFinanceCollector

            engine = DecisionEngine()
            yfc = YahooFinanceCollector()
            successes = 0

            for i, ticker in enumerate(tickers_to_scan):
                try:
                    # Collect data first
                    yfc.collect(ticker)
                    # Then analyze
                    engine.analyze(ticker)
                    successes += 1
                except Exception as e:
                    st.caption(f"Skipped {ticker}: {e}")
                progress.progress((i + 1) / len(tickers_to_scan))
            st.success(f"Analyzed {successes} of {len(tickers_to_scan)} stocks!")
            st.rerun()

    st.divider()

    # === FILTER CONTROLS ===
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        filter_action = st.selectbox(
            "Filter by Action",
            ["All", "BUY", "STRONG_BUY", "HOLD", "SELL", "STRONG_SELL"],
            key="rec_filter_action",
        )
    with col2:
        filter_confidence = st.slider(
            "Min Confidence", 0.0, 1.0, 0.0, 0.05,
            key="rec_filter_conf",
        )
    with col3:
        sort_by = st.selectbox(
            "Sort by",
            ["Score (Highest)", "Score (Lowest)", "Confidence", "Most Recent"],
            key="rec_sort",
        )
    with col4:
        show_limit = st.selectbox("Show", [10, 25, 50, 100], key="rec_limit")

    # Build query based on filters
    where_clauses = ["1=1"]
    params = []

    if filter_action != "All":
        where_clauses.append("d.action = ?")
        params.append(filter_action)
    if filter_confidence > 0:
        where_clauses.append("d.confidence >= ?")
        params.append(filter_confidence)

    # Sort
    order = {
        "Score (Highest)": "d.composite_score DESC",
        "Score (Lowest)": "d.composite_score ASC",
        "Confidence": "d.confidence DESC",
        "Most Recent": "d.decided_at DESC",
    }.get(sort_by, "d.composite_score DESC")

    # Get latest decision per ticker (across ALL analyzed stocks, not just watchlist)
    query = f"""
        SELECT d.*, s.company_name, s.sector
        FROM decisions d
        LEFT JOIN stocks s ON d.ticker = s.ticker
        WHERE d.id IN (
            SELECT MAX(id) FROM decisions GROUP BY ticker
        ) AND {' AND '.join(where_clauses)}
        ORDER BY {order}
        LIMIT ?
    """
    params.append(show_limit)

    decisions = list(db.execute(query, tuple(params)))

    # Show data freshness
    latest_decision = db.execute_one(
        "SELECT MAX(decided_at) as last_analyzed FROM decisions"
    )
    if latest_decision and latest_decision.get("last_analyzed"):
        st.caption(f"Latest analysis: {latest_decision['last_analyzed'][:16]}")

    if not decisions:
        st.info(
            "No recommendations yet. Select a stock universe above and click "
            "'Scan & Analyze' to discover opportunities across the market."
        )
        return

    # Summary metrics
    buys = [d for d in decisions if d["action"] in ("BUY", "STRONG_BUY")]
    sells = [d for d in decisions if d["action"] in ("SELL", "STRONG_SELL")]
    holds = [d for d in decisions if d["action"] == "HOLD"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Analyzed", str(len(decisions)))
    m2.metric("Buy Signals", str(len(buys)))
    m3.metric("Hold Signals", str(len(holds)))
    m4.metric("Sell Signals", str(len(sells)))

    st.divider()

    # Quick overview table
    st.subheader("Recommendations Overview")
    overview_data = []
    for d in decisions:
        ext = {}
        if d.get("extended_data_json"):
            try:
                ext = json.loads(d["extended_data_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        targets = ext.get("price_targets", {})
        upside = targets.get("upside_pct", 0) if targets else 0

        overview_data.append({
            "Ticker": d["ticker"],
            "Company": d.get("company_name", "")[:25] if d.get("company_name") else "",
            "Sector": d.get("sector", "")[:15] if d.get("sector") else "",
            "Action": d["action"].replace("_", " "),
            "Score": f"{d['composite_score']:+.1f}",
            "Confidence": f"{d['confidence']:.0%}" if d.get("confidence") else "N/A",
            "Position": f"{d['position_size_pct']:.1f}%" if d.get("position_size_pct") else "-",
            "Upside": f"{upside:+.1f}%" if upside else "-",
            "Date": d.get("decided_at", "")[:10],
        })

    st.dataframe(pd.DataFrame(overview_data), width="stretch", hide_index=True)

    teach_if_enabled("composite_score")
    teach_if_enabled("confidence")
    teach_if_enabled("position_size")

    st.divider()

    # Detailed recommendation cards
    st.subheader("Detailed Analysis")

    # Tabs for Buy / Hold / Sell
    tab_buy, tab_hold, tab_sell = st.tabs(["Buy Signals", "Hold", "Sell Signals"])

    with tab_buy:
        teach_if_enabled("buy_recommendation")
        buy_decisions = [d for d in decisions if d["action"] in ("BUY", "STRONG_BUY")]
        if buy_decisions:
            for d in buy_decisions:
                ext = {}
                if d.get("extended_data_json"):
                    try:
                        ext = json.loads(d["extended_data_json"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                _render_recommendation_card(d, ext)
        else:
            st.info("No buy signals at this time. Try scanning a different stock universe.")

    with tab_hold:
        teach_if_enabled("hold_recommendation")
        hold_decisions = [d for d in decisions if d["action"] == "HOLD"]
        if hold_decisions:
            for d in hold_decisions:
                ext = {}
                if d.get("extended_data_json"):
                    try:
                        ext = json.loads(d["extended_data_json"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                _render_recommendation_card(d, ext)
        else:
            st.info("No hold signals at this time.")

    with tab_sell:
        teach_if_enabled("sell_recommendation")
        sell_decisions = [d for d in decisions if d["action"] in ("SELL", "STRONG_SELL")]
        if sell_decisions:
            for d in sell_decisions:
                ext = {}
                if d.get("extended_data_json"):
                    try:
                        ext = json.loads(d["extended_data_json"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                _render_recommendation_card(d, ext)
        else:
            st.info("No sell signals at this time. All analyzed stocks look acceptable or better.")

    # Educational footer
    st.divider()
    teach_me("stop_loss")
    teach_me("scenario_analysis")
    teach_me("price_targets")
