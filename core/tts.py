"""Free neural TTS via the Microsoft Edge voice catalog (CPU, no key, internet only).

Wrapped as a synchronous API around edge_tts's asyncio entry point; retries
transient failures because the upstream endpoint occasionally returns empty
streams.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

from .util import run, which_ffmpeg, probe_duration

VOICES = [
    {"id": "en-US-AndrewNeural", "label": "English (US) - Andrew, male"},
    {"id": "en-US-AvaNeural", "label": "English (US) - Ava, female"},
    {"id": "en-US-BrianNeural", "label": "English (US) - Brian, male"},
    {"id": "en-GB-SoniaNeural", "label": "English (UK) - Sonia, female"},
    {"id": "hi-IN-MadhurNeural", "label": "Hindi - Madhur, male"},
    {"id": "hi-IN-SwaraNeural", "label": "Hindi - Swara, female"},
    {"id": "en-IN-NeerjaNeural", "label": "Indian English - Neerja, female"},
    {"id": "en-IN-PrabhatNeural", "label": "Indian English - Prabhat, male"},
    {"id": "es-ES-ElviraNeural", "label": "Spanish - Elvira, female"},
    {"id": "fr-FR-DeniseNeural", "label": "French - Denise, female"},
    {"id": "de-DE-KatjaNeural", "label": "German - Katja, female"},
    {"id": "zh-CN-XiaoxiaoNeural", "label": "Chinese - Xiaoxiao, female"},
    {"id": "ja-JP-NanamiNeural", "label": "Japanese - Nanami, female"},
    {"id": "ar-SA-ZariyahNeural", "label": "Arabic - Zariyah, female"},
]


def synthesize(text: str, out_path: Path, voice: str = "en-US-AndrewNeural",
               rate: str = "+0%", attempts: int = 4) -> Path:
    """Render text to a 48 kHz stereo WAV at out_path (mp3 then transcode for
    uniform sample rate / no decode-variance in mixing graphs)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mp3 = out_path.with_suffix(".mp3")
    code = "import asyncio,edge_tts;asyncio.run(edge_tts.Communicate(" \
           "TEXT,VOICE,rate=RATE).save(OUT))"
    for i in range(attempts):
        run_code = code.replace("TEXT", repr(text)).replace("VOICE", repr(voice)) \
            .replace("RATE", repr(rate)).replace("OUT", repr(str(mp3)))
        proc = subprocess.run(
            [sys.executable, "-c", run_code], capture_output=True, text=True)
        if proc.returncode == 0 and mp3.exists() and mp3.stat().st_size > 1024:
            break
        if i < attempts - 1:
            time.sleep(2 + i * 2)
    else:
        raise RuntimeError(f"TTS failed after {attempts} attempts: {proc.stderr[-300:]}")
    ff, _ = which_ffmpeg()
    run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp3),
         "-ar", "48000", "-ac", "2", str(out_path)])
    mp3.unlink(missing_ok=True)
    return out_path


def synthesize_duration(text: str, out_path: Path, voice: str, rate: str = "+0%") -> float:
    synthesize(text, out_path, voice, rate)
    return probe_duration(out_path)
