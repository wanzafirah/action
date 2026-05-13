"""Chat History page: review past chat sessions saved per user, grouped by date & session."""
from collections import defaultdict

import streamlit as st

from ui.components import chat_bubble
from utils.helpers import normalize_value


def render() -> None:
    st.markdown("## Chat History")
    st.caption("Review past questions you asked, grouped by date and session.")

    records = st.session_state.get("history_records", [])
    search = st.text_input("Search", placeholder="Keyword in question or answer…")

    if not records:
        st.info("No chat history found.")
        return

    filtered = list(records)
    if search.strip():
        needle = search.strip().lower()
        filtered = [
            r for r in filtered
            if needle in normalize_value(r.get("question"), "").lower()
            or needle in normalize_value(r.get("answer"), "").lower()
        ]

    if not filtered:
        st.info("No results match your search.")
        return

    # Group by thread_key (date | session_id)
    threads: dict[str, list] = defaultdict(list)
    for r in filtered:
        threads[normalize_value(r.get("thread_key"), "ungrouped")].append(r)

    for key, entries in sorted(threads.items(), key=lambda kv: kv[0], reverse=True):
        entries.sort(key=lambda e: normalize_value(e.get("timestamp"), ""))
        thread_date = normalize_value(entries[0].get("thread_date"), "unknown date")
        thread_title = normalize_value(entries[0].get("thread_title"), "Chat session")

        with st.expander(f"📅 {thread_date}  ·  {thread_title}", expanded=False):
            for entry in entries:
                chat_bubble("user", normalize_value(entry.get("question"), ""))
                chat_bubble("assistant", normalize_value(entry.get("answer"), ""))
                st.caption(
                    f"{normalize_value(entry.get('timestamp'), '')}"
                )
            st.markdown("")
