"""Action Tracker page: browse saved meetings and edit their action items."""
import streamlit as st

from core.database import save_meeting
from ui.components import action_card, kpi_card
from utils.helpers import normalize_status, normalize_value


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
        kpi_card("Completed", str(done), "Marked Done", "#166534")
    with c3:
        kpi_card("Outstanding", str(pending), "Pending / In Progress / Overdue", "#b45309")

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
        with st.expander(
            f"{normalize_value(meeting.get('title'), 'Untitled')}  ·  "
            f"{normalize_value(meeting.get('date'), 'no date')}",
            expanded=False,
        ):
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


def _render_meeting(meeting: dict) -> None:
    st.markdown(f"**Summary:** {normalize_value(meeting.get('summary'), 'No summary.')}")
    st.markdown(f"**Objective:** {normalize_value(meeting.get('objective'), 'Not provided')}")
    st.markdown(
        f"**Department:** {normalize_value(meeting.get('deptName') or meeting.get('department'), 'Unassigned')}"
    )

    # ── Smart Follow-Up Email button ─────────────────────────────────
    meeting_id = normalize_value(meeting.get("id") or meeting.get("activityId"), "unknown")
    email_key  = f"followup_email_{meeting_id}"
    email_open = f"followup_open_{meeting_id}"

    if st.button("📧 Generate Follow-Up Email", key=f"btn_email_{meeting_id}"):
        if st.session_state.get(email_open):
            st.session_state.pop(email_key, None)
            st.session_state[email_open] = False
        else:
            with st.spinner("Drafting follow-up email…"):
                try:
                    from core.pipeline import generate_followup_email
                    st.session_state[email_key] = generate_followup_email(meeting)
                    st.session_state[email_open] = True
                except Exception as exc:
                    st.session_state[email_key] = f"Could not generate email: {exc}"
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
