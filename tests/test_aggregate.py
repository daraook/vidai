import json

from vidai.aggregate import _fmt_ts, build_output, build_timeline
from vidai.download import VideoInfo
from vidai.keyframes import Keyframe
from vidai.transcribe import Segment, Transcript, Word


def test_fmt_ts_minutes_and_hours():
    assert _fmt_ts(75) == "01:15"
    assert _fmt_ts(35480) == "9:51:20"   # vidéo 9h : hh:mm:ss, pas 591:20
    assert _fmt_ts(0) == "00:00"


def _info(duration=12.0):
    return VideoInfo(path=None, url="http://x/v", title="Titre", platform="Test", duration=duration)


def _transcript():
    words = [
        Word(0.0, 0.5, "bonjour"),
        Word(0.5, 1.0, "monde"),
        Word(6.0, 6.5, "plan"),
        Word(6.5, 7.0, "deux"),
    ]
    seg = Segment(0.0, 7.0, "bonjour monde plan deux", words)
    return Transcript(segments=[seg], language="fr")


_CONFIG = {"model": "base", "frame_format": "jpg"}


def test_timeline_attaches_words_to_correct_span(tmp_path):
    keyframes = [Keyframe(0.0, "start", 12.0), Keyframe(5.0, "scene_change", 12.0)]
    frames = [tmp_path / "frames" / "kf_0001.jpg", tmp_path / "frames" / "kf_0002.jpg"]
    tl = build_timeline(keyframes, frames, _transcript(), outdir=tmp_path)

    assert tl[0]["span"] == [0.0, 5.0]
    assert tl[0]["text"] == "bonjour monde"
    assert tl[1]["span"] == [5.0, 12.0]
    assert tl[1]["text"] == "plan deux"
    assert tl[0]["frame"] == "frames/kf_0001.jpg"


def test_span_capped_at_window_end_across_clips(tmp_path):
    # deux fenêtres : [0,5] et [30,40]. Le span de la dernière keyframe de la
    # fenêtre 1 ne doit PAS traverser le trou jusqu'à 30.
    keyframes = [
        Keyframe(0.0, "start", 5.0),      # fenêtre 1, se termine à 5
        Keyframe(30.0, "start", 40.0),    # fenêtre 2, se termine à 40
    ]
    frames = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    tl = build_timeline(keyframes, frames, _transcript(), outdir=tmp_path)
    assert tl[0]["span"] == [0.0, 5.0]     # cappé à la fin de fenêtre 1, pas 30
    assert tl[1]["span"] == [30.0, 40.0]


def test_timeline_empty_text_when_no_speech(tmp_path):
    keyframes = [Keyframe(0.0, "start", 12.0), Keyframe(8.0, "scene_change", 12.0)]
    frames = [tmp_path / "frames" / "kf_0001.jpg", tmp_path / "frames" / "kf_0002.jpg"]
    tl = build_timeline(keyframes, frames, _transcript(), outdir=tmp_path)
    assert tl[1]["text"] == ""
    assert tl[1]["frame"] is not None


def test_build_output_full_json(tmp_path):
    keyframes = [Keyframe(0.0, "start", 12.0), Keyframe(5.0, "scene_change", 12.0)]
    frames = [tmp_path / "frames" / "kf_0001.jpg", tmp_path / "frames" / "kf_0002.jpg"]
    json_path = build_output(tmp_path, _info(), keyframes, frames, _transcript(), _CONFIG)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["source"]["language"] == "fr"
    assert len(data["timeline"]) == 2
    assert data["transcript"][0]["words"][0] == {"start": 0.0, "end": 0.5, "word": "bonjour"}


def test_build_output_writes_markdown(tmp_path):
    keyframes = [Keyframe(0.0, "start", 12.0)]
    frames = [tmp_path / "frames" / "kf_0001.jpg"]
    build_output(tmp_path, _info(), keyframes, frames, _transcript(), _CONFIG, write_markdown=True)
    md = (tmp_path / "output.md").read_text(encoding="utf-8")
    assert "bonjour monde" in md
    assert "frames/kf_0001.jpg" in md
