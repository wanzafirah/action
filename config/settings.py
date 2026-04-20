"""Credential readers.

Reads from Streamlit secrets first, then environment variables.
Kept separate from constants.py so that secret-loading stays Streamlit-aware.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

import streamlit as st


# ------------------------------------------------------------------
# Generic secret reader
# ------------------------------------------------------------------
def _secret(key: str, default: str = "") -> str:
    """Return a secret from st.secrets, falling back to environment variables."""
    try:
        value = st.secrets.get(key, "")
    except Exception:
        value = ""
    return str(value or os.getenv(key, default)).strip()


# ------------------------------------------------------------------
# Ollama (remote via ngrok when deployed on Streamlit Cloud)
# ------------------------------------------------------------------
def _normalize_ollama_url(raw: str) -> str:
    """Make sure the Ollama URL ends with /api/generate."""
    url = (raw or "").strip()
    if not url:
        return "http://127.0.0.1:11434/api/generate"
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    path = (parsed.path or "").rstrip("/")
    if path in ("", "/"):
        parsed = parsed._replace(path="/api/generate")
        return urlunparse(parsed)
    return url.rstrip("/")


def get_ollama_url() -> str:
    return _normalize_ollama_url(_secret("OLLAMA_URL", "http://127.0.0.1:11434/api/generate"))


# ------------------------------------------------------------------
# Supabase
# ------------------------------------------------------------------
def get_supabase_config() -> dict:
    """Return Supabase connection info, or empty dict when not configured.

    Accepts either a service role key (preferred for server-side writes) or
    an anon key. Configure in .streamlit/secrets.toml as:

        SUPABASE_URL = "https://xxxxx.supabase.co"
        SUPABASE_KEY = "eyJhbGciOi..."
    """
    url = _secret("SUPABASE_URL")
    key = (
        _secret("SUPABASE_SERVICE_ROLE_KEY")
        or _secret("SUPABASE_KEY")
        or _secret("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        return {}
    return {"url": url.rstrip("/"), "key": key}


def is_supabase_configured() -> bool:
    return bool(get_supabase_config())
