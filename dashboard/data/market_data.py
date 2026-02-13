"""Centralized market data helpers for the dashboard.

All functions are cached with appropriate TTLs to avoid redundant API calls.
These are reused across Today, Markets, and other pages.
"""

from datetime import datetime, timezone, timedelta
import streamlit as st


@st.cache_data(ttl=300, show_spinner=False)
def get_market_indices() -> dict:
    """Fetch SPY/QQQ/DIA/IWM/VIX prices + changes (cached 5 min).

    Returns dict keyed by symbol: {price, change, change_pct, prev_close}.
    """
    import math
    try:
        import yfinance as yf
        symbols = ["SPY", "QQQ", "DIA", "IWM", "^VIX"]
        display_names = ["SPY", "QQQ", "DIA", "IWM", "VIX"]

        data = yf.download(" ".join(symbols), period="5d", interval="1d",
                           progress=False, threads=True)
        if data.empty:
            return {}

        results = {}
        for sym, name in zip(symbols, display_names):
            try:
                close_series = data["Close"][sym].dropna() if len(symbols) > 1 else data["Close"].dropna()
                if close_series is not None and len(close_series) > 0:
                    current = float(close_series.iloc[-1])
                    prev = float(close_series.iloc[-2]) if len(close_series) > 1 else current
                    if math.isnan(current) or math.isnan(prev):
                        continue
                    results[name] = {
                        "price": current,
                        "change": current - prev,
                        "change_pct": ((current - prev) / prev * 100) if prev else 0,
                        "prev_close": prev,
                    }
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return results
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def get_fear_greed() -> dict:
    """Fetch CNN Fear & Greed Index (cached 1 hour).

    Returns {value: int, description: str} or empty dict.
    """
    try:
        import fear_and_greed
        data = fear_and_greed.get()
        return {
            "value": int(data.value),
            "description": data.description,
        }
    except Exception:
        return {}


def get_market_status() -> str:
    """Determine current US market status based on Eastern Time."""
    try:
        now_utc = datetime.now(timezone.utc)
        month = now_utc.month
        is_dst = 3 <= month <= 10
        et_offset = timedelta(hours=-4 if is_dst else -5)
        now_et = now_utc + et_offset

        weekday = now_et.weekday()
        current_minutes = now_et.hour * 60 + now_et.minute

        if weekday >= 5:
            return "Closed"
        if current_minutes < 4 * 60:
            return "Closed"
        elif current_minutes < 9 * 60 + 30:
            return "Pre-Market"
        elif current_minutes < 16 * 60:
            return "Open"
        elif current_minutes < 20 * 60:
            return "After Hours"
        else:
            return "Closed"
    except Exception:
        return "Closed"


@st.cache_data(ttl=43200, show_spinner=False)
def get_earnings_today() -> list[dict]:
    """Fetch today's earnings calendar from Finnhub (cached 12h).

    Returns list of {symbol, hour, epsEstimate, revenueEstimate}.
    """
    try:
        from config.settings import get_settings
        settings = get_settings()
        api_key = settings.finnhub_api_key
        if not api_key:
            return []

        import finnhub
        client = finnhub.Client(api_key=api_key)
        today = datetime.now().strftime("%Y-%m-%d")
        data = client.earnings_calendar(_from=today, to=today, symbol="")

        results = []
        for item in (data.get("earningsCalendar") or []):
            results.append({
                "symbol": item.get("symbol", ""),
                "hour": item.get("hour", ""),
                "eps_estimate": item.get("epsEstimate"),
                "revenue_estimate": item.get("revenueEstimate"),
            })
        return results[:30]
    except Exception:
        return []


