"""Single source of truth for all CSS.

Injected once from app.py via inject_css(). Everything else uses class names
defined here (.kpi-card, .action-card, .chat-bubble, .calendar-day, etc.).
"""
import streamlit as st


_CSS = """
<style>
:root {
    --bg-outer: #0E1F2F;
    --surface: #ffffff;
    --surface-soft: #f8f6fb;
    --border: #d8dceb;
    --text: #0f172a;
    --text-muted: #27425D;
    --text-soft: #6e7f96;
    --brand: #0E1B48;
    --brand-2: #27425D;
    --accent: #87A7D0;
    --soft-pink: #C18DB4;
    --soft-blush: #E2CAD8;
}
.stApp {
    background:
        radial-gradient(circle at top right, rgba(135, 167, 208, 0.14), transparent 30%),
        radial-gradient(circle at bottom left, rgba(193, 141, 180, 0.18), transparent 36%),
        var(--bg-outer);
    color: var(--text);
    font-family: "Aptos", "Segoe UI", Arial, sans-serif;
    font-size: 16px;
    line-height: 1.6;
}
.block-container {
    padding: 1.25rem 1.5rem 2rem;
    margin: 1rem auto;
    max-width: 1380px;
    background: linear-gradient(180deg, var(--surface) 0%, #fcfbfe 100%);
    border-radius: 28px;
    box-shadow: 0 22px 60px rgba(15, 23, 42, 0.18);
}
.hero-shell {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 42%, #4f46e5 100%);
    color: white;
    border-radius: 24px;
    padding: 1.45rem 1.8rem 1.35rem;
    margin-bottom: 1.15rem;
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.18);
    position: relative;
    overflow: hidden;
}
.hero-shell h1 {
    margin: 0;
    font-size: 2.15rem;
    color: #ffffff !important;
    font-weight: 800;
    font-family: "Trebuchet MS", "Segoe UI", Verdana, sans-serif;
}
.hero-shell p {
    margin: 0.35rem 0 0;
    color: rgba(255,255,255,0.92);
    font-weight: 700;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #27425D 0%, #0E1B48 52%, #0E1F2F 100%);
    border-right: 1px solid rgba(255,255,255,0.10);
}
.sidebar-title {
    margin: 0 0 1rem;
    color: #ffffff !important;
    font-size: 1.45rem;
    font-weight: 800;
}
.sidebar-subtitle {
    margin: -0.7rem 0 1rem;
    color: rgba(255,255,255,0.78);
    font-size: 0.88rem;
}
section[data-testid="stSidebar"] .stButton > button {
    border-radius: 18px !important;
    min-height: 3rem;
    border: 0 !important;
    font-weight: 700 !important;
    background: rgba(135,167,208,0.18) !important;
    color: #ffffff !important;
}

/* Cards shared across pages */
.hero-panel, .kpi-card, .action-card, .info-card, .dashboard-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: 0 14px 28px rgba(15, 23, 42, 0.06);
}
.hero-panel { padding: 1.35rem 1.4rem; }
.hero-badge {
    display: inline-block;
    background: var(--soft-blush);
    color: var(--brand);
    padding: 0.35rem 0.7rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 700;
    margin-bottom: 0.8rem;
}
.hero-panel h2 {
    margin: 0 0 0.6rem;
    color: var(--text);
    font-size: 1.55rem;
}
.hero-panel p { margin: 0; color: var(--text-soft); }
.hero-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.9rem;
    margin-top: 1.1rem;
    color: var(--text-muted);
}
.summary-section {
    margin-top: 0.85rem;
    padding: 1rem 1.05rem;
    border-radius: 18px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, #ffffff 0%, #fbfbfe 100%);
}
.summary-section-title {
    font-size: 0.92rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--brand-2);
    margin-bottom: 0.55rem;
}
.summary-section-body { color: var(--text); font-size: 0.98rem; }

/* KPI cards */
.kpi-card { padding: 1rem 1.05rem; min-height: 108px; }
.kpi-label {
    color: var(--text-soft);
    font-size: 0.86rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}
.kpi-value {
    margin-top: 0.45rem;
    font-size: 1.85rem;
    font-weight: 800;
    color: var(--text);
}
.kpi-subtitle { margin-top: 0.45rem; color: var(--text-soft); font-size: 0.92rem; }

/* Action cards */
.action-card { padding: 1rem 1rem 0.85rem; margin-bottom: 0.75rem; }
.action-top {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 0.8rem;
    margin-bottom: 0.45rem;
}
.action-title { color: var(--text); font-weight: 700; font-size: 1rem; }
.action-meta { color: var(--text-muted); font-size: 0.92rem; }
.action-subtle { color: var(--text-soft); font-size: 0.9rem; }

/* Inputs */
.stButton button {
    background: var(--brand);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    padding: 0.55rem 0.9rem;
}
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"] { border-radius: 12px !important; }

/* Chat bubbles */
.chat-thread {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    margin: 0.9rem 0 1rem;
}
.chat-bubble {
    max-width: min(82%, 820px);
    padding: 0.9rem 1rem;
    border-radius: 18px;
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    border: 1px solid var(--border);
    font-size: 0.98rem;
    word-wrap: break-word;
    white-space: pre-wrap;
}
.chat-bubble.user {
    margin-left: auto;
    background: linear-gradient(135deg, #C18DB4, #b57aa6);
    color: #ffffff;
    border-color: rgba(193, 141, 180, 0.28);
    border-bottom-right-radius: 6px;
}
.chat-bubble.assistant {
    margin-right: auto;
    background: #f7f4f8;
    color: var(--text);
    border-bottom-left-radius: 6px;
}

/* Dashboard layout */
.dashboard-shell {
    display: grid;
    grid-template-columns: minmax(0, 1.35fr) minmax(310px, 0.85fr);
    gap: 1rem;
    align-items: start;
}
.dashboard-stack { display: flex; flex-direction: column; gap: 1rem; }
.dashboard-card { padding: 1rem 1.05rem; }
.dashboard-title { font-size: 1.55rem; font-weight: 800; color: var(--text); margin: 0 0 0.2rem; }
.dashboard-copy { color: var(--text-soft); font-size: 0.96rem; margin: 0; }

/* Calendar widget */
.calendar-widget { margin-top: 0.6rem; }
.calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 0.42rem;
}
.calendar-head { margin-bottom: 0.45rem; }
.calendar-day-label {
    text-align: center;
    color: var(--text-soft);
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
}
.calendar-day {
    aspect-ratio: 1 / 1;
    border-radius: 16px;
    display: grid;
    place-items: center;
    background: #f5f6fa;
    color: var(--text);
    font-weight: 700;
    border: 1px solid #dbe2ed;
}
.calendar-day.empty { background: transparent; border-color: transparent; }
.calendar-day.today { background: var(--brand); color: #ffffff; }
.calendar-day.pending-deadline {
    background: #fef3c7;
    border-color: #f59e0b;
    color: #92400e;
    box-shadow: inset 0 0 0 2px #facc15;
}

/* Upcoming items */
.upcoming-item {
    padding: 0.85rem 0.95rem;
    border-radius: 16px;
    background: #f8f6fb;
    border: 1px solid #ddd5e5;
    margin-top: 0.7rem;
}
.upcoming-title {
    font-weight: 800;
    color: var(--brand);
    font-size: 1rem;
    margin-bottom: 0.15rem;
}
.upcoming-date {
    padding: 0.45rem 0.55rem;
    border-radius: 14px;
    background: linear-gradient(135deg, #E2CAD8, #87A7D0);
    color: var(--brand);
    text-align: center;
    font-weight: 800;
    font-size: 0.82rem;
    min-width: 74px;
}
.upcoming-top {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: start;
}

/* Expanders */
[data-testid="stExpander"] { border: none !important; background: transparent !important; }
[data-testid="stExpander"] summary {
    background: #ffffff !important;
    border: 1px solid var(--border) !important;
    border-radius: 16px !important;
    padding: 0.7rem 0.9rem !important;
    box-shadow: 0 10px 24px rgba(14, 27, 72, 0.06) !important;
}

/* Completion ring (dashboard) */
.completion-card {
    background: #ffffff;
    border: 1px solid #ddd5e5;
    border-radius: 16px;
    padding: 1rem 1.05rem;
    min-height: 108px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.completion-wrap { display: flex; justify-content: center; padding: 0.2rem 0 0.35rem; flex: 1; }
.completion-ring {
    --size: 88px;
    width: var(--size);
    height: var(--size);
    border-radius: 50%;
    background: conic-gradient(#87A7D0 calc(var(--pct) * 1%), #edf1f7 0);
    display: grid;
    place-items: center;
}
.completion-inner {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: #ffffff;
    display: grid;
    place-items: center;
    font-size: 1.2rem;
    font-weight: 800;
    color: var(--brand);
}

@media (max-width: 980px) {
    .dashboard-shell { grid-template-columns: 1fr; }
}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
