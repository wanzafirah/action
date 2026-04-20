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
from config.constants import TALENTCORP_DEPT_KEYWORDS
from utils.formatters import get_upcoming_meetings  # kept for potential reuse
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
# TalentCorp department filter
# ------------------------------------------------------------------
def _is_talentcorp_dept(dept: str) -> bool:
    """Return True if dept name matches a TalentCorp unit (case-insensitive partial match)."""
    if not dept:
        return True  # unknown dept → don't exclude
    dl = dept.lower().strip()
    # Exact match in keyword set
    if dl in TALENTCORP_DEPT_KEYWORDS:
        return True
    # Partial match: any TalentCorp keyword appears in the dept string, or vice versa
    for kw in TALENTCORP_DEPT_KEYWORDS:
        if kw in dl or dl in kw:
            return True
    return False


# ------------------------------------------------------------------
# Local helper — all meetings with at least one non-done action
# ------------------------------------------------------------------
def _get_all_active_meetings(meetings: list) -> list:
    from utils.helpers import days_left as _dl
    candidates = []
    for m in meetings:
        actions = [
            a for a in (m.get("actions") or [])
            if normalize_status(a) not in ("Done", "Cancelled")
        ]
        if not actions:
            continue
        dl_values = []
        for a in actions:
            d = normalize_value(a.get("deadline"), "")
            if d and d not in ("None", "Not stated"):
                v = _dl(d)
                if v is not None:
                    dl_values.append(v)
        urgency = min(dl_values) if dl_values else 9999
        candidates.append((urgency, m))
    candidates.sort(key=lambda t: t[0])
    return [m for _, m in candidates]


# ------------------------------------------------------------------
# Upcoming Tasks — flat list of action items grouped by department
# ------------------------------------------------------------------
def _render_upcoming(meetings: list) -> None:
    """Collect all non-done action items, group by department, render as cards."""
    from collections import defaultdict
    from ui.components import action_card

    st.markdown("#### Upcoming Tasks")

    # Gather Pending and In Progress action items only (Overdue/Done/Cancelled excluded)
    action_rows = []
    for m in meetings:
        m_date  = normalize_value(m.get("date"), "")
        m_title = normalize_value(m.get("title"), "Untitled meeting")
        m_dept  = normalize_value(m.get("deptName") or m.get("department"), "").strip()
        if m_dept in ("None", "Not stated", "No group"):
            m_dept = ""

        for a in (m.get("actions") or []):
            if normalize_status(a) not in ("Pending", "In Progress"):
                continue
            # Action's own department takes priority; fall back to meeting's dept
            a_dept = normalize_value(a.get("department") or a.get("company"), "").strip()
            if a_dept in ("None", "Not stated", ""):
                a_dept = m_dept

            # Filter out action items belonging to external (non-TalentCorp) organisations
            if a_dept and not _is_talentcorp_dept(a_dept):
                continue

            action_rows.append({"action": a, "dept": a_dept, "meeting_date": m_date, "meeting_title": m_title})

    if not action_rows:
        st.info("No pending actions. Add a meeting in Capture to see it here.")
        return

    # Group by department
    dept_map: dict = defaultdict(list)
    for row in action_rows:
        dept_map[row["dept"]].append(row)

    named_depts = sorted(k for k in dept_map if k)

    for dept in named_depts:
        st.markdown(
            f"<div style='font-size:0.82rem;font-weight:800;color:var(--brand-2);"
            f"text-transform:uppercase;letter-spacing:0.06em;margin:0.9rem 0 0.25rem'>"
            f"🏢 {dept}</div>",
            unsafe_allow_html=True,
        )
        for row in dept_map[dept]:
            action_card(row["action"], meeting_date=row["meeting_date"], meeting_title=row["meeting_title"])

    if "" in dept_map:
        if named_depts:
            st.markdown(
                "<div style='font-size:0.82rem;font-weight:800;color:var(--text-soft);"
                "text-transform:uppercase;letter-spacing:0.06em;margin:0.9rem 0 0.25rem'>"
                "📋 Other</div>",
                unsafe_allow_html=True,
            )
        for row in dept_map[""]:
            action_card(row["action"], meeting_date=row["meeting_date"], meeting_title=row["meeting_title"])


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
        # User cleared their ID — wipe the current session so next login starts fresh
        st.session_state.pop("dashboard_chat_messages", None)
        st.session_state.pop("dashboard_chat_session_id", None)
        st.caption("Your chat history is private — only visible when this ID is entered.")
        return

    # Start a fresh session each time this ID is entered for the first time
    if "dashboard_chat_messages" not in st.session_state:
        st.session_state.dashboard_chat_messages = []
        st.session_state.dashboard_chat_session_id = uid()

    messages = st.session_state.dashboard_chat_messages

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
