"""Stakeholders directory — external contacts from all meetings."""
from __future__ import annotations

from datetime import date

import streamlit as st

from core.stakeholder_db import load_external_stakeholders, save_external_stakeholders
from utils.helpers import uid

_TODAY = date.today().isoformat()


def render() -> None:
    st.markdown("## Stakeholders")
    st.caption("External contacts from outside TalentCorp. Search by name or organisation.")

    # Load from disk + merge any from session_state meetings
    all_s = load_external_stakeholders()
    meetings = st.session_state.get("meetings", [])
    for m in meetings:
        for s in (m.get("externalStakeholders") or []):
            existing_keys = {
                (x.get("name", "").lower(), x.get("organisation", "").lower())
                for x in all_s
            }
            key = (s.get("name", "").lower(), s.get("organisation", "").lower())
            if key not in existing_keys and s.get("name"):
                all_s.append({**s, "meeting_ids": [m.get("id", "")], "date_added": _TODAY})

    # ── Search + Add button ─────────────────────────────────────────
    col_search, col_add = st.columns([3, 1])
    with col_search:
        search = st.text_input(
            "Search",
            placeholder="Search by name or organisation…",
            key="stk_search",
            label_visibility="collapsed",
        )
    with col_add:
        if st.button("Add New Stakeholder", use_container_width=True, key="stk_open_add"):
            st.session_state.stk_show_add = not st.session_state.get("stk_show_add", False)

    # ── Add form ────────────────────────────────────────────────────
    if st.session_state.get("stk_show_add"):
        with st.container():
            st.markdown(
                "<div style='background:#f8f9fc;border:1px solid #d8dceb;border-radius:16px;"
                "padding:1rem 1.1rem;margin-bottom:0.8rem'>",
                unsafe_allow_html=True,
            )
            st.markdown("#### Add Stakeholder")
            fc1, fc2 = st.columns(2)
            with fc1:
                n_name  = st.text_input("Name *",         key="stk_n_name")
                n_org   = st.text_input("Organisation *", key="stk_n_org")
                n_phone = st.text_input("Phone",          key="stk_n_phone")
            with fc2:
                n_pos   = st.text_input("Position",       key="stk_n_pos")
                n_email = st.text_input("Email",          key="stk_n_email")

            if st.button("Save Stakeholder", key="stk_save_new"):
                if n_name.strip():
                    new_entry = {
                        "id":           uid(),
                        "name":         n_name.strip(),
                        "position":     n_pos.strip(),
                        "organisation": n_org.strip(),
                        "phone":        n_phone.strip(),
                        "email":        n_email.strip(),
                        "date_added":   _TODAY,
                        "meeting_ids":  [],
                    }
                    all_s.append(new_entry)
                    save_external_stakeholders(all_s)
                    for k in ("stk_n_name", "stk_n_pos", "stk_n_org", "stk_n_phone", "stk_n_email"):
                        st.session_state.pop(k, None)
                    st.session_state.stk_show_add = False
                    st.success(f"Added {new_entry['name']}.")
                    st.rerun()
                else:
                    st.warning("Name is required.")
            st.markdown("</div>", unsafe_allow_html=True)

    if not all_s:
        st.info("No external stakeholders yet. Add them when capturing a meeting, or click 'Add New Stakeholder' above.")
        return

    # ── KPIs ────────────────────────────────────────────────────────
    orgs = {s.get("organisation", "") for s in all_s if s.get("organisation")}
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>Total contacts</div>"
            f"<div class='kpi-value' style='color:#364C84'>{len(all_s)}</div>"
            f"<div class='kpi-subtitle'>External stakeholders</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>Organisations</div>"
            f"<div class='kpi-value' style='color:#0f766e'>{len(orgs)}</div>"
            f"<div class='kpi-subtitle'>Unique companies / agencies</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # ── Filter ──────────────────────────────────────────────────────
    needle = search.strip().lower()
    filtered = [
        s for s in all_s
        if not needle
        or needle in s.get("name", "").lower()
        or needle in s.get("organisation", "").lower()
        or needle in s.get("position", "").lower()
    ]

    if not filtered:
        st.info(f"No stakeholders match '{search.strip()}'.")
        return

    # ── Table ───────────────────────────────────────────────────────
    _render_table(filtered, all_s)


def _render_table(filtered: list, all_s: list) -> None:
    """Render stakeholders as a styled HTML table with a Remove button per row."""

    # Build meeting title lookup
    meetings = st.session_state.get("meetings", [])
    mtg_lookup = {m.get("id"): m.get("title", "Untitled") for m in meetings}

    # Table header
    header = (
        "<div style='overflow-x:auto'>"
        "<table style='width:100%;border-collapse:collapse;font-size:0.88rem'>"
        "<thead>"
        "<tr style='background:#364C84;color:#ffffff'>"
        "<th style='padding:0.6rem 0.8rem;text-align:left;border-radius:8px 0 0 0'>Name</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left'>Position</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left'>Organisation</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left'>Phone</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left'>Email</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left'>Date Added</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left;border-radius:0 8px 0 0'>Meetings</th>"
        "</tr></thead><tbody>"
    )

    rows_html = ""
    for i, s in enumerate(filtered):
        bg = "#ffffff" if i % 2 == 0 else "#f8f9fc"
        mtg_ids   = s.get("meeting_ids", [])
        mtg_names = ", ".join(mtg_lookup.get(mid, "") for mid in mtg_ids if mtg_lookup.get(mid))
        date_added = s.get("date_added", "—")
        email = s.get("email", "")
        email_html = f"<a href='mailto:{email}' style='color:#364C84'>{email}</a>" if email else "—"

        rows_html += (
            f"<tr style='background:{bg};border-bottom:1px solid #e2e8f0'>"
            f"<td style='padding:0.55rem 0.8rem;font-weight:700;color:#0f172a'>{s.get('name','')}</td>"
            f"<td style='padding:0.55rem 0.8rem;color:#27425D'>{s.get('position','') or '—'}</td>"
            f"<td style='padding:0.55rem 0.8rem;color:#27425D'>{s.get('organisation','') or '—'}</td>"
            f"<td style='padding:0.55rem 0.8rem;color:#27425D'>{s.get('phone','') or '—'}</td>"
            f"<td style='padding:0.55rem 0.8rem'>{email_html}</td>"
            f"<td style='padding:0.55rem 0.8rem;color:#6e7f96;white-space:nowrap'>{date_added}</td>"
            f"<td style='padding:0.55rem 0.8rem;color:#6e7f96;font-size:0.82rem'>{mtg_names or '—'}</td>"
            f"</tr>"
        )

    footer = "</tbody></table></div>"
    st.markdown(header + rows_html + footer, unsafe_allow_html=True)

    # Remove buttons below table (one per row)
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    st.caption("Select a row to remove:")
    cols = st.columns(min(len(filtered), 6))
    for i, s in enumerate(filtered):
        col_idx = i % len(cols)
        if cols[col_idx].button(
            f"Remove {s.get('name', '')}",
            key=f"stk_del_{s.get('id',i)}",
            use_container_width=True,
        ):
            updated = [x for x in all_s if x.get("id") != s.get("id")]
            save_external_stakeholders(updated)
            st.rerun()
