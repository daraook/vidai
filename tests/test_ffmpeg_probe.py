"""Tests d'intégration des sondes ffmpeg : présence d'audio et durée."""

import subprocess

import pytest

from vidai.ffmpeg_utils import ffmpeg_path, has_audio, probe_duration, probe_media


def _make(path, *, with_audio):
    inputs = ["-f", "lavfi", "-i", "testsrc=s=160x120:d=2:r=10"]
    if with_audio:
        inputs += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", *inputs,
           "-pix_fmt", "yuv420p", "-shortest", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


@pytest.fixture
def video_with_audio(tmp_path):
    return _make(tmp_path / "with.mp4", with_audio=True)


@pytest.fixture
def video_muted(tmp_path):
    return _make(tmp_path / "muted.mp4", with_audio=False)


def test_has_audio_true(video_with_audio):
    assert has_audio(video_with_audio) is True


def test_has_audio_false(video_muted):
    assert has_audio(video_muted) is False


def test_probe_duration_close_to_2s(video_muted):
    assert abs(probe_duration(video_muted) - 2.0) < 0.5


def test_probe_duration_missing_file_returns_zero(tmp_path):
    assert probe_duration(tmp_path / "nope.mp4") == 0.0


def test_probe_media_single_pass(video_with_audio):
    probe = probe_media(video_with_audio)
    assert probe.has_audio is True
    assert abs(probe.duration - 2.0) < 0.5


def test_probe_media_missing_file(tmp_path):
    probe = probe_media(tmp_path / "nope.mp4")
    assert probe.duration == 0.0
    assert probe.has_audio is False


def test_link_is_stale_detection(tmp_path):
    from vidai.ffmpeg_utils import _link_is_stale

    real = tmp_path / "real-v7.1"
    real.write_bytes(b"x" * 10)

    ok_link = tmp_path / "ffmpeg_ok"
    ok_link.symlink_to(real)
    assert _link_is_stale(ok_link, real) is False

    other = tmp_path / "real-v6.0"
    other.write_bytes(b"y" * 10)
    wrong_target = tmp_path / "ffmpeg_wrong"
    wrong_target.symlink_to(other)
    assert _link_is_stale(wrong_target, real) is True

    gone = tmp_path / "gone"
    gone.write_bytes(b"z")
    broken = tmp_path / "ffmpeg_broken"
    broken.symlink_to(gone)
    gone.unlink()
    assert _link_is_stale(broken, real) is True

    copy_same = tmp_path / "ffmpeg_copy"
    copy_same.write_bytes(b"x" * 10)  # même taille -> considérée à jour
    assert _link_is_stale(copy_same, real) is False
    copy_stale = tmp_path / "ffmpeg_copy2"
    copy_stale.write_bytes(b"x" * 4)  # taille différente -> périmée
    assert _link_is_stale(copy_stale, real) is True

    missing = tmp_path / "ffmpeg_absent"
    assert _link_is_stale(missing, real) is False  # absent = pas périmé, juste à créer
