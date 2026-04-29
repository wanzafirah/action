"""Calendar widget — interactive button grid with coloured day cells.

Each day is a Streamlit button. Meeting days are blue, deadline days are yellow.
Clicking a highlighted date shows the detail panel inline below the calendar.
"""
from datetime import date
import calendar as _cal
import json

import streamlit as st
import streamlit.components.v1 as components

from utils.formatters import (
    get_actions_due_on_date,
    get_meeting_conducted_days,
    get_meetings_on_date,
    get_pending_deadline_days,
)
from utils.helpers import normalize_status, normalize_value


# ── Sizing CSS (applied once) ─────────────────────────────────────────────────
_SIZE_CSS = """
<style>
/* Remove column padding so cells are tight */
div[data-testid="stHorizontalBlock"] {
    gap: 2px !important;
}
div[data-testid="stColumn"] {
    padding: 0 1px !important;
    min-width: 0 !important;
}
/* Small, square, non-wrapping buttons */
div[data-testid="stColumn"] button {
    padding: 0.15rem 0.05rem !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    min-height: 1.9rem !important;
    max-height: 1.9rem !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    border-radius: 7px !important;
    line-height: 1 !important;
    width: 100% !important;
}
</style>
"""


def _inject_colors(conducted: set, pending: set, selected_day: int) -> None:
    """Inject JS to colour calendar day buttons after Streamlit renders them.

    Uses window.parent to reach across the component iframe boundary.
    Matches buttons by their text content (single or double digit day numbers).
    """
    meeting_js  = json.dumps(sorted(conducted))
    deadline_js = json.dumps(sorted(pending))

    js = f"""
    <script>
    (function() {{
        var MEETING  = {meeting_js};
        var DEADLINE = {deadline_js};
        var SELECTED = {selected_day};

        function applyColors() {{
            try {{
                var doc = window.parent.document;
                var marker = doc.getElementById('cal-color-marker');
                if (!marker) return;

                // Walk up to the calendar container, then find all buttons inside it
                var container = marker.closest('section') || doc.body;
                var buttons = container.querySelectorAll('button');

                buttons.forEach(function(btn) {{
                    var txt = (btn.innerText || btn.textContent || '').trim();
                    if (!/^\\d{{1,2}}$/.test(txt)) return;
                    var day = parseInt(txt, 10);
                    if (day < 1 || day > 31) return;

                    var isM = MEETING.indexOf(day)  !== -1;
                    var isD = DEADLINE.indexOf(day) !== -1;
                    var isSel = (day === SELECTED);

                    if (isSel) {{
                        btn.style.setProperty('background', '#1e3a5f', 'important');
                        btn.style.setProperty('color',      '#ffffff', 'important');
                        btn.style.setProperty('border',     '2px solid #1e3a5f', 'important');
                    }} else if (isM && isD) {{
                        btn.style.setProperty('background', '#dbeafe', 'important');
                        btn.style.setProperty('color',      '#1e40af', 'important');
                        btn.style.setProperty('border',     '2px solid #6366f1', 'important');
                    }} else if (isM) {{
                        btn.style.setProperty('background', '#dbeafe', 'important');
                        btn.style.setProperty('color',      '#1e40af', 'important');
                        btn.style.setProperty('border',     '2px solid #3b82f6', 'important');
                    }} else if (isD) {{
                        btn.style.setProperty('background', '#fef3c7', 'important');
                        btn.style.setProperty('color',      '#92400e', 'important');
                        btn.style.setProperty('border',     '2px solid #f59e0b', 'important');
                    }} else {{
                        btn.style.setProperty('background', 'transparent', 'important');
                        btn.style.setProperty('color',      '#374151',     'important');
                        btn.style.setProperty('border',     '1px solid #e2e8f0', 'important');
                    }}
                }});
            }} catch(e) {{}}
        }}

        // Run shortly after Streamlit finishes rendering
        setTimeout(applyColors, 150);
        setTimeout(applyColors, 500);
    }})();
    </script>
    """
    components.html(js, height=0)


