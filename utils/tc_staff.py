"""Load TalentCorp staff list from the bundled Excel file."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

_EXCEL_PATH = Path(__file__).resolve().parent.parent / "TC Staff Details.xlsx"


def load_tc_staff() -> list[dict]:
    """Return [{name, email, tcid}] from TC Staff Details.xlsx."""
    if not _EXCEL_PATH.exists():
        st.warning(f"TC Staff file not found at: {_EXCEL_PATH}")
        return []

    # Close-lock check (Excel creates ~$filename when the file is open)
    lock_file = _EXCEL_PATH.parent / f"~${_EXCEL_PATH.name}"
    if lock_file.exists():
        st.warning("TC Staff Excel is currently open in Excel. Close the file and refresh.")
        return []

    try:
        import pandas as pd
        df = pd.read_excel(str(_EXCEL_PATH), engine="openpyxl")
        # Normalise column names — strip whitespace and handle casing
        df.columns = [str(c).strip() for c in df.columns]

        # Find the name column (first column containing "name" case-insensitive)
        name_col  = next((c for c in df.columns if "name"  in c.lower()), df.columns[0])
        email_col = next((c for c in df.columns if "email" in c.lower()), None)
        tcid_col  = next((c for c in df.columns if "tcid"  in c.lower() or "id" in c.lower()), None)

        staff: list[dict] = []
        for _, row in df.iterrows():
            name = str(row[name_col]).strip() if row[name_col] and str(row[name_col]) != "nan" else ""
            if not name:
                continue
            staff.append({
                "name":  name,
                "email": str(row[email_col]).strip() if email_col and str(row[email_col]) != "nan" else "",
                "tcid":  str(row[tcid_col]).strip()  if tcid_col  and str(row[tcid_col])  != "nan" else "",
            })
        return sorted(staff, key=lambda x: x["name"])

    except Exception as exc:
        st.error(f"Could not load TC staff list: {exc}")
        return []


def get_tc_names() -> list[str]:
    """Return just the sorted name strings for use in multiselect / selectbox."""
    return [s["name"] for s in load_tc_staff()]
