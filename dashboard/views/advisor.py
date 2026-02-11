"""AI Advisor Page — Chat, stock explainer, and trade ideas."""

import streamlit as st

from dashboard.components.auth import get_current_user_id


def _ai_setup_cta(feature_name: str = "this feature"):
    """Render an actionable CTA when AI is unavailable."""
    st.markdown(f"""
    <div class="setup-card">
        <div style="font-size: 1.2rem; font-weight: 700; color: #f59e0b; margin-bottom: 8px;">
            AI Required
        </div>
        <div style="color: #94a3b8; margin-bottom: 12px;">
            Add your Anthropic API key in Settings to enable {feature_name}.
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Go to Settings", key=f"cta_{feature_name.replace(' ', '_')}", type="primary"):
        st.session_state["nav_target"] = "Settings"
        st.rerun()


def _render_chat_tab(user_id: int):
    """Render the conversational AI chat interface."""
    from analysis.ai_advisor import ClaudeAdvisor
    advisor = ClaudeAdvisor(user_id)

    if not advisor.is_available():
        _ai_setup_cta("AI chat")
        return

    # Initialize chat history
    if "advisor_messages" not in st.session_state:
        st.session_state.advisor_messages = []

    # Suggested starters
    if not st.session_state.advisor_messages:
        st.markdown("**Try asking:**")
        suggestions = [
            "How is my portfolio doing?",
            "What should I buy right now?",
            "Am I too concentrated in tech?",
            "Explain my biggest winner",
        ]
        cols = st.columns(len(suggestions))
        for i, suggestion in enumerate(suggestions):
            with cols[i]:
                if st.button(suggestion, key=f"suggest_{i}", use_container_width=True):
                    st.session_state.advisor_messages.append(
                        {"role": "user", "content": suggestion}
                    )
                    st.rerun()

    # Display chat history
    for msg in st.session_state.advisor_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Clear chat button
    if st.session_state.advisor_messages:
        if st.button("Clear Chat", key="clear_chat"):
            st.session_state.advisor_messages = []
            st.rerun()

    # Chat input
    if prompt := st.chat_input("Ask about your portfolio, stocks, or markets..."):
        st.session_state.advisor_messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            # Build chat history for context (limit to last 10 messages)
            history = st.session_state.advisor_messages[-10:-1]
            response_text = st.write_stream(
                advisor.stream_answer(prompt, chat_history=history)
            )

        st.session_state.advisor_messages.append(
            {"role": "assistant", "content": response_text}
        )


def _render_explain_tab(user_id: int):
    """Render the stock explainer tab."""
    from analysis.ai_advisor import ClaudeAdvisor
    advisor = ClaudeAdvisor(user_id)

    if not advisor.is_available():
        _ai_setup_cta("stock explanations")
        return

    st.markdown("Enter a ticker to get a plain-English analysis of what the data says.")

    col1, col2 = st.columns([3, 1])
    with col1:
        ticker = st.text_input("Ticker Symbol", placeholder="AAPL",
                               key="explain_ticker").strip().upper()
    with col2:
        st.write("")  # Spacing
        explain_btn = st.button("Explain", type="primary", key="explain_btn")

    if explain_btn and ticker:
        with st.spinner(f"Analyzing {ticker}..."):
            explanation = advisor.explain_stock(ticker)

        if explanation:
            st.markdown(explanation)
        else:
            st.warning(f"Could not generate explanation for {ticker}. "
                       "Make sure the stock has been analyzed first.")
    elif explain_btn:
        st.warning("Enter a ticker symbol first.")

    # Show recently explained (from cache)
    if "explain_ticker" in st.session_state and not explain_btn:
        from database.models import AIAdviceCacheDAO
        cache_dao = AIAdviceCacheDAO()
        # Show last few explanations from cache
        recent = cache_dao._get_recent_cache(user_id, "stock_explain") if hasattr(cache_dao, '_get_recent_cache') else []


def _render_trade_ideas_tab(user_id: int):
    """Render the AI trade suggestions tab."""
    from analysis.ai_advisor import ClaudeAdvisor
    advisor = ClaudeAdvisor(user_id)

    if not advisor.is_available():
        _ai_setup_cta("trade ideas")
        return

    st.markdown("""
    Get an AI-powered trade recommendation based on your portfolio,
    current market conditions, and analysis signals.
    """)

    if st.button("Generate Trade Idea", type="primary", key="trade_idea_btn"):
        with st.spinner("Deep analysis in progress... This may take a moment."):
            suggestion = advisor.get_trade_suggestion()

        if suggestion:
            st.markdown(suggestion)
        else:
            st.warning("Could not generate a trade suggestion. Try again later.")

    st.caption("Trade ideas are AI-generated suggestions, not financial advice. "
               "Always do your own research before trading.")


def render():
    """Render the advisor page."""
    st.header("AI Advisor")

    user_id = get_current_user_id()
    if not user_id:
        st.warning("Please log in to use the AI advisor.")
        return

    tab_chat, tab_explain, tab_trades = st.tabs([
        "Ask Anything", "Explain a Stock", "Trade Ideas"
    ])

    with tab_chat:
        _render_chat_tab(user_id)

    with tab_explain:
        _render_explain_tab(user_id)

    with tab_trades:
        _render_trade_ideas_tab(user_id)
