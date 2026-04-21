"""Capture page: upload audio / paste transcript -> run pipeline -> save meeting."""
from datetime import date

import streamlit as st

from config.constants import (
    ACTIVITY_CATEGORY_OPTIONS,
    ACTIVITY_TYPE_OPTIONS,
    DEFAULT_DEPARTMENTS,
    ORGANIZATION_TYPE_OPTIONS,
)
from core.database import save_meeting
from core.pipeline import run_pipeline
from core.services import (
    append_document_to_transcript,
    extract_text_from_document,
    transcribe_audio_file,
)
from core.stakeholder_db import upsert_stakeholders_from_meeting
from ui.components import action_card, summary_panel
from utils.helpers import generate_activity_id, uid
from utils.tc_staff import get_tc_names, render_upload_widget


SUPPORTED_AUDIO = ["mp3", "m4a", "wav", "mp4", "mpeg", "mpga", "webm"]
SUPPORTED_DOCS = ["pdf", "docx", "xlsx", "xls", "csv"]


def _clear_all_inputs() -> None:
    """Reset every capture form field and the generated brief back to defaults.
    External stakeholders are intentionally preserved — clear them separately.
    """
    keys = [
        "cap_category", "cap_title", "cap_date", "cap_type", "cap_org",
        "cap_depts", "cap_updated_by", "cap_tc_members",
        "cap_mode", "cap_translate", "cap_audio_upload", "cap_audio_record",
        "cap_docs", "cap_transcript", "cap_transcript_editor",
        "cap_ext_excel",
        # generated brief
        "pending_result", "cap_email_draft", "cap_email_ta",
        "cap_pdf_bytes", "cap_pdf_title",
    ]
    for k in keys:
        st.session_state.pop(k, None)
    st.session_state._cap_id_val = ""
    # Clear any leftover action-card widget keys from a previous brief
    stale = [k for k in st.session_state if k.startswith((
        "text_", "status_", "owner_", "dept_", "dl_mode_", "dl_",
        "btn_idea_", "idea_open_", "idea_",
    ))]
    for k in stale:
        st.session_state.pop(k, None)


