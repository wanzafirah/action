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

from config.constants import OLLAMA_MODEL, WHISPER_MODEL, WHISPER_CPU_THREADS
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
# TRANSCRIPT CORRECTION (Ollama)
# ==================================================================
TRANSCRIPT_CORRECTOR_SYSTEM = (
    "You are a Malaysian-context transcript editor. The text you receive was "
    "produced by an automatic speech recognition system listening to Malaysian "
    "workplace meetings that mix English and Bahasa Malaysia (Manglish). "
    "Your job is to fix obvious mis-transcriptions of Malay words, proper "
    "nouns, and Malaysian institution names — without changing the meaning, "
    "rephrasing, summarising, or translating. "
    "\n\n"
    "Common terms you should recognise and correct: "
    "TalentCorp, MyMahir, MyNext, MyXpats, MyHeart, GEF, MPT, GCEO, Supabase; "
    "Pusat Kaunseling Kerjaya, Pertahanan, Alumni, Universiti Malaysia Pahang "
    "Al-Sultan Abdullah (UMP), UPNM, UiTM, UM, UKM, UTM, USM, MMU, APU, UCSI, "
    "UTAR; Group Strategy Office, School Talent Hub, MyMahir Workforce "
    "Solutions, Group Business Intelligence, Graduates Emerging Talent, "
    "MyHeart Facilitation, MYXpats Operations, GCEO Liaison Office. "
    "\n\n"
    "Examples of fixes you should make: "
    "Pousat → Pusat; Patahanan → Pertahanan; Alumnai → Alumni; "
    "Kejaya → Kejayaan or Kerjaya (use whichever fits the surrounding words); "
    "Consoling → Kaunseling; Sherizan stays as Sherizan; Hazman stays as Hazman. "
    "\n\n"
    "Rules: "
    "1. Output ONLY the corrected transcript. No preface, no explanation, no markdown. "
    "2. Preserve all sentences, all speakers, all line breaks. "
    "3. Never invent facts, dates, or names that are not phonetically present. "
    "4. If a word is genuinely ambiguous, leave it as-is rather than guessing wildly. "
    "5. Keep code-switching intact — do not translate Malay to English or vice versa."
)


def correct_transcript_with_ollama(raw_transcript: str, lang_choice: str = "English / Manglish") -> str:
    """Run a raw Whisper transcript through llama3.2 for Malaysian-context correction.

    Cheap (local model), but high-impact: catches name and place-name garbling
    that ASR fundamentally cannot fix on its own.
    """
    if not raw_transcript or not raw_transcript.strip():
        return raw_transcript

    register = (
        "The transcript is in Manglish (mixed English + Bahasa Malaysia)."
        if lang_choice != "Bahasa Melayu"
        else "The transcript is in Bahasa Malaysia."
    )

    user_msg = (
        f"{register}\n\n"
        "Correct the transcript below. Output only the corrected transcript.\n\n"
        f"--- TRANSCRIPT ---\n{raw_transcript}\n--- END ---"
    )

    # Generous token budget — output should be roughly the same length as input.
    approx_tokens = max(800, int(len(raw_transcript.split()) * 2.0))
    corrected = call_ollama(
        system=TRANSCRIPT_CORRECTOR_SYSTEM,
        user_msg=user_msg,
        max_tokens=min(approx_tokens, 4000),
        temperature=0.05,                     # near-deterministic, just fix errors
        num_ctx=max(4096, approx_tokens + 1024),
    ).strip()

    # Defensive: if the model returned nothing useful, fall back to raw.
    if not corrected or len(corrected) < len(raw_transcript) * 0.4:
        return raw_transcript
    return corrected


#audio transcription (whisper)
@st.cache_resource(show_spinner=False)
def get_whisper_model():
    if WhisperModel is None:
        raise RuntimeError(
            "faster-whisper is not installed. Add `faster-whisper` to requirements.txt."
        )
    return WhisperModel(
        WHISPER_MODEL,
        device="cpu",
        compute_type="int8",
        cpu_threads=WHISPER_CPU_THREADS,
    )


