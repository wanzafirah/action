"""Capture page: upload audio / paste transcript -> run pipeline -> save meeting."""
from datetime import date

import streamlit as st

from config.constants import (
    ACTIVITY_CATEGORY_OPTIONS,
    ACTIVITY_TYPE_OPTIONS,
    DEFAULT_DEPARTMENTS,
    ORGANIZATION_TYPE_OPTIONS,
)
from config.settings import get_deepgram_key
from core.database import save_meeting
from core.pipeline import run_pipeline
from core.services import (
    append_document_to_transcript,
    extract_text_from_document,
    transcribe_audio_file,
)
from core.stakeholder_db import upsert_stakeholders_from_meeting
from ui.components import action_card, summary_panel
from utils.helpers import generate_activity_id, normalize_value, uid
from utils.tc_staff import get_tc_names, render_upload_widget


SUPPORTED_AUDIO = ["mp3", "m4a", "wav", "mp4", "mpeg", "mpga", "webm"]
SUPPORTED_DOCS = ["pdf", "docx", "xlsx", "xls", "csv"]


def _render_company_history(result: dict, meetings: list) -> None:  # noqa: ARG001
    """Show TalentCorp programme history for companies mentioned in this meeting.

    Pulls company names from:
    1. NLP pipeline named entities (organisations)
    2. External stakeholders added in the form

    Looks up each company against the TalentCorp CSV dataset (fuzzy match).
    Shows a compact card per company: name, type, sector, programmes + dates.
    If the company is not in the dataset, shows "None".
    """
    from utils.company_db import get_company_programmes

    # Collect candidate company names
    orgs: list[str] = list(
        (result.get("nlp_pipeline") or {})
        .get("named_entities", {})
        .get("organizations", [])
    )
    ext_stk = st.session_state.get("cap_ext_stakeholders", [])
    for s in ext_stk:
        org = (s.get("organisation") or "").strip()
        if org and org not in orgs:
            orgs.append(org)

    # Filter out very short / vague strings and TalentCorp itself
    # (this system belongs to TalentCorp — no need to look up its own history)
    _TC_NAMES = {"talentcorp", "talent corp", "talentcorp malaysia",
                 "talent corporation", "tc", "mynext", "mytalent"}
    orgs = [
        o for o in orgs
        if o and len(o.strip()) >= 3 and o.strip().lower() not in _TC_NAMES
    ]
    if not orgs:
        return

    # Look up all companies (deduplicate by lower name)
    seen_lower: set[str] = set()
    company_data: list[tuple[str, list[dict]]] = []
    for org in orgs:
        key = org.strip().lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        history = get_company_programmes(org)
        company_data.append((org, history))

    if not company_data:
        return

    st.markdown("### TalentCorp Programme History")
    st.caption(
        "Programme participation for companies mentioned in this meeting. "
        "Data sourced from TalentCorp records."
    )

    # Render cards — up to 3 per row
    MAX_COLS = 3
    for row_start in range(0, len(company_data), MAX_COLS):
        chunk = company_data[row_start: row_start + MAX_COLS]
        cols = st.columns(len(chunk))
        for col, (company, history) in zip(cols, chunk):
            with col:
                _render_company_card(company, history)


