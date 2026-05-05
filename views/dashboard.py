"""Dashboard page: KPIs, calendar, AI chat, upcoming task cards."""
from datetime import datetime

import streamlit as st

from core.database import save_history_entry
from core.pipeline import chat_with_meetings, stream_chat_with_meetings
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

    # ── Header row: title + New Meeting button ───────────────────────
    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    hdr_left, hdr_right = st.columns([3, 1])
    with hdr_left:
        st.markdown(
            "<div style='font-size:1.5rem;font-weight:800;color:var(--text);"
            "line-height:1.2;margin-bottom:0.1rem'>Dashboard</div>",
            unsafe_allow_html=True,
        )
    with hdr_right:
        if st.button("＋  New Meeting", key="dash_new_meeting",
                     type="primary", use_container_width=True):
            st.session_state.current_page = "Capture"
            st.rerun()

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Two-column layout
    main_col, side_col = st.columns([2.2, 1], gap="large")

    with main_col:
        _render_kpis(meetings)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        _render_overdue_alert(meetings)
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
        if normalize_status(a) in {"Pending", "In Progress"}
    )
    overdue = sum(1 for a in all_actions if normalize_status(a) == "Overdue")
    done = sum(1 for a in all_actions if normalize_status(a) == "Done")
    total_actions = len(all_actions)
    completion = int((done / total_actions) * 100) if total_actions else 0

    kpi_wide("Total meetings", str(total_meetings))

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card("Action items", str(total_actions), "Extracted tasks", "#0f766e")
    with c2:
        kpi_card("Pending", str(pending), "Still open", "#b45309")
    with c3:
        kpi_card("Overdue", str(overdue), "Past deadline", "#991b1b")
    with c4:
        kpi_card("Completed", str(done), "Marked done", "#1d4ed8")
    with c5:
        completion_ring(completion)


