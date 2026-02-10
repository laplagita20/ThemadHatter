"""Tests for broker CSV parsing logic."""

import pytest
from dashboard.views.portfolio import _parse_broker_csv, _find_column


class TestFindColumn:
    def test_exact_match(self):
        assert _find_column(["Symbol", "Quantity", "Price"], ["Symbol"]) == 0

    def test_case_insensitive(self):
        assert _find_column(["SYMBOL", "quantity", "Price"], ["symbol"]) == 0

    def test_multiple_candidates(self):
        assert _find_column(["Ticker", "Qty", "Cost"], ["Symbol", "Ticker"]) == 0

    def test_not_found(self):
        assert _find_column(["A", "B", "C"], ["Z"]) is None


class TestParseBrokerCSV:
    def test_robinhood_format(self):
        csv = "Instrument,Quantity,Average Cost\nAAPL,10,150.00\nMSFT,5,300.00"
        result = _parse_broker_csv(csv, "Robinhood")
        assert len(result) == 2
        assert result[0] == {"ticker": "AAPL", "shares": 10.0, "cost": 150.0}
        assert result[1] == {"ticker": "MSFT", "shares": 5.0, "cost": 300.0}

    def test_fidelity_format(self):
        csv = "Symbol,Quantity,Cost Basis Per Share\nNVDA,20,120.50\nGOOG,3,140.00"
        result = _parse_broker_csv(csv, "Fidelity")
        assert len(result) == 2
        assert result[0]["ticker"] == "NVDA"
        assert result[0]["shares"] == 20.0

    def test_schwab_format(self):
        csv = "Symbol,Quantity,Cost Basis\nTSLA,15,$200.00\nAMD,50,$110.50"
        result = _parse_broker_csv(csv, "Schwab")
        assert len(result) == 2
        assert result[0]["ticker"] == "TSLA"
        assert result[0]["cost"] == 200.0  # Dollar sign stripped

    def test_webull_format(self):
        csv = "Ticker,Qty,Avg Cost\nSPY,100,450.00\nQQQ,50,380.00"
        result = _parse_broker_csv(csv, "Webull")
        assert len(result) == 2

    def test_skips_cash_rows(self):
        csv = "Symbol,Quantity,Average Cost\nAAPL,10,150.00\nCASH,0,0\nTOTAL,0,0"
        result = _parse_broker_csv(csv, "Robinhood")
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"

    def test_skips_empty_tickers(self):
        csv = "Symbol,Quantity,Average Cost\nAAPL,10,150.00\n,,\n,0,0"
        result = _parse_broker_csv(csv, "Robinhood")
        assert len(result) == 1

    def test_strips_exchange_prefix(self):
        csv = "Symbol,Quantity,Average Cost\nNASDAQ:AAPL,10,150.00"
        result = _parse_broker_csv(csv, "Robinhood")
        assert result[0]["ticker"] == "AAPL"

    def test_handles_dollar_signs_and_commas(self):
        csv = 'Symbol,Quantity,Cost Basis\nAAPL,"1,000","$150.50"'
        result = _parse_broker_csv(csv, "Schwab")
        assert len(result) == 1
        assert result[0]["shares"] == 1000.0
        assert result[0]["cost"] == 150.5

    def test_missing_cost_column_defaults_to_zero(self):
        csv = "Symbol,Quantity\nAAPL,10\nMSFT,5"
        result = _parse_broker_csv(csv, "Fidelity")
        assert len(result) == 2
        assert result[0]["cost"] == 0.0

    def test_unknown_broker_returns_empty(self):
        result = _parse_broker_csv("Symbol,Qty\nAAPL,10", "UnknownBroker")
        assert result == []

    def test_no_data_rows_returns_empty(self):
        csv = "Symbol,Quantity,Average Cost"
        result = _parse_broker_csv(csv, "Robinhood")
        assert result == []

    def test_empty_input(self):
        result = _parse_broker_csv("", "Robinhood")
        assert result == []

    def test_quoted_fields(self):
        csv = '"Symbol","Quantity","Average Cost"\n"AAPL","10","150.00"'
        result = _parse_broker_csv(csv, "Robinhood")
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
