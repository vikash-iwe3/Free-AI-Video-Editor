# Changelog

All notable changes to Free AI Video Editor are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-09-12

### Changed
- **Renamed** the project from *VideoForge* to **Free AI Video Editor** (UI,
  package metadata, docs and repo URLs) to reflect what it is: a free,
  local AI video editor for text / images / clips / voice.
- **Complete UI redesign** — minimal professional design system: neutral dark
  palette with a single indigo accent, inline SVG icon tabs (deep-linkable
  `#images`, `#clips`…), uppercase micro-labels, switch toggles, numbered
  scene cards, and a Queue rail with status dots, relative timestamps and a
  slim progress bar.
### Added
- Editor UI previews in the README (Text, Images, Clips, Voice tabs).

## [1.0.0] — 2026-09-12

First public release.

### Added
- **Text → Video**: scene list → auto-generated slides (Pillow, gradient
  backgrounds, auto-fit headings, word-wrapped body, 6 palettes,
  circuit-line texture) with per-scene AI narration and burned-in captions.
- **Images → Video**: ordered image montage with Ken-Burns motion
  (`zoompan`), per-image captions spoken and burned, crossfade/fade/hard-cut
  options.
- **Clips → Video**: upload video clips with per-clip trim (in/duration),
  canvas/fps normalization, crossfade joins (`xfade` + `acrossfade` with
  automatic fallback to hard cut), keep/mute clip audio, BGM bed, end fade.
- **Voice → Video**: uploaded voice track (or typed narration via TTS) with
  optional images; visuals auto-fit to the audio length; captions from your
  text lines (evenly spread) or offline speech-to-text (optional
  faster-whisper).
- Single-page dark UI: drag-and-drop uploads, reorderable scenes/images/clips,
  per-job progress + stage text, inline HTML5 video preview, download, delete,
  jobs persist across restarts (JSON state files).
- API for scripting: `POST /api/upload`, `POST /api/jobs`,
  `GET /api/jobs[/<id>]`, `GET /api/jobs/<id>/result`, `DELETE /api/jobs/<id>`,
  `GET /api/meta`, `GET /api/health`.
- 14 neural voices across en-US/en-GB/en-IN/hi-IN/es-ES/fr-FR/de-DE/zh-CN/
  ja-JP/ar-SA, speech-rate control.
- Cross-platform font resolution (Windows Arial/Nirmala/YaHei → Linux DejaVu/
  Noto/Liberation → macOS Helvetica/PingFang), with runtime copy into a local
  fonts directory for ffmpeg drawtext safety.
- CPU-only pipeline: ffmpeg (libx264 + aac), Pillow, edge-tts; loudness-
  normalized audio (`-16 LUFS`), 480p/720p/1080p @ 30fps.
- Test suite (`pytest`), GitHub Actions CI (Linux matrix, Python 3.10/3.12),
  launcher scripts `run.bat` / `run.sh`.

### Fixed during bring-up (kept here as design notes)
- ffmpeg filtergraph path escaping on Windows: solved structurally by running
  each job with `cwd=<job dir>` and relative `fontfile=`/`textfile=` only.
- Pillow 12 removed `FreeTypeFont.height`; line height now derives from
  `getmetrics()` with fallback.
- `ffmpeg -map` semantics: once any explicit map exists all others must be
  explicit — image segments now map both video and audio.
- `mix_music` output-stream labels used the wrong loop variable; fixed.
- Stale in-memory job state after external edits; job state is now read from
  disk (`workspace/jobs/<id>/job.json`) and memory is a fallback only.

## [Unreleased]

### Planned
- Aspect-ratio presets (9:16 vertical / 1:1 square)
- Optional BGM ducking under narration (sidechaincompress)
- Simple title-card overlay mode (lower thirds)
