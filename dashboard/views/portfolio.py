"""Portfolio Overview Dashboard Page."""

import csv
import io
import time
import streamlit as st
import yfinance as yf
import pandas as pd

from database.models import PortfolioDAO, StockDAO, RecurringInvestmentDAO
from database.connection import get_connection
from dashboard.components.charts import create_sector_pie_chart, create_performance_chart
from dashboard.components.tables import holdings_table, decisions_table
from dashboard.components.teach_me import teach_if_enabled

# Cache TTL for live prices (seconds)
PRICE_CACHE_TTL = 60  # Refresh prices every 60 seconds

# Broker CSV column mappings: (ticker_col, shares_col, cost_col)
# Values can be a list of possible column names (case-insensitive match)
BROKER_FORMATS = {
    "Robinhood": {
        "ticker": ["Instrument", "Symbol"],
        "shares": ["Quantity", "Shares"],
        "cost": ["Average Cost", "Avg Cost"],
        "help": "Export from Robinhood: Account > Statements & History > Export CSV",
    },
    "Fidelity": {
        "ticker": ["Symbol"],
        "shares": ["Quantity", "Shares"],
        "cost": ["Cost Basis Per Share", "Average Cost Basis"],
        "help": "Export from Fidelity: Positions > Download",
    },
    "Schwab": {
        "ticker": ["Symbol"],
        "shares": ["Quantity", "Shares"],
        "cost": ["Cost Basis", "Price Paid"],
        "help": "Export from Schwab: Accounts > Positions > Export",
    },
    "Webull": {
        "ticker": ["Ticker", "Symbol"],
        "shares": ["Qty", "Quantity", "Shares"],
        "cost": ["Avg Cost", "Average Cost"],
        "help": "Export from Webull: Portfolio > More > Export Positions",
    },
    "E*Trade": {
        "ticker": ["Symbol"],
        "shares": ["Quantity", "Qty"],
        "cost": ["Price Paid", "Cost Basis Per Share"],
        "help": "Export from E*Trade: Portfolio > Download Positions",
    },
    "Interactive Brokers": {
        "ticker": ["Symbol", "Financial Instrument"],
        "shares": ["Position", "Quantity"],
        "cost": ["Avg Cost", "Cost Basis Per Share", "Avg Price"],
        "help": "Export from IBKR: Portfolio > Export to CSV",
    },
    "TD Ameritrade": {
        "ticker": ["Symbol"],
        "shares": ["Quantity", "Qty", "Shares"],
        "cost": ["Average Price", "Cost/Share"],
        "help": "Export from TD Ameritrade: My Account > Positions > Export",
    },
}


def _get_live_prices(tickers: list[str]) -> dict:
    """Fetch live prices for multiple tickers using yfinance batch download.

    Uses session_state cache with TTL to avoid hammering the API on every rerun.
    Returns {ticker: {price, change, change_pct}}.
    """
    import math

    cache_key = "live_prices"
    cache_ts_key = "live_prices_ts"

    # Check if cache is still fresh
    now = time.time()
    if (cache_key in st.session_state
            and cache_ts_key in st.session_state
            and now - st.session_state[cache_ts_key] < PRICE_CACHE_TTL):
        return st.session_state[cache_key]

    prices = {}
    if not tickers:
        return prices

    try:
        # Batch download is much faster than individual yf.Ticker().info calls
        ticker_str = " ".join(tickers)
        data = yf.download(ticker_str, period="5d", interval="1d", progress=False, threads=True)

        if data.empty:
            return prices

        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    close_series = data["Close"].dropna()
                else:
                    close_series = data["Close"][ticker].dropna()

                if close_series is not None and len(close_series) > 0:
                    current = float(close_series.iloc[-1])
                    prev = float(close_series.iloc[-2]) if len(close_series) > 1 else current

                    # Skip if NaN
                    if math.isnan(current) or math.isnan(prev):
                        continue

                    change = current - prev
                    change_pct = (change / prev * 100) if prev else 0
                    prices[ticker] = {
                        "price": current,
                        "change": change,
                        "change_pct": change_pct,
                    }
            except (KeyError, IndexError, TypeError, ValueError):
                continue

        # For any tickers that failed batch, try individual fast info
        missing = [t for t in tickers if t not in prices]
        for ticker in missing[:5]:  # Cap individual lookups
            try:
                info = yf.Ticker(ticker).fast_info
                price = getattr(info, "last_price", None)
                prev = getattr(info, "previous_close", None)
                if price and not math.isnan(price):
                    change = (price - prev) if prev and not math.isnan(prev) else 0
                    change_pct = (change / prev * 100) if prev and not math.isnan(prev) else 0
                    prices[ticker] = {
                        "price": price,
                        "change": change,
                        "change_pct": change_pct,
                    }
            except Exception:
                continue

    except Exception:
        pass

    # Update cache
    st.session_state[cache_key] = prices
    st.session_state[cache_ts_key] = now
    return prices


