"""Extraction de frames : 1 image par timestamp retenu par la sélection de keyframes.

Nommage `kf_0001.<ext>`, indexé sur l'ordre de la timeline. JPG par défaut
(léger, ADR-009), PNG en option.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .errors import FFmpegError
from .ffmpeg_utils import run_ffmpeg

# Recul appliqué quand un seek à `t` ne produit aucune frame (t au-delà de la
# dernière frame décodable) : on retente légèrement en amont pour capturer la
# fin réelle de la vidéo plutôt que d'échouer.
_RETRY_BACKOFF_S = 0.5

# Invocations ffmpeg concurrentes (1 par frame). Chaque process est indépendant
# et écrit son propre fichier ; borné pour ne pas saturer les petites machines.
_MAX_WORKERS = min(4, os.cpu_count() or 1)


def _scale_filter(width: int) -> str:
    """Filtre ffmpeg : plafonne le plus GRAND côté à `width` px, ratio préservé, jamais d'upscale.

    `force_original_aspect_ratio=decrease` fait rentrer l'image dans la boîte
    `min(iw,width) × min(ih,width)` sans jamais l'agrandir : une image déjà plus
    petite que `width` sur ses deux côtés reste intacte. Cap sur le plus grand côté
    (et non la seule largeur) → le portrait vertical (TikTok, Reels) est traité aussi.
    """
    return f"scale='min(iw,{width})':'min(ih,{width})':force_original_aspect_ratio=decrease"


def _extract_one(
    video_path: Path, frame_path: Path, ts: float, *, ext: str, width: int | None
) -> str | None:
    """Extrait la frame à `ts` vers `frame_path`. Retourne None si l'invocation
    ffmpeg a réussi, sinon son message d'erreur (l'appelant décide de retenter).

    Un seek à/au-delà de la fin produit zéro frame : ffmpeg ≤ 7 sort en code 0
    sans créer de fichier, ffmpeg ≥ 8 sort en erreur (« Could not open encoder
    before EOF »). Les deux cas doivent mener au même retry en amont.
    """
    args = [
        "-ss", f"{max(ts, 0.0):.3f}",  # seek avant -i = rapide
        "-i", str(video_path),
        "-frames:v", "1",
    ]
    if width and width > 0:
        args += ["-vf", _scale_filter(width)]
    if ext == "jpg":
        args += ["-q:v", "2"]  # qualité JPEG élevée
    args.append(str(frame_path))
    try:
        run_ffmpeg(args, context=f"extraction frame @ {ts:.2f}s")
    except FFmpegError as e:
        return str(e)
    return None


def extract_frames(
    video_path: Path,
    outdir: Path,
    timestamps: list[float],
    *,
    fmt: str = "jpg",
    start_index: int = 1,
    width: int | None = None,
) -> list[Path]:
    """Extrait 1 frame par timestamp (secondes). Retourne les chemins, alignés sur l'index.

    `fmt` : "jpg" (défaut) ou "png". `start_index` : index de départ du nommage
    (utile pour concaténer plusieurs clips sans collision de noms).
    `width` : si défini et > 0, plafonne le plus grand côté des frames à cette
    valeur en px (downscale seul, jamais d'upscale) pour réduire le coût en tokens
    côté agent consommateur. `None`/0 = résolution source intacte.

    Invariant : chaque chemin retourné existe sur disque. Un seek à/au-delà de la
    fin de la vidéo (ffmpeg sort code 0 SANS créer de fichier) est retenté en
    amont ; s'il ne produit toujours rien, FFmpegError est levée.
    """
    ext = "png" if fmt == "png" else "jpg"
    frames_dir = outdir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    def _job(indexed: tuple[int, float]) -> Path:
        i, ts = indexed
        frame_path = frames_dir / f"kf_{i:04d}.{ext}"
        err = _extract_one(video_path, frame_path, ts, ext=ext, width=width)
        if not frame_path.exists():
            retry_ts = max(ts - _RETRY_BACKOFF_S, 0.0)
            err = _extract_one(video_path, frame_path, retry_ts, ext=ext, width=width) or err
        if not frame_path.exists():
            detail = f"\nDernière erreur ffmpeg : {err}" if err else ""
            raise FFmpegError(
                f"Aucune frame extraite à {ts:.2f}s (au-delà de la fin de la vidéo ?). "
                f"Vérifie le timestamp par rapport à la durée réelle.{detail}"
            )
        return frame_path

    jobs = list(enumerate(timestamps, start=start_index))
    if len(jobs) <= 1:
        return [_job(j) for j in jobs]
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        return list(pool.map(_job, jobs))  # ordre préservé, 1ʳᵉ erreur propagée
