"""Calendar widget — visual HTML grid + interactive date detail panel.

Clicking a blue (meeting) or yellow (deadline) day button below the calendar
reveals the meetings held or tasks due on that date.
"""
from datetime import date

import streamlit as st

from utils.formatters import (
    build_calendar_html,
    get_actions_due_on_date,
    get_meeting_conducted_days,
    get_meetings_on_date,
    get_pending_deadline_days,
)
from utils.helpers import normalize_status, normalize_value, pretty_deadline


def render(meetings: list) -> None:
    today = date.today()
    year  = st.session_state.get("calendar_year",  today.year)
    month = st.session_state.get("calendar_month", today.month)

    # ── Month navigation ─────────────────────────────────────────────
    col_prev, col_title, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀", key="cal_prev", use_container_width=True):
            month -= 1
            if month < 1:
                month, year = 12, year - 1
            st.session_state.calendar_month  = month
            st.session_state.calendar_year   = year
            st.session_state.cal_selected    = None   # clear selection on nav
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
            st.session_state.calendar_month  = month
            st.session_state.calendar_year   = year
            st.session_state.cal_selected    = None
            st.rerun()

    # ── Visual HTML grid (blue = meeting held, yellow = deadline) ────
    st.markdown(build_calendar_html(meetings, year, month), unsafe_allow_html=True)

    # ── Interactive day buttons (highlighted dates only) ─────────────
    pending   = get_pending_deadline_days(meetings, year, month)
    conducted = get_meeting_conducted_days(meetings, year, month)
    all_highlighted = sorted((conducted | pending))

    if not all_highlighted:
        return

    st.markdown(
        "<div style='font-size:0.78rem;color:#6e7f96;margin-top:0.5rem;margin-bottom:0.3rem'>"
        "Click a date below to see details:</div>",
        unsafe_allow_html=True,
    )

    # Render one small button per highlighted day in a flowing grid
    MAX_COLS = 7
    days_list = all_highlighted
    rows = [days_list[i:i+MAX_COLS] for i in range(0, len(days_list), MAX_COLS)]

    for row in rows:
        cols = st.columns(MAX_COLS)
        for i, day_num in enumerate(row):
            is_m = day_num in conducted
            is_d = day_num in pending
            # Emoji prefix communicates type without needing colour styling
            if is_m and is_d:
                label = f"📅⚡{day_num}"
            elif is_m:
                label = f"📅{day_num}"
            else:
                label = f"⚡{day_num}"

            date_iso = date(year, month, day_num).isoformat()
            selected = st.session_state.get("cal_selected")

            if cols[i].button(
                label,
                key=f"cal_btn_{year}_{month}_{day_num}",
                use_container_width=True,
                type="primary" if selected == date_iso else "secondary",
            ):
                # Toggle: click again to deselect
                if selected == date_iso:
                    st.session_state.cal_selected = None
                else:
                    st.session_state.cal_selected = date_iso
                st.rerun()

    # ── Detail panel ─────────────────────────────────────────────────
    selected = st.session_state.get("cal_selected")
    if not selected:
        return

    sel_day  = int(selected.split("-")[2])
    is_m = sel_day in conducted
    is_d = sel_day in pending

    st.markdown(
        f"<div style='margin-top:0.7rem;font-weight:800;font-size:0.95rem;"
        f"color:var(--brand)'>{selected}</div>",
        unsafe_allow_html=True,
    )

    # Meetings held on this date
    if is_m:
        mtgs = get_meetings_on_date(meetings, selected)
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#1e40af;"
            "margin:0.35rem 0 0.2rem'>📅 Meetings held</div>",
            unsafe_allow_html=True,
        )
        if mtgs:
            for m in mtgs:
                title = normalize_value(m.get("title"), "Untitled")
                dept  = normalize_value(m.get("deptName") or m.get("department"), "")
                meta  = f" · {dept}" if dept else ""
                st.markdown(
                    f"<div style='background:#eff6ff;border:1px solid #bfdbfe;"
                    f"border-radius:8px;padding:0.35rem 0.6rem;margin-bottom:0.25rem;"
                    f"font-size:0.85rem'>"
                    f"<strong>{title}</strong>{meta}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No meeting details found.")

    # Action items due on this date
    if is_d:
        actions = get_actions_due_on_date(meetings, selected)
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#92400e;"
            "margin:0.35rem 0 0.2rem'>⚡ Tasks due</div>",
            unsafe_allow_html=True,
        )
        if actions:
            for a in actions:
                text   = normalize_value(a.get("text"), "Untitled task")
                owner  = normalize_value(a.get("owner"), "Not stated")
                status = normalize_status(a)
                mtitle = a.get("_meeting_title", "")
                st.markdown(
                    f"<div style='background:#fffbeb;border:1px solid #fcd34d;"
                    f"border-radius:8px;padding:0.35rem 0.6rem;margin-bottom:0.25rem;"
                    f"font-size:0.85rem'>"
                    f"<strong>{text}</strong><br>"
                    f"<span style='color:#6e7f96;font-size:0.78rem'>"
                    f"{mtitle} · {owner} · {status}</span></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No tasks found for this date.")
