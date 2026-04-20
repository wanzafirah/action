"""Meeting analysis pipeline.

Flow:
    run_pipeline(transcript, metadata)
      -> compact transcript
      -> call Ollama once with PIPELINE_SYSTEM
      -> extract JSON (with repair fallback)
      -> normalize into a safe result shape
"""
from __future__ import annotations

import ast
import json
import re

from config.constants import JSON_REPAIR_SYSTEM, PIPELINE_SYSTEM
from core.services import call_ollama
from utils.helpers import (
    compact_transcript_for_prompt,
    normalize_value,
    parse_yes_no,
    transcript_sentences,
)


# ------------------------------------------------------------------
# JSON extraction / repair
# ------------------------------------------------------------------
def extract_json(raw: str) -> dict:
    """Parse JSON from the LLM output, tolerating small formatting mistakes."""
    cleaned = re.sub(r"```(?:json)?", "", raw or "").strip()
    cleaned = (
        cleaned.replace("\u201c", '"').replace("\u201d", '"')
               .replace("\u2018", "'").replace("\u2019", "'")
    )

    # 1. Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2. Find the JSON object inside and attempt small repairs
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise json.JSONDecodeError("No JSON object found", cleaned, 0)
    candidate = match.group(0).strip()

    repairs = [
        candidate,
        re.sub(r",\s*([}\]])", r"\1", candidate),                           # trailing commas
        re.sub(r'([{\s,])([A-Za-z_][\w\- ]*)(\s*:)', r'\1"\2"\3', candidate),  # bare keys
    ]
    for repair in repairs:
        try:
            return json.loads(repair)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(repair)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    raise json.JSONDecodeError("Unable to parse JSON", candidate, 0)


def _repair_with_ollama(raw: str) -> dict:
    prompt = f"Fix this into valid JSON only:\n\n{raw[:2500]}"
    repaired = call_ollama(JSON_REPAIR_SYSTEM, prompt, max_tokens=1500)
    return extract_json(repaired)


# ------------------------------------------------------------------
# Safe default result
# ------------------------------------------------------------------
def _safe_result(transcript: str, metadata: dict | None = None) -> dict:
    """Minimal valid result used when the LLM call fails entirely."""
    metadata = metadata or {}
    return {
        "title": normalize_value(metadata.get("Title") or metadata.get("Activity Title"), "Untitled"),
        "meeting_type": normalize_value(metadata.get("Activity Type"), "Not Provided"),
        "category": normalize_value(metadata.get("Category"), "Not Provided"),
        "nlp_pipeline": {
            "token_count": len((transcript or "").split()),
            "sentence_count": len(transcript_sentences(transcript)),
            "named_entities": {"persons": [], "organizations": [], "dates": [], "locations": []},
        },
        "classification": {"action_items_count": 0, "decisions_count": 0, "discussion_points_count": 0},
        "objective": "Objective could not be extracted.",
        "summary": "Summary could not be generated from the transcript.",
        "outcome": "Not provided",
        "follow_up": False,
        "follow_up_reason": "",
        "key_decisions": [],
        "discussion_points": [],
        "action_items": [],
    }


