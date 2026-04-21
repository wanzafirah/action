"""Stakeholders directory — external contacts from all meetings."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core.stakeholder_db import load_external_stakeholders, save_external_stakeholders
from utils.helpers import uid

_TODAY = date.today().isoformat()


def render() -> None:
    st.markdown("## Stakeholders")
    st.caption("External contacts from outside TalentCorp. Edit cells directly, add rows, or select rows to delete.")

    # ── Load data ───────────────────────────────────────────────────
    all_s = load_external_stakeholders()

    # Merge any external stakeholders captured in meetings this session
    meetings = st.session_state.get("meetings", [])
    for m in meetings:
        for s in (m.get("externalStakeholders") or []):
            existing_keys = {
                (x.get("name", "").lower(), x.get("organisation", "").lower())
                for x in all_s
            }
            key = (s.get("name", "").lower(), s.get("organisation", "").lower())
            if key not in existing_keys and s.get("name"):
                all_s.append({
                    **s,
                    "date_added": _TODAY,
                    "meeting_ids": [m.get("id", "")],
                })

    # ── Search ──────────────────────────────────────────────────────
    search = st.text_input(
        "Search",
        placeholder="Search by name or organisation…",
        key="stk_search",
        label_visibility="collapsed",
    )

    # ── KPIs ────────────────────────────────────────────────────────
    if all_s:
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

    # ── Build meeting title lookup ───────────────────────────────────
    mtg_lookup = {m.get("id"): m.get("title", "Untitled") for m in meetings}

    # ── Convert to DataFrame ─────────────────────────────────────────
    def _to_df(records: list) -> pd.DataFrame:
        rows = []
        for s in records:
            mtg_ids   = s.get("meeting_ids", [])
            mtg_names = ", ".join(mtg_lookup.get(mid, "") for mid in mtg_ids if mtg_lookup.get(mid))
            rows.append({
                "_id":          s.get("id", uid()),
                "Name":         s.get("name", ""),
                "Position":     s.get("position", ""),
                "Organisation": s.get("organisation", ""),
                "Phone":        s.get("phone", ""),
                "Email":        s.get("email", ""),
                "Date Added":   s.get("date_added", _TODAY),
                "Meetings":     mtg_names or "—",
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["_id", "Name", "Position", "Organisation", "Phone", "Email", "Date Added", "Meetings"]
        )

    # Apply search filter for display (editor still shows filtered view)
    needle = search.strip().lower()
    display_s = [
        s for s in all_s
        if not needle
        or needle in s.get("name", "").lower()
        or needle in s.get("organisation", "").lower()
        or needle in s.get("position", "").lower()
    ] if needle else all_s

    df = _to_df(display_s)

    # ── Editable table ───────────────────────────────────────────────
    edited_df = st.data_editor(
        df,
        key="stk_editor",
        num_rows="dynamic",          # allows adding new rows at the bottom
        use_container_width=True,
        hide_index=True,
        column_config={
            "_id": None,             # hide internal ID column
            "Name":         st.column_config.TextColumn("Name",         width="medium"),
            "Position":     st.column_config.TextColumn("Position",     width="medium"),
            "Organisation": st.column_config.TextColumn("Organisation", width="medium"),
            "Phone":        st.column_config.TextColumn("Phone",        width="small"),
            "Email":        st.column_config.TextColumn("Email",        width="medium"),
            "Date Added":   st.column_config.TextColumn("Date Added",   width="small",  disabled=True),
            "Meetings":     st.column_config.TextColumn("Meetings",     width="medium", disabled=True),
        },
    )

    # ── Save changes button ──────────────────────────────────────────
    if st.button("Save changes", type="primary", key="stk_save_edits"):
        # Rebuild all_s from edited_df (excluding search-filtered-out records)
        # First, keep records not shown in the current filtered view unchanged
        shown_ids = set(df["_id"].tolist())
        kept = [s for s in all_s if s.get("id") not in shown_ids]

        # Add back the edited rows
        for _, row in edited_df.iterrows():
            name = str(row.get("Name", "")).strip()
            if not name:
                continue  # skip blank rows
            kept.append({
                "id":           str(row.get("_id") or uid()),
                "name":         name,
                "position":     str(row.get("Position", "") or "").strip(),
                "organisation": str(row.get("Organisation", "") or "").strip(),
                "phone":        str(row.get("Phone", "") or "").strip(),
                "email":        str(row.get("Email", "") or "").strip(),
                "date_added":   str(row.get("Date Added") or _TODAY),
                "meeting_ids":  next(
                    (s.get("meeting_ids", []) for s in all_s if s.get("id") == str(row.get("_id", ""))),
                    [],
                ),
            })

        save_external_stakeholders(kept)
        st.success("Stakeholder list saved.")
        st.rerun()
