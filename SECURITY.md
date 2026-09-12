# Security Policy

## How Free AI Video Editor handles your data

Free AI Video Editor is **local-first by design**:

- The server binds to `127.0.0.1` only — it is not reachable from other
  machines on your network.
- Uploaded media and rendered outputs stay inside `workspace/` on your disk
  and are never sent anywhere.
- The only outbound network calls are:
  1. **edge-tts** (Microsoft's free text-to-speech endpoint) — *only* when you
     enable an AI voice-over; the text you chose to speak is the payload.
  2. **faster-whisper model download** (Hugging Face) — *only* if you install
     the optional ASR extra and enable auto-captions.
- No analytics, no telemetry, no accounts, no environment secrets.

## Upload limits

- Max request size: 2 GB (`MAX_CONTENT_LENGTH`); accepted kinds are
  video/image/audio by extension whitelist (`app.py`).
- File names are discarded; storage paths use random ids.

## If you expose it beyond localhost

Free AI Video Editor has **no authentication**. Do not port-forward or place it behind
a public reverse proxy as-is. If you must, front it with an authenticated
proxy and keep `MAX_CONTENT_LENGTH` low.

## Reporting a vulnerability

Please report suspected security issues privately via a GitHub **security
advisory** or to [Vikash](https://github.com/vikash-iwe3) directly — not a public issue. We aim
to acknowledge within 72 hours and patch promptly.

## Supported versions

| Version | Supported |
|---|---|
| 1.x | ✅ |
| < 1.x | ❌ |
