"""Pure helper functions (no Streamlit imports).

These are small building blocks used across the app. Keeping them Streamlit-
free makes them easy to reason about and unit-test.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from uuid import uuid4


# ------------------------------------------------------------------
# ID generation
# ------------------------------------------------------------------
def uid() -> str:
    return uuid4().hex[:9]


def today_str() -> str:
    return date.today().isoformat()


def meeting_id_prefix(category: str) -> str:
    mapping = {
        "external meeting": "EX",
        "internal meeting": "IN",
        "workshop": "WS",
    }
    category_text = str(category or "").strip().lower()
    if category_text in mapping:
        return mapping[category_text]
    cleaned = re.sub(r"[^A-Z]", "", str(category or "").upper())
    return cleaned[:2] if cleaned else "MT"


def generate_activity_id(category: str, meeting_date: date, meetings: list | None = None) -> str:
    """Return the next sequential activity id, e.g. IN-2026-001."""
    prefix = meeting_id_prefix(category)
    year_text = str(meeting_date.year)
    pattern = re.compile(rf"^{re.escape(prefix)}-{re.escape(year_text)}-(\d{{3}})$")
    next_number = 1
    if meetings:
        numbers = []
        for meeting in meetings:
            candidate = str(
                meeting.get("meetingID")
                or meeting.get("activityId")
                or meeting.get("id")
                or ""
            ).strip()
            m = pattern.match(candidate)
            if m:
                try:
                    numbers.append(int(m.group(1)))
                except Exception:
                    pass
        if numbers:
            next_number = max(numbers) + 1
    return f"{prefix}-{year_text}-{next_number:03d}"


# ------------------------------------------------------------------
# Deadline helpers
# ------------------------------------------------------------------
def days_left(deadline: str):
    try:
        return (datetime.strptime(str(deadline), "%Y-%m-%d").date() - date.today()).days
    except Exception:
        return None


def pretty_deadline(deadline: str) -> str:
    if not deadline or deadline == "None":
        return "None"
    delta = days_left(deadline)
    if delta is None:
        return deadline
    if delta < 0:
        return f"{deadline} | {abs(delta)}d overdue"
    if delta == 0:
        return f"{deadline} | due today"
    return f"{deadline} | {delta}d left"


def normalize_status(action: dict) -> str:
    """Return 'Overdue' automatically when a deadline has passed."""
    current = action.get("status", "Pending")
    if current in ("Done", "Cancelled"):
        return current
    delta = days_left(action.get("deadline", ""))
    if delta is not None and delta < 0:
        return "Overdue"
    return current


# ------------------------------------------------------------------
# Value / list normalisation
# ------------------------------------------------------------------
def normalize_value(value, fallback: str = "None") -> str:
    """Turn any LLM output (str/dict/list/None) into a clean display string."""
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, dict):
        for key in ("text", "title", "name", "decision", "point", "summary", "value"):
            if key in value and str(value[key]).strip():
                return str(value[key]).strip()
        parts = [f"{k}: {v}" for k, v in value.items() if str(v).strip()]
        return "; ".join(parts) if parts else fallback
    if isinstance(value, list):
        parts = [normalize_value(item, "") for item in value]
        parts = [p for p in parts if p]
        return ", ".join(parts) if parts else fallback
    return str(value).strip() or fallback


def join_list(items: list, fallback: str = "None") -> str:
    clean = [str(i) for i in (items or []) if str(i).strip()]
    return ", ".join(clean) if clean else fallback


def html_lines(items, fallback: str = "None") -> str:
    rendered = [normalize_value(i, "") for i in (items or [])]
    rendered = [i for i in rendered if i]
    return "<br>".join(rendered) if rendered else fallback


def load_text_list(value) -> list:
    """Parse a value that might be a JSON list, a comma-separated string, or a list."""
    if value in ("", None):
        return []
    if isinstance(value, list):
        return [str(i).strip() for i in value if str(i).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(i).strip() for i in parsed if str(i).strip()]
        except Exception:
            pass
        return [p.strip() for p in re.split(r"[;,]\s*", value) if p.strip()]
    text = str(value).strip()
    return [text] if text else []


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------
def parse_yes_no(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("yes", "y", "true", "1")
    return bool(value)


def yes_no_text(value) -> str:
    return "Yes" if parse_yes_no(value) else "No"


def json_dumps_safe(value) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def json_loads_safe(value, fallback):
    if value in ("", None):
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


# ------------------------------------------------------------------
# Transcript helpers
# ------------------------------------------------------------------
def transcript_sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text or "") if p.strip()]


def compact_transcript_for_prompt(text: str, max_chars: int = 2200) -> str:
    """Trim a transcript to fit in the LLM context, keeping high-signal lines."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    keywords = (
        "action", "deadline", "follow-up", "follow up", "decision", "agreed",
        "approved", "pending", "date", "month", "budget", "owner", "assign", "task",
    )
    priority = [s for s in transcript_sentences(text) if any(k in s.lower() for k in keywords)]
    compacted = " ".join(priority)[:max_chars].strip()
    return compacted or text[:max_chars].strip()


# ------------------------------------------------------------------
# Simple HTML snippet
# ------------------------------------------------------------------
def pill(label: str, color: str, bg: str) -> str:
    return (
        f"<span style='display:inline-block;padding:0.3rem 0.7rem;border-radius:999px;"
        f"background:{bg};color:{color};font-weight:600;font-size:0.82rem'>{label}</span>"
    )
