"""Folder management for the Action Tracker.

Folders are stored in a local JSON file (data/folders.json).
Structure: { "folder_name": ["meeting_id1", "meeting_id2", ...], ... }
"""
from __future__ import annotations
import json
from pathlib import Path

_FOLDER_PATH = Path(__file__).parent.parent / "data" / "folders.json"


def _load() -> dict[str, list[str]]:
    try:
        if _FOLDER_PATH.exists():
            return json.loads(_FOLDER_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict[str, list[str]]) -> None:
    _FOLDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _FOLDER_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_folders() -> dict[str, list[str]]:
    """Return all folders as {folder_name: [meeting_id, ...]}."""
    return _load()


def create_folder(name: str) -> bool:
    """Create a new empty folder. Returns False if it already exists."""
    name = name.strip()
    if not name:
        return False
    data = _load()
    if name in data:
        return False
    data[name] = []
    _save(data)
    return True


def rename_folder(old_name: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name:
        return False
    data = _load()
    if old_name not in data or new_name in data:
        return False
    data[new_name] = data.pop(old_name)
    _save(data)
    return True


def delete_folder(name: str) -> None:
    """Delete a folder (meetings are NOT deleted, just unlinked)."""
    data = _load()
    data.pop(name, None)
    _save(data)


def add_meeting_to_folder(folder_name: str, meeting_id: str) -> None:
    data = _load()
    if folder_name not in data:
        data[folder_name] = []
    if meeting_id not in data[folder_name]:
        data[folder_name].append(meeting_id)
    _save(data)


def remove_meeting_from_folder(folder_name: str, meeting_id: str) -> None:
    data = _load()
    if folder_name in data and meeting_id in data[folder_name]:
        data[folder_name].remove(meeting_id)
    _save(data)


def get_meeting_folder(meeting_id: str) -> str | None:
    """Return the folder a meeting belongs to, or None."""
    for name, ids in _load().items():
        if meeting_id in ids:
            return name
    return None


def get_all_assigned_ids() -> set[str]:
    """Return all meeting IDs that are assigned to any folder."""
    data = _load()
    return {mid for ids in data.values() for mid in ids}
