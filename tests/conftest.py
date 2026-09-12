import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from core.util import which_ffmpeg


@pytest.fixture(scope="session")
def ffmpeg():
    try:
        ff, fp = which_ffmpeg()
    except RuntimeError:
        pytest.skip("ffmpeg/ffprobe not available")
    return ff, fp
