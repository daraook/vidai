from vidai.transcribe import Segment, Transcript, Word, offset_transcript


def _t():
    return Transcript(
        segments=[Segment(0.0, 2.0, "salut", [Word(0.0, 1.0, "salut")], no_speech_prob=0.2)],
        language="fr",
    )


def test_offset_transcript_shifts_all_times():
    out = offset_transcript(_t(), 100.0)
    seg = out.segments[0]
    assert seg.start == 100.0
    assert seg.end == 102.0
    assert seg.words[0].start == 100.0
    assert seg.words[0].end == 101.0
    assert seg.no_speech_prob == 0.2  # préservé


def test_offset_zero_is_noop_identity():
    t = _t()
    assert offset_transcript(t, 0.0) is t