def _clear_stakeholders() -> None:
    """Remove all external stakeholders from the current capture form."""
    st.session_state.cap_ext_stakeholders = []


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    # Page title — no hero banner per user request
    st.markdown("## Capture a Meeting")
    st.caption("Record, upload or paste your transcript to generate a structured brief.")

    # ----- Activity metadata -----
    st.markdown("### Activity details")
    col_a, col_b = st.columns(2)
    with col_a:
        category = st.selectbox("Category", ACTIVITY_CATEGORY_OPTIONS, key="cap_category")
        title = st.text_input("Activity title", key="cap_title")
        meeting_date = st.date_input("Meeting date", value=date.today(), key="cap_date")
    with col_b:
        activity_type = st.selectbox("Meeting type", ACTIVITY_TYPE_OPTIONS, key="cap_type")
        organization_type = st.selectbox("Organization type", ORGANIZATION_TYPE_OPTIONS, key="cap_org")

    # ----- Activity ID — own full-width row; keyless input avoids session-state conflict -----
    if "_cap_id_val" not in st.session_state:
        st.session_state._cap_id_val = ""   # starts empty; user types or generates

    def _gen_id_callback():
        """on_click fires BEFORE re-render — safe to update _cap_id_val here."""
        from datetime import date as _date
        cat  = st.session_state.get("cap_category", "Internal Meeting")
        dt   = st.session_state.get("cap_date", _date.today())
        mtgs = st.session_state.get("meetings", [])
        st.session_state._cap_id_val = generate_activity_id(cat, dt, mtgs)

    id_col, btn_col = st.columns([4, 1])
    with id_col:
        # No key= on this text_input so Streamlit doesn't write-back and conflict
        # with _cap_id_val on the same rerun. We persist user typing manually.
        activity_id = st.text_input(
            "Activity ID",
            value=st.session_state._cap_id_val,
            placeholder="Type your own ID or click Generate ID →",
        )
        st.session_state._cap_id_val = activity_id   # keep in sync with user edits
    with btn_col:
        st.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
        st.button("Generate ID", key="cap_gen_id",
                  on_click=_gen_id_callback, use_container_width=True)

    departments = st.multiselect("Departments involved", DEFAULT_DEPARTMENTS, key="cap_depts")

    # TC staff — show upload widget if file not available (e.g. Streamlit Cloud)
    render_upload_widget()
    tc_names = get_tc_names()

    col_tc, col_rb = st.columns(2)
    with col_tc:
        tc_members = st.multiselect(
            "Other TC Member",
            options=tc_names,
            key="cap_tc_members",
            placeholder="Search and select TC staff…",
        )
    with col_rb:
        report_by_options = [""] + tc_names
        rb_default = st.session_state.get("cap_updated_by", "")
        rb_index = report_by_options.index(rb_default) if rb_default in report_by_options else 0
        updated_by = st.selectbox(
            "Report by",
            options=report_by_options,
            index=rb_index,
            key="cap_updated_by",
            format_func=lambda x: x if x else "— Select staff member —",
        )

    # ----- External Stakeholders -----
    st.markdown("### Stakeholders")
    st.caption("People from outside TalentCorp involved in this meeting.")

    if "cap_ext_stakeholders" not in st.session_state:
        st.session_state.cap_ext_stakeholders = []

    # Upload Excel option
    ext_excel = st.file_uploader(
        "Upload stakeholder list (Excel — columns: Name, Position, Organisation, Phone, Email)",
        type=["xlsx", "xls"],
        key="cap_ext_excel",
    )
    if ext_excel and st.button("Import from Excel", key="cap_import_ext"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(ext_excel, read_only=True, data_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            _header = next(rows_iter, None)  # skip header
            imported = 0
            for row in rows_iter:
                name = str(row[0]).strip() if row[0] else ""
                if not name:
                    continue
                st.session_state.cap_ext_stakeholders.append({
                    "id":           uid(),
                    "name":         name,
                    "position":     str(row[1]).strip() if len(row) > 1 and row[1] else "",
                    "organisation": str(row[2]).strip() if len(row) > 2 and row[2] else "",
                    "phone":        str(row[3]).strip() if len(row) > 3 and row[3] else "",
                    "email":        str(row[4]).strip() if len(row) > 4 and row[4] else "",
                })
                imported += 1
            st.success(f"Imported {imported} stakeholder(s).")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not read Excel: {exc}")

    # Manual add form
    with st.expander("Add stakeholder manually", expanded=False):
        sc1, sc2 = st.columns(2)
        with sc1:
            s_name = st.text_input("Name", key="cap_s_name")
            s_org  = st.text_input("Organisation", key="cap_s_org")
            s_phone = st.text_input("Phone", key="cap_s_phone")
        with sc2:
            s_pos   = st.text_input("Position", key="cap_s_pos")
            s_email = st.text_input("Email", key="cap_s_email")
        if st.button("Add Stakeholder", key="cap_add_ext"):
            if s_name.strip():
                st.session_state.cap_ext_stakeholders.append({
                    "id":           uid(),
                    "name":         s_name.strip(),
                    "position":     s_pos.strip(),
                    "organisation": s_org.strip(),
                    "phone":        s_phone.strip(),
                    "email":        s_email.strip(),
                })
                for k in ("cap_s_name", "cap_s_pos", "cap_s_org", "cap_s_phone", "cap_s_email"):
                    st.session_state.pop(k, None)
                st.rerun()
            else:
                st.warning("Name is required.")

    # Show added stakeholders
    ext_stk = st.session_state.cap_ext_stakeholders
    if ext_stk:
        stk_hdr, stk_clear = st.columns([5, 1])
        with stk_hdr:
            st.caption(f"{len(ext_stk)} stakeholder(s) added to this meeting.")
        with stk_clear:
            if st.button("Clear all", key="cap_clear_ext_all", help="Remove all stakeholders from this form"):
                _clear_stakeholders()
                st.rerun()

        for i, s in enumerate(ext_stk):
            col_info, col_del = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"<div style='background:#f8f9fc;border:1px solid #e2e8f0;border-radius:10px;"
                    f"padding:0.45rem 0.8rem;font-size:0.88rem;color:#0f172a'>"
                    f"<strong>{s['name']}</strong>"
                    f"{' · ' + s['position'] if s['position'] else ''}"
                    f"{' · ' + s['organisation'] if s['organisation'] else ''}"
                    f"{' · ' + s['phone'] if s['phone'] else ''}"
                    f"{' · ' + s['email'] if s['email'] else ''}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with col_del:
                if st.button("Remove", key=f"cap_del_ext_{i}"):
                    st.session_state.cap_ext_stakeholders.pop(i)
                    st.rerun()

    # ----- Audio / transcript -----
    st.markdown("### Transcript")
    mode = st.radio(
        "How will you provide the meeting content?",
        ["Manual transcript", "Upload audio file", "Record meeting audio"],
        horizontal=True,
        key="cap_mode",
    )
    translate = (
        st.radio(
            "Transcript language",
            ["Translate to English", "Keep spoken language"],
            horizontal=True,
            key="cap_translate",
        )
        == "Translate to English"
    )

    audio_source = None
    if mode == "Upload audio file":
        audio_source = st.file_uploader(
            "Audio file",
            type=SUPPORTED_AUDIO,
            key="cap_audio_upload",
            help="Supported formats: mp3, m4a, wav, mp4, webm",
        )
    elif mode == "Record meeting audio":
        audio_source = st.audio_input("Record now", key="cap_audio_record")

    if audio_source is not None and st.button("Transcribe audio", key="cap_transcribe"):
        with st.spinner("Transcribing… first run may download the Whisper model."):
            try:
                text = transcribe_audio_file(audio_source, translate)
                st.session_state.cap_transcript = text
                st.session_state.cap_transcript_editor = text
                st.success("Transcript ready — edit below if needed.")
                st.rerun()
            except Exception as exc:
                st.error(f"Transcription failed: {exc}")

    # ----- Supporting documents -----
    docs = st.file_uploader(
        "Supporting documents (optional)",
        type=SUPPORTED_DOCS,
        accept_multiple_files=True,
        key="cap_docs",
    )
    if docs:
        if st.button("Attach document content", key="cap_attach_docs"):
            try:
                current = st.session_state.get("cap_transcript", "")
                for d in docs:
                    current = append_document_to_transcript(
                        current, extract_text_from_document(d)
                    )
                st.session_state.cap_transcript = current
                # Also update the text_area widget key so it re-renders with new value
                st.session_state.cap_transcript_editor = current
                st.success(f"Added content from {len(docs)} document(s).")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read document: {exc}")

    transcript = st.text_area(
        "Transcript (editable)",
        value=st.session_state.get("cap_transcript", ""),
        height=260,
        key="cap_transcript_editor",
    )
    st.session_state.cap_transcript = transcript

    # ----- Action row: Generate + Clear -----
    btn_gen, btn_clear = st.columns([2, 1])
    with btn_gen:
        do_generate = st.button(
            "Generate brief",
            type="primary",
            key="cap_generate",
        )
    with btn_clear:
        if st.button("Clear all inputs", key="cap_clear_all"):
            _clear_all_inputs()
            st.rerun()

    if do_generate and not transcript.strip():
        st.warning("Please paste or type a transcript first.")
    elif do_generate:
        metadata = {
            "Title": title,
            "Category": category,
            "Activity Type": activity_type,
            "Organization Type": organization_type,
            "Departments": ", ".join(departments),
            "Report By": updated_by,
            "TC Members": ", ".join(st.session_state.get("cap_tc_members", [])),
            "Meeting Date": meeting_date.isoformat(),
            "Activity ID": activity_id,
        }
        with st.spinner("Analyzing transcript…"):
            try:
                result = run_pipeline(transcript, metadata)
                st.session_state.pending_result = {
                    "result": result,
                    "metadata": metadata,
                    "activity_id": activity_id,
                    "meeting_date": meeting_date.isoformat(),
                    "departments": departments,
                    "tc_members": list(st.session_state.get("cap_tc_members", [])),
                    "external_stakeholders": list(st.session_state.get("cap_ext_stakeholders", [])),
                    "updated_by": updated_by,
                    "transcript": transcript,
                    "category": category,
                }
            except Exception as exc:
                st.error(f"Pipeline failed: {exc}")

    # ----- Show pending result -----
    pending = st.session_state.get("pending_result")
    if pending:
        st.markdown("---")
        result = pending["result"]
        summary_panel(result)

        # ── Copy Email button ─────────────────────────────────────────
        if st.button("Copy Meeting Summary Email", key="cap_email_btn"):
            st.session_state.cap_email_draft = _build_email_text(pending, result)

        if st.session_state.get("cap_email_draft"):
            st.text_area(
                "Email draft — copy and paste to send",
                value=st.session_state.cap_email_draft,
                height=300,
                key="cap_email_ta",
            )

        st.markdown("### Action items")
        st.caption("Review and edit the AI-generated tasks before saving.")
        actions = result.get("action_items", [])
        if not actions:
            st.info("No action items were extracted from this transcript.")
        for idx, a in enumerate(actions):
            a.setdefault("id", f"act-{uid()}-{idx}")
            action_card(a, editable=True, persist_callback=lambda: None)

        # ── Download PDF ──────────────────────────────────────────────
        # Cache PDF bytes in session_state so the download button always has data
        if "cap_pdf_bytes" not in st.session_state:
            try:
                from utils.export import generate_meeting_pdf
                _pdf_record = _build_meeting_record(pending)
                st.session_state.cap_pdf_bytes = generate_meeting_pdf(_pdf_record)
                st.session_state.cap_pdf_title = "".join(
                    c for c in (result.get("title") or "meeting") if c.isalnum() or c in " _-"
                )[:40].strip()
            except Exception as _e:
                st.session_state.cap_pdf_bytes = b""
                st.caption(f"PDF generation failed: {_e}")

        if st.session_state.get("cap_pdf_bytes"):
            st.download_button(
                label="Download Brief (PDF)",
                data=st.session_state.cap_pdf_bytes,
                file_name=f"{st.session_state.get('cap_pdf_title', 'meeting')}.pdf",
                mime="application/pdf",
                key="cap_dl_pdf",
            )

        col_save, col_discard = st.columns(2)
        with col_save:
            if st.button("Save meeting", type="primary", key="cap_save"):
                meeting = _build_meeting_record(pending)
                st.session_state.meetings.append(meeting)
                # Sync external stakeholders to central directory
                try:
                    upsert_stakeholders_from_meeting(
                        meeting["id"],
                        pending.get("external_stakeholders", []),
                    )
                except Exception:
                    pass
                try:
                    save_meeting(meeting)
                    st.success(f"Saved meeting {meeting['activityId']}.")
                except Exception as exc:
                    st.warning(f"Saved locally but Supabase sync failed: {exc}")
                _clear_all_inputs()
                st.rerun()
        with col_discard:
            if st.button("Discard brief", key="cap_discard"):
                # Clear the generated brief and all related state
                for _k in ["pending_result", "cap_email_draft", "cap_email_ta",
                           "cap_pdf_bytes", "cap_pdf_title"]:
                    st.session_state.pop(_k, None)
                # Clear leftover action-card widget keys
                for _k in [k for k in st.session_state if k.startswith((
                    "text_", "status_", "owner_", "dept_", "dl_mode_", "dl_",
                    "btn_idea_", "idea_open_", "idea_",
                ))]:
                    st.session_state.pop(_k, None)
                st.rerun()


def _build_email_text(pending: dict, result: dict) -> str:
    """Format the generated brief as a copy-paste email."""
    from datetime import datetime as _dt
    title      = result.get("title") or pending["metadata"].get("Title") or "Meeting Recap"
    date_str   = pending.get("meeting_date", "")
    report_by  = pending.get("updated_by", "") or "The Meeting Organizer"
    summary    = result.get("summary", "")
    decisions  = result.get("key_decisions") or []

    try:
        date_display = _dt.strptime(date_str, "%Y-%m-%d").strftime("%A, %d %B %Y")
    except Exception:
        date_display = date_str

    action_lines = []
    for i, a in enumerate(result.get("action_items", []) or [], 1):
        text     = a.get("text", "")
        owner    = a.get("owner", "Not stated")
        deadline = a.get("deadline", "Not stated")
        action_lines.append(f"  {i}. {text}\n     Owner: {owner} | Deadline: {deadline}")

    decision_lines = "\n".join(f"  - {d}" for d in decisions) if decisions else "  None recorded."
    actions_block  = "\n".join(action_lines) if action_lines else "  No action items recorded."

    return (
        f"Dear colleagues,\n\n"
        f"Please find below the meeting monitoring report for today, for your reference.\n\n"
        f"MEDIA MONITORING REPORT\n"
        f"Date: {date_display}\n\n"
        f"Meeting: {title}\n\n"
        f"Summary:\n{summary}\n\n"
        f"Key Decisions:\n{decision_lines}\n\n"
        f"Action Items:\n{actions_block}\n\n"
        f"Regards,\n{report_by}"
    )


def _build_meeting_record(pending: dict) -> dict:
    """Flatten the pipeline result + form fields into a stored meeting dict."""
    result = pending["result"]
    return {
        "id": uid(),
        "user_id": pending["updated_by"],
        "title": result.get("title") or pending["metadata"].get("Title") or "Untitled",
        "date": pending["meeting_date"],
        "category": pending["category"],
        "summary": result.get("summary", ""),
        "objective": result.get("objective", ""),
        "outcome": result.get("outcome", ""),
        "followUp": bool(result.get("follow_up")),
        "followUpReason": result.get("follow_up_reason", ""),
        "transcript": pending["transcript"],
        "deptName": ", ".join(pending["departments"]),
        "department": ", ".join(pending["departments"]),
        "activityId": pending["activity_id"],
        "meetingID": pending["activity_id"],
        "stakeholders": pending.get("tc_members", []),
        "externalStakeholders": pending.get("external_stakeholders", []),
        "companies": [],
        "keyDecisions": result.get("key_decisions", []),
        "discussionPoints": result.get("discussion_points", []),
        "actions": result.get("action_items", []),
    }
