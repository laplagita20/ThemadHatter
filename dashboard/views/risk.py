"""Risk Dashboard Page."""

import streamlit as st
from engine.risk_manager import RiskManager
from dashboard.components.charts import (
    create_var_gauge, create_monte_carlo_fan_chart,
    create_correlation_heatmap, create_stress_test_chart,
)
from dashboard.components.tables import kelly_table, stress_test_table
from dashboard.components.teach_me import teach_if_enabled


def render():
    """Render the risk dashboard page."""
    st.header("Risk Dashboard")

    rm = RiskManager()

    # Generate report button
    if st.button("Generate Risk Report", type="primary"):
        with st.spinner("Running risk analysis (VaR, Monte Carlo, stress tests...)"):
            report = rm.generate_risk_report()
            st.session_state["risk_report"] = report

    report = st.session_state.get("risk_report")
    if not report:
        # Try loading from cached data
        st.info("Click 'Generate Risk Report' to run full risk analysis, or run: python main.py risk-report")

        # Show basic portfolio risk summary
        summary = rm.get_portfolio_risk_summary()
        if summary.get("status") == "ok":
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Portfolio Value", f"${summary['total_value']:,.2f}")
            col2.metric("Positions", str(summary["num_positions"]))
            col3.metric("Sectors", str(summary["num_sectors"]))
            col4.metric("HHI Index", f"{summary['hhi']:.4f}")
        return

    # === VaR Section ===
    st.subheader("Value at Risk")
    teach_if_enabled("var")
    var_data = report.get("var", {})
    if "error" not in var_data:
        col1, col2, col3 = st.columns(3)

        with col1:
            fig = create_var_gauge(
                var_data.get("historical_var_pct", 0),
                "VaR 95% (5-day)"
            )
            st.plotly_chart(fig, width="stretch")

        with col2:
            fig = create_var_gauge(
                var_data.get("var_99_pct", 0),
                "VaR 99% (5-day)"
            )
            st.plotly_chart(fig, width="stretch")

        with col3:
            st.metric("95% VaR ($)", f"${var_data.get('historical_var_dollar', 0):,.2f}")
            st.metric("99% VaR ($)", f"${var_data.get('var_99_dollar', 0):,.2f}")
            st.metric("CVaR 95% ($)", f"${var_data.get('cvar_dollar', 0):,.2f}")
            st.metric("Annual Volatility", f"{var_data.get('portfolio_volatility_annual', 0):.1f}%")
    else:
        st.warning(f"VaR calculation: {var_data.get('error')}")

    st.divider()

    # === Monte Carlo Section ===
    st.subheader("Monte Carlo Simulation (12-month)")
    teach_if_enabled("monte_carlo")
    mc = report.get("monte_carlo", {})
    if "error" not in mc:
        # Fan chart
        if mc.get("fan_chart"):
            fig = create_monte_carlo_fan_chart(
                mc["fan_chart"],
                mc.get("portfolio_value", 0),
            )
            st.plotly_chart(fig, width="stretch")

        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Bear Case (10th)", f"${mc.get('bear_case', 0):,.2f}")
        col2.metric("Base Case (50th)", f"${mc.get('base_case', 0):,.2f}")
        col3.metric("Bull Case (90th)", f"${mc.get('bull_case', 0):,.2f}")
        col4.metric("Expected Return", f"{mc.get('expected_return_pct', 0):+.1f}%")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("P(Positive Return)", f"{mc.get('prob_positive_return', 0):.0%}")
        col6.metric("P(>10% Gain)", f"{mc.get('prob_10pct_gain', 0):.0%}")
        col7.metric("P(>10% Loss)", f"{mc.get('prob_10pct_loss', 0):.0%}")
        col8.metric("Simulations", f"{mc.get('num_simulations', 0):,}")
    else:
        st.warning(f"Monte Carlo: {mc.get('error')}")

    st.divider()

    # === Correlation Section ===
    st.subheader("Correlation & Diversification")
    teach_if_enabled("diversification")
    corr = report.get("correlation", {})
    if "error" not in corr:
        col1, col2 = st.columns([2, 1])

        with col1:
            if corr.get("correlation_matrix") and corr.get("tickers"):
                fig = create_correlation_heatmap(corr["tickers"], corr["correlation_matrix"])
                st.plotly_chart(fig, width="stretch")

        with col2:
            div_ratio = corr.get("diversification_ratio", 0)
            st.metric("Diversification Ratio", f"{div_ratio:.2f}",
                       delta="Well Diversified" if div_ratio > 1.2 else "Needs Improvement")
            st.metric("Max Correlation", f"{corr.get('max_correlation', 0):.2f}")

            if corr.get("high_corr_pairs"):
                st.warning("Highly correlated pairs (>0.8):")
                for pair in corr["high_corr_pairs"]:
                    st.text(f"  {pair['pair']}: {pair['correlation']:.2f}")
    else:
        st.warning(f"Correlation: {corr.get('error')}")

    st.divider()

    # === Stress Tests ===
    st.subheader("Stress Tests")
    stress = report.get("stress_tests", [])
    if stress and "error" not in stress[0]:
        fig = create_stress_test_chart(stress)
        st.plotly_chart(fig, width="stretch")
        stress_test_table(stress)
    else:
        st.info("No stress test results available.")

    st.divider()

    # === Kelly Criterion ===
    st.subheader("Kelly Criterion Position Sizing")
    kelly = report.get("kelly_criterion", {})
    kelly_table(kelly)

    st.divider()

    # === Drawdown ===
    st.subheader("Maximum Drawdown")
    dd = report.get("max_drawdown", {})
    if "error" not in dd:
        col1, col2, col3 = st.columns(3)
        col1.metric("Max Drawdown", f"{dd.get('max_drawdown_pct', 0):.1f}%")
        col2.metric("Current Drawdown", f"{dd.get('current_drawdown_pct', 0):.1f}%")
        col3.metric("Peak Equity", f"${dd.get('peak_equity', 0):,.2f}")

        if dd.get("circuit_breaker_active"):
            st.error("CIRCUIT BREAKER ACTIVE - Position sizes should be reduced by 50%")
        for alert in dd.get("alerts", []):
            st.warning(alert)
    else:
        st.info(f"Drawdown: {dd.get('error')}")
