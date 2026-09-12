"""Optional offline speech-to-text for auto-captions (faster-whisper, CPU int8).

Gracefully reports unavailability instead of failing the whole pipeline.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .util import JOBS

CACHE = JOBS / ".asr_cache"


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def transcribe(audio_path: Path, model_size: str = "base",
               language: str | None = None) -> list[dict]:
    """Return [{text, start, end}] using faster-whisper on CPU (int8)."""
    if not available():
        raise RuntimeError(
            "faster-whisper is not installed; run: pip install faster-whisper")
    CACHE.mkdir(parents=True, exist_ok=True)
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8",
                         download_root=str(CACHE))
    segs_iter, _info = model.transcribe(str(audio_path), language=language,
                                        vad_filter=True)
    return [{"text": s.text.strip(), "start": round(float(s.start), 2),
             "end": round(float(s.end), 2)} for s in segs_iter if s.text.strip()]
