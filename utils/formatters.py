"""Pure formatting helpers: email templates, dataframes, calendar.

These do not touch Streamlit or any database. They're what the pages use
to turn raw meeting dicts into display-ready HTML and tables.
"""
from __future__ import annotations

import calendar
import html
from datetime import date, datetime

import pandas as pd

from utils.helpers import (
    join_list,
    normalize_status,
    normalize_value,
    pretty_deadline,
)


# ------------------------------------------------------------------
# Email templates
# ------------------------------------------------------------------
def build_email_subject(meeting: dict) -> str:
    title = normalize_value(meeting.get("title"), "Meeting recap")
    meeting_date = normalize_value(meeting.get("date"), "")
    return f"Meeting recap: {title}" + (f" ({meeting_date})" if meeting_date else "")


def build_email_body(meeting: dict) -> str:
    lines = [
        f"Meeting: {normalize_value(meeting.get('title'), 'Untitled')}",
        f"Date: {normalize_value(meeting.get('date'), 'TBD')}",
        f"Objective: {normalize_value(meeting.get('objective'), 'Not provided')}",
        "",
        "Summary:",
        normalize_value(meeting.get("summary"), "No summary available."),
        "",
    ]
    actions = meeting.get("actions") or []
    if actions:
        lines.append("Action items:")
        for a in actions:
            text = normalize_value(a.get("text"), "Untitled action")
            owner = normalize_value(a.get("owner"), "Not stated")
            deadline = pretty_deadline(normalize_value(a.get("deadline"), ""))
            lines.append(f"- {text} | owner: {owner} | deadline: {deadline}")
    else:
        lines.append("No action items were captured.")
    return "\n".join(lines)


# ------------------------------------------------------------------
# DataFrame builders (for Dashboard KPIs and charts)
# ------------------------------------------------------------------
def build_meeting_dataframe(meetings: list) -> pd.DataFrame:
    if not meetings:
        return pd.DataFrame()
    rows = []
    for m in meetings:
        parsed = pd.to_datetime(m.get("date"), errors="coerce")
        rows.append({
            "id": m.get("id", ""),
            "title": m.get("title", ""),
            "date": m.get("date", ""),
            "month": parsed.strftime("%Y-%m") if not pd.isna(parsed) else "",
            "year": int(parsed.year) if not pd.isna(parsed) else None,
            "category": m.get("category", "Internal Meeting"),
            "department": m.get("deptName") or m.get("department") or "Unassigned",
            "follow_up": bool(m.get("followUp")),
            "actions_count": len(m.get("actions", []) or []),
            "decisions_count": len(m.get("keyDecisions", []) or []),
        })
    return pd.DataFrame(rows)


def build_action_dataframe(meetings: list) -> pd.DataFrame:
    rows = []
    for m in meetings:
        for a in m.get("actions", []) or []:
            rows.append({
                "id": a.get("id", ""),
                "meeting_id": m.get("id", ""),
                "meeting_title": m.get("title", ""),
                "meeting_date": m.get("date", ""),
                "text": normalize_value(a.get("text"), "Untitled action"),
                "owner": normalize_value(a.get("owner"), "Not stated"),
                "department": normalize_value(a.get("department") or a.get("company"), "Not stated"),
                "deadline": normalize_value(a.get("deadline"), "None"),
                "status": normalize_status(a),
                "priority": a.get("priority", "Medium"),
            })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Calendar widget
# ------------------------------------------------------------------
def get_pending_deadline_days(meetings: list, year: int, month: int) -> set:
    days = set()
    for m in meetings:
        for a in m.get("actions", []) or []:
            if normalize_status(a) not in {"Pending", "In Progress", "Overdue"}:
                continue
            deadline = normalize_value(a.get("deadline"), "")
            if not deadline or deadline in ("None", "Not stated"):
                continue
            try:
                parsed = datetime.strptime(str(deadline), "%Y-%m-%d").date()
            except Exception:
                continue
            if parsed.year == year and parsed.month == month:
                days.add(parsed.day)
    return days


