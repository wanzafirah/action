"""People Accountability page.

Shows every named assignee found across all saved meetings, their action item
counts, completion rate, and a drill-down of every task assigned to them.
Sorted by most overdue first so a boss can see who needs a nudge immediately.
"""
from __future__ import annotations

from collections import defaultdict

import streamlit as st

from config.constants import STATUS_CFG
from utils.helpers import days_left, normalize_status, normalize_value, pill


_ORG_KEYWORDS = (
    "team", "corp", "sdn", "bhd", "ltd", "inc", "department", "division",
    "unit", "group", "ministry", "agency", "centre", "center", "office",
    "bureau", "talentcorp", "mynext", "region", "mimos", "fstc", "upnm",
    "hepa", "tnc", "university", "college", "institute", "jabatan",
)


def _is_person(name: str) -> bool:
    """Return True only if the name looks like a human (not an org)."""
    if not name or name in ("Not stated", "None", ""):
        return False
    nl = name.lower()
    return not any(kw in nl for kw in _ORG_KEYWORDS)


def render() -> None:
    meetings = st.session_state.get("meetings", [])

    st.markdown("## People")
    st.caption("Individual action item performance across all meetings.")

    # ── Collect all action items per named person ──────────────────
    people_actions: dict[str, list] = defaultdict(list)
    for m in meetings:
        m_title = normalize_value(m.get("title"), "Untitled meeting")
        m_date  = normalize_value(m.get("date"), "")
        for a in (m.get("actions") or []):
            owner = normalize_value(a.get("owner"), "Not stated")
            if not _is_person(owner):
                continue
            people_actions[owner].append({
                **a,
                "_meeting_title": m_title,
                "_meeting_date":  m_date,
            })

    if not people_actions:
        st.info("No named assignees found yet. Capture meetings with explicitly named action item owners to see them here.")
        return

    # ── Build summary rows ─────────────────────────────────────────
    rows = []
    for person, actions in people_actions.items():
        total    = len(actions)
        done     = sum(1 for a in actions if normalize_status(a) == "Done")
        overdue  = sum(1 for a in actions if normalize_status(a) == "Overdue")
        in_prog  = sum(1 for a in actions if normalize_status(a) == "In Progress")
        pending  = sum(1 for a in actions if normalize_status(a) == "Pending")
        rate     = int((done / total) * 100) if total else 0
        rows.append({
            "person":      person,
            "total":       total,
            "done":        done,
            "overdue":     overdue,
            "in_progress": in_prog,
            "pending":     pending,
            "rate":        rate,
            "actions":     actions,
        })

    # Sort: most overdue first → then lowest completion rate
    rows.sort(key=lambda r: (-r["overdue"], r["rate"]))

    # ── Global KPIs ────────────────────────────────────────────────
    total_people = len(rows)
    avg_rate     = int(sum(r["rate"] for r in rows) / total_people) if total_people else 0
    at_risk      = sum(1 for r in rows if r["overdue"] > 0)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>People tracked</div>"
            f"<div class='kpi-value' style='color:#1d4ed8'>{total_people}</div>"
            f"<div class='kpi-subtitle'>Named assignees</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>Avg completion</div>"
            f"<div class='kpi-value' style='color:#0f766e'>{avg_rate}%</div>"
            f"<div class='kpi-subtitle'>Across all people</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>At risk</div>"
            f"<div class='kpi-value' style='color:#991b1b'>{at_risk}</div>"
            f"<div class='kpi-subtitle'>People with overdue items</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

    # ── Search filter ──────────────────────────────────────────────
    search = st.text_input("Search by name", placeholder="Filter people…", key="people_search")
    filtered = [r for r in rows if not search or search.lower() in r["person"].lower()]

    if not filtered:
        st.info("No people match your search.")
        return

    # ── Render each person card ────────────────────────────────────
    for row in filtered:
        _render_person_card(row)


