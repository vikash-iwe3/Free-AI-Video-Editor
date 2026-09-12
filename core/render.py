"""ffmpeg render engine (CPU, libx264/aac).

Every job gets its own working directory and runs ffmpeg with cwd set there, so
filter-graph paths (textfile/fontfile) stay relative and colon-free.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from .util import (FPS, SAMPLE_RATE, run, which_ffmpeg, probe_duration,
                   probe_has_audio, font_rel, write_text_file)

ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-pix_fmt", "yuv420p", "-r", str(FPS),
       "-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE), "-ac", "2",
       "-movflags", "+faststart"]
VIDEO_ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-r", str(FPS)]


def canvas(res: str) -> tuple[int, int]:
    return {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}[res or "1080p"]

# ---------------------------------------------------------------- segments

def image_to_segment(img: Path, dur: float, out_dir: Path, name: str,
                     cw: int = 1920, ch: int = 1080, pan: str = "in") -> Path:
    """Ken-Burns a still image into a normalized video segment with silent audio."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.mp4"
    frames = max(2, int(dur * FPS))
    if pan == "in":
        zp = (f"zoompan=z='min(1+0.00045*on,1.10)':x='iw/2-(iw/zoom/2)':"
              f"y='ih/2-(ih/zoom/2)':d={frames}:s={cw}x{ch}:fps={FPS}")
    elif pan == "left":
        zp = (f"zoompan=z='1.10':x='(iw-iw/zoom)*on/{frames}':y='ih/2-(ih/zoom/2)':"
              f"d={frames}:s={cw}x{ch}:fps={FPS}")
    elif pan == "right":
        zp = (f"zoompan=z='1.10':x='(iw-iw/zoom)*(1-on/{frames})':y='ih/2-(ih/zoom/2)':"
              f"d={frames}:s={cw}x{ch}:fps={FPS}")
    else:
        zp = f"scale={cw}:{ch}:force_original_aspect_ratio=decrease,pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    ff, _ = which_ffmpeg()
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(Path(img).resolve()),
           "-f", "lavfi", "-t", f"{dur:.3f}",
           "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}"]
    if pan == "static":
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(Path(img).resolve()),
                "-map", "2:v", "-vf", zp]
    else:
        # zoompan expands the single decoded frame into `frames` output frames;
        # hold at native 1.0 for the first third, then slow zoom-in
        hold = frames // 3
        zp = (f"zoompan=z='if(lt(on,{hold}),1,min(1+0.00045*(on-{hold}),1.10))':"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={cw}x{ch}:fps={FPS}")
        cmd += ["-map", "0:v", "-vf",
                f"scale={cw*2}:{ch*2}:force_original_aspect_ratio=increase,crop={cw*2}:{ch*2}," + zp]
    cmd += ["-map", "1:a", "-t", f"{dur:.3f}"] + ENC + [out.name]
    run(cmd, cwd=out_dir)
    return out


def video_to_segment(src: Path, out_dir: Path, name: str, tin: float = 0.0,
                     tlen: float | None = None, cw: int = 1920, ch: int = 1080,
                     keep_audio: bool = True, volume: float = 1.0) -> Path:
    """Re-cut + normalize a video clip to the canvas; adds silent audio when the
    source has none so every segment is concat/xfade compatible."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.mp4"
    has_a = probe_has_audio(src)
    dur = probe_duration(src)
    if tlen is None:
        tlen = max(0.2, dur - tin)
    vf = (f"scale={cw}:{ch}:force_original_aspect_ratio=decrease,"
          f"pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}")
    cmd = [ff_bin(), "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{tin:.3f}", "-t", f"{tlen:.3f}", "-i", str(Path(src).resolve())]
    if not has_a or not keep_audio:
        cmd += ["-f", "lavfi", "-t", f"{tlen:.3f}",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}"]
        cmd += ["-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    else:
        cmd += ["-vf", vf, "-af", f"volume={volume:.3f}"]
    cmd += ENC + [out.name]
    run(cmd, cwd=out_dir)
    return out


def silence_seconds(seconds: float, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.wav"
    run([ff_bin(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-t", f"{seconds:.3f}",
         "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}",
         "-c:a", "pcm_s16le", str(out)], cwd=out_dir)
    return out


def build_narration(parts: list[tuple[Path | None, float]], out_dir: Path) -> Path:
    """Interleave (wav|None, seconds) -> one track (None means silence)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    items: list[Path] = []
    for i, (wav, sec) in enumerate(parts):
        if wav is not None and wav.exists():
            items.append(wav)
        if sec > 0.01:
            items.append(silence_seconds(sec, out_dir, f"sil_{i}"))
    if not items:
        return silence_seconds(1, out_dir, "sil_empty")
    inputs: list[str] = []
    flt: list[str] = []
    for i, p in enumerate(items):
        inputs += ["-i", p.name]
        flt.append(f"[{i}:a]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo[a{i}]")
    flt.append("".join(f"[a{i}]" for i in range(len(items))) +
               f"concat=n={len(items)}:v=0:a=1[out]")
    out = out_dir / "narration.wav"
    run([ff_bin(), "-hide_banner", "-loglevel", "error", "-y"] + inputs +
        ["-filter_complex", ";".join(flt), "-map", "[out]", str(out)], cwd=out_dir)
    return out

# ---------------------------------------------------------------- assembly

def join_segments(segs: list[Path], out_dir: Path, transition: str = "cut",
                  trans_dur: float = 0.5) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "assembled.mp4"
    if len(segs) == 1:
        shutil.copy2(segs[0], out)
        return out
    if transition in ("dissolve", "fade"):
        try:
            return _xfade_chain(segs, out, trans_dur if transition == "dissolve" else 0.35)
        except RuntimeError:
            pass  # fall back to hard cut
    lst = out_dir / "join.txt"
    lines = "".join("file '" + str(Path(p).resolve()).replace("\\", "/") + "'\n" for p in segs)
    lst.write_text(lines, encoding="utf-8")
    run([ff_bin(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", lst.name,
         "-c", "copy", out.name], cwd=out_dir)
    return out


def _xfade_chain(segs: list[Path], out: Path, d: float) -> Path:
    durs = [probe_duration(p) for p in segs]
    n = len(segs)
    inputs: list[str] = []
    flt: list[str] = []
    for i, p in enumerate(segs):
        inputs += ["-i", str(Path(p).resolve())]
    # video chain
    prev = "0:v"
    offset = durs[0] - d
    for i in range(1, n):
        nxt = f"vx{i}"
        flt.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={d:.3f}:offset={offset:.3f}[{nxt}]")
        prev = nxt
        offset += durs[i] - d
    # audio chain
    prev_a = "0:a"
    for i in range(1, n):
        nxt_a = f"ax{i}"
        flt.append(f"[{prev_a}][{i}:a]acrossfade=d={d:.3f}:c1=tri:c2=tri[{nxt_a}]")
        prev_a = nxt_a
    flt.append(f"[{prev}]format=yuv420p[v]")
    flt.append(f"[{prev_a}]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo[a]")
    run([ff_bin(), "-hide_banner", "-loglevel", "error", "-y"] + inputs +
        ["-filter_complex", ";".join(flt), "-map", "[v]", "-map", "[a]"] +
        ENC + [out.name], cwd=out.parent)
    return out


def _wrap_caption(text: str, width: int = 60) -> str:
    if len(text) <= width:
        return text
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def burn_captions(video: Path, windows: list[dict], out_dir: Path,
                  cw: int = 1920, ch: int = 1080) -> Path:
    """windows: [{text, start, end, size?, pos?}] burned via drawtext."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "captioned.mp4"
    if not windows:
        shutil.copy2(video, out)
        return out
    filters = []
    for i, w in enumerate(windows):
        txt = Path(f"cap_{i}.txt")
        write_text_file(out_dir / txt, _wrap_caption(w["text"]))
        size = int(w.get("size", 40 * ch / 1080))
        y = w.get("y") or f"h-text_h-{int(60 * ch / 1080)}"
        font = font_rel(w["text"], bold=bool(w.get("bold", True)), dst_dir=out_dir)
        color = w.get("color") or "white"
        filters.append(
            f"drawtext=fontfile={font}:textfile={txt.name}:"
            f"fontcolor={color}:"
            f"fontsize={size}:box=1:boxcolor=black@0.55:boxborderw={int(16*ch/1080)}:"
            f"x=(w-text_w)/2:y={y}:"
            f"enable='between(t,{w['start']:.3f},{w['end']:.3f})'")
    run([ff_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", video.name,
         "-vf", ",".join(filters), "-c:a", "copy"] + VIDEO_ENC +
        ["-movflags", "+faststart", out.name], cwd=out_dir)
    return out


def mix_music(video: Path, narration: Path | None, out_dir: Path,
              bgm: Path | None = None, bgm_gain: float = 0.22,
              narration_gain: float = 1.0, fade_out: float = 0.8) -> Path:
    """Replace the (usually silent) segment audio with narration + optional BGM."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "mixed.mp4"
    vd = probe_duration(video)
    cmd = [ff_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", video.name]
    idx = 1
    parts: list[str] = []
    flt: list[str] = []
    if narration is not None:
        cmd += ["-i", str(Path(narration).resolve())]
        flt.append(f"[{idx}:a]volume={narration_gain:.3f},apad=whole_dur={vd:.3f},atrim=0:{vd:.3f}[n{idx}]")
        parts.append(f"[n{idx}]")
        idx += 1
    if bgm is not None:
        cmd += ["-stream_loop", "-1", "-i", str(Path(bgm).resolve())]
        flt.append(f"[{idx}:a]volume={bgm_gain:.3f},afade=t=in:st=0:d=1,"
                   f"afade=t=out:st={max(0, vd - fade_out):.3f}:d={fade_out},"
                   f"atrim=0:{vd:.3f}[m{idx}]")
        parts.append(f"[m{idx}]")
        idx += 1
    if not parts:
        shutil.copy2(video, out)
        return out
    if len(parts) == 1:
        flt.append(f"{parts[0]}loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
    else:
        flt.append("".join(parts) + f"amix=inputs={len(parts)}:duration=first:dropout_transition=0:normalize=0,"
                                   f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
    cmd += ["-filter_complex", ";".join(flt), "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-ar", str(SAMPLE_RATE), "-ac", "2", out.name]
    run(cmd, cwd=out_dir)
    return out


def fade_tail(video: Path, out_dir: Path, d: float = 0.7) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "faded.mp4"
    vd = probe_duration(video)
    run([ff_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", video.name,
         "-vf", f"fade=t=out:st={max(0, vd - d):.3f}:d={d}",
         "-af", f"afade=t=out:st={max(0, vd - d):.3f}:d={d}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "192k", out.name], cwd=out_dir)
    return out


def ff_bin() -> str:
    ff, _ = which_ffmpeg()
    return ff
