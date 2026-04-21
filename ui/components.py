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
    meeting_title: str = "",
    show_suggestion: bool = False,
) -> None:
    """Render a single action item with smart nudge flags."""
    status = normalize_status(action)
    cfg = STATUS_CFG.get(status, STATUS_CFG["Pending"])
    _raw_owner = normalize_value(action.get("owner"), "")
    _raw_dept  = normalize_value(action.get("department") or action.get("company"), "")
    # If owner looks like an organisation (contains org-like words, or matches the department),
    # treat it as "Not stated" — a person's name should not contain these keywords.
    _org_keywords = ("team", "corp", "sdn", "bhd", "ltd", "inc", "department",
                     "division", "unit", "group", "ministry", "agency", "centre",
                     "center", "office", "bureau", "talentcorp", "mynext")
    _owner_lower = _raw_owner.lower()
    _is_org = (
        not _raw_owner
        or _raw_owner == "Not stated"
        or any(kw in _owner_lower for kw in _org_keywords)
        or _raw_owner.lower() == _raw_dept.lower()
    )
    owner = "Not stated" if _is_org else _raw_owner
    # If department is just the company name (talentcorp / talent corp / tc), show "Not stated"
    _dept_lower = _raw_dept.lower().strip()
    _vague_depts = {"talentcorp", "talent corp", "tc", "talentcorp malaysia", "not stated", "none", ""}
    department = "Not stated" if _dept_lower in _vague_depts else (_raw_dept or "Not stated")
    deadline_display = pretty_deadline(normalize_value(action.get("deadline"), "None"))
    action_text = normalize_value(action.get("text"), "Untitled action")

    # Optional meeting title label above the action
    mtitle_html = ""
    if meeting_title:
        mtitle_html = (f"<div style='font-size:0.74rem;color:var(--text-soft);"
                       f"margin-bottom:0.2rem'>Meeting: {meeting_title}</div>")

    # Build nudge pills HTML
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

    suggestion_html = ""
    if show_suggestion:
        suggestion = normalize_value(action.get("suggestion"), "")
        if suggestion and suggestion != "No next-step suggestion generated.":
            suggestion_html = f"<div class='action-subtle'>{suggestion}</div>"

    st.markdown(
        f"<div class='action-card'>"
        f"{mtitle_html}"
        f"<div class='action-top'>"
        f"<div class='action-title'>{action_text}</div>"
        f"{pill(status, cfg['color'], cfg['bg'])}"
        f"</div>"
        f"{nudge_html}"
        f"<div class='action-meta'>"
        f"Assignee: {owner} &nbsp;|&nbsp; Department: {department} &nbsp;|&nbsp; Deadline: {deadline_display}"
        f"</div>"
        f"{suggestion_html}"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not editable:
        return

    action_id = action.get("id", "")

    # ── Give Idea button (AI project manager guidance) ───────────────
    idea_key  = f"idea_{action_id}"
    idea_open = f"idea_open_{action_id}"
    if st.button("Give Idea", key=f"btn_idea_{action_id}", use_container_width=False):
        if st.session_state.get(idea_open):
            # Toggle off
            st.session_state.pop(idea_key, None)
            st.session_state[idea_open] = False
        else:
            with st.spinner("Thinking…"):
                try:
                    from core.pipeline import get_action_idea
                    st.session_state[idea_key] = get_action_idea(action)
                    st.session_state[idea_open] = True
                except Exception as exc:
                    st.session_state[idea_key] = f"Could not generate ideas: {exc}"
                    st.session_state[idea_open] = True
            st.rerun()

    if st.session_state.get(idea_open) and st.session_state.get(idea_key):
        import re as _re
        _raw_idea = st.session_state[idea_key]
        # Strip **bold** markdown symbols
        _clean_idea = _re.sub(r"\*\*(.+?)\*\*", r"\1", _raw_idea)
        _clean_idea = _re.sub(r"\*(.+?)\*", r"\1", _clean_idea)
        st.markdown(
            f"<div style='background:#f0fdf4;border:1px solid #86efac;border-radius:12px;"
            f"padding:0.7rem 0.9rem;margin:0.3rem 0 0.5rem;font-size:0.88rem;color:#14532d'>"
            f"<strong>Guidance</strong><br><br>"
            f"{_clean_idea.replace(chr(10), '<br>')}"
            f"</div>",
            unsafe_allow_html=True,
        )
    # ── Editable fields (2-column layout) ───────────────────────────
    col_edit1, col_edit2 = st.columns(2)

    with col_edit1:
        current = action.get("status", "Pending")
        new_status = st.selectbox(
            "Status",
            STATUSES,
            index=STATUSES.index(current) if current in STATUSES else 0,
            key=f"status_{action_id}",
        )

    with col_edit2:
        _cur_owner = action.get("owner", "")
        if _cur_owner in ("Not stated", "None"):
            _cur_owner = ""
        new_owner = st.text_input(
            "Assignee",
            value=_cur_owner,
            key=f"owner_{action_id}",
            placeholder="Person's name",
        )

    col_edit3, col_edit4 = st.columns(2)

    with col_edit3:
        _cur_dept = action.get("department") or action.get("company") or ""
        if _cur_dept in ("Not stated", "None", "TalentCorp", "Talent Corp", "TC"):
            _cur_dept = ""
        new_dept = st.text_input(
            "Department",
            value=_cur_dept,
            key=f"dept_{action_id}",
            placeholder="e.g. Group Digital",
        )

    with col_edit4:
        deadline_value = normalize_value(action.get("deadline"), "")
        mode = st.selectbox(
            "Deadline",
            ["No deadline", "Set deadline"],
            index=0 if deadline_value in ("", "None", "Not stated") else 1,
            key=f"dl_mode_{action_id}",
        )

    try:
        default_deadline = datetime.strptime(deadline_value, "%Y-%m-%d").date()
    except Exception:
        default_deadline = date.today()
    edited = st.date_input(
        "Deadline date",
        value=default_deadline,
        key=f"dl_{action_id}",
        disabled=mode == "No deadline",
        label_visibility="collapsed",
    )
    new_deadline = "None" if mode == "No deadline" else edited.isoformat()

    changed = False
    if new_status != current:
        action["status"] = new_status
        changed = True
    if new_deadline != normalize_value(action.get("deadline"), "None"):
        action["deadline"] = new_deadline
        changed = True
    _saved_owner = new_owner.strip() or "Not stated"
    if _saved_owner != normalize_value(action.get("owner"), "Not stated"):
        action["owner"] = _saved_owner
        changed = True
    _saved_dept = new_dept.strip() or "Not stated"
    if _saved_dept != normalize_value(action.get("department") or action.get("company"), "Not stated"):
        action["department"] = _saved_dept
        action["company"]    = _saved_dept
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