def _apply_live_prices(holdings: list[dict], live_prices: dict) -> list[dict]:
    """Update holdings with live price data, recalculating P&L.

    Only overwrites snapshot prices with live prices when valid (non-NaN).
    """
    import math

    updated = []
    for h in holdings:
        h = dict(h)  # Make a mutable copy
        ticker = h["ticker"]
        if ticker in live_prices:
            lp = live_prices[ticker]
            new_price = lp["price"]

            # Only apply if price is a valid number
            if new_price and not math.isnan(new_price):
                qty = h.get("quantity", 0) or 0
                cost = h.get("average_cost", 0) or 0

                h["current_price"] = new_price
                h["market_value"] = qty * new_price
                h["unrealized_pl"] = (new_price - cost) * qty if cost else 0
                h["unrealized_pl_pct"] = ((new_price / cost) - 1) * 100 if cost else 0
                h["_daily_change"] = lp.get("change", 0)
                h["_daily_change_pct"] = lp.get("change_pct", 0)
        updated.append(h)
    return updated


def _merge_and_snapshot(portfolio_dao, new_holding: dict):
    """Load existing holdings, merge in the new one, and create a fresh snapshot."""
    existing = list(portfolio_dao.get_latest_holdings())
    merged = {h["ticker"]: dict(h) for h in existing}
    merged[new_holding["ticker"]] = new_holding
    portfolio_dao.snapshot_holdings(list(merged.values()))


def _fetch_and_build_holding(ticker: str, shares: float, cost_basis: float) -> dict:
    """Fetch live price data and build a holding dict."""
    stock = yf.Ticker(ticker)
    info = stock.info
    current_price = info.get("currentPrice") or info.get("regularMarketPrice") or cost_basis
    market_value = shares * current_price
    unrealized_pl = (current_price - cost_basis) * shares if cost_basis else 0
    unrealized_pl_pct = ((current_price / cost_basis) - 1) * 100 if cost_basis else 0
    return {
        "ticker": ticker,
        "quantity": shares,
        "average_cost": cost_basis,
        "current_price": current_price,
        "market_value": market_value,
        "unrealized_pl": unrealized_pl,
        "unrealized_pl_pct": unrealized_pl_pct,
        "sector": info.get("sector", ""),
        "_info": info,  # pass along for stock upsert
    }


def _find_column(header_row: list[str], possible_names: list[str]) -> int | None:
    """Find the index of a column by trying multiple possible names (case-insensitive)."""
    header_lower = [h.lower().strip() for h in header_row]
    for name in possible_names:
        if name.lower() in header_lower:
            return header_lower.index(name.lower())
    return None


def _parse_broker_csv(csv_text: str, broker: str) -> list[dict]:
    """Parse CSV text using broker-specific column mappings. Returns list of {ticker, shares, cost}."""
    fmt = BROKER_FORMATS.get(broker)
    if not fmt:
        return []

    rows = list(csv.reader(io.StringIO(csv_text.strip())))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if len(rows) < 2:
        return []

    # First row is header
    header = [h.strip() for h in rows[0]]
    ticker_idx = _find_column(header, fmt["ticker"])
    shares_idx = _find_column(header, fmt["shares"])
    cost_idx = _find_column(header, fmt["cost"])

    if ticker_idx is None or shares_idx is None:
        return []

    results = []
    for parts in rows[1:]:
        parts = [p.strip() for p in parts]
        if len(parts) <= max(filter(None, [ticker_idx, shares_idx, cost_idx]), default=0):
            continue
        try:
            ticker = parts[ticker_idx].upper().strip()
            # Skip non-stock rows (cash, totals, empty)
            if not ticker or ticker in ("CASH", "TOTAL", "PENDING", "--", "N/A"):
                continue
            # Remove exchange prefixes if present (e.g., "NASDAQ:AAPL")
            if ":" in ticker:
                ticker = ticker.split(":")[-1]

            shares = abs(float(parts[shares_idx].replace(",", "").replace("$", "")))
            cost = 0.0
            if cost_idx is not None and cost_idx < len(parts):
                cost_str = parts[cost_idx].replace(",", "").replace("$", "").strip()
                if cost_str and cost_str not in ("--", "N/A", ""):
                    cost = abs(float(cost_str))

            if shares > 0:
                results.append({"ticker": ticker, "shares": shares, "cost": cost})
        except (ValueError, IndexError):
            continue

    return results


