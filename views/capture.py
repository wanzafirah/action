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
from ui.components import action_card, summary_panel
from utils.helpers import generate_activity_id, uid


SUPPORTED_AUDIO = ["mp3", "m4a", "wav", "mp4", "mpeg", "mpga", "webm"]
SUPPORTED_DOCS = ["pdf", "docx", "xlsx", "xls", "csv"]


def _clear_all_inputs() -> None:
    """Reset every capture form field back to defaults."""
    keys = [
        "cap_category", "cap_title", "cap_date", "cap_type", "cap_org",
        "cap_depts", "cap_updated_by", "cap_stakeholders",
        "cap_mode", "cap_translate", "cap_audio_upload", "cap_audio_record",
        "cap_docs", "cap_transcript", "cap_transcript_editor",
        "pending_result",
    ]
    for k in keys:
        st.session_state.pop(k, None)
    # Reset ID field to empty (don't pop — we always read it via _cap_id_val)
    st.session_state._cap_id_val = ""
    st.session_state.pop("cap_email_draft", None)
    st.session_state.pop("cap_pdf_bytes", None)
    st.session_state.pop("cap_pdf_title", None)


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    # Page title — no hero banner per user request
    st.markdown("## Capture a Meeting")
    st.caption("Record, upload, or paste your transcript to generate a structured brief.")

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
            placeholder="Type your own ID, or click Generate ID →",
        )
        st.session_state._cap_id_val = activity_id   # keep in sync with user edits
    with btn_col:
        st.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
        st.button("Generate ID", key="cap_gen_id",
                  on_click=_gen_id_callback, use_container_width=True)

    departments = st.multiselect("Departments involved", DEFAULT_DEPARTMENTS, key="cap_depts")
    stakeholders_raw = st.text_input("Stakeholders (comma-separated)", key="cap_stakeholders")
    updated_by = st.text_input("Report by", key="cap_updated_by")

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
            "Stakeholders": stakeholders_raw,
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
                    "stakeholders": [s.strip() for s in stakeholders_raw.split(",") if s.strip()],
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
        if st.button("📧 Copy Meeting Summary Email", key="cap_email_btn"):
            st.session_state.cap_email_draft = _build_email_text(pending, result)

        if st.session_state.get("cap_email_draft"):
            st.text_area(
                "Email draft — copy and paste to send",
                value=st.session_state.cap_email_draft,
                height=300,
                key="cap_email_ta",
            )

        st.markdown("### Action items")
        actions = result.get("action_items", [])
        if not actions:
            st.info("No action items were extracted from this transcript.")
        for idx, a in enumerate(actions):
            a.setdefault("id", f"act-{uid()}-{idx}")
            action_card(a)

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
                label="⬇ Download Brief (PDF)",
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
                try:
                    save_meeting(meeting)
                    st.success(f"Saved meeting {meeting['activityId']}.")
                except Exception as exc:
                    st.warning(f"Saved locally but Supabase sync failed: {exc}")
                _clear_all_inputs()
                st.rerun()
        with col_discard:
            if st.button("Discard", key="cap_discard"):
                st.session_state.pop("pending_result", None)
                st.session_state.pop("cap_email_draft", None)
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
        "stakeholders": pending["stakeholders"],
        "companies": [],
        "keyDecisions": result.get("key_decisions", []),
        "discussionPoints": result.get("discussion_points", []),
        "actions": result.get("action_items", []),
    }
