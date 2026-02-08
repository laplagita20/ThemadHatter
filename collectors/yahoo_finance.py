"""Yahoo Finance collector: prices, fundamentals, financials."""

import logging
import json
import yfinance as yf
import pandas as pd

from collectors.base_collector import BaseCollector
from database.models import PriceDAO, FundamentalsDAO, StockDAO

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

        return {
            "ticker": ticker,
            "prices": prices,
            "info": info or {},
        }

    def store(self, data: dict):
        ticker = data["ticker"]
        prices = data.get("prices")
        info = data.get("info", {})

        # Store price history
        if prices is not None and not (isinstance(prices, pd.DataFrame) and prices.empty):
            if isinstance(prices, pd.DataFrame):
                rows = []
                for date, row in prices.iterrows():
                    rows.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "open": float(row.get("Open", 0)),
                        "high": float(row.get("High", 0)),
                        "low": float(row.get("Low", 0)),
                        "close": float(row.get("Close", 0)),
                        "volume": int(row.get("Volume", 0)),
                        "adj_close": float(row.get("Close", 0)),
                    })
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

            self.fund_dao.insert(ticker, {
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "ps_ratio": info.get("priceToSalesTrailing12Months"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "peg_ratio": info.get("pegRatio"),
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "gross_margin": info.get("grossMargins"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "roic": None,
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
                "free_cash_flow": info.get("freeCashflow"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "raw": info,
            })
            logger.info("Stored fundamentals for %s", ticker)
