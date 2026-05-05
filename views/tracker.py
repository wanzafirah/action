"""Action Tracker page: folder-based meeting organisation with inline action editing."""
import streamlit as st

from core.database import save_meeting
from ui.components import action_card, kpi_card
from utils.helpers import days_left, normalize_status, normalize_value
from utils.folder_db import (
    get_folders,
    create_folder,
    delete_folder,
    rename_folder,
    add_meeting_to_folder,
    remove_meeting_from_folder,
    get_all_assigned_ids,
)


STATUS_FILTERS = ["All", "Pending", "In Progress", "Done", "Overdue"]


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    st.markdown("## Action Tracker")
    st.caption("Organise meetings into folders and track action items.")

    # ── Global KPIs ──────────────────────────────────────────────────
    all_actions = [a for m in meetings for a in (m.get("actions") or [])]
    total  = len(all_actions)
    done   = sum(1 for a in all_actions if normalize_status(a) == "Done")
    pending = sum(1 for a in all_actions if normalize_status(a) in {"Pending", "In Progress"})
    overdue = sum(1 for a in all_actions if normalize_status(a) == "Overdue")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total actions", str(total),   "Across all meetings",      "#1d4ed8")
    with c2:
        kpi_card("Pending",       str(pending), "Pending / In Progress",    "#b45309")
    with c3:
        kpi_card("Overdue",       str(overdue), "Past deadline",            "#991b1b")
    with c4:
        kpi_card("Completed",     str(done),    "Marked Done",              "#166534")

    # ── View selector ────────────────────────────────────────────────
    view = st.session_state.get("tracker_view", "folders")

    tab_folders, tab_all = st.tabs(["Folders", "All Meetings"])

    with tab_folders:
        _render_folders_view(meetings)

    with tab_all:
        _render_all_meetings_view(meetings)


# ──────────────────────────────────────────────────────────────────────
# FOLDERS VIEW
# ──────────────────────────────────────────────────────────────────────
def _render_folders_view(meetings: list) -> None:
    """Top level: list of folders. Clicking one drills into its meetings."""
    folders = get_folders()
    meeting_lookup = {
        normalize_value(m.get("id") or m.get("activityId"), ""): m
        for m in meetings
        if normalize_value(m.get("id") or m.get("activityId"), "")
    }

    # ── Create new folder ────────────────────────────────────────────
    with st.expander("Create new folder", expanded=False):
        col_name, col_btn = st.columns([3, 1])
        with col_name:
            new_folder_name = st.text_input(
                "Folder name",
                key="new_folder_name",
                placeholder="e.g. 1MDB Weekly, UPNM Collaboration",
                label_visibility="collapsed",
            )
        with col_btn:
            st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)
            if st.button("Create", key="btn_create_folder", type="primary", use_container_width=True):
                if new_folder_name.strip():
                    if create_folder(new_folder_name.strip()):
                        st.success(f"Folder '{new_folder_name.strip()}' created.")
                        st.rerun()
                    else:
                        st.warning("A folder with that name already exists.")
                else:
                    st.warning("Please enter a folder name.")

    if not folders and not meetings:
        st.info("No folders yet. Create one above to start organising your meetings.")
        return

    # ── Folder cards ─────────────────────────────────────────────────
    for folder_name, meeting_ids in folders.items():
        folder_meetings = [meeting_lookup[mid] for mid in meeting_ids if mid in meeting_lookup]

        # Badge counts
        n_overdue = sum(
            1 for m in folder_meetings
            for a in (m.get("actions") or [])
            if normalize_status(a) == "Overdue"
        )
        n_pending = sum(
            1 for m in folder_meetings
            for a in (m.get("actions") or [])
            if normalize_status(a) in ("Pending", "In Progress")
        )
        badge_parts = []
        if n_overdue:
            badge_parts.append(
                f"<span style='background:#fee2e2;color:#991b1b;padding:0.1rem 0.45rem;"
                f"border-radius:999px;font-size:0.72rem;font-weight:700'>{n_overdue} overdue</span>"
            )
        if n_pending:
            badge_parts.append(
                f"<span style='background:#fef3c7;color:#92400e;padding:0.1rem 0.45rem;"
                f"border-radius:999px;font-size:0.72rem;font-weight:700'>{n_pending} pending</span>"
            )
        badges_html = " ".join(badge_parts)
        count_label = f"{len(folder_meetings)} meeting{'s' if len(folder_meetings) != 1 else ''}"

        st.markdown(
            f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;"
            f"padding:0.65rem 0.9rem;margin-bottom:0.1rem;display:flex;"
            f"align-items:center;justify-content:space-between'>"
            f"<div>"
            f"<span style='font-weight:700;color:#0f172a;font-size:0.95rem'>{folder_name}</span>"
            f"<span style='color:#94a3b8;font-size:0.8rem;margin-left:0.6rem'>{count_label}</span>"
            f"</div>"
            f"<div style='display:flex;gap:0.4rem;align-items:center'>{badges_html}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        open_key = f"folder_open_{folder_name}"
        btn_label = "Close" if st.session_state.get(open_key) else "Open"
        col_open, col_del = st.columns([5, 1])
        with col_open:
            if st.button(btn_label, key=f"btn_open_{folder_name}", use_container_width=True):
                st.session_state[open_key] = not st.session_state.get(open_key, False)
                st.rerun()
        with col_del:
            if st.button("Delete", key=f"btn_del_{folder_name}", use_container_width=True):
                delete_folder(folder_name)
                st.session_state.pop(open_key, None)
                st.rerun()

        if st.session_state.get(open_key):
            _render_folder_content(folder_name, folder_meetings, meetings, meeting_lookup)

        st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)

    # ── Ungrouped meetings ───────────────────────────────────────────
    assigned_ids = get_all_assigned_ids()
    ungrouped = [
        m for m in meetings
        if normalize_value(m.get("id") or m.get("activityId"), "") not in assigned_ids
    ]
    if ungrouped:
        st.markdown(
            "<div style='font-size:0.8rem;font-weight:700;color:#94a3b8;"
            "text-transform:uppercase;letter-spacing:0.05em;margin:1rem 0 0.4rem'>Ungrouped</div>",
            unsafe_allow_html=True,
        )
        ungrouped_open_key = "ungrouped_open"
        if st.button(
            "Close ungrouped" if st.session_state.get(ungrouped_open_key) else f"Show {len(ungrouped)} ungrouped meetings",
            key="btn_ungrouped",
        ):
            st.session_state[ungrouped_open_key] = not st.session_state.get(ungrouped_open_key, False)
            st.rerun()

        if st.session_state.get(ungrouped_open_key):
            _render_folder_content(None, ungrouped, meetings, {
                normalize_value(m.get("id") or m.get("activityId"), ""): m for m in meetings
            })