def _render_company_card(company: str, history: list) -> None:
    """Render a single TalentCorp history card for one extracted company name."""
    # Gradient card style
    card_style = (
        "background:#f8f9fc;border:1px solid #e2e8f0;"
        "border-radius:14px;padding:0.9rem 1rem;margin-bottom:0.6rem"
    )

    if not history:
        st.markdown(
            f"<div style='{card_style}'>"
            f"<div style='font-weight:800;font-size:0.95rem;color:#0f172a;"
            f"margin-bottom:0.25rem'>{company}</div>"
            f"<div style='font-size:0.82rem;color:#94a3b8'>"
            f"None — not found in TalentCorp records.</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # How many distinct company names were found?
    distinct = history[0].get("_distinct_count", 1)

    if distinct > 8:
        # Too many matches — name is ambiguous, don't show wrong companies
        st.markdown(
            f"<div style='{card_style}'>"
            f"<div style='font-weight:800;font-size:0.95rem;color:#0f172a;"
            f"margin-bottom:0.25rem'>{company}</div>"
            f"<div style='font-size:0.82rem;color:#b45309;margin-bottom:0.2rem'>"
            f"Name is too generic — {distinct} companies found.</div>"
            f"<div style='font-size:0.8rem;color:#6e7f96'>"
            f"Search by exact name in the Companies tab.</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # Group entries by company name — case-insensitive so "1337 VENTURES SDN BHD"
    # and "1337 Ventures Sdn Bhd" (NLP form) collapse into a single card.
    # Within each group, deduplicate programmes — same programme shown only once.
    seen_names: dict[str, dict] = {}   # canonical_lower → display info
    canonical_display: dict[str, str] = {}  # canonical_lower → prettiest display name

    for entry in history:
        cn_raw = entry.get("company_name", "")
        cn_key = cn_raw.strip().lower()
        if cn_key not in seen_names:
            if len(seen_names) >= 3:
                continue
            seen_names[cn_key] = {
                "company_type": entry.get("company_type") or "",
                "sector":       entry.get("sector")       or "",
                "programmes":   [],
                "prog_seen":    set(),
            }
            # Prefer title-cased / mixed-case name over all-caps
            canonical_display[cn_key] = cn_raw
        elif cn_raw != cn_raw.upper() and canonical_display[cn_key] == canonical_display[cn_key].upper():
            # Replace an ALL-CAPS stored name with a nicer mixed-case version
            canonical_display[cn_key] = cn_raw

        prog = (entry.get("programme") or "").strip()
        if prog and prog not in seen_names[cn_key]["prog_seen"]:
            seen_names[cn_key]["programmes"].append(prog)
            seen_names[cn_key]["prog_seen"].add(prog)

    # Build card body — one block per matching company name
    body_html = ""
    for cn_key, info in seen_names.items():
        cname  = canonical_display.get(cn_key, cn_key)
        ctype  = info["company_type"]
        sector = info["sector"]
        meta   = " &nbsp;·&nbsp; ".join(x for x in [ctype, sector] if x) or "—"

        progs = info["programmes"]
        if not progs:
            prog_lines = "<li style='color:#94a3b8'>No programme recorded</li>"
        else:
            prog_lines = "".join(
                f"<li style='margin-bottom:0.1rem'>{p}</li>" for p in progs
            )

        body_html += (
            f"<div style='margin-bottom:0.6rem'>"
            f"<div style='font-weight:700;font-size:0.9rem;color:#0f172a'>{cname}</div>"
            f"<div style='font-size:0.76rem;color:#6e7f96;margin-bottom:0.25rem'>{meta}</div>"
            f"<ul style='margin:0;padding-left:1.1rem;font-size:0.85rem;"
            f"color:#0f172a;line-height:1.5'>{prog_lines}</ul>"
            f"</div>"
        )

    more_note = ""
    if distinct > 3:
        more_note = (
            f"<div style='font-size:0.76rem;color:#6e7f96;border-top:1px solid #e2e8f0;"
            f"margin-top:0.4rem;padding-top:0.4rem'>"
            f"+ {distinct - 3} more companies match this name. "
            f"Search in Companies tab for full list.</div>"
        )

    # Header: if only 1 distinct company found, use the database name directly
    # (avoids showing two almost-identical names e.g. "1337 Ventures Sdn Bhd" +
    # "1337 VENTURES SDN BHD").  For multiple matches, use the extracted query name
    # as the header so the user knows what was detected.
    if len(seen_names) == 1:
        single_key = next(iter(seen_names))
        header_name = canonical_display.get(single_key, company)
    else:
        header_name = company

    header = (
        f"<div style='font-weight:800;font-size:0.95rem;color:#0f172a;"
        f"margin-bottom:0.5rem'>{header_name}</div>"
    )

    # When there is exactly 1 matched company, strip its name from the body
    # (it is already in the header) — keep only type, sector, programmes.
    if len(seen_names) == 1:
        single_key = next(iter(seen_names))
        info = seen_names[single_key]
        ctype  = info["company_type"]
        sector = info["sector"]
        meta   = " &nbsp;·&nbsp; ".join(x for x in [ctype, sector] if x) or "—"
        progs  = info["programmes"]
        prog_lines = "".join(
            f"<li style='margin-bottom:0.1rem'>{p}</li>" for p in progs
        ) if progs else "<li style='color:#94a3b8'>No programme recorded</li>"
        body_html = (
            f"<div style='font-size:0.76rem;color:#6e7f96;margin-bottom:0.35rem'>{meta}</div>"
            f"<ul style='margin:0;padding-left:1.1rem;font-size:0.85rem;"
            f"color:#0f172a;line-height:1.5'>{prog_lines}</ul>"
        )

    st.markdown(
        f"<div style='{card_style}'>{header}{body_html}{more_note}</div>",
        unsafe_allow_html=True,
    )


def _clear_all_inputs() -> None:
    """Reset every capture form field and the generated brief back to defaults.
    External stakeholders are intentionally preserved — clear them separately.

    The transcript text_area is reset by bumping a counter used as part of its key.
    This forces Streamlit to create a brand-new widget (empty by default) without
    needing to write directly to the widget key, which some Streamlit versions forbid.
    """
    for k in [
        "cap_category", "cap_title", "cap_date", "cap_type", "cap_org",
        "cap_depts", "cap_updated_by", "cap_tc_members",
        "cap_mode", "cap_translate", "cap_audio_upload", "cap_audio_record",
        "cap_docs", "cap_ext_excel",
        "cap_transcript", "cap_transcript_original", "cap_transcript_ver",
        "cap_ext_stakeholders",
        "cap_s_name", "cap_s_pos", "cap_s_org_query", "cap_s_org_select",
        "cap_s_phone", "cap_s_email",
        "pending_result", "cap_email_draft", "cap_email_ta",
        "cap_pdf_bytes", "cap_pdf_title",
        "cap_live_captured",
    ]:
        st.session_state.pop(k, None)
    # Bump the clear counter → the text_area gets a new key → renders empty
    st.session_state["cap_clear_n"] = st.session_state.get("cap_clear_n", 0) + 1
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


def _render_record_section(lang_choice: str) -> None:
    """Render the 'Record meeting audio' panel.

    • If DEEPGRAM_API_KEY is configured AND streamlit-webrtc + deepgram-sdk are
      installed → show live transcription with speaker labels.
    • Otherwise → fall back to the standard st.audio_input recorder + Whisper batch
      transcription.
    """
    from core.live_transcription import is_available as _live_ok, RTC_CONFIG

    dg_key = get_deepgram_key()
    live_mode = bool(dg_key) and _live_ok()

    if live_mode:
        _render_live_transcription(lang_choice, dg_key, RTC_CONFIG)
    else:
        # ── Fallback: batch Whisper ──────────────────────────────────────
        if not dg_key:
            st.caption(
                "💡 Add `DEEPGRAM_API_KEY` to your secrets for live transcription. "
                "Using standard recorder + Whisper for now."
            )
        else:
            st.caption(
                "💡 Install `streamlit-webrtc`, `deepgram-sdk`, and `av` for live "
                "transcription. Using standard recorder + Whisper for now."
            )
        audio_source = st.audio_input("Record now", key="cap_audio_record")
        if audio_source is not None:
            st.download_button(
                label="⬇ Save recording",
                data=audio_source.getvalue(),
                file_name="meeting_recording.wav",
                mime="audio/wav",
                key="cap_download_audio",
            )
            if st.button("Transcribe recording", key="cap_transcribe_rec"):
                with st.spinner("Transcribing…"):
                    try:
                        from core.services import transcribe_audio_file as _ta
                        text = _ta(audio_source, lang_choice)
                        if not text.strip():
                            st.warning(
                                "Whisper returned no speech. The file may be silent, "
                                "too short, or the VAD filter dropped everything."
                            )
                        else:
                            st.session_state.cap_transcript = text
                            st.session_state.cap_transcript_original = text
                            st.session_state["cap_transcript_ver"] = (
                                st.session_state.get("cap_transcript_ver", 0) + 1
                            )
                            st.success("Transcript ready — edit below if needed.")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Transcription failed: {exc}")


def _render_live_transcription(lang_choice: str, dg_key: str, rtc_config: dict) -> None:
    """Live transcription UI using Deepgram streaming + streamlit-webrtc."""
    from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration
    from core.live_transcription import DeepgramAudioProcessor

    dg_lang = "ms" if lang_choice == "Bahasa Melayu" else "en"

    st.markdown(
        "<div style='background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;"
        "padding:0.7rem 1rem;font-size:0.88rem;color:#166534;margin-bottom:0.6rem'>"
        "🎙 <strong>Live transcription active</strong> — transcript appears as you speak. "
        "Speakers are automatically labelled. Click <strong>START</strong> to begin."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── WebRTC streamer ──────────────────────────────────────────────────────
    webrtc_ctx = webrtc_streamer(
        key="live_asr",
        mode=WebRtcMode.SENDONLY,
        audio_processor_factory=lambda: DeepgramAudioProcessor(
            api_key=dg_key,
            language=dg_lang,
            diarize=True,
        ),
        rtc_configuration=RTCConfiguration(rtc_config),
        media_stream_constraints={"audio": True, "video": False},
        async_processing=True,
    )

    proc = webrtc_ctx.audio_processor if webrtc_ctx else None
    is_playing = bool(webrtc_ctx and webrtc_ctx.state.playing)

    # ── Live transcript box ──────────────────────────────────────────────────
    st.markdown("**Live transcript**")
    transcript_box = st.empty()

    if is_playing and proc:
        finals = proc.store.formatted()
        interim = proc.store.get_interim()
        if finals or interim:
            display = finals
            if interim:
                display += ("\n" if finals else "") + f"*{interim}*"
            transcript_box.markdown(display)
        else:
            transcript_box.caption("Listening… start speaking.")

        col_refresh, col_use = st.columns(2)
        with col_refresh:
            if st.button("🔄 Refresh transcript", key="cap_live_refresh"):
                st.rerun()
        with col_use:
            current_final = proc.store.plain_text() if proc else ""
            if current_final and st.button("✅ Use current transcript", key="cap_live_use"):
                st.session_state.cap_transcript = current_final
                st.session_state.cap_transcript_original = current_final
                st.session_state["cap_transcript_ver"] = (
                    st.session_state.get("cap_transcript_ver", 0) + 1
                )
                st.success("Transcript saved — stop recording when ready.")
                st.rerun()

    elif not is_playing and proc and proc.store.has_content():
        # Recording just stopped — auto-capture transcript
        final_text = proc.store.plain_text()
        formatted   = proc.store.formatted()

        transcript_box.markdown(formatted or final_text)

        if final_text and "cap_live_captured" not in st.session_state:
            st.session_state.cap_transcript = final_text
            st.session_state.cap_transcript_original = final_text
            st.session_state["cap_transcript_ver"] = (
                st.session_state.get("cap_transcript_ver", 0) + 1
            )
            st.session_state["cap_live_captured"] = True
            st.success("Recording stopped — transcript is ready below. Edit if needed.")
            st.rerun()

    elif not is_playing:
        transcript_box.caption("Press START above to begin recording.")
        # Clear the captured flag so next session starts fresh
        st.session_state.pop("cap_live_captured", None)

    # ── Speaker legend ───────────────────────────────────────────────────────
    with st.expander("About speaker labels", expanded=False):
        st.markdown(
            "Deepgram automatically detects different voices and labels them "
            "**Speaker 1**, **Speaker 2**, etc. The labels are based on voice tone "
            "and speaking pattern — they don't know the person's name. "
            "You can rename speakers in the transcript box below before generating the brief."
        )


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
            s_name  = st.text_input("Name", key="cap_s_name")
            s_phone = st.text_input("Phone", key="cap_s_phone")
        with sc2:
            s_pos   = st.text_input("Position", key="cap_s_pos")
            s_email = st.text_input("Email", key="cap_s_email")

        # Organisation — searchable combobox backed by TalentCorp company records
        s_org_query = st.text_input(
            "Organisation",
            key="cap_s_org_query",
            placeholder="Type to search TalentCorp records, or enter a new name…",
        )
        s_org = s_org_query.strip()
        if len(s_org) >= 3:
            try:
                from utils.company_db import search_company_names as _sc
                _matches = _sc(s_org)
            except Exception:
                _matches = []
            if _matches:
                _sel = st.selectbox(
                    "Select from TalentCorp companies (or keep typed name above)",
                    ["— Use name typed above —"] + _matches,
                    key="cap_s_org_select",
                )
                if _sel != "— Use name typed above —":
                    s_org = _sel
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
                for k in ("cap_s_name", "cap_s_pos", "cap_s_org_query", "cap_s_org_select",
                          "cap_s_phone", "cap_s_email"):
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

    # audio/transcript
    st.markdown("### Transcript")
    mode = st.radio(
        "How will you provide the meeting content?",
        ["Manual transcript", "Upload audio file", "Record meeting audio"],
        horizontal=True,
        key="cap_mode",
    )
    lang_choice = st.radio(
        "Audio language",
        ["English / Manglish", "Bahasa Melayu"],
        horizontal=True,
        key="cap_translate",
    )
    translate = lang_choice  # passed to transcribe_audio_file

    audio_source = None
    if mode == "Upload audio file":
        audio_source = st.file_uploader(
            "Audio file",
            type=SUPPORTED_AUDIO,
            key="cap_audio_upload",
            help="Supported formats: mp3, m4a, wav, mp4, webm",
        )

    elif mode == "Record meeting audio":
        _render_record_section(lang_choice)

    if audio_source is not None and st.button("Transcribe audio", key="cap_transcribe"):
        with st.spinner("Transcribing…"):
            try:
                text = transcribe_audio_file(audio_source, lang_choice)
                if not text.strip():
                    st.warning(
                        "Whisper returned no speech. The file may be silent, too short, "
                        "or the VAD filter dropped everything. Try a different file."
                    )
                else:
                    st.session_state.cap_transcript = text
                    st.session_state.cap_transcript_original = text   # save raw Whisper output
                    # Bump cap_transcript_ver so the text_area gets a brand-new key
                    # and Streamlit honours value= with the fresh transcript content.
                    st.session_state["cap_transcript_ver"] = (
                        st.session_state.get("cap_transcript_ver", 0) + 1
                    )
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
                # Bump so the text_area rebuilds with the updated value=.
                st.session_state["cap_transcript_ver"] = (
                    st.session_state.get("cap_transcript_ver", 0) + 1
                )
                st.success(f"Added content from {len(docs)} document(s).")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read document: {exc}")

    # The key includes two counters:
    #   cap_clear_n      – bumped by "Clear all inputs" to reset the widget to empty
    #   cap_transcript_ver – bumped every time a new transcript is loaded (audio or doc)
    # Together they force Streamlit to create a brand-new widget so `value=` is respected.
    _ta_key = (
        f"cap_transcript_editor"
        f"_{st.session_state.get('cap_clear_n', 0)}"
        f"_{st.session_state.get('cap_transcript_ver', 0)}"
    )
    transcript = st.text_area(
        "Transcript (editable)",
        value=st.session_state.get("cap_transcript", ""),
        height=260,
        key=_ta_key,
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
                import json as _json
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
                    # originals — Whisper raw output if transcribed, otherwise the typed transcript
                    "transcript_original": st.session_state.get("cap_transcript_original", "") or transcript,
                    "recap_original": _json.dumps(result, ensure_ascii=False),
                    "category": category,
                }
            except Exception as exc:
                st.error(f"Pipeline failed: {exc}")

    # pending result
    pending = st.session_state.get("pending_result")
    if pending:
        st.markdown("---")
        result = pending["result"]
        summary_panel(result)

        #company history table
        _render_company_history(result, meetings)

        # email copy button
        if st.button("Copy Meeting Summary Email", key="cap_email_btn"):
            st.session_state.cap_email_draft = _build_email_text(pending, result)

        if st.session_state.get("cap_email_draft"):
            st.text_area(
                "Email draft — copy and paste to send",
                value=st.session_state.cap_email_draft,
                height=300,
                key="cap_email_ta",
            )
            import urllib.parse as _up
            _title = (pending.get("title") or result.get("title") or "Meeting").strip()
            _subject = _up.quote(f"Meeting Follow-Up: {_title}")
            _body = _up.quote(st.session_state.cap_email_draft)
            _gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&su={_subject}&body={_body}"
            st.link_button("Send via Gmail", _gmail_url, use_container_width=True)

        st.markdown("### Action items")
        st.caption("Review and edit the AI-generated tasks before saving.")
        actions = result.get("action_items", [])
        if not actions:
            st.info("No action items were extracted from this transcript.")
        for idx, a in enumerate(actions):
            a.setdefault("id", f"act-{uid()}-{idx}")
            action_card(a, editable=True, persist_callback=lambda: None)

        #download PDF
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
    objective  = result.get("objective", "") or "Not provided"

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

    actions_block = "\n".join(action_lines) if action_lines else "  No action items recorded."

    return (
        f"Dear colleagues,\n\n"
        f"Please find below the meeting monitoring report for today, for your reference.\n\n"
        f"MEDIA MONITORING REPORT\n"
        f"Date: {date_display}\n\n"
        f"Meeting: {title}\n\n"
        f"Objective:\n{objective}\n\n"
        f"Summary:\n{summary}\n\n"
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
        # Original snapshots for comparison
        "transcript_original": pending.get("transcript_original", ""),
        "recap_original": pending.get("recap_original", ""),
    }
