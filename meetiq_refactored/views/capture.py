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


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    st.markdown(
        "<div class='hero-shell'><h1>Capture a meeting</h1>"
        "<p>Record, upload, or paste — let MeetIQ generate the brief for you.</p></div>",
        unsafe_allow_html=True,
    )

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
        activity_id = st.text_input(
            "Activity ID",
            value=st.session_state.get("cap_activity_id") or generate_activity_id(category, meeting_date, meetings),
            key="cap_activity_id",
        )

    departments = st.multiselect("Departments involved", DEFAULT_DEPARTMENTS, key="cap_depts")
    updated_by = st.text_input("Report by", key="cap_updated_by")
    stakeholders_raw = st.text_input("Stakeholders (comma-separated)", key="cap_stakeholders")

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
        audio_source = st.file_uploader("Audio file", type=SUPPORTED_AUDIO, key="cap_audio_upload")
    elif mode == "Record meeting audio":
        audio_source = st.audio_input("Record now", key="cap_audio_record")

    if audio_source is not None and st.button("Transcribe audio", key="cap_transcribe"):
        with st.spinner("Transcribing… first run may download the Whisper model."):
            try:
                st.session_state.cap_transcript = transcribe_audio_file(audio_source, translate)
                st.success("Transcript ready — edit below if needed.")
            except Exception as exc:
                st.error(f"Transcription failed: {exc}")

    # ----- Supporting documents -----
    docs = st.file_uploader(
        "Supporting documents (optional)",
        type=SUPPORTED_DOCS,
        accept_multiple_files=True,
        key="cap_docs",
    )
    if docs and st.button("Attach document content", key="cap_attach_docs"):
        try:
            current = st.session_state.get("cap_transcript", "")
            for d in docs:
                current = append_document_to_transcript(current, extract_text_from_document(d))
            st.session_state.cap_transcript = current
            st.success(f"Added content from {len(docs)} document(s).")
        except Exception as exc:
            st.error(f"Could not read document: {exc}")

    transcript = st.text_area(
        "Transcript (editable)",
        value=st.session_state.get("cap_transcript", ""),
        height=260,
        key="cap_transcript_editor",
    )
    st.session_state.cap_transcript = transcript

    # ----- Generate -----
    if st.button("Generate brief", type="primary", disabled=not transcript.strip(), key="cap_generate"):
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
        with st.spinner("Analysing transcript with Ollama…"):
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

        st.markdown("### Action items")
        actions = result.get("action_items", [])
        if not actions:
            st.info("No action items were extracted from this transcript.")
        for idx, a in enumerate(actions):
            a.setdefault("id", f"act-{uid()}-{idx}")
            action_card(a)

        col_save, col_clear = st.columns(2)
        with col_save:
            if st.button("Save meeting", type="primary", key="cap_save"):
                meeting = _build_meeting_record(pending)
                st.session_state.meetings.append(meeting)
                try:
                    save_meeting(meeting)
                    st.success(f"Saved meeting {meeting['activityId']}.")
                except Exception as exc:
                    st.warning(f"Saved locally but Supabase sync failed: {exc}")
                st.session_state.pop("pending_result", None)
                st.session_state.cap_transcript = ""
                st.session_state.pop("cap_activity_id", None)
                st.rerun()
        with col_clear:
            if st.button("Discard", key="cap_discard"):
                st.session_state.pop("pending_result", None)
                st.rerun()


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
