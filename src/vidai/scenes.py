"""Détection des changements de plan via ffmpeg.

Utilise le filtre `select='gt(scene,threshold)'` + `showinfo` : ffmpeg calcule
un score de différence entre frames consécutives (0 = identique, 1 = tout change)
et `showinfo` journalise le `pts_time` des frames retenues. On parse ces temps.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .errors import FFmpegError
from .ffmpeg_utils import ffmpeg_path

_PTS_RE = re.compile(r"pts_time:(\d+(?:\.\d+)?)")


def detect_scene_changes(
    video_path: Path,
    *,
    threshold: float = 0.4,
    start: float | None = None,
    duration: float | None = None,
) -> list[float]:
    """Retourne les timestamps ABSOLUS (secondes) des changements de plan détectés.

    `threshold` ∈ ]0,1[ : plus bas = plus sensible. Défaut 0.4 (ADR-007).
    `start`/`duration` : restreint l'analyse à une fenêtre ; les temps retournés
    sont ramenés en absolu (on ajoute `start`).
    Ne lève pas si aucune scène détectée (retourne []) ; lève FFmpegError si
    ffmpeg échoue réellement.
    """
    cmd = [ffmpeg_path(), "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", f"{max(start, 0.0):.3f}"]  # seek avant -i -> pts remis à ~0
    cmd += ["-i", str(video_path)]
    if duration is not None:
        cmd += ["-t", f"{max(duration, 0.0):.3f}"]
    cmd += [
        "-an",  # ignore l'audio
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        raise FFmpegError(
            f"ffmpeg a échoué (détection de scènes). Code {proc.returncode}.\n"
            f"stderr: {proc.stderr.strip()[:2000]}"
        )

    # showinfo journalise sur stderr ; une ligne par frame retenue.
    offset = start or 0.0
    times = [float(m) + offset for m in _PTS_RE.findall(proc.stderr)]
    return sorted(set(times))