# ------------------------------------------------------------------
# Normalisation
# ------------------------------------------------------------------
def normalize_result(result: dict, transcript: str, metadata: dict | None = None) -> dict:
    """Ensure the result has every required key and consistent types."""
    safe = _safe_result(transcript, metadata)
    if not isinstance(result, dict):
        return safe

    merged = {**safe, **result}

    # Nested dicts — merge key by key so missing subkeys get their defaults.
    merged["nlp_pipeline"] = {**safe["nlp_pipeline"], **(result.get("nlp_pipeline") or {})}
    merged["nlp_pipeline"]["named_entities"] = {
        **safe["nlp_pipeline"]["named_entities"],
        **((result.get("nlp_pipeline") or {}).get("named_entities") or {}),
    }
    merged["classification"] = {**safe["classification"], **(result.get("classification") or {})}

    # Lists must be lists
    for key in ("key_decisions", "discussion_points", "action_items"):
        if not isinstance(merged.get(key), list):
            merged[key] = safe[key]

    # Strings must be non-empty
    for key in ("title", "meeting_type", "category", "objective", "summary", "outcome"):
        merged[key] = normalize_value(merged.get(key), safe[key])

    # Booleans
    merged["follow_up"] = parse_yes_no(merged.get("follow_up"))
    merged["follow_up_reason"] = normalize_value(merged.get("follow_up_reason"), "")

    # Clean each action item so later UI code can trust the shape.
    cleaned_actions = []
    for action in merged["action_items"]:
        if not isinstance(action, dict):
            continue
        owner = normalize_value(action.get("owner"), "Not stated")
        department = normalize_value(action.get("department") or action.get("company"), "Not stated")
        cleaned_actions.append({
            "text": normalize_value(action.get("text"), "Untitled action"),
            "owner": owner,
            "department": department,
            "company": department,
            "deadline": normalize_value(action.get("deadline"), "None"),
            "priority": normalize_value(action.get("priority"), "Medium"),
            "status": normalize_value(action.get("status"), "Pending"),
            "follow_up_required": parse_yes_no(action.get("follow_up_required", True)),
            "follow_up_reason": normalize_value(action.get("follow_up_reason"), ""),
            "suggestion": normalize_value(
                action.get("suggestion"),
                f"Coordinate with {owner} to close this item.",
            ),
        })
    merged["action_items"] = cleaned_actions

    # Keep classification counts in sync.
    merged["classification"]["action_items_count"] = len(cleaned_actions)
    merged["classification"]["decisions_count"] = len(merged["key_decisions"])
    merged["classification"]["discussion_points_count"] = len(merged["discussion_points"])

    # Follow-up is true when there is at least one action.
    merged["follow_up"] = bool(cleaned_actions) or merged["follow_up"]

    return merged


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------
def run_pipeline(transcript: str, metadata: dict | None = None) -> dict:
    """Analyse a transcript and return the normalised meeting brief."""
    compact = compact_transcript_for_prompt((transcript or "").strip(), max_chars=2200)

    metadata_lines = [
        f"{label}: {normalize_value(value, '')}"
        for label, value in (metadata or {}).items()
        if normalize_value(value, "")
    ]
    metadata_block = "\n".join(metadata_lines) or "None provided"

    user_msg = (
        "Return detailed JSON with summary, objective, outcome, follow-up, action items, "
        "deadlines, and practical suggestions.\n"
        "Use only tasks and deadlines that are explicitly stated in the meeting recap.\n"
        "Make the summary strong enough that someone who missed the meeting understands "
        "what happened, what was agreed, what is pending, and what should happen next.\n\n"
        f"Activity metadata:\n{metadata_block}\n\n"
        f"Meeting content:\n{compact}"
    )

    try:
        raw = call_ollama(PIPELINE_SYSTEM, user_msg, max_tokens=1800)
        try:
            result = extract_json(raw)
        except Exception:
            # Ask the model to fix its own malformed output, then re-parse.
            result = _repair_with_ollama(raw)
    except Exception:
        result = _safe_result(compact, metadata)

    return normalize_result(result, compact, metadata)


# ------------------------------------------------------------------
# Chat / Q&A
# ------------------------------------------------------------------
def chat_with_meetings(question: str, meetings: list) -> str:
    """Answer a question grounded in the stored meeting data."""
    from utils.helpers import join_list, normalize_status

    blocks = []
    for m in meetings[:8]:
        actions = m.get("actions", []) or []
        action_lines = [
            f"- {normalize_value(a.get('text'))} | owner: {normalize_value(a.get('owner'), 'Not stated')} | "
            f"status: {normalize_status(a)} | deadline: {normalize_value(a.get('deadline'), 'None')}"
            for a in actions
        ]
        blocks.append("\n".join([
            f"Date: {m.get('date', '')}",
            f"Title: {m.get('title', '')}",
            f"Summary: {normalize_value(m.get('summary') or m.get('recaps'), 'No summary.')}",
            f"Objective: {normalize_value(m.get('objective'), 'Not provided')}",
            f"Stakeholders: {join_list(m.get('stakeholders', []), 'None')}",
            "Action items:",
            "\n".join(action_lines) if action_lines else "- None",
        ]))

    context = "\n\n".join(blocks) if blocks else "No meeting data available."

    from config.constants import CHAT_SYSTEM
    user_msg = f"Meeting data:\n{context}\n\nQuestion: {question}"
    return call_ollama(CHAT_SYSTEM, user_msg, max_tokens=400)
