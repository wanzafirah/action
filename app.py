"""MeetIQ — AI meeting insight generator and action tracker.

Entry point: only does Streamlit setup + page routing. All real work lives
inside the page modules under `pages/`.

Run locally:
    streamlit run app.py
"""
import streamlit as st

from core.database import load_all
from ui import sidebar
from views import capture, dashboard, history, tracker
from ui.styles import inject_css


# ------------------------------------------------------------------
# Page setup  (must be the very first Streamlit call)
# ------------------------------------------------------------------
st.set_page_config(page_title="AI Meeting Insight Generator", page_icon="🧠", layout="wide")
inject_css()


# ------------------------------------------------------------------
# Session state (one-time load from Supabase)
# ------------------------------------------------------------------
def _init_state() -> None:
    if st.session_state.get("data_loaded"):
        return
    meetings, departments, history_records = load_all()
    st.session_state.meetings = meetings
    st.session_state.departments = departments
    st.session_state.history_records = history_records
    st.session_state.current_page = st.session_state.get("current_page", "Dashboard")
    st.session_state.chat_history = []
    st.session_state.data_loaded = True


_init_state()


# ------------------------------------------------------------------
# Sidebar + router
# ------------------------------------------------------------------
sidebar.render()

PAGES = {
    "Dashboard": dashboard.render,
    "Capture":   capture.render,
    "Tracker":   tracker.render,
    "History":   history.render,
}

current = st.session_state.get("current_page", "Dashboard")
render_page = PAGES.get(current, dashboard.render)
render_page()
