"""Yahoo Finance collector: prices, fundamentals, financials."""

import logging
import math
import json
import yfinance as yf
import pandas as pd

from collectors.base_collector import BaseCollector
from database.models import PriceDAO, FundamentalsDAO, StockDAO, InsiderTradeDAO
from utils.validators import validate_price

logger = logging.getLogger("stock_model.collectors.yahoo")


class YahooFinanceCollector(BaseCollector):
    """Collects price history and fundamental data from Yahoo Finance."""

    name = "yahoo_finance"
    rate_limit = 2.0
    rate_period = 1.0

    def __init__(self):
        super().__init__()
        self.price_dao = PriceDAO()
        self.fund_dao = FundamentalsDAO()
        self.stock_dao = StockDAO()
        self.insider_dao = InsiderTradeDAO()

    def collect(self, ticker: str = None) -> dict:
        if not ticker:
            return {}

        logger.info("Collecting Yahoo Finance data for %s", ticker)
        stock = yf.Ticker(ticker)

        # Price history (1 year, cached 15 min)
        prices = self._cached_call(
            f"prices_{ticker}",
            lambda: stock.history(period="1y"),
            ttl=900,
        )

        # Fundamentals (cached 24 hr)
        info = self._cached_call(
            f"info_{ticker}",
            lambda: stock.info,
            ttl=86400,
        )

        # Insider transactions (cached 24 hr)
        insider_transactions = self._cached_call(
            f"insider_{ticker}",
            lambda: stock.insider_transactions,
            ttl=86400,
        )

        return {
            "ticker": ticker,
            "prices": prices,
            "info": info or {},
            "insider_transactions": insider_transactions,
        }

    def store(self, data: dict):
        ticker = data["ticker"]
        prices = data.get("prices")
        info = data.get("info", {})

        # Store price history
        if prices is not None and not (isinstance(prices, pd.DataFrame) and prices.empty):
            if isinstance(prices, pd.DataFrame):
                rows = []
                skipped = 0
                for date, row in prices.iterrows():
                    close_v = validate_price(row.get("Close", 0))
                    if close_v is None:
                        skipped += 1
                        continue
                    rows.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "open": validate_price(row.get("Open", 0)) or 0,
                        "high": validate_price(row.get("High", 0)) or 0,
                        "low": validate_price(row.get("Low", 0)) or 0,
                        "close": close_v,
                        "volume": int(row.get("Volume", 0)) if not pd.isna(row.get("Volume", 0)) else 0,
                        "adj_close": close_v,
                    })
                if skipped:
                    logger.warning("Skipped %d invalid price rows for %s", skipped, ticker)
                if rows:
                    self.price_dao.upsert_many(ticker, rows)
                    logger.info("Stored %d price records for %s", len(rows), ticker)

        # Store fundamentals
        if info:
            self.stock_dao.upsert(
                ticker=ticker,
                company_name=info.get("longName", info.get("shortName", "")),
                sector=info.get("sector", ""),
                industry=info.get("industry", ""),
                market_cap=info.get("marketCap"),
            )

            def _finite(v):
                """Return v if finite, else None."""
                if v is None:
                    return None
                try:
                    f = float(v)
                    return f if math.isfinite(f) else None
                except (TypeError, ValueError):
                    return None

            self.fund_dao.insert(ticker, {
                "pe_ratio": _finite(info.get("trailingPE")),
                "forward_pe": _finite(info.get("forwardPE")),
                "pb_ratio": _finite(info.get("priceToBook")),
                "ps_ratio": _finite(info.get("priceToSalesTrailing12Months")),
                "ev_ebitda": _finite(info.get("enterpriseToEbitda")),
                "peg_ratio": _finite(info.get("pegRatio")),
                "profit_margin": _finite(info.get("profitMargins")),
                "operating_margin": _finite(info.get("operatingMargins")),
                "gross_margin": _finite(info.get("grossMargins")),
                "roe": _finite(info.get("returnOnEquity")),
                "roa": _finite(info.get("returnOnAssets")),
                "roic": None,
                "revenue_growth": _finite(info.get("revenueGrowth")),
                "earnings_growth": _finite(info.get("earningsGrowth")),
                "debt_to_equity": _finite(info.get("debtToEquity")),
                "current_ratio": _finite(info.get("currentRatio")),
                "quick_ratio": _finite(info.get("quickRatio")),
                "free_cash_flow": _finite(info.get("freeCashflow")),
                "dividend_yield": _finite(info.get("dividendYield")),
                "beta": _finite(info.get("beta")),
                "market_cap": _finite(info.get("marketCap")),
                "enterprise_value": _finite(info.get("enterpriseValue")),
                "raw": info,
            })
            logger.info("Stored fundamentals for %s", ticker)

        # Store insider transactions
        insider_tx = data.get("insider_transactions")
        if insider_tx is not None and isinstance(insider_tx, pd.DataFrame) and not insider_tx.empty:
            count = 0
            for _, row in insider_tx.iterrows():
                shares = row.get("Shares", 0)
                value = row.get("Value", 0)
                # Handle NaN values
                if pd.isna(shares):
                    shares = 0
                if pd.isna(value):
                    value = 0

                # yfinance puts tx type in Text field (e.g., "Sale at price 271.23 per share.")
                tx_text = str(row.get("Text", "")).strip()
                tx_field = str(row.get("Transaction", "")).strip()
                combined = f"{tx_text} {tx_field}".lower()

                if "sale" in combined or "sell" in combined:
                    tx_type = "S"
                elif "purchase" in combined or "buy" in combined:
                    tx_type = "P"
                elif "gift" in combined:
                    tx_type = "A-AWARD"
                elif "conversion" in combined or "exercise" in combined:
                    tx_type = "M"  # Exercise/conversion
                elif not combined.strip() and shares > 0 and (not value or value == 0):
                    # Empty text with positive shares and no value = stock award/RSU vesting
                    tx_type = "A-AWARD"
                else:
                    tx_type = combined[:20] if combined.strip() else "A-AWARD"

                # Parse date
                start_date = row.get("Start Date")
                if hasattr(start_date, "strftime"):
                    tx_date = start_date.strftime("%Y-%m-%d")
                elif start_date is not None and not pd.isna(start_date):
                    tx_date = str(start_date)[:10]
                else:
                    tx_date = None

                price_per_share = abs(value / shares) if shares and shares != 0 else None

                self.insider_dao.insert({
                    "ticker": ticker,
                    "filer_name": str(row.get("Insider", "Unknown")),
                    "filer_title": str(row.get("Position", "")) if not pd.isna(row.get("Position", "")) else "",
                    "transaction_date": tx_date,
                    "transaction_type": tx_type,
                    "shares": abs(float(shares)) if shares else 0,
                    "price_per_share": price_per_share,
                    "total_value": abs(float(value)) if value else 0,
                    "shares_owned_after": None,
                })
                count += 1
            logger.info("Stored %d insider transactions for %s", count, ticker)
