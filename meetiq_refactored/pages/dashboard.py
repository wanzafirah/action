"""Dashboard page: KPIs, upcoming deadlines, calendar, AI chat."""
from datetime import datetime

import streamlit as st

from core.database import save_history_entry
from core.pipeline import chat_with_meetings
from ui import calendar as calendar_widget
from ui.components import chat_bubble, completion_ring, kpi_card
from utils.formatters import get_upcoming_meetings
from utils.helpers import (
    normalize_status,
    normalize_value,
    pretty_deadline,
    today_str,
    uid,
)


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    # Hero
    st.markdown(
        "<div class='hero-shell'>"
        "<h1>MeetIQ Dashboard</h1>"
        "<p>AI meeting intelligence + action tracker</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # KPIs
    total_meetings = len(meetings)
    all_actions = [a for m in meetings for a in (m.get("actions") or [])]
    pending = sum(1 for a in all_actions if normalize_status(a) in {"Pending", "In Progress", "Overdue"})
    done = sum(1 for a in all_actions if normalize_status(a) == "Done")
    completion = int((done / len(all_actions)) * 100) if all_actions else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Meetings", str(total_meetings), "Total recorded", "#1d4ed8")
    with c2:
        kpi_card("Action items", str(len(all_actions)), "Extracted tasks", "#0f766e")
    with c3:
        kpi_card("Pending", str(pending), "Still open", "#b45309")
    with c4:
        completion_ring(completion)

    st.markdown("<div class='dashboard-shell'>", unsafe_allow_html=True)

    # Left column: upcoming
    with st.container():
        st.markdown("### Upcoming deadlines")
        upcoming = get_upcoming_meetings(meetings, limit=5)
        if not upcoming:
            st.info("No pending deadlines. Add a meeting in Capture to see it here.")
        for m in upcoming:
            next_deadline = "—"
            for a in m.get("actions") or []:
                if normalize_status(a) in {"Pending", "In Progress"}:
                    deadline = normalize_value(a.get("deadline"), "")
                    if deadline and deadline != "None":
                        next_deadline = pretty_deadline(deadline)
                        break
            st.markdown(
                f"""
                <div class='upcoming-item'>
                    <div class='upcoming-top'>
                        <div>
                            <div class='upcoming-title'>{normalize_value(m.get('title'), 'Untitled')}</div>
                            <div class='upcoming-report-by'>
                                {normalize_value(m.get('deptName') or m.get('department'), 'Unassigned')}
                            </div>
                        </div>
                        <div class='upcoming-date'>{next_deadline}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Right column: calendar + chat
    st.markdown("### Calendar")
    calendar_widget.render(meetings)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    _render_chat(meetings)


# ------------------------------------------------------------------
# Chat section
# ------------------------------------------------------------------
def _render_chat(meetings: list) -> None:
    st.markdown("### Ask about your meetings")
    user_id = st.text_input(
        "Your ID (groups your chat history)",
        value=st.session_state.get("chat_user_id", ""),
        key="chat_user_id_input",
    )
    st.session_state.chat_user_id = user_id

    history = st.session_state.setdefault("chat_history", [])
    container = st.container(height=360)
    with container:
        if not history:
            st.caption("Start by asking something like 'what are my pending items?'")
        for entry in history:
            chat_bubble(entry["role"], entry["text"])

    with st.form("chat_form", clear_on_submit=True):
        question = st.text_input("Your question", key="chat_question", placeholder="e.g. what's pending this week?")
        submit = st.form_submit_button("Ask")

    if submit and question.strip():
        history.append({"role": "user", "text": question})
        try:
            answer = chat_with_meetings(question, meetings)
        except Exception as exc:
            answer = f"Sorry, I couldn't reach the model. ({exc})"
        history.append({"role": "assistant", "text": answer})

        if user_id.strip():
            save_history_entry({
                "id": uid(),
                "user_id": user_id.strip(),
                "thread_key": f"{user_id.strip()}|{today_str()}",
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
