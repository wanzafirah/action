"""Local JSON persistence for external stakeholders (non-TC contacts).

Stored at data/stakeholders.json — survives app restarts.
Each record: {id, name, position, organisation, phone, email, meeting_ids[]}
"""
from __future__ import annotations

import json
from pathlib import Path

from utils.helpers import uid

_DATA_FILE = Path(__file__).parent.parent / "data" / "stakeholders.json"


def load_external_stakeholders() -> list[dict]:
    if not _DATA_FILE.exists():
        return []
    try:
        return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_external_stakeholders(stakeholders: list[dict]) -> None:
    _DATA_FILE.parent.mkdir(exist_ok=True)
    _DATA_FILE.write_text(
        json.dumps(stakeholders, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def upsert_stakeholders_from_meeting(meeting_id: str, new_entries: list[dict]) -> None:
    """Merge meeting's external stakeholders into the central directory."""
    if not new_entries:
        return
    all_s = load_external_stakeholders()
    existing_keys = {
        (s.get("name", "").lower(), s.get("organisation", "").lower())
        for s in all_s
    }
    for entry in new_entries:
        key = (entry.get("name", "").lower(), entry.get("organisation", "").lower())
        if key in existing_keys:
            # Add meeting_id reference to existing record
            for s in all_s:
                if (s.get("name", "").lower(), s.get("organisation", "").lower()) == key:
                    if meeting_id not in s.get("meeting_ids", []):
                        s.setdefault("meeting_ids", []).append(meeting_id)
        else:
            all_s.append({
                "id":           entry.get("id") or uid(),
                "name":         entry.get("name", ""),
                "position":     entry.get("position", ""),
                "organisation": entry.get("organisation", ""),
                "phone":        entry.get("phone", ""),
                "email":        entry.get("email", ""),
                "meeting_ids":  [meeting_id],
            })
            existing_keys.add(key)
    save_external_stakeholders(all_s)
