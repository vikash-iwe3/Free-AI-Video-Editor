"""Shared helpers: paths, ffmpeg/ffprobe runners, font resolution, filter escaping.

All ffmpeg work is CPU-only (libx264/aac). Jobs run with cwd=<job dir> so every
path that enters a filtergraph (textfile/fontfile) is a *relative* path with no
drive-letter colon -- this sidesteps ffmpeg's filtergraph colon-escaping entirely
on Windows.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = APP_DIR / "workspace"
UPLOADS = WORKSPACE / "uploads"
JOBS = WORKSPACE / "jobs"
OUTPUTS = WORKSPACE / "outputs"
STATIC_FONTS = WORKSPACE / "static_fonts"
for _d in (UPLOADS, JOBS, OUTPUTS, STATIC_FONTS):
    _d.mkdir(parents=True, exist_ok=True)

FPS = 30
SAMPLE_RATE = 48000

# ---------------------------------------------------------------- ffmpeg runs

def which_ffmpeg() -> tuple[str, str]:
    ff = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    fp = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not ff or not fp:
        raise RuntimeError("ffmpeg/ffprobe not found on PATH")
    return ff, fp


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 3600) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2500:]
        raise RuntimeError(f"command failed ({cmd[0]} ...): {tail}")
    return proc.stderr or proc.stdout


def probe_duration(path: Path) -> float:
    _ff, fp = which_ffmpeg()
    out = run([fp, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(out.strip())


def probe_has_audio(path: Path) -> bool:
    _ff, fp = which_ffmpeg()
    out = run([fp, "-v", "error", "-select_streams", "a",
               "-show_entries", "stream=index", "-of", "csv=p=0", str(path)])
    return bool(out.strip())


def probe_video(path: Path) -> dict:
    _ff, fp = which_ffmpeg()
    out = run([fp, "-v", "error", "-show_entries",
               "stream=codec_type,width,height,r_frame_rate,duration",
               "-show_entries", "format=duration", "-of", "json", str(path)])
    return json.loads(out)

# ---------------------------------------------------------------- fonts

# Per-script candidate file names (tried in order, first hit wins).
# Windows ships the first entries; Linux/macOS resolve to DejaVu / Noto.
_FONT_CANDIDATES = {
    "latin_bold": ["arialbd.ttf", "Arial-Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Helvetica.ttc"],
    "latin": ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Helvetica.ttc"],
    "deva": ["Nirmala.ttc", "NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari[wght].ttf", "mangal.ttf"],
    "cjk": ["msyh.ttc", "NotoSansCJK-Regular.ttc", "NotoSansSC-Regular.otf", "PingFang.ttc", "msyh.ttf"],
}
_DEV_RE = re.compile(r"[\u0900-\u097F\u0A00-\u0A7F\u0B80-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F]")
_CJK_RE = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF\u3400-\u4DBF]")

_OS_FONT_DIRS = [
    Path(os.environ.get("SystemRoot", "C:\\Windows")) / "Fonts",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts",
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".fonts",
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
    Path.home() / "Library/Fonts",
]

_font_cache: dict[tuple[str, bool], Path | None] = {}


def script_of(text: str) -> str:
    if _DEV_RE.search(text):
        return "deva"
    if _CJK_RE.search(text):
        return "cjk"
    return "latin"


def _search_font(name: str) -> Path | None:
    p = STATIC_FONTS / name
    if p.exists():
        return p
    for base in _OS_FONT_DIRS:
        if not base.is_dir():
            continue
        direct = base / name
        if direct.exists():
            return direct
        # Linux dists nest fonts under truetype/<family>/...
        try:
            for cand in base.rglob(name):
                return cand
        except (PermissionError, OSError):
            continue
    return None


def font_path(text: str, bold: bool = False) -> Path | None:
    """Resolve a usable font for the text's script; None = use PIL default."""
    sc = script_of(text)
    key = (f"{sc}_bold" if (bold and sc == "latin") else sc, bold)
    if key in _font_cache:
        return _font_cache[key]
    found = None
    for name in _FONT_CANDIDATES[sc]:
        found = _search_font(name)
        if found:
            break
    _font_cache[key] = found
    return found


def ensure_fonts() -> None:
    """Best-effort: copy preferred OS fonts into workspace/static_fonts so that
    drawtext/caption rendering always finds a file (some ffmpeg builds, notably
    Windows, have no fontconfig fallback)."""
    if any(STATIC_FONTS.glob("*")):
        return
    for group in _FONT_CANDIDATES.values():
        for name in group:
            src = _search_font(name)
            if src and STATIC_FONTS not in src.parents:
                try:
                    shutil.copy2(src, STATIC_FONTS / src.name)
                except OSError:
                    pass
                break


def font_rel(text: str, bold: bool = False, dst_dir: Path | None = None) -> str:
    """Copy the needed font into dst_dir (or STATIC_FONTS) and return a path with
    forward slashes and no colon, safe for filter strings."""
    src = font_path(text, bold)
    if src is None:
        raise RuntimeError(
            "no usable system font found for captions; install a font "
            "(e.g. 'sudo apt install fonts-dejavu' or keep Arial/Nirmala)")
    target_dir = dst_dir or STATIC_FONTS
    target_dir.mkdir(parents=True, exist_ok=True)
    dst = target_dir / src.name
    if dst_dir and not dst.exists():
        shutil.copy2(src, dst)
    return dst.name.replace("\\", "/")

# ---------------------------------------------------------------- text utils

def write_text_file(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def safe_slug(text: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9\u0900-\u097F]+", "-", text or "").strip("-")
    return (s[:maxlen] or "untitled").lower()
