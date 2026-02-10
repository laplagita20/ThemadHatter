"""Tests for the AI advisor module with mocked Anthropic client."""

import pytest
from unittest.mock import MagicMock, patch
from analysis.ai_advisor import ClaudeAdvisor


@pytest.fixture
def user_with_prefs(test_db):
    """Create a test user with preferences."""
    from database.models import UserDAO, UserPreferencesDAO
    user_dao = UserDAO(db=test_db)
    uid = user_dao.create("testuser", "password123")
    prefs_dao = UserPreferencesDAO(db=test_db)
    prefs_dao.update(uid, risk_tolerance="aggressive", experience_level="advanced",
                     onboarding_completed=1)
    return uid


@pytest.fixture
def user_with_portfolio(user_with_prefs, test_db, sample_holdings):
    """Create a test user with portfolio holdings."""
    from database.models import PortfolioDAO
    portfolio_dao = PortfolioDAO(db=test_db)
    portfolio_dao.snapshot_holdings(sample_holdings, user_with_prefs)
    return user_with_prefs


@pytest.fixture
def mock_anthropic():
    """Mock the anthropic module."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="This is a test AI response.")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_client.messages.create.return_value = mock_response
    return mock_client


# --- UserDAO Session Tests ---

class TestUserSessions:
    def test_create_session(self, test_db):
        from database.models import UserDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("sessionuser", "password123")
        token = user_dao.create_session(uid)
        assert token is not None
        assert len(token) > 20

    def test_validate_session(self, test_db):
        from database.models import UserDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("valuser", "password123")
        token = user_dao.create_session(uid)
        user = user_dao.validate_session(token)
        assert user is not None
        assert user["id"] == uid
        assert user["username"] == "valuser"

    def test_validate_invalid_session(self, test_db):
        from database.models import UserDAO
        user_dao = UserDAO(db=test_db)
        result = user_dao.validate_session("invalid_token_xyz")
        assert result is None

    def test_destroy_session(self, test_db):
        from database.models import UserDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("destroyuser", "password123")
        token = user_dao.create_session(uid)
        user_dao.destroy_session(token)
        result = user_dao.validate_session(token)
        assert result is None


# --- UserPreferencesDAO Tests ---

class TestUserPreferences:
    def test_auto_create_defaults(self, test_db):
        from database.models import UserDAO, UserPreferencesDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("prefuser", "password123")
        prefs_dao = UserPreferencesDAO(db=test_db)
        prefs = prefs_dao.get(uid)
        assert prefs["risk_tolerance"] == "moderate"
        assert prefs["investment_horizon"] == "medium"
        assert prefs["onboarding_completed"] == 0

    def test_update_preferences(self, test_db):
        from database.models import UserDAO, UserPreferencesDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("updatepref", "password123")
        prefs_dao = UserPreferencesDAO(db=test_db)
        prefs_dao.update(uid, risk_tolerance="aggressive", ai_personality="concise")
        prefs = prefs_dao.get(uid)
        assert prefs["risk_tolerance"] == "aggressive"
        assert prefs["ai_personality"] == "concise"
        # Unchanged fields keep defaults
        assert prefs["investment_horizon"] == "medium"

    def test_ignores_invalid_fields(self, test_db):
        from database.models import UserDAO, UserPreferencesDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("invalidfield", "password123")
        prefs_dao = UserPreferencesDAO(db=test_db)
        # Should not raise
        prefs_dao.update(uid, bogus_field="value", risk_tolerance="conservative")
        prefs = prefs_dao.get(uid)
        assert prefs["risk_tolerance"] == "conservative"


# --- AIAdviceCacheDAO Tests ---

class TestAIAdviceCache:
    def test_store_and_retrieve(self, test_db):
        from database.models import UserDAO, AIAdviceCacheDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("cacheuser", "password123")
        cache_dao = AIAdviceCacheDAO(db=test_db)

        cache_dao.store(uid, "digest", "2025-01-01", "Test response",
                        model_used="sonnet", tokens_used=150, ttl_hours=24)
        cached = cache_dao.get_cached(uid, "digest", "2025-01-01")
        assert cached is not None
        assert cached["response_text"] == "Test response"
        assert cached["model_used"] == "sonnet"

    def test_cache_miss(self, test_db):
        from database.models import UserDAO, AIAdviceCacheDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("nomatch", "password123")
        cache_dao = AIAdviceCacheDAO(db=test_db)
        result = cache_dao.get_cached(uid, "digest", "nonexistent")
        assert result is None

    def test_invalidate(self, test_db):
        from database.models import UserDAO, AIAdviceCacheDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("invaluser", "password123")
        cache_dao = AIAdviceCacheDAO(db=test_db)

        cache_dao.store(uid, "digest", "key1", "resp1", ttl_hours=24)
        cache_dao.store(uid, "explain", "key2", "resp2", ttl_hours=24)

        cache_dao.invalidate(uid, "digest")
        assert cache_dao.get_cached(uid, "digest", "key1") is None
        assert cache_dao.get_cached(uid, "explain", "key2") is not None

    def test_invalidate_all(self, test_db):
        from database.models import UserDAO, AIAdviceCacheDAO
        user_dao = UserDAO(db=test_db)
        uid = user_dao.create("invalall", "password123")
        cache_dao = AIAdviceCacheDAO(db=test_db)

        cache_dao.store(uid, "digest", "k1", "r1", ttl_hours=24)
        cache_dao.store(uid, "explain", "k2", "r2", ttl_hours=24)

        cache_dao.invalidate(uid)
        assert cache_dao.get_cached(uid, "digest", "k1") is None
        assert cache_dao.get_cached(uid, "explain", "k2") is None


# --- ClaudeAdvisor Tests ---

class TestClaudeAdvisor:
    def test_is_available_no_key(self, user_with_prefs):
        with patch("analysis.ai_advisor.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="")
            advisor = ClaudeAdvisor(user_with_prefs)
            assert advisor.is_available() is False

    def test_is_available_with_key(self, user_with_prefs):
        with patch("analysis.ai_advisor.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="sk-ant-test")
            advisor = ClaudeAdvisor(user_with_prefs)
            assert advisor.is_available() is True

    def test_build_system_prompt(self, user_with_prefs):
        advisor = ClaudeAdvisor(user_with_prefs)
        prompt = advisor._build_system_prompt()
        assert "aggressive" in prompt  # risk tolerance
        assert "advanced" in prompt  # experience level
        assert "Mad Hatter" in prompt

    def test_build_portfolio_context_empty(self, user_with_prefs):
        advisor = ClaudeAdvisor(user_with_prefs)
        ctx = advisor._build_portfolio_context()
        assert "no portfolio" in ctx.lower()

    def test_build_portfolio_context_with_holdings(self, user_with_portfolio):
        advisor = ClaudeAdvisor(user_with_portfolio)
        ctx = advisor._build_portfolio_context()
        assert "AAPL" in ctx
        assert "MSFT" in ctx
        assert "positions" in ctx.lower()

    def test_smart_alerts_empty_portfolio(self, user_with_prefs):
        advisor = ClaudeAdvisor(user_with_prefs)
        alerts = advisor.get_smart_alerts()
        assert alerts == []

    def test_smart_alerts_with_holdings(self, user_with_portfolio, test_db):
        # Add a losing position for tax-loss harvest detection
        from database.models import PortfolioDAO
        portfolio_dao = PortfolioDAO(db=test_db)
        holdings = [
            {"ticker": "LOSS", "quantity": 50, "average_cost": 100.0,
             "current_price": 80.0, "market_value": 4000.0,
             "unrealized_pl": -1000.0, "unrealized_pl_pct": -20.0,
             "sector": "Tech"},
        ]
        portfolio_dao.snapshot_holdings(holdings, user_with_portfolio)

        advisor = ClaudeAdvisor(user_with_portfolio)
        alerts = advisor.get_smart_alerts()
        # Should detect tax-loss harvest candidate
        tax_alerts = [a for a in alerts if a["category"] == "tax"]
        assert len(tax_alerts) >= 1
        assert "LOSS" in tax_alerts[0]["title"]

    def test_portfolio_digest_no_key(self, user_with_prefs):
        with patch("analysis.ai_advisor.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="")
            advisor = ClaudeAdvisor(user_with_prefs)
            result = advisor.get_portfolio_digest()
            assert result is None

    def test_explain_stock_no_key(self, user_with_prefs):
        with patch("analysis.ai_advisor.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="")
            advisor = ClaudeAdvisor(user_with_prefs)
            result = advisor.explain_stock("AAPL")
            assert result is None

    def test_portfolio_digest_with_mock(self, user_with_portfolio, mock_anthropic):
        with patch("analysis.ai_advisor.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="sk-ant-test")
            advisor = ClaudeAdvisor(user_with_portfolio)
            advisor._client = mock_anthropic

            result = advisor.get_portfolio_digest()
            assert result == "This is a test AI response."
            mock_anthropic.messages.create.assert_called_once()

    def test_explain_stock_with_mock(self, user_with_portfolio, mock_anthropic):
        with patch("analysis.ai_advisor.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="sk-ant-test")
            advisor = ClaudeAdvisor(user_with_portfolio)
            advisor._client = mock_anthropic

            result = advisor.explain_stock("AAPL")
            assert result == "This is a test AI response."

    def test_answer_question_with_mock(self, user_with_portfolio, mock_anthropic):
        with patch("analysis.ai_advisor.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="sk-ant-test")
            advisor = ClaudeAdvisor(user_with_portfolio)
            advisor._client = mock_anthropic

            result = advisor.answer_question("How is my portfolio doing?")
            assert result == "This is a test AI response."

    def test_digest_caching(self, user_with_portfolio, mock_anthropic, test_db):
        """Test that digest results are cached and reused."""
        with patch("analysis.ai_advisor.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(anthropic_api_key="sk-ant-test")
            advisor = ClaudeAdvisor(user_with_portfolio)
            advisor._client = mock_anthropic

            # First call — hits API
            result1 = advisor.get_portfolio_digest()
            assert mock_anthropic.messages.create.call_count == 1

            # Second call — should use cache
            result2 = advisor.get_portfolio_digest()
            assert mock_anthropic.messages.create.call_count == 1  # Not called again
            assert result2 == result1
