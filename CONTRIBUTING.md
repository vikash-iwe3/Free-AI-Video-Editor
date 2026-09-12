# Contributing to Free AI Video Editor

Thanks for your interest! Free AI Video Editor is a small, dependency-light project —
contributions are welcome and easy to review.

## Dev environment

```bash
git clone https://github.com/vikash-iwe3/Free-AI-Video-Editor.git
cd Free AI Video Editor
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python app.py                    # http://127.0.0.1:8137
```

Requirements: **Python 3.10+** and **ffmpeg + ffprobe on PATH**. No GPU,
no accounts, no build step.

## Test before pushing

```bash
pytest -q
```

The suite renders real MP4s with ffmpeg (a few seconds per test) and keeps
everything inside a temp directory — no network needed.

## Where things live

| Area | File |
|---|---|
| HTTP routes / API | `app.py` |
| Job manager + the four pipelines | `core/jobs.py` |
| ffmpeg building blocks (segments, transitions, captions, mixing) | `core/render.py` |
| Slide generation | `core/slides.py` |
| TTS | `core/tts.py` |
| Optional ASR (captions) | `core/asr.py` |
| Probing / fonts / process helpers | `core/util.py` |
| UI | `static/index.html`, `static/app.js`, `static/style.css` |

## Conventions & guardrails

- **Paths in filtergraphs must stay relative.** Every ffmpeg invocation runs
  with `cwd=<job dir>` and passes only bare filenames to `fontfile=` /
  `textfile=`. Absolute paths with `C\:` break filtergraph escaping on Windows
  (see README "Design notes") — keep command-line `-i` args absolute, and
  keep anything inside a filter string relative.
- Keep the CPU-only promise: no torch, no CUDA, no GPU encoders.
- Once any `-map` appears on an ffmpeg command, **all** mapped streams must be
  explicit — otherwise ffmpeg silently drops the rest.
- Python style: stdlib + type hints where natural; match surrounding style.
- UI changes need no build step; static files are served as-is.
- User media lives in `workspace/` and is **gitignored** — never commit it.

## Pull requests

1. Branch from `main` (`git checkout -b feat/xyz`).
2. Keep diffs focused; one feature per PR.
3. Add/extend a test when changing a pipeline or adding an endpoint.
4. `pytest -q` must pass (CI runs it on Linux, Python 3.10 + 3.12).
5. Update `CHANGELOG.md` under *Unreleased* for anything user-visible.

Bug reports and ideas via GitHub issues are welcome too — include the exact
UI mode, parameters, and the job's error text (`Jobs` panel → error, or
`workspace/jobs/<id>/job.json`).
