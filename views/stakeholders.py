"""Stakeholders directory — external contacts from all meetings."""
from __future__ import annotations

import streamlit as st

from core.stakeholder_db import load_external_stakeholders, save_external_stakeholders
from utils.helpers import uid


def render() -> None:
    st.markdown("## Stakeholders")
    st.caption("External contacts from outside TalentCorp. Search by name or organisation.")

    # Load from disk + merge any in session that aren't saved yet
    all_s = load_external_stakeholders()

    # Also pull external stakeholders from meetings already in session_state
    # (in case they were captured but not yet persisted)
    meetings = st.session_state.get("meetings", [])
    for m in meetings:
        for s in (m.get("externalStakeholders") or []):
            key = (s.get("name", "").lower(), s.get("organisation", "").lower())
            existing_keys = {
                (x.get("name", "").lower(), x.get("organisation", "").lower())
                for x in all_s
            }
            if key not in existing_keys and s.get("name"):
                all_s.append({**s, "meeting_ids": [m.get("id", "")]})

    # ── Search bar ──────────────────────────────────────────────────
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
        st.markdown("---")
        st.markdown("#### Add Stakeholder")
        fc1, fc2 = st.columns(2)
        with fc1:
            n_name = st.text_input("Name *", key="stk_n_name")
            n_org  = st.text_input("Organisation *", key="stk_n_org")
            n_phone = st.text_input("Phone", key="stk_n_phone")
        with fc2:
            n_pos   = st.text_input("Position", key="stk_n_pos")
            n_email = st.text_input("Email", key="stk_n_email")

        if st.button("Save Stakeholder", key="stk_save_new"):
            if n_name.strip():
                new_entry = {
                    "id":           uid(),
                    "name":         n_name.strip(),
                    "position":     n_pos.strip(),
                    "organisation": n_org.strip(),
                    "phone":        n_phone.strip(),
                    "email":        n_email.strip(),
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
        st.markdown("---")

    if not all_s:
        st.info("No external stakeholders yet. Add them when capturing a meeting, or click 'Add New Stakeholder' above.")
        return

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

    # ── KPIs ────────────────────────────────────────────────────────
    orgs = {s.get("organisation", "") for s in all_s if s.get("organisation")}
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"<div class='kpi-card'>"
            f"<div class='kpi-label'>Total contacts</div>"
            f"<div class='kpi-value' style='color:#364C84'>{len(all_s)}</div>"
            f"<div class='kpi-subtitle'>External stakeholders</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div class='kpi-card'>"
            f"<div class='kpi-label'>Organisations</div>"
            f"<div class='kpi-value' style='color:#0f766e'>{len(orgs)}</div>"
            f"<div class='kpi-subtitle'>Unique companies / agencies</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # ── Group by organisation ────────────────────────────────────────
    from collections import defaultdict
    org_map: dict = defaultdict(list)
    for s in filtered:
        org_map[s.get("organisation") or "Unknown Organisation"].append(s)

    for org in sorted(org_map.keys()):
        st.markdown(
            f"<div style='font-size:0.82rem;font-weight:800;color:#364C84;"
            f"text-transform:uppercase;letter-spacing:0.06em;margin:0.9rem 0 0.3rem'>"
            f"{org}</div>",
            unsafe_allow_html=True,
        )
        for s in org_map[org]:
            _render_stakeholder_card(s, all_s)


def _render_stakeholder_card(s: dict, all_s: list) -> None:
    s_id   = s.get("id", "")
    name   = s.get("name", "Unnamed")
    pos    = s.get("position", "")
    org    = s.get("organisation", "")
    phone  = s.get("phone", "")
    email  = s.get("email", "")
    mtgs   = s.get("meeting_ids", [])

    meetings = st.session_state.get("meetings", [])
    mtg_titles = []
    for m in meetings:
        if m.get("id") in mtgs:
            mtg_titles.append(m.get("title", "Untitled"))

    with st.expander(f"{name}  ·  {pos or org or 'External stakeholder'}", expanded=False):
        col_info, col_action = st.columns([4, 1])
        with col_info:
            details = []
            if pos:    details.append(f"<strong>Position:</strong> {pos}")
            if org:    details.append(f"<strong>Organisation:</strong> {org}")
            if phone:  details.append(f"<strong>Phone:</strong> {phone}")
            if email:  details.append(f"<strong>Email:</strong> <a href='mailto:{email}'>{email}</a>")
            st.markdown(
                "<div style='background:#f8f9fc;border:1px solid #e2e8f0;border-radius:12px;"
                "padding:0.7rem 0.9rem;font-size:0.9rem;color:#0f172a;line-height:1.8'>"
                + "<br>".join(details)
                + "</div>",
                unsafe_allow_html=True,
            )
            if mtg_titles:
                st.markdown(
                    "<div style='font-size:0.8rem;color:#6e7f96;margin-top:0.4rem'>"
                    "Meetings: " + ", ".join(mtg_titles[:5]) + "</div>",
                    unsafe_allow_html=True,
                )

        with col_action:
            if st.button("Remove", key=f"stk_del_{s_id}"):
                updated = [x for x in all_s if x.get("id") != s_id]
                save_external_stakeholders(updated)
                st.rerun()
