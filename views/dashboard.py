"""Dashboard page: KPIs, calendar, AI chat, upcoming task cards."""
from datetime import datetime

import streamlit as st

from core.database import save_history_entry
from core.pipeline import chat_with_meetings
from ui import calendar as calendar_widget
from ui.components import (
    completion_ring,
    kpi_card,
    kpi_wide,
)
from utils.formatters import get_digest_items, get_upcoming_meetings
from utils.helpers import (
    normalize_status,
    normalize_value,
    today_str,
    uid,
)


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    # Two-column layout
    main_col, side_col = st.columns([2.2, 1], gap="large")

    with main_col:
        _render_kpis(meetings)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        _render_digest(meetings)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        _render_upcoming(meetings)

    with side_col:
        st.markdown("#### Calendar")
        calendar_widget.render(meetings)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        _render_chatbot(meetings)


# ------------------------------------------------------------------
# KPI section
# ------------------------------------------------------------------
def _render_kpis(meetings: list) -> None:
    total_meetings = len(meetings)
    all_actions = [a for m in meetings for a in (m.get("actions") or [])]
    pending = sum(
        1 for a in all_actions
        if normalize_status(a) in {"Pending", "In Progress", "Overdue"}
    )
    done = sum(1 for a in all_actions if normalize_status(a) == "Done")
    total_actions = len(all_actions)
    completion = int((done / total_actions) * 100) if total_actions else 0

    kpi_wide("Total meetings", str(total_meetings))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Action items", str(total_actions), "Extracted tasks", "#0f766e")
    with c2:
        kpi_card("Pending", str(pending), "Still open", "#b45309")
    with c3:
        kpi_card("Completed", str(done), "Marked done", "#1d4ed8")
    with c4:
        completion_ring(completion)


# ------------------------------------------------------------------
# Daily Digest — smart nudge summary, no email needed
# ------------------------------------------------------------------
def _render_digest(meetings: list) -> None:
    digest = get_digest_items(meetings)
    total_alerts = sum(len(v) for v in digest.values())

    with st.expander(
        f"📋 Today's Action Digest  {'🔴 ' + str(total_alerts) + ' items need attention' if total_alerts else '✅ All clear'}",
        expanded=total_alerts > 0,
    ):
        if total_alerts == 0:
            st.markdown(
                "<div class='digest-empty'>🎉 No urgent items today. Great job keeping up!</div>",
                unsafe_allow_html=True,
            )
            return

        sections = [
            ("overdue",   "🔴",  "red",    "Overdue"),
            ("due_today", "🔔",  "amber",  "Due Today"),
            ("due_3days", "⚡",  "amber",  "Due Within 3 Days"),
            ("due_week",  "🕐",  "blue",   "Due This Week"),
            ("stale",     "⏳",  "purple", "Long Pending (14+ days)"),
        ]

        for key, icon, colour, label in sections:
            items = digest[key]
            if not items:
                continue

            st.markdown(
                f"<div class='digest-section-label {colour}'>{icon} {label} ({len(items)})</div>",
                unsafe_allow_html=True,
            )
            for row in items:
                dl = row["days_left"]
                if dl is not None and dl < 0:
                    badge_text = f"{abs(dl)}d overdue"
                    badge_style = "background:#fee2e2;color:#991b1b"
                elif dl == 0:
                    badge_text = "Due today"
                    badge_style = "background:#fef3c7;color:#92400e"
                elif dl is not None:
                    badge_text = f"{dl}d left"
                    badge_style = "background:#eff6ff;color:#1e40af"
                else:
                    badge_text = f"{row['sitting_days']}d pending"
                    badge_style = "background:#f3e8ff;color:#6b21a8"

                owner_dept = row["owner"]
                if row["department"] and row["department"] != "Not stated":
                    owner_dept += f" · {row['department']}"

                st.markdown(
                    f"""
                    <div class='digest-row'>
                        <div>
                            <div class='digest-row-text'>{row['text']}</div>
                            <div class='digest-row-meta'>{row['meeting_title']} · {owner_dept}</div>
                        </div>
                        <span class='digest-row-badge' style='{badge_style}'>{badge_text}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ------------------------------------------------------------------
# Upcoming tasks — show only meeting title; expand to see full details
# ------------------------------------------------------------------
def _render_upcoming(meetings: list) -> None:
    st.markdown("#### Upcoming tasks")
    upcoming = get_upcoming_meetings(meetings, limit=5)
    if not upcoming:
        st.info("No pending deadlines. Add a meeting in Capture to see it here.")
        return

    for m in upcoming:
        title = normalize_value(m.get("title"), "Untitled meeting")
        meeting_date = normalize_value(m.get("date"), "")
        label = f"{title}  ·  {meeting_date}" if meeting_date else title
        with st.expander(label, expanded=False):
            _render_upcoming_detail(m)


def _render_upcoming_detail(meeting: dict) -> None:
    """Render full meeting detail inside the expander — same style as tracker."""
    from ui.components import action_card

    report_by = normalize_value(meeting.get("user_id") or meeting.get("updated_by"), "Not stated")
    activity_id = normalize_value(meeting.get("activityId") or meeting.get("meetingID"), "No ID")
    department = normalize_value(meeting.get("deptName") or meeting.get("department"), "No group")
    summary = normalize_value(meeting.get("summary") or meeting.get("recaps"), "No summary yet.")

    st.markdown(
        f"""
        <div class='upcoming-header'>
            <div>
                <div class='upcoming-report-by'>Report by: {report_by}</div>
                <div class='upcoming-meta'>{activity_id} | {department}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f"**Summary:** {summary}")
    st.markdown("**Action Items**")

    actions = [
        a for a in (meeting.get("actions") or [])
        if normalize_status(a) in {"Pending", "In Progress", "Overdue"}
    ]
    if not actions:
        st.caption("No pending action items for this meeting.")
    meeting_date = normalize_value(meeting.get("date"), "")
    for a in actions:
        action_card(a, meeting_date=meeting_date)


