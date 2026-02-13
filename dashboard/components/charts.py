"""Reusable chart components for the dashboard."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np


def create_tv_chart(prices: list[dict], ticker: str = "",
                    decisions: list[dict] = None, height: int = 500) -> bool:
    """Render a TradingView-style candlestick chart with volume.

    Uses streamlit-lightweight-charts for a native TradingView look.
    Falls back to Plotly candlestick if the package is not installed.

    Returns True if rendered successfully, False to signal fallback needed.
    """
    try:
        from streamlit_lightweight_charts import renderLightweightCharts
        import streamlit as st

        if not prices:
            return False

        # Build candlestick data
        candle_data = []
        volume_data = []
        for p in prices:
            candle_data.append({
                "time": p["date"],
                "open": p["open"],
                "high": p["high"],
                "low": p["low"],
                "close": p["close"],
            })
            is_up = p["close"] >= p["open"]
            volume_data.append({
                "time": p["date"],
                "value": p.get("volume", 0),
                "color": "rgba(38, 166, 154, 0.5)" if is_up else "rgba(239, 83, 80, 0.5)",
            })

        # SMA calculations
        closes = [p["close"] for p in prices]
        sma_50_data = []
        sma_200_data = []
        for i in range(len(closes)):
            if i >= 49:
                sma_50_data.append({
                    "time": prices[i]["date"],
                    "value": sum(closes[i - 49:i + 1]) / 50,
                })
            if i >= 199:
                sma_200_data.append({
                    "time": prices[i]["date"],
                    "value": sum(closes[i - 199:i + 1]) / 200,
                })

        # Build series
        series = [
            {
                "type": "Candlestick",
                "data": candle_data,
                "options": {
                    "upColor": "#26A69A",
                    "downColor": "#EF5350",
                    "borderVisible": False,
                    "wickUpColor": "#26A69A",
                    "wickDownColor": "#EF5350",
                },
            },
        ]

        if sma_50_data:
            series.append({
                "type": "Line",
                "data": sma_50_data,
                "options": {
                    "color": "#FF9800",
                    "lineWidth": 1,
                    "title": "SMA 50",
                },
            })

        if sma_200_data:
            series.append({
                "type": "Line",
                "data": sma_200_data,
                "options": {
                    "color": "#2962FF",
                    "lineWidth": 1,
                    "title": "SMA 200",
                },
            })

        # Buy/sell markers from decisions
        if decisions:
            buy_markers = []
            sell_markers = []
            date_set = {p["date"] for p in prices}
            for d in decisions:
                date_str = d.get("decided_at", "")[:10]
                if date_str not in date_set:
                    continue
                matching = [p for p in prices if p["date"] == date_str]
                if not matching:
                    continue
                p = matching[0]
                action = d.get("action", "")
                if action in ("BUY", "STRONG_BUY"):
                    buy_markers.append({
                        "time": date_str,
                        "position": "belowBar",
                        "color": "#26A69A",
                        "shape": "arrowUp",
                        "text": "Buy",
                    })
                elif action in ("SELL", "STRONG_SELL"):
                    sell_markers.append({
                        "time": date_str,
                        "position": "aboveBar",
                        "color": "#EF5350",
                        "shape": "arrowDown",
                        "text": "Sell",
                    })

            if buy_markers or sell_markers:
                # Markers are attached to the candlestick series
                series[0]["markers"] = buy_markers + sell_markers

        chart_options = {
            "height": height,
            "layout": {
                "background": {"type": "solid", "color": "#131722"},
                "textColor": "#D1D4DC",
            },
            "grid": {
                "vertLines": {"color": "#1E222D"},
                "horzLines": {"color": "#1E222D"},
            },
            "timeScale": {
                "borderColor": "#2A2E39",
                "timeVisible": False,
            },
            "rightPriceScale": {
                "borderColor": "#2A2E39",
            },
        }

        # Volume chart
        volume_chart_options = {
            "height": 120,
            "layout": {
                "background": {"type": "solid", "color": "#131722"},
                "textColor": "#787B86",
            },
            "grid": {
                "vertLines": {"color": "#1E222D"},
                "horzLines": {"color": "#1E222D"},
            },
            "timeScale": {
                "borderColor": "#2A2E39",
                "timeVisible": False,
            },
            "rightPriceScale": {
                "borderColor": "#2A2E39",
            },
        }

        volume_series = [{
            "type": "Histogram",
            "data": volume_data,
            "options": {
                "priceFormat": {"type": "volume"},
                "priceScaleId": "",
            },
        }]

        renderLightweightCharts([
            {"chart": chart_options, "series": series},
            {"chart": volume_chart_options, "series": volume_series},
        ], f"tv_chart_{ticker}")

        return True

    except ImportError:
        return False
    except Exception:
        return False


def create_candlestick_chart(prices: list[dict], ticker: str,
                              sma_50: list = None, sma_200: list = None,
                              bb_upper: list = None, bb_lower: list = None) -> go.Figure:
    """Create a candlestick chart with optional technical overlays."""
    dates = [p["date"] for p in prices]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=[0.7, 0.3])

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=dates,
        open=[p["open"] for p in prices],
        high=[p["high"] for p in prices],
        low=[p["low"] for p in prices],
        close=[p["close"] for p in prices],
        name="Price",
    ), row=1, col=1)

    # SMA overlays
    if sma_50:
        fig.add_trace(go.Scatter(
            x=dates[-len(sma_50):], y=sma_50,
            name="SMA 50", line=dict(color="orange", width=1),
        ), row=1, col=1)
    if sma_200:
        fig.add_trace(go.Scatter(
            x=dates[-len(sma_200):], y=sma_200,
            name="SMA 200", line=dict(color="blue", width=1),
        ), row=1, col=1)

    # Bollinger Bands
    if bb_upper and bb_lower:
        fig.add_trace(go.Scatter(
            x=dates[-len(bb_upper):], y=bb_upper,
            name="BB Upper", line=dict(color="gray", width=1, dash="dot"),
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=dates[-len(bb_lower):], y=bb_lower,
            name="BB Lower", line=dict(color="gray", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(128,128,128,0.1)",
        ), row=1, col=1)

    # Volume
    colors = ["green" if p["close"] >= p["open"] else "red" for p in prices]
    fig.add_trace(go.Bar(
        x=dates,
        y=[p.get("volume", 0) for p in prices],
        name="Volume",
        marker_color=colors,
        opacity=0.5,
    ), row=2, col=1)

    fig.update_layout(
        title=f"{ticker} Price Chart",
        xaxis_rangeslider_visible=False,
        height=500,
        template="plotly_dark",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

    return fig


def create_radar_chart(analyzer_scores: dict) -> go.Figure:
    """Create a radar chart of analyzer scores."""
    categories = list(analyzer_scores.keys())
    values = [analyzer_scores[c] for c in categories]
    # Close the polygon
    categories.append(categories[0])
    values.append(values[0])

    fig = go.Figure(data=go.Scatterpolar(
        r=values,
        theta=[c.title() for c in categories],
        fill="toself",
        fillcolor="rgba(0,176,246,0.2)",
        line=dict(color="rgb(0,176,246)"),
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[-100, 100]),
        ),
        showlegend=False,
        title="Analyzer Scores",
        height=400,
        template="plotly_dark",
    )
    return fig


def create_gauge_chart(value: float, title: str, min_val: float = 0,
                        max_val: float = 100, suffix: str = "") -> go.Figure:
    """Create a gauge/meter chart."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title},
        number={"suffix": suffix},
        gauge={
            "axis": {"range": [min_val, max_val]},
            "bar": {"color": "darkblue"},
            "steps": [
                {"range": [min_val, max_val * 0.33], "color": "lightgreen"},
                {"range": [max_val * 0.33, max_val * 0.66], "color": "yellow"},
                {"range": [max_val * 0.66, max_val], "color": "red"},
            ],
        },
    ))
    fig.update_layout(height=250, template="plotly_dark")
    return fig


