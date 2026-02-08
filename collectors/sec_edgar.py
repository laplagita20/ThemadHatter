"""SEC EDGAR collector: filings, XBRL financial data, insider trades, 13-F holdings."""

import logging
import json
import requests
from datetime import datetime

from collectors.base_collector import BaseCollector
from database.connection import get_connection

logger = logging.getLogger("stock_model.collectors.sec_edgar")

BASE_URL = "https://data.sec.gov"
EFTS_URL = "https://efts.sec.gov/LATEST"


class SECEdgarCollector(BaseCollector):
    """Collects SEC filings, XBRL data, insider trades from EDGAR."""

    name = "sec_edgar"
    rate_limit = 10.0
    rate_period = 1.0

    def __init__(self):
        super().__init__()
        ua = self.settings.sec_edgar_user_agent
        self.headers = {
            "User-Agent": ua if ua else "StockModel research@example.com",
            "Accept-Encoding": "gzip, deflate",
        }
        self.db = get_connection()
        self._cik_cache = {}

    def _get(self, url: str) -> dict | None:
        """Rate-limited GET request to SEC EDGAR."""
        def do_request():
            resp = requests.get(url, headers=self.headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        return self._rate_limited_call(do_request)

    def _lookup_cik(self, ticker: str) -> str | None:
        """Look up CIK number for a ticker."""
        if ticker in self._cik_cache:
            return self._cik_cache[ticker]

        data = self._cached_call(
            "company_tickers",
            lambda: self._get(f"{BASE_URL}/files/company_tickers.json"),
            ttl=86400,
        )
        if not data:
            return None

        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                self._cik_cache[ticker] = cik
                return cik
        return None

    def collect(self, ticker: str = None) -> dict:
        if not ticker:
            return {}

        logger.info("Collecting SEC EDGAR data for %s", ticker)
        cik = self._lookup_cik(ticker)
        if not cik:
            logger.warning("Could not find CIK for %s", ticker)
            return {"ticker": ticker, "cik": None}

        result = {"ticker": ticker, "cik": cik}

        # Company submissions (filings list)
        submissions = self._cached_call(
            f"submissions_{cik}",
            lambda: self._get(f"{BASE_URL}/submissions/CIK{cik}.json"),
            ttl=21600,
        )
        if submissions:
            result["filings"] = self._parse_filings(submissions, ticker)

        # Company facts (XBRL financial data)
        facts = self._cached_call(
            f"companyfacts_{cik}",
            lambda: self._get(f"{BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json"),
            ttl=86400,
        )
        if facts:
            result["financial_data"] = self._parse_xbrl_facts(facts, ticker)

        return result

    def _parse_filings(self, submissions: dict, ticker: str) -> list[dict]:
        """Parse filing metadata from submissions JSON."""
        filings = []
        recent = submissions.get("filings", {}).get("recent", {})
        if not recent:
            return filings

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        descs = recent.get("primaryDocDescription", [])

        target_types = {"10-K", "10-Q", "8-K", "4", "13F-HR"}

        for i in range(min(len(forms), 100)):
            form = forms[i] if i < len(forms) else ""
            if form not in target_types:
                continue
            filings.append({
                "ticker": ticker,
                "filing_type": form,
                "filed_date": dates[i] if i < len(dates) else None,
                "accession_number": accessions[i] if i < len(accessions) else None,
                "primary_document": docs[i] if i < len(docs) else None,
                "description": descs[i] if i < len(descs) else None,
            })

        return filings

    def _parse_xbrl_facts(self, facts: dict, ticker: str) -> list[dict]:
        """Parse XBRL company facts into financial data rows."""
        data_rows = []
        us_gaap = facts.get("facts", {}).get("us-gaap", {})

        key_metrics = {
            "Revenues": "revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
            "NetIncomeLoss": "net_income",
            "GrossProfit": "gross_profit",
            "OperatingIncomeLoss": "operating_income",
            "Assets": "total_assets",
            "Liabilities": "total_liabilities",
            "StockholdersEquity": "stockholders_equity",
            "EarningsPerShareBasic": "eps_basic",
            "EarningsPerShareDiluted": "eps_diluted",
            "OperatingCashFlow": "operating_cash_flow",
            "NetCashProvidedByOperatingActivities": "operating_cash_flow",
            "LongTermDebt": "long_term_debt",
            "CommonStockSharesOutstanding": "shares_outstanding",
        }

        for xbrl_tag, metric_name in key_metrics.items():
            concept = us_gaap.get(xbrl_tag, {})
            units = concept.get("units", {})
            # Try USD first, then shares, then pure
            values = units.get("USD", units.get("shares", units.get("pure", [])))

            for entry in values[-20:]:  # last 20 entries
                period_end = entry.get("end")
                if not period_end:
                    continue

                fp = entry.get("fp", "")
                fy = entry.get("fy")
                filed = entry.get("filed")

                data_rows.append({
                    "ticker": ticker,
                    "metric": metric_name,
                    "period_end": period_end,
                    "period_type": fp,
                    "value": entry.get("val"),
                    "unit": "USD" if "USD" in units else "shares" if "shares" in units else "pure",
                    "fiscal_year": fy,
                    "fiscal_quarter": self._fp_to_quarter(fp),
                    "filed_date": filed,
                })

        return data_rows

    def _fp_to_quarter(self, fp: str) -> int | None:
        mapping = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}
        return mapping.get(fp)

    def store(self, data: dict):
        ticker = data.get("ticker")
        cik = data.get("cik")

        if cik:
            # Update CIK in stocks table
            self.db.execute(
                "UPDATE stocks SET cik = ? WHERE ticker = ?", (cik, ticker)
            )

        # Store filings
        filings = data.get("filings", [])
        for f in filings:
            try:
                self.db.execute_insert(
                    """INSERT OR IGNORE INTO sec_filings
                       (ticker, cik, filing_type, filed_date, accession_number,
                        primary_document, description)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (ticker, cik, f["filing_type"], f["filed_date"],
                     f["accession_number"], f["primary_document"], f["description"]),
                )
            except Exception as e:
                logger.debug("Filing insert skipped: %s", e)

        # Store XBRL financial data
        financial_data = data.get("financial_data", [])
        for row in financial_data:
            try:
                self.db.execute_insert(
                    """INSERT OR REPLACE INTO sec_financial_data
                       (ticker, metric, period_end, period_type, value, unit,
                        fiscal_year, fiscal_quarter, filed_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["ticker"], row["metric"], row["period_end"],
                     row["period_type"], row["value"], row["unit"],
                     row["fiscal_year"], row["fiscal_quarter"], row["filed_date"]),
                )
            except Exception as e:
                logger.debug("Financial data insert skipped: %s", e)

        if filings:
            logger.info("Stored %d filings for %s", len(filings), ticker)
        if financial_data:
            logger.info("Stored %d financial data points for %s", len(financial_data), ticker)
