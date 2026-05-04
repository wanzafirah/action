"""Reusable UI components.

Each function renders a self-contained widget. No page-level state.

IMPORTANT: All st.markdown HTML must be passed as a single stripped string.
Multi-line indented f-strings cause Streamlit's markdown parser to treat the
content as a preformatted code block, even with unsafe_allow_html=True.
"""
from datetime import date, datetime

import streamlit as st

from config.constants import DEFAULT_DEPARTMENTS, STATUS_CFG, STATUSES
from utils.tc_staff import get_tc_names
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
    key_prefix: str = "",
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
    _k = f"{key_prefix}{action_id}"

    # ── Edit / Give Idea toggle buttons side by side ─────────────────
    edit_toggle_key = f"edit_open_{_k}"
    idea_key        = f"idea_{_k}"
    idea_open       = f"idea_open_{_k}"

    col_edit_btn, col_idea_btn = st.columns(2)
    with col_edit_btn:
        if st.button(
            "Hide Edit" if st.session_state.get(edit_toggle_key) else "Edit",
            key=f"btn_toggle_edit_{_k}",
            use_container_width=True,
        ):
            st.session_state[edit_toggle_key] = not st.session_state.get(edit_toggle_key, False)
            st.rerun()
    with col_idea_btn:
        if st.button("Give Idea", key=f"btn_idea_{_k}", use_container_width=True):
            if st.session_state.get(idea_open):
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

    # ── Give Idea panel ──────────────────────────────────────────────
    if st.session_state.get(idea_open) and st.session_state.get(idea_key):
        import re as _re
        _raw_idea = st.session_state[idea_key]
        _clean_idea = _re.sub(r"\*\*(.+?)\*\*", r"\1", _raw_idea)
        _clean_idea = _re.sub(r"\*(.+?)\*", r"\1", _clean_idea)

        # Parse effort tags and render as coloured pills
        _EFFORT_STYLES = {
            "<30MIN":    ("< 30 min",   "#dcfce7", "#166534", "#bbf7d0"),
            "<1HOUR":    ("< 1 hour",   "#fef9c3", "#854d0e", "#fde047"),
            "MULTI-DAY": ("Multi-day",  "#fee2e2", "#991b1b", "#fca5a5"),
        }
        _lines = _clean_idea.strip().splitlines()
        _rows_html = ""
        for _line in _lines:
            _line = _line.strip()
            if not _line:
                continue
            # Detect [TAG] at start of line
            _tag_match = _re.match(r"^(\d+\.\s*)?\[?(<30min|<1hour|multi-day)\]?\s*", _line, _re.IGNORECASE)
            if _tag_match:
                _tag = _tag_match.group(2).upper().strip("<>").replace(" ", "-")
                # Normalise to dict keys
                _tag_map = {"30MIN": "<30MIN", "1HOUR": "<1HOUR", "MULTIDAY": "MULTI-DAY", "MULTI-DAY": "MULTI-DAY", "<30MIN": "<30MIN", "<1HOUR": "<1HOUR"}
                _tag = _tag_map.get(_tag, _tag)
                _step_text = _line[_tag_match.end():].strip()
                _label, _bg, _fg, _border = _EFFORT_STYLES.get(_tag, ("", "#f1f5f9", "#334155", "#cbd5e1"))
                _pill_html = (
                    f"<span style='background:{_bg};color:{_fg};border:1px solid {_border};"
                    f"padding:0.15rem 0.5rem;border-radius:999px;font-size:0.72rem;"
                    f"font-weight:700;white-space:nowrap;margin-right:0.4rem'>{_label}</span>"
                )
                _rows_html += (
                    f"<div style='display:flex;align-items:flex-start;gap:0.3rem;"
                    f"margin-bottom:0.45rem'>{_pill_html}"
                    f"<span style='font-size:0.87rem;color:#14532d'>{_step_text}</span></div>"
                )
            else:
                _rows_html += f"<div style='font-size:0.87rem;color:#14532d;margin-bottom:0.35rem'>{_line}</div>"

        st.markdown(
            f"<div style='background:#f0fdf4;border:1px solid #86efac;border-radius:12px;"
            f"padding:0.7rem 0.9rem;margin:0.3rem 0 0.5rem'>"
            f"<div style='font-weight:700;color:#14532d;font-size:0.85rem;"
            f"margin-bottom:0.55rem'>Guidance</div>"
            f"{_rows_html}"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Edit fields — shown only when Edit is toggled on ────────────
    if not st.session_state.get(edit_toggle_key, False):
        return

    # ── Editable task text ───────────────────────────────────────────
    new_text = st.text_input(
        "Task description",
        value=action.get("text", ""),
        key=f"text_{_k}",
        placeholder="Describe the action item…",
    )

    # ── Editable fields (2-column layout) ───────────────────────────
    col_edit1, col_edit2 = st.columns(2)

    with col_edit1:
        current = action.get("status", "Pending")
        new_status = st.selectbox(
            "Status",
            STATUSES,
            index=STATUSES.index(current) if current in STATUSES else 0,
            key=f"status_{_k}",
        )

    with col_edit2:
        _cur_owner_raw = action.get("owner", "")
        if _cur_owner_raw in ("Not stated", "None"):
            _cur_owner_raw = ""
        _cur_owners = [n.strip() for n in _cur_owner_raw.split(",") if n.strip()]
        _tc_names = get_tc_names()
        _extra = [n for n in _cur_owners if n not in _tc_names]
        _owner_opts = _tc_names + _extra
        new_owners = st.multiselect(
            "Assignee",
            options=_owner_opts,
            default=[n for n in _cur_owners if n in _owner_opts],
            key=f"owner_{_k}",
            placeholder="Select one or more assignees…",
        )

    col_edit3, col_edit4 = st.columns(2)

    with col_edit3:
        _cur_dept = action.get("department") or action.get("company") or ""
        if _cur_dept in ("Not stated", "None", "TalentCorp", "Talent Corp", "TC"):
            _cur_dept = ""
        # Build options: blank + all TalentCorp departments + manual entry fallback
        _dept_opts = [""] + DEFAULT_DEPARTMENTS + ["Other (type manually)"]
        _dept_idx = _dept_opts.index(_cur_dept) if _cur_dept in _dept_opts else 0
        _dept_sel = st.selectbox(
            "Department",
            options=_dept_opts,
            index=_dept_idx,
            key=f"dept_sel_{_k}",
        )
        if _dept_sel == "Other (type manually)":
            new_dept = st.text_input(
                "Department (manual)",
                value=_cur_dept if _cur_dept not in _dept_opts else "",
                key=f"dept_{_k}",
                placeholder="Type department name…",
            )
        else:
            new_dept = _dept_sel

    with col_edit4:
        deadline_value = normalize_value(action.get("deadline"), "")
        mode = st.selectbox(
            "Deadline",
            ["No deadline", "Set deadline"],
            index=0 if deadline_value in ("", "None", "Not stated") else 1,
            key=f"dl_mode_{_k}",
        )

    try:
        default_deadline = datetime.strptime(deadline_value, "%Y-%m-%d").date()
    except Exception:
        default_deadline = date.today()
    edited = st.date_input(
        "Deadline date",
        value=default_deadline,
        key=f"dl_{_k}",
        disabled=mode == "No deadline",
        label_visibility="collapsed",
    )
    new_deadline = "None" if mode == "No deadline" else edited.isoformat()

    changed = False
    _new_text_stripped = new_text.strip()
    if _new_text_stripped and _new_text_stripped != normalize_value(action.get("text"), ""):
        action["text"] = _new_text_stripped
        changed = True
    if new_status != current:
        action["status"] = new_status
        changed = True
    if new_deadline != normalize_value(action.get("deadline"), "None"):
        action["deadline"] = new_deadline
        changed = True
    _saved_owner = ", ".join(new_owners) if new_owners else "Not stated"
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

    if not (next_steps or people):
        return

    left, right = st.columns(2)
    with left:
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
