"""Daily task reminder script — runs via GitHub Actions.

Checks Supabase for action items due within the next 7 days,
looks up the task owner's email from the staff_emails table,
and sends a Gmail reminder. Each meeting is only notified once.

Required environment variables (set as GitHub Secrets):
    SUPABASE_URL          — e.g. https://xxxx.supabase.co
    SUPABASE_KEY          — service role key
    GMAIL_SENDER          — sender Gmail address
    GMAIL_APP_PASSWORD    — Gmail app password (16-char, no spaces)

Supabase tables required:
    meetings       — existing table
    staff_emails   — CREATE TABLE staff_emails (name text PRIMARY KEY, email text NOT NULL);
    notifications  — CREATE TABLE notifications (meeting_id text PRIMARY KEY, sent_at timestamptz DEFAULT now());
"""
from __future__ import annotations

import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ── Config from environment ──────────────────────────────────────────────────
SUPABASE_URL      = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY      = os.environ.get("SUPABASE_KEY", "")
GMAIL_SENDER      = os.environ.get("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")

MEETINGS_TABLE     = "meetings"
STAFF_EMAILS_TABLE = "staff_emails"
NOTIFICATIONS_TABLE = "notifications"

DEADLINE_WINDOW_DAYS = 7   # notify when deadline is within this many days


# ── Supabase helpers ─────────────────────────────────────────────────────────
def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get(table: str, params: dict | None = None) -> list[dict]:
    import urllib.request, urllib.parse
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*"
    if params:
        url += "&" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()) or []


def _insert(table: str, row: dict) -> None:
    import urllib.request
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    data = json.dumps(row).encode()
    req = urllib.request.Request(url, data=data, headers={
        **_headers(),
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }, method="POST")
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as exc:
        print(f"  [warn] Could not insert into {table}: {exc}")


# ── Date helpers ─────────────────────────────────────────────────────────────
def _days_left(deadline_str: str) -> int | None:
    """Return days until deadline (negative = overdue). None if no valid date."""
    if not deadline_str or deadline_str in ("None", "Not stated", ""):
        return None
    try:
        dl = datetime.strptime(deadline_str.strip(), "%Y-%m-%d").date()
        return (dl - date.today()).days
    except ValueError:
        return None


# ── Email sender ─────────────────────────────────────────────────────────────
def _send_email(to_email: str, subject: str, body: str) -> bool:
    """Send a plain-text email via Gmail SMTP. Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = GMAIL_SENDER
        msg["To"]      = to_email
        msg["Subject"] = subject

        # Plain text part
        msg.attach(MIMEText(body, "plain"))

        # HTML part (nicer formatting)
        html_body = body.replace("\n", "<br>").replace("  ", "&nbsp;&nbsp;")
        html = f"""
        <html><body style="font-family:sans-serif;font-size:14px;color:#0f172a;line-height:1.7">
        {html_body}
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, to_email, msg.as_string())
        return True
    except Exception as exc:
        print(f"  [error] Failed to send email to {to_email}: {exc}")
        return False


