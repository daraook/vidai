from vidai.keyframes import select_keyframes


def _times(kfs):
    return [round(kf.t, 3) for kf in kfs]


def _reasons(kfs):
    return [kf.reason for kf in kfs]


def test_union_start_scene_and_maxgap():
    kfs = select_keyframes([7.0], start=0.0, end=20.0, max_gap_s=5.0, min_gap_s=1.0)
    assert _times(kfs) == [0.0, 5.0, 7.0, 10.0, 15.0]
    assert _reasons(kfs) == ["start", "max_gap", "scene_change", "max_gap", "max_gap"]


def test_window_end_carried_on_each_keyframe():
    kfs = select_keyframes([], start=0.0, end=20.0, max_gap_s=5.0, min_gap_s=1.0)
    assert all(kf.window_end == 20.0 for kf in kfs)


def test_scene_change_wins_over_close_maxgap():
    kfs = select_keyframes([5.3], start=0.0, end=12.0, max_gap_s=5.0, min_gap_s=1.0)
    times = _times(kfs)
    assert 5.3 in times
    assert 5.0 not in times


def test_start_never_replaced_by_close_scene():
    kfs = select_keyframes([0.5], start=0.0, end=12.0, max_gap_s=5.0, min_gap_s=1.0)
    assert (kfs[0].t, kfs[0].reason) == (0.0, "start")
    assert 0.5 not in _times(kfs)


def test_windowed_start_offset():
    # fenêtre [10, 30] : première keyframe à 10 (start), filet à 15,20,25
    kfs = select_keyframes([], start=10.0, end=30.0, max_gap_s=5.0, min_gap_s=1.0)
    assert _times(kfs) == [10.0, 15.0, 20.0, 25.0]
    assert kfs[0].reason == "start"


def test_min_gap_dedup_between_scenes():
    kfs = select_keyframes([4.0, 4.5], start=0.0, end=20.0, max_gap_s=100.0, min_gap_s=1.0)
    assert _times(kfs) == [0.0, 4.0]
