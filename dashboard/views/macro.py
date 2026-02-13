"""Macro & Market Dashboard Page."""

import streamlit as st
import plotly.graph_objects as go

from database.models import MacroDAO
from analysis.macroeconomic import MacroeconomicAnalyzer
from dashboard.components.charts import create_dalio_quadrant_chart
from dashboard.components.tables import macro_indicators_table


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_regimes() -> dict:
    """Detect macro regimes (cached 1 hour)."""
    analyzer = MacroeconomicAnalyzer()
    return analyzer._detect_regimes()


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_dalio_quadrant(regimes_key: str) -> dict | None:
    """Detect Dalio quadrant from regimes (cached 1 hour)."""
    analyzer = MacroeconomicAnalyzer()
    regimes = analyzer._detect_regimes()
    return analyzer._detect_dalio_quadrant(regimes)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_recession_probability(regimes_key: str) -> float | None:
    """Calculate recession probability (cached 1 hour)."""
    analyzer = MacroeconomicAnalyzer()
    regimes = analyzer._detect_regimes()
    return analyzer._calculate_recession_probability(regimes)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_macro_series(series_id: str, limit: int = 252) -> list[dict]:
    """Fetch a FRED macro series from the database (cached 1 hour)."""
    macro_dao = MacroDAO()
    return list(macro_dao.get_series(series_id, limit=limit))


def render():
    """Render the macro & market page."""
    st.header("Macro & Market Overview")

    macro_dao = MacroDAO()
    analyzer = MacroeconomicAnalyzer()

    # Detect current regimes (cached)
    regimes = _cached_regimes()

    if not regimes:
        st.warning("No macro data available. Run: python main.py collect --source fred")
        return

    # === Dalio Quadrant ===
    st.subheader("Dalio's Economic Machine")
    # Use a stable key derived from regimes for caching
    regimes_key = str(sorted(regimes.items())) if regimes else ""
    dalio = _cached_dalio_quadrant(regimes_key)

    col1, col2 = st.columns([2, 1])

    with col1:
        if dalio:
            fig = create_dalio_quadrant_chart(dalio["quadrant"])
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Insufficient data for Dalio quadrant detection.")

    with col2:
        if dalio:
            st.markdown(f"### Current Regime")
            st.markdown(f"**{dalio['label']}**")
            st.markdown(f"- Stocks: {dalio.get('stocks', 'N/A')}")
            st.markdown(f"- Bonds: {dalio.get('bonds', 'N/A')}")
            st.markdown(f"- Commodities: {dalio.get('commodities', 'N/A')}")

            from analysis.macroeconomic import DALIO_SECTOR_MAP
            favored = DALIO_SECTOR_MAP.get(dalio["quadrant"], [])
            if favored:
                st.markdown(f"**Favored Sectors:** {', '.join(favored)}")

    st.divider()

    # === Key Economic Indicators ===
    st.subheader("Key Economic Indicators")

    # Display regime gauges
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        growth = regimes.get("growth", "N/A")
        color = "green" if growth == "high" else "red" if growth == "low" else "gray"
        st.markdown(f"**GDP Growth**")
        st.markdown(f":{color}[{growth.title() if isinstance(growth, str) else growth}]")
        if "gdp_growth_rate" in regimes:
            st.caption(f"YoY: {regimes['gdp_growth_rate']:.1f}%")

    with col2:
        inflation = regimes.get("inflation", "N/A")
        color = "red" if inflation == "high" else "green" if inflation == "low" else "gray"
        st.markdown(f"**Inflation**")
        st.markdown(f":{color}[{inflation.title() if isinstance(inflation, str) else inflation}]")
        if "inflation_rate" in regimes:
            st.caption(f"CPI YoY: {regimes['inflation_rate']:.1f}%")

    with col3:
        rate = regimes.get("rate", "N/A")
        color = "red" if rate == "rising" else "green" if rate == "falling" else "gray"
        st.markdown(f"**Interest Rates**")
        st.markdown(f":{color}[{rate.title() if isinstance(rate, str) else rate}]")

    with col4:
        yc = regimes.get("yield_curve")
        if yc is not None:
            color = "red" if yc < 0 else "green" if yc > 0.5 else "orange"
            st.markdown(f"**Yield Curve**")
            st.markdown(f":{color}[{yc:.2f}%]")
            if yc < 0:
                st.caption("INVERTED - recession signal")
        else:
            st.markdown("**Yield Curve**")
            st.markdown(":gray[N/A]")

    st.divider()

    # === Yield Curve Chart ===
    st.subheader("Treasury Yield Curve")
    _render_yield_curve_chart(macro_dao)

    st.divider()

    # === Credit Spread Chart ===
    st.subheader("High Yield Credit Spread")
    _render_series_chart(macro_dao, "BAMLH0A0HYM2", "ICE BofA HY Spread (%)", "red")

    # === Financial Stress ===
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Financial Stress Index")
        fsi = regimes.get("financial_stress_index")
        if fsi is not None:
            color = "red" if fsi > 0 else "green"
            st.metric("St. Louis FSI", f"{fsi:.2f}",
                       delta="Above Normal" if fsi > 0 else "Normal")
        _render_series_chart(macro_dao, "STLFSI4", "St. Louis Fed FSI", "orange")

    with col2:
        st.subheader("VIX (Fear Index)")
        vix = regimes.get("vix")
        if vix is not None:
            color = "red" if vix > 25 else "green"
            st.metric("VIX", f"{vix:.1f}",
                       delta="Elevated" if vix > 25 else "Calm")
        _render_series_chart(macro_dao, "VIXCLS", "CBOE VIX", "purple")

    st.divider()

    # === Recession Probability ===
    st.subheader("Recession Probability")
    recession_prob = _cached_recession_probability(regimes_key)
    if recession_prob is not None:
        color = "red" if recession_prob > 40 else "orange" if recession_prob > 20 else "green"
        st.metric("Recession Probability", f"{recession_prob:.0f}%")
        st.progress(min(recession_prob / 100, 1.0))
        if recession_prob > 50:
            st.error("HIGH recession probability - defensive posture recommended")
        elif recession_prob > 30:
            st.warning("Elevated recession risk - reduce equity exposure")

    st.divider()

    # === Full Indicators Table ===
    st.subheader("All Macro Indicators")
    macro_indicators_table(regimes)


