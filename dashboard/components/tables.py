"""Reusable formatted data table components for the dashboard."""

import streamlit as st
import pandas as pd


def holdings_table(holdings: list[dict]):
    """Display portfolio holdings as a formatted table."""
    if not holdings:
        st.info("No portfolio holdings found.")
        return

    df = pd.DataFrame([{
        "Ticker": h["ticker"],
        "Qty": f"{h['quantity']:.2f}",
        "Avg Cost": f"${h['average_cost']:.2f}" if h.get("average_cost") else "N/A",
        "Price": f"${h['current_price']:.2f}" if h.get("current_price") else "N/A",
        "Value": f"${h['market_value']:,.2f}" if h.get("market_value") else "N/A",
        "P&L": f"${h['unrealized_pl']:,.2f}" if h.get("unrealized_pl") else "N/A",
        "P&L %": f"{h['unrealized_pl_pct']:.1f}%" if h.get("unrealized_pl_pct") else "N/A",
        "Sector": h.get("sector", "N/A"),
    } for h in holdings])

    st.dataframe(df, width="stretch", hide_index=True)


def decisions_table(decisions: list[dict]):
    """Display recent decisions as a formatted table."""
    if not decisions:
        st.info("No recent decisions found.")
        return

    df = pd.DataFrame([{
        "Ticker": d["ticker"],
        "Action": d["action"],
        "Score": f"{d['composite_score']:+.1f}",
        "Confidence": f"{d['confidence']:.0%}" if d.get("confidence") else "N/A",
        "Position": f"{d['position_size_pct']:.1f}%" if d.get("position_size_pct") else "N/A",
        "Date": d.get("decided_at", "")[:10],
    } for d in decisions])

    st.dataframe(df, width="stretch", hide_index=True)


def scoring_breakdown_table(factors: list[dict]):
    """Display analysis factor breakdown."""
    if not factors:
        st.info("No scoring data available.")
        return

    df = pd.DataFrame([{
        "Factor": f["name"],
        "Value": str(f.get("value", "N/A")),
        "Impact": f"{f['impact']:+.0f}",
        "Explanation": f.get("explanation", "")[:80],
    } for f in factors])

    st.dataframe(df, width="stretch", hide_index=True)


def stress_test_table(stress_results: list[dict]):
    """Display stress test results."""
    if not stress_results:
        st.info("No stress test results available.")
        return

    df = pd.DataFrame([{
        "Scenario": s["scenario_name"],
        "Market Shock": f"{s['market_shock_pct']:.0f}%",
        "Portfolio Impact": f"{s['portfolio_impact_pct']:+.1f}%",
        "Loss": f"${s['portfolio_loss']:+,.0f}",
        "Value After": f"${s['portfolio_value_after']:,.0f}",
    } for s in stress_results])

    st.dataframe(df, width="stretch", hide_index=True)


def kelly_table(kelly_data: dict):
    """Display Kelly Criterion sizing."""
    if kelly_data.get("kelly_pct") is None:
        st.info(f"Kelly Criterion: {kelly_data.get('reason', 'Insufficient data')}")
        return

    cols = st.columns(4)
    cols[0].metric("Full Kelly", f"{kelly_data['kelly_pct']:.1f}%")
    cols[1].metric("Half Kelly", f"{kelly_data['half_kelly_pct']:.1f}%")
    cols[2].metric("Win Rate", f"{kelly_data['win_rate']:.0%}")
    cols[3].metric("W/L Ratio", f"{kelly_data['win_loss_ratio']:.2f}")


def macro_indicators_table(regimes: dict):
    """Display key macro indicators."""
    rows = []
    indicator_map = {
        "growth": ("GDP Growth Regime", None),
        "rate": ("Interest Rate Regime", None),
        "inflation": ("Inflation Regime", None),
        "yield_curve": ("Yield Curve Spread", "%"),
        "vix": ("VIX", ""),
        "unemployment": ("Unemployment Rate", "%"),
        "consumer_sentiment": ("Consumer Sentiment", ""),
        "credit_spread": ("HY Credit Spread", "%"),
        "financial_stress_index": ("Financial Stress Index", ""),
        "breakeven_inflation": ("Breakeven Inflation", "%"),
        "jobless_claims": ("Initial Jobless Claims", ""),
    }

    for key, (label, unit) in indicator_map.items():
        if key in regimes:
            val = regimes[key]
            if unit == "%":
                display = f"{val:.2f}%"
            elif isinstance(val, (int, float)):
                display = f"{val:,.1f}"
            else:
                display = str(val).title()
            rows.append({"Indicator": label, "Value": display})

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No macro data available. Run: python main.py collect --source fred")
