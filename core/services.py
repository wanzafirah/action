"""External services: Ollama LLM, Whisper ASR, document text extraction.

Every external call lives here so the rest of the app never touches `requests`,
`whisper`, `pypdf`, or `python-docx` directly.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Generator

import pandas as pd
import requests
import streamlit as st

from config.constants import OLLAMA_MODEL, WHISPER_MODEL
from config.settings import get_ollama_url

# ---- Optional dependencies (fail lazily so missing packages don't crash import) ----
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None


# ==================================================================
# OLLAMA
# ==================================================================
def call_ollama(system: str, user_msg: str, max_tokens: int = 1800,
                temperature: float = 0.1, num_ctx: int = 3072) -> str:
    """Send a prompt to Ollama and return the raw text response.

    Automatically adds the ngrok-skip header when the URL points to an ngrok
    tunnel (needed for Streamlit Cloud deployments).
    """
    url = get_ollama_url()
    headers = {}
    if "ngrok" in url:
        headers["ngrok-skip-browser-warning"] = "true"

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": user_msg,
        "system": system,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "num_ctx": num_ctx,
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.1,  # reduce repetition → shorter/faster output
        },
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=300)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {url}. "
            "If deployed on Streamlit Cloud, make sure OLLAMA_URL points to a reachable ngrok tunnel."
        ) from exc

    body = response.text or ""
    if body.lstrip().lower().startswith("<!doctype html") or "<html" in body.lower()[:200]:
        raise RuntimeError(
            f"OLLAMA_URL is returning HTML instead of JSON. Update it to end with /api/generate. Current: {url}"
        )
    return response.json().get("response", "")


def stream_ollama(system: str, user_msg: str, max_tokens: int = 300,
                  num_ctx: int = 2048, temperature: float = 0.1) -> Generator[str, None, None]:
    """Stream tokens from Ollama one chunk at a time.

    Yields each text fragment as it arrives so the UI can display a
    typing effect without waiting for the full response.
    """
    url = get_ollama_url()
    headers = {}
    if "ngrok" in url:
        headers["ngrok-skip-browser-warning"] = "true"

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": user_msg,
        "system": system,
        "stream": True,
        "options": {
            "num_predict": max_tokens,
            "num_ctx": num_ctx,
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }

    try:
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if not chunk.get("done"):
                            yield chunk.get("response", "")
                    except Exception:
                        continue
    except requests.RequestException as exc:
        yield f"\n\n[Error reaching Ollama: {exc}]"


# ==================================================================
# FASTER-WHISPER (ASR + auto language detection)
# ==================================================================
@st.cache_resource(show_spinner=False)
def get_whisper_model():
    if WhisperModel is None:
        raise RuntimeError(
            "faster-whisper is not installed. Add `faster-whisper` to requirements.txt."
        )
    # int8 quantisation keeps CPU memory low enough to run on Streamlit Cloud.
    return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")


def transcribe_audio_file(uploaded_file, translate_to_english: bool = True) -> str:
    """Transcribe an audio file and return the text.

    Language is auto-detected by Whisper. If `translate_to_english` is True,
    the output is translated to English; otherwise the spoken language is kept.
    """
    model = get_whisper_model()
    name = getattr(uploaded_file, "name", "audio.wav")
    data = uploaded_file.getvalue()
    if not data:
        raise RuntimeError("Audio file is empty.")

    suffix = os.path.splitext(name)[1] or ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()

    try:
        task = "translate" if translate_to_english else "transcribe"
        # beam_size=5 gives better accuracy for mixed-language (Malay-English) audio.
        # language=None lets Whisper auto-detect the language per segment.
        # initial_prompt seeds Whisper's vocabulary with TalentCorp brand names and
        # common Manglish/Malay terms so they are transcribed correctly.
        initial_prompt = (
            "This is a TalentCorp Malaysia internal meeting in Manglish — a mix of "
            "English and Bahasa Malaysia. "
            "Brand names: TalentCorp, MyMahir, MyNext, MyXpats, MyHeart, MyWira, "
            "GEF, MPT, MYXpats, TCBD, GCEO, Supabase. "
            "Common Malay words: lah, kan, boleh, macam, memang, sikit, banyak, "
            "sudah, belum, takde, takut, cakap, kena, okay, ya, eh, ah, "
            "nak, ada, dari, untuk, dengan, tapi, sebab, kalau, bila, semua. "
            "Departments: Group Digital, Group Finance, Group Human Resources, "
            "Group Strategy Office, Campus Engagement, School Talent Hub, "
            "MyMahir Workforce Solutions, Group Business Intelligence."
        )
        segments, _info = model.transcribe(
            tmp.name,
            task=task,
            vad_filter=True,
            beam_size=5,
            language=None,
            initial_prompt=initial_prompt,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        return text.strip()
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)


# ==================================================================
# DOCUMENT EXTRACTION (PDF / DOCX / XLSX / CSV)
# ==================================================================
def _dataframe_to_text(df: pd.DataFrame, row_limit: int = 40) -> str:
    df = df.fillna("")
    if df.empty:
        return ""
    out = []
    for idx, row in df.head(row_limit).iterrows():
        fields = [f"{c}: {str(row[c]).strip()}" for c in df.columns if str(row[c]).strip()]
        if fields:
            out.append(f"Row {idx + 1}: " + " | ".join(fields))
    return "\n".join(out)


def extract_text_from_document(uploaded_file) -> str:
    """Extract readable text from an uploaded supporting document."""
    name = getattr(uploaded_file, "name", "document").lower()
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    if name.endswith(".pdf"):
        if PdfReader is None:
            raise RuntimeError("PDF support requires `pypdf`.")
        reader = PdfReader(uploaded_file)
        pages = [p.extract_text() or "" for p in reader.pages]
        text = "\n".join(p.strip() for p in pages if p.strip())
        if not text:
            raise RuntimeError("This PDF has no selectable text (likely scanned).")
        return text

    if name.endswith(".docx"):
        if Document is None:
            raise RuntimeError("DOCX support requires `python-docx`.")
        doc = Document(uploaded_file)
        return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())

    if name.endswith((".xlsx", ".xls")):
        sheets = pd.read_excel(uploaded_file, sheet_name=None)
        chunks = []
        for sheet_name, frame in sheets.items():
            chunks.append(f"Sheet: {sheet_name}")
            chunks.append(_dataframe_to_text(frame))
        return "\n\n".join(c for c in chunks if c.strip())

    if name.endswith(".csv"):
        return _dataframe_to_text(pd.read_csv(uploaded_file))

    raise RuntimeError("Unsupported document format. Use PDF, DOCX, XLSX, XLS, or CSV.")


def append_document_to_transcript(current: str, extracted: str) -> str:
    current = (current or "").strip()
    if current:
        return f"{current}\n\nSupporting document:\n{extracted}"
    return extracted
