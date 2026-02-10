"""Stock Analysis Deep-Dive Dashboard Page."""

import json
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

from database.connection import get_connection
from dashboard.components.charts import create_candlestick_chart, create_radar_chart
from dashboard.components.teach_me import teach_if_enabled, teach_me


def render():
    """Render the stock analysis deep-dive page."""
    st.header("Stock Analysis Deep-Dive")

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

    # === KEY METRICS ROW ===
    if decision:
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Recommendation", decision["action"])
        col2.metric("Score", f"{decision['composite_score']:+.1f}/100")
        col3.metric("Confidence", f"{decision['confidence']:.0%}" if decision.get("confidence") else "N/A")
        col4.metric("Conviction", f"{extended.get('conviction_score', 0):.0f}/100")
        col5.metric("Position Size", f"{decision['position_size_pct']:.1f}%" if decision.get("position_size_pct") else "N/A")
        col6.metric("Stop Loss", f"{decision.get('stop_loss_pct', 15):.0f}%")

    teach_if_enabled("composite_score")
    teach_if_enabled("confidence")
    teach_if_enabled("position_size")
    teach_if_enabled("stop_loss")

    st.divider()

    # === PRICE CHART + RADAR ===
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Price Chart")
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            if not hist.empty:
                prices = [{
                    "date": str(d.date()),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                } for d, row in hist.iterrows()]

                closes = [p["close"] for p in prices]
                sma_50 = [sum(closes[max(0, i - 50):i]) / min(i, 50) for i in range(1, len(closes) + 1)] if len(closes) >= 50 else None
                sma_200 = [sum(closes[max(0, i - 200):i]) / min(i, 200) for i in range(1, len(closes) + 1)] if len(closes) >= 200 else None

                # Build buy/sell signal annotations from past decisions
                buy_signals = []
                sell_signals = []
                try:
                    past_decisions = list(db.execute(
                        """SELECT action, composite_score, decided_at
                           FROM decisions WHERE ticker = ?
                           ORDER BY decided_at DESC LIMIT 50""",
                        (ticker,),
                    ))
                    for dec in past_decisions:
                        date_str = dec["decided_at"][:10]
                        matching = [p for p in prices if p["date"] == date_str]
                        if matching:
                            p = matching[0]
                            if dec["action"] in ("BUY", "STRONG_BUY"):
                                buy_signals.append({"date": date_str, "price": p["low"] * 0.98})
                            elif dec["action"] in ("SELL", "STRONG_SELL"):
                                sell_signals.append({"date": date_str, "price": p["high"] * 1.02})
                except Exception:
                    pass

                fig = create_candlestick_chart(prices, ticker, sma_50=sma_50, sma_200=sma_200)

                # Overlay buy/sell signals
                if buy_signals:
                    fig.add_trace(go.Scatter(
                        x=[s["date"] for s in buy_signals],
                        y=[s["price"] for s in buy_signals],
                        mode="markers",
                        marker=dict(symbol="triangle-up", size=12, color="lime"),
                        name="Buy Signal",
                    ))
                if sell_signals:
                    fig.add_trace(go.Scatter(
                        x=[s["date"] for s in sell_signals],
                        y=[s["price"] for s in sell_signals],
                        mode="markers",
                        marker=dict(symbol="triangle-down", size=12, color="red"),
                        name="Sell Signal",
                    ))

                st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"Could not load price chart: {e}")

    with right:
        st.subheader("Analyzer Scores")
        analyzer_scores = {}
        for r in latest_results:
            analyzer_scores[r["analyzer_name"]] = r["score"]

        if analyzer_scores:
            fig = create_radar_chart(analyzer_scores)
            st.plotly_chart(fig, width="stretch")

        # Indicator agreement summary
        if analyzer_scores:
            bullish = sum(1 for s in analyzer_scores.values() if s > 10)
            bearish = sum(1 for s in analyzer_scores.values() if s < -10)
            total = len(analyzer_scores)
            neutral_count = total - bullish - bearish
            if bullish > bearish:
                st.success(f"{bullish}/{total} indicators bullish, {bearish} bearish, {neutral_count} neutral")
            elif bearish > bullish:
                st.error(f"{bearish}/{total} indicators bearish, {bullish} bullish, {neutral_count} neutral")
            else:
                st.info(f"Mixed signals: {bullish} bullish, {bearish} bearish, {neutral_count} neutral")

    st.divider()

    # === MULTI-HORIZON OUTLOOK ===
    horizons = extended.get("horizons", [])
    if horizons:
        st.subheader("Multi-Horizon Outlook")
        horizon_df = pd.DataFrame([{
            "Horizon": h["horizon"].replace("_", " ").title(),
            "Action": h["action"],
            "Score": f"{h['score']:+.1f}",
            "Confidence": f"{h['confidence']:.0%}" if h.get("confidence") else "N/A",
        } for h in horizons])
        st.dataframe(horizon_df, width="stretch", hide_index=True)

    # === PRICE TARGETS ===
    targets = extended.get("price_targets", {})
    if targets and targets.get("blended"):
        st.subheader("Price Targets")
        teach_if_enabled("price_targets")
        current = targets.get("current_price", 0)
        target_data = []
        for key, label in [("dcf", "DCF Intrinsic Value"), ("analyst_consensus", "Analyst Consensus"),
                           ("technical", "Technical Target"), ("blended", "Blended Target")]:
            val = targets.get(key)
            if val:
                upside = ((val / current) - 1) * 100 if current else 0
                target_data.append({"Source": label, "Target": f"${val:,.2f}", "Upside": f"{upside:+.1f}%"})
        if target_data:
            col_t1, col_t2 = st.columns([1, 1])
            with col_t1:
                st.dataframe(pd.DataFrame(target_data), width="stretch", hide_index=True)
            with col_t2:
                if targets.get("analyst_high") and targets.get("analyst_low"):
                    st.metric("Current Price", f"${current:,.2f}")
                    st.metric("Analyst Range", f"${targets['analyst_low']:,.2f} - ${targets['analyst_high']:,.2f}")
                    st.metric("Overall Upside", f"{targets.get('upside_pct', 0):+.1f}%")

    # === SCENARIO ANALYSIS ===
    scenarios = extended.get("scenarios", {})
    if scenarios and scenarios.get("base_price"):
        st.divider()
        current = targets.get("current_price", 0) if targets else 0
        with st.expander("Scenario Analysis (12-month)", expanded=True):
            teach_if_enabled("scenario_analysis")
            scenario_data = []
            for case, color in [("bull", "green"), ("base", "gray"), ("bear", "red")]:
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

    st.divider()

    # === ANALYSIS BREAKDOWN ===
    if decision:
        st.subheader("Analysis Breakdown")
        cols = st.columns(min(len(latest_results), 5))
        for i, r in enumerate(latest_results):
            with cols[i % len(cols)]:
                score = r["score"]
                color = "green" if score > 10 else "red" if score < -10 else "gray"
                st.markdown(f"**{r['analyzer_name'].title()}**")
                st.markdown(f":{color}[Score: {score:+.1f}] | Conf: {r['confidence']:.0%}")

    # === PEER COMPARISON ===
    peers = extended.get("peer_comparison", [])
    if peers:
        st.divider()
        with st.expander("Peer Comparison", expanded=True):
            peer_df = pd.DataFrame([{
                "Metric": p.get("metric", ""),
                "Value": p.get("value", "N/A"),
                "Sector Avg": p.get("sector_avg", "N/A"),
                "vs Sector": "Better" if p.get("better_than_sector") else "Worse",
            } for p in peers])
            st.dataframe(peer_df, width="stretch", hide_index=True)

    # === BULL / BEAR CASE ===
    if decision and (decision.get("bull_case") or decision.get("bear_case")):
        st.divider()
        st.subheader("Investment Thesis")
        col_bull, col_bear = st.columns(2)
        with col_bull:
            if decision.get("bull_case"):
                st.success(f"**Bull Case:** {decision['bull_case']}")
        with col_bear:
            if decision.get("bear_case"):
                st.error(f"**Bear Case:** {decision['bear_case']}")

    # === RISK WARNINGS ===
    if decision and decision.get("risk_warnings"):
        st.divider()
        st.subheader("Risk Warnings")
        for warning in decision["risk_warnings"].split("; "):
            if warning.strip():
                st.warning(warning.strip())

    # === PROFESSIONAL SCORING MODELS ===
    st.divider()
    st.subheader("Professional Scoring Models")
    teach_if_enabled("piotroski_score")
    teach_if_enabled("altman_z_score")

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
    else:
        st.info("No computed scores yet. Run analysis to generate Piotroski, Altman, etc.")

    # DCF Valuation
    dcf = db.execute_one(
        "SELECT * FROM dcf_valuations WHERE ticker = ? ORDER BY computed_at DESC LIMIT 1",
        (ticker,),
    )
    if dcf:
        st.divider()
        st.subheader("DCF Valuation")
        teach_if_enabled("dcf_valuation")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Intrinsic Value", f"${dcf['intrinsic_value']:.2f}" if dcf.get("intrinsic_value") else "N/A")
        c2.metric("Current Price", f"${dcf['current_price']:.2f}" if dcf.get("current_price") else "N/A")
        c3.metric("Margin of Safety", f"{dcf['margin_of_safety']:.1f}%" if dcf.get("margin_of_safety") else "N/A")
        c4.metric("Growth Rate", f"{dcf['growth_rate'] * 100:.1f}%" if dcf.get("growth_rate") else "N/A")

    # === DETAILED FACTOR BREAKDOWN ===
    st.divider()
    st.subheader("Detailed Factor Breakdown")
    for r in latest_results:
        if r.get("factors_json"):
            with st.expander(f"{r['analyzer_name'].title()} Factors"):
                try:
                    factors = json.loads(r["factors_json"])
                    from dashboard.components.tables import scoring_breakdown_table
                    scoring_breakdown_table(factors)
                except (json.JSONDecodeError, TypeError):
                    st.text("Could not parse factors data")
