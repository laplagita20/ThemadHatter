"""Onboarding Flow — Multi-step setup for new users."""

import streamlit as st

from database.models import UserPreferencesDAO, UserWatchlistDAO, StockDAO, PortfolioDAO
from dashboard.components.auth import get_current_user_id


POPULAR_STOCKS = [
    ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "Nvidia"),
    ("GOOGL", "Alphabet"), ("AMZN", "Amazon"), ("META", "Meta"),
    ("TSLA", "Tesla"), ("JPM", "JPMorgan"), ("V", "Visa"),
    ("JNJ", "Johnson & Johnson"), ("UNH", "UnitedHealth"), ("XOM", "Exxon"),
]


def render():
    """Render the multi-step onboarding flow."""
    user_id = get_current_user_id()
    if not user_id:
        return

    prefs_dao = UserPreferencesDAO()

    # Track step in session state
    if "onboarding_step" not in st.session_state:
        st.session_state.onboarding_step = 1

    step = st.session_state.onboarding_step

    # Progress bar
    st.progress(step / 4)

    if step == 1:
        _step_welcome()
    elif step == 2:
        _step_risk_profile(user_id, prefs_dao)
    elif step == 3:
        _step_portfolio(user_id)
    elif step == 4:
        _step_watchlist(user_id, prefs_dao)


def _step_welcome():
    """Step 1: Welcome screen."""
    st.markdown("""
    <div style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 4rem; margin-bottom: 16px;">&#127913;</div>
        <h1 style="color: #f59e0b; margin-bottom: 8px;">Welcome to The Mad Hatter</h1>
        <p style="color: #94a3b8; font-size: 1.2rem; max-width: 600px; margin: 0 auto 24px;">
            Your AI-powered financial advisor. Let's set up your profile
            so we can give you personalized insights.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    **Here's what The Mad Hatter can do for you:**

    - **AI Portfolio Insights** — Daily digests and personalized analysis
    - **Smart Alerts** — Tax-loss harvesting, earnings, concentration warnings
    - **Stock Explainer** — Plain-English analysis of any stock
    - **Trade Ideas** — AI-powered suggestions based on your goals
    - **Market Scanner** — Scan thousands of stocks for opportunities
    """)

    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        if st.button("Get Started", type="primary", use_container_width=True, key="ob_start"):
            st.session_state.onboarding_step = 2
            st.rerun()


def _step_risk_profile(user_id: int, prefs_dao: UserPreferencesDAO):
    """Step 2: Risk profile questionnaire."""
    st.header("Your Investment Profile")
    st.markdown("This helps us tailor insights and recommendations to your goals.")

    with st.form("risk_profile_form"):
        risk_tolerance = st.select_slider(
            "Risk Tolerance",
            options=["conservative", "moderate", "aggressive"],
            value="moderate",
            help="How much risk are you comfortable with?",
        )

        investment_horizon = st.select_slider(
            "Investment Horizon",
            options=["short", "medium", "long"],
            value="medium",
            help="Short (< 1yr), Medium (1-5yr), Long (5+ yr)",
        )

        experience_level = st.select_slider(
            "Experience Level",
            options=["beginner", "intermediate", "advanced"],
            value="intermediate",
            help="This affects how we explain things to you.",
        )

        ai_personality = st.selectbox(
            "AI Communication Style",
            ["balanced", "concise", "detailed", "encouraging"],
            help="How should the AI advisor talk to you?",
        )

        submitted = st.form_submit_button("Continue", type="primary")

        if submitted:
            prefs_dao.update(
                user_id,
                risk_tolerance=risk_tolerance,
                investment_horizon=investment_horizon,
                experience_level=experience_level,
                ai_personality=ai_personality,
            )
            st.session_state.onboarding_step = 3
            st.rerun()

    if st.button("Back", key="ob_back_2"):
        st.session_state.onboarding_step = 1
        st.rerun()


