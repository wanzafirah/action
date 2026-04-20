"""Analytics page — charts and performance trends across all saved meetings."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

import streamlit as st

from utils.helpers import normalize_status, normalize_value


_ORG_KEYWORDS = (
    "team", "corp", "sdn", "bhd", "ltd", "inc", "department", "division",
    "unit", "group", "ministry", "agency", "centre", "center", "office",
    "bureau", "talentcorp", "mynext", "region",
)


def _is_person(name: str) -> bool:
    if not name or name in ("Not stated", "None", ""):
        return False
    return not any(kw in name.lower() for kw in _ORG_KEYWORDS)


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    st.markdown("## Analytics")
    st.caption("Trends and performance metrics across all your meetings.")

    if not meetings:
        st.info("No meetings yet. Capture some meetings to see analytics here.")
        return

    try:
        import pandas as pd
    except ImportError:
        st.error("pandas is required for analytics charts. Run: pip install pandas")
        return

    all_actions = [a for m in meetings for a in (m.get("actions") or [])]

    # ── Top-level KPI row ──────────────────────────────────────────
    total_mtgs   = len(meetings)
    total_acts   = len(all_actions)
    done_acts    = sum(1 for a in all_actions if normalize_status(a) == "Done")
    overdue_acts = sum(1 for a in all_actions if normalize_status(a) == "Overdue")
    rate         = int((done_acts / total_acts) * 100) if total_acts else 0

    c1, c2, c3, c4 = st.columns(4)
    for col, title, value, color in [
        (c1, "Total meetings",  str(total_mtgs),   "#1d4ed8"),
        (c2, "Total actions",   str(total_acts),   "#0f766e"),
        (c3, "Overdue",         str(overdue_acts), "#991b1b"),
        (c4, "Completion rate", f"{rate}%",         "#7c3aed"),
    ]:
        with col:
            st.markdown(
                f"<div class='kpi-card'>"
                f"<div class='kpi-label'>{title}</div>"
                f"<div class='kpi-value' style='color:{color}'>{value}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Row 1: Meetings per month  |  Action item status breakdown ──
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Meetings per month")
        month_counts: dict[str, int] = defaultdict(int)
        for m in meetings:
            d = normalize_value(m.get("date"), "")
            try:
                key = datetime.strptime(d, "%Y-%m-%d").strftime("%b %Y")
                month_counts[key] += 1
            except Exception:
                pass

        if month_counts:
            sorted_keys = sorted(month_counts, key=lambda x: datetime.strptime(x, "%b %Y"))
            df = pd.DataFrame(
                {"Meetings": [month_counts[k] for k in sorted_keys]},
                index=sorted_keys,
            )
            st.bar_chart(df, color="#27425D")
        else:
            st.info("No dated meetings found.")

    with col_r:
        st.markdown("#### Action item status")
        status_counts = Counter(normalize_status(a) for a in all_actions)
        if status_counts:
            order = ["Pending", "In Progress", "Done", "Overdue", "Cancelled"]
            labels  = [s for s in order if s in status_counts]
            values  = [status_counts[s] for s in labels]
            df_s = pd.DataFrame({"Count": values}, index=labels)
            st.bar_chart(df_s, color="#0E1B48")

    st.markdown("---")

    # ── Row 2: Completion by dept  |  Top assignees pending load ───
    col_l2, col_r2 = st.columns(2)

    with col_l2:
        st.markdown("#### Completion rate by department (top 10)")
        dept_stats: dict[str, dict] = defaultdict(lambda: {"done": 0, "total": 0})
        for m in meetings:
            m_dept = normalize_value(m.get("deptName") or m.get("department"), "").strip()
            for a in (m.get("actions") or []):
                dept = normalize_value(a.get("department") or a.get("company"), "").strip()
                if not dept or dept in ("None", "Not stated"):
                    dept = m_dept
                if not dept or dept in ("None", "Not stated", ""):
                    dept = "Unassigned"
                dept_stats[dept]["total"] += 1
                if normalize_status(a) == "Done":
                    dept_stats[dept]["done"] += 1

        if dept_stats:
            dept_rates = {
                dept: int((v["done"] / v["total"]) * 100) if v["total"] else 0
                for dept, v in dept_stats.items()
            }
            top = sorted(dept_rates.items(), key=lambda x: -x[1])[:10]
            df_d = pd.DataFrame({"Completion %": [v for _, v in top]}, index=[d for d, _ in top])
            st.bar_chart(df_d, color="#87A7D0")
        else:
            st.info("No department data available.")

    with col_r2:
        st.markdown("#### Top assignees — pending load")
        person_pending: dict[str, int] = defaultdict(int)
        for a in all_actions:
            if normalize_status(a) in ("Done", "Cancelled"):
                continue
            owner = normalize_value(a.get("owner"), "Not stated")
            if not _is_person(owner):
                continue
            person_pending[owner] += 1

        if person_pending:
            top_p = sorted(person_pending.items(), key=lambda x: -x[1])[:10]
            df_p = pd.DataFrame({"Pending actions": [v for _, v in top_p]}, index=[k for k, _ in top_p])
            st.bar_chart(df_p, color="#C18DB4")
        else:
            st.info("No named assignees with pending actions.")

    st.markdown("---")

    # ── Row 3: Meetings by category  |  Meetings by org type ───────
    col_l3, col_r3 = st.columns(2)

    with col_l3:
        st.markdown("#### Meetings by category")
        cat_counts = Counter(
            normalize_value(m.get("category"), "Uncategorised") for m in meetings
        )
        if cat_counts:
            df_c = pd.DataFrame(
                {"Count": list(cat_counts.values())},
                index=list(cat_counts.keys()),
            )
            st.bar_chart(df_c, color="#E2CAD8")

    with col_r3:
        st.markdown("#### Follow-up required")
        needs_followup  = sum(1 for m in meetings if m.get("followUp"))
        no_followup     = total_mtgs - needs_followup
        df_fu = pd.DataFrame(
            {"Meetings": [needs_followup, no_followup]},
            index=["Follow-up needed", "Closed"],
        )
        st.bar_chart(df_fu, color="#0E1B48")
