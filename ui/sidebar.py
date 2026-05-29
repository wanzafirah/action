"""Sidebar navigation."""
import base64
from pathlib import Path

import streamlit as st


# Display label → internal page key mapping
NAV_ITEMS = [
    ("Dashboard",      "Dashboard"),
    ("Analytics",      "Analytics"),
    ("Action Tracker", "Tracker"),
    ("Companies",      "Companies"),
    ("Stakeholders",   "Stakeholders"),
    ("Chat History",   "History"),
]

_LOGO_PATH = Path(__file__).parent.parent / "TC LOGO.png"


def _logo_base64() -> str | None:
    """Return the TC logo as a base64 data URI, or None if file not found."""
    try:
        data = _LOGO_PATH.read_bytes()
        return "data:image/png;base64," + base64.b64encode(data).decode()
    except Exception:
        return None


def render() -> None:
    with st.sidebar:
        # ── TC Logo ──────────────────────────────────────────────────
        logo_src = _logo_base64()
        if logo_src:
            st.markdown(
                f"<div class='sidebar-logo-wrap'>"
                f"<img src='{logo_src}'/>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='sidebar-title'>Promptly</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='sidebar-subtitle'>by zaf ♡</div>",
            unsafe_allow_html=True,
        )
        for display_label, page_key in NAV_ITEMS:
            is_active = st.session_state.get("current_page") == page_key
            label = f"{display_label}" if is_active else display_label
            if st.button(label, key=f"nav_{page_key}", use_container_width=True):
                st.session_state.current_page = page_key
                # Clear dashboard chat session when navigating away
                if page_key != "Dashboard":
                    st.session_state.pop("dashboard_chat_messages", None)
                    st.session_state.pop("dashboard_chat_session_id", None)
                st.rerun()
