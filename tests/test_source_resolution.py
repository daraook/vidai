import pytest

from vidai.download import _as_local_path, _find_media, from_local_file, is_local_source
from vidai.errors import DownloadError


def test_is_local_source(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"\x00")
    assert is_local_source(str(f)) is True
    assert is_local_source("https://youtu.be/x") is False


def test_http_url_not_treated_as_local():
    assert _as_local_path("https://youtube.com/watch?v=x") is None
    assert _as_local_path("http://tiktok.com/x") is None


def test_existing_file_detected_as_local(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00")
    assert _as_local_path(str(f)) == f


def test_missing_local_path_is_none(tmp_path):
    assert _as_local_path(str(tmp_path / "nope.mp4")) is None


def test_file_uri_detected(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00")
    assert _as_local_path(f.as_uri()) == f


def test_from_local_file_builds_local_info(tmp_path):
    f = tmp_path / "myclip.mp4"
    f.write_bytes(b"\x00")
    info = from_local_file(f)
    assert info.is_local is True
    assert info.platform == "local"
    assert info.title == "myclip"


def test_from_local_file_missing_raises(tmp_path):
    with pytest.raises(DownloadError):
        from_local_file(tmp_path / "ghost.mp4")


def test_find_media_resolves_by_glob(tmp_path):
    # le fichier réel a une extension différente de celle devinée
    real = tmp_path / "clip0_v.mp4"
    real.write_bytes(b"\x00")
    got = _find_media(tmp_path, "clip0_v", tmp_path / "clip0_v.webm")
    assert got == real


def test_find_media_ignores_part_files(tmp_path):
    (tmp_path / "clip0_v.part").write_bytes(b"\x00")
    real = tmp_path / "clip0_v.mp4"
    real.write_bytes(b"\x00")
    assert _find_media(tmp_path, "clip0_v", tmp_path / "clip0_v.webm") == real
