"""Professional trading dashboard theme — TradingView/Bloomberg inspired."""

import streamlit as st

# Color palette — TradingView-inspired
COLORS = {
    "bg_primary": "#131722",
    "bg_card": "#1E222D",
    "bg_elevated": "#2A2E39",
    "border": "#2A2E39",
    "border_light": "#363A45",
    "accent": "#2962FF",
    "accent_hover": "#1E53E5",
    "green": "#26A69A",
    "green_bg": "rgba(38, 166, 154, 0.12)",
    "red": "#EF5350",
    "red_bg": "rgba(239, 83, 80, 0.12)",
    "text_primary": "#D1D4DC",
    "text_secondary": "#787B86",
    "text_muted": "#5D606B",
    "white": "#FFFFFF",
}


def inject_theme():
    """Inject the professional trading dashboard CSS theme."""
    st.markdown("""
    <style>
    /* === PROFESSIONAL TRADING DASHBOARD THEME === */

    /* Main background */
    .stApp {
        background: #131722;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #1E222D;
        border-right: 1px solid #2A2E39;
    }

    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2 {
        color: #D1D4DC;
        font-weight: 700;
    }

    /* Headers */
    .stApp h1 {
        color: #D1D4DC !important;
        font-weight: 700;
        letter-spacing: -0.3px;
    }

    .stApp h2 {
        color: #D1D4DC !important;
        border-bottom: 1px solid #2A2E39;
        padding-bottom: 8px;
        font-weight: 600;
    }

    .stApp h3 {
        color: #787B86 !important;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.85rem !important;
        letter-spacing: 0.5px;
    }

    /* Metric cards — clean flat style */
    [data-testid="stMetric"] {
        background: #1E222D;
        border: 1px solid #2A2E39;
        border-radius: 8px;
        padding: 14px;
    }

    [data-testid="stMetric"] label {
        color: #787B86 !important;
        text-transform: uppercase;
        font-size: 0.7rem !important;
        letter-spacing: 0.8px;
    }

    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #D1D4DC !important;
        font-weight: 700;
        font-size: 1.4rem !important;
    }

    /* Positive/negative delta colors */
    [data-testid="stMetricDelta"] svg[fill="rgba(9, 171, 59)"] ~ div {
        color: #26A69A !important;
    }
    [data-testid="stMetricDelta"] svg[fill="rgba(255, 43, 43)"] ~ div {
        color: #EF5350 !important;
    }

    /* DataFrames / tables — compact with alternating rows */
    .stDataFrame {
        border: 1px solid #2A2E39;
        border-radius: 6px;
        overflow: hidden;
    }

    /* Buttons */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="baseButton-primary"] {
        background: #2962FF !important;
        border: none !important;
        color: white !important;
        border-radius: 6px;
        font-weight: 600;
        transition: background 0.2s ease;
    }

    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="baseButton-primary"]:hover {
        background: #1E53E5 !important;
    }

    .stButton > button[kind="secondary"],
    .stButton > button[data-testid="baseButton-secondary"] {
        background: transparent !important;
        border: 1px solid #363A45 !important;
        color: #D1D4DC !important;
        border-radius: 6px;
    }

    .stButton > button[kind="secondary"]:hover,
    .stButton > button[data-testid="baseButton-secondary"]:hover {
        background: rgba(41, 98, 255, 0.1) !important;
        border-color: #2962FF !important;
    }

    /* Expander */
    .streamlit-expanderHeader {
        background: #1E222D !important;
        border: 1px solid #2A2E39;
        border-radius: 6px;
        color: #D1D4DC !important;
    }

    /* Alerts */
    .stAlert [data-testid="stAlertContentSuccess"] {
        background: rgba(38, 166, 154, 0.1);
        border-left: 3px solid #26A69A;
    }
    .stAlert [data-testid="stAlertContentWarning"] {
        background: rgba(255, 152, 0, 0.1);
        border-left: 3px solid #FF9800;
    }
    .stAlert [data-testid="stAlertContentError"] {
        background: rgba(239, 83, 80, 0.1);
        border-left: 3px solid #EF5350;
    }
    .stAlert [data-testid="stAlertContentInfo"] {
        background: rgba(41, 98, 255, 0.1);
        border-left: 3px solid #2962FF;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid #2A2E39;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        border-radius: 0;
        color: #787B86;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important;
        border-bottom: 2px solid #2962FF !important;
        color: #D1D4DC !important;
    }

    /* Inputs */
    .stSelectbox > div > div,
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stTextArea > div > div > textarea {
        background: #1E222D !important;
        border: 1px solid #2A2E39 !important;
        border-radius: 6px;
        color: #D1D4DC !important;
    }

    .stSelectbox > div > div:focus-within,
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #2962FF !important;
        box-shadow: 0 0 0 1px rgba(41, 98, 255, 0.3) !important;
    }

    /* Divider */
    hr {
        border-color: #2A2E39 !important;
    }

    /* Radio buttons in sidebar */
    .stRadio > div {
        gap: 2px;
    }
    .stRadio > div > label {
        padding: 8px 12px;
        border-radius: 4px;
        transition: background 0.15s ease;
    }
    .stRadio > div > label:hover {
        background: rgba(41, 98, 255, 0.1);
    }
    .stRadio > div > label[data-checked="true"] {
        background: rgba(41, 98, 255, 0.15);
    }

    /* Progress bar */
    .stProgress > div > div > div {
        background: #2962FF !important;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #131722;
    }
    ::-webkit-scrollbar-thumb {
        background: #2A2E39;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #363A45;
    }

    /* Top accent line */
    section[data-testid="stSidebar"]::before {
        content: "";
        display: block;
        height: 2px;
        background: #2962FF;
        margin-bottom: 1rem;
    }

    /* Containers */
    [data-testid="stExpander"] {
        background: #1E222D;
        border: 1px solid #2A2E39;
        border-radius: 6px;
        overflow: hidden;
    }

    /* Chat messages */
    [data-testid="stChatMessage"] {
        background: #1E222D !important;
        border: 1px solid #2A2E39;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }

    [data-testid="stChatMessage"][data-testid*="user"] {
        background: rgba(41, 98, 255, 0.08) !important;
        border-color: rgba(41, 98, 255, 0.2);
    }

    [data-testid="stChatInput"] textarea {
        background: #1E222D !important;
        border: 1px solid #2A2E39 !important;
        border-radius: 8px;
        color: #D1D4DC !important;
    }

    [data-testid="stChatInput"] textarea:focus {
        border-color: #2962FF !important;
        box-shadow: 0 0 0 1px rgba(41, 98, 255, 0.3) !important;
    }

    /* Smart alert cards */
    .smart-alert {
        background: #1E222D;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 8px;
        border-left: 3px solid;
    }
    .smart-alert.success { border-left-color: #26A69A; }
    .smart-alert.warning { border-left-color: #FF9800; }
    .smart-alert.info { border-left-color: #2962FF; }
    .smart-alert.error { border-left-color: #EF5350; }

    /* Setup cards */
    .setup-card {
        background: #1E222D;
        border: 1px solid #2A2E39;
        border-radius: 8px;
        padding: 24px;
        margin-bottom: 16px;
    }
    .setup-card:hover {
        border-color: #363A45;
    }

    /* API key status cards */
    .api-key-card {
        background: #1E222D;
        border: 1px solid #2A2E39;
        border-radius: 6px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .api-key-card.configured {
        border-color: rgba(38, 166, 154, 0.4);
    }

    /* Market bar component */
    .market-bar {
        display: flex;
        gap: 16px;
        padding: 8px 0;
        border-bottom: 1px solid #2A2E39;
        margin-bottom: 16px;
    }
    .market-bar-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.85rem;
    }
    .market-bar-item .symbol {
        color: #787B86;
        font-weight: 600;
    }
    .market-bar-item .price {
        color: #D1D4DC;
    }
    .market-bar-item .change-up {
        color: #26A69A;
        font-weight: 600;
    }
    .market-bar-item .change-down {
        color: #EF5350;
        font-weight: 600;
    }

    /* Market status badge */
    .market-status {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .market-status.open { background: rgba(38, 166, 154, 0.15); color: #26A69A; }
    .market-status.closed { background: rgba(120, 123, 134, 0.15); color: #787B86; }
    .market-status.pre-market { background: rgba(255, 152, 0, 0.15); color: #FF9800; }
    .market-status.after-hours { background: rgba(41, 98, 255, 0.15); color: #2962FF; }

    </style>
    """, unsafe_allow_html=True)


def mad_hatter_header():
    """Render the branded header in sidebar."""
    st.markdown("""
    <div style="text-align: center; padding: 0.5rem 0 1rem 0;">
        <div style="font-size: 1.8rem; font-weight: 700;
                    color: #D1D4DC;
                    letter-spacing: -0.5px; line-height: 1.1;">
            Mad Hatter
        </div>
        <div style="font-size: 0.75rem; color: #787B86; letter-spacing: 2px;
                    text-transform: uppercase; margin-top: 4px;">
            Trading Dashboard
        </div>
    </div>
    """, unsafe_allow_html=True)
