"""Animated slide generator for text-to-video (PIL, no GPU).

Renders 1920x1080 PNG slides with gradient backgrounds, auto-fitted headings,
word-wrapped body text and language-aware fonts (Latin / Devanagari / CJK).
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .util import font_path

W, H = 1920, 1080

PALETTES = [
    ((10, 14, 30), (16, 42, 68), (125, 249, 201)),   # midnight / mint
    ((18, 10, 28), (64, 20, 60), (255, 176, 122)),   # plum / amber
    ((8, 18, 24), (10, 60, 66), (126, 231, 255)),    # deep teal / sky
    ((22, 10, 10), (90, 24, 24), (255, 138, 138)),   # charcoal / coral
    ((12, 12, 16), (48, 44, 30), (255, 224, 130)),   # graphite / gold
    ((14, 16, 40), (40, 46, 120), (170, 190, 255)),  # navy / periwinkle
]


def _gradient(c1, c2) -> Image.Image:
    img = Image.new("RGB", (1, H))
    for y in range(H):
        f = y / (H - 1)
        img.putpixel((0, y), tuple(round(a + (b - a) * f) for a, b in zip(c1, c2)))
    return img.resize((W, H))


def _wrap(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        words = para.split()
        cur = ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = wd
        lines.append(cur)
    return lines


def _line_h(font) -> int:
    try:
        asc, desc = font.getmetrics()
        return int((asc + desc) * 1.12)
    except Exception:
        return int(font.size * 1.3)


def _load_font(text, size, bold):
    path = font_path(text, bold=bold)
    if path is not None:
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def _fit_font(text, size_start, max_w, max_lines, weight="bold"):
    size = size_start
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > 18:
        f = _load_font(text, size, weight == "bold")
        if len(_wrap(probe, text, f, max_w)) <= max_lines:
            return f
        size -= 4
    return _load_font(text, 18, weight == "bold")


def make_slide(text: str, body: str = "", seed: int = 0,
               out_dir: Path | None = None) -> Path:
    """heading `text` + optional body -> slide PNG, returns path."""
    rng = random.Random(seed)
    c1, c2, accent = PALETTES[rng.randrange(len(PALETTES))]
    img = _gradient(c1, c2)
    d = ImageDraw.Draw(img)

    # subtle circuit-lines texture
    for i in range(14):
        x0 = rng.randint(0, W)
        y0 = rng.randint(0, H)
        col = tuple(min(255, c + 14) for c in c2)
        d.line([x0, y0, x0 + rng.choice([-1, 1]) * rng.randint(60, 260), y0], fill=col, width=2)
        d.ellipse([x0 - 4, y0 - 4, x0 + 4, y0 + 4], fill=col)

    pad = 150
    max_w = W - 2 * pad

    title_font = _fit_font(text or " ", 96, max_w, 2)
    tlines = _wrap(d, text, title_font, max_w) if text else []
    th = _line_h(title_font) * len(tlines)

    body_font = _fit_font(body or "x", 44, max_w, 6, weight="regular") if body else None
    blines = _wrap(d, body, body_font, max_w) if body else []

    body_lh = _line_h(body_font) if body_font else 0
    block_h = th + (40 if tlines and blines else 0) + len(blines) * body_lh
    y = (H - block_h) // 2
    for ln in tlines:
        d.text((pad, y), ln, font=title_font, fill=(255, 255, 255))
        y += _line_h(title_font)
    if tlines and blines:
        d.rectangle([pad, y + 6, pad + 120, y + 12], fill=accent)
        y += 46
    for ln in blines:
        d.text((pad, y), ln, font=body_font, fill=(225, 230, 240))
        y += _line_h(body_font)

    if out_dir is None:
        out_dir = Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5((text + "|" + body + str(seed)).encode()).hexdigest()[:8]
    out = Path(out_dir) / f"slide_{key}.png"
    img.save(out)
    return out
