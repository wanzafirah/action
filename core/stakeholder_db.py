"""External stakeholder persistence — Supabase primary, local JSON fallback.

Supabase table: stakeholders
Each record: {id, name, position, organisation, phone, email, date_added, meeting_ids}

Falls back to data/stakeholders.json when Supabase is not configured.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import requests

from utils.helpers import uid

_DATA_FILE = Path(__file__).parent.parent / "data" / "stakeholders.json"
_TABLE = "stakeholders"


# ------------------------------------------------------------------
# Supabase helpers (mirrors core/database.py pattern)
# ------------------------------------------------------------------
def _is_configured() -> bool:
    try:
        from config.settings import is_supabase_configured
        return is_supabase_configured()
    except Exception:
        return False


def _headers(prefer: str = "return=representation") -> dict:
    from config.settings import get_supabase_config
    cfg = get_supabase_config()
    return {
        "apikey": cfg["key"],
        "Authorization": f"Bearer {cfg['key']}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _table_url() -> str:
    from config.settings import get_supabase_config
    return f"{get_supabase_config()['url']}/rest/v1/{_TABLE}"


def _sb_load() -> list[dict]:
    resp = requests.get(_table_url(), headers=_headers(), params={"select": "*"}, timeout=30)
    resp.raise_for_status()
    rows = resp.json() or []
    result = []
    for row in rows:
        # meeting_ids may be stored as a JSON string or a native list
        mids = row.get("meeting_ids", [])
        if isinstance(mids, str):
            try:
                mids = json.loads(mids)
            except Exception:
                mids = []
        result.append({
            "id":           row.get("id", ""),
            "name":         row.get("name", ""),
            "position":     row.get("position", ""),
            "organisation": row.get("organisation", ""),
            "phone":        row.get("phone", ""),
            "email":        row.get("email", ""),
            "date_added":   str(row.get("date_added", "")),
            "meeting_ids":  mids,
        })
    return result


def _sb_upsert(stakeholders: list[dict]) -> None:
    if not stakeholders:
        return
    rows = []
    for s in stakeholders:
        rows.append({
            "id":           s.get("id") or uid(),
            "name":         s.get("name", ""),
            "position":     s.get("position", ""),
            "organisation": s.get("organisation", ""),
            "phone":        s.get("phone", ""),
            "email":        s.get("email", ""),
            "date_added":   s.get("date_added") or date.today().isoformat(),
            "meeting_ids":  json.dumps(s.get("meeting_ids", [])),
        })
    resp = requests.post(
        _table_url(),
        headers=_headers(prefer="resolution=merge-duplicates,return=minimal"),
        json=rows,
        timeout=60,
    )
    resp.raise_for_status()


def _sb_delete(stakeholder_id: str) -> None:
    resp = requests.delete(
        _table_url(),
        headers=_headers(prefer="return=minimal"),
        params={"id": f"eq.{stakeholder_id}"},
        timeout=30,
    )
    resp.raise_for_status()


# ------------------------------------------------------------------
# Local JSON fallback
# ------------------------------------------------------------------
def _local_load() -> list[dict]:
    if not _DATA_FILE.exists():
        return []
    try:
        return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _local_save(stakeholders: list[dict]) -> None:
    _DATA_FILE.parent.mkdir(exist_ok=True)
    _DATA_FILE.write_text(
        json.dumps(stakeholders, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------
def load_external_stakeholders() -> list[dict]:
    if _is_configured():
        try:
            return _sb_load()
        except Exception:
            pass
    return _local_load()


def save_external_stakeholders(stakeholders: list[dict]) -> None:
    if _is_configured():
        try:
            _sb_upsert(stakeholders)
            return
        except Exception:
            pass
    _local_save(stakeholders)


def delete_external_stakeholder(stakeholder_id: str) -> None:
    """Delete a single stakeholder by id."""
    if _is_configured():
        try:
            _sb_delete(stakeholder_id)
            return
        except Exception:
            pass
    # Fallback: remove from local JSON
    all_s = _local_load()
    _local_save([s for s in all_s if s.get("id") != stakeholder_id])


def upsert_stakeholders_from_meeting(meeting_id: str, new_entries: list[dict]) -> None:
    """Merge meeting's external stakeholders into the central directory."""
    if not new_entries:
        return
    all_s = load_external_stakeholders()
    existing_keys = {
        (s.get("name", "").lower(), s.get("organisation", "").lower())
        for s in all_s
    }
    changed: list[dict] = []
    for entry in new_entries:
        key = (entry.get("name", "").lower(), entry.get("organisation", "").lower())
        if key in existing_keys:
            for s in all_s:
                if (s.get("name", "").lower(), s.get("organisation", "").lower()) == key:
                    if meeting_id not in s.get("meeting_ids", []):
                        s.setdefault("meeting_ids", []).append(meeting_id)
                        changed.append(s)
        else:
            new = {
                "id":           entry.get("id") or uid(),
                "name":         entry.get("name", ""),
                "position":     entry.get("position", ""),
                "organisation": entry.get("organisation", ""),
                "phone":        entry.get("phone", ""),
                "email":        entry.get("email", ""),
                "date_added":   date.today().isoformat(),
                "meeting_ids":  [meeting_id],
            }
            all_s.append(new)
            changed.append(new)
            existing_keys.add(key)

    if not changed:
        return

    # Write back
    if _is_configured():
        try:
            _sb_upsert(changed)
            return
        except Exception:
            pass
    _local_save(all_s)
