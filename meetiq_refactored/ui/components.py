"""Reusable UI components.

Each function renders a self-contained widget. No page-level state.
"""
from datetime import date, datetime

import streamlit as st

from config.constants import STATUS_CFG, STATUSES
from utils.formatters import render_chat_bubble_html
from utils.helpers import (
    join_list,
    normalize_status,
    normalize_value,
    pill,
    pretty_deadline,
)


# ------------------------------------------------------------------
# KPI card
# ------------------------------------------------------------------
def kpi_card(title: str, value: str, subtitle: str, accent: str = "#0f766e") -> None:
    st.markdown(
        f"""
        <div class='kpi-card'>
            <div class='kpi-label'>{title}</div>
            <div class='kpi-value' style='color:{accent}'>{value}</div>
            <div class='kpi-subtitle'>{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_wide(label: str, value: str) -> None:
    """Full-width hero KPI card used at the top of the dashboard."""
    st.markdown(
        f"""
        <div class='kpi-wide'>
            <div class='kpi-wide-label'>{label}</div>
            <div class='kpi-wide-value'>{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def completion_ring(percent: int) -> None:
    safe = max(0, min(int(percent), 100))
    st.markdown(
        f"""
        <div class='completion-card'>
            <div class='kpi-label'>Completion</div>
            <div class='completion-wrap'>
                <div class='completion-ring' style='--pct:{safe};'>
                    <div class='completion-inner'>{safe}%</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------
# Action card
# ------------------------------------------------------------------
def action_card(action: dict, editable: bool = False, persist_callback=None) -> None:
    """Render a single action item. When editable, show status + deadline controls."""
    status = normalize_status(action)
    cfg = STATUS_CFG.get(status, STATUS_CFG["Pending"])
    owner = normalize_value(action.get("owner"), "Not stated")
    department = normalize_value(action.get("department") or action.get("company"), "Not stated")
    suggestion = action.get("suggestion", "")

    st.markdown(
        f"""
        <div class='action-card'>
            <div class='action-top'>
                <div class='action-title'>{normalize_value(action.get('text'), 'Untitled action')}</div>
                {pill(status, cfg['color'], cfg['bg'])}
            </div>
            <div class='action-meta'>
                Assignee: {owner} &nbsp;|&nbsp; Department: {department} &nbsp;|&nbsp;
                Deadline: {pretty_deadline(normalize_value(action.get('deadline'), 'None'))}
            </div>
            <div class='action-subtle'>{normalize_value(suggestion, 'No next-step suggestion generated.')}</div>
        </div>
        """,
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
        index=0 if deadline_value in ("", "None") else 1,
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
    """Render the executive brief produced by run_pipeline()."""
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
        f"""
        <div class='hero-panel'>
            <div class='hero-badge'>Executive Meeting Brief</div>
            <h2>{title}</h2>
            <p>{summary}</p>
            <div class='hero-grid'>
                <div><strong>Objective</strong><br>{objective}</div>
                <div><strong>Follow-up</strong><br>{follow_up}</div>
            </div>
        </div>
        """,
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


def upcoming_task_card(meeting: dict) -> None:
    """Render a full meeting card with its pending action items.

    Matches the Upcoming Tasks design: report-by header + date pill,
    activity id line, summary paragraph, then every action item below.
    """
    report_by = normalize_value(meeting.get("user_id") or meeting.get("updated_by"), "Not stated")
    meeting_date = normalize_value(meeting.get("date"), "TBD")
    activity_id = normalize_value(meeting.get("activityId") or meeting.get("meetingID"), "No ID")
    department = normalize_value(
        meeting.get("deptName") or meeting.get("department"), "No group"
    )
    summary = normalize_value(meeting.get("summary") or meeting.get("recaps"), "No summary yet.")
    title = normalize_value(meeting.get("title"), "Untitled meeting")

    st.markdown(
        f"""
        <div class='upcoming-card'>
            <div class='upcoming-header'>
                <div>
                    <div class='upcoming-report-by'>Report by: {report_by}</div>
                    <div class='upcoming-meta'>{activity_id} | {department}</div>
                </div>
                <div class='upcoming-date'>{meeting_date}</div>
            </div>
            <div style='font-weight:700;color:var(--text);margin-bottom:0.4rem'>{title}</div>
            <p class='upcoming-summary'><strong>Summary:</strong> {summary}</p>
            <div class='upcoming-section-title'>Action Items</div>
        </div>
        """,
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


def _summary_section(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class='summary-section'>
            <div class='summary-section-title'>{title}</div>
            <div class='summary-section-body'>{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
