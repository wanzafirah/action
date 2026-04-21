"""Load TalentCorp staff list from the bundled Excel file.

Falls back to a session-state cache populated via in-app upload when
the file is not present (e.g. on Streamlit Cloud).
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

_EXCEL_PATH = Path(__file__).resolve().parent.parent / "TC Staff Details.xlsx"
_SESSION_KEY = "tc_staff_cache"


def _parse_excel(source) -> list[dict]:
    """Parse an Excel file (path string or file-like object) into staff dicts."""
    import pandas as pd
    df = pd.read_excel(source, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    name_col  = next((c for c in df.columns if "name"  in c.lower()), df.columns[0])
    email_col = next((c for c in df.columns if "email" in c.lower()), None)
    tcid_col  = next((c for c in df.columns if "tcid"  in c.lower() or "tc id" in c.lower()), None)

    staff: list[dict] = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() == "nan":
            continue
        staff.append({
            "name":  name,
            "email": str(row[email_col]).strip() if email_col and str(row[email_col]) != "nan" else "",
            "tcid":  str(row[tcid_col]).strip()  if tcid_col  and str(row[tcid_col])  != "nan" else "",
        })
    return sorted(staff, key=lambda x: x["name"])


def load_tc_staff() -> list[dict]:
    """Return staff list. Tries local file first, then session cache."""
    # 1. Local file (works when running locally or if pushed to git)
    if _EXCEL_PATH.exists():
        lock = _EXCEL_PATH.parent / f"~${_EXCEL_PATH.name}"
        if not lock.exists():
            try:
                staff = _parse_excel(str(_EXCEL_PATH))
                st.session_state[_SESSION_KEY] = staff   # keep cache in sync
                return staff
            except Exception:
                pass

    # 2. Session-state cache (populated via in-app upload below)
    if _SESSION_KEY in st.session_state:
        return st.session_state[_SESSION_KEY]

    return []


def get_tc_names() -> list[str]:
    return [s["name"] for s in load_tc_staff()]


def render_upload_widget() -> None:
    """Show a compact upload box when the Excel file is missing.
    Call this from the Capture page so users can load staff on Streamlit Cloud.
    """
    if _EXCEL_PATH.exists() or _SESSION_KEY in st.session_state:
        return   # file already available — nothing to show

    st.info(
        "TC Staff list not found. Upload **TC Staff Details.xlsx** once to enable "
        "staff search for this session.",
        icon="ℹ️",
    )
    uploaded = st.file_uploader(
        "Upload TC Staff Details.xlsx",
        type=["xlsx"],
        key="tc_staff_upload_widget",
    )
    if uploaded:
        try:
            staff = _parse_excel(uploaded)
            st.session_state[_SESSION_KEY] = staff
            st.success(f"Loaded {len(staff)} staff members.")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not read file: {exc}")
