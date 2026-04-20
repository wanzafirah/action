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
            if normalize_status(a) != "Pending":
                continue
            deadline = normalize_value(a.get("deadline"), "")
            if not deadline or deadline == "None":
                continue
            try:
                parsed = datetime.strptime(str(deadline), "%Y-%m-%d").date()
            except Exception:
                continue
            if parsed.year == year and parsed.month == month:
                days.add(parsed.day)
    return days


def build_calendar_html(meetings: list, year: int, month: int) -> str:
    """HTML calendar for the dashboard; pending deadlines are highlighted."""
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    header = "".join(f"<div class='calendar-day-label'>{l}</div>" for l in labels)
    today = date.today()
    pending = get_pending_deadline_days(meetings, year, month)
    cells = []
    for week in weeks:
        for day_num in week:
            classes = ["calendar-day"]
            label = "" if day_num == 0 else str(day_num)
            if day_num == 0:
                classes.append("empty")
            else:
                if day_num in pending:
                    classes.append("pending-deadline")
                if day_num == today.day and month == today.month and year == today.year:
                    classes.append("today")
            cells.append(f"<div class='{' '.join(classes)}'>{label}</div>")
    return (
        "<div class='calendar-widget'>"
        f"<div class='calendar-grid calendar-head'>{header}</div>"
        f"<div class='calendar-grid'>{''.join(cells)}</div>"
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
