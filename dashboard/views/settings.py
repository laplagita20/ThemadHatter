"""Settings Page — User preferences and API key management."""

import streamlit as st

from config.settings import get_settings, invalidate_settings
from database.models import UserPreferencesDAO, AppConfigDAO, AIAdviceCacheDAO
from dashboard.components.auth import get_current_user_id
from dashboard.components.teach_me import teach_me_sidebar


def _render_api_key_field(label: str, config_key: str, description: str,
                          config_dao: AppConfigDAO, placeholder: str = "sk-..."):
    """Render an interactive API key field with save/remove."""
    settings = get_settings()
    current = getattr(settings, config_key.lower(), "") or ""

    st.markdown(f"**{label}**")
    st.caption(description)

    if current:
        # Show masked key + remove button
        masked = current[:8] + "..." + current[-4:] if len(current) > 12 else "****"
        col1, col2 = st.columns([4, 1])
        with col1:
            st.success(f"Configured: `{masked}`")
        with col2:
            if st.button("Remove", key=f"remove_{config_key}"):
                config_dao.delete(config_key.upper())
                invalidate_settings()
                st.rerun()
    else:
        # Show input field
        new_key = st.text_input(
            f"Enter {label}",
            type="password",
            placeholder=placeholder,
            key=f"input_{config_key}",
            label_visibility="collapsed",
        )
        if st.button("Save", key=f"save_{config_key}", type="primary"):
            if new_key and new_key.strip():
                config_dao.set(config_key.upper(), new_key.strip())
                invalidate_settings()
                st.success(f"{label} saved!")
                st.rerun()
            else:
                st.warning("Please enter a key.")


def render():
    """Render the settings page."""
    st.header("Settings")

    user_id = get_current_user_id()
    if not user_id:
        st.warning("Please log in.")
        return

    prefs_dao = UserPreferencesDAO()
    prefs = prefs_dao.get(user_id)
    config_dao = AppConfigDAO()

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
            AIAdviceCacheDAO().invalidate(user_id)
            st.success("Profile updated! AI advice will adapt to your new preferences.")

    st.divider()

    # AI Advisor API Key
    st.subheader("AI Advisor")
    _render_api_key_field(
        "Anthropic API Key",
        "ANTHROPIC_API_KEY",
        "Powers AI insights, stock explanations, and trade ideas. "
        "Get a key from [console.anthropic.com](https://console.anthropic.com/)",
        config_dao,
        placeholder="sk-ant-...",
    )

    st.divider()

    # Data Source API Keys
    st.subheader("Data Source API Keys")

    _render_api_key_field(
        "FRED API Key",
        "FRED_API_KEY",
        "Economic data (GDP, inflation, interest rates). "
        "Free at [fred.stlouisfed.org/docs/api](https://fred.stlouisfed.org/docs/api/api_key.html)",
        config_dao,
        placeholder="abc123...",
    )

    st.markdown("")  # spacing

    _render_api_key_field(
        "Alpha Vantage API Key",
        "ALPHA_VANTAGE_API_KEY",
        "Analyst price targets and earnings history. "
        "Free at [alphavantage.co](https://www.alphavantage.co/support/#api-key)",
        config_dao,
        placeholder="ABCD1234...",
    )

    st.markdown("")  # spacing

    _render_api_key_field(
        "Finnhub API Key",
        "FINNHUB_API_KEY",
        "Real-time quotes and market news. "
        "Free at [finnhub.io](https://finnhub.io/register)",
        config_dao,
        placeholder="abc123def...",
    )

    st.divider()

    # Learning Mode
    st.subheader("Learning Mode")
    teach_me_sidebar()

    st.divider()

    # Data Management
    st.subheader("Data Management")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Clear AI Cache", key="clear_ai_cache"):
            AIAdviceCacheDAO().invalidate(user_id)
            st.success("AI cache cleared. Fresh insights will be generated.")

    with col2:
        if st.button("Re-run Onboarding", key="rerun_onboarding"):
            prefs_dao.update(user_id, onboarding_completed=0)
            st.rerun()
