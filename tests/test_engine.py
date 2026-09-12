"""Tests for the ffmpeg render engine building blocks.

Self-contained: assets are generated on the fly with Pillow/ffmpeg, so the
suite never needs the network and leaves nothing behind in workspace/.
"""
import numpy as np
import pytest
from PIL import Image

from core import render
from core.util import run, probe_video

pytestmark = pytest.mark.skipif(False, reason="ffmpeg fixture decides")


@pytest.fixture()
def sample_png(tmp_path):
    a = np.zeros((360, 640, 3), dtype=np.uint8)
    a[:, :, 1] = 180
    for y in range(0, 360, 40):
        a[y, :, :] = (255, 255, 255)
    p = tmp_path / "shot.png"
    Image.fromarray(a).save(p)
    return p


@pytest.fixture()
def sample_wav(ffmpeg, tmp_path):
    ff, _ = ffmpeg
    p = tmp_path / "tone.wav"
    run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=400:duration=2", str(p)])
    return p


@pytest.fixture()
def sample_clip(ffmpeg, tmp_path):
    ff, _ = ffmpeg
    p = tmp_path / "clip.mp4"
    run([ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=500:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", str(p)])
    return p


def test_image_to_segment_dims_and_audio(ffmpeg, sample_png, tmp_path):
    out = render.image_to_segment(sample_png, 2.0, tmp_path, "seg", 1280, 720)
    assert out.exists()
    info = probe_video(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert v["width"] == 1280 and v["height"] == 720
    assert render.probe_has_audio(out)
    assert abs(render.probe_duration(out) - 2.0) < 0.35


def test_burn_captions_multiline_and_unicode(ffmpeg, sample_png, tmp_path):
    seg = render.image_to_segment(sample_png, 2.0, tmp_path, "seg", 1280, 720)
    out = render.burn_captions(seg, [
        {"text": "First caption line here with enough words to wrap around the box nicely yes ok",
         "start": 0.05, "end": 1.9},
        {"text": "हिन्दी कैप्शन rendering test", "start": 0.5, "end": 1.5},
    ], tmp_path, 1280, 720)
    assert out.exists()
    assert abs(render.probe_duration(out) - render.probe_duration(seg)) < 0.3


def test_join_segments_cut_and_dissolve(ffmpeg, sample_png, tmp_path):
    a = render.image_to_segment(sample_png, 2.0, tmp_path, "a", 1280, 720)
    b = render.image_to_segment(sample_png, 2.5, tmp_path, "b", 1280, 720)
    cut = render.join_segments([a, b], tmp_path / "cut", transition="cut")
    assert abs(render.probe_duration(cut) - 4.5) < 0.2
    xf = render.join_segments([a, b], tmp_path / "xf", transition="dissolve",
                              trans_dur=0.5)
    assert abs(render.probe_duration(xf) - 4.0) < 0.25


def test_video_to_segment_trims_and_scales(ffmpeg, sample_clip, tmp_path):
    out = render.video_to_segment(sample_clip, tmp_path, "n", tin=0.5,
                                  tlen=1.0, cw=1280, ch=720)
    v = next(s for s in probe_video(out)["streams"]
             if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1280, 720)
    assert abs(render.probe_duration(out) - 1.0) < 0.2


def test_mix_music_applies_loudnorm_and_audio(ffmpeg, sample_png, sample_wav, tmp_path):
    seg = render.image_to_segment(sample_png, 2.0, tmp_path, "seg", 1280, 720)
    mixed = render.mix_music(seg, sample_wav, tmp_path)
    assert render.probe_has_audio(mixed)
    log = run([ffmpeg[0], "-hide_banner", "-i", str(mixed), "-af",
               "volumedetect", "-f", "null", "-"], cwd=tmp_path)
    assert "mean_volume" in log
