"""Flask app tests via the test client (no network, no port binding)."""
import time

import pytest

from app import app


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def _wait_job(client, jid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").get_json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(1.0)
    pytest.fail(f"job {jid} timed out")


def test_health_and_meta(client):
    h = client.get("/api/health").get_json()
    if not h["ok"]:
        pytest.skip("ffmpeg not available")
    m = client.get("/api/meta").get_json()
    assert m["ok"] is True
    assert "version" in m and m["version"]
    assert len(m["voices"]) >= 10


def test_uploads_are_classified(client):
    import numpy as np
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.fromarray(np.zeros((64, 64, 3), np.uint8)).save(buf, format="PNG")
    buf.seek(0)
    r = client.post("/api/upload", data={"files": (buf, "x.png")},
                    content_type="multipart/form-data")
    up = r.get_json()["uploads"][0]
    assert up["kind"] == "image"


def test_unknown_job_kind_rejected(client):
    r = client.post("/api/jobs", json={"kind": "laser-video", "params": {}})
    assert r.status_code == 400


def test_text_to_video_end_to_end(client):
    if not client.get("/api/health").get_json()["ok"]:
        pytest.skip("ffmpeg not available")
    params = {
        "scenes": [
            {"heading": "Alpha", "body": "first slide body", "duration": 1.2},
            {"heading": "ब्रेन", "body": "devanagari script renders too", "duration": 1.2},
        ],
        "voice": "en-US-AndrewNeural", "resolution": "480p",
        "with_slides_narration": False,
    }
    r = client.post("/api/jobs", json={"kind": "text-to-video", "params": params})
    jid = r.get_json()["id"]
    j = _wait_job(client, jid)
    assert j["status"] == "done", j.get("error")
    body = client.get(f"/api/jobs/{jid}/result").data
    assert len(body) > 10_000
    # listed and deletable
    assert any(x["id"] == jid for x in client.get("/api/jobs").get_json())
    client.delete(f"/api/jobs/{jid}")
    assert not any(x["id"] == jid for x in client.get("/api/jobs").get_json())
