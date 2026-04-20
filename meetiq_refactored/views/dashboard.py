"""Dashboard page: KPIs, calendar, gated AI chat, upcoming task cards."""
from datetime import datetime

import streamlit as st

from core.database import save_history_entry
from core.pipeline import chat_with_meetings
from ui import calendar as calendar_widget
from ui.components import (
    chat_bubble,
    completion_ring,
    kpi_card,
    kpi_wide,
    upcoming_task_card,
)
from utils.formatters import get_upcoming_meetings
from utils.helpers import (
    normalize_status,
    today_str,
    uid,
)


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    # Two-column layout: main (cards + upcoming) on the left, calendar + chat on the right
    main_col, side_col = st.columns([2.2, 1], gap="large")

    with main_col:
        _render_kpis(meetings)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        _render_upcoming(meetings)

    with side_col:
        st.markdown("#### Calendar")
        calendar_widget.render(meetings)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        _render_chatbot(meetings)


# ------------------------------------------------------------------
# KPI section: wide hero card + 4 smaller cards underneath
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

    # Full-width hero KPI
    kpi_wide("Total meetings", str(total_meetings))

    # 4 cards underneath
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
# Upcoming tasks
# ------------------------------------------------------------------
def _render_upcoming(meetings: list) -> None:
    st.markdown("#### Upcoming tasks")
    upcoming = get_upcoming_meetings(meetings, limit=5)
    if not upcoming:
        st.info("No pending deadlines. Add a meeting in Capture to see it here.")
        return
    for m in upcoming:
        upcoming_task_card(m)


# ------------------------------------------------------------------
# Gated chatbot — user must enter their ID before chatting.
# Each user's chat history is scoped to their ID.
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

    history_key = f"chat_history__{st.session_state.chat_user_id}"
    history = st.session_state.setdefault(history_key, [])

    container = st.container(height=300)
    with container:
        if not history:
            st.caption("Try: 'What tasks are pending this week?'")
        for entry in history:
            chat_bubble(entry["role"], entry["text"])

    with st.form(f"chat_form__{st.session_state.chat_user_id}", clear_on_submit=True):
        question = st.text_input(
            "Your question",
            key=f"chat_q__{st.session_state.chat_user_id}",
            placeholder="Ask about your meetings…",
            label_visibility="collapsed",
        )
        submit = st.form_submit_button("Ask")

    if submit and question.strip():
        history.append({"role": "user", "text": question})
        try:
            answer = chat_with_meetings(question, meetings)
        except Exception as exc:
            answer = f"Sorry, I couldn't reach the model. ({exc})"
        history.append({"role": "assistant", "text": answer})

        save_history_entry({
            "id": uid(),
            "user_id": st.session_state.chat_user_id,
            "thread_key": f"{st.session_state.chat_user_id}|{today_str()}",
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
