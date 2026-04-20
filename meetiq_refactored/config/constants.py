"""App-wide constants and prompt templates.

Kept as a pure module (no Streamlit imports) so it can be imported from
anywhere, including unit tests.
"""

# ------------------------------------------------------------------
# Model configuration
# ------------------------------------------------------------------
OLLAMA_MODEL = "llama3.2:latest"
WHISPER_MODEL = "tiny"           # faster-whisper model size: tiny / base / small / medium

# ------------------------------------------------------------------
# Supabase table names
# ------------------------------------------------------------------
MEETINGS_TABLE = "meetings"
DEPARTMENTS_TABLE = "departments"
HISTORY_TABLE = "history"

# ------------------------------------------------------------------
# Dropdown / option lists (shown in the Capture form)
# ------------------------------------------------------------------
STATUSES = ["Pending", "In Progress", "Done", "Overdue", "Cancelled"]
MTG_TYPES = ["Virtual", "Physical", "Not Provided"]
CATEGORIES = ["External Meeting", "Internal Meeting", "Workshop"]

ACTIVITY_CATEGORY_OPTIONS = [
    "Internal Meeting",
    "External Meeting",
    "Workshop / Focus Group / Roundtable",
    "Courtesy Call",
    "Forum / Conference / Webinar",
    "Open Day / Career Fair / related",
    "Podcast / Interview",
    "Speaking Engagement / Sharing Session",
]
ROLE_OPTIONS = ["Organiser", "Guest / Attendees", "Speaker", "Moderator", "Panel", "Auditor"]
ACTIVITY_TYPE_OPTIONS = ["None", "Virtual", "Physical", "Both"]
ORGANIZATION_TYPE_OPTIONS = ["Institution", "Company"]

DEFAULT_DEPARTMENTS = [
    "Group client management",
    "Group communications & public relations",
    "Group information & communication technology",
    "Group finance",
    "Group government engagement & facilitation",
    "Group human resources, admin & procurement",
    "Group research & policy",
    "Group CEO liaison office",
    "Graduate & emerging talent",
    "School Talent",
    "MyMahir",
]

# ------------------------------------------------------------------
# Status visual configuration
# ------------------------------------------------------------------
STATUS_CFG = {
    "Pending":     {"color": "#b45309", "bg": "#fde68a"},
    "In Progress": {"color": "#1d4ed8", "bg": "#bfdbfe"},
    "Done":        {"color": "#166534", "bg": "#bbf7d0"},
    "Overdue":     {"color": "#991b1b", "bg": "#fecaca"},
    "Cancelled":   {"color": "#374151", "bg": "#d1d5db"},
}

# ==================================================================
# PROMPT TEMPLATES
# ==================================================================

# ---- Meeting analysis pipeline ----------------------------------
PIPELINE_SYSTEM = """You are a meeting intelligence system. Return ONLY valid JSON, no markdown.

Your task is to analyse a meeting transcript and produce a structured recap that
someone who missed the meeting can read in 30 seconds.

Write:
- A 4-6 sentence summary in your own words (not a copy of the first line).
- A concise one-line objective.
- Key decisions that were explicitly agreed, confirmed, or approved.
- Discussion points covering the main topics raised.
- Action items for every explicit task, request, commitment, or deliverable.

Rules:
- Only capture action items that are explicitly stated. Do not invent tasks.
- For each action item include: text, owner, department, deadline, priority,
  follow_up_required, follow_up_reason, suggestion.
- If owner or deadline is missing, use "Not stated" and "None".
- suggestion is a short practical next-step idea.
- If the transcript is only about purpose/objective with no tasks, return an
  empty action_items list and set follow_up to false.
- If a timeline (date, month, "early October", "before the event") is stated
  near an action, copy it into deadline.

Return exactly this schema:
{
  "title": "string",
  "meeting_type": "string",
  "category": "string",
  "nlp_pipeline": {
    "token_count": 0,
    "sentence_count": 0,
    "named_entities": {
      "persons": [],
      "organizations": [],
      "dates": [],
      "locations": []
    }
  },
  "classification": {
    "action_items_count": 0,
    "decisions_count": 0,
    "discussion_points_count": 0
  },
  "objective": "string",
  "summary": "string",
  "outcome": "string",
  "follow_up": true,
  "follow_up_reason": "string",
  "key_decisions": [],
  "discussion_points": [],
  "action_items": [
    {
      "text": "string",
      "owner": "Not stated",
      "department": "string",
      "deadline": "None",
      "priority": "Medium",
      "follow_up_required": true,
      "follow_up_reason": "string",
      "suggestion": "string"
    }
  ]
}
"""

# ---- JSON repair prompt (used when Ollama returns malformed JSON) -----
JSON_REPAIR_SYSTEM = (
    "You repair malformed meeting-analysis JSON. "
    "Return only valid JSON with the same meaning. No markdown, no explanation."
)

# ---- Chat / Q&A ---------------------------------------------------
CHAT_SYSTEM = """You are MeetIQ's AI assistant.

You answer questions using the meeting data provided below.

Rules:
- Treat Pending, In Progress, and Overdue action items as "not completed".
- Never claim there are no pending items if the data shows any of those statuses.
- Mention meeting title, owner, deadline, and status when relevant.
- If the question is broader than the stored data, answer from the data first,
  then add a practical suggestion.
- Be concise and business-friendly. Do not invent facts.
"""
