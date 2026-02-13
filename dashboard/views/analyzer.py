"""Stock Analysis Deep-Dive Dashboard Page."""

import json
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

from database.connection import get_connection
from dashboard.components.charts import (
    create_candlestick_chart, create_radar_chart, create_tv_chart,
)
from dashboard.components.teach_me import teach_if_enabled, teach_me


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_price_history(ticker: str, period: str = "1y") -> list[dict]:
    """Fetch OHLCV price history via yfinance (cached 5 min)."""
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)
    if hist.empty:
        return []
    return [{
        "date": str(d.date()),
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
        "volume": int(row["Volume"]),
    } for d, row in hist.iterrows()]


def render():
    """Render the stock analysis deep-dive page."""
    st.header("Stock Analysis")

    # Ticker search
    ticker = st.text_input("Enter Ticker Symbol", value="", placeholder="AAPL, NVDA, MU...").upper().strip()

    if not ticker:
        st.info("Enter a ticker symbol above to analyze.")
        return

    db = get_connection()

    # Action buttons
    col_btn1, col_btn2, col_status = st.columns([1, 1, 2])
    with col_btn1:
        run_analysis = st.button("Run Analysis", type="primary")
    with col_btn2:
        full_refresh = st.button("Collect & Analyze", help="Collects fresh data from all sources then runs analysis")

    if full_refresh:
        with st.spinner(f"Collecting data for {ticker}..."):
            try:
                from collectors.yahoo_finance import YahooFinanceCollector
                yfc = YahooFinanceCollector()
                yfc.collect(ticker)
            except Exception:
                pass
        with st.spinner(f"Analyzing {ticker}..."):
            try:
                from engine.decision_engine import DecisionEngine
                engine = DecisionEngine()
                result = engine.analyze(ticker)
                st.success(f"Analysis complete: {result.action} (Score: {result.composite_score:+.1f})")
                _fetch_price_history.clear()
            except Exception as e:
                st.error(f"Analysis failed: {e}")

    if run_analysis and not full_refresh:
        with st.spinner(f"Analyzing {ticker}..."):
            try:
                from engine.decision_engine import DecisionEngine
                engine = DecisionEngine()
                result = engine.analyze(ticker)
                st.success(f"Analysis complete: {result.action} (Score: {result.composite_score:+.1f})")
            except Exception as e:
                st.error(f"Analysis failed: {e}")

    # Get latest analysis results
    results = list(db.execute(
        """SELECT * FROM analysis_results WHERE ticker = ?
           ORDER BY analyzed_at DESC LIMIT 20""",
        (ticker,),
    ))

    if not results:
        st.warning(f"No analysis data for {ticker}. Click 'Run Analysis' to get started.")
        return

    # Group by most recent analysis session
    latest_time = results[0]["analyzed_at"]
    latest_results = [r for r in results if r["analyzed_at"] == latest_time]

    # Get decision
    decision = db.execute_one(
        "SELECT * FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT 1",
        (ticker,),
    )

    # Parse extended data
    extended = {}
    if decision and decision.get("extended_data_json"):
        try:
            extended = json.loads(decision["extended_data_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    # === PRICE CHART (full width, TradingView-style) ===
    prices = _fetch_price_history(ticker)
    if prices:
        # Get past decisions for buy/sell markers
        past_decisions = []
        try:
            past_decisions = list(db.execute(
                """SELECT action, composite_score, decided_at
                   FROM decisions WHERE ticker = ?
                   ORDER BY decided_at DESC LIMIT 50""",
                (ticker,),
            ))
        except Exception:
            pass

        # Try TradingView chart first, fall back to Plotly
        tv_rendered = create_tv_chart(prices, ticker, decisions=past_decisions)
        if not tv_rendered:
            # Plotly fallback
            closes = [p["close"] for p in prices]
            sma_50 = [sum(closes[max(0, i - 50):i]) / min(i, 50) for i in range(1, len(closes) + 1)] if len(closes) >= 50 else None
            sma_200 = [sum(closes[max(0, i - 200):i]) / min(i, 200) for i in range(1, len(closes) + 1)] if len(closes) >= 200 else None

            fig = create_candlestick_chart(prices, ticker, sma_50=sma_50, sma_200=sma_200)

            # Overlay buy/sell signals
            for dec in past_decisions:
                date_str = dec["decided_at"][:10]
                matching = [p for p in prices if p["date"] == date_str]
                if matching:
                    p = matching[0]
                    if dec["action"] in ("BUY", "STRONG_BUY"):
                        fig.add_trace(go.Scatter(
                            x=[date_str], y=[p["low"] * 0.98],
                            mode="markers",
                            marker=dict(symbol="triangle-up", size=12, color="#26A69A"),
                            name="Buy Signal", showlegend=False,
                        ))
                    elif dec["action"] in ("SELL", "STRONG_SELL"):
                        fig.add_trace(go.Scatter(
                            x=[date_str], y=[p["high"] * 1.02],
                            mode="markers",
                            marker=dict(symbol="triangle-down", size=12, color="#EF5350"),
                            name="Sell Signal", showlegend=False,
                        ))

            st.plotly_chart(fig, width="stretch")

    st.divider()

    # === KEY METRICS + RADAR (2-column) ===
    left, right = st.columns([3, 2])

    with left:
        if decision:
            col1, col2, col3 = st.columns(3)
            col1.metric("Recommendation", decision["action"])
            col2.metric("Score", f"{decision['composite_score']:+.1f}/100")
            col3.metric("Confidence", f"{decision['confidence']:.0%}" if decision.get("confidence") else "N/A")

            col4, col5, col6 = st.columns(3)
            col4.metric("Conviction", f"{extended.get('conviction_score', 0):.0f}/100")
            col5.metric("Position Size", f"{decision['position_size_pct']:.1f}%" if decision.get("position_size_pct") else "N/A")
            col6.metric("Stop Loss", f"{decision.get('stop_loss_pct', 15):.0f}%")

        # Investment Thesis
        if decision and (decision.get("bull_case") or decision.get("bear_case")):
            col_bull, col_bear = st.columns(2)
            with col_bull:
                if decision.get("bull_case"):
                    st.success(f"**Bull:** {decision['bull_case']}")
            with col_bear:
                if decision.get("bear_case"):
                    st.error(f"**Bear:** {decision['bear_case']}")

    with right:
        analyzer_scores = {}
        for r in latest_results:
            analyzer_scores[r["analyzer_name"]] = r["score"]

        if analyzer_scores:
            fig = create_radar_chart(analyzer_scores)
            st.plotly_chart(fig, width="stretch")

            # Indicator agreement summary
            bullish = sum(1 for s in analyzer_scores.values() if s > 10)
            bearish = sum(1 for s in analyzer_scores.values() if s < -10)
            total = len(analyzer_scores)
            neutral_count = total - bullish - bearish
            if bullish > bearish:
                st.success(f"{bullish}/{total} bullish, {bearish} bearish, {neutral_count} neutral")
            elif bearish > bullish:
                st.error(f"{bearish}/{total} bearish, {bullish} bullish, {neutral_count} neutral")
            else:
                st.info(f"Mixed: {bullish} bullish, {bearish} bearish, {neutral_count} neutral")

    st.divider()

    # === TABBED DETAIL SECTIONS ===
    tab_thesis, tab_scenarios, tab_peers, tab_risk, tab_factors = st.tabs([
        "Thesis", "Scenarios", "Peers", "Risk", "Factors"
    ])

    with tab_thesis:
        # Multi-Horizon Outlook
        horizons = extended.get("horizons", [])
        if horizons:
            st.markdown("**Multi-Horizon Outlook**")
            horizon_df = pd.DataFrame([{
                "Horizon": h["horizon"].replace("_", " ").title(),
                "Action": h["action"],
                "Score": f"{h['score']:+.1f}",
                "Confidence": f"{h['confidence']:.0%}" if h.get("confidence") else "N/A",
            } for h in horizons])
            st.dataframe(horizon_df, width="stretch", hide_index=True)

        # Price Targets
        targets = extended.get("price_targets", {})
        if targets and targets.get("blended"):
            st.markdown("**Price Targets**")
            current = targets.get("current_price", 0)
            target_data = []
            for key, label in [("dcf", "DCF Intrinsic"), ("analyst_consensus", "Analyst"),
                               ("technical", "Technical"), ("blended", "Blended")]:
                val = targets.get(key)
                if val:
                    upside = ((val / current) - 1) * 100 if current else 0
                    target_data.append({"Source": label, "Target": f"${val:,.2f}", "Upside": f"{upside:+.1f}%"})
            if target_data:
                col_t1, col_t2 = st.columns([2, 1])
                with col_t1:
                    st.dataframe(pd.DataFrame(target_data), width="stretch", hide_index=True)
                with col_t2:
                    if targets.get("analyst_high") and targets.get("analyst_low"):
                        st.metric("Current", f"${current:,.2f}")
                        st.metric("Analyst Range", f"${targets['analyst_low']:,.2f} - ${targets['analyst_high']:,.2f}")
                        st.metric("Upside", f"{targets.get('upside_pct', 0):+.1f}%")

        # Analysis breakdown
        if decision:
            st.markdown("**Analyzer Scores**")
            cols = st.columns(min(len(latest_results), 5))
            for i, r in enumerate(latest_results):
                with cols[i % len(cols)]:
                    score = r["score"]
                    color = "green" if score > 10 else "red" if score < -10 else "gray"
                    st.markdown(f"**{r['analyzer_name'].title()}**")
                    st.markdown(f":{color}[{score:+.1f}] | {r['confidence']:.0%}")

    with tab_scenarios:
        scenarios = extended.get("scenarios", {})
        if scenarios and scenarios.get("base_price"):
            current = targets.get("current_price", 0) if targets else 0
            scenario_data = []
            for case in ["bull", "base", "bear"]:
                price = scenarios.get(f"{case}_price")
                prob = scenarios.get(f"{case}_probability", 0)
                reasoning = scenarios.get(f"{case}_reasoning", "")
                if price:
                    upside = ((price / current) - 1) * 100 if current else 0
                    scenario_data.append({
                        "Scenario": case.title(),
                        "Price": f"${price:,.2f}",
                        "Probability": f"{prob:.0%}",
                        "Return": f"{upside:+.1f}%",
                        "Reasoning": reasoning,
                    })
            if scenario_data:
                st.dataframe(pd.DataFrame(scenario_data), width="stretch", hide_index=True)
        else:
            st.info("No scenario analysis available. Run analysis to generate.")

    with tab_peers:
        peers = extended.get("peer_comparison", [])
        if peers:
            peer_df = pd.DataFrame([{
                "Metric": p.get("metric", ""),
                "Value": p.get("value", "N/A"),
                "Sector Avg": p.get("sector_avg", "N/A"),
                "vs Sector": "Better" if p.get("better_than_sector") else "Worse",
            } for p in peers])
            st.dataframe(peer_df, width="stretch", hide_index=True)
        else:
            st.info("No peer comparison data available.")

    with tab_risk:
        # Risk Warnings
        if decision and decision.get("risk_warnings"):
            for warning in decision["risk_warnings"].split("; "):
                if warning.strip():
                    st.warning(warning.strip())
        else:
            st.info("No risk warnings.")

        # Professional Scoring Models
        st.markdown("**Scoring Models**")
        scores = list(db.execute(
            """SELECT score_type, score_value, details_json, computed_at
               FROM computed_scores WHERE ticker = ?
               ORDER BY computed_at DESC""",
            (ticker,),
        ))

        seen = set()
        unique_scores = []
        for s in scores:
            if s["score_type"] not in seen:
                seen.add(s["score_type"])
                unique_scores.append(s)

        if unique_scores:
            score_cols = st.columns(min(len(unique_scores), 4))
            for i, s in enumerate(unique_scores[:4]):
                with score_cols[i]:
                    st.metric(
                        s["score_type"].replace("_", " ").title(),
                        f"{s['score_value']:.2f}",
                    )

        # DCF Valuation
        dcf = db.execute_one(
            "SELECT * FROM dcf_valuations WHERE ticker = ? ORDER BY computed_at DESC LIMIT 1",
            (ticker,),
        )
        if dcf:
            st.markdown("**DCF Valuation**")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Intrinsic Value", f"${dcf['intrinsic_value']:.2f}" if dcf.get("intrinsic_value") else "N/A")
            c2.metric("Current Price", f"${dcf['current_price']:.2f}" if dcf.get("current_price") else "N/A")
            c3.metric("Margin of Safety", f"{dcf['margin_of_safety']:.1f}%" if dcf.get("margin_of_safety") else "N/A")
            c4.metric("Growth Rate", f"{dcf['growth_rate'] * 100:.1f}%" if dcf.get("growth_rate") else "N/A")

    with tab_factors:
        for r in latest_results:
            if r.get("factors_json"):
                with st.expander(f"{r['analyzer_name'].title()} Factors", expanded=True):
                    try:
                        factors = json.loads(r["factors_json"])
                        from dashboard.components.tables import scoring_breakdown_table
                        scoring_breakdown_table(factors)
                    except (json.JSONDecodeError, TypeError):
                        st.text("Could not parse factors data")