def _render_folder_content(
    folder_name: str | None,
    folder_meetings: list,
    all_meetings: list,
    meeting_lookup: dict,
) -> None:
    """Render meetings inside an open folder, plus controls to add/remove."""
    st.markdown(
        "<div style='border-left:3px solid #bfdbfe;padding-left:0.75rem;margin:0.4rem 0 0.6rem'>",
        unsafe_allow_html=True,
    )

    # ── Add meeting to folder ────────────────────────────────────────
    if folder_name is not None:
        assigned_ids = {normalize_value(m.get("id") or m.get("activityId"), "") for m in folder_meetings}
        available = [
            m for m in all_meetings
            if normalize_value(m.get("id") or m.get("activityId"), "") not in assigned_ids
        ]
        col_sel, col_add, col_new = st.columns([4, 1, 2])
        with col_sel:
            opts = {
                f"{normalize_value(m.get('title'), 'Untitled')}  ·  {normalize_value(m.get('date'), '')}": m
                for m in sorted(available, key=lambda m: normalize_value(m.get("date"), ""), reverse=True)
            } if available else {}
            selected_label = st.selectbox(
                "Add existing meeting",
                ["— select meeting —"] + list(opts.keys()),
                key=f"add_mtg_sel_{folder_name}",
                label_visibility="collapsed",
            )
        with col_add:
            st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)
            if st.button("Add", key=f"btn_add_mtg_{folder_name}", use_container_width=True,
                         disabled=selected_label == "— select meeting —"):
                selected_m = opts[selected_label]
                mid = normalize_value(selected_m.get("id") or selected_m.get("activityId"), "")
                if mid:
                    add_meeting_to_folder(folder_name, mid)
                    st.rerun()
        with col_new:
            st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)
            if st.button("+ New meeting", key=f"btn_new_mtg_{folder_name}", use_container_width=True):
                st.session_state["capture_folder"] = folder_name
                st.session_state.current_page = "Capture"
                st.rerun()

    # ── Meeting list ─────────────────────────────────────────────────
    if not folder_meetings:
        st.caption("No meetings in this folder yet.")
    else:
        folder_meetings_sorted = sorted(
            folder_meetings,
            key=lambda m: normalize_value(m.get("date"), ""),
            reverse=True,
        )
        for meeting in folder_meetings_sorted:
            _render_meeting_expander(meeting, folder_name)

    st.markdown("</div>", unsafe_allow_html=True)


