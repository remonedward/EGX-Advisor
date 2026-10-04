"""CSS and UI styling components."""
import streamlit as st


def apply_rtl():
    st.markdown("""
        <style>
        /* RTL Global */
        body {
            direction: rtl;
            text-align: right;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        /* Streamlit components RTL overrides */
        .stMarkdown, .stText, .stAlert, .stSelectbox, .stTextInput, .stButton {
            direction: rtl;
            text-align: right;
        }
        
        /* Metric cards */
        [data-testid="stMetricValue"] {
            direction: ltr;
            text-align: right;
        }
        
        /* Recommendation Badge */
        .rec-badge {
            display: inline-block;
            padding: 8px 16px;
            font-size: 24px;
            font-weight: bold;
            border-radius: 8px;
            text-align: center;
            width: 100%;
            margin-top: 10px;
            margin-bottom: 20px;
        }
        .rec-شراء-قوي { background-color: #1b5e20; color: white; }
        .rec-شراء { background-color: #4caf50; color: white; }
        .rec-احتفاظ { background-color: #ff9800; color: white; }
        .rec-بيع { background-color: #f44336; color: white; }
        .rec-بيع-قوي { background-color: #b71c1c; color: white; }
        
        /* Hide row indices in dataframe */
        [data-testid="stDataFrame"] {
            direction: rtl;
        }
        
        /* Fix table headers alignment */
        th {
            text-align: right !important;
        }
        </style>
    """, unsafe_allow_html=True)


def badge_html(recommendation: str) -> str:
    css_class = f"rec-{recommendation.replace(' ', '-')}"
    return f"<div class='rec-badge {css_class}'>{recommendation}</div>"