# ------------------------------------------------------------------
# Overdue Alert Panel
# ------------------------------------------------------------------
def _render_overdue_alert(meetings: list) -> None:
    """Red alert banner listing every overdue action item across all meetings."""
    from utils.helpers import days_left as _dl

    overdue_rows = []
    for m in meetings:
        m_title = normalize_value(m.get("title"), "Untitled meeting")
        for a in (m.get("actions") or []):
            if normalize_status(a) != "Overdue":
                continue
            deadline = normalize_value(a.get("deadline"), "")
            dl = _dl(deadline) if deadline and deadline not in ("None", "Not stated") else None
            days_over = abs(dl) if dl is not None and dl < 0 else 0
            overdue_rows.append({
                "text":      normalize_value(a.get("text"), "Untitled action"),
                "owner":     normalize_value(a.get("owner"), "Not stated"),
                "dept":      normalize_value(a.get("department") or a.get("company"), ""),
                "days_over": days_over,
                "mtitle":    m_title,
            })

    if not overdue_rows:
        return

    overdue_rows.sort(key=lambda r: -r["days_over"])

    rows_html = ""
    for r in overdue_rows:
        dept_part = f" &nbsp;|&nbsp; {r['dept']}" if r["dept"] and r["dept"] not in ("Not stated", "None") else ""
        rows_html += (
            f"<div style='background:#fff1f1;border:1px solid #fca5a5;border-radius:10px;"
            f"padding:0.5rem 0.8rem;margin-bottom:0.35rem'>"
            f"<div style='font-weight:700;color:#7f1d1d;font-size:0.92rem'>{r['text']}</div>"
            f"<div style='font-size:0.8rem;color:#991b1b;margin-top:0.15rem'>"
            f"{r['owner']}{dept_part} &nbsp;|&nbsp; {r['mtitle']} "
            f"&nbsp;|&nbsp; <strong>{r['days_over']}d overdue</strong>"
            f"</div></div>"
        )

    st.markdown(
        f"<div style='background:#fef2f2;border:2px solid #ef4444;border-radius:16px;"
        f"padding:0.9rem 1rem;margin-bottom:1rem'>"
        f"<div style='font-weight:800;color:#991b1b;font-size:1rem;margin-bottom:0.6rem'>"
        f"Overdue Actions — {len(overdue_rows)} item(s) need immediate attention</div>"
        f"{rows_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


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
# Upcoming Tasks — items due within the next 7 days only (not overdue)
# ------------------------------------------------------------------
def _render_upcoming(meetings: list) -> None:
    """Show action items due within the next 7 days. Overdue items appear in the red panel above."""
    from collections import defaultdict
    from utils.helpers import days_left as _dl
    from ui.components import action_card

    st.markdown("#### Upcoming Tasks")
    st.caption("Tasks with deadlines in the next 7 days.")

    action_rows = []
    for m in meetings:
        m_date  = normalize_value(m.get("date"), "")
        m_title = normalize_value(m.get("title"), "Untitled meeting")
        m_dept  = normalize_value(m.get("deptName") or m.get("department"), "").strip()
        if m_dept in ("None", "Not stated", "No group"):
            m_dept = ""

        for a in (m.get("actions") or []):
            status = normalize_status(a)
            if status in ("Done", "Cancelled", "Overdue"):
                continue

            deadline = normalize_value(a.get("deadline"), "")
            dl = _dl(deadline) if deadline and deadline not in ("None", "Not stated") else None

            # Only include if deadline is between today and 7 days from now
            if dl is None or dl < 0 or dl > 7:
                continue

            a_dept = normalize_value(a.get("department") or a.get("company"), "").strip()
            if a_dept in ("None", "Not stated", "TalentCorp", "Talent Corp", "TC", ""):
                a_dept = m_dept if m_dept else ""

            action_rows.append({
                "action":       a,
                "dept":         a_dept,
                "meeting_date": m_date,
                "meeting_title": m_title,
                "dl":           dl if dl is not None else 9999,
            })

    if not action_rows:
        st.info("No tasks due in the next 7 days.")
        return

    # Sort: overdue first, then soonest deadline
    action_rows.sort(key=lambda r: r["dl"])

    # Group by department
    dept_map: dict = defaultdict(list)
    for row in action_rows:
        dept_map[row["dept"]].append(row)

    named_depts = sorted(k for k in dept_map if k)

    for dept in named_depts:
        st.markdown(
            f"<div style='font-size:0.82rem;font-weight:800;color:var(--brand-2);"
            f"text-transform:uppercase;letter-spacing:0.06em;margin:0.9rem 0 0.25rem'>"
            f"{dept}</div>",
            unsafe_allow_html=True,
        )
        for row in dept_map[dept]:
            action_card(row["action"], meeting_date=row["meeting_date"], meeting_title=row["meeting_title"])

    if "" in dept_map:
        if named_depts:
            st.markdown(
                "<div style='font-size:0.82rem;font-weight:800;color:var(--text-soft);"
                "text-transform:uppercase;letter-spacing:0.06em;margin:0.9rem 0 0.25rem'>"
                "Unassigned</div>",
                unsafe_allow_html=True,
            )
        for row in dept_map[""]:
            action_card(row["action"], meeting_date=row["meeting_date"], meeting_title=row["meeting_title"])


# ------------------------------------------------------------------
# Chatbot — fresh session on each Dashboard visit; saves to history
# ------------------------------------------------------------------
def _render_chatbot(meetings: list) -> None:
    st.markdown("#### Ask your meetings")

    # Initialise session on first load
    if "dashboard_chat_messages" not in st.session_state:
        st.session_state.dashboard_chat_messages = []
        st.session_state.dashboard_chat_session_id = uid()

    messages = st.session_state.dashboard_chat_messages

    # Message thread
    # Only render settled messages here; pending user message is rendered in the
    # streaming block below to avoid showing it twice.
    is_pending = messages and messages[-1]["role"] == "user"
    settled = messages[:-1] if is_pending else messages

    container = st.container(height=300)
    with container:
        if not messages:
            st.caption("Try: 'What tasks are pending this week?'")
        for entry in settled:
            from ui.components import chat_bubble
            chat_bubble(entry["role"], entry["text"])

    # Hide the submit button — Enter key still submits the form
    st.markdown(
        "<style>div[data-testid='stFormSubmitButton']{display:none !important}</style>",
        unsafe_allow_html=True,
    )

    # Input form
    with st.form("chat_form", clear_on_submit=True):
        question = st.text_input(
            "Your question",
            key="chat_q",
            placeholder="Ask about your meetings…",
            label_visibility="collapsed",
        )
        submit = st.form_submit_button("Ask →")

    if submit and question.strip():
        messages.append({"role": "user", "text": question})
        st.rerun()  # show user message immediately, then stream the reply

    # Save chat to history — visible once there is at least one answered exchange
    completed = [m for m in messages if m["role"] == "assistant"]
    if completed:
        save_key = f"chat_saved__{st.session_state.dashboard_chat_session_id}"
        already_saved = st.session_state.get(save_key, False)
        if already_saved:
            st.caption("Saved to Chat History")
        else:
            if st.button("Save chat", key="chat_save", use_container_width=True):
                session_id = st.session_state.get("dashboard_chat_session_id", uid())
                # Save each Q&A pair that hasn't been stored yet
                pairs = [(messages[i], messages[i + 1])
                         for i in range(0, len(messages) - 1, 2)
                         if messages[i]["role"] == "user"
                         and i + 1 < len(messages)
                         and messages[i + 1]["role"] == "assistant"]
                for q_entry, a_entry in pairs:
                    save_history_entry({
                        "id": uid(),
                        "user_id": "shared",
                        "thread_key": f"shared|{today_str()}|{session_id}",
                        "thread_date": today_str(),
                        "thread_title": q_entry["text"][:60],
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "question": q_entry["text"],
                        "answer": a_entry["text"],
                        "meeting_id": "",
                        "meeting_title": "",
                        "context": "general",
                    })
                st.session_state[save_key] = True
                st.rerun()

    # If the last message is from the user and has no reply yet → stream the answer
    if is_pending:
        pending_q = messages[-1]["text"]
        with container:
            from ui.components import chat_bubble
            # settled messages are already rendered above — only add the pending user bubble
            chat_bubble("user", pending_q)

            # Stream assistant reply with a typing effect
            reply_placeholder = st.empty()
            accumulated = ""
            try:
                for chunk in stream_chat_with_meetings(pending_q, meetings):
                    accumulated += chunk
                    reply_placeholder.markdown(
                        f"<div style='background:#f0f4ff;border-radius:14px 14px 14px 4px;"
                        f"padding:0.65rem 0.9rem;font-size:0.9rem;color:#0f172a;"
                        f"margin:0.3rem 0;max-width:92%'>{accumulated}▌</div>",
                        unsafe_allow_html=True,
                    )
            except Exception as exc:
                accumulated = f"Sorry, I couldn't reach the model. ({exc})"
            # Final render without cursor
            reply_placeholder.markdown(
                f"<div style='background:#f0f4ff;border-radius:14px 14px 14px 4px;"
                f"padding:0.65rem 0.9rem;font-size:0.9rem;color:#0f172a;"
                f"margin:0.3rem 0;max-width:92%'>{accumulated}</div>",
                unsafe_allow_html=True,
            )

        messages.append({"role": "assistant", "text": accumulated})
        session_id = st.session_state.get("dashboard_chat_session_id", uid())
        save_history_entry({
            "id": uid(),
            "user_id": st.session_state.chat_user_id,
            "thread_key": f"{st.session_state.chat_user_id}|{today_str()}|{session_id}",
            "thread_date": today_str(),
            "thread_title": pending_q[:60],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "question": pending_q,
            "answer": accumulated,
            "meeting_id": "",
            "meeting_title": "",
            "context": "general",
        })
        st.rerun()