# ------------------------------------------------------------------
# Chatbot — fresh session on each Dashboard visit; saves to history
# ------------------------------------------------------------------
def _render_chatbot(meetings: list) -> None:
    st.markdown("#### Ask your meetings")

    user_id = st.text_input(
        "Enter your ID to start chatting",
        value=st.session_state.get("chat_user_id", ""),
        key="chat_user_id_input",
        placeholder="e.g. wan01",
    )
    st.session_state.chat_user_id = user_id.strip()

    if not st.session_state.chat_user_id:
        st.caption("Your chat history is private — only visible when this ID is entered.")
        return

    # Per-session in-memory messages (NOT loaded from DB so it starts fresh)
    if "dashboard_chat_messages" not in st.session_state:
        st.session_state.dashboard_chat_messages = []
        st.session_state.dashboard_chat_session_id = uid()

    messages = st.session_state.dashboard_chat_messages

    # New Chat button
    top_l, top_r = st.columns([3, 1])
    with top_r:
        if st.button("New Chat", key="chat_new_session", use_container_width=True):
            st.session_state.dashboard_chat_messages = []
            st.session_state.dashboard_chat_session_id = uid()
            st.rerun()

    # Message thread
    container = st.container(height=300)
    with container:
        if not messages:
            st.caption("Try: 'What tasks are pending this week?'")
        for entry in messages:
            from ui.components import chat_bubble
            chat_bubble(entry["role"], entry["text"])

    # Input form
    with st.form(f"chat_form__{st.session_state.chat_user_id}", clear_on_submit=True):
        question = st.text_input(
            "Your question",
            key=f"chat_q__{st.session_state.chat_user_id}",
            placeholder="Ask about your meetings…",
            label_visibility="collapsed",
        )
        submit = st.form_submit_button("Ask →")

    if submit and question.strip():
        messages.append({"role": "user", "text": question})
        try:
            answer = chat_with_meetings(question, meetings)
        except Exception as exc:
            answer = f"Sorry, I couldn't reach the model. ({exc})"
        messages.append({"role": "assistant", "text": answer})

        session_id = st.session_state.get("dashboard_chat_session_id", uid())
        save_history_entry({
            "id": uid(),
            "user_id": st.session_state.chat_user_id,
            "thread_key": f"{st.session_state.chat_user_id}|{today_str()}|{session_id}",
            "thread_date": today_str(),
            "thread_title": question[:60],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "question": question,
            "answer": answer,
            "meeting_id": "",
            "meeting_title": "",
            "context": "general",
        })
        st.rerun()
