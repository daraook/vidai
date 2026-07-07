"""Tests dédup : distance de Hamming (pur) + fusion sur plan fixe (intégration)."""

import subprocess

import pytest

from vidai.dedup import dedup_keyframes, frame_signature, hamming
from vidai.ffmpeg_utils import ffmpeg_path
from vidai.keyframes import Keyframe


def test_hamming_counts_differing_bits():
    assert hamming(0b1010, 0b1010) == 0
    assert hamming(0b1010, 0b1000) == 1
    assert hamming(0b0000, 0b1111) == 4


@pytest.fixture
def static_then_change(tmp_path):
    """6 s d'un plan fixe (mires SMPTE) puis 3 s d'un autre plan fixe (rgbtestsrc)."""
    path = tmp_path / "v.mp4"
    cmd = [
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "smptebars=s=320x240:d=6:r=10",
        "-f", "lavfi", "-i", "rgbtestsrc=s=320x240:d=3:r=10",
        "-filter_complex", "[0][1]concat=n=2:v=1:a=0[v]", "-map", "[v]",
        "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def test_signature_stable_on_static_scene(static_then_change):
    # même plan à 1s et 4s -> signatures identiques (distance nulle)
    s1 = frame_signature(static_then_change, 1.0)
    s2 = frame_signature(static_then_change, 4.0)
    assert s1 is not None and s2 is not None
    assert hamming(s1, s2) == 0


def test_signature_differs_across_scenes(static_then_change):
    s_smpte = frame_signature(static_then_change, 2.0)
    s_rgb = frame_signature(static_then_change, 7.5)
    assert hamming(s_smpte, s_rgb) > 6


def test_dedup_collapses_static_run(static_then_change):
    keyframes = [
        Keyframe(0.0, "start", 9.0),
        Keyframe(2.0, "max_gap", 9.0),
        Keyframe(4.0, "max_gap", 9.0),
        Keyframe(7.5, "max_gap", 9.0),
    ]
    kept = dedup_keyframes(static_then_change, keyframes, max_distance=6)
    # les 2 max_gap dans le plan fixe fusionnent ; le changement de plan reste
    assert [(kf.t, kf.reason) for kf in kept] == [(0.0, "start"), (7.5, "max_gap")]


def test_dedup_preserves_scene_changes(static_then_change):
    # une frame scene_change n'est jamais supprimée, même si visuellement proche
    keyframes = [Keyframe(0.0, "start", 9.0), Keyframe(2.0, "scene_change", 9.0)]
    kept = dedup_keyframes(static_then_change, keyframes, max_distance=6)
    assert kept == keyframes
