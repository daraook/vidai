"""Vérification des dépendances (`vidai --check`).

Contrôle que ffmpeg (bundlé ou système), yt-dlp et faster-whisper sont
opérationnels, avant même de lancer un traitement.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class DepStatus:
    name: str
    ok: bool
    detail: str


def check_dependencies() -> list[DepStatus]:
    """Retourne l'état de chaque dépendance critique."""
    return [_check_ffmpeg(), _check_ytdlp(), _check_faster_whisper()]


def _check_ffmpeg() -> DepStatus:
    try:
        from .ffmpeg_utils import ffmpeg_path

        path = ffmpeg_path()
        proc = subprocess.run([path, "-version"], capture_output=True, text=True)
        first = proc.stdout.splitlines()[0] if proc.stdout else "version inconnue"
        origin = "bundlé" if "imageio" in path else "système"
        return DepStatus("ffmpeg", proc.returncode == 0, f"{origin} · {first}")
    except Exception as e:  # noqa: BLE001
        return DepStatus("ffmpeg", False, str(e))


def _check_ytdlp() -> DepStatus:
    try:
        import yt_dlp

        return DepStatus("yt-dlp", True, f"v{yt_dlp.version.__version__}")
    except Exception as e:  # noqa: BLE001
        return DepStatus("yt-dlp", False, f"non importable : {e}")


def _check_faster_whisper() -> DepStatus:
    try:
        import faster_whisper  # noqa: F401

        return DepStatus("faster-whisper", True, "importable (modèle téléchargé au 1er usage)")
    except Exception as e:  # noqa: BLE001
        return DepStatus("faster-whisper", False, f"non importable : {e}")


def format_report(statuses: list[DepStatus]) -> str:
    """Rapport lisible ; ✓/✗ par dépendance."""
    lines = ["Vérification des dépendances VidAI :"]
    for s in statuses:
        mark = "✓" if s.ok else "✗"
        lines.append(f"  {mark} {s.name:16} {s.detail}")
    all_ok = all(s.ok for s in statuses)
    lines.append("")
    lines.append("Tout est prêt." if all_ok else "Des dépendances manquent — voir ci-dessus.")
    return "\n".join(lines)
