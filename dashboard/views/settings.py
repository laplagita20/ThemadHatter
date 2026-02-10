"""Settings Page — User preferences and API key management."""

import streamlit as st

from config.settings import get_settings
from database.models import UserPreferencesDAO
from dashboard.components.auth import get_current_user_id


def render():
    """Render the settings page."""
    st.header("Settings")

    user_id = get_current_user_id()
    if not user_id:
        st.warning("Please log in.")
        return

    prefs_dao = UserPreferencesDAO()
    prefs = prefs_dao.get(user_id)

    # Investment Profile
    st.subheader("Investment Profile")

    with st.form("settings_profile"):
        risk_tolerance = st.select_slider(
            "Risk Tolerance",
            options=["conservative", "moderate", "aggressive"],
            value=prefs.get("risk_tolerance", "moderate"),
        )

        investment_horizon = st.select_slider(
            "Investment Horizon",
            options=["short", "medium", "long"],
            value=prefs.get("investment_horizon", "medium"),
            help="Short (< 1yr), Medium (1-5yr), Long (5+ yr)",
        )

        experience_level = st.select_slider(
            "Experience Level",
            options=["beginner", "intermediate", "advanced"],
            value=prefs.get("experience_level", "intermediate"),
        )

        ai_personality = st.selectbox(
            "AI Communication Style",
            ["balanced", "concise", "detailed", "encouraging"],
            index=["balanced", "concise", "detailed", "encouraging"].index(
                prefs.get("ai_personality", "balanced")
            ),
        )

        if st.form_submit_button("Save Profile", type="primary"):
            prefs_dao.update(
                user_id,
                risk_tolerance=risk_tolerance,
                investment_horizon=investment_horizon,
                experience_level=experience_level,
                ai_personality=ai_personality,
            )
            # Invalidate AI cache so new preferences take effect
            from database.models import AIAdviceCacheDAO
            AIAdviceCacheDAO().invalidate(user_id)
            st.success("Profile updated! AI advice will adapt to your new preferences.")

    st.divider()

    # API Key Status
    st.subheader("AI Advisor Status")
    settings = get_settings()

    if settings.anthropic_api_key:
        st.success("Anthropic API key is configured. AI features are active.")
        # Show masked key
        key = settings.anthropic_api_key
        masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "****"
        st.text(f"Key: {masked}")
    else:
        st.warning("No Anthropic API key configured. AI features are disabled.")
        st.markdown("""
        **To enable AI features:**
        1. Get an API key from [console.anthropic.com](https://console.anthropic.com/)
        2. Add it to your `.env` file: `ANTHROPIC_API_KEY=sk-ant-...`
        3. Or set it as an environment variable
        4. Restart the dashboard
        """)

    st.divider()

    # Other API Keys
    st.subheader("Data Source API Keys")

    apis = [
        ("FRED", settings.fred_api_key, "Economic data (GDP, inflation, rates)"),
        ("Alpha Vantage", settings.alpha_vantage_api_key, "Analyst targets, earnings history"),
        ("Finnhub", settings.finnhub_api_key, "Real-time quotes, market news"),
    ]

    for name, key, desc in apis:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text(f"{name}: {desc}")
        with col2:
            if key:
                st.markdown(":green[Configured]")
            else:
                st.markdown(":red[Not set]")

    st.divider()

    # Data Management
    st.subheader("Data Management")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Clear AI Cache", key="clear_ai_cache"):
            from database.models import AIAdviceCacheDAO
            AIAdviceCacheDAO().invalidate(user_id)
            st.success("AI cache cleared. Fresh insights will be generated.")

    with col2:
        if st.button("Re-run Onboarding", key="rerun_onboarding"):
            prefs_dao.update(user_id, onboarding_completed=0)
            st.rerun()
