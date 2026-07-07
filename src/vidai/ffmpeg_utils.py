"""Résolution du binaire ffmpeg et helpers d'exécution.

Priorité : ffmpeg bundlé par imageio-ffmpeg (zéro install système), puis ffmpeg du PATH.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .errors import FFmpegError

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_STREAM_RE = re.compile(r"Stream #\d+:\d+.*: Audio:")


@dataclass(frozen=True)
class MediaProbe:
    """Métadonnées lues en UNE passe `ffmpeg -i` (durée + présence d'audio)."""

    duration: float  # secondes ; 0.0 si illisible
    has_audio: bool


@lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    """Chemin vers un binaire ffmpeg utilisable. Bundlé d'abord, système en fallback."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # imageio-ffmpeg absent ou binaire indisponible
        system = shutil.which("ffmpeg")
        if system:
            return system
        raise FFmpegError(
            "Aucun ffmpeg disponible. Installe le paquet `imageio-ffmpeg` "
            "(`pip install imageio-ffmpeg`) ou ffmpeg sur le système."
        ) from None


@lru_cache(maxsize=1)
def ffmpeg_dir_for_ytdlp() -> str:
    """Dossier contenant un exécutable nommé `ffmpeg`, à passer à yt-dlp.

    imageio-ffmpeg livre un binaire au nom versionné (ffmpeg-linux-x86_64-vX)
    que yt-dlp ne reconnaît pas. On expose donc un lien/copie nommé `ffmpeg`
    dans un dossier stable et on retourne ce dossier.
    """
    real = Path(ffmpeg_path())
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    if real.name == exe_name:
        return str(real.parent)  # déjà un ffmpeg système bien nommé

    cache_dir = Path(tempfile.gettempdir()) / "vidai-ffmpeg"
    cache_dir.mkdir(parents=True, exist_ok=True)
    link = cache_dir / exe_name
    if _link_is_stale(link, real):
        link.unlink(missing_ok=True)
    if not link.exists():
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError):  # droits/plateforme sans symlink
            shutil.copy2(real, link)
            link.chmod(0o755)
    return str(cache_dir)


def _link_is_stale(link: Path, real: Path) -> bool:
    """True si le lien/copie en cache ne correspond plus au binaire bundlé actuel.

    Arrive après mise à jour d'imageio-ffmpeg (binaire au nom versionné → nouvelle
    cible) : symlink pointant ailleurs, symlink cassé, ou copie de taille différente.
    """
    if not link.exists():
        return link.is_symlink()  # symlink cassé (cible disparue)
    if link.is_symlink():
        return link.resolve() != real.resolve()
    return link.stat().st_size != real.stat().st_size


def run_ffmpeg(args: list[str], *, context: str) -> None:
    """Exécute ffmpeg avec `args` (sans le binaire). Lève FFmpegError sur échec."""
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        raise FFmpegError(
            f"ffmpeg a échoué ({context}). Code {proc.returncode}.\n"
            f"stderr: {proc.stderr.strip()[:2000]}"
        )


def probe_media(path: Path) -> MediaProbe:
    """Sonde un média en UNE passe `ffmpeg -i` : durée + présence d'audio.

    `ffmpeg -i` sort en code ≠ 0 (faute de sortie déclarée) mais journalise les
    métadonnées sur stderr ; pas besoin de ffprobe. Durée 0.0 si illisible.
    """
    proc = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        errors="replace",
    )
    m = _DURATION_RE.search(proc.stderr)
    duration = 0.0
    if m:
        hours, minutes, seconds = int(m.group(1)), int(m.group(2)), float(m.group(3))
        duration = hours * 3600 + minutes * 60 + seconds
    return MediaProbe(duration=duration, has_audio=bool(_AUDIO_STREAM_RE.search(proc.stderr)))


def probe_duration(path: Path) -> float:
    """Durée d'un média en secondes (0.0 si illisible). Voir `probe_media`."""
    return probe_media(path).duration


def has_audio(path: Path) -> bool:
    """True si le média contient au moins une piste audio. Voir `probe_media`."""
    return probe_media(path).has_audio
