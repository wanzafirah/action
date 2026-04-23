"""Companies page — TalentCorp programme participation directory."""
from __future__ import annotations

import streamlit as st


def render() -> None:
    st.markdown("## Companies")
    st.caption("TalentCorp programme participation directory.")

    # Load data (cached after first call)
    from utils.company_db import get_all_data
    import pandas as pd

    df = get_all_data()
    df = df[df['CompanyName'].str.strip() != ''].copy()

    # ── KPI cards ───────────────────────────────────────────────────
    total_companies = int(df['CompanyName'].nunique())
    total_records   = len(df)
    programmes      = sorted(p for p in df['Programme'].unique() if p)

    c1, c2, c3 = st.columns(3)
    for col, title, value, sub, color in [
        (c1, "Companies",   f"{total_companies:,}", "Unique companies",            "#1d4ed8"),
        (c2, "Records",     f"{total_records:,}",   "Programme participation entries", "#0f766e"),
        (c3, "Programmes",  str(len(programmes)),   "Active programmes",            "#92400e"),
    ]:
        with col:
            st.markdown(
                f"<div class='kpi-card'>"
                f"<div class='kpi-label'>{title}</div>"
                f"<div class='kpi-value' style='color:{color}'>{value}</div>"
                f"<div class='kpi-subtitle'>{sub}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)

    # ── Filters ─────────────────────────────────────────────────────
    col_search, col_prog, col_type = st.columns([3, 2, 2])
    with col_search:
        search = st.text_input(
            "Search company name",
            placeholder="Type to search…",
            key="co_search",
        )
    with col_prog:
        prog_filter = st.multiselect(
            "Programme",
            options=programmes,
            key="co_prog",
        )
    with col_type:
        types = sorted(t for t in df['CompanyType'].unique() if t)
        type_filter = st.multiselect(
            "Company Type",
            options=types,
            key="co_type",
        )

    # ── Apply filters ────────────────────────────────────────────────
    filtered = df.copy()
    if search.strip():
        filtered = filtered[
            filtered['CompanyName'].str.lower().str.contains(
                search.strip().lower(), na=False, regex=False
            )
        ]
    if prog_filter:
        filtered = filtered[filtered['Programme'].isin(prog_filter)]
    if type_filter:
        filtered = filtered[filtered['CompanyType'].isin(type_filter)]

    st.caption(f"Showing {len(filtered):,} records")

    # ── Table ────────────────────────────────────────────────────────
    display = filtered[['RefDate', 'CompanyName', 'CompanyType', 'Sector', 'Programme']].copy()
    display.columns = ['Date', 'Company Name', 'Company Type', 'Sector', 'Programme']
    display = display.sort_values(['Company Name', 'Date']).reset_index(drop=True)

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            'Date':         st.column_config.TextColumn('Date',         width='small'),
            'Company Name': st.column_config.TextColumn('Company Name', width='large'),
            'Company Type': st.column_config.TextColumn('Type',         width='small'),
            'Sector':       st.column_config.TextColumn('Sector',       width='medium'),
            'Programme':    st.column_config.TextColumn('Programme',    width='small'),
        },
    )
