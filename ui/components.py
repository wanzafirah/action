"""Reusable UI components.

Each function renders a self-contained widget. No page-level state.

IMPORTANT: All st.markdown HTML must be passed as a single stripped string.
Multi-line indented f-strings cause Streamlit's markdown parser to treat the
content as a preformatted code block, even with unsafe_allow_html=True.
"""
from datetime import date, datetime

import streamlit as st

from config.constants import STATUS_CFG, STATUSES
from utils.formatters import render_chat_bubble_html
from utils.helpers import (
    join_list,
    normalize_status,
    normalize_value,
    nudge_flags,
    pill,
    pretty_deadline,
)


# ------------------------------------------------------------------
# KPI card
# ------------------------------------------------------------------
def kpi_card(title: str, value: str, subtitle: str, accent: str = "#0f766e") -> None:
    st.markdown(
        f"<div class='kpi-card'>"
        f"<div class='kpi-label'>{title}</div>"
        f"<div class='kpi-value' style='color:{accent}'>{value}</div>"
        f"<div class='kpi-subtitle'>{subtitle}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def kpi_wide(label: str, value: str) -> None:
    st.markdown(
        f"<div class='kpi-wide'>"
        f"<div class='kpi-wide-label'>{label}</div>"
        f"<div class='kpi-wide-value'>{value}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def completion_ring(percent: int) -> None:
    safe = max(0, min(int(percent), 100))
    st.markdown(
        f"<div class='completion-card'>"
        f"<div class='kpi-label'>Completion</div>"
        f"<div class='completion-wrap'>"
        f"<div class='completion-ring' style='--pct:{safe};'>"
        f"<div class='completion-inner'>{safe}%</div>"
        f"</div></div></div>",
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------
# Action card
# ------------------------------------------------------------------
def action_card(
    action: dict,
    editable: bool = False,
    persist_callback=None,
    meeting_date: str = "",
) -> None:
    """Render a single action item with smart nudge flags."""
    status = normalize_status(action)
    cfg = STATUS_CFG.get(status, STATUS_CFG["Pending"])
    owner = normalize_value(action.get("owner"), "Not stated")
    department = normalize_value(action.get("department") or action.get("company"), "Not stated")
    suggestion = normalize_value(action.get("suggestion"), "No next-step suggestion generated.")
    deadline_display = pretty_deadline(normalize_value(action.get("deadline"), "None"))
    action_text = normalize_value(action.get("text"), "Untitled action")

    # Build nudge pills HTML (single line, no indentation)
    nudge_html = ""
    flags = nudge_flags(action, meeting_date)
    if flags:
        pills = ""
        for f in flags:
            if "overdue" in f.lower():
                cls = "nudge-overdue"
            elif "act soon" in f.lower() or "today" in f.lower():
                cls = "nudge-urgent"
            elif "due in" in f.lower():
                cls = "nudge-soon"
            elif "needs attention" in f.lower():
                cls = "nudge-critical"
            else:
                cls = "nudge-stale"
            pills += f"<span class='nudge-pill {cls}'>{f}</span>"
        nudge_html = f"<div class='nudge-bar'>{pills}</div>"

    st.markdown(
        f"<div class='action-card'>"
        f"<div class='action-top'>"
        f"<div class='action-title'>{action_text}</div>"
        f"{pill(status, cfg['color'], cfg['bg'])}"
        f"</div>"
        f"{nudge_html}"
        f"<div class='action-meta'>"
        f"Assignee: {owner} &nbsp;|&nbsp; Department: {department} &nbsp;|&nbsp; Deadline: {deadline_display}"
        f"</div>"
        f"<div class='action-subtle'>{suggestion}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not editable:
        return

    action_id = action.get("id", "")
    current = action.get("status", "Pending")
    new_status = st.selectbox(
        "Update status",
        STATUSES,
        index=STATUSES.index(current) if current in STATUSES else 0,
        key=f"status_{action_id}",
        label_visibility="collapsed",
    )

    deadline_value = normalize_value(action.get("deadline"), "")
    mode = st.selectbox(
        "Deadline mode",
        ["No deadline", "Set deadline"],
        index=0 if deadline_value in ("", "None", "Not stated") else 1,
        key=f"dl_mode_{action_id}",
    )
    try:
        default_deadline = datetime.strptime(deadline_value, "%Y-%m-%d").date()
    except Exception:
        default_deadline = date.today()
    edited = st.date_input(
        "Deadline",
        value=default_deadline,
        key=f"dl_{action_id}",
        disabled=mode == "No deadline",
    )
    new_deadline = "None" if mode == "No deadline" else edited.isoformat()

    changed = False
    if new_status != current:
        action["status"] = new_status
        changed = True
    if new_deadline != normalize_value(action.get("deadline"), "None"):
        action["deadline"] = new_deadline
        changed = True
    if changed and persist_callback:
        persist_callback()


# ------------------------------------------------------------------
# Chat bubble
# ------------------------------------------------------------------
def chat_bubble(role: str, text: str) -> None:
    st.markdown(render_chat_bubble_html(role, text), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Summary panel (shown after the pipeline runs)
# ------------------------------------------------------------------
def summary_panel(result: dict) -> None:
    title = normalize_value(result.get("title"), "Untitled meeting")
    summary = normalize_value(result.get("summary"), "No summary generated.")
    objective = normalize_value(result.get("objective"), "Not provided")
    follow_up = "Yes" if result.get("follow_up") else "No"

    key_points = result.get("discussion_points") or []
    next_steps = [
        normalize_value(a.get("text"), "")
        for a in result.get("action_items", []) if isinstance(a, dict)
    ]
    next_steps = [s for s in next_steps if s]
    people = [
        normalize_value(p, "")
        for p in result.get("nlp_pipeline", {}).get("named_entities", {}).get("persons", [])
    ]
    people = [p for p in people if p]

    st.markdown(
        f"<div class='hero-panel'>"
        f"<div class='hero-badge'>Executive Meeting Brief</div>"
        f"<h2>{title}</h2>"
        f"<p>{summary}</p>"
        f"<div class='hero-grid'>"
        f"<div><strong>Objective</strong><br>{objective}</div>"
        f"<div><strong>Follow-up needed</strong><br>{follow_up}</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    if not (key_points or next_steps or people):
        return

    left, mid, right = st.columns(3)
    with left:
        _summary_section("Key Points Discussed", join_list(key_points))
    with mid:
        _summary_section("Next Steps", join_list(next_steps))
    with right:
        _summary_section("People Involved", join_list(people))


def _summary_section(title: str, body: str) -> None:
    st.markdown(
        f"<div class='summary-section'>"
        f"<div class='summary-section-title'>{title}</div>"
        f"<div class='summary-section-body'>{body}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------
# Upcoming task card (kept for backward compat; dashboard uses expanders)
# ------------------------------------------------------------------
def upcoming_task_card(meeting: dict) -> None:
    report_by = normalize_value(meeting.get("user_id") or meeting.get("updated_by"), "Not stated")
    meeting_date = normalize_value(meeting.get("date"), "TBD")
    activity_id = normalize_value(meeting.get("activityId") or meeting.get("meetingID"), "No ID")
    department = normalize_value(meeting.get("deptName") or meeting.get("department"), "No group")
    summary = normalize_value(meeting.get("summary") or meeting.get("recaps"), "No summary yet.")
    title = normalize_value(meeting.get("title"), "Untitled meeting")

    st.markdown(
        f"<div class='upcoming-card'>"
        f"<div class='upcoming-header'>"
        f"<div>"
        f"<div class='upcoming-report-by'>Report by: {report_by}</div>"
        f"<div class='upcoming-meta'>{activity_id} | {department}</div>"
        f"</div>"
        f"<div class='upcoming-date'>{meeting_date}</div>"
        f"</div>"
        f"<div style='font-weight:700;color:var(--text);margin-bottom:0.4rem'>{title}</div>"
        f"<p class='upcoming-summary'><strong>Summary:</strong> {summary}</p>"
        f"<div class='upcoming-section-title'>Action Items</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    actions = [
        a for a in (meeting.get("actions") or [])
        if normalize_status(a) in {"Pending", "In Progress", "Overdue"}
    ]
    if not actions:
        st.caption("No pending action items for this meeting.")
        return
    for a in actions:
        action_card(a)