def get_meeting_conducted_days(meetings: list, year: int, month: int) -> set:
    """Return set of day numbers when meetings were actually conducted."""
    days = set()
    for m in meetings:
        meeting_date_str = normalize_value(m.get("date"), "")
        if not meeting_date_str:
            continue
        try:
            parsed = datetime.strptime(str(meeting_date_str), "%Y-%m-%d").date()
        except Exception:
            continue
        if parsed.year == year and parsed.month == month:
            days.add(parsed.day)
    return days


def build_calendar_html(meetings: list, year: int, month: int) -> str:
    """HTML calendar for the dashboard.

    Yellow = pending action deadline.
    Blue   = meeting conducted on that date.
    """
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    header = "".join(f"<div class='calendar-day-label'>{l}</div>" for l in labels)
    today = date.today()
    pending = get_pending_deadline_days(meetings, year, month)
    conducted = get_meeting_conducted_days(meetings, year, month)
    cells = []
    for week in weeks:
        for day_num in week:
            classes = ["calendar-day"]
            label = "" if day_num == 0 else str(day_num)
            if day_num == 0:
                classes.append("empty")
            else:
                if day_num in conducted:
                    classes.append("meeting-conducted")
                if day_num in pending:
                    classes.append("pending-deadline")
                if day_num == today.day and month == today.month and year == today.year:
                    classes.append("today")
            cells.append(f"<div class='{' '.join(classes)}'>{label}</div>")

    legend = (
        "<div style='display:flex;gap:1rem;margin-top:0.5rem;font-size:0.75rem;'>"
        "<span><span style='display:inline-block;width:10px;height:10px;border-radius:3px;"
        "background:#dbeafe;border:1px solid #3b82f6;margin-right:3px'></span>Meeting held</span>"
        "<span><span style='display:inline-block;width:10px;height:10px;border-radius:3px;"
        "background:#fef3c7;border:1px solid #f59e0b;margin-right:3px'></span>Action deadline</span>"
        "</div>"
    )
    return (
        "<div class='calendar-widget'>"
        f"<div class='calendar-grid calendar-head'>{header}</div>"
        f"<div class='calendar-grid'>{''.join(cells)}</div>"
        f"{legend}"
        "</div>"
    )


# ------------------------------------------------------------------
# Chat bubble
# ------------------------------------------------------------------
def render_chat_bubble_html(role: str, text: str) -> str:
    safe = html.escape(str(text)).replace("\n", "<br>")
    return f"<div class='chat-bubble {role}'>{safe}</div>"


# ------------------------------------------------------------------
# Upcoming-meetings list (deadline-sorted)
# ------------------------------------------------------------------
def get_upcoming_meetings(meetings: list, limit: int = 4) -> list:
    candidates = []
    for m in meetings:
        active = [a for a in (m.get("actions") or []) if normalize_status(a) in {"Pending", "In Progress"}]
        if not active:
            continue
        deadlines = []
        for a in active:
            d = normalize_value(a.get("deadline"), "")
            if not d or d == "None":
                continue
            try:
                deadlines.append(datetime.strptime(d, "%Y-%m-%d").date())
            except Exception:
                continue
        if deadlines:
            key = min(deadlines)
        else:
            try:
                key = datetime.strptime(str(m.get("date", "")), "%Y-%m-%d").date()
            except Exception:
                key = date.max
        candidates.append((key, m))
    candidates.sort(key=lambda t: t[0])
    return [m for _, m in candidates[:limit]]


def get_meetings_on_date(meetings: list, target_date: str) -> list:
    """Return meetings whose conducted date matches target_date (YYYY-MM-DD)."""
    return [m for m in meetings if normalize_value(m.get("date"), "") == target_date]


def get_actions_due_on_date(meetings: list, target_date: str) -> list:
    """Return action items (with their meeting title) due on target_date."""
    rows = []
    for m in meetings:
        for a in (m.get("actions") or []):
            if normalize_value(a.get("deadline"), "") == target_date:
                rows.append({**a, "_meeting_title": normalize_value(m.get("title"), "Untitled")})
    return rows


