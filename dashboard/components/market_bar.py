"""Market bar component — top indices ticker and market status."""

from datetime import datetime, timezone, timedelta
import streamlit as st


def get_market_status() -> str:
    """Determine current US market status based on Eastern Time."""
    try:
        # US Eastern Time (UTC-5, UTC-4 during DST)
        import time as _time
        # Simple DST check: March-November is roughly DST
        now_utc = datetime.now(timezone.utc)
        month = now_utc.month
        is_dst = 3 <= month <= 10
        et_offset = timedelta(hours=-4 if is_dst else -5)
        now_et = now_utc + et_offset

        weekday = now_et.weekday()  # 0=Monday, 6=Sunday
        hour = now_et.hour
        minute = now_et.minute
        current_minutes = hour * 60 + minute

        if weekday >= 5:  # Saturday or Sunday
            return "Closed"

        if current_minutes < 4 * 60:  # Before 4:00 AM
            return "Closed"
        elif current_minutes < 9 * 60 + 30:  # 4:00 AM - 9:30 AM
            return "Pre-Market"
        elif current_minutes < 16 * 60:  # 9:30 AM - 4:00 PM
            return "Open"
        elif current_minutes < 20 * 60:  # 4:00 PM - 8:00 PM
            return "After Hours"
        else:
            return "Closed"
    except Exception:
        return "Closed"


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_market_indices() -> list[dict]:
    """Fetch SPY, QQQ, DIA, IWM, VIX prices + daily change (cached 5 min)."""
    import math
    try:
        import yfinance as yf
        symbols = ["SPY", "QQQ", "DIA", "IWM", "^VIX"]
        display_names = ["SPY", "QQQ", "DIA", "IWM", "VIX"]

        data = yf.download(" ".join(symbols), period="5d", interval="1d",
                           progress=False, threads=True)
        if data.empty:
            return []

        results = []
        for sym, name in zip(symbols, display_names):
            try:
                if len(symbols) == 1:
                    close_series = data["Close"].dropna()
                else:
                    close_series = data["Close"][sym].dropna()

                if close_series is not None and len(close_series) > 0:
                    current = float(close_series.iloc[-1])
                    prev = float(close_series.iloc[-2]) if len(close_series) > 1 else current

                    if math.isnan(current) or math.isnan(prev):
                        continue

                    change = current - prev
                    change_pct = (change / prev * 100) if prev else 0
                    results.append({
                        "symbol": name,
                        "price": current,
                        "change": change,
                        "change_pct": change_pct,
                    })
            except (KeyError, IndexError, TypeError, ValueError):
                continue

        return results
    except Exception:
        return []


def render_market_bar():
    """Render the top market indices bar."""
    indices = _fetch_market_indices()
    if not indices:
        return

    cols = st.columns(len(indices))
    for i, idx in enumerate(indices):
        with cols[i]:
            change_pct = idx["change_pct"]
            if change_pct >= 0:
                color = "#26A69A"
                arrow = "+"
            else:
                color = "#EF5350"
                arrow = ""
            st.markdown(
                f'<div style="text-align:center;">'
                f'<span style="color:#787B86;font-size:0.75rem;font-weight:600;">{idx["symbol"]}</span><br>'
                f'<span style="color:#D1D4DC;font-size:0.95rem;font-weight:700;">'
                f'${idx["price"]:,.2f}</span><br>'
                f'<span style="color:{color};font-size:0.8rem;font-weight:600;">'
                f'{arrow}{change_pct:.2f}%</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
