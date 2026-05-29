"""MeetIQ — AI meeting insight generator and action tracker.
Entry point: only does Streamlit setup + page routing. All real work lives
inside the page modules under `pages/`.
Run locally:
    streamlit run app.py
"""
import streamlit as st
from core.database import load_all
from ui import sidebar
from views import analytics, capture, companies, dashboard, history, people, stakeholders, tracker
from ui.styles import inject_css

# ── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI-Powered Meeting Insight Generator and Action Tracker",
    page_icon="",
    layout="wide",
)
inject_css()

# Hide Streamlit's toolbar and default sidebar nav; force custom sidebar visible
st.markdown("""
<style>
[data-testid="stToolbar"]    { display: none !important; }
[data-testid="stSidebarNav"] { display: none !important; }
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div:first-child {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Load data from Supabase (once per session) ───────────────────────────────
def _init_state() -> None:
    if st.session_state.get("data_loaded"):
        return
    meetings, departments, history_records = load_all()
    st.session_state.meetings          = meetings
    st.session_state.departments       = departments
    st.session_state.history_records   = history_records
    st.session_state.current_page      = st.session_state.get("current_page", "Dashboard")
    st.session_state.chat_history      = []
    st.session_state.data_loaded       = True

_init_state()

# ── Sidebar ───────────────────────────────────────────────────────────────────
sidebar.render()

# ── Page routing ──────────────────────────────────────────────────────────────
PAGES = {
    "Dashboard":    dashboard.render,
    "Capture":      capture.render,
    "Tracker":      tracker.render,
    "History":      history.render,
    "People":       people.render,
    "Companies":    companies.render,
    "Stakeholders": stakeholders.render,
    "Analytics":    analytics.render,
}

current     = st.session_state.get("current_page", "Dashboard")
render_page = PAGES.get(current, dashboard.render)
render_page()
