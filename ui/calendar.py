"""Calendar widget — interactive button grid.

Each day is a real Streamlit button. Clicking a highlighted date
(blue = meeting held, yellow = deadline) shows the detail panel inline.
"""
from datetime import date
import calendar as _cal

import streamlit as st

from utils.formatters import (
    get_actions_due_on_date,
    get_meeting_conducted_days,
    get_meetings_on_date,
    get_pending_deadline_days,
)
# build_calendar_html no longer used — calendar is now a native Streamlit button grid
from utils.helpers import normalize_status, normalize_value


_CSS = """
<style>
/* ── Calendar grid wrapper ───────────────────────────── */
.cal-wrap { margin-bottom: 0.25rem; }

/* Remove ALL padding/gap between calendar columns */
.cal-wrap div[data-testid="stHorizontalBlock"] {
    gap: 3px !important;
}
.cal-wrap div[data-testid="stColumn"] {
    padding: 0 !important;
    min-width: 0 !important;
}

/* ── Every day button ────────────────────────────────── */
.cal-wrap button[kind="secondary"],
.cal-wrap button[kind="primary"] {
    width: 100% !important;
    padding: 0.3rem 0.1rem !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    min-height: 2.2rem !important;
    border-radius: 8px !important;
    line-height: 1 !important;
}

/* Empty / normal day — invisible */
.cal-wrap .cal-empty button,
.cal-wrap .cal-normal button {
    background: transparent !important;
    border: 1px solid #e2e8f0 !important;
    color: #374151 !important;
    box-shadow: none !important;
}
.cal-wrap .cal-empty button { visibility: hidden !important; }

/* Today — ring */
.cal-wrap .cal-today button {
    background: transparent !important;
    border: 2px solid #6366f1 !important;
    color: #6366f1 !important;
    font-weight: 800 !important;
}

/* Meeting held — blue fill */
.cal-wrap .cal-meeting button {
    background: #dbeafe !important;
    border: 2px solid #3b82f6 !important;
    color: #1e40af !important;
    font-weight: 800 !important;
}

/* Deadline — yellow fill */
.cal-wrap .cal-deadline button {
    background: #fef3c7 !important;
    border: 2px solid #f59e0b !important;
    color: #92400e !important;
    font-weight: 800 !important;
}

/* Both meeting + deadline */
.cal-wrap .cal-both button {
    background: linear-gradient(135deg, #dbeafe 50%, #fef3c7 50%) !important;
    border: 2px solid #6366f1 !important;
    color: #1e3a8a !important;
    font-weight: 800 !important;
}

/* Selected — dark fill */
.cal-wrap .cal-selected button,
.cal-wrap .cal-selected button[kind="primary"] {
    background: #1e3a5f !important;
    border: 2px solid #1e3a5f !important;
    color: #ffffff !important;
    font-weight: 800 !important;
}
</style>
"""


def render(meetings: list) -> None:
    today = date.today()
    year  = st.session_state.get("calendar_year",  today.year)
    month = st.session_state.get("calendar_month", today.month)

    # ── Month navigation ──────────────────────────────────────────
    col_prev, col_title, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("◀", key="cal_prev", use_container_width=True):
            month -= 1
            if month < 1:
                month, year = 12, year - 1
            st.session_state.calendar_month = month
            st.session_state.calendar_year  = year
            st.session_state.cal_selected   = None
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
            st.session_state.calendar_year  = year
            st.session_state.cal_selected   = None
            st.rerun()

    # Pre-compute highlighted days
    pending   = get_pending_deadline_days(meetings, year, month)
    conducted = get_meeting_conducted_days(meetings, year, month)
    selected  = st.session_state.get("cal_selected")

    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Day-of-week header ────────────────────────────────────────
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hcols = st.columns(7)
    for col, lbl in zip(hcols, day_labels):
        col.markdown(
            f"<div style='text-align:center;font-size:0.72rem;font-weight:700;"
            f"color:#6e7f96;padding:0.2rem 0'>{lbl}</div>",
            unsafe_allow_html=True,
        )

    # ── Week rows ─────────────────────────────────────────────────
    cal = _cal.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    st.markdown("<div class='cal-wrap'>", unsafe_allow_html=True)
    for week in weeks:
        wcols = st.columns(7)
        for col, day_num in zip(wcols, week):
            if day_num == 0:
                css_class = "cal-empty"
                label = " "
            else:
                date_iso = date(year, month, day_num).isoformat()
                is_m  = day_num in conducted
                is_d  = day_num in pending
                is_today = (day_num == today.day and month == today.month and year == today.year)
                is_sel = (selected == date_iso)

                if is_sel:
                    css_class = "cal-selected"
                elif is_m and is_d:
                    css_class = "cal-both"
                elif is_m:
                    css_class = "cal-meeting"
                elif is_d:
                    css_class = "cal-deadline"
                elif is_today:
                    css_class = "cal-today"
                else:
                    css_class = "cal-normal"

                label = str(day_num)

            with col:
                st.markdown(f"<div class='{css_class}'>", unsafe_allow_html=True)
                clicked = st.button(
                    label,
                    key=f"cal_day_{year}_{month}_{day_num}",
                    use_container_width=True,
                )
                st.markdown("</div>", unsafe_allow_html=True)

                if clicked and day_num != 0:
                    date_iso = date(year, month, day_num).isoformat()
                    # Toggle: click again to deselect
                    st.session_state.cal_selected = None if selected == date_iso else date_iso
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Legend ────────────────────────────────────────────────────
    st.markdown(
        "<div style='display:flex;gap:1rem;margin-top:0.4rem;font-size:0.74rem;color:#6e7f96'>"
        "<span><span style='display:inline-block;width:10px;height:10px;border-radius:3px;"
        "background:#dbeafe;border:1px solid #3b82f6;margin-right:3px'></span>Meeting held</span>"
        "<span><span style='display:inline-block;width:10px;height:10px;border-radius:3px;"
        "background:#fef3c7;border:1px solid #f59e0b;margin-right:3px'></span>Action deadline</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Detail panel ──────────────────────────────────────────────
    selected = st.session_state.get("cal_selected")
    if not selected:
        return

    sel_day = int(selected.split("-")[2])
    is_m = sel_day in conducted
    is_d = sel_day in pending

    if not (is_m or is_d):
        return

    st.markdown(
        f"<div style='margin-top:0.7rem;font-weight:800;font-size:0.95rem;"
        f"color:var(--brand)'>{selected}</div>",
        unsafe_allow_html=True,
    )

    if is_m:
        mtgs = get_meetings_on_date(meetings, selected)
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#1e40af;"
            "margin:0.35rem 0 0.2rem'>Meetings held</div>",
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

    if is_d:
        actions = get_actions_due_on_date(meetings, selected)
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#92400e;"
            "margin:0.35rem 0 0.2rem'>Tasks due</div>",
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
