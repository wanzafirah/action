"""People Accountability page.

Two modes:
  1. Personal view — user types their name and sees all tasks assigned to them.
  2. Team overview — all named assignees sorted by most at-risk first.
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
    if not name or name in ("Not stated", "None", ""):
        return False
    return not any(kw in name.lower() for kw in _ORG_KEYWORDS)


def _collect_people(meetings: list) -> dict[str, list]:
    """Return {person_name: [action_dicts]} across all meetings.

    Handles comma-separated owner strings (e.g. "Aisyah, Farhan, Mei Ling")
    by splitting each into individual names so every person appears separately.
    """
    people: dict[str, list] = defaultdict(list)
    for m in meetings:
        m_title = normalize_value(m.get("title"), "Untitled meeting")
        m_date  = normalize_value(m.get("date"), "")
        for a in (m.get("actions") or []):
            raw_owner = normalize_value(a.get("owner"), "Not stated")
            # Split comma-separated names into individuals
            names = [n.strip() for n in raw_owner.split(",") if n.strip()]
            for owner in names:
                if not _is_person(owner):
                    continue
                people[owner].append({**a, "_meeting_title": m_title, "_meeting_date": m_date})
    return people


def render() -> None:
    meetings = st.session_state.get("meetings", [])
    people_actions = _collect_people(meetings)

    st.markdown("## People")

    if not people_actions:
        st.info("No named assignees found yet. Capture meetings with explicitly named action item owners to see them here.")
        return

    # Build summary rows
    rows = []
    for person, actions in people_actions.items():
        total   = len(actions)
        done    = sum(1 for a in actions if normalize_status(a) == "Done")
        overdue = sum(1 for a in actions if normalize_status(a) == "Overdue")
        in_prog = sum(1 for a in actions if normalize_status(a) == "In Progress")
        pending = sum(1 for a in actions if normalize_status(a) == "Pending")
        rate    = int((done / total) * 100) if total else 0
        rows.append({"person": person, "total": total, "done": done,
                     "overdue": overdue, "in_progress": in_prog,
                     "pending": pending, "rate": rate, "actions": actions})

    rows.sort(key=lambda r: (-r["overdue"], r["rate"]))

    # KPIs (always shown based on full dataset)
    all_rows = rows
    total_people = len(all_rows)
    avg_rate     = int(sum(r["rate"] for r in all_rows) / total_people) if total_people else 0
    at_risk      = sum(1 for r in all_rows if r["overdue"] > 0)

    c1, c2, c3 = st.columns(3)
    for col, title, value, color, sub in [
        (c1, "People tracked", str(total_people), "#1d4ed8", "Named assignees"),
        (c2, "Avg completion",  f"{avg_rate}%",    "#0f766e", "Across all people"),
        (c3, "At risk",         str(at_risk),       "#991b1b", "Have overdue items"),
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

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Filter by name — text search
    team_search = st.text_input(
        "Filter by name",
        placeholder="Filter by name…",
        key="people_team_search",
    )
    filtered = [r for r in rows if not team_search or team_search.lower() in r["person"].lower()]

    if not filtered:
        st.info("No people match your search.")
        return

    for row in filtered:
        _render_person_card(row)


# ------------------------------------------------------------------
# Personal task view
# ------------------------------------------------------------------
def _render_personal_view(name: str, people_actions: dict[str, list]) -> None:
    # Fuzzy match: find all people whose name contains the search term
    matches = {p: a for p, a in people_actions.items() if name.lower() in p.lower()}

    if not matches:
        st.warning(f"No action items found assigned to **{name}**. Check the spelling matches the transcript.")
        return

    for person, actions in matches.items():
        total   = len(actions)
        done    = sum(1 for a in actions if normalize_status(a) == "Done")
        overdue = sum(1 for a in actions if normalize_status(a) == "Overdue")
        pending = sum(1 for a in actions if normalize_status(a) == "Pending")
        in_prog = sum(1 for a in actions if normalize_status(a) == "In Progress")
        rate    = int((done / total) * 100) if total else 0
        ring    = "#22c55e" if rate >= 75 else "#f59e0b" if rate >= 40 else "#ef4444"

        st.markdown(
            f"<div style='background:#ffffff;border:1px solid #d8dceb;border-radius:18px;"
            f"padding:1rem 1.2rem;margin-bottom:0.6rem;"
            f"box-shadow:0 8px 20px rgba(14,27,72,0.06)'>"
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"margin-bottom:0.75rem'>"
            f"<div style='display:flex;align-items:center;gap:0.75rem'>"
            f"<div style='width:46px;height:46px;border-radius:50%;"
            f"background:linear-gradient(135deg,#E2CAD8,#87A7D0);"
            f"display:grid;place-items:center;font-weight:800;font-size:1.15rem;color:#0E1B48'>"
            f"{person[0].upper()}</div>"
            f"<div><div style='font-weight:800;font-size:1.1rem;color:#0f172a'>{person}</div>"
            f"<div style='font-size:0.82rem;color:#6e7f96'>"
            f"{total} tasks &nbsp;·&nbsp; {done} done &nbsp;·&nbsp; "
            f"{pending} pending &nbsp;·&nbsp; {in_prog} in progress"
            f"{'&nbsp;·&nbsp; <span style=color:#991b1b;font-weight:700>' + str(overdue) + ' overdue</span>' if overdue > 0 else ''}"  # noqa
            f"</div></div></div>"
            f"<div style='text-align:center'>"
            f"<div style='font-size:2rem;font-weight:800;color:{ring}'>{rate}%</div>"
            f"<div style='font-size:0.72rem;color:#6e7f96'>completion</div>"
            f"</div></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Sort: overdue first, then by deadline
        def _sort_key(a):
            s = normalize_status(a)
            dl = days_left(normalize_value(a.get("deadline"), "")) or 9999
            if s == "Overdue":    return (0, dl)
            if s == "In Progress": return (1, dl)
            if s == "Pending":     return (2, dl)
            return (3, dl)

        for a in sorted(actions, key=_sort_key):
            _render_action_row(a)


# ------------------------------------------------------------------
# Team card + action rows
# ------------------------------------------------------------------
def _render_person_card(row: dict) -> None:
    person  = row["person"]
    rate    = row["rate"]
    overdue = row["overdue"]
    total   = row["total"]
    done    = row["done"]
    pending = row["pending"]
    in_prog = row["in_progress"]
    ring    = "#22c55e" if rate >= 75 else "#f59e0b" if rate >= 40 else "#ef4444"

    ob = (f"<span style='background:#fee2e2;color:#991b1b;padding:0.2rem 0.55rem;"
          f"border-radius:999px;font-size:0.76rem;font-weight:700'>{overdue} overdue</span> "
          if overdue > 0 else
          f"<span style='background:#dcfce7;color:#166534;padding:0.2rem 0.55rem;"
          f"border-radius:999px;font-size:0.76rem;font-weight:700'>On track</span> ")

    with st.expander(f"{person}  ·  {rate}% complete  {'[overdue]' if overdue > 0 else ''}", expanded=False):
        st.markdown(
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"gap:0.8rem;margin-bottom:0.7rem'>"
            f"<div style='display:flex;align-items:center;gap:0.7rem'>"
            f"<div style='width:42px;height:42px;border-radius:50%;"
            f"background:linear-gradient(135deg,#E2CAD8,#87A7D0);"
            f"display:grid;place-items:center;font-weight:800;font-size:1rem;color:#0E1B48'>"
            f"{person[0].upper()}</div>"
            f"<div><div style='font-weight:800;font-size:0.98rem;color:#0f172a'>{person}</div>"
            f"<div style='font-size:0.8rem;color:#6e7f96'>"
            f"{total} action(s) · {done} done · {pending} pending · {in_prog} in progress"
            f"</div></div></div>"
            f"<div style='display:flex;align-items:center;gap:0.6rem'>"
            f"{ob}"
            f"<div style='text-align:center'>"
            f"<div style='font-size:1.4rem;font-weight:800;color:{ring}'>{rate}%</div>"
            f"<div style='font-size:0.7rem;color:#6e7f96'>completion</div>"
            f"</div></div></div>",
            unsafe_allow_html=True,
        )
        for a in row["actions"]:
            _render_action_row(a)


def _render_action_row(a: dict) -> None:
    status   = normalize_status(a)
    cfg      = STATUS_CFG.get(status, STATUS_CFG["Pending"])
    text     = normalize_value(a.get("text"), "Untitled action")
    deadline = normalize_value(a.get("deadline"), "None")
    mtitle   = normalize_value(a.get("_meeting_title"), "")

    dl = days_left(deadline) if deadline not in ("None", "Not stated", "") else None
    if dl is not None and dl < 0:
        dl_html = f"<span style='color:#991b1b;font-weight:700'>{abs(dl)}d overdue</span>"
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
        f"<div style='font-size:0.8rem;color:#6e7f96;margin-top:0.28rem'>"
        f"Meeting: {mtitle} &nbsp;|&nbsp; Deadline: {deadline} &nbsp;|&nbsp; {dl_html}"
        f"</div></div>",
        unsafe_allow_html=True,
    )