# ── Build reminder email body ────────────────────────────────────────────────
def _build_body(owner: str, tasks: list[dict]) -> str:
    today_str = date.today().strftime("%A, %d %B %Y")
    lines = [
        f"Dear {owner},",
        "",
        "This is a reminder from MeetIQ. You have the following action items",
        f"due within the next {DEADLINE_WINDOW_DAYS} days:",
        "",
    ]
    for i, t in enumerate(tasks, 1):
        dl     = t.get("deadline", "Not stated")
        text   = t.get("text", "")
        mtitle = t.get("meeting_title", "")
        days   = t.get("days_left")

        if days == 0:
            urgency = "due TODAY"
        elif days == 1:
            urgency = "due TOMORROW"
        else:
            urgency = f"due in {days} day(s)"

        lines.append(f"  {i}. {text}")
        lines.append(f"     Meeting : {mtitle}")
        lines.append(f"     Deadline: {dl}  ({urgency})")
        lines.append("")

    lines += [
        "Please ensure these tasks are completed on time.",
        "",
        f"Sent by MeetIQ  ·  {today_str}",
    ]
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    # Validate config
    missing = [k for k, v in {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
        "GMAIL_SENDER": GMAIL_SENDER,
        "GMAIL_APP_PASSWORD": GMAIL_APP_PASSWORD,
    }.items() if not v]
    if missing:
        print(f"[error] Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] MeetIQ daily reminder starting...")

    # ── 1. Load staff email lookup ───────────────────────────────────────────
    print("Loading staff emails...")
    staff_rows = _get(STAFF_EMAILS_TABLE)
    # Normalise keys to lowercase for case-insensitive matching
    email_map: dict[str, str] = {
        row["name"].strip().lower(): row["email"].strip()
        for row in staff_rows
        if row.get("name") and row.get("email")
    }
    print(f"  {len(email_map)} staff email(s) loaded.")

    if not email_map:
        print("[warn] staff_emails table is empty — no emails to send.")
        return

    # ── 2. Load already-notified meetings ────────────────────────────────────
    print("Loading notification log...")
    notified_ids: set[str] = {
        row["meeting_id"]
        for row in _get(NOTIFICATIONS_TABLE)
        if row.get("meeting_id")
    }
    print(f"  {len(notified_ids)} meeting(s) already notified.")

    # ── 3. Load all meetings ─────────────────────────────────────────────────
    print("Loading meetings from Supabase...")
    meetings_raw = _get(MEETINGS_TABLE)
    print(f"  {len(meetings_raw)} meeting(s) found.")

    # ── 4. Find upcoming tasks grouped by meeting and owner ──────────────────
    # Structure: { meeting_id: { owner_name: [task_dict, ...] } }
    upcoming: dict[str, dict[str, list]] = {}
    meeting_titles: dict[str, str] = {}

    for row in meetings_raw:
        m_id    = row.get("id", "")
        m_title = row.get("title", "Untitled")
        meeting_titles[m_id] = m_title

        # Skip if already notified
        if m_id in notified_ids:
            continue

        # Parse actions (stored as JSON string or list)
        raw_actions = row.get("actions", "[]")
        if isinstance(raw_actions, str):
            try:
                actions = json.loads(raw_actions)
            except json.JSONDecodeError:
                actions = []
        else:
            actions = raw_actions or []

        for action in actions:
            status = (action.get("status") or "Pending").strip()
            if status in ("Done", "Cancelled"):
                continue

            deadline_str = (action.get("deadline") or "").strip()
            days = _days_left(deadline_str)
            if days is None or days < 0 or days > DEADLINE_WINDOW_DAYS:
                continue

            owner = (action.get("owner") or "").strip()
            if not owner or owner.lower() in ("not stated", "none", ""):
                continue

            # Check if owner has an email
            owner_key = owner.lower()
            if owner_key not in email_map:
                print(f"  [skip] No email found for owner '{owner}' — add to staff_emails table.")
                continue

            if m_id not in upcoming:
                upcoming[m_id] = {}
            if owner not in upcoming[m_id]:
                upcoming[m_id][owner] = []

            upcoming[m_id][owner].append({
                "text":          action.get("text", ""),
                "deadline":      deadline_str,
                "days_left":     days,
                "meeting_title": m_title,
            })

    if not upcoming:
        print("No upcoming tasks to notify about. All done.")
        return

    print(f"\nFound {len(upcoming)} meeting(s) with upcoming tasks to notify.")

    # ── 5. Send emails ───────────────────────────────────────────────────────
    notified_meetings: list[str] = []

    for m_id, owner_tasks in upcoming.items():
        m_title = meeting_titles.get(m_id, "Untitled")
        print(f"\nMeeting: {m_title} ({m_id})")
        all_sent = True

        for owner, tasks in owner_tasks.items():
            email = email_map[owner.lower()]
            subject = f"[MeetIQ] Reminder: {len(tasks)} task(s) due soon — {m_title}"
            body = _build_body(owner, tasks)

            print(f"  Sending to {owner} <{email}> — {len(tasks)} task(s)...")
            sent = _send_email(email, subject, body)
            if not sent:
                all_sent = False

        # Only mark as notified if all emails for this meeting were sent
        if all_sent:
            notified_meetings.append(m_id)

    # ── 6. Mark meetings as notified in Supabase ────────────────────────────
    print(f"\nMarking {len(notified_meetings)} meeting(s) as notified...")
    for m_id in notified_meetings:
        _insert(NOTIFICATIONS_TABLE, {
            "meeting_id": m_id,
            "sent_at": datetime.utcnow().isoformat() + "Z",
        })
        print(f"  Marked: {m_id}")

    print(f"\n[done] Reminder run complete. {len(notified_meetings)} meeting(s) notified.")


if __name__ == "__main__":
    main()
