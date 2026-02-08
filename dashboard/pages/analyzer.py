"""Stock Analysis Deep-Dive Dashboard Page."""

import json
import streamlit as st
import yfinance as yf

from database.connection import get_connection
from dashboard.components.charts import create_candlestick_chart, create_radar_chart
from dashboard.components.tables import scoring_breakdown_table


def render():
    """Render the stock analysis deep-dive page."""
    st.header("Stock Analysis Deep-Dive")

    # Ticker search
    ticker = st.text_input("Enter Ticker Symbol", value="", placeholder="AAPL, NVDA, MU...").upper().strip()

    if not ticker:
        st.info("Enter a ticker symbol above to analyze.")
        return

    db = get_connection()

    # Run analysis button
    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        run_analysis = st.button("Run Analysis", type="primary")

    if run_analysis:
        with st.spinner(f"Analyzing {ticker}..."):
            try:
                from engine.decision_engine import DecisionEngine
                engine = DecisionEngine()
                decision = engine.analyze(ticker)
                st.success(f"Analysis complete: {decision.action} (Score: {decision.composite_score:+.1f})")
            except Exception as e:
                st.error(f"Analysis failed: {e}")

    # Get latest analysis results
    results = list(db.execute(
        """SELECT * FROM analysis_results WHERE ticker = ?
           ORDER BY analyzed_at DESC LIMIT 20""",
        (ticker,),
    ))

    if not results:
        st.warning(f"No analysis data for {ticker}. Click 'Run Analysis' or run: python main.py analyze {ticker}")
        return

    # Group by most recent analysis session
    latest_time = results[0]["analyzed_at"]
    latest_results = [r for r in results if r["analyzed_at"] == latest_time]

    # Key metrics
    decision = db.execute_one(
        "SELECT * FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT 1",
        (ticker,),
    )

    if decision:
        col1, col2, col3, col4 = st.columns(4)
        action = decision["action"]
        score = decision["composite_score"]
        conf = decision["confidence"]

        col1.metric("Recommendation", action)
        col2.metric("Score", f"{score:+.1f}/100")
        col3.metric("Confidence", f"{conf:.0%}" if conf else "N/A")
        col4.metric("Position Size", f"{decision['position_size_pct']:.1f}%" if decision.get("position_size_pct") else "N/A")

    st.divider()

    # Two-column layout
    left, right = st.columns([3, 2])

    with left:
        # Price chart
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

                # Calculate SMA
                closes = [p["close"] for p in prices]
                sma_50 = [sum(closes[max(0, i - 50):i]) / min(i, 50) for i in range(1, len(closes) + 1)] if len(closes) >= 50 else None
                sma_200 = [sum(closes[max(0, i - 200):i]) / min(i, 200) for i in range(1, len(closes) + 1)] if len(closes) >= 200 else None

                fig = create_candlestick_chart(prices, ticker, sma_50=sma_50, sma_200=sma_200)
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Could not load price chart: {e}")

    with right:
        # Radar chart of analyzer scores
        st.subheader("Analyzer Scores")
        analyzer_scores = {}
        for r in latest_results:
            analyzer_scores[r["analyzer_name"]] = r["score"]

        if analyzer_scores:
            fig = create_radar_chart(analyzer_scores)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Multi-horizon recommendations
    if decision:
        breakdown = json.loads(decision["analysis_breakdown_json"]) if decision.get("analysis_breakdown_json") else {}

        st.subheader("Analysis Breakdown")
        cols = st.columns(len(latest_results) if latest_results else 1)
        for i, r in enumerate(latest_results):
            with cols[i % len(cols)]:
                score = r["score"]
                color = "green" if score > 10 else "red" if score < -10 else "gray"
                st.markdown(f"**{r['analyzer_name'].title()}**")
                st.markdown(f":{color}[Score: {score:+.1f}] | Conf: {r['confidence']:.0%}")

    # Scoring Models (Piotroski, Altman, Beneish, DCF)
    st.divider()
    st.subheader("Professional Scoring Models")

    scores = list(db.execute(
        """SELECT score_type, score_value, details_json, computed_at
           FROM computed_scores WHERE ticker = ?
           ORDER BY computed_at DESC""",
        (ticker,),
    ))

    # Deduplicate by score_type
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
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Intrinsic Value", f"${dcf['intrinsic_value']:.2f}" if dcf.get("intrinsic_value") else "N/A")
        c2.metric("Current Price", f"${dcf['current_price']:.2f}" if dcf.get("current_price") else "N/A")
        c3.metric("Margin of Safety", f"{dcf['margin_of_safety']:.1f}%" if dcf.get("margin_of_safety") else "N/A")
        c4.metric("Growth Rate", f"{dcf['growth_rate'] * 100:.1f}%" if dcf.get("growth_rate") else "N/A")

    # Factor breakdown
    st.divider()
    st.subheader("Detailed Factor Breakdown")
    for r in latest_results:
        if r.get("factors_json"):
            with st.expander(f"{r['analyzer_name'].title()} Factors"):
                try:
                    factors = json.loads(r["factors_json"])
                    scoring_breakdown_table(factors)
                except (json.JSONDecodeError, TypeError):
                    st.text("Could not parse factors data")
