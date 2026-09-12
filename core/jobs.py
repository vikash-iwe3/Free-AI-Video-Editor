"""Job manager + the four render pipelines (text/image/clip/voice -> video).

Pipelines run in daemon threads and publish JSON state per job; the web layer
polls that state. No GPU, no external accounts: ffmpeg + Pillow + edge-tts.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from . import render, slides, tts
from .util import (UPLOADS, JOBS, OUTPUTS, probe_duration, safe_slug,
                   write_text_file)

JOBS_MEM: dict[str, dict] = {}
_LOCK = threading.Lock()

# ------------------------------------------------------------------ state

def _new_job(kind: str, meta: dict) -> dict:
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "kind": kind, "status": "queued", "stage": "queued",
           "progress": 0, "error": None, "output": None,
           "created": time.time(), "meta": meta}
    with _LOCK:
        JOBS_MEM[jid] = job
    return job


def _upd(jid: str, **kw):
    with _LOCK:
        JOBS_MEM[jid].update(kw)
    (JOBS / jid / "job.json").write_text(
        json.dumps(JOBS_MEM[jid], ensure_ascii=False, indent=1), encoding="utf-8")


def _start(jid: str, fn):
    def _run():
        _upd(jid, status="running", stage="starting", progress=2)
        try:
            out = fn()
            final = OUTPUTS / f"{jid}.mp4"
            if out.resolve() != final.resolve():
                import shutil
                shutil.move(str(out), final)
            _upd(jid, status="done", stage="finished", progress=100,
                 output=final.name)
        except Exception as exc:  # noqa: BLE001 - report to UI
            _upd(jid, status="error", stage="failed",
                 error=str(exc)[-1500:])
    threading.Thread(target=_run, daemon=True).start()
    return jid


def get_job(jid: str) -> dict | None:
    p = JOBS / jid / "job.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    with _LOCK:
        return JOBS_MEM.get(jid)


def list_jobs() -> list[dict]:
    seen = {}
    for p in JOBS.glob("*/job.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            seen[j["id"]] = j
        except Exception:
            pass
    with _LOCK:
        for jid, j in JOBS_MEM.items():
            if jid not in seen:
                seen[jid] = j
    return sorted(seen.values(), key=lambda j: j["created"], reverse=True)


def job_dir(jid: str) -> Path:
    d = JOBS / jid
    d.mkdir(parents=True, exist_ok=True)
    return d


def uploaded_path(uid: str) -> Path:
    hits = list(UPLOADS.glob(f"{uid}.*")) + [p for p in UPLOADS.glob(f"{uid}_*")]
    if not hits:
        raise FileNotFoundError(f"upload not found: {uid}")
    return hits[0]

# ------------------------------------------------------------------ pipelines

def _resolution(p: dict) -> tuple[int, int]:
    return render.canvas(p.get("resolution", "1080p"))


def pipeline_text_to_video(jid: str, p: dict) -> None:
    """scenes -> slides + narration + captions."""
    def work():
        d = job_dir(jid)
        cw, ch = _resolution(p)
        scenes = p.get("scenes") or []
        if not scenes:
            raise ValueError("no scenes provided")
        voice = p.get("voice", "en-US-AndrewNeural")
        rate = p.get("rate", "+0%")
        with_music = p.get("with_slides_narration", True)

        segs, caption_windows, narr_parts = [], [], []
        tl = 0.0
        for i, sc in enumerate(scenes):
            heading = (sc.get("heading") or "").strip()
            body = (sc.get("body") or "").strip()
            spoken = (sc.get("narration") or "").strip() or (heading + ". " if heading else "") + body
            _upd(jid, stage=f"narrating scene {i+1}/{len(scenes)}",
                 progress=int(5 + 60 * i / len(scenes)))
            dur = None
            if with_music and spoken:
                wav = d / f"narr_{i}.wav"
                dur = tts.synthesize_duration(spoken, wav, voice, rate)
                narr_parts.append((wav, 0.35))
                cap_text = spoken
                cap_dur = dur
            else:
                dur = float(sc.get("duration", 4))
                narr_parts.append((None, dur))
                cap_text = heading or body
                cap_dur = dur
            png = slides.make_slide(heading or f"Scene {i+1}", body, seed=i, out_dir=d / "slides")
            seg = render.image_to_segment(png, dur + 0.35, d / "segs", f"seg_{i}", cw, ch,
                                          pan="in")
            segs.append(seg)
            caption_windows.append({"text": cap_text, "start": tl,
                                    "end": tl + cap_dur, "size": int(30 * ch / 1080),
                                    "y": f"h-text_h-{int(40*ch/1080)}"})
            tl += dur + 0.35
        _upd(jid, stage="assembling", progress=72)
        video = render.join_segments(segs, d, transition="fade", trans_dur=0.4)
        video = render.burn_captions(video, caption_windows, d, cw, ch)
        _upd(jid, stage="mixing audio", progress=86)
        narration = render.build_narration(narr_parts, d) if with_music else None
        bgm = uploaded_path(p["bgm"]) if p.get("bgm") else None
        video = render.mix_music(video, narration, d, bgm=bgm,
                                 bgm_gain=p.get("bgm_gain", 0.22),
                                 narration_gain=1.0)
        video = render.fade_tail(video, d)
        return video
    _start(jid, work)


def pipeline_images_to_video(jid: str, p: dict) -> None:
    """ordered images (+captions) -> Ken Burns montage with optional VO/music."""
    def work():
        d = job_dir(jid)
        cw, ch = _resolution(p)
        images = p.get("images") or []
        if not images:
            raise ValueError("no images provided")
        voice = p.get("voice", "en-US-AndrewNeural")
        rate = p.get("rate", "+0%")
        narrate = p.get("narrate_captions", True)
        trans = p.get("transition", "dissolve")

        narr_parts, segs, caption_windows = [], [], []
        tl = 0.0
        for i, im in enumerate(images):
            img = uploaded_path(im["id"])
            caption = (im.get("caption") or "").strip()
            _upd(jid, stage=f"image {i+1}/{len(images)}",
                 progress=int(5 + 55 * i / len(images)))
            wav = None
            if narrate and caption:
                wav = d / f"narr_{i}.wav"
                dur = tts.synthesize_duration(caption, wav, voice, rate) + 0.5
            else:
                dur = float(im.get("duration", 3.5))
            narr_parts.append((wav, max(0.0, dur - (probe_duration(wav) if wav else 0))))
            pans = ["in", "left", "right"]
            seg = render.image_to_segment(img, dur, d / "segs", f"seg_{i}", cw, ch,
                                          pan=pans[i % 3] if len(images) > 1 else "in")
            segs.append(seg)
            if caption:
                cap_dur = min(dur, (probe_duration(wav) + 0.4) if wav else dur)
                caption_windows.append({"text": caption, "start": tl + 0.15,
                                        "end": tl + cap_dur})
            tl += dur
        _upd(jid, stage="assembling", progress=70)
        video = render.join_segments(segs, d, transition=trans,
                                     trans_dur=float(p.get("trans_dur", 0.5)))
        video = render.burn_captions(video, caption_windows, d, cw, ch)
        _upd(jid, stage="mixing audio", progress=85)
        narration = render.build_narration(narr_parts, d) if narrate else None
        bgm = uploaded_path(p["bgm"]) if p.get("bgm") else None
        video = render.mix_music(video, narration, d, bgm=bgm,
                                 bgm_gain=p.get("bgm_gain", 0.2))
        video = render.fade_tail(video, d)
        return video
    _start(jid, work)


def pipeline_clips_to_video(jid: str, p: dict) -> None:
    """ordered video clips with trims, transitions, optional BGM."""
    def work():
        d = job_dir(jid)
        cw, ch = _resolution(p)
        clips = p.get("clips") or []
        if not clips:
            raise ValueError("no clips provided")
        trans = p.get("transition", "dissolve")
        keep_a = p.get("keep_audio", True)
        vol = float(p.get("clip_volume", 1.0))

        segs = []
        _upd(jid, stage="normalizing clips", progress=10)
        for i, c in enumerate(clips):
            src = uploaded_path(c["id"])
            tin, tlen = float(c.get("in", 0)), c.get("dur")
            tlen = float(tlen) if tlen else None
            seg = render.video_to_segment(src, d / "segs", f"seg_{i}",
                                          tin, tlen, cw, ch, keep_a, vol)
            segs.append(seg)
            _upd(jid, progress=10 + int(55 * (i + 1) / len(clips)))
        _upd(jid, stage="assembling", progress=70)
        video = render.join_segments(segs, d, transition=trans,
                                     trans_dur=float(p.get("trans_dur", 0.5)))
        if p.get("bgm"):
            _upd(jid, stage="mixing BGM", progress=85)
            bgm = uploaded_path(p["bgm"])
            video = render.mix_music(video, None, d, bgm=bgm,
                                     bgm_gain=p.get("bgm_gain", 0.18))
        if p.get("fade_out", True):
            video = render.fade_tail(video, d)
        return video
    _start(jid, work)


def pipeline_voice_to_video(jid: str, p: dict) -> None:
    """voice audio (uploaded or TTS) + images (or solid bg) -> fitting video."""
    def work():
        d = job_dir(jid)
        cw, ch = _resolution(p)
        if p.get("audio"):
            src_audio = uploaded_path(p["audio"])
            audio = d / "voice.wav"
            render.run([render.ff_bin(), "-hide_banner", "-loglevel", "error",
                        "-y", "-i", str(src_audio), "-ar", "48000", "-ac", "2",
                        str(audio)])
        elif p.get("narration_text"):
            audio = d / "voice.wav"
            tts.synthesize(p["narration_text"], audio,
                           p.get("voice", "en-US-AndrewNeural"), p.get("rate", "+0%"))
        else:
            raise ValueError("provide a voice audio file or narration text")
        total = probe_duration(audio)
        _upd(jid, stage=f"audio ready ({total:.1f}s)", progress=25)

        images = p.get("images") or []
        segs = []
        if images:
            n = len(images)
            per = max(0.6, total / n)
            for i, im in enumerate(images):
                img = uploaded_path(im["id"]) if isinstance(im, dict) else uploaded_path(im)
                seg_dur = per + (0.4 if i == n - 1 else 0)
                seg = render.image_to_segment(
                    img, seg_dur, d / "segs", f"seg_{i}", cw, ch,
                    pan=("in" if i % 3 == 0 else "left" if i % 3 == 1 else "right"))
                segs.append(seg)
                _upd(jid, progress=25 + int(40 * (i + 1) / n))
        else:
            png = slides.make_slide(p.get("title") or "", p.get("subtitle") or "",
                                    seed=7, out_dir=d / "slides")
            segs.append(render.image_to_segment(png, total + 0.3, d / "segs",
                                                "seg_0", cw, ch, pan="in"))
        _upd(jid, stage="assembling", progress=70)
        video = render.join_segments(segs, d, transition=p.get("transition", "dissolve"),
                                     trans_dur=0.4)
        mode = p.get("caption_mode", "lines")
        caps: list[dict] = []
        if mode == "auto":
            _upd(jid, stage="transcribing audio", progress=74)
            try:
                from . import asr
                for s in asr.transcribe(audio, p.get("asr_model", "base"), p.get("language")):
                    caps.append({"text": s["text"], "start": s["start"],
                                 "end": min(s["end"] + 0.2, total)})
            except Exception as e:  # noqa: BLE001 - captions are optional
                _upd(jid, stage=f"auto-caption skipped: {e}", progress=78)
        elif mode == "lines":
            lines = [ln.strip() for ln in (p.get("caption_lines") or "").split("\n") if ln.strip()]
            if lines:
                per = total / len(lines)
                caps = [{"text": ln, "start": 0.15 + k * per,
                         "end": 0.15 + (k + 1) * per - 0.05} for k, ln in enumerate(lines)]
        if caps:
            _upd(jid, stage="burning captions", progress=82)
            video = render.burn_captions(video, caps, d, cw, ch)
        _upd(jid, stage="mixing audio", progress=90)
        bgm = uploaded_path(p["bgm"]) if p.get("bgm") else None
        video = render.mix_music(video, audio, d, bgm=bgm,
                                 bgm_gain=p.get("bgm_gain", 0.15))
        video = render.fade_tail(video, d)
        return video
    _start(jid, work)


PIPELINES = {
    "text-to-video": pipeline_text_to_video,
    "images-to-video": pipeline_images_to_video,
    "clips-to-video": pipeline_clips_to_video,
    "voice-to-video": pipeline_voice_to_video,
}


def create_job(kind: str, params: dict) -> str:
    meta = dict(params)
    jid = _new_job(kind, meta).get("id")
    job_dir(jid)
    _upd(jid, status="queued", stage="queued", progress=0)
    PIPELINES[kind](jid, params)
    return jid
