import pytest

from vidai.errors import VidAIError
from vidai.pipeline import _compute_windows


def test_no_clips_is_full_video():
    assert _compute_windows(None, 120.0) == [(0.0, 120.0)]


def test_clips_sorted_and_clamped():
    # non triés + dépassement de la durée -> triés et clampés
    assert _compute_windows([(90.0, 200.0), (10.0, 30.0)], 120.0) == [(10.0, 30.0), (90.0, 120.0)]


def test_overlapping_clips_merged():
    assert _compute_windows([(10.0, 40.0), (30.0, 60.0)], 120.0) == [(10.0, 60.0)]


def test_adjacent_clips_merged():
    assert _compute_windows([(10.0, 30.0), (30.0, 50.0)], 120.0) == [(10.0, 50.0)]


def test_disjoint_clips_kept_separate():
    assert _compute_windows([(10.0, 30.0), (50.0, 70.0)], 120.0) == [(10.0, 30.0), (50.0, 70.0)]


def test_all_clips_out_of_range_raises():
    with pytest.raises(VidAIError):
        _compute_windows([(200.0, 300.0)], 120.0)


def test_clip_stream_height_follows_quality_request():
    from vidai.pipeline import _clip_stream_height

    # JPG + cap ≤ 1280 : un flux 720p (grand côté 1280) suffit
    assert _clip_stream_height("jpg", 1024) == 720
    assert _clip_stream_height("jpg", 1280) == 720
    # cap au-delà de 1280, cap 0 (= source) ou PNG : il faut du 1080p
    assert _clip_stream_height("jpg", 1568) == 1080
    assert _clip_stream_height("jpg", 0) == 1080
    assert _clip_stream_height("png", 1024) == 1080


def test_delete_source_after_rules():
    from pathlib import Path

    from vidai.download import VideoInfo
    from vidai.pipeline import PipelineOptions, _delete_source_after

    def info(local):
        return VideoInfo(path=Path("/x/source.mp4"), url="u", title="t",
                         platform="p", duration=10.0, is_local=local)

    def opts(**kw):
        return PipelineOptions(url="u", outdir=Path("/x"), **kw)

    # téléchargée, run normal -> supprimée
    assert _delete_source_after(opts(), info(local=False)) is True
    # fichier local de l'utilisateur -> jamais supprimé
    assert _delete_source_after(opts(), info(local=True)) is False
    # --keep-video -> conservée
    assert _delete_source_after(opts(keep_video=True), info(local=False)) is False
    # --transcript-only (phase 1 de triage) -> conservée pour la phase 2
    assert _delete_source_after(opts(transcript_only=True), info(local=False)) is False
