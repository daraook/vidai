import pytest

from vidai.cli import _parse_clips, _parse_time_token, _parse_timestamps, _validate, build_parser


def _args(argv):
    return build_parser().parse_args(argv)


def test_validate_frames_at_and_clip_mutually_exclusive():
    args = _args(["x", "--frames-at", "1", "--clip", "0-5"])
    assert _validate(args, [1.0], [(0.0, 5.0)]) is not None


def test_validate_rejects_bad_scene_threshold():
    args = _args(["x", "--scene-threshold", "1.5"])
    assert _validate(args, None, None) is not None


def test_validate_accepts_sane_defaults():
    assert _validate(_args(["x"]), None, None) is None


def test_frame_width_default_and_override():
    assert _args(["x"]).frame_width == 1568
    assert _args(["x", "--frame-width", "768"]).frame_width == 768
    assert _args(["x", "--frame-width", "0"]).frame_width == 0  # 0 = résolution source


def test_validate_rejects_negative_frame_width():
    assert _validate(_args(["x", "--frame-width", "-1"]), None, None) is not None


def test_quiet_flag():
    assert _args(["x"]).quiet is False
    assert _args(["x", "--quiet"]).quiet is True
    assert _args(["x", "-q"]).quiet is True


def test_parse_timestamps_ok():
    assert _parse_timestamps("12,45,90.5") == [12.0, 45.0, 90.5]
    assert _parse_timestamps(" 3 , 7 ") == [3.0, 7.0]


def test_parse_time_token_formats():
    assert _parse_time_token("42") == 42.0
    assert _parse_time_token("1:30") == 90.0
    assert _parse_time_token("1:02:03") == 3723.0


def test_parse_clips_ok():
    assert _parse_clips(["10-30", "1:30-2:15"]) == [(10.0, 30.0), (90.0, 135.0)]


def test_parse_clips_invalid():
    with pytest.raises(ValueError):
        _parse_clips(["10"])          # pas de '-'
    with pytest.raises(ValueError):
        _parse_clips(["30-10"])       # inversé


def test_parse_timestamps_invalid():
    with pytest.raises(ValueError):
        _parse_timestamps("abc")
    with pytest.raises(ValueError):
        _parse_timestamps(",,")


def test_url_optional_allows_check():
    # --check sans SOURCE ne doit pas faire échouer le parsing
    args = build_parser().parse_args(["--check"])
    assert args.check is True
    assert args.url is None
