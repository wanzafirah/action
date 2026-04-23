"""Supabase persistence layer.

Uses the REST API directly (no extra SDK dependency) so deployment on
Streamlit Cloud stays lightweight.

Tables expected in Supabase:
    meetings     (id text pk, user_id, title, date, category, summary,
                  objective, outcome, follow_up bool, follow_up_reason,
                  stakeholders jsonb, companies jsonb, key_decisions jsonb,
                  discussion_points jsonb, actions jsonb, transcript,
                  department, activity_id, created_at timestamptz default now())

    departments  (id text pk, name text, budget numeric)

    history      (id text pk, user_id, thread_key, thread_date, thread_title,
                  timestamp, question, answer, meeting_id, meeting_title,
                  context)
"""
from __future__ import annotations

import requests
import streamlit as st

from config.constants import DEPARTMENTS_TABLE, HISTORY_TABLE, MEETINGS_TABLE
from config.settings import get_supabase_config, is_supabase_configured
from utils.helpers import json_dumps_safe, json_loads_safe


# ------------------------------------------------------------------
# Low-level HTTP
# ------------------------------------------------------------------
def _headers(prefer: str = "return=representation") -> dict:
    cfg = get_supabase_config()
    return {
        "apikey": cfg["key"],
        "Authorization": f"Bearer {cfg['key']}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _table_url(table: str) -> str:
    return f"{get_supabase_config()['url']}/rest/v1/{table}"


def _get(table: str) -> list[dict]:
    response = requests.get(_table_url(table), headers=_headers(), params={"select": "*"}, timeout=30)
    response.raise_for_status()
    return response.json() or []


def _upsert(table: str, rows: list[dict]) -> None:
    if not rows:
        return
    response = requests.post(
        _table_url(table),
        headers=_headers(prefer="resolution=merge-duplicates,return=minimal"),
        json=rows,
        timeout=60,
    )
    response.raise_for_status()


def _delete_by_id(table: str, row_id: str) -> None:
    response = requests.delete(
        _table_url(table),
        headers=_headers(prefer="return=minimal"),
        params={"id": f"eq.{row_id}"},
        timeout=30,
    )
    response.raise_for_status()


# ------------------------------------------------------------------
# Row <-> dict conversion
# ------------------------------------------------------------------
# Columns stored as JSON text in Supabase (jsonb works too).
_MEETING_JSON_COLS = (
    "stakeholders", "companies", "key_decisions", "discussion_points", "actions",
)


def _serialize_meeting(meeting: dict) -> dict:
    """Turn an in-memory meeting dict into a Supabase row."""
    row = {
        "id": meeting.get("id"),
        "user_id": meeting.get("user_id", ""),
        "title": meeting.get("title", ""),
        "date": meeting.get("date", ""),
        "category": meeting.get("category", ""),
        "summary": meeting.get("summary", ""),
        "objective": meeting.get("objective", ""),
        "outcome": meeting.get("outcome", ""),
        "follow_up": bool(meeting.get("followUp", False)),
        "follow_up_reason": meeting.get("followUpReason", ""),
        "transcript": meeting.get("transcript", ""),
        "transcript_original": meeting.get("transcript_original", ""),
        "recap_original": meeting.get("recap_original", ""),
        "department": meeting.get("deptName") or meeting.get("department", ""),
        "activity_id": meeting.get("activityId") or meeting.get("meetingID", ""),
        # JSON fields
        "stakeholders": json_dumps_safe(meeting.get("stakeholders", [])),
        "companies": json_dumps_safe(meeting.get("companies", [])),
        "key_decisions": json_dumps_safe(meeting.get("keyDecisions", [])),
        "discussion_points": json_dumps_safe(meeting.get("discussionPoints", [])),
        "actions": json_dumps_safe(meeting.get("actions", [])),
    }
    return row


def _deserialize_meeting(row: dict) -> dict:
    """Turn a Supabase row back into the in-memory shape the UI expects."""
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id", ""),
        "title": row.get("title", ""),
        "date": row.get("date", ""),
        "category": row.get("category", "Internal Meeting"),
        "summary": row.get("summary", ""),
        "objective": row.get("objective", ""),
        "outcome": row.get("outcome", ""),
        "followUp": bool(row.get("follow_up", False)),
        "followUpReason": row.get("follow_up_reason", ""),
        "transcript": row.get("transcript", ""),
        "transcript_original": row.get("transcript_original", ""),
        "recap_original": row.get("recap_original", ""),
        "deptName": row.get("department", ""),
        "department": row.get("department", ""),
        "activityId": row.get("activity_id", ""),
        "meetingID": row.get("activity_id", ""),
        "stakeholders": json_loads_safe(row.get("stakeholders"), []),
        "companies": json_loads_safe(row.get("companies"), []),
        "keyDecisions": json_loads_safe(row.get("key_decisions"), []),
        "discussionPoints": json_loads_safe(row.get("discussion_points"), []),
        "actions": json_loads_safe(row.get("actions"), []),
    }


# ------------------------------------------------------------------
# Public API  (used by pages/)
# ------------------------------------------------------------------
def load_all() -> tuple[list, list, list]:
    """Return (meetings, departments, history). Empty lists if Supabase isn't set up."""
    if not is_supabase_configured():
        st.warning(
            "Supabase is not configured. Add SUPABASE_URL and SUPABASE_KEY to "
            "`.streamlit/secrets.toml` (or as environment variables) to persist data."
        )
        return [], [], []

    try:
        meetings_raw = _get(MEETINGS_TABLE)
        departments = _get(DEPARTMENTS_TABLE)
        history = _get(HISTORY_TABLE)
    except requests.HTTPError as exc:
        st.error(f"Supabase load failed: {exc.response.text[:200] if exc.response else exc}")
        return [], [], []
    except Exception as exc:
        st.error(f"Supabase load failed: {exc}")
        return [], [], []

    meetings = [_deserialize_meeting(row) for row in meetings_raw]
    return meetings, departments, history


def save_meeting(meeting: dict) -> None:
    if not is_supabase_configured():
        return
    _upsert(MEETINGS_TABLE, [_serialize_meeting(meeting)])


def delete_meeting(meeting_id: str) -> None:
    if not is_supabase_configured():
        return
    _delete_by_id(MEETINGS_TABLE, meeting_id)


def save_department(department: dict) -> None:
    if not is_supabase_configured():
        return
    _upsert(DEPARTMENTS_TABLE, [{
        "id": department.get("id"),
        "name": department.get("name", ""),
        "budget": float(department.get("budget", 0) or 0),
    }])


def save_history_entry(entry: dict) -> None:
    if not is_supabase_configured():
        return
    _upsert(HISTORY_TABLE, [{
        "id": entry.get("id"),
        "user_id": entry.get("user_id", ""),
        "thread_key": entry.get("thread_key", ""),
        "thread_date": entry.get("thread_date", ""),
        "thread_title": entry.get("thread_title", ""),
        "timestamp": entry.get("timestamp", ""),
        "question": entry.get("question", ""),
        "answer": entry.get("answer", ""),
        "meeting_id": entry.get("meeting_id", ""),
        "meeting_title": entry.get("meeting_title", ""),
        "context": entry.get("context", "general"),
    }])
