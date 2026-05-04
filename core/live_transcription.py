"""Live transcription via Deepgram streaming API + streamlit-webrtc.

Architecture
------------
Browser mic → WebRTC → streamlit-webrtc recv() callback
                              ↓
                       thread-safe audio queue
                              ↓
                    Deepgram WebSocket worker thread
                              ↓
                      _TranscriptStore (session-safe)

Setup
-----
1. Add DEEPGRAM_API_KEY to .streamlit/secrets.toml or as an env var.
2. Ensure requirements.txt includes:
       streamlit-webrtc>=0.47.0
       deepgram-sdk>=3.2.0
       av>=10.0.0

If the Deepgram key is missing or packages are not installed the module
degrades gracefully — is_available() returns False and the caller can fall
back to batch Whisper transcription.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

# ── Optional heavy deps — fail lazily so a missing package never breaks import ──
try:
    import av  # noqa: F401  (used inside recv())
    import numpy as np
    _AV = True
except ImportError:
    _AV = False
    np = None  # type: ignore[assignment]

try:
    from streamlit_webrtc import AudioProcessorBase, RTCConfiguration, WebRtcMode  # noqa: F401
    _WEBRTC = True
except ImportError:
    _WEBRTC = False

    # Provide a no-op base class so the class definition below doesn't fail
    class AudioProcessorBase:  # type: ignore[no-redef]
        pass

try:
    from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
    _DEEPGRAM = True
except ImportError:
    _DEEPGRAM = False


# ---------------------------------------------------------------------------
# Public STUN configuration (no credentials needed)
# ---------------------------------------------------------------------------
RTC_CONFIG: dict = {
    "iceServers": [
        {"urls": ["stun:stun.l.google.com:19302"]},
        {"urls": ["stun:stun1.l.google.com:19302"]},
    ]
}


def is_available() -> bool:
    """True when all three optional dependencies are installed."""
    return _AV and _WEBRTC and _DEEPGRAM


# ---------------------------------------------------------------------------
# Thread-safe transcript store
# ---------------------------------------------------------------------------
class _TranscriptStore:
    """Accumulates final and interim Deepgram segments across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._finals: list[dict] = []   # {"speaker": int|None, "text": str}
        self._interim: str = ""

    # ── Writers (called from Deepgram callback thread) ──────────────────────
    def add_final(self, speaker: Optional[int], text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self._finals.append({"speaker": speaker, "text": text})

    def set_interim(self, text: str) -> None:
        with self._lock:
            self._interim = (text or "").strip()

    # ── Readers (called from main Streamlit thread) ──────────────────────────
    def get_interim(self) -> str:
        with self._lock:
            return self._interim

    def has_content(self) -> bool:
        with self._lock:
            return bool(self._finals or self._interim)

    def formatted(self) -> str:
        """Finals with speaker labels, e.g. '[Speaker 1]: Hello there.'"""
        with self._lock:
            finals = list(self._finals)

        if not finals:
            return ""

        lines: list[str] = []
        _SENTINEL = object()
        cur_spk: object = _SENTINEL
        cur_words: list[str] = []

        for seg in finals:
            spk = seg.get("speaker")
            txt = seg["text"]
            if spk != cur_spk:
                if cur_words and cur_spk is not _SENTINEL:
                    label = (
                        f"Speaker {(cur_spk or 0) + 1}"  # type: ignore[operator]
                        if cur_spk is not None
                        else "Speaker"
                    )
                    lines.append(f"[{label}]: {' '.join(cur_words)}")
                cur_spk = spk
                cur_words = [txt]
            else:
                cur_words.append(txt)

        if cur_words and cur_spk is not _SENTINEL:
            label = (
                f"Speaker {(cur_spk or 0) + 1}"  # type: ignore[operator]
                if cur_spk is not None
                else "Speaker"
            )
            lines.append(f"[{label}]: {' '.join(cur_words)}")

        return "\n".join(lines)

    def plain_text(self) -> str:
        """Finals as plain text without speaker labels."""
        with self._lock:
            return " ".join(s["text"] for s in self._finals if s["text"])


# ---------------------------------------------------------------------------
# Audio processor
# ---------------------------------------------------------------------------
class DeepgramAudioProcessor(AudioProcessorBase):  # type: ignore[misc]
    """
    streamlit-webrtc audio processor that streams PCM frames to Deepgram.

    Example usage in capture.py::

        from streamlit_webrtc import webrtc_streamer, WebRtcMode
        from core.live_transcription import DeepgramAudioProcessor, RTC_CONFIG

        ctx = webrtc_streamer(
            key="live_asr",
            mode=WebRtcMode.SENDONLY,
            audio_processor_factory=lambda: DeepgramAudioProcessor(
                api_key=get_deepgram_key(),
                language="en",
                diarize=True,
            ),
            rtc_configuration=RTC_CONFIG,
            media_stream_constraints={"audio": True, "video": False},
            async_processing=True,
        )

        if ctx.audio_processor:
            st.write(ctx.audio_processor.store.formatted())
    """

    def __init__(
        self,
        api_key: str,
        language: str = "en",
        diarize: bool = True,
    ) -> None:
        self._api_key = api_key
        self._language = language
        self._diarize = diarize

        # Thread-safe queue: main audio pipeline → Deepgram worker
        self._audio_queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=500)

        # Public: read from Streamlit main thread
        self.store = _TranscriptStore()

        # Sample-rate discovery from first frame
        self._sample_rate: Optional[int] = None
        self._sr_ready = threading.Event()

        # Start the Deepgram worker immediately
        self._worker = threading.Thread(target=self._dg_worker, daemon=True)
        self._worker.start()

    # ── streamlit-webrtc interface ───────────────────────────────────────────
    def recv(self, frame: "av.AudioFrame") -> "av.AudioFrame":  # type: ignore[name-defined]
        """Receive one audio frame from WebRTC, convert, enqueue for Deepgram."""
        if not _AV or np is None:
            return frame
        try:
            audio = frame.to_ndarray()

            # Collapse to mono
            if audio.ndim > 1:
                audio = audio.mean(axis=0)

            # Normalise to int16 regardless of source format
            fmt = frame.format.name if frame.format else ""
            if fmt in ("fltp", "flt", "dblp", "dbl"):
                # Float [-1, 1] → int16
                audio_i16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
            elif fmt in ("s16", "s16p"):
                audio_i16 = audio.astype(np.int16)
            elif fmt in ("s32", "s32p"):
                audio_i16 = (audio >> 16).astype(np.int16)
            else:
                # Unknown — assume float
                audio_i16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)

            # Capture sample rate from first frame
            if self._sample_rate is None:
                self._sample_rate = frame.sample_rate
                self._sr_ready.set()

            try:
                self._audio_queue.put_nowait(audio_i16.tobytes())
            except queue.Full:
                pass  # Drop frame under extreme load rather than block

        except Exception:
            pass  # Never let a recv() error bubble up to WebRTC internals

        return frame

    # ── Deepgram worker ──────────────────────────────────────────────────────
    def _dg_worker(self) -> None:
        """Background thread: maintain Deepgram WebSocket and drain audio queue."""
        if not _DEEPGRAM:
            self.store.add_final(None, "[deepgram-sdk not installed — pip install deepgram-sdk]")
            return

        # Wait until the first audio frame tells us the sample rate (max 30 s)
        if not self._sr_ready.wait(timeout=30):
            self.store.add_final(None, "[Timed out waiting for audio — check microphone permissions]")
            return

        sample_rate = self._sample_rate or 48000

        try:
            client = DeepgramClient(self._api_key)
            conn = client.listen.live.v("1")

            # ── Transcript callback (runs in Deepgram's internal thread) ────
            def _on_transcript(_self: object, result: object, **_kw: object) -> None:
                try:
                    alt = result.channel.alternatives[0]  # type: ignore[attr-defined]
                    text: str = alt.transcript or ""
                    if not text:
                        return
                    speaker: Optional[int] = None
                    if self._diarize and getattr(alt, "words", None):
                        speaker = getattr(alt.words[0], "speaker", None)
                    if result.is_final:  # type: ignore[attr-defined]
                        self.store.add_final(speaker, text)
                        self.store.set_interim("")
                    else:
                        self.store.set_interim(text)
                except Exception:
                    pass

            conn.on(LiveTranscriptionEvents.Transcript, _on_transcript)

            opts = LiveOptions(
                model="nova-2",
                language=self._language,
                diarize=self._diarize,
                punctuate=True,
                smart_format=True,
                encoding="linear16",
                sample_rate=sample_rate,
                channels=1,
            )
            conn.start(opts)

            # Drain queue → Deepgram until sentinel None received
            while True:
                chunk = self._audio_queue.get()
                if chunk is None:
                    break
                conn.send(chunk)

            conn.finish()

        except Exception as exc:
            self.store.add_final(None, f"[Deepgram error: {exc}]")

    def stop(self) -> None:
        """Signal worker to finish cleanly (called when WebRTC stops)."""
        try:
            self._audio_queue.put_nowait(None)
        except queue.Full:
            pass