@st.cache_data(ttl=43200, show_spinner=False)
def get_economic_events_today() -> list[dict]:
    """Fetch today's economic events from Finnhub (cached 12h).

    Returns list of {event, time, actual, estimate, prev, impact}.
    """
    try:
        from config.settings import get_settings
        settings = get_settings()
        api_key = settings.finnhub_api_key
        if not api_key:
            return []

        import finnhub
        client = finnhub.Client(api_key=api_key)
        today = datetime.now().strftime("%Y-%m-%d")
        data = client.economic_calendar(_from=today, to=today)

        results = []
        for item in (data.get("economicCalendar") or []):
            results.append({
                "event": item.get("event", ""),
                "time": item.get("time", ""),
                "actual": item.get("actual"),
                "estimate": item.get("estimate"),
                "prev": item.get("prev"),
                "impact": item.get("impact", ""),
            })
        return results[:20]
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def get_overnight_news(tickers: tuple = ()) -> list[dict]:
    """Fetch news articles from last 12h (cached 30 min)."""
    try:
        from database.connection import get_connection
        db = get_connection()
        articles = list(db.execute(
            """SELECT * FROM news_articles
               WHERE fetched_at >= datetime('now', '-12 hours')
               ORDER BY published_at DESC LIMIT 30"""
        ))
        return articles
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def get_all_latest_decisions() -> list[dict]:
    """Get the latest decision for every ticker in the database (cached 10 min)."""
    try:
        from database.connection import get_connection
        db = get_connection()
        return list(db.execute(
            """SELECT d.* FROM decisions d
               INNER JOIN (
                   SELECT ticker, MAX(decided_at) as max_dt
                   FROM decisions GROUP BY ticker
               ) latest ON d.ticker = latest.ticker AND d.decided_at = latest.max_dt
               ORDER BY d.composite_score DESC"""
        ))
    except Exception:
        return []


# --- Fed Economic Data Helpers ---

# Key indicators to display with human-readable names
_FED_INDICATORS = {
    "ICSA": {"name": "Initial Jobless Claims", "unit": "K", "divisor": 1000, "change_type": "wow", "format": ",.0f"},
    "CPIAUCSL": {"name": "Inflation Rate (CPI)", "unit": "%", "divisor": 1, "change_type": "yoy", "format": ".1f"},
    "UNRATE": {"name": "Unemployment Rate", "unit": "%", "divisor": 1, "change_type": "mom", "format": ".1f"},
    "FEDFUNDS": {"name": "Fed Funds Rate", "unit": "%", "divisor": 1, "change_type": "mom", "format": ".2f"},
    "UMCSENT": {"name": "Consumer Sentiment", "unit": "", "divisor": 1, "change_type": "mom", "format": ".1f"},
    "GDP": {"name": "GDP Growth", "unit": "%", "divisor": 1, "change_type": "qoq", "format": ".1f"},
}


@st.cache_data(ttl=3600, show_spinner=False)
def get_key_economic_indicators() -> dict:
    """Fetch latest values for key Fed economic indicators (cached 1 hour).

    Returns dict keyed by series_id: {name, value, prev_value, change,
    change_pct, sparkline (last 12 data points), unit}.
    """
    from database.models import MacroDAO
    macro_dao = MacroDAO()
    results = {}

    for series_id, meta in _FED_INDICATORS.items():
        try:
            data = list(macro_dao.get_series(series_id, limit=24))
            if not data:
                continue

            # Data comes DESC, so [0] is latest
            latest_val = data[0]["value"]
            prev_val = data[1]["value"] if len(data) > 1 else latest_val

            # For CPI, calculate YoY % change
            if series_id == "CPIAUCSL" and len(data) >= 13:
                yoy_pct = ((data[0]["value"] - data[12]["value"]) / data[12]["value"]) * 100
                display_val = yoy_pct
                prev_yoy = ((data[1]["value"] - data[13]["value"]) / data[13]["value"]) * 100 if len(data) >= 14 else yoy_pct
                change = display_val - prev_yoy
            elif series_id == "GDP" and len(data) >= 2:
                # GDP: QoQ annualized change
                qoq = ((data[0]["value"] - data[1]["value"]) / data[1]["value"]) * 100 * 4
                display_val = qoq
                prev_qoq = ((data[1]["value"] - data[2]["value"]) / data[2]["value"]) * 100 * 4 if len(data) >= 3 else qoq
                change = display_val - prev_qoq
            elif series_id == "ICSA":
                display_val = latest_val / meta["divisor"]
                change = (latest_val - prev_val) / meta["divisor"]
            else:
                display_val = latest_val / meta["divisor"]
                change = (latest_val - prev_val) / meta["divisor"]

            # Sparkline data (chronological order, last 12 points)
            sparkline = [d["value"] for d in reversed(data[:12])]

            results[series_id] = {
                "name": meta["name"],
                "value": display_val,
                "raw_value": latest_val,
                "prev_value": prev_val,
                "change": change,
                "sparkline": sparkline,
                "unit": meta["unit"],
                "format": meta["format"],
                "date": data[0].get("date", ""),
            }
        except Exception:
            continue

    return results
