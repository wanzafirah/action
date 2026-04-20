"""Calendar widget (month navigation + clickable dates)."""
from datetime import date

import streamlit as st

from utils.formatters import build_calendar_html


def render(meetings: list) -> None:
    """Render the dashboard calendar with month navigation."""
    today = date.today()
    year = st.session_state.get("calendar_year", today.year)
    month = st.session_state.get("calendar_month", today.month)

    col_prev, col_title, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀", key="cal_prev", use_container_width=True):
            month -= 1
            if month < 1:
                month, year = 12, year - 1
            st.session_state.calendar_month = month
            st.session_state.calendar_year = year
            st.rerun()
    with col_title:
        st.markdown(
            f"<div style='text-align:center;font-weight:800;font-size:1.1rem'>"
            f"{date(year, month, 1).strftime('%B %Y')}</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("▶", key="cal_next", use_container_width=True):
            month += 1
            if month > 12:
                month, year = 1, year + 1
            st.session_state.calendar_month = month
            st.session_state.calendar_year = year
            st.rerun()

    st.markdown(build_calendar_html(meetings, year, month), unsafe_allow_html=True)
