"""Action Tracker page: browse saved meetings and edit their action items."""
import streamlit as st

from core.database import save_meeting
from ui.components import action_card, kpi_card
from utils.helpers import days_left, normalize_status, normalize_value


STATUS_FILTERS = ["All", "Pending", "In Progress", "Done", "Overdue"]


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    st.markdown("## Action Tracker")
    st.caption("Update statuses and deadlines across every saved meeting.")

    # Global KPIs
    all_actions = [a for m in meetings for a in (m.get("actions") or [])]
    total = len(all_actions)
    done = sum(1 for a in all_actions if normalize_status(a) == "Done")
    pending = sum(1 for a in all_actions if normalize_status(a) in {"Pending", "In Progress", "Overdue"})
    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Total actions", str(total), "Across all meetings", "#1d4ed8")
    with c2:
        kpi_card("Pending", str(pending), "Pending / In Progress / Overdue", "#b45309")
    with c3:
        kpi_card("Completed", str(done), "Marked Done", "#166534")

    # Filters
    col_search, col_status = st.columns([2, 1])
    with col_search:
        search = st.text_input("Search meetings", placeholder="Title, department, stakeholder…")
    with col_status:
        status_filter = st.selectbox("Status", STATUS_FILTERS, key="tracker_status")

    filtered = _filter_meetings(meetings, search, status_filter)
    if not filtered:
        st.info("No meetings match your filter.")
        return

    filtered.sort(key=lambda m: normalize_value(m.get("date"), ""), reverse=True)

    for meeting in filtered:
        title   = normalize_value(meeting.get("title"), "Untitled")
        m_date  = normalize_value(meeting.get("date"), "no date")
        actions = meeting.get("actions") or []

        # Build deadline summary for the expander label
        n_overdue = sum(1 for a in actions if normalize_status(a) == "Overdue")
        n_pending = sum(1 for a in actions if normalize_status(a) in ("Pending", "In Progress"))
        min_dl    = None
        for a in actions:
            dl = days_left(normalize_value(a.get("deadline"), ""))
            if dl is not None and normalize_status(a) not in ("Done", "Cancelled"):
                min_dl = dl if min_dl is None else min(min_dl, dl)

        if n_overdue > 0:
            badge = f"  [{n_overdue} overdue]"
        elif min_dl is not None and min_dl <= 3:
            badge = f"  [due in {min_dl}d]"
        elif n_pending > 0:
            badge = f"  [{n_pending} pending]"
        else:
            badge = ""

        with st.expander(f"{title}  ·  {m_date}{badge}", expanded=False):
            _render_meeting(meeting)


def _filter_meetings(meetings: list, search: str, status_filter: str) -> list:
    out = []
    needle = search.strip().lower()
    for m in meetings:
        if needle:
            haystack = " ".join(str(m.get(k, "")) for k in ("title", "department", "deptName", "summary"))
            haystack += " " + " ".join(str(s) for s in m.get("stakeholders", []) or [])
            if needle not in haystack.lower():
                continue
        if status_filter != "All":
            actions = m.get("actions", []) or []
            if not any(normalize_status(a) == status_filter for a in actions):
                continue
        out.append(m)
    return out


def _build_followup_email(meeting: dict) -> str:
    """Format the saved meeting data as a copy-paste follow-up email (no AI call)."""
    from datetime import datetime as _dt
    title      = normalize_value(meeting.get("title"), "Meeting")
    date_str   = normalize_value(meeting.get("date"), "")
    summary    = normalize_value(meeting.get("summary"), "No summary provided.")
    objective  = normalize_value(meeting.get("objective"), "")
    report_by  = normalize_value(meeting.get("user_id") or meeting.get("updated_by"), "The Meeting Organizer")

    try:
        date_display = _dt.strptime(date_str, "%Y-%m-%d").strftime("%A, %d %B %Y")
    except Exception:
        date_display = date_str

    action_lines = []
    for i, a in enumerate((meeting.get("actions") or []), 1):
        if normalize_status(a) not in ("Done", "Cancelled"):
            text     = normalize_value(a.get("text"), "")
            owner    = normalize_value(a.get("owner"), "Not stated")
            deadline = normalize_value(a.get("deadline"), "Not stated")
            action_lines.append(f"  {i}. {text}\n     Owner: {owner} | Deadline: {deadline}")

    actions_block  = "\n".join(action_lines) if action_lines else "  No pending action items."
    objective_line = f"\nObjective:\n{objective}\n" if objective else ""

    return (
        f"Dear colleagues,\n\n"
        f"Please find below the meeting monitoring report for your reference.\n\n"
        f"MEETING RECAP\n"
        f"Date: {date_display}\n\n"
        f"Meeting: {title}\n\n"
        f"Summary:\n{summary}\n"
        f"{objective_line}\n"
        f"Action Items:\n{actions_block}\n\n"
        f"Regards,\n{report_by}"
    )