def _render_person_card(row: dict) -> None:
    person  = row["person"]
    rate    = row["rate"]
    overdue = row["overdue"]
    total   = row["total"]
    done    = row["done"]
    pending = row["pending"]
    in_prog = row["in_progress"]

    ring_color = "#22c55e" if rate >= 75 else "#f59e0b" if rate >= 40 else "#ef4444"

    overdue_badge = (
        f"<span style='background:#fee2e2;color:#991b1b;padding:0.2rem 0.6rem;"
        f"border-radius:999px;font-size:0.78rem;font-weight:700;white-space:nowrap'>"
        f"⚠ {overdue} overdue</span>"
        if overdue > 0 else
        f"<span style='background:#dcfce7;color:#166534;padding:0.2rem 0.6rem;"
        f"border-radius:999px;font-size:0.78rem;font-weight:700'>✓ On track</span>"
    )

    expander_label = f"{person}  ·  {rate}% complete  {'⚠ overdue' if overdue > 0 else ''}"

    with st.expander(expander_label, expanded=False):
        st.markdown(
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"gap:0.8rem;margin-bottom:0.75rem'>"
            f"<div style='display:flex;align-items:center;gap:0.75rem'>"
            f"<div style='width:44px;height:44px;border-radius:50%;"
            f"background:linear-gradient(135deg,#E2CAD8,#87A7D0);"
            f"display:grid;place-items:center;font-weight:800;font-size:1.1rem;color:#0E1B48'>"
            f"{person[0].upper()}</div>"
            f"<div>"
            f"<div style='font-weight:800;font-size:1rem;color:#0f172a'>{person}</div>"
            f"<div style='font-size:0.82rem;color:#6e7f96'>"
            f"{total} action(s) &nbsp;·&nbsp; {done} done &nbsp;·&nbsp; "
            f"{pending} pending &nbsp;·&nbsp; {in_prog} in progress"
            f"</div></div></div>"
            f"<div style='display:flex;align-items:center;gap:0.75rem'>"
            f"{overdue_badge}"
            f"<div style='text-align:center'>"
            f"<div style='font-size:1.5rem;font-weight:800;color:{ring_color}'>{rate}%</div>"
            f"<div style='font-size:0.72rem;color:#6e7f96'>completion</div>"
            f"</div></div></div>",
            unsafe_allow_html=True,
        )

        for a in row["actions"]:
            status  = normalize_status(a)
            cfg     = STATUS_CFG.get(status, STATUS_CFG["Pending"])
            text    = normalize_value(a.get("text"), "Untitled action")
            deadline = normalize_value(a.get("deadline"), "None")
            mtitle  = normalize_value(a.get("_meeting_title"), "")

            dl = days_left(deadline) if deadline not in ("None", "Not stated", "") else None
            if dl is not None and dl < 0:
                dl_html = (f"<span style='color:#991b1b;font-weight:700'>"
                           f"⚠ {abs(dl)}d overdue</span>")
            elif dl == 0:
                dl_html = "<span style='color:#92400e;font-weight:700'>🔔 Due today</span>"
            elif dl is not None and dl <= 3:
                dl_html = f"<span style='color:#b45309;font-weight:700'>🔔 {dl}d left</span>"
            elif dl is not None:
                dl_html = f"<span style='color:#1d4ed8'>{dl}d left</span>"
            else:
                dl_html = "<span style='color:#6e7f96'>No deadline</span>"

            st.markdown(
                f"<div style='background:#f8f9fc;border:1px solid #e2e8f0;border-radius:12px;"
                f"padding:0.6rem 0.9rem;margin-bottom:0.4rem'>"
                f"<div style='display:flex;justify-content:space-between;align-items:start;gap:0.5rem'>"
                f"<div style='font-weight:600;color:#0f172a;font-size:0.92rem;flex:1'>{text}</div>"
                f"{pill(status, cfg['color'], cfg['bg'])}"
                f"</div>"
                f"<div style='font-size:0.8rem;color:#6e7f96;margin-top:0.3rem'>"
                f"📋 {mtitle} &nbsp;|&nbsp; Deadline: {deadline} &nbsp;|&nbsp; {dl_html}"
                f"</div></div>",
                unsafe_allow_html=True,
            )
