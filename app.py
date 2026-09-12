"""Free AI Video Editor - CPU-only web video studio (Flask).

Serves the single-page UI and a small JSON API. Everything renders locally with
ffmpeg + Pillow + edge-tts; no GPU, no cloud accounts.
"""
from __future__ import annotations

import json
import mimetypes
import shutil
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file, abort, send_from_directory

from core import jobs, tts, util
from core.util import UPLOADS, OUTPUTS, JOBS, run, probe_video, which_ffmpeg, safe_slug, ensure_fonts

__version__ = "1.1.0"
__author__ = "Vikash"

ensure_fonts()
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB

VID_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
AUD_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def _classify(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in VID_EXT:
        return "video"
    if suf in IMG_EXT:
        return "image"
    if suf in AUD_EXT:
        return "audio"
    return "other"


# ------------------------------------------------------------------ pages

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ------------------------------------------------------------------ meta

@app.route("/api/meta")
def api_meta():
    try:
        ff, fp = which_ffmpeg()
        ffok = True
    except Exception:
        ffok = False
    return jsonify({
        "version": __version__,
        "author": __author__,
        "home": "https://github.com/vikash-iwe3/Free-AI-Video-Editor",
        "voices": tts.VOICES,
        "ffmpeg": ffok,
        "resolutions": ["480p", "720p", "1080p"],
        "ok": ffok,
    })


@app.route("/api/health")
def api_health():
    try:
        ff, fp = which_ffmpeg()
        return jsonify({"ok": True, "ffmpeg": ff, "ffprobe": fp})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 200


# ------------------------------------------------------------------ uploads

@app.route("/api/upload", methods=["POST"])
def api_upload():
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return jsonify({"error": "no files"}), 400
    out = []
    for fs in files:
        name = fs.filename or "upload"
        ext = Path(name).suffix.lower() or ".bin"
        uid = uuid.uuid4().hex[:12]
        dest = UPLOADS / f"{uid}{ext}"
        fs.save(dest)
        kind = _classify(dest)
        info = {"id": uid, "name": name, "kind": kind,
                "size": dest.stat().st_size}
        if kind == "video":
            try:
                info["duration"] = probe_video(dest).get("format", {}).get("duration")
            except Exception:
                pass
        out.append(info)
    return jsonify({"uploads": out})


@app.route("/api/preview/<uid>")
def api_preview(uid):
    hits = list(UPLOADS.glob(f"{uid}.*"))
    if not hits:
        abort(404)
    return send_file(hits[0])


# ------------------------------------------------------------------ jobs

@app.route("/api/jobs", methods=["POST"])
def api_create_job():
    p = request.get_json(force=True) or {}
    kind = p.get("kind")
    if kind not in jobs.PIPELINES:
        return jsonify({"error": f"unknown kind {kind}"}), 400
    params = p.get("params") or {}
    try:
        jid = jobs.create_job(kind, params)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500
    return jsonify({"id": jid})


@app.route("/api/jobs")
def api_list_jobs():
    return jsonify(jobs.list_jobs())


@app.route("/api/jobs/<jid>")
def api_job(jid):
    j = jobs.get_job(jid)
    if not j:
        abort(404)
    return jsonify(j)


@app.route("/api/jobs/<jid>/result")
def api_job_result(jid):
    j = jobs.get_job(jid)
    if not j or j.get("status") != "done" or not j.get("output"):
        abort(404)
    f = OUTPUTS / j["output"]
    if not f.exists():
        abort(404)
    return send_file(f, mimetype="video/mp4")


@app.route("/api/jobs/<jid>/stream")
def api_job_stream(jid):
    """Range-request video streaming for the in-page player."""
    j = jobs.get_job(jid)
    if not j or not j.get("output"):
        abort(404)
    f = OUTPUTS / j["output"]
    if not f.exists():
        abort(404)
    return send_file(f, mimetype="video/mp4", conditional=True)


@app.route("/api/jobs/<jid>", methods=["DELETE"])
def api_delete_job(jid):
    j = jobs.get_job(jid)
    if j and j.get("output"):
        (OUTPUTS / j["output"]).unlink(missing_ok=True)
    shutil.rmtree(JOBS / jid, ignore_errors=True)
    with jobs._LOCK:  # noqa: SLF001
        jobs.JOBS_MEM.pop(jid, None)
    return jsonify({"ok": True})


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "file too large"}), 413


@app.errorhandler(500)
def server_error(e):  # noqa: ARG001
    return jsonify({"error": "server error"}), 500


if __name__ == "__main__":
    port = 8137
    print(f"\n  Free AI Video Editor running at  http://127.0.0.1:{port}\n", flush=True)
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
