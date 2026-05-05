"""PDF export utility for meeting briefs.

Uses reportlab (pre-installed) to generate a formatted PDF bytes object
that can be streamed as a Streamlit download button.
"""
from __future__ import annotations

import io
from datetime import datetime

from utils.helpers import normalize_status, normalize_value


# ── Colour palette (matches app theme) ─────────────────────────────
BRAND       = (14, 27, 72)       # #0E1B48
BRAND_2     = (39, 66, 93)       # #27425D
ACCENT      = (135, 167, 208)    # #87A7D0
SOFT_PINK   = (193, 141, 180)    # #C18DB4
TEXT        = (15, 23, 42)       # #0f172a
TEXT_MUTED  = (39, 66, 93)
TEXT_SOFT   = (110, 127, 150)    # #6e7f96
WHITE       = (255, 255, 255)
RED         = (153, 27, 27)
AMBER       = (180, 83, 9)
GREEN       = (22, 101, 52)
BLUE        = (29, 78, 216)
BG_SOFT     = (248, 246, 251)
BORDER      = (216, 220, 235)


def _r(rgb):
    return tuple(c / 255 for c in rgb)


def generate_meeting_pdf(meeting: dict) -> bytes:
    """Return a formatted PDF as bytes for a saved meeting record."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
        )
        from reportlab.lib import colors
    except ImportError:
        return b""

    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=normalize_value(meeting.get("title"), "Meeting Brief"),
    )

    brand_color   = colors.Color(*_r(BRAND))
    brand2_color  = colors.Color(*_r(BRAND_2))
    accent_color  = colors.Color(*_r(ACCENT))
    pink_color    = colors.Color(*_r(SOFT_PINK))
    text_color    = colors.Color(*_r(TEXT))
    muted_color   = colors.Color(*_r(TEXT_MUTED))
    soft_color    = colors.Color(*_r(TEXT_SOFT))
    red_color     = colors.Color(*_r(RED))
    amber_color   = colors.Color(*_r(AMBER))
    green_color   = colors.Color(*_r(GREEN))
    blue_color    = colors.Color(*_r(BLUE))
    bg_color      = colors.Color(*_r(BG_SOFT))
    border_color  = colors.Color(*_r(BORDER))

    STATUS_COLORS = {
        "Pending":     amber_color,
        "In Progress": blue_color,
        "Done":        green_color,
        "Overdue":     red_color,
        "Cancelled":   soft_color,
    }

    def _style(name, **kw):
        return ParagraphStyle(name, **kw)

    badge_style  = _style("badge",  fontSize=7,  textColor=colors.white,
                          backColor=brand2_color, borderPadding=(2, 5, 2, 5),
                          borderRadius=4, leading=12)
    title_style  = _style("title",  fontSize=20, textColor=brand_color,
                          fontName="Helvetica-Bold", spaceAfter=4, leading=24)
    h2_style     = _style("h2",     fontSize=13, textColor=brand2_color,
                          fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4, leading=16)
    label_style  = _style("label",  fontSize=8,  textColor=soft_color,
                          fontName="Helvetica-Bold",
                          textTransform="uppercase", letterSpacing=0.8)
    body_style   = _style("body",   fontSize=10, textColor=text_color,
                          fontName="Helvetica", leading=15, spaceAfter=3)
    meta_style   = _style("meta",   fontSize=9,  textColor=muted_color,
                          fontName="Helvetica", leading=13)
    action_style = _style("action", fontSize=10, textColor=text_color,
                          fontName="Helvetica-Bold", leading=14)
    sub_style    = _style("sub",    fontSize=9,  textColor=soft_color,
                          fontName="Helvetica", leading=12)
    footer_style = _style("footer", fontSize=8,  textColor=soft_color,
                          fontName="Helvetica-Oblique", alignment=TA_CENTER)

    story = []

    # ── Header banner ───────────────────────────────────────────────
    title   = normalize_value(meeting.get("title"), "Untitled Meeting")
    m_date  = normalize_value(meeting.get("date"), "")
    cat     = normalize_value(meeting.get("category"), "")
    dept    = normalize_value(meeting.get("deptName") or meeting.get("department"), "")
    act_id  = normalize_value(meeting.get("activityId") or meeting.get("meetingID"), "")
    rep_by  = normalize_value(meeting.get("user_id") or meeting.get("updated_by"), "")

    try:
        date_display = datetime.strptime(m_date, "%Y-%m-%d").strftime("%d %B %Y")
    except Exception:
        date_display = m_date

    header_data = [[
        Paragraph("MEETING BRIEF", badge_style),
        Paragraph(date_display, meta_style),
    ]]
    header_tbl = Table(header_data, colWidths=["70%", "30%"])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), brand_color),
        ("TEXTCOLOR",   (0, 0), (-1, -1), colors.white),
        ("ALIGN",       (1, 0), (1, 0),   "RIGHT"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), [6, 6, 6, 6]),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 12))

    story.append(Paragraph(title, title_style))

    # Meta row
    meta_parts = []
    if cat:      meta_parts.append(f"Category: {cat}")
    if dept:     meta_parts.append(f"Department: {dept}")
    if act_id:   meta_parts.append(f"ID: {act_id}")
    if rep_by:   meta_parts.append(f"Report by: {rep_by}")
    if meta_parts:
        story.append(Paragraph("  ·  ".join(meta_parts), meta_style))
    story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=8))

    # ── Summary & Objective ────────────────────────────────────────
    summary   = normalize_value(meeting.get("summary"),   "No summary provided.")
    objective = normalize_value(meeting.get("objective"), "")
    outcome   = normalize_value(meeting.get("outcome"),   "")
    follow_up = "Yes" if meeting.get("followUp") else "No"
    fu_reason = normalize_value(meeting.get("followUpReason"), "")

    story.append(Paragraph("Summary", h2_style))
    story.append(Paragraph(summary, body_style))

    if objective:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Objective", h2_style))
        story.append(Paragraph(objective, body_style))

    if outcome and outcome not in ("Not provided", "None"):
        story.append(Spacer(1, 6))
        story.append(Paragraph("Outcome", h2_style))
        story.append(Paragraph(outcome, body_style))

    # Follow-up
    fu_text = f"Follow-up required: {follow_up}"
    if follow_up == "Yes" and fu_reason:
        fu_text += f"  —  {fu_reason}"
    story.append(Spacer(1, 4))
    story.append(Paragraph(fu_text, meta_style))
    story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=8))

    # ── Action Items ───────────────────────────────────────────────
    actions = meeting.get("actions") or []
    if actions:
        story.append(Paragraph("Action Items", h2_style))

        for i, a in enumerate(actions, 1):
            status   = normalize_status(a)
            text     = normalize_value(a.get("text"),     "Untitled action")
            owner    = normalize_value(a.get("owner"),    "Not stated")
            dept_a   = normalize_value(a.get("department") or a.get("company"), "Not stated")
            deadline = normalize_value(a.get("deadline"), "Not stated")
            priority = normalize_value(a.get("priority"), "Medium")
            st_color = STATUS_COLORS.get(status, soft_color)

            row_data = [[
                Paragraph(f"{i}. {text}", action_style),
                Paragraph(status, ParagraphStyle("st", fontSize=8, textColor=st_color,
                                                  fontName="Helvetica-Bold")),
            ]]
            sub_data = [[
                Paragraph(f"Owner: {owner}  ·  Dept: {dept_a}  ·  Deadline: {deadline}  ·  Priority: {priority}", sub_style),
                "",
            ]]

            tbl = Table(row_data + sub_data, colWidths=["78%", "22%"])
            tbl.setStyle(TableStyle([
                ("BACKGROUND",  (0, 0), (-1, -1), bg_color),
                ("ALIGN",       (1, 0), (1, 0),   "RIGHT"),
                ("VALIGN",      (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING",  (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("BOX",         (0, 0), (-1, -1), 0.5, border_color),
                ("ROUNDEDCORNERS", (0, 0), (-1, -1), [4, 4, 4, 4]),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 4))

    # ── Footer ─────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=border_color))
    story.append(Spacer(1, 4))
    generated = datetime.now().strftime("%d %B %Y, %H:%M")
    story.append(Paragraph(
        f"Generated by AI-Powered Meeting Insight Generator  ·  {generated}",
        footer_style,
    ))

    doc.build(story)
    return buf.getvalue()


# ── iCalendar (.ics) export ─────────────────────────────────────────
def generate_ics(meeting: dict) -> bytes:
    """Generate an iCalendar (.ics) file for a meeting.

    The file contains:
    - An all-day calendar event on the meeting date
    - Meeting summary, objective, and action items in the description
    - A 1-day-before email + display reminder (VALARM)

    Recipients open the file → click "Add to Calendar" →
    Google Calendar / Outlook / Apple Calendar adds it with a reminder.
    """
    from datetime import datetime as _dt, timezone as _tz
    import uuid as _uuid

    title      = normalize_value(meeting.get("title"), "Meeting")
    date_str   = normalize_value(meeting.get("date"), "")
    summary    = normalize_value(meeting.get("summary"), "")
    objective  = normalize_value(meeting.get("objective"), "")
    report_by  = normalize_value(meeting.get("user_id") or meeting.get("updated_by"), "")
    actions    = meeting.get("actions") or []

    # Parse meeting date → YYYYMMDD for all-day event
    try:
        meeting_date = _dt.strptime(date_str, "%Y-%m-%d")
        dtstart = meeting_date.strftime("%Y%m%d")
        # All-day event ends the next day in iCal
        from datetime import timedelta as _td
        dtend = (meeting_date + _td(days=1)).strftime("%Y%m%d")
    except Exception:
        today = _dt.now()
        dtstart = today.strftime("%Y%m%d")
        dtend   = today.strftime("%Y%m%d")

    # Timestamp of when this .ics was created (UTC)
    dtstamp = _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")

    # Build description — escape commas, semicolons, newlines per RFC 5545
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    desc_parts = []
    if summary:
        desc_parts.append(f"Summary:\\n{summary}")
    if objective:
        desc_parts.append(f"Objective:\\n{objective}")

    pending_actions = [
        a for a in actions
        if normalize_status(a) not in ("Done", "Cancelled")
    ]
    if pending_actions:
        desc_parts.append("Action Items:")
        for i, a in enumerate(pending_actions, 1):
            text     = normalize_value(a.get("text"), "")
            owner    = normalize_value(a.get("owner"), "Not stated")
            deadline = normalize_value(a.get("deadline"), "Not stated")
            desc_parts.append(f"  {i}. {text} | Owner: {owner} | Deadline: {deadline}")

    if report_by:
        desc_parts.append(f"\\nReport by: {report_by}")

    description = _esc("\\n\\n".join(desc_parts))
    uid = str(_uuid.uuid4()) + "@meetiq"

    ics = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MeetIQ//Meeting Reminder//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        f"SUMMARY:Follow-Up: {_esc(title)}",
        f"DESCRIPTION:{description}",
        # Reminder: display alert 1 day before
        "BEGIN:VALARM",
        "TRIGGER:-P1D",
        "ACTION:DISPLAY",
        "DESCRIPTION:Meeting follow-up reminder",
        "END:VALARM",
        # Second reminder: email 1 day before
        "BEGIN:VALARM",
        "TRIGGER:-P1D",
        "ACTION:EMAIL",
        "SUMMARY:Meeting follow-up reminder",
        f"DESCRIPTION:{description}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])
    return ics.encode("utf-8")
