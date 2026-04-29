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
    "MyHeart Facilitation",
    "MPT",
    "Graduates Emerging Talent",
    "School Talent Hub",
    "GCEO Liaison Office",
    "Communications",
    "Group Strategy Office",
    "Group Business Intelligence",
    "GEF",
    "MYXpats Operations",
    "Group Research, Development and Policy",
    "MyMahir",
    "MyMahir - Workforce Solution",
    "Graduate & Emerging Talent",
]

# Lowercase set used to filter action items to TalentCorp-only departments
TALENTCORP_DEPT_KEYWORDS = {d.lower() for d in DEFAULT_DEPARTMENTS} | {
    "talentcorp", "talent corp", "tc", "talentcorp malaysia",
}

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

Analyse the transcript and produce a structured brief.

Rules:
- summary: 3-5 sentences in your own words covering what happened, what was agreed, what is next.
- objective: one concise sentence.
- action_items: Include tasks that are EXPLICITLY stated using words like "needs to", "will", "must", "should", "has to", "is required to", "agreed to", or where a person is clearly assigned a responsibility. Do NOT invent tasks. Do NOT add tasks just because a topic was discussed without a clear assignment. If no clear task is assigned to anyone, action_items MUST be an empty list [].
- owner: ONLY the person explicitly assigned the task by name. If unclear or not stated, use "Not stated". NEVER use a department name, organisation name, or team name as the owner.
- department: a TalentCorp department only (MyMahir, MPT, GEF, School Talent Hub,
  Group Strategy Office, Group Business Intelligence, MYXpats Operations,
  Communications, GCEO Liaison Office, MyHeart Facilitation, Graduate & Emerging Talent).
  Use "Not stated" if none applies.
- deadline: use "None" unless an actual date or clear timeframe is stated in the transcript.
- If no tasks are explicitly stated, return action_items as [] and follow_up as false. Do not add placeholder tasks.

Return exactly this schema (no extra fields, no markdown):
{
  "title": "string",
  "objective": "string",
  "summary": "string",
  "follow_up": false,
  "nlp_pipeline": {"named_entities": {"persons": [], "organizations": [], "dates": [], "locations": []}},
  "action_items": []
}
"""

# ---- JSON repair prompt (used when Ollama returns malformed JSON) -----
JSON_REPAIR_SYSTEM = (
    "You repair malformed meeting-analysis JSON. "
    "Return only valid JSON with the same meaning. No markdown, no explanation."
)

# ---- Chat / Q&A ---------------------------------------------------
CHAT_SYSTEM = """You are MeetIQ's friendly AI assistant for a meeting insight system.

You help users understand their meeting data — action items, deadlines, summaries, and stakeholders.

Rules:
- Only answer using the meeting data provided. Do not invent facts.
- Be conversational and helpful. Answer in plain, clear language.
- For counting questions: count ALL action items carefully across every meeting.
- Treat Pending, In Progress, and Overdue as "not completed / not done".
- Never claim there are no items if the data shows any.
- When asked about a keyword (e.g. "UPNM"), search titles, summaries, stakeholders, AND each action item's text and owner.
- Always state exact counts (e.g. "There are 4 action items related to UPNM").
- For meeting details: mention title, owner, deadline, and status when relevant.
- Keep answers concise and business-friendly.

Interpreting "overdue meeting" or "overdue item":
- An "overdue meeting" means a meeting with at least one [Overdue] action item.
- If asked for an overdue meeting summary, only return summaries of meetings that have overdue actions.
- Never mix unrelated meetings into overdue-related answers.
"""
