from vidai.download import _friendly_download_error


def test_private_video_message_suggests_cookies():
    msg = _friendly_download_error("ERROR: Private video. Sign in", has_cookies=False)
    assert "privée" in msg.lower()
    assert "--cookies" in msg


def test_private_video_no_cookie_hint_when_already_provided():
    msg = _friendly_download_error("ERROR: Private video", has_cookies=True)
    assert "--cookies" not in msg


def test_drm_message():
    assert "drm" in _friendly_download_error("This video is DRM protected", False).lower()


def test_unavailable_message():
    msg = _friendly_download_error("Video unavailable, removed by user", False)
    assert "indisponible" in msg.lower()