def create_var_gauge(var_pct: float, title: str = "Value at Risk (95%)") -> go.Figure:
    """Create a VaR gauge chart."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=var_pct,
        title={"text": title},
        number={"suffix": "%"},
        gauge={
            "axis": {"range": [0, 15]},
            "bar": {"color": "darkblue"},
            "steps": [
                {"range": [0, 3], "color": "green"},
                {"range": [3, 7], "color": "yellow"},
                {"range": [7, 15], "color": "red"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 10,
            },
        },
    ))
    fig.update_layout(height=250, template="plotly_dark")
    return fig


def create_monte_carlo_fan_chart(fan_chart: dict, portfolio_value: float) -> go.Figure:
    """Create a Monte Carlo fan chart showing P10/P50/P90 paths."""
    fig = go.Figure()

    n_points = len(fan_chart.get("p10", []))
    x = list(range(n_points))

    fig.add_trace(go.Scatter(
        x=x, y=fan_chart.get("p90", []),
        name="90th Percentile (Bull)",
        line=dict(color="green", width=1),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=fan_chart.get("p10", []),
        name="10th Percentile (Bear)",
        line=dict(color="red", width=1),
        fill="tonexty", fillcolor="rgba(128,128,128,0.15)",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=fan_chart.get("p50", []),
        name="50th Percentile (Base)",
        line=dict(color="white", width=2),
    ))

    # Starting value line
    fig.add_hline(y=portfolio_value, line_dash="dash", line_color="gray",
                  annotation_text=f"Starting: ${portfolio_value:,.0f}")

    fig.update_layout(
        title="Monte Carlo Simulation - 12 Month Outlook",
        xaxis_title="Trading Days",
        yaxis_title="Portfolio Value ($)",
        height=400,
        template="plotly_dark",
    )
    return fig


def create_correlation_heatmap(tickers: list, matrix: list) -> go.Figure:
    """Create a correlation matrix heatmap."""
    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=tickers,
        y=tickers,
        colorscale="RdBu",
        zmid=0,
        zmin=-1,
        zmax=1,
        text=[[f"{v:.2f}" for v in row] for row in matrix],
        texttemplate="%{text}",
        textfont={"size": 10},
    ))

    fig.update_layout(
        title="Holdings Correlation Matrix",
        height=max(400, len(tickers) * 50),
        template="plotly_dark",
    )
    return fig


def create_sector_pie_chart(sector_weights: dict) -> go.Figure:
    """Create a sector allocation pie chart."""
    fig = go.Figure(data=[go.Pie(
        labels=list(sector_weights.keys()),
        values=list(sector_weights.values()),
        hole=0.4,
        textinfo="label+percent",
        textposition="auto",
    )])

    fig.update_layout(
        title="Sector Allocation",
        height=350,
        template="plotly_dark",
    )
    return fig


def create_performance_chart(dates: list, portfolio_values: list,
                              benchmark_values: list = None,
                              benchmark_name: str = "SPY") -> go.Figure:
    """Create portfolio performance vs benchmark chart."""
    fig = go.Figure()

    # Normalize to percentage returns from start
    if portfolio_values:
        base = portfolio_values[0]
        port_returns = [(v / base - 1) * 100 for v in portfolio_values]
        fig.add_trace(go.Scatter(
            x=dates, y=port_returns,
            name="Portfolio",
            line=dict(color="cyan", width=2),
        ))

    if benchmark_values:
        base_bm = benchmark_values[0]
        bm_returns = [(v / base_bm - 1) * 100 for v in benchmark_values]
        fig.add_trace(go.Scatter(
            x=dates, y=bm_returns,
            name=benchmark_name,
            line=dict(color="gray", width=1, dash="dot"),
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="gray")

    fig.update_layout(
        title="Portfolio vs Benchmark",
        xaxis_title="Date",
        yaxis_title="Return (%)",
        height=350,
        template="plotly_dark",
    )
    return fig


def create_dalio_quadrant_chart(quadrant: str) -> go.Figure:
    """Create Dalio's 4-quadrant economic machine visualization."""
    # Quadrant positions
    quadrants = {
        "goldilocks": (0.75, 0.75),
        "disinflation_boom": (0.75, 0.25),
        "stagflation": (0.25, 0.75),
        "deflation": (0.25, 0.25),
    }

    fig = go.Figure()

    # Draw quadrant boxes
    labels = {
        (0.75, 0.75): "Goldilocks\n(Growth+, Inflation+)",
        (0.75, 0.25): "Disinflation Boom\n(Growth+, Inflation-)",
        (0.25, 0.75): "Stagflation\n(Growth-, Inflation+)",
        (0.25, 0.25): "Deflation\n(Growth-, Inflation-)",
    }

    colors = {
        "goldilocks": "rgba(0,200,0,0.3)",
        "disinflation_boom": "rgba(0,100,200,0.3)",
        "stagflation": "rgba(200,100,0,0.3)",
        "deflation": "rgba(200,0,0,0.3)",
    }

    for q_name, (x, y) in quadrants.items():
        is_current = q_name == quadrant
        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(
                size=80 if is_current else 50,
                color=colors.get(q_name, "gray"),
                line=dict(color="white" if is_current else "gray", width=3 if is_current else 1),
            ),
            text=[labels[(x, y)]],
            textposition="middle center",
            textfont=dict(size=12 if is_current else 10, color="white"),
            showlegend=False,
        ))

    fig.update_layout(
        title="Dalio's Economic Machine - Current Regime",
        xaxis=dict(title="Growth", range=[0, 1], showgrid=False, showticklabels=False),
        yaxis=dict(title="Inflation", range=[0, 1], showgrid=False, showticklabels=False),
        height=400,
        template="plotly_dark",
    )

    # Add axis labels
    fig.add_annotation(x=0.1, y=0.5, text="Growth -", showarrow=False, font=dict(color="gray"))
    fig.add_annotation(x=0.9, y=0.5, text="Growth +", showarrow=False, font=dict(color="gray"))
    fig.add_annotation(x=0.5, y=0.1, text="Inflation -", showarrow=False, font=dict(color="gray"))
    fig.add_annotation(x=0.5, y=0.9, text="Inflation +", showarrow=False, font=dict(color="gray"))

    return fig


def create_stress_test_chart(stress_results: list) -> go.Figure:
    """Create a horizontal bar chart of stress test results."""
    scenarios = [s["scenario_name"] for s in stress_results]
    impacts = [s["portfolio_impact_pct"] for s in stress_results]
    colors = ["red" if i < -20 else "orange" if i < -10 else "yellow" for i in impacts]

    fig = go.Figure(go.Bar(
        x=impacts,
        y=scenarios,
        orientation="h",
        marker_color=colors,
        text=[f"{i:.1f}%" for i in impacts],
        textposition="auto",
    ))

    fig.update_layout(
        title="Stress Test Scenarios - Portfolio Impact",
        xaxis_title="Portfolio Impact (%)",
        height=300,
        template="plotly_dark",
    )
    return fig
