"""Test d'intégration détection de plans : génère une vidéo à 3 mires texturées
et vérifie que les 2 coupures sont détectées. Utilise le ffmpeg bundlé."""

import subprocess

import pytest

from vidai.ffmpeg_utils import ffmpeg_path
from vidai.scenes import detect_scene_changes


@pytest.fixture
def three_scene_video(tmp_path):
    """3 plans texturés statiques de 3 s (mires) -> coupures nettes à 3s et 6s."""
    path = tmp_path / "mires.mp4"
    cmd = [
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "smptebars=s=320x240:d=3:r=10",
        "-f", "lavfi", "-i", "rgbtestsrc=s=320x240:d=3:r=10",
        "-f", "lavfi", "-i", "yuvtestsrc=s=320x240:d=3:r=10",
        "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0[v]", "-map", "[v]",
        "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def test_detects_two_cuts_on_textured_scenes(three_scene_video):
    cuts = detect_scene_changes(three_scene_video, threshold=0.4)
    assert len(cuts) == 2
    assert abs(cuts[0] - 3.0) < 0.5
    assert abs(cuts[1] - 6.0) < 0.5


def test_high_threshold_detects_fewer(three_scene_video):
    # seuil très strict -> au plus autant de coupures qu'au seuil normal
    assert len(detect_scene_changes(three_scene_video, threshold=0.95)) <= 2