def render(meetings: list) -> None:
    today = date.today()
    year  = st.session_state.get("calendar_year",  today.year)
    month = st.session_state.get("calendar_month", today.month)

    # ── Month navigation ──────────────────────────────────────────────────────
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
    selected_day = int(selected.split("-")[2]) if selected else -1

    # ── CSS sizing ────────────────────────────────────────────────────────────
    st.markdown(_SIZE_CSS, unsafe_allow_html=True)

    # ── Day-of-week header ────────────────────────────────────────────────────
    hcols = st.columns(7)
    for col, lbl in zip(hcols, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        col.markdown(
            f"<div style='text-align:center;font-size:0.7rem;font-weight:700;"
            f"color:#6e7f96;padding:0.15rem 0'>{lbl}</div>",
            unsafe_allow_html=True,
        )

    # ── Week rows ─────────────────────────────────────────────────────────────
    cal = _cal.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    for week_idx, week in enumerate(weeks):
        wcols = st.columns(7)
        for col_idx, (col, day_num) in enumerate(zip(wcols, week)):
            with col:
                label = " " if day_num == 0 else str(day_num)
                clicked = st.button(
                    label,
                    key=f"cal_day_{year}_{month}_{week_idx}_{col_idx}",
                    use_container_width=True,
                )
                if clicked and day_num != 0:
                    date_iso = date(year, month, day_num).isoformat()
                    st.session_state.cal_selected = (
                        None if selected == date_iso else date_iso
                    )
                    st.rerun()

    # ── Legend ────────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='display:flex;gap:1rem;margin-top:0.3rem;font-size:0.72rem;color:#6e7f96'>"
        "<span><span style='display:inline-block;width:10px;height:10px;border-radius:3px;"
        "background:#dbeafe;border:1px solid #3b82f6;margin-right:3px'></span>Meeting held</span>"
        "<span><span style='display:inline-block;width:10px;height:10px;border-radius:3px;"
        "background:#fef3c7;border:1px solid #f59e0b;margin-right:3px'></span>Action deadline</span>"
        "</div>"
        # Marker used by the JS colour injector to find the calendar's section
        "<span id='cal-color-marker' style='display:none'></span>",
        unsafe_allow_html=True,
    )

    # ── Inject colour JS ──────────────────────────────────────────────────────
    _inject_colors(conducted, pending, selected_day)

    # ── Detail panel ──────────────────────────────────────────────────────────
    selected = st.session_state.get("cal_selected")
    if not selected:
        return

    sel_day = int(selected.split("-")[2])
    is_m = sel_day in conducted
    is_d = sel_day in pending

    if not (is_m or is_d):
        return

    st.markdown(
        f"<div style='margin-top:0.6rem;font-weight:800;font-size:0.95rem;"
        f"color:var(--brand)'>{selected}</div>",
        unsafe_allow_html=True,
    )

    if is_m:
        mtgs = get_meetings_on_date(meetings, selected)
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#1e40af;"
            "margin:0.3rem 0 0.2rem'>Meetings held</div>",
            unsafe_allow_html=True,
        )
        for m in mtgs:
            title = normalize_value(m.get("title"), "Untitled")
            dept  = normalize_value(m.get("deptName") or m.get("department"), "")
            meta  = f" · {dept}" if dept else ""
            st.markdown(
                f"<div style='background:#eff6ff;border:1px solid #bfdbfe;"
                f"border-radius:8px;padding:0.35rem 0.6rem;margin-bottom:0.2rem;"
                f"font-size:0.84rem'><strong>{title}</strong>{meta}</div>",
                unsafe_allow_html=True,
            )

    if is_d:
        actions = get_actions_due_on_date(meetings, selected)
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#92400e;"
            "margin:0.3rem 0 0.2rem'>Tasks due</div>",
            unsafe_allow_html=True,
        )
        for a in actions:
            text   = normalize_value(a.get("text"), "Untitled task")
            owner  = normalize_value(a.get("owner"), "Not stated")
            status = normalize_status(a)
            mtitle = a.get("_meeting_title", "")
            st.markdown(
                f"<div style='background:#fffbeb;border:1px solid #fcd34d;"
                f"border-radius:8px;padding:0.35rem 0.6rem;margin-bottom:0.2rem;"
                f"font-size:0.84rem'>"
                f"<strong>{text}</strong><br>"
                f"<span style='color:#6e7f96;font-size:0.77rem'>"
                f"{mtitle} · {owner} · {status}</span></div>",
                unsafe_allow_html=True,
            )
