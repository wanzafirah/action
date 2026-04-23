"""Companies page — TalentCorp programme participation directory."""
from __future__ import annotations

from datetime import date as _date
from pathlib import Path

import streamlit as st

_CSV_PATH = Path(__file__).parent.parent / "datacompany 1.csv"

# Programme colour map (background, text)
_PROG_COLORS: dict[str, tuple[str, str]] = {
    "STAR":   ("#dbeafe", "#1d4ed8"),
    "WCC":    ("#d1fae5", "#065f46"),
    "mynext": ("#ede9fe", "#5b21b6"),
    "IP":     ("#fef3c7", "#92400e"),
    "BURSA":  ("#fee2e2", "#991b1b"),
    "CCPTax": ("#f1f5f9", "#334155"),
    "RP-T":   ("#ecfdf5", "#047857"),
    "REP":    ("#fff7ed", "#c2410c"),
    "IAC":    ("#eff6ff", "#1e40af"),
    "WLPs":   ("#faf5ff", "#6d28d9"),
    "SIP":    ("#e0f2fe", "#0369a1"),
}
_PROG_DEFAULT = ("#f1f5f9", "#334155")

_PROGRAMMES = ["STAR", "WCC", "CCPTax", "IP", "mynext", "RP-T", "REP", "IAC", "WLPs", "BURSA", "SIP"]
_COMPANY_TYPES = ["MNC", "SME", "GLC", "Others"]


def _pill(text: str) -> str:
    bg, fg = _PROG_COLORS.get(text, _PROG_DEFAULT)
    return (
        f"<span style='background:{bg};color:{fg};padding:0.18rem 0.55rem;"
        f"border-radius:999px;font-size:0.75rem;font-weight:700;"
        f"white-space:nowrap;display:inline-block;margin:0.1rem 0.15rem'>"
        f"{text}</span>"
    )


def render() -> None:
    from utils.company_db import get_all_data

    st.markdown("## Companies")
    st.caption("TalentCorp programme participation directory.")

    df = get_all_data()
    df = df[df["CompanyName"].str.strip() != ""].copy()

    # ── KPI cards ───────────────────────────────────────────────────
    total_companies = int(df["CompanyName"].nunique())
    total_records   = len(df)
    programmes      = sorted(p for p in df["Programme"].unique() if p)

    c1, c2, c3 = st.columns(3)
    for col, title, value, sub, color in [
        (c1, "Companies",  f"{total_companies:,}", "Unique companies",                "#1d4ed8"),
        (c2, "Records",    f"{total_records:,}",   "Programme participation entries",  "#0f766e"),
        (c3, "Programmes", str(len(programmes)),   "Active programmes",                "#92400e"),
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

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    # ── Add Company form ─────────────────────────────────────────────
    with st.expander("Add new company record", expanded=False):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            new_name = st.text_input("Company Name *", key="co_new_name", placeholder="e.g. Acme Sdn Bhd")
            new_type = st.selectbox("Company Type", [""] + _COMPANY_TYPES, key="co_new_type")
        with fc2:
            new_prog = st.selectbox("Programme", [""] + _PROGRAMMES, key="co_new_prog")
            new_sector = st.text_input("Sector", key="co_new_sector", placeholder="e.g. Financial Services")
        with fc3:
            new_date = st.date_input("Date", value=_date.today(), key="co_new_date")
            st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
            add_btn = st.button("Add Record", key="co_add_btn", type="primary", use_container_width=True)

        if add_btn:
            if new_name.strip():
                import csv
                with open(_CSV_PATH, "a", newline="", encoding="latin1") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        new_name.strip(),
                        new_type,
                        new_prog,
                        new_date.strftime("%m/%d/%Y"),
                        new_sector.strip(),
                    ])
                # Invalidate the LRU cache so the new row appears immediately
                from utils.company_db import _load_df
                _load_df.cache_clear()
                st.success(f"✓ Added **{new_name.strip()}** to records.")
                st.rerun()
            else:
                st.warning("Company Name is required.")

    # ── Filters ─────────────────────────────────────────────────────
    col_s, col_p, col_t = st.columns([3, 2, 2])
    with col_s:
        search = st.text_input("Search company name", placeholder="Type to search…", key="co_search")
    with col_p:
        prog_filter = st.multiselect("Programme", options=programmes, key="co_prog")
    with col_t:
        types = sorted(t for t in df["CompanyType"].unique() if t)
        type_filter = st.multiselect("Company Type", options=types, key="co_type")

    # ── Apply filters ─────────────────────────────────────────────────
    filtered = df.copy()
    if search.strip():
        filtered = filtered[
            filtered["CompanyName"].str.lower().str.contains(
                search.strip().lower(), na=False, regex=False
            )
        ]
    if prog_filter:
        filtered = filtered[filtered["Programme"].isin(prog_filter)]
    if type_filter:
        filtered = filtered[filtered["CompanyType"].isin(type_filter)]

    filtered = filtered.sort_values(["CompanyName", "RefDate"]).reset_index(drop=True)
    n = len(filtered)
    st.caption(f"Showing {n:,} records")

    # ── Table view ────────────────────────────────────────────────────
    # For small result sets (<= 300) render a styled HTML table with
    # coloured programme pills. For large sets fall back to st.dataframe.
    if n == 0:
        st.info("No records match your filters.")
        return

    if n <= 300:
        _render_html_table(filtered)
    else:
        _render_dataframe(filtered)


