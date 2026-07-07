from vidai.doctor import check_dependencies
from vidai.transcribe import Segment, Transcript, filter_speech


def _t():
    return Transcript(
        segments=[
            Segment(0.0, 2.0, "vraie parole", no_speech_prob=0.1),
            Segment(2.0, 4.0, "la la la (musique)", no_speech_prob=0.95),
            Segment(4.0, 6.0, "encore parole", no_speech_prob=0.3),
        ],
        language="fr",
    )


def test_filter_drops_high_no_speech():
    filtered, removed = filter_speech(_t(), max_no_speech=0.85)
    assert removed == 1
    assert [s.text for s in filtered.segments] == ["vraie parole", "encore parole"]


def test_filter_disabled_at_one():
    filtered, removed = filter_speech(_t(), max_no_speech=1.0)
    assert removed == 0
    assert len(filtered.segments) == 3


def test_doctor_all_present_in_this_env():
    # dans l'environnement de test, toutes les deps sont installées
    statuses = check_dependencies()
    assert all(s.ok for s in statuses), {s.name: s.detail for s in statuses if not s.ok}