def _render_yield_curve_chart(macro_dao):
    """Render yield curve chart using 2Y and 10Y treasury data."""
    try:
        dgs10 = _cached_macro_series("DGS10", 252)
        dgs2 = _cached_macro_series("DGS2", 252)
        spread = _cached_macro_series("T10Y2Y", 252)

        if not spread:
            st.info("No yield curve data available.")
            return

        dates = [s["date"] for s in reversed(spread)]
        values = [s["value"] for s in reversed(spread)]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=values,
            name="10Y-2Y Spread",
            line=dict(color="cyan", width=2),
            fill="tozeroy",
            fillcolor="rgba(0,200,200,0.1)",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="red",
                      annotation_text="Inversion Threshold")
        fig.update_layout(
            xaxis_title="Date", yaxis_title="Spread (%)",
            height=300, template="plotly_dark",
        )
        st.plotly_chart(fig, width="stretch")
    except Exception as e:
        st.warning(f"Yield curve chart failed: {e}")


def _render_series_chart(macro_dao, series_id: str, title: str, color: str):
    """Render a FRED series line chart."""
    try:
        data = _cached_macro_series(series_id, 120)
        if not data:
            return

        dates = [d["date"] for d in reversed(data)]
        values = [d["value"] for d in reversed(data)]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=values,
            name=title,
            line=dict(color=color, width=2),
        ))
        fig.update_layout(
            height=200, template="plotly_dark",
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, width="stretch")
    except Exception:
        pass
