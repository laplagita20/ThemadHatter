"""Mad Hatter finance theme - dark wonderland meets Wall Street."""

import streamlit as st

# Color palette
COLORS = {
    "bg_dark": "#0e1117",
    "bg_card": "#1a1f2e",
    "bg_sidebar": "#12152b",
    "purple_deep": "#2d1b69",
    "purple_accent": "#7c3aed",
    "purple_glow": "#a78bfa",
    "teal": "#06b6d4",
    "teal_dark": "#0e7490",
    "gold": "#f59e0b",
    "gold_muted": "#d97706",
    "green_profit": "#10b981",
    "red_loss": "#ef4444",
    "text_primary": "#e2e8f0",
    "text_muted": "#94a3b8",
    "border": "#334155",
}


def inject_theme():
    """Inject the Mad Hatter CSS theme into the Streamlit app."""
    st.markdown("""
    <style>
    /* === MAD HATTER FINANCE THEME === */

    /* Main background */
    .stApp {
        background: linear-gradient(180deg, #0e1117 0%, #12152b 50%, #0e1117 100%);
    }

    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #12152b 0%, #1a1040 100%);
        border-right: 1px solid #2d1b69;
    }

    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2 {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 50%, #f59e0b 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
    }

    /* Header styling with gold accent */
    .stApp h1 {
        background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 50%, #d97706 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        letter-spacing: -0.5px;
    }

    .stApp h2 {
        color: #a78bfa !important;
        border-bottom: 2px solid #2d1b69;
        padding-bottom: 8px;
    }

    .stApp h3 {
        color: #06b6d4 !important;
    }

    /* Metric cards with glass morphism */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(45, 27, 105, 0.4) 0%, rgba(30, 20, 70, 0.6) 100%);
        border: 1px solid rgba(124, 58, 237, 0.3);
        border-radius: 12px;
        padding: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px rgba(124, 58, 237, 0.1);
        transition: all 0.3s ease;
    }

    [data-testid="stMetric"]:hover {
        border-color: rgba(124, 58, 237, 0.6);
        box-shadow: 0 4px 30px rgba(124, 58, 237, 0.2);
        transform: translateY(-2px);
    }

    [data-testid="stMetric"] label {
        color: #94a3b8 !important;
        text-transform: uppercase;
        font-size: 0.7rem !important;
        letter-spacing: 1px;
    }

    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #f59e0b !important;
        font-weight: 700;
    }

    /* Positive/negative delta colors */
    [data-testid="stMetricDelta"] svg[fill="rgba(9, 171, 59)"] ~ div {
        color: #10b981 !important;
    }
    [data-testid="stMetricDelta"] svg[fill="rgba(255, 43, 43)"] ~ div {
        color: #ef4444 !important;
    }

    /* DataFrames / tables */
    .stDataFrame {
        border: 1px solid #2d1b69;
        border-radius: 8px;
        overflow: hidden;
    }

    /* Buttons */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #7c3aed 0%, #2d1b69 100%) !important;
        border: 1px solid #a78bfa !important;
        color: white !important;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }

    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="baseButton-primary"]:hover {
        background: linear-gradient(135deg, #a78bfa 0%, #7c3aed 100%) !important;
        box-shadow: 0 4px 20px rgba(124, 58, 237, 0.4);
    }

    .stButton > button[kind="secondary"],
    .stButton > button[data-testid="baseButton-secondary"] {
        background: transparent !important;
        border: 1px solid #06b6d4 !important;
        color: #06b6d4 !important;
        border-radius: 8px;
    }

    .stButton > button[kind="secondary"]:hover,
    .stButton > button[data-testid="baseButton-secondary"]:hover {
        background: rgba(6, 182, 212, 0.1) !important;
    }

    /* Expander */
    .streamlit-expanderHeader {
        background: rgba(45, 27, 105, 0.3) !important;
        border: 1px solid rgba(124, 58, 237, 0.2);
        border-radius: 8px;
        color: #a78bfa !important;
    }

    /* Success / Warning / Error / Info alerts */
    .stAlert [data-testid="stAlertContentSuccess"] {
        background: rgba(16, 185, 129, 0.15);
        border-left: 4px solid #10b981;
    }
    .stAlert [data-testid="stAlertContentWarning"] {
        background: rgba(245, 158, 11, 0.15);
        border-left: 4px solid #f59e0b;
    }
    .stAlert [data-testid="stAlertContentError"] {
        background: rgba(239, 68, 68, 0.15);
        border-left: 4px solid #ef4444;
    }
    .stAlert [data-testid="stAlertContentInfo"] {
        background: rgba(6, 182, 212, 0.15);
        border-left: 4px solid #06b6d4;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(45, 27, 105, 0.3);
        border-radius: 8px 8px 0 0;
        border: 1px solid rgba(124, 58, 237, 0.2);
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(124, 58, 237, 0.3) !important;
        border-color: #7c3aed !important;
        color: #f59e0b !important;
    }

    /* Selectbox / inputs */
    .stSelectbox > div > div,
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stTextArea > div > div > textarea {
        background: rgba(26, 31, 46, 0.8) !important;
        border: 1px solid #334155 !important;
        border-radius: 8px;
        color: #e2e8f0 !important;
    }

    .stSelectbox > div > div:focus-within,
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #7c3aed !important;
        box-shadow: 0 0 0 2px rgba(124, 58, 237, 0.2) !important;
    }

    /* Divider */
    hr {
        border-color: #2d1b69 !important;
    }

    /* Radio buttons in sidebar */
    .stRadio > div {
        gap: 2px;
    }
    .stRadio > div > label {
        padding: 8px 12px;
        border-radius: 6px;
        transition: all 0.2s ease;
    }
    .stRadio > div > label:hover {
        background: rgba(124, 58, 237, 0.15);
    }
    .stRadio > div > label[data-checked="true"] {
        background: rgba(124, 58, 237, 0.25);
    }

    /* Progress bar */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #7c3aed 0%, #06b6d4 100%) !important;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0e1117;
    }
    ::-webkit-scrollbar-thumb {
        background: #2d1b69;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #7c3aed;
    }

    /* Mad Hatter branding flourish */
    section[data-testid="stSidebar"]::before {
        content: "";
        display: block;
        height: 3px;
        background: linear-gradient(90deg, #7c3aed, #f59e0b, #06b6d4, #7c3aed);
        margin-bottom: 1rem;
    }

    /* Card-like containers */
    [data-testid="stExpander"] {
        background: rgba(26, 31, 46, 0.5);
        border: 1px solid rgba(124, 58, 237, 0.2);
        border-radius: 12px;
        overflow: hidden;
    }

    /* === AI ADVISOR STYLES === */

    /* Chat messages */
    [data-testid="stChatMessage"] {
        background: rgba(26, 31, 46, 0.6) !important;
        border: 1px solid rgba(124, 58, 237, 0.15);
        border-radius: 12px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }

    /* User messages slightly different */
    [data-testid="stChatMessage"][data-testid*="user"] {
        background: rgba(45, 27, 105, 0.3) !important;
        border-color: rgba(124, 58, 237, 0.3);
    }

    /* Chat input */
    [data-testid="stChatInput"] textarea {
        background: rgba(26, 31, 46, 0.8) !important;
        border: 1px solid rgba(124, 58, 237, 0.3) !important;
        border-radius: 12px;
        color: #e2e8f0 !important;
    }

    [data-testid="stChatInput"] textarea:focus {
        border-color: #7c3aed !important;
        box-shadow: 0 0 0 2px rgba(124, 58, 237, 0.2) !important;
    }

    /* Smart alert cards */
    .smart-alert {
        background: rgba(26, 31, 46, 0.5);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
        border-left: 3px solid;
    }
    .smart-alert.success { border-left-color: #10b981; }
    .smart-alert.warning { border-left-color: #f59e0b; }
    .smart-alert.info { border-left-color: #06b6d4; }
    .smart-alert.error { border-left-color: #ef4444; }

    /* AI insight card */
    .ai-insight-card {
        background: linear-gradient(135deg, rgba(45, 27, 105, 0.3), rgba(6, 182, 212, 0.1));
        border: 1px solid rgba(124, 58, 237, 0.3);
        border-radius: 12px;
        padding: 20px;
        margin: 8px 0;
    }

    /* Onboarding progress */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #7c3aed 0%, #f59e0b 100%) !important;
        border-radius: 4px;
    }

    /* Setup cards for empty state and CTAs */
    .setup-card {
        background: linear-gradient(135deg, rgba(45, 27, 105, 0.4), rgba(30, 20, 70, 0.6));
        border: 1px solid rgba(124, 58, 237, 0.3);
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 16px;
        transition: all 0.3s ease;
    }
    .setup-card:hover {
        border-color: rgba(124, 58, 237, 0.6);
        box-shadow: 0 4px 20px rgba(124, 58, 237, 0.15);
    }

    /* API key status cards */
    .api-key-card {
        background: rgba(26, 31, 46, 0.6);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .api-key-card.configured {
        border-color: rgba(16, 185, 129, 0.4);
    }
    </style>
    """, unsafe_allow_html=True)


def mad_hatter_header():
    """Render the Mad Hatter branded header."""
    st.markdown("""
    <div style="text-align: center; padding: 0.5rem 0 1rem 0;">
        <div style="font-size: 2.5rem; font-weight: 800;
                    background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 30%, #d97706 70%, #f59e0b 100%);
                    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                    letter-spacing: -1px; line-height: 1.1;">
            The Mad Hatter
        </div>
        <div style="font-size: 0.85rem; color: #06b6d4; letter-spacing: 3px;
                    text-transform: uppercase; margin-top: 4px;">
            AI Financial Advisor
        </div>
        <div style="height: 2px; margin-top: 12px;
                    background: linear-gradient(90deg, transparent, #7c3aed, #f59e0b, #06b6d4, transparent);">
        </div>
    </div>
    """, unsafe_allow_html=True)