def _step_portfolio(user_id: int):
    """Step 3: Import portfolio (or skip)."""
    st.header("Import Your Portfolio")
    st.markdown("Add your holdings so we can give you personalized advice. You can always do this later.")

    st.caption("Enter holdings, one per line. Use `@ price` for cost basis.")
    portfolio_text = st.text_area(
        "Holdings",
        placeholder="AAPL 100 @ 150\nMSFT 50 @ 380\nNVDA 20\nGOOGL 10 @ 140",
        height=150,
        key="ob_portfolio_text",
        label_visibility="collapsed",
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("Save Holdings", type="primary", key="ob_save_holdings"):
            if portfolio_text and portfolio_text.strip():
                from utils.portfolio_parser import parse_portfolio_text
                parsed = parse_portfolio_text(portfolio_text)
                if parsed:
                    holdings = [
                        {"ticker": p["ticker"], "quantity": p["shares"],
                         "average_cost": p["cost"]}
                        for p in parsed
                    ]
                    portfolio_dao = PortfolioDAO()
                    portfolio_dao.snapshot_holdings(holdings, user_id)
                    st.success(f"Added {len(holdings)} holdings!")
                    st.session_state.onboarding_step = 4
                    st.rerun()
                else:
                    st.error("Could not parse any holdings. Use format: `AAPL 100 @ 150`")
            else:
                st.warning("Enter at least one holding, or skip.")
    with col2:
        if st.button("Skip for Now", key="ob_skip_portfolio"):
            st.session_state.onboarding_step = 4
            st.rerun()
    with col3:
        if st.button("Back", key="ob_back_3"):
            st.session_state.onboarding_step = 2
            st.rerun()


def _step_watchlist(user_id: int, prefs_dao: UserPreferencesDAO):
    """Step 4: Add watchlist stocks with popular suggestions."""
    st.header("Build Your Watchlist")
    st.markdown("Pick stocks you want to track. You can always add more later.")

    wl_dao = UserWatchlistDAO()
    stock_dao = StockDAO()

    # Popular stock buttons
    st.markdown("**Popular stocks:**")
    cols = st.columns(4)
    selected = st.session_state.get("ob_selected_stocks", set())

    for i, (ticker, name) in enumerate(POPULAR_STOCKS):
        with cols[i % 4]:
            label = f"{ticker}" if ticker not in selected else f"{ticker} (added)"
            if st.button(label, key=f"ob_pop_{ticker}", use_container_width=True,
                         disabled=ticker in selected):
                stock_dao.upsert(ticker=ticker, company_name=name)
                wl_dao.add(user_id, ticker)
                selected.add(ticker)
                st.session_state.ob_selected_stocks = selected
                st.rerun()

    # Custom tickers
    st.divider()
    custom = st.text_input("Add other tickers (comma-separated)",
                           placeholder="MU, SOFI, PLTR", key="ob_custom_tickers")
    if st.button("Add Custom", key="ob_add_custom"):
        if custom:
            tickers = [t.strip().upper() for t in custom.split(",") if t.strip()]
            for t in tickers:
                try:
                    import yfinance as yf
                    info = yf.Ticker(t).info
                    stock_dao.upsert(
                        ticker=t,
                        company_name=info.get("longName", info.get("shortName", "")),
                        sector=info.get("sector", ""),
                    )
                    wl_dao.add(user_id, t)
                    st.success(f"Added {t}")
                except Exception as e:
                    st.error(f"Failed: {t} — {e}")

    st.divider()

    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        if st.button("Finish Setup", type="primary", use_container_width=True,
                      key="ob_finish"):
            prefs_dao.update(user_id, onboarding_completed=1)
            # Clean up session state
            st.session_state.pop("onboarding_step", None)
            st.session_state.pop("ob_selected_stocks", None)
            st.rerun()

    if st.button("Back", key="ob_back_4"):
        st.session_state.onboarding_step = 3
        st.rerun()