def _render_recurring_investments(holdings):
    """Render the recurring investments management section."""
    st.subheader("Recurring Investments (DCA)")
    teach_if_enabled("recurring_investment")

    recurring_dao = RecurringInvestmentDAO()
    active_plans = list(recurring_dao.get_all_active())

    # Show existing plans
    if active_plans:
        plan_data = []
        for plan in active_plans:
            plan_data.append({
                "Ticker": plan["ticker"],
                "Amount": f"${plan['amount']:,.2f}",
                "Frequency": plan["frequency"].title(),
                "Day": str(plan.get("day_of_period", 1)),
                "Next Date": plan.get("next_investment_date", "N/A"),
                "Total Invested": f"${plan.get('total_invested', 0):,.2f}",
                "Shares Bought": f"{plan.get('total_shares_bought', 0):,.4f}",
                "Executions": str(plan.get("num_executions", 0)),
            })
        st.dataframe(pd.DataFrame(plan_data), width="stretch", hide_index=True)

        # Monthly DCA total
        def _monthly_multiplier(freq):
            if freq == "daily":
                return 21  # ~21 market days per month
            elif freq == "weekly":
                return 4
            elif freq == "biweekly":
                return 2
            return 1
        monthly_total = sum(p["amount"] * _monthly_multiplier(p["frequency"]) for p in active_plans)
        st.metric("Estimated Monthly DCA", f"${monthly_total:,.2f}")
    else:
        st.info("No recurring investments set up yet. Add one below to start dollar-cost averaging.")

    # Add new recurring investment
    with st.expander("Set Up Recurring Investment", expanded=not active_plans):
        tickers_available = [h["ticker"] for h in holdings] if holdings else []

        with st.form("recurring_form", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if tickers_available:
                    rec_ticker = st.selectbox(
                        "Stock", ["(New ticker)"] + tickers_available, key="rec_ticker"
                    )
                    if rec_ticker == "(New ticker)":
                        rec_ticker = st.text_input("Enter ticker", key="rec_new_ticker").upper().strip()
                else:
                    rec_ticker = st.text_input("Ticker Symbol", placeholder="AAPL", key="rec_ticker_input").upper().strip()
            with col2:
                rec_amount = st.number_input("Amount ($)", min_value=1.0, value=100.0, step=25.0, format="%.2f")
            with col3:
                rec_frequency = st.selectbox("Frequency", ["daily", "weekly", "biweekly", "monthly"])
            with col4:
                if rec_frequency == "daily":
                    rec_day = 0  # Not used for daily
                    st.caption("Invests every market day (Mon-Fri)")
                elif rec_frequency == "monthly":
                    rec_day = st.number_input("Day of Month", min_value=1, max_value=28, value=1)
                else:
                    rec_day = st.selectbox("Day of Week", list(range(7)),
                                           format_func=lambda x: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][x])

            if st.form_submit_button("Create DCA Plan", type="primary"):
                if rec_ticker:
                    try:
                        recurring_dao.create(rec_ticker, rec_amount, rec_frequency, rec_day)
                        st.success(f"Created {rec_frequency} ${rec_amount:.2f} plan for {rec_ticker}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create plan: {e}")
                else:
                    st.warning("Enter a ticker symbol")

    # Manage existing plans
    if active_plans:
        with st.expander("Manage DCA Plans"):
            for plan in active_plans:
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.text(f"{plan['ticker']} - ${plan['amount']:,.2f} {plan['frequency']}")
                with col2:
                    new_amt = st.number_input(
                        "New amount", min_value=0.0, value=float(plan['amount']),
                        step=25.0, key=f"edit_amt_{plan['id']}", label_visibility="collapsed"
                    )
                    if new_amt != plan['amount'] and st.button("Update", key=f"update_{plan['id']}"):
                        recurring_dao.update_amount(plan['id'], new_amt)
                        st.rerun()
                with col3:
                    if st.button("Cancel Plan", key=f"cancel_{plan['id']}"):
                        recurring_dao.deactivate(plan['id'])
                        st.success(f"Cancelled {plan['ticker']} DCA plan")
                        st.rerun()