def _render_meeting_expander(meeting: dict, folder_name: str | None) -> None:
    """Single meeting row inside a folder."""
    title   = normalize_value(meeting.get("title"), "Untitled")
    m_date  = normalize_value(meeting.get("date"), "no date")
    actions = meeting.get("actions") or []
    meeting_id = normalize_value(meeting.get("id") or meeting.get("activityId"), "")

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
        # Remove from folder button
        if folder_name is not None and meeting_id:
            if st.button("Remove from folder", key=f"btn_rm_{folder_name}_{meeting_id}"):
                remove_meeting_from_folder(folder_name, meeting_id)
                st.rerun()
        _render_meeting(meeting, key_prefix=f"fld_{folder_name or 'ug'}_")


# ──────────────────────────────────────────────────────────────────────
# ALL MEETINGS VIEW (original flat list)
# ──────────────────────────────────────────────────────────────────────
def _render_all_meetings_view(meetings: list) -> None:
    col_search, col_status = st.columns([2, 1])
    with col_search:
        search = st.text_input("Search meetings", placeholder="Title, department, stakeholder…", key="tracker_search_all")
    with col_status:
        status_filter = st.selectbox("Status", STATUS_FILTERS, key="tracker_status_all")

    filtered = _filter_meetings(meetings, search, status_filter)
    if not filtered:
        st.info("No meetings match your filter.")
        return

    filtered.sort(key=lambda m: normalize_value(m.get("date"), ""), reverse=True)

    for meeting in filtered:
        title   = normalize_value(meeting.get("title"), "Untitled")
        m_date  = normalize_value(meeting.get("date"), "no date")
        actions = meeting.get("actions") or []

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
            _render_meeting(meeting, key_prefix="all_")


# ──────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ──────────────────────────────────────────────────────────────────────
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


def _render_meeting(meeting: dict, key_prefix: str = "") -> None:
    st.markdown(f"**Summary:** {normalize_value(meeting.get('summary'), 'No summary.')}")
    st.markdown(f"**Objective:** {normalize_value(meeting.get('objective'), 'Not provided')}")
    st.markdown(
        f"**Department:** {normalize_value(meeting.get('deptName') or meeting.get('department'), 'Unassigned')}"
    )

    orig_t = meeting.get("transcript_original", "") or meeting.get("transcript", "")
    if orig_t:
        with st.expander("View original content", expanded=False):
            m_id = normalize_value(meeting.get("id") or meeting.get("activityId"), "x")
            st.text_area(
                "Original transcript",
                value=orig_t,
                height=220,
                disabled=True,
                key=f"{key_prefix}orig_t_{m_id}",
            )

    meeting_id = normalize_value(meeting.get("id") or meeting.get("activityId"), "unknown")
    email_key  = f"followup_email_{meeting_id}"
    email_open = f"followup_open_{meeting_id}"

    # Download PDF
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
            key=f"{key_prefix}dl_pdf_{meeting_id}",
        )

    if st.button("Copy Follow-Up Email", key=f"{key_prefix}btn_email_{meeting_id}"):
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
            key=f"{key_prefix}email_ta_{meeting_id}",
        )
        import urllib.parse as _up
        _subject = _up.quote(f"Meeting Follow-Up: {normalize_value(meeting.get('title'), 'Meeting')}")
        _body = _up.quote(st.session_state[email_key])
        _gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&su={_subject}&body={_body}"
        st.link_button("Send via Gmail", _gmail_url, use_container_width=True)

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
    meeting_key = meeting.get("id") or meeting.get("title", "")
    for action in actions:
        action_card(
            action,
            editable=True,
            persist_callback=persist,
            meeting_date=meeting_date,
            key_prefix=f"{key_prefix}{meeting_key}_",
        )