def transcribe_audio_file(
    uploaded_file,
    lang_choice: str = "English / Manglish",
    ai_correct: bool = True,
) -> str:
    """Transcribe an audio file and return the text.

    lang_choice:
      "English / Manglish" — pins Whisper to MALAY (ms). Counter-intuitive
          but Malay-pinned Whisper handles English code-switching naturally,
          while English-pinned Whisper has no Malay vocabulary and garbles
          proper nouns (Pusat → Pousat, Pertahanan → Patahanan, etc.).
      "Bahasa Melayu" — also pins to Malay. Same engine path; kept as a
          separate label so the UI reads naturally to non-Manglish users.

    ai_correct:
      When True (default), the raw Whisper output is post-processed by
      llama3.2 with a Malaysian-context correction prompt that fixes
      mistranscribed names, organisations and Malay terms.
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
        # Both modes pin to Malay. Whisper handles code-switched English-in-Malay
        # natively, but English-pinned Whisper has no Malay phonemes and
        # produces garbage for Malay names. Differentiate only via the prompt
        # so Whisper biases towards the right register.
        task = "transcribe"
        language = "ms"

        if lang_choice == "Bahasa Melayu":
            initial_prompt = (
                "Ini adalah mesyuarat dalaman TalentCorp Malaysia dalam Bahasa Malaysia. "
                "Penceramah membincangkan kerjasama dengan Pusat Kaunseling Kerjaya, "
                "Alumni Universiti Malaysia Pahang Al-Sultan Abdullah, Pertahanan, "
                "Politeknik dan Institut Pengajian Tinggi Awam. Mereka menyebut nama "
                "jenama TalentCorp, MyMahir, MyNext, MyXpats, MyHeart, GEF, MPT serta "
                "jabatan seperti Pejabat Strategi Kumpulan, Pusat Bakat Sekolah, "
                "MyMahir Penyelesaian Tenaga Kerja, Pengurusan Bakat Kumpulan."
            )
        else:
            # English / Manglish — same Malay engine, prompt biases toward
            # the typical TalentCorp Manglish meeting register.
            initial_prompt = (
                "Mesyuarat TalentCorp Malaysia dalam Manglish, campuran Bahasa "
                "Malaysia dan English. Penceramah membincangkan kerjasama dengan "
                "Pusat Kaunseling Kerjaya, Alumni Universiti Malaysia Pahang "
                "Al-Sultan Abdullah, Pertahanan, Politeknik. Penceramah Sherizan, "
                "Hazman, Mei Ling, Aisyah, Farhan, Lim Jing Rou, Kavitha. "
                "Brand: TalentCorp, MyMahir, MyNext, MyXpats, MyHeart, MyWira, "
                "GEF, MPT, GCEO, Supabase. Departments: Group Strategy Office, "
                "School Talent Hub, MyMahir Workforce Solutions, Group Business "
                "Intelligence, Graduates Emerging Talent, MyHeart Facilitation, "
                "MYXpats Operations, GCEO Liaison Office. Universities: UMP, "
                "UPNM, UPM, UTM, UiTM, UM, UKM, USM, UNITEN, MMU, APU, UCSI, UTAR."
            )

        segments, _info = model.transcribe(
            tmp.name,
            task=task,
            vad_filter=True,
            beam_size=5,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,  # avoid hallucination loops
            temperature=[0.0, 0.2, 0.4],       # fall back gracefully if no good hypothesis
        )
        raw = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        if not raw:
            return raw

        if not ai_correct:
            return raw

        # Post-correction with Ollama (Malaysian-context prompt)
        try:
            return correct_transcript_with_ollama(raw, lang_choice)
        except Exception:
            # If Ollama is unreachable, return the raw Whisper output rather
            # than failing the whole transcription.
            return raw
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)


#extract document (pdf/excel/docx/csv)
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