def render():
    """Render the portfolio overview page."""
    st.header("Portfolio Overview")

    portfolio_dao = PortfolioDAO()
    stock_dao = StockDAO()
    db = get_connection()

    # --- Add Holdings Dropdown ---
    with st.expander("Add Holdings", expanded=False):
        teach_if_enabled("cost_basis", inline=True)

        import_method = st.selectbox(
            "How would you like to add holdings?",
            ["Manual Entry", "Import from Broker", "Paste CSV"],
            key="import_method",
        )

        if import_method == "Manual Entry":
            st.caption("Enter each position one at a time. Your data stays local.")
            with st.form("add_holding_form", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                with col1:
                    ticker_input = st.text_input("Ticker Symbol", placeholder="AAPL").upper().strip()
                with col2:
                    shares_input = st.number_input("Shares", min_value=0.0, step=0.01, format="%.4f")
                with col3:
                    cost_input = st.number_input("Cost Basis per Share ($)", min_value=0.0, step=0.01, format="%.2f")

                submitted = st.form_submit_button("Add Holding", type="primary")

                if submitted and ticker_input and shares_input > 0:
                    with st.spinner(f"Fetching {ticker_input} data..."):
                        try:
                            holding = _fetch_and_build_holding(ticker_input, shares_input, cost_input)
                            info = holding.pop("_info")
                            _merge_and_snapshot(portfolio_dao, holding)
                            stock_dao.upsert(
                                ticker=ticker_input,
                                company_name=info.get("longName", info.get("shortName", "")),
                                sector=info.get("sector", ""),
                                industry=info.get("industry", ""),
                                market_cap=info.get("marketCap"),
                            )
                            st.success(f"Added {shares_input:.2f} shares of {ticker_input} at ${cost_input:.2f}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to add holding: {e}")

        elif import_method == "Import from Broker":
            broker = st.selectbox(
                "Select your broker",
                list(BROKER_FORMATS.keys()),
                key="broker_select",
            )
            fmt = BROKER_FORMATS[broker]
            st.info(fmt["help"])
            st.caption(
                "Your CSV never leaves your machine. We only look up current prices via Yahoo Finance."
            )

            csv_input = st.text_area(
                f"Paste your {broker} CSV export here",
                placeholder="Paste the full CSV including the header row...",
                height=150,
                key="broker_csv_input",
            )

            if st.button("Import from Broker", type="primary", key="broker_import_btn"):
                if csv_input.strip():
                    parsed = _parse_broker_csv(csv_input, broker)
                    if not parsed:
                        st.error(
                            f"Could not parse CSV. Make sure you included the header row. "
                            f"Expected columns: {', '.join(fmt['ticker'] + fmt['shares'] + fmt['cost'])}"
                        )
                    else:
                        st.info(f"Found {len(parsed)} positions. Importing...")
                        progress = st.progress(0)
                        imported = 0
                        for i, row in enumerate(parsed):
                            try:
                                holding = _fetch_and_build_holding(row["ticker"], row["shares"], row["cost"])
                                info = holding.pop("_info")
                                _merge_and_snapshot(portfolio_dao, holding)
                                stock_dao.upsert(
                                    ticker=row["ticker"],
                                    company_name=info.get("longName", ""),
                                    sector=info.get("sector", ""),
                                    industry=info.get("industry", ""),
                                )
                                imported += 1
                            except Exception as e:
                                st.warning(f"Skipped {row['ticker']}: {e}")
                            progress.progress((i + 1) / len(parsed))
                        st.success(f"Imported {imported} of {len(parsed)} positions")
                        st.rerun()
                else:
                    st.warning("Paste your CSV data first")

        elif import_method == "Paste CSV":
            st.caption("Generic format: `ticker, shares, cost_basis` (one per line, no header needed)")
            csv_input = st.text_area(
                "Paste CSV data",
                placeholder="AAPL, 10, 150.00\nMSFT, 5, 300.00\nNVDA, 20, 120.50",
                height=100,
                key="generic_csv_input",
            )
            if st.button("Import Holdings", key="generic_import_btn"):
                if csv_input.strip():
                    lines = [l.strip() for l in csv_input.strip().split("\n") if l.strip()]
                    progress = st.progress(0)
                    imported = 0
                    for i, line in enumerate(lines):
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 3:
                            try:
                                t, s, c = parts[0].upper(), float(parts[1]), float(parts[2])
                                holding = _fetch_and_build_holding(t, s, c)
                                info = holding.pop("_info")
                                _merge_and_snapshot(portfolio_dao, holding)
                                stock_dao.upsert(
                                    ticker=t, company_name=info.get("longName", ""),
                                    sector=info.get("sector", ""), industry=info.get("industry", ""),
                                )
                                imported += 1
                            except Exception as e:
                                st.error(f"Failed for {parts[0]}: {e}")
                        progress.progress((i + 1) / len(lines))
                    st.success(f"Imported {imported} of {len(lines)} positions")
                    st.rerun()

    holdings = list(portfolio_dao.get_latest_holdings())

    if not holdings:
        st.info("No holdings yet. Use the form above to add your first position.")
        return

    # === LIVE PRICE REFRESH ===
    tickers = [h["ticker"] for h in holdings]
    with st.spinner("Refreshing live prices..."):
        live_prices = _get_live_prices(tickers)
    if live_prices:
        holdings = _apply_live_prices(holdings, live_prices)

    # Price freshness indicator
    from datetime import datetime
    price_ts = st.session_state.get("live_prices_ts")
    if price_ts:
        refresh_time = datetime.fromtimestamp(price_ts)
        time_ago = int(time.time() - price_ts)
        if time_ago < 60:
            freshness = f"Live  -  Updated {time_ago}s ago"
        elif time_ago < 3600:
            freshness = f"Updated {time_ago // 60}m ago"
        else:
            freshness = f"Updated at {refresh_time.strftime('%I:%M %p')}"
    else:
        freshness = "Prices from last snapshot"

    st.caption(f"{freshness}  |  Auto-refreshes every {PRICE_CACHE_TTL}s")

    # Key metrics (filter out NaN values to prevent poisoning totals)
    import math

    def _safe_val(v):
        """Return 0 for None, NaN, or non-numeric values."""
        if v is None:
            return 0
        try:
            f = float(v)
            return 0 if math.isnan(f) else f
        except (TypeError, ValueError):
            return 0

    total_value = sum(_safe_val(h["market_value"]) for h in holdings)
    total_pl = sum(_safe_val(h["unrealized_pl"]) for h in holdings)
    total_cost = sum(_safe_val(h.get("average_cost", 0)) * _safe_val(h.get("quantity", 0)) for h in holdings)
    daily_change = sum(_safe_val(h.get("_daily_change", 0)) * _safe_val(h.get("quantity", 0)) for h in holdings)
    num_positions = len(holdings)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Portfolio Value", f"${total_value:,.2f}",
                delta=f"${daily_change:+,.2f} today" if daily_change else None)
    col2.metric("Unrealized P&L", f"${total_pl:+,.2f}",
                delta=f"{(total_pl / max(total_cost, 1)) * 100:+.1f}%")
    col3.metric("Positions", str(num_positions))

    sectors = set(h["sector"] for h in holdings if h.get("sector"))
    col4.metric("Sectors", str(len(sectors)))

    teach_if_enabled("portfolio_value", inline=True)
    teach_if_enabled("unrealized_pl")

    st.divider()

    # Two-column layout
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Holdings vs Model Ratings")

        # Merge holdings with latest model recommendations
        latest_decisions = {}
        for t in tickers:
            d = db.execute_one(
                "SELECT action, composite_score FROM decisions WHERE ticker = ? ORDER BY decided_at DESC LIMIT 1",
                (t,),
            )
            if d:
                latest_decisions[t] = d

        enriched = []
        for h in holdings:
            row = {
                "Ticker": h["ticker"],
                "Qty": f"{h['quantity']:.2f}",
                "Price": f"${h['current_price']:.2f}" if h.get("current_price") else "N/A",
                "Value": f"${_safe_val(h['market_value']):,.2f}",
                "P&L %": f"{_safe_val(h.get('unrealized_pl_pct', 0)):+.1f}%",
            }
            dec = latest_decisions.get(h["ticker"])
            if dec:
                row["Rating"] = dec["action"]
                row["Score"] = f"{dec['composite_score']:+.1f}"
            else:
                row["Rating"] = "N/A"
                row["Score"] = "-"
            enriched.append(row)

        st.dataframe(pd.DataFrame(enriched), width="stretch", hide_index=True)

        # Delete holding controls
        tickers_in_portfolio = [h["ticker"] for h in holdings]
        remove_ticker = st.selectbox("Remove a holding", [""] + tickers_in_portfolio, key="remove_holding")
        if remove_ticker and st.button("Remove", key="remove_btn"):
            portfolio_dao.delete_holding(remove_ticker)
            st.success(f"Removed {remove_ticker}")
            st.rerun()

    with right:
        sector_weights = {}
        for h in holdings:
            sector = h.get("sector") or "Unknown"
            sector_weights[sector] = sector_weights.get(sector, 0) + _safe_val(h["market_value"])

        if sector_weights and total_value > 0:
            sector_pcts = {k: v / total_value * 100 for k, v in sector_weights.items()}
            fig = create_sector_pie_chart(sector_pcts)
            st.plotly_chart(fig, width="stretch")
            teach_if_enabled("sector_allocation")

    st.divider()

    # === TAX-LOSS HARVESTING ALERTS ===
    harvest_candidates = [
        h for h in holdings
        if _safe_val(h.get("unrealized_pl_pct", 0)) < -5
    ]
    if harvest_candidates:
        with st.expander(f"Tax-Loss Harvesting Candidates ({len(harvest_candidates)})"):
            st.caption("Holdings with >5% unrealized loss that may qualify for tax-loss harvesting.")
            harvest_data = [{
                "Ticker": h["ticker"],
                "Loss": f"${_safe_val(h['unrealized_pl']):+,.2f}",
                "Loss %": f"{_safe_val(h.get('unrealized_pl_pct', 0)):+.1f}%",
                "Cost Basis": f"${_safe_val(h.get('average_cost', 0)):,.2f}",
                "Current": f"${_safe_val(h.get('current_price', 0)):,.2f}",
            } for h in harvest_candidates]
            st.dataframe(pd.DataFrame(harvest_data), width="stretch", hide_index=True)

    # === EARNINGS CALENDAR ===
    with st.expander("Upcoming Earnings"):
        earnings_data = []
        for t in tickers[:20]:  # Cap to avoid slow API calls
            try:
                stock_yf = yf.Ticker(t)
                cal = stock_yf.calendar
                if cal is not None:
                    if isinstance(cal, dict):
                        ed = cal.get("Earnings Date")
                        if ed:
                            # Can be a list of dates
                            date_str = str(ed[0])[:10] if isinstance(ed, list) else str(ed)[:10]
                            earnings_data.append({"Ticker": t, "Earnings Date": date_str})
                    elif isinstance(cal, pd.DataFrame) and not cal.empty:
                        if "Earnings Date" in cal.columns:
                            date_str = str(cal["Earnings Date"].iloc[0])[:10]
                            earnings_data.append({"Ticker": t, "Earnings Date": date_str})
            except Exception:
                continue
        if earnings_data:
            st.dataframe(pd.DataFrame(earnings_data), width="stretch", hide_index=True)
        else:
            st.info("No upcoming earnings dates found for holdings.")

    st.divider()

    # --- Recurring Investments Section ---
    _render_recurring_investments(holdings)

    st.divider()

    # Performance chart
    st.subheader("Portfolio Performance")
    snapshots = list(db.execute(
        """SELECT snapshot_date, total_equity FROM portfolio_snapshots
           WHERE total_equity IS NOT NULL
           ORDER BY snapshot_date ASC LIMIT 365"""
    ))

    if len(snapshots) >= 2:
        dates = [s["snapshot_date"][:10] for s in snapshots]
        values = [s["total_equity"] for s in snapshots]
        fig = create_performance_chart(dates, values)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Insufficient snapshot data for performance chart. Data accumulates over time.")

    # Recent decisions
    st.divider()
    st.subheader("Recent Decisions")
    recent = list(db.execute(
        """SELECT ticker, action, composite_score, confidence,
                  position_size_pct, decided_at
           FROM decisions ORDER BY decided_at DESC LIMIT 10"""
    ))
    decisions_table(recent)
