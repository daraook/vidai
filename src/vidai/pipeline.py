"""Orchestration du pipeline complet : source -> output.json (timeline synchronisée).

download -> audio -> transcription (au mot) -> scènes -> sélection keyframes
-> extraction frames -> agrégation (timeline + transcript).
100% CPU. Chaque étape est un module pur ; ici on les enchaîne + logs + nettoyage.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .aggregate import build_output
from .audio import extract_audio
from .dedup import dedup_keyframes
from .download import (
    VideoInfo,
    download_clip,
    is_local_source,
    probe_meta,
    resolve_source,
)
from .errors import VidAIError
from .ffmpeg_utils import has_audio, probe_duration, probe_media
from .frames import extract_frames
from .keyframes import Keyframe, select_keyframes
from .scenes import detect_scene_changes
from .transcribe import Segment, Transcript, filter_speech, offset_transcript, transcribe

Window = tuple[float, float]
Log = Callable[[str], None]


@dataclass
class PipelineOptions:
    url: str
    outdir: Path
    model: str = "base"
    language: str | None = None
    markdown: bool = False
    keep_video: bool = False
    cookies: str | None = None
    scene_threshold: float = 0.4
    max_gap_s: float = 5.0
    min_gap_s: float = 1.0
    frame_format: str = "jpg"  # "jpg" | "png"
    frame_width: int = 1568     # plafond du plus grand côté des frames (px) ; 0 = source intacte
    dedup: bool = True
    dedup_distance: int = 6
    visual_only: bool = False       # ignorer l'audio (musique/parasite) -> timeline visuelle
    max_no_speech: float = 0.85     # filtre les segments non-parlés (musique) ; >=1.0 = off
    transcript_only: bool = False   # produire le transcript sans extraire d'images (phase 1)
    frames_at: list[float] | None = None  # extraire uniquement ces timestamps (phase 2)
    clips: list[Window] | None = None     # ne traiter que ces fenêtres [a, b]


def _log(msg: str) -> None:
    """Progression sur stderr (stdout réservé au chemin final pour les agents)."""
    print(f"[vidai] {msg}", file=sys.stderr, flush=True)


def _safe_unlink(path: Path) -> None:
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _clear_frames_dir(outdir: Path) -> None:
    """Repart d'un dossier frames propre (évite des kf_* résiduels d'un run précédent)."""
    shutil.rmtree(outdir / "frames", ignore_errors=True)


def run_pipeline(opts: PipelineOptions, *, log: Log = _log) -> Path:
    """Exécute le pipeline complet et retourne le chemin de output.json."""
    outdir = opts.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    _clear_frames_dir(outdir)

    if not opts.transcript_only:
        if opts.frame_width:
            log(
                f"Frames plafonnées à {opts.frame_width}px (plus grand côté, sans upscale) pour "
                "limiter le coût en tokens côté agent. --frame-width 0 = résolution source. "
                "Seuils/tokens variables selon le modèle consommateur ; voir README."
            )
        else:
            log(
                "Frames en résolution source (--frame-width 0) : qualité maximale, "
                "coût en tokens plus élevé côté agent consommateur."
            )

    # URL + --clip (sans --frames-at) : téléchargement PARTIEL des plages seulement.
    if opts.clips and not is_local_source(opts.url) and not opts.frames_at:
        return _run_range_mode(opts, log=log)

    return _run_full_mode(opts, log=log)


def _run_full_mode(opts: PipelineOptions, *, log: Log) -> Path:
    """Source complète (fichier local ou téléchargement intégral), fenêtres par seek."""
    outdir = opts.outdir
    log(f"Source : {opts.url}")
    info = resolve_source(opts.url, outdir, cookies=opts.cookies)
    origine = "fichier local" if info.is_local else "téléchargée"
    log(f"    ✓ {info.title} [{info.platform}] ({info.duration:.0f}s) — {origine}")

    assert info.path is not None  # le mode complet produit toujours un fichier
    probe = probe_media(info.path)  # une seule passe ffmpeg : durée + présence d'audio
    duration = info.duration if info.duration > 0 else probe.duration
    if duration <= 0:
        raise VidAIError("Impossible de déterminer la durée de la vidéo (fichier illisible ?).")
    windows = _compute_windows(opts.clips, duration)
    if opts.clips:
        total = sum(b - a for a, b in windows)
        log(f"Fenêtres --clip : {len(windows)} intervalle(s), {total:.0f}s sur {duration:.0f}s")

    temps: list[Path] = []
    if _delete_source_after(opts, info):
        temps.append(info.path)
    elif opts.transcript_only and not info.is_local and not opts.keep_video:
        log(
            f"Vidéo conservée ({info.path.name}) : c'est la phase 1 d'un triage — "
            "la phase 2 (--frames-at) la réutilisera sans re-télécharger."
        )
    try:
        transcript = _transcribe_windows(
            info, opts, windows, temps, source_has_audio=probe.has_audio, log=log
        )
        keyframes = _build_keyframes(info, opts, windows, duration, log=log)
        frame_paths = _extract_or_skip(info.path, keyframes, opts, log=log)
        log("Agrégation → timeline + transcript")
        config = _base_config(opts) | {"clips": _clips_cfg(windows, opts)}
        json_path = build_output(
            outdir, info, keyframes, frame_paths, transcript, config, write_markdown=opts.markdown
        )
    finally:
        for p in temps:
            _safe_unlink(p)
    log(f"Terminé : {json_path}")
    return json_path


def _run_range_mode(opts: PipelineOptions, *, log: Log) -> Path:
    """URL + --clip : ne télécharge que les plages (pistes séparées, 0-based), recale en absolu."""
    outdir = opts.outdir
    log(f"Source : {opts.url} (téléchargement partiel des plages)")
    meta = probe_meta(opts.url, cookies=opts.cookies)
    duration = meta.duration if meta.duration > 0 else max(b for _, b in opts.clips)
    windows = _compute_windows(opts.clips, duration)
    total = sum(b - a for a, b in windows)
    log(f"    ✓ {meta.title} [{meta.platform}] — {len(windows)} plage(s), {total:.0f}s ciblés")

    want_audio = not opts.visual_only
    height = _clip_stream_height(opts.frame_format, opts.frame_width)
    all_kf: list[Keyframe] = []
    segments: list[Segment] = []
    frame_paths: list[Path] = []
    temps: list[Path] = []
    language = "?"
    running = 1

    try:
        for i, (a, b) in enumerate(windows):
            tag = "vidéo+audio" if want_audio else "vidéo"
            log(f"Plage {a:.0f}-{b:.0f}s : téléchargement fragmenté ({tag})")
            clip = download_clip(
                opts.url, outdir, a, b, i,
                cookies=opts.cookies, want_audio=want_audio, height=height,
            )
            temps.append(clip.video_path)
            if clip.audio_path:
                temps.append(clip.audio_path)
            clen = probe_duration(clip.video_path)

            scenes = detect_scene_changes(clip.video_path, threshold=opts.scene_threshold)
            kf_local = select_keyframes(
                scenes, start=0.0, end=clen, max_gap_s=opts.max_gap_s, min_gap_s=opts.min_gap_s
            )
            if opts.dedup and not opts.transcript_only:
                kf_local = dedup_keyframes(
                    clip.video_path, kf_local, max_distance=opts.dedup_distance
                )

            if not opts.transcript_only:
                frame_paths.extend(
                    extract_frames(
                        clip.video_path, outdir, [kf.t for kf in kf_local],
                        fmt=opts.frame_format, start_index=running, width=opts.frame_width,
                    )
                )
            running += len(kf_local)
            all_kf.extend(Keyframe(kf.t + a, kf.reason, kf.window_end + a) for kf in kf_local)

            if want_audio and clip.audio_path and has_audio(clip.audio_path):
                wav = extract_audio(clip.audio_path, outdir, name=f"audio_{i}.wav")
                temps.append(wav)
                tr = offset_transcript(
                    transcribe(wav, model=opts.model, language=opts.language), a
                )
                tr, _ = filter_speech(tr, opts.max_no_speech)
                segments.extend(tr.segments)
                if tr.language not in ("?", "none"):
                    language = tr.language

        all_kf.sort(key=lambda kf: kf.t)
        segments.sort(key=lambda s: s.start)
        transcript = Transcript(segments, language if segments else _empty_lang(opts))
        log(f"    ✓ {len(all_kf)} keyframe(s), {len(segments)} segment(s) transcrit(s)")

        config = _base_config(opts) | {"clips": _clips_cfg(windows, opts), "partial_download": True}
        log("Agrégation → timeline + transcript")
        json_path = build_output(
            outdir, meta, all_kf, frame_paths, transcript, config, write_markdown=opts.markdown
        )
    finally:
        for p in temps:
            if not (opts.keep_video and p.suffix.lower() in _VIDEO_SUFFIXES):
                _safe_unlink(p)
    log(f"Terminé : {json_path}")
    return json_path


_VIDEO_SUFFIXES = frozenset({".mp4", ".mkv", ".webm", ".m4v", ".mov"})


def _delete_source_after(opts: PipelineOptions, info: VideoInfo) -> bool:
    """True si la vidéo téléchargée doit être supprimée en fin de run (mode complet).

    Jamais pour un fichier local (source de l'utilisateur), jamais avec
    --keep-video, et jamais en --transcript-only : c'est la phase 1 d'un triage,
    la phase 2 (--frames-at) réutilise la vidéo sans re-télécharger.
    """
    return (
        info.path is not None
        and not info.is_local
        and not opts.keep_video
        and not opts.transcript_only
    )


def _clip_stream_height(frame_format: str, frame_width: int) -> int:
    """Hauteur du flux téléchargé en mode plage, alignée sur la qualité demandée.

    Un flux 720p plafonne le grand côté à 1280px : suffisant seulement si le cap
    `--frame-width` reste ≤ 1280 en JPG. PNG, cap 0 (= source) ou cap > 1280
    exigent du 1080p pour tenir la promesse de qualité (voir ADR-012).
    """
    wants_hd = frame_format == "png" or not frame_width or frame_width > 1280
    return 1080 if wants_hd else 720


def _empty_lang(opts: PipelineOptions) -> str:
    return "none" if opts.visual_only else "?"


def _clips_cfg(windows: list[Window], opts: PipelineOptions) -> list[list[float]] | None:
    return [[a, b] for a, b in windows] if opts.clips else None


def _extract_or_skip(
    video_path: Path | None, keyframes: list[Keyframe], opts: PipelineOptions, *, log: Log
) -> list[Path]:
    """Extrait les frames, sauf en --transcript-only (positions candidates seules)."""
    if opts.transcript_only:
        log(f"Transcript-only : {len(keyframes)} position(s) candidate(s), 0 image extraite")
        return []
    assert video_path is not None
    cap = f"≤{opts.frame_width}px" if opts.frame_width else "résolution source"
    log(f"Extraction de {len(keyframes)} keyframe(s) ({opts.frame_format}, plus grand côté {cap})")
    times = [kf.t for kf in keyframes]
    return extract_frames(
        video_path, opts.outdir, times, fmt=opts.frame_format, width=opts.frame_width
    )


def _base_config(opts: PipelineOptions) -> dict:
    """Config commune reportée dans output.json."""
    return {
        "model": opts.model,
        "scene_threshold": opts.scene_threshold,
        "max_gap_s": opts.max_gap_s,
        "min_gap_s": opts.min_gap_s,
        "frame_format": opts.frame_format,
        "frame_width": opts.frame_width,
        "dedup": opts.dedup,
        "dedup_distance": opts.dedup_distance,
        "visual_only": opts.visual_only,
        "transcript_only": opts.transcript_only,
        "frames_at": opts.frames_at,
    }


def _compute_windows(clips: list[Window] | None, duration: float) -> list[Window]:
    """Normalise les fenêtres : clamp à [0, durée], tri, fusion des chevauchements.

    Sans `--clip` : une seule fenêtre couvrant toute la vidéo.
    """
    if not clips:
        return [(0.0, duration)]
    valid = sorted(
        (max(0.0, a), min(duration, b)) for a, b in clips if min(duration, b) > max(0.0, a)
    )
    if not valid:
        raise VidAIError("Aucun intervalle --clip valide dans la durée de la vidéo.")
    merged = [valid[0]]
    for a, b in valid[1:]:
        la, lb = merged[-1]
        if a <= lb:  # chevauchement/adjacence -> fusion
            merged[-1] = (la, max(lb, b))
        else:
            merged.append((a, b))
    return merged


def _transcribe_windows(
    info: VideoInfo,
    opts: PipelineOptions,
    windows: list[Window],
    temps: list[Path],
    *,
    source_has_audio: bool,
    log: Log,
) -> Transcript:
    """Transcrit chaque fenêtre (temps recalés en absolu) et fusionne. Alimente `temps`."""
    if opts.visual_only:
        log("Audio ignoré (--visual-only) → timeline purement visuelle")
        return Transcript(segments=[], language="none")
    if info.path is None or not source_has_audio:
        log("Aucune piste audio détectée → timeline purement visuelle")
        return Transcript(segments=[], language="none")

    log(f"Transcription au mot (faster-whisper '{opts.model}', CPU int8)")
    segments: list[Segment] = []
    language = "?"
    total_removed = 0
    for i, (a, b) in enumerate(windows):
        ap = extract_audio(info.path, opts.outdir, start=a, duration=b - a, name=f"audio_{i}.wav")
        temps.append(ap)
        tr = offset_transcript(transcribe(ap, model=opts.model, language=opts.language), a)
        tr, removed = filter_speech(tr, opts.max_no_speech)
        total_removed += removed
        segments.extend(tr.segments)
        if tr.language not in ("?", "none"):
            language = tr.language
    segments.sort(key=lambda s: s.start)
    transcript = Transcript(segments=segments, language=language)
    note = f" (−{total_removed} segment(s) non-parlé(s)/musique filtré(s))" if total_removed else ""
    log(
        f"    ✓ {len(segments)} segment(s), {len(transcript.all_words())} mot(s), "
        f"langue={language}{note}"
    )
    return transcript


def _build_keyframes(
    info: VideoInfo, opts: PipelineOptions, windows: list[Window], duration: float, *, log: Log
) -> list[Keyframe]:
    """Positions manuelles (--frames-at) OU sélection auto par fenêtre (scènes+filet+dédup)."""
    if opts.frames_at:
        kfs = [
            Keyframe(min(max(t, 0.0), duration), "manual", duration) for t in sorted(opts.frames_at)
        ]
        log(f"Keyframes manuelles (--frames-at) : {len(kfs)} position(s)")
        return kfs

    assert info.path is not None
    log(f"Détection des changements de plan (seuil {opts.scene_threshold})")
    all_kfs: list[Keyframe] = []
    total_scenes = 0
    for a, b in windows:
        scenes = detect_scene_changes(
            info.path, threshold=opts.scene_threshold, start=a, duration=b - a
        )
        total_scenes += len(scenes)
        all_kfs.extend(
            select_keyframes(
                scenes, start=a, end=b, max_gap_s=opts.max_gap_s, min_gap_s=opts.min_gap_s
            )
        )
    all_kfs.sort(key=lambda kf: kf.t)
    log(f"    ✓ {total_scenes} changement(s) de plan")

    if opts.dedup and not opts.transcript_only:
        before = len(all_kfs)
        all_kfs = dedup_keyframes(info.path, all_kfs, max_distance=opts.dedup_distance)
        log(f"    ✓ dédup visuelle : {before} → {len(all_kfs)} (−{before - len(all_kfs)})")
    return all_kfs
