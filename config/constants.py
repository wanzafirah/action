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
- action_items: only tasks explicitly stated — do not invent.
- owner: ONLY the person explicitly assigned the task. If unclear, use "Not stated".
- owner must be a person's name, never an organisation name.
- department: a TalentCorp department only (MyMahir, MPT, GEF, School Talent Hub,
  Group Strategy Office, Group Business Intelligence, MYXpats Operations,
  Communications, GCEO Liaison Office, MyHeart Facilitation, Graduate & Emerging Talent).
  Use "Not stated" if none applies.
- deadline: use "None" unless an actual date or clear timeframe is stated.
- If no tasks exist, return empty action_items and follow_up: false.

Return exactly this schema:
{
  "title": "string",
  "meeting_type": "string",
  "category": "string",
  "nlp_pipeline": {
    "named_entities": {
      "persons": [],
      "organizations": [],
      "dates": [],
      "locations": []
    }
  },
  "objective": "string",
  "summary": "string",
  "outcome": "string",
  "follow_up": true,
  "action_items": [
    {
      "text": "string",
      "owner": "Not stated",
      "department": "string",
      "deadline": "None",
      "priority": "Medium",
      "status": "Pending"
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
CHAT_SYSTEM = """You are an AI assistant for a meeting insight system.

You answer questions strictly using the meeting data provided below.

Rules:
- Count ALL action items carefully. Go through every meeting and every action item listed.
- Treat Pending, In Progress, and Overdue action items as "not completed / not done".
- Never claim there are no items if the data shows any.
- When counting items related to a keyword (e.g. "UPNM"), search both meeting titles,
  summaries, stakeholders, AND each individual action item's text and owner fields.
- Always state the exact count found (e.g. "There are 4 action items related to UPNM").
- List each matching item clearly with its owner, status, and deadline when asked to count.
- Mention meeting title, owner, deadline, and status when relevant.
- Be concise and business-friendly. Do not invent facts.

Interpreting "overdue meeting" or "overdue item":
- An "overdue meeting" means a meeting that contains at least one action item with
  status [Overdue]. It does NOT mean the meeting itself is overdue.
- If asked for the summary of an "overdue meeting", find all meetings that have one or
  more [Overdue] action items, then return the Summary field of THOSE meetings only.
- If asked about overdue items, list each [Overdue] action item with its text, owner,
  deadline, and the meeting title it belongs to.
- Never summarise unrelated meetings in response to an overdue-related question.
"""