def _render_meeting(meeting: dict) -> None:
    st.markdown(f"**Summary:** {normalize_value(meeting.get('summary'), 'No summary.')}")
    st.markdown(f"**Objective:** {normalize_value(meeting.get('objective'), 'Not provided')}")
    st.markdown(
        f"**Department:** {normalize_value(meeting.get('deptName') or meeting.get('department'), 'Unassigned')}"
    )

    # ── Original content comparison ──────────────────────────────────
    orig_t = meeting.get("transcript_original", "")
    orig_r = meeting.get("recap_original", "")
    if orig_t or orig_r:
        with st.expander("View original content", expanded=False):
            tab_t, tab_r = st.tabs(["Original Transcript", "Original AI Output"])
            m_id = normalize_value(meeting.get("id") or meeting.get("activityId"), "x")
            with tab_t:
                if orig_t:
                    st.text_area(
                        "Raw Whisper output (before any edits)",
                        value=orig_t,
                        height=220,
                        disabled=True,
                        key=f"orig_t_{m_id}",
                    )
                else:
                    st.caption("No original transcript saved (meeting was entered manually).")
            with tab_r:
                if orig_r:
                    import json as _json
                    try:
                        r = _json.loads(orig_r)
                        st.markdown(f"**Original Summary:** {r.get('summary','')}")
                        st.markdown(f"**Original Objective:** {r.get('objective','')}")
                        orig_actions = r.get("action_items", [])
                        if orig_actions:
                            st.markdown("**Original Action Items:**")
                            for a in orig_actions:
                                st.markdown(
                                    f"- {a.get('text','Untitled')} | "
                                    f"Owner: {a.get('owner','Not stated')} | "
                                    f"Deadline: {a.get('deadline','None')}"
                                )
                    except Exception:
                        st.text_area("Original AI output", value=orig_r[:2000], height=220,
                                     disabled=True, key=f"orig_r_{m_id}")
                else:
                    st.caption("No original AI output saved.")

    # ── Smart Follow-Up Email button ─────────────────────────────────
    meeting_id = normalize_value(meeting.get("id") or meeting.get("activityId"), "unknown")
    email_key  = f"followup_email_{meeting_id}"
    email_open = f"followup_open_{meeting_id}"

    # ── Download PDF button ──────────────────────────────────────────
    _pdf_cache_key = f"pdf_bytes_{meeting_id}"
    if _pdf_cache_key not in st.session_state:
        try:
            from utils.export import generate_meeting_pdf
            st.session_state[_pdf_cache_key] = generate_meeting_pdf(meeting)
        except Exception as _e:
            st.session_state[_pdf_cache_key] = b""
            st.caption(f"PDF error: {_e}")
    if st.session_state.get(_pdf_cache_key):
        _safe_title = "".join(
            c for c in normalize_value(meeting.get("title"), "meeting")
            if c.isalnum() or c in " _-"
        )[:40].strip()
        st.download_button(
            label="Download Brief (PDF)",
            data=st.session_state[_pdf_cache_key],
            file_name=f"{_safe_title}.pdf",
            mime="application/pdf",
            key=f"dl_pdf_{meeting_id}",
        )

    if st.button("Copy Follow-Up Email", key=f"btn_email_{meeting_id}"):
        if st.session_state.get(email_open):
            st.session_state.pop(email_key, None)
            st.session_state[email_open] = False
        else:
            st.session_state[email_key] = _build_followup_email(meeting)
            st.session_state[email_open] = True
        st.rerun()

    if st.session_state.get(email_open) and st.session_state.get(email_key):
        st.text_area(
            "Follow-up email draft (copy to send)",
            value=st.session_state[email_key],
            height=280,
            key=f"email_ta_{meeting_id}",
        )

    actions = meeting.get("actions", []) or []
    if not actions:
        st.info("No action items for this meeting.")
        return

    st.markdown("#### Action items")

    def persist() -> None:
        try:
            save_meeting(meeting)
        except Exception as exc:
            st.warning(f"Supabase sync failed: {exc}")

    meeting_date = normalize_value(meeting.get("date"), "")
    for action in actions:
        action_card(action, editable=True, persist_callback=persist, meeting_date=meeting_date)
