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


#JSON repair
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
        re.sub(r",\s*([}\]])", r"\1", candidate),                           
        re.sub(r'([{\s,])([A-Za-z_][\w\- ]*)(\s*:)', r'\1"\2"\3', candidate),  
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


#safe result
def _safe_result(transcript: str, metadata: dict | None = None) -> dict:
    """Minimal valid result used when the LLM call fails entirely."""
    metadata = metadata or {}
    words = (transcript or "").split()
    return {
        "title": normalize_value(metadata.get("Title") or metadata.get("Activity Title"), "Untitled"),
        "meeting_type": normalize_value(metadata.get("Activity Type"), "Not Provided"),
        "category": normalize_value(metadata.get("Category"), "Not Provided"),
        "nlp_pipeline": {
            # token/sentence counts computed in Python — not asked from LLM
            "token_count": len(words),
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


#normalization
def normalize_result(result: dict, transcript: str, metadata: dict | None = None) -> dict:
    """Ensure the result has every required key and consistent types."""
    safe = _safe_result(transcript, metadata)
    if not isinstance(result, dict):
        return safe

    merged = {**safe, **result}

    # meeting_type / category / outcome come from form metadata, not LLM
    metadata = metadata or {}
    merged["meeting_type"] = normalize_value(metadata.get("Activity Type"), safe["meeting_type"])
    merged["category"]     = normalize_value(metadata.get("Category"),      safe["category"])
    merged["outcome"]      = normalize_value(result.get("outcome"),          "Not provided")

    # merge key by key so missing subkeys get their defaults.
    llm_nlp = result.get("nlp_pipeline") or {}
    merged["nlp_pipeline"] = {**safe["nlp_pipeline"], **llm_nlp}
    merged["nlp_pipeline"]["named_entities"] = {
        **safe["nlp_pipeline"]["named_entities"],
        **(llm_nlp.get("named_entities") or {}),
    }
    # Always compute token/sentence counts in Python — LLM no longer generates them
    words = (transcript or "").split()
    merged["nlp_pipeline"]["token_count"] = len(words)
    merged["nlp_pipeline"]["sentence_count"] = len(transcript_sentences(transcript))

    merged["classification"] = {**safe["classification"], **(result.get("classification") or {})}

    # Lists must be lists — key_decisions / discussion_points default to [] since LLM no longer generates them
    for key in ("key_decisions", "discussion_points", "action_items"):
        if not isinstance(merged.get(key), list):
            merged[key] = safe[key]

    # Strings must be non-empty
    for key in ("title", "meeting_type", "category", "objective", "summary", "outcome"):
        merged[key] = normalize_value(merged.get(key), safe[key])

    # Booleans
    merged["follow_up"] = parse_yes_no(merged.get("follow_up"))
    merged["follow_up_reason"] = normalize_value(merged.get("follow_up_reason"), "")

    # Placeholder texts the LLM writes when it finds no tasks — filter these out.
    _EMPTY_TEXTS = {"none", "n/a", "not stated", "no action items", "untitled action", ""}

    # Clean each action item so later UI code can trust the shape.
    cleaned_actions = []
    for action in merged["action_items"]:
        if not isinstance(action, dict):
            continue
        raw_text = (action.get("text") or "").strip()
        # Skip placeholder / empty action items the LLM fabricates when nothing exists
        if raw_text.lower() in _EMPTY_TEXTS:
            continue
        owner = normalize_value(action.get("owner"), "Not stated")
        department = normalize_value(action.get("department") or action.get("company"), "Not stated")
        cleaned_actions.append({
            "text": raw_text,
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

    # Follow-up is ONLY true when there are real extracted action items.
    # This prevents "Follow-up: Yes" appearing when the LLM found nothing to extract.
    merged["follow_up"] = bool(cleaned_actions)

    return merged


#input (meeting recap)
def run_pipeline(transcript: str, metadata: dict | None = None) -> dict:
    """Analyse a transcript and return the normalised meeting brief."""
    compact = compact_transcript_for_prompt((transcript or "").strip(), max_chars=3000)

    # Only pass the most useful metadata fields to keep the prompt short
    _KEEP = {"Title", "Category", "Meeting Date", "Departments", "Report By"}
    metadata_lines = [
        f"{label}: {normalize_value(value, '')}"
        for label, value in (metadata or {}).items()
        if label in _KEEP and normalize_value(value, "")
    ]
    metadata_block = "\n".join(metadata_lines) or "None provided"

    user_msg = (
        f"Metadata:\n{metadata_block}\n\n"
        f"Transcript:\n{compact}"
    )

    try:
        raw = call_ollama(PIPELINE_SYSTEM, user_msg, max_tokens=450, num_ctx=4096)
        try:
            result = extract_json(raw)
        except Exception:
            result = _repair_with_ollama(raw)
    except Exception:
        result = _safe_result(compact, metadata)

    return normalize_result(result, compact, metadata)


# ------------------------------------------------------------------
# Smart Follow-Up Email (AI-generated)
# ------------------------------------------------------------------
def generate_followup_email(meeting: dict) -> str:
    """AI drafts a professional follow-up email for a meeting."""
    from utils.helpers import join_list, normalize_status

    title      = normalize_value(meeting.get("title"), "Meeting")
    date_str   = normalize_value(meeting.get("date"), "")
    summary    = normalize_value(meeting.get("summary"), "")
    dept       = normalize_value(meeting.get("deptName") or meeting.get("department"), "")
    report_by  = normalize_value(meeting.get("user_id") or meeting.get("updated_by"), "The Meeting Organizer")
    objective    = normalize_value(meeting.get("objective"), "")
    stakeholders = join_list(meeting.get("stakeholders") or [], "")

    actions = meeting.get("actions") or []
    action_lines = []
    for a in actions:
        if normalize_status(a) not in ("Done", "Cancelled"):
            action_lines.append(
                f"- {normalize_value(a.get('text'))} | Owner: {normalize_value(a.get('owner'), 'Not stated')} | Deadline: {normalize_value(a.get('deadline'), 'Not stated')}"
            )

    SYSTEM = (
        "You are an executive assistant. Write a concise professional follow-up email after a meeting. "
        "Use the exact format: start with 'Dear colleagues,', then a brief intro line, then "
        "'MEETING RECAP', then Date, Meeting, Objective, Summary, Action Items sections, "
        "then 'Regards,' and the sender name. Keep it professional and concise."
    )
    user_msg = (
        f"Meeting: {title}\nDate: {date_str}\nDepartment: {dept}\n"
        f"Attendees/Stakeholders: {stakeholders}\n"
        f"Objective: {objective}\n"
        f"Summary: {summary}\n"
        f"Pending Action Items:\n" + ("\n".join(action_lines) or "None") + f"\n"
        f"Report by / Sender: {report_by}\n\n"
        "Write the follow-up email now."
    )
    return call_ollama(SYSTEM, user_msg, max_tokens=600)


# ------------------------------------------------------------------
# Give Idea — AI project manager guidance for one action item
# ------------------------------------------------------------------
def get_action_idea(action: dict) -> str:
    """AI acts as project manager and gives step-by-step guidance for an action item."""
    SYSTEM = (
        "You are a senior project manager. Given an unfinished action item, "
        "provide 3-5 specific, practical next steps to help the team complete it. "
        "Consider potential blockers, who to involve, and quick wins. "
        "Be direct and actionable. Use a numbered list."
    )
    text     = normalize_value(action.get("text"), "Unknown task")
    owner    = normalize_value(action.get("owner"), "Not stated")
    dept     = normalize_value(action.get("department"), "Not stated")
    deadline = normalize_value(action.get("deadline"), "None")
    status   = normalize_value(action.get("status"), "Pending")

    user_msg = (
        f"Action item: {text}\n"
        f"Owner: {owner} | Department: {dept}\n"
        f"Deadline: {deadline} | Status: {status}\n\n"
        "As project manager, give specific steps to get this done:"
    )
    return call_ollama(SYSTEM, user_msg, max_tokens=350)


# ------------------------------------------------------------------
# Quick intent classifier — handles greetings/chit-chat without Ollama
# ------------------------------------------------------------------
_GREETINGS = {
    "hi", "hello", "hey", "hai", "hye", "helo", "yo", "sup",
    "assalamualaikum", "salam", "waalaikumsalam",
    "good morning", "good afternoon", "good evening", "selamat pagi",
    "selamat tengah hari", "selamat petang", "selamat malam",
}
_THANKS = {
    "thanks", "thank you", "terima kasih", "tq", "ty", "cheers",
    "ok", "okay", "alright", "noted", "got it", "i see", "sure",
    "great", "awesome", "nice", "good", "bagus", "baik",
}
_BYE = {"bye", "goodbye", "see you", "selamat tinggal", "chow", "ciao", "tata"}


def _quick_reply(question: str) -> str | None:
    """Return an instant reply for greetings/chit-chat without calling Ollama.
    Returns None if the question should go to the LLM."""
    q = question.strip().lower().rstrip("!.,? ")

    if q in _GREETINGS or any(q.startswith(g + " ") for g in _GREETINGS):
        return (
            "Hi there! I'm MeetIQ's AI assistant.\n\n"
            "I can help you with:\n"
            "- Pending or overdue action items\n"
            "- Meeting summaries and objectives\n"
            "- Deadlines and task owners\n"
            "- Stakeholder contact details\n\n"
            "What would you like to know about your meetings?"
        )

    if q in _THANKS:
        return "You're welcome! Let me know if you need anything else about your meetings."

    if q in _BYE:
        return "Goodbye! Come back anytime to check your meetings."

    # Very short inputs that aren't questions — gently redirect
    if len(q.split()) <= 2 and "?" not in question and not any(
        kw in q for kw in ("how", "what", "who", "when", "where", "why",
                           "list", "show", "tell", "find", "count", "overdue",
                           "pending", "task", "meeting", "action", "deadline")
    ):
        return (
            "I'm your meeting assistant! Ask me about your meetings, "
            "action items, deadlines, or stakeholders."
        )

    return None  # let the LLM handle it


def _build_meeting_context(question: str, meetings: list) -> tuple[str, int, int]:
    """Build a compact meeting context string, capped to keep LLM fast.
    Returns (context_str, num_overdue_meetings, total_overdue_actions)."""
    from utils.helpers import join_list, normalize_status

    # Detect if question is about contacts to decide whether to load stakeholder db
    _contact_kws = ("contact", "phone", "email", "stakeholder", "organisation",
                    "company", "who is", "siapa", "nombor", "address")
    needs_stk = any(kw in question.lower() for kw in _contact_kws)

    # Cap summary per meeting to keep total context small and fast
    blocks = []
    for m in meetings:
        actions = m.get("actions", []) or []
        overdue_actions = [a for a in actions if normalize_status(a) == "Overdue"]
        action_lines = [
            f"  [{normalize_status(a)}] {normalize_value(a.get('text'))} "
            f"| owner: {normalize_value(a.get('owner'), 'Not stated')} "
            f"| deadline: {normalize_value(a.get('deadline'), 'Not stated')}"
            for a in actions
        ]
        overdue_flag = (
            f"HAS OVERDUE ACTIONS: YES ({len(overdue_actions)} overdue)"
            if overdue_actions else "HAS OVERDUE ACTIONS: NO"
        )
        summary_short = normalize_value(m.get("summary") or m.get("recaps"), "No summary.")[:150]
        ext_stk = m.get("externalStakeholders") or []
        ext_lines = [
            f"  {s.get('name','')} | {s.get('position','')} | {s.get('organisation','')} | {s.get('email','')}"
            for s in ext_stk if s.get("name")
        ] if needs_stk else []

        blocks.append("\n".join(filter(None, [
            "--- Meeting ---",
            f"Date: {m.get('date', '')}",
            f"Title: {m.get('title', '')}",
            overdue_flag,
            f"TC Members: {join_list(m.get('stakeholders', []), 'None')}",
            (f"External: {chr(10).join(ext_lines)}" if ext_lines else ""),
            f"Summary: {summary_short}",
            f"Total action items: {len(actions)}",
            "Action items:" if action_lines else "Action items: None",
            "\n".join(action_lines) if action_lines else "",
        ])))

    meeting_context = "\n\n".join(blocks) if blocks else "No meeting data available."

    # Cap total context at 3000 chars to keep inference fast
    if len(meeting_context) > 3000:
        meeting_context = meeting_context[:3000] + "\n[...context capped for speed]"

    stk_context = ""
    if needs_stk:
        try:
            from core.stakeholder_db import load_external_stakeholders
            all_stk = load_external_stakeholders()
            stk_lines = [
                f"  {s.get('name','')} | {s.get('position','')} | {s.get('organisation','')} | {s.get('phone','')} | {s.get('email','')}"
                for s in all_stk if s.get("name")
            ]
            stk_context = ("--- Stakeholder Directory ---\n" + "\n".join(stk_lines)) if stk_lines else ""
        except Exception:
            pass

    full_context = meeting_context + ("\n\n" + stk_context if stk_context else "")

    overdue_meetings = [
        m for m in meetings
        if any(normalize_status(a) == "Overdue" for a in (m.get("actions") or []))
    ]
    total_overdue = sum(
        sum(1 for a in (m.get("actions") or []) if normalize_status(a) == "Overdue")
        for m in meetings
    )

    return full_context, len(overdue_meetings), total_overdue, overdue_meetings


# ------------------------------------------------------------------
# Chat / Q&A
# ------------------------------------------------------------------
def chat_with_meetings(question: str, meetings: list) -> str:
    """Answer a question grounded in meeting data. Handles greetings instantly."""
    # Greetings / chit-chat — no Ollama call needed
    quick = _quick_reply(question)
    if quick:
        return quick

    full_context, n_overdue_mtgs, total_overdue, overdue_meetings = _build_meeting_context(question, meetings)

    from config.constants import CHAT_SYSTEM
    user_msg = (
        f"FACTS (pre-computed — use these exact numbers):\n"
        f"- Total meetings: {len(meetings)}\n"
        f"- Meetings with at least one overdue action: {n_overdue_mtgs}"
        + (f" (titles: {', '.join(m.get('title','Untitled') for m in overdue_meetings)})" if overdue_meetings else "") + "\n"
        f"- Total overdue action items across all meetings: {total_overdue}\n\n"
        f"Data:\n{full_context}\n\n"
        f"Question: {question}"
    )
    return call_ollama(CHAT_SYSTEM, user_msg, max_tokens=300, num_ctx=2048)


def stream_chat_with_meetings(question: str, meetings: list):
    """Streaming version — handles greetings instantly, uses LLM only for real questions."""
    from core.services import stream_ollama

    # Greetings / chit-chat — instant reply, zero Ollama calls
    quick = _quick_reply(question)
    if quick:
        yield quick
        return

    full_context, n_overdue_mtgs, total_overdue, overdue_meetings = _build_meeting_context(question, meetings)

    from config.constants import CHAT_SYSTEM
    user_msg = (
        f"FACTS (pre-computed — use these exact numbers):\n"
        f"- Total meetings: {len(meetings)}\n"
        f"- Meetings with at least one overdue action: {n_overdue_mtgs}"
        + (f" (titles: {', '.join(m.get('title','Untitled') for m in overdue_meetings)})" if overdue_meetings else "") + "\n"
        f"- Total overdue action items across all meetings: {total_overdue}\n\n"
        f"Data:\n{full_context}\n\n"
        f"Question: {question}"
    )

    yield from stream_ollama(CHAT_SYSTEM, user_msg, max_tokens=300, num_ctx=2048)
