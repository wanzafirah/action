"""Sidebar navigation."""
import streamlit as st


# Display label → internal page key mapping
NAV_ITEMS = [
    ("Dashboard",      "Dashboard"),
    ("Action Tracker", "Tracker"),
    ("Capture",        "Capture"),
    ("Chat History",   "History"),
]


def render() -> None:
    with st.sidebar:
        st.markdown(
            "<div class='sidebar-title'>AI-Powered Meeting Insight Generator and Action Tracker</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='sidebar-subtitle'>by zaf ♡</div>",
            unsafe_allow_html=True,
        )
        for display_label, page_key in NAV_ITEMS:
            is_active = st.session_state.get("current_page") == page_key
            label = f"● {display_label}" if is_active else display_label
            if st.button(label, key=f"nav_{page_key}", use_container_width=True):
                st.session_state.current_page = page_key
                # Clear dashboard chat session when navigating away
                if page_key != "Dashboard":
                    st.session_state.pop("dashboard_chat_messages", None)
                    st.session_state.pop("dashboard_chat_session_id", None)
                st.rerun()
