"""App-wide constants and prompt templates.

Kept as a pure module (no Streamlit imports) so it can be imported from
anywhere, including unit tests.
"""

# ------------------------------------------------------------------
# Model configuration
# ------------------------------------------------------------------
OLLAMA_MODEL = "llama3.2:latest"
WHISPER_MODEL = "base"           # faster-whisper model size: tiny / base / small / medium

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
    # Strategic Support Units
    "Communications",
    "Group Business Intelligence",
    "Group CEO Liaison Office",
    "GCEO Liaison Office",
    "Group Client Relationship Management",
    "Group Communications & Public Relations",
    "Group Digital",
    "Group Finance",
    "Group Government Engagement & Facilitation",
    "Group Human Resources Admin & Procurement",
    "Group Research, Development and Policy",
    "Group Research & Policy",
    "Group Strategy Office",
    "Business Intelligence",
    "Digital & Technology Solutions",
    "IT Operations & Security",
    "Strategic Communications",
    "Brand Marketing",
    "Digital Marketing",
    "Events",
    "Production",
    # Business Development Units
    "GEF",
    "Graduate & Emerging Talent",
    "Graduates Emerging Talent",
    "Campus Engagement",
    "Centre of Excellence",
    "Internship Facilitation",
    "MPT",
    "MyHeart Facilitation",
    "MyHeart Network",
    "MyHeart Operations",
    "MyMahir",
    "MyMahir - Workforce Solution",
    "MyMahir Sector Development",
    "MyMahir Workforce Solutions",
    "MYXpats Operations",
    "MyXpats Operations",
    "Residence Pass-Talent",
    "School Talent",
    "School Talent Hub",
    "Veteran MyWira",
    "Wanita MyWira",
    "Women DEI & Work-Life Practices",
    "Work-Life Practices",
    # Regional Offices
    "Region - Northern",
    "Region - Southern",
    "Region - East Coast",
    "Region - East Malaysia",
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
- CRITICAL OWNER RULE: "owner" must ONLY be set to a person's name if that specific
  person was explicitly told to do the task, volunteered to do it, or was directly
  assigned it during the meeting. DO NOT use names from the attendees list, People
  Involved section, or anyone mentioned in the meeting unless they were specifically
  assigned THAT task. If there is any doubt, use "Not stated".
- "owner" must be a PERSON's name (e.g. "Ahmad", "Sarah"), NOT an organisation name.
  If only an organisation is mentioned, use "Not stated" for owner and put the
  organisation name in "department".
- "department" MUST be a TalentCorp internal department name (e.g. "MPT", "GEF", "MyMahir",
  "Group Digital", "Graduate & Emerging Talent", "MYXpats Operations", "Communications",
  "Group Strategy Office", "School Talent Hub", "GCEO Liaison Office"). Do NOT put an
  external company name (e.g. "1337 Ventures", "CIMB Bank") in the department field.
  If no TalentCorp department is mentioned, use "Not stated".
- If deadline is NOT explicitly stated in the transcript, use "None". Do NOT guess or infer
  deadlines from vague language like "soon" or "as soon as possible".
- Only use a deadline if an actual date, month, or clear timeframe is stated near that task.
- suggestion is a short practical next-step idea.
- If the transcript is only about purpose/objective with no tasks, return an
  empty action_items list and set follow_up to false.

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
