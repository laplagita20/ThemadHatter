"""Authentication UI - Login / Register / Logout for multi-user support."""

import streamlit as st
from database.models import UserDAO


def login_register_page():
    """Render the login/register gate page. Returns True if user is authenticated."""
    if st.session_state.get("user_id"):
        return True

    st.markdown("""
    <div style="text-align: center; padding: 40px 0 20px 0;">
        <span style="font-size: 3rem;">&#127913;</span>
        <h1 style="color: #f59e0b; margin: 0;">The Mad Hatter</h1>
        <p style="color: #94a3b8;">Professional-Grade Financial Intelligence</p>
    </div>
    """, unsafe_allow_html=True)

    user_dao = UserDAO()

    tab_login, tab_register = st.tabs(["Login", "Create Account"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            submitted = st.form_submit_button("Login", type="primary")

            if submitted:
                if not username or not password:
                    st.error("Enter both username and password")
                else:
                    user = user_dao.authenticate(username, password)
                    if user:
                        st.session_state["user_id"] = user["id"]
                        st.session_state["username"] = user["username"]
                        st.rerun()
                    else:
                        st.error("Invalid username or password")

    with tab_register:
        with st.form("register_form"):
            new_user = st.text_input("Username", key="reg_user",
                                     help="At least 3 characters, case-insensitive")
            new_pass = st.text_input("Password", type="password", key="reg_pass",
                                     help="At least 6 characters")
            confirm_pass = st.text_input("Confirm Password", type="password", key="reg_confirm")
            submitted = st.form_submit_button("Create Account", type="primary")

            if submitted:
                if not new_user or not new_pass:
                    st.error("All fields are required")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match")
                else:
                    try:
                        user_dao.create(new_user, new_pass)
                        user = user_dao.authenticate(new_user, new_pass)
                        if user:
                            st.session_state["user_id"] = user["id"]
                            st.session_state["username"] = user["username"]
                            st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    return False


def logout_button():
    """Render a logout button in the sidebar."""
    username = st.session_state.get("username", "")
    st.sidebar.caption(f"Logged in as **{username}**")
    if st.sidebar.button("Logout", key="logout_btn"):
        for key in ["user_id", "username", "risk_report", "live_prices", "live_prices_ts"]:
            st.session_state.pop(key, None)
        st.rerun()


def get_current_user_id() -> int | None:
    """Get the current logged-in user's ID from session state."""
    return st.session_state.get("user_id")
