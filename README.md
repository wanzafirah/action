# MeetIQ — AI Meeting Insight Generator & Action Tracker

A Streamlit app that turns a meeting recording (or a pasted transcript) into a
structured brief — summary, objective, key decisions, discussion points, and
trackable action items with owners and deadlines.

Built for a final-year project. Uses **faster-whisper** for transcription and
**Ollama 3.2** (running locally via ngrok) for every generation task, so the
app stays free to run and keeps meeting audio on-device.

---

## Features

- Transcribe audio (mp3 / m4a / wav / mp4 / webm) with automatic language detection
- Optional translation to English
- Attach supporting PDFs, Word docs, Excel, or CSV to enrich the transcript
- One-shot LLM pipeline returns summary, objective, action items, decisions
- Supabase storage for meetings, departments, and chat history
- Tracker page with editable statuses and deadlines
- Dashboard with KPIs, calendar, and AI chat grounded in your stored meetings

---

## Project structure

```
meetiq_refactored/
├── app.py                 # entry point + router
├── config/
│   ├── constants.py       # prompts + option lists
│   └── settings.py        # secrets readers (Ollama URL, Supabase)
├── core/
│   ├── pipeline.py        # run_pipeline, extract_json, normalize_result
│   ├── database.py        # Supabase load/save
│   └── services.py        # Ollama call, Whisper, document extraction
├── pages/
│   ├── dashboard.py       # KPIs + calendar + chat
│   ├── capture.py         # upload/record + run pipeline + save
│   ├── tracker.py         # edit saved meetings and actions
│   └── history.py         # past chat threads
├── ui/
│   ├── sidebar.py         # navigation
│   ├── calendar.py        # calendar widget
│   ├── components.py      # kpi_card, action_card, chat_bubble, summary_panel
│   └── styles.py          # all CSS in one place
└── utils/
    ├── helpers.py         # pure helpers
    └── formatters.py      # dataframe builders, email body, calendar HTML
```

---

## Setup (local)

```bash
# 1. Python 3.11+ recommended
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Install Ollama and pull the model (https://ollama.com)
ollama pull llama3.2
ollama serve                   # keep this running in a separate terminal

# 3. Copy the secrets template and fill in Supabase + OLLAMA_URL
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
#   -> edit .streamlit/secrets.toml

# 4. Run
streamlit run app.py
```

---

## Deploying to Streamlit Cloud with ngrok

Streamlit Cloud cannot run Ollama itself, so the recommended pattern is:

1. Run Ollama on your own machine (`ollama serve`).
2. Expose it via ngrok:
   ```bash
   ngrok http 11434
   ```
3. Copy the `https://xxxx.ngrok-free.app` URL.
4. In the Streamlit Cloud app → *Settings → Secrets*, paste:
   ```toml
   OLLAMA_URL = "https://xxxx.ngrok-free.app/api/generate"
   SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
   SUPABASE_KEY = "eyJhbGciOi..."
   ```
5. The Ollama client in `core/services.py` automatically adds the
   `ngrok-skip-browser-warning` header when the URL contains `ngrok`.

> Keep your ngrok terminal open whenever you demo the deployed app — the
> tunnel dies if you close it.

---

## Supabase schema

Create three tables with RLS disabled (or a policy that allows your key):

```sql
create table meetings (
    id text primary key,
    user_id text,
    title text,
    date text,
    category text,
    summary text,
    objective text,
    outcome text,
    follow_up boolean default false,
    follow_up_reason text,
    transcript text,
    department text,
    activity_id text,
    stakeholders jsonb default '[]'::jsonb,
    companies jsonb default '[]'::jsonb,
    key_decisions jsonb default '[]'::jsonb,
    discussion_points jsonb default '[]'::jsonb,
    actions jsonb default '[]'::jsonb,
    created_at timestamptz default now()
);

create table departments (
    id text primary key,
    name text,
    budget numeric default 0
);

create table history (
    id text primary key,
    user_id text,
    thread_key text,
    thread_date text,
    thread_title text,
    timestamp text,
    question text,
    answer text,
    meeting_id text,
    meeting_title text,
    context text
);
```

Store a **service role** key for server-side writes, or an **anon** key plus
permissive RLS policies.

---

## Why Ollama 3.2 (and not Claude)

For a final year project:

- **Free to run** — zero recurring API cost during development and demo
- **Offline** — the demo works even if the venue's WiFi is unreliable
- **Privacy defence** — meeting audio never leaves your machine, which is a
  real talking point in viva defence

If you later want to switch to Claude or another hosted model, only
`core/services.py` needs to change — `core/pipeline.py` calls one function
(`call_ollama`) and doesn't care what model answers.
