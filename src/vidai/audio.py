"""Extraction audio : vidéo -> WAV mono 16 kHz PCM (format attendu par Whisper).

Peut extraire une fenêtre temporelle `[start, start+duration]` pour ne transcrire
qu'une portion (option --clip), ce qui économise le temps CPU sur les longs formats.
"""

from __future__ import annotations

from pathlib import Path

from .ffmpeg_utils import run_ffmpeg


def extract_audio(
    video_path: Path,
    outdir: Path,
    *,
    start: float | None = None,
    duration: float | None = None,
    name: str = "audio.wav",
) -> Path:
    """Extrait l'audio en WAV 16 kHz mono. Retourne le chemin.

    `start`/`duration` (secondes) : fenêtre optionnelle ; None = tout l'audio.
    `name` : nom du fichier de sortie (utile pour plusieurs fenêtres).
    """
    audio_path = outdir / name
    args: list[str] = []
    if start is not None:
        args += ["-ss", f"{max(start, 0.0):.3f}"]  # seek avant -i = rapide
    args += ["-i", str(video_path)]
    if duration is not None:
        args += ["-t", f"{max(duration, 0.0):.3f}"]
    args += [
        "-vn",              # pas de vidéo
        "-ac", "1",         # mono
        "-ar", "16000",     # 16 kHz
        "-acodec", "pcm_s16le",
        str(audio_path),
    ]
    run_ffmpeg(args, context="extraction audio")
    return audio_path
