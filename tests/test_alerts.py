"""Tests for rule-based smart alerts."""

import pytest
from analysis.alerts import get_smart_alerts


@pytest.fixture
def user_with_prefs(test_db):
    """Create a test user with preferences."""
    from database.models import UserDAO, UserPreferencesDAO
    user_dao = UserDAO(db=test_db)
    uid = user_dao.create("alertuser", "password123")
    prefs_dao = UserPreferencesDAO(db=test_db)
    prefs_dao.update(uid, onboarding_completed=1)
    return uid


@pytest.fixture
def user_with_portfolio(user_with_prefs, test_db, sample_holdings):
    """Create a test user with portfolio holdings."""
    from database.models import PortfolioDAO
    portfolio_dao = PortfolioDAO(db=test_db)
    portfolio_dao.snapshot_holdings(sample_holdings, user_with_prefs)
    return user_with_prefs


class TestSmartAlerts:
    def test_empty_portfolio(self, user_with_prefs):
        alerts = get_smart_alerts(user_with_prefs)
        assert alerts == []

    def test_tax_loss_harvest(self, user_with_portfolio, test_db):
        from database.models import PortfolioDAO
        portfolio_dao = PortfolioDAO(db=test_db)
        holdings = [
            {"ticker": "LOSS", "quantity": 50, "average_cost": 100.0,
             "current_price": 80.0, "market_value": 4000.0,
             "unrealized_pl": -1000.0, "unrealized_pl_pct": -20.0,
             "sector": "Tech"},
        ]
        portfolio_dao.snapshot_holdings(holdings, user_with_portfolio)

        alerts = get_smart_alerts(user_with_portfolio)
        tax_alerts = [a for a in alerts if a["category"] == "tax"]
        assert len(tax_alerts) >= 1
        assert "LOSS" in tax_alerts[0]["title"]
        assert tax_alerts[0]["severity"] == "info"

    def test_concentration_risk(self, test_db):
        from database.models import UserDAO, UserPreferencesDAO, PortfolioDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("concuser", "password123")
        UserPreferencesDAO(db=test_db).update(uid, onboarding_completed=1)

        portfolio_dao = PortfolioDAO(db=test_db)
        holdings = [
            {"ticker": "BIG", "quantity": 100, "average_cost": 100.0,
             "current_price": 100.0, "market_value": 10000.0,
             "unrealized_pl": 0, "unrealized_pl_pct": 0, "sector": "Tech"},
            {"ticker": "SML", "quantity": 10, "average_cost": 10.0,
             "current_price": 10.0, "market_value": 100.0,
             "unrealized_pl": 0, "unrealized_pl_pct": 0, "sector": "Tech"},
        ]
        portfolio_dao.snapshot_holdings(holdings, uid)

        alerts = get_smart_alerts(uid)
        risk_alerts = [a for a in alerts if a["category"] == "risk"]
        assert len(risk_alerts) >= 1
        assert "BIG" in risk_alerts[0]["title"]

    def test_no_false_alerts(self, test_db):
        """A balanced portfolio with no losses should produce no alerts."""
        from database.models import UserDAO, UserPreferencesDAO, PortfolioDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("baluser", "password123")
        UserPreferencesDAO(db=test_db).update(uid, onboarding_completed=1)

        portfolio_dao = PortfolioDAO(db=test_db)
        # 5 positions, each ~20% — no concentration risk, no losses
        holdings = [
            {"ticker": "AA", "quantity": 10, "average_cost": 100.0,
             "current_price": 105.0, "market_value": 1050.0,
             "unrealized_pl": 50.0, "unrealized_pl_pct": 5.0, "sector": "Tech"},
            {"ticker": "BB", "quantity": 10, "average_cost": 100.0,
             "current_price": 102.0, "market_value": 1020.0,
             "unrealized_pl": 20.0, "unrealized_pl_pct": 2.0, "sector": "Health"},
            {"ticker": "CC", "quantity": 10, "average_cost": 100.0,
             "current_price": 101.0, "market_value": 1010.0,
             "unrealized_pl": 10.0, "unrealized_pl_pct": 1.0, "sector": "Energy"},
            {"ticker": "DD", "quantity": 10, "average_cost": 100.0,
             "current_price": 103.0, "market_value": 1030.0,
             "unrealized_pl": 30.0, "unrealized_pl_pct": 3.0, "sector": "Finance"},
            {"ticker": "EE", "quantity": 10, "average_cost": 100.0,
             "current_price": 104.0, "market_value": 1040.0,
             "unrealized_pl": 40.0, "unrealized_pl_pct": 4.0, "sector": "Retail"},
        ]
        portfolio_dao.snapshot_holdings(holdings, uid)

        alerts = get_smart_alerts(uid)
        assert alerts == []