def _render_html_table(df) -> None:
    """Custom HTML table with coloured programme pills."""
    rows_html = ""
    for _, row in df.iterrows():
        prog = row.get("Programme", "") or ""
        prog_html = _pill(prog) if prog else "<span style='color:#94a3b8'>—</span>"
        ctype = row.get("CompanyType", "") or ""
        sector = row.get("Sector", "") or ""
        date_v = row.get("RefDate", "") or ""
        name = str(row.get("CompanyName", ""))

        rows_html += (
            f"<tr>"
            f"<td style='color:#6e7f96;font-size:0.82rem;white-space:nowrap'>{date_v}</td>"
            f"<td style='font-weight:600;color:#0f172a'>{name}</td>"
            f"<td style='color:#475569;font-size:0.83rem'>{ctype}</td>"
            f"<td style='color:#475569;font-size:0.83rem'>{sector}</td>"
            f"<td>{prog_html}</td>"
            f"</tr>"
        )

    table_html = (
        "<div style='overflow-x:auto;border-radius:12px;border:1px solid #e2e8f0'>"
        "<table style='width:100%;border-collapse:collapse;font-size:0.88rem'>"
        "<thead><tr style='background:#f8fafc;border-bottom:2px solid #e2e8f0'>"
        "<th style='padding:0.6rem 0.8rem;text-align:left;color:#64748b;"
        "font-weight:700;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.04em;"
        "white-space:nowrap'>Date</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left;color:#64748b;"
        "font-weight:700;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.04em'>"
        "Company Name</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left;color:#64748b;"
        "font-weight:700;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.04em'>"
        "Type</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left;color:#64748b;"
        "font-weight:700;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.04em'>"
        "Sector</th>"
        "<th style='padding:0.6rem 0.8rem;text-align:left;color:#64748b;"
        "font-weight:700;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.04em'>"
        "Programme</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )

    # Add alternating row stripes via CSS
    st.markdown(
        "<style>"
        "table tbody tr:nth-child(even) { background:#f8fafc; }"
        "table tbody tr:hover { background:#eff6ff; }"
        "table tbody td { padding: 0.5rem 0.8rem; border-bottom: 1px solid #f1f5f9; }"
        "</style>"
        + table_html,
        unsafe_allow_html=True,
    )


def _render_dataframe(df) -> None:
    """Fallback plain dataframe for large result sets."""
    display = df[["RefDate", "CompanyName", "CompanyType", "Sector", "Programme"]].copy()
    display.columns = ["Date", "Company Name", "Type", "Sector", "Programme"]
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "Date":         st.column_config.TextColumn("Date",         width="small"),
            "Company Name": st.column_config.TextColumn("Company Name", width="large"),
            "Type":         st.column_config.TextColumn("Type",         width="small"),
            "Sector":       st.column_config.TextColumn("Sector",       width="medium"),
            "Programme":    st.column_config.TextColumn("Programme",    width="small"),
        },
    )