def get_all_active_meetings(meetings: list) -> list:
    """Return all meetings that have at least one non-done action item.

    Sorted so most-urgent (overdue / due soonest) meetings appear first.
    """
    from utils.helpers import days_left, normalize_status, normalize_value

    candidates = []
    for m in meetings:
        actions = [
            a for a in (m.get("actions") or [])
            if normalize_status(a) not in ("Done", "Cancelled")
        ]
        if not actions:
            continue

        # Urgency key: minimum days_left across actions with deadlines
        dl_values = []
        for a in actions:
            d = normalize_value(a.get("deadline"), "")
            if d and d not in ("None", "Not stated"):
                dl = days_left(d)
                if dl is not None:
                    dl_values.append(dl)

        # Meetings with overdue/nearest deadlines first; no-deadline meetings last
        urgency = min(dl_values) if dl_values else 9999
        candidates.append((urgency, m))

    candidates.sort(key=lambda t: t[0])
    return [m for _, m in candidates]


def get_digest_items(meetings: list) -> dict:
    """Categorise all non-done action items for the daily digest.

    Returns a dict with keys:
      overdue      — past deadline
      due_today    — deadline is today
      due_3days    — deadline within 3 days (excl. today)
      due_week     — deadline within 4-7 days
      stale        — Pending > 14 days, no deadline set or far away
    Each value is a list of dicts: {text, owner, department, deadline, meeting_title, meeting_date, days_left, sitting_days}
    """
    from utils.helpers import days_left, normalize_status, normalize_value

    result = {
        "overdue":   [],
        "due_today":  [],
        "due_3days":  [],
        "due_week":   [],
        "stale":      [],
    }

    today = date.today()

    for m in meetings:
        m_title = normalize_value(m.get("title"), "Untitled")
        m_date_str = normalize_value(m.get("date"), "")
        # how many days has this meeting been in the system
        try:
            m_date = datetime.strptime(m_date_str, "%Y-%m-%d").date()
            sitting = (today - m_date).days
        except Exception:
            sitting = 0

        for a in (m.get("actions") or []):
            status = normalize_status(a)
            if status in ("Done", "Cancelled"):
                continue

            deadline_str = normalize_value(a.get("deadline"), "")
            dl = days_left(deadline_str) if deadline_str not in ("", "None", "Not stated") else None

            row = {
                "text":          normalize_value(a.get("text"), "Untitled action"),
                "owner":         normalize_value(a.get("owner"), "Not stated"),
                "department":    normalize_value(a.get("department") or a.get("company"), ""),
                "deadline":      deadline_str if deadline_str not in ("", "None", "Not stated") else "Not stated",
                "meeting_title": m_title,
                "meeting_date":  m_date_str,
                "days_left":     dl,
                "sitting_days":  sitting,
                "status":        status,
            }

            if dl is not None and dl < 0:
                result["overdue"].append(row)
            elif dl == 0:
                result["due_today"].append(row)
            elif dl is not None and dl <= 3:
                result["due_3days"].append(row)
            elif dl is not None and dl <= 7:
                result["due_week"].append(row)
            elif sitting >= 14 and status == "Pending":
                result["stale"].append(row)

    # Sort each bucket
    for key in ("overdue", "due_today", "due_3days", "due_week"):
        result[key].sort(key=lambda r: (r["days_left"] or 0))
    result["stale"].sort(key=lambda r: r["sitting_days"], reverse=True)

    return result


def get_meetings_for_deadline(meetings: list, target_date: date) -> list:
    target_text = target_date.isoformat()
    out = []
    for m in meetings:
        actions = m.get("actions") or []
        if any(
            normalize_status(a) in {"Pending", "In Progress"}
            and normalize_value(a.get("deadline"), "") == target_text
            for a in actions
        ):
            out.append(m)
    return out
