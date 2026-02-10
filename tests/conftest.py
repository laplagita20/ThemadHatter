"""Shared test fixtures for the Mad Hatter stock model test suite."""

import json
import pytest
from datetime import datetime, timedelta

import database.connection as _conn_mod
from database.connection import DatabaseConnection
from database.schema import initialize_database


@pytest.fixture
def test_db(tmp_path):
    """Create a fresh isolated test database with schema initialized."""
    db_path = tmp_path / "test.db"
    # Bypass the singleton to get a fresh DB per test
    db = DatabaseConnection(db_path)
    initialize_database(db)
    # Temporarily replace the global singleton so any code calling
    # get_connection() without arguments also uses the test DB
    old_db = _conn_mod._db
    _conn_mod._db = db
    yield db
    _conn_mod._db = old_db


@pytest.fixture
def stock_dao(test_db):
    from database.models import StockDAO
    return StockDAO(db=test_db)


@pytest.fixture
def price_dao(test_db):
    from database.models import PriceDAO
    return PriceDAO(db=test_db)


@pytest.fixture
def fundamentals_dao(test_db):
    from database.models import FundamentalsDAO
    return FundamentalsDAO(db=test_db)


@pytest.fixture
def analysis_result_dao(test_db):
    from database.models import AnalysisResultDAO
    return AnalysisResultDAO(db=test_db)


@pytest.fixture
def decision_dao(test_db):
    from database.models import DecisionDAO
    return DecisionDAO(db=test_db)


@pytest.fixture
def portfolio_dao(test_db):
    from database.models import PortfolioDAO
    return PortfolioDAO(db=test_db)


@pytest.fixture
def insider_trade_dao(test_db):
    from database.models import InsiderTradeDAO
    return InsiderTradeDAO(db=test_db)


@pytest.fixture
def computed_score_dao(test_db):
    from database.models import ComputedScoreDAO
    return ComputedScoreDAO(db=test_db)


@pytest.fixture
def recurring_investment_dao(test_db):
    from database.models import RecurringInvestmentDAO
    return RecurringInvestmentDAO(db=test_db)


@pytest.fixture
def sample_stock():
    return {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 3000000000000,
    }


@pytest.fixture
def sample_holdings():
    return [
        {
            "ticker": "AAPL",
            "quantity": 100,
            "average_cost": 150.0,
            "current_price": 175.0,
            "market_value": 17500.0,
            "unrealized_pl": 2500.0,
            "unrealized_pl_pct": 16.67,
            "sector": "Technology",
        },
        {
            "ticker": "MSFT",
            "quantity": 50,
            "average_cost": 300.0,
            "current_price": 350.0,
            "market_value": 17500.0,
            "unrealized_pl": 2500.0,
            "unrealized_pl_pct": 16.67,
            "sector": "Technology",
        },
        {
            "ticker": "JNJ",
            "quantity": 75,
            "average_cost": 160.0,
            "current_price": 155.0,
            "market_value": 11625.0,
            "unrealized_pl": -375.0,
            "unrealized_pl_pct": -3.125,
            "sector": "Healthcare",
        },
    ]


@pytest.fixture
def sample_insider_trades():
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    return [
        {
            "ticker": "AAPL",
            "filer_name": "John CEO",
            "filer_title": "Chief Executive Officer",
            "transaction_date": today,
            "transaction_type": "P",
            "shares": 10000,
            "price_per_share": 175.0,
            "total_value": 1750000,
            "shares_owned_after": 50000,
        },
        {
            "ticker": "AAPL",
            "filer_name": "Jane CFO",
            "filer_title": "Chief Financial Officer",
            "transaction_date": week_ago,
            "transaction_type": "P",
            "shares": 5000,
            "price_per_share": 172.0,
            "total_value": 860000,
            "shares_owned_after": 25000,
        },
        {
            "ticker": "AAPL",
            "filer_name": "Bob Director",
            "filer_title": "Director",
            "transaction_date": month_ago,
            "transaction_type": "S",
            "shares": 2000,
            "price_per_share": 170.0,
            "total_value": 340000,
            "shares_owned_after": 10000,
        },
    ]


@pytest.fixture
def sample_price_history():
    """Generate 60 days of synthetic price data."""
    import random
    random.seed(42)
    rows = []
    base_price = 170.0
    start = datetime.now() - timedelta(days=60)
    for i in range(60):
        date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        change = random.uniform(-3, 3)
        base_price += change
        rows.append({
            "date": date,
            "open": round(base_price - 1, 2),
            "high": round(base_price + 2, 2),
            "low": round(base_price - 2, 2),
            "close": round(base_price, 2),
            "volume": random.randint(50000000, 150000000),
            "adj_close": round(base_price, 2),
        })
    return rows


@pytest.fixture
def sample_fundamentals():
    return {
        "pe_ratio": 28.5,
        "forward_pe": 25.0,
        "pb_ratio": 45.0,
        "ps_ratio": 7.5,
        "ev_ebitda": 22.0,
        "peg_ratio": 1.8,
        "profit_margin": 0.26,
        "operating_margin": 0.30,
        "gross_margin": 0.44,
        "roe": 1.60,
        "roa": 0.28,
        "roic": 0.45,
        "revenue_growth": 0.08,
        "earnings_growth": 0.12,
        "debt_to_equity": 1.87,
        "current_ratio": 0.99,
        "quick_ratio": 0.94,
        "free_cash_flow": 100000000000,
        "dividend_yield": 0.005,
        "beta": 1.24,
        "market_cap": 3000000000000,
        "enterprise_value": 3100000000000,
        "raw": {},
    }
