"""Tests d'extraction de frames : cap de résolution, invariant d'existence, bords."""

import subprocess

import pytest

from vidai.errors import FFmpegError
from vidai.ffmpeg_utils import ffmpeg_path
from vidai.frames import _scale_filter, extract_frames


def _make_video(path, duration=4):
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc=s=320x240:d={duration}:r=10",
           "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@pytest.fixture
def video4s(tmp_path):
    return _make_video(tmp_path / "v.mp4")


def _dimensions(image_path):
    out = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-i", str(image_path)],
        capture_output=True, text=True, errors="replace",
    )
    return out.stderr


def test_scale_filter_caps_longest_side_without_upscale():
    f = _scale_filter(1568)
    # boîte min(source, cap) par côté + decrease → cap sur le plus grand côté, jamais d'upscale
    assert f == "scale='min(iw,1568)':'min(ih,1568)':force_original_aspect_ratio=decrease"


def test_scale_filter_respects_custom_width():
    assert "768" in _scale_filter(768)
    assert "force_original_aspect_ratio=decrease" in _scale_filter(768)


def test_extract_frames_all_paths_exist(video4s, tmp_path):
    paths = extract_frames(video4s, tmp_path, [0.0, 1.5, 3.0])
    assert len(paths) == 3
    assert all(p.exists() for p in paths)
    assert [p.name for p in paths] == ["kf_0001.jpg", "kf_0002.jpg", "kf_0003.jpg"]


def test_extract_frames_ordered_with_start_index(video4s, tmp_path):
    paths = extract_frames(video4s, tmp_path, [1.0, 2.0], start_index=5)
    assert [p.name for p in paths] == ["kf_0005.jpg", "kf_0006.jpg"]


def test_extract_at_exact_end_recovers_via_backoff(video4s, tmp_path):
    # à t=durée, ffmpeg sort code 0 SANS créer de fichier → le recul doit rattraper
    paths = extract_frames(video4s, tmp_path, [4.0])
    assert paths[0].exists()


def test_extract_far_beyond_end_never_silent(video4s, tmp_path):
    # Le comportement ffmpeg varie selon la version/build : ≤7 sort en code 0 sans
    # fichier, certains 8.x sortent en erreur, d'autres clampent sur la dernière
    # frame. L'invariant produit : soit une frame existe, soit erreur explicite —
    # jamais un chemin retourné sans fichier.
    try:
        paths = extract_frames(video4s, tmp_path, [10.0])
    except FFmpegError as e:
        assert "Aucune frame extraite" in str(e)
    else:
        assert paths[0].exists()


def test_extract_png_format(video4s, tmp_path):
    paths = extract_frames(video4s, tmp_path, [1.0], fmt="png")
    assert paths[0].suffix == ".png"
    assert paths[0].exists()


def test_extract_frames_width_cap_applied(video4s, tmp_path):
    # source 320x240, cap 160 → plus grand côté 160 (ratio préservé : 160x120)
    paths = extract_frames(video4s, tmp_path, [1.0], width=160)
    assert "160x120" in _dimensions(paths[0])


def test_extract_frames_no_upscale(video4s, tmp_path):
    # cap 9999 > source 320x240 → dimensions intactes
    paths = extract_frames(video4s, tmp_path, [1.0], width=9999)
    assert "320x240" in _dimensions(paths[0])
