"""Sidebar navigation."""
import streamlit as st


PAGES = ["Dashboard", "Capture", "Tracker", "History"]


def render() -> None:
    with st.sidebar:
        st.markdown("<div class='sidebar-title'>MeetIQ</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='sidebar-subtitle'>AI meeting insight & action tracker</div>",
            unsafe_allow_html=True,
        )
        for page in PAGES:
            # Highlight the active page via a simple label prefix.
            label = f"● {page}" if st.session_state.get("current_page") == page else page
            if st.button(label, key=f"nav_{page}", use_container_width=True):
                st.session_state.current_page = page
                st.rerun()
