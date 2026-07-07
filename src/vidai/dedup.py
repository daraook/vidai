"""Déduplication des keyframes visuellement quasi identiques.

Objectif : économiser des tokens côté agent. Sur un plan fixe (talking-head,
diaporama), le filet `max_gap` produit des images redondantes. On calcule une
signature perceptuelle (dHash) par candidat et on fusionne ceux trop proches
du dernier gardé — leur intervalle de temps est absorbé par la keyframe
précédente (le texte reste intégral, seule l'image redondante disparaît).

Les keyframes `start` et `scene_change` sont protégées (jamais supprimées) :
un changement de plan porte, par définition, une information visuelle nouvelle.

Sans dépendance : la signature vient d'une micro-extraction ffmpeg 9×8 en
niveaux de gris (72 octets), transformée en dHash 64 bits en Python pur.
"""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .ffmpeg_utils import ffmpeg_path
from .keyframes import Keyframe

_HASH_W = 9  # largeur (comparaisons horizontales -> 8 bits/ligne)
_HASH_H = 8  # hauteur (8 lignes) -> 64 bits

# Sondes ffmpeg concurrentes (72 octets chacune, indépendantes) ; même borne
# que frames._MAX_WORKERS pour ne pas saturer les petites machines.
_MAX_WORKERS = min(4, os.cpu_count() or 1)

_PROTECTED = frozenset({"start", "scene_change"})


def frame_signature(video_path: Path, t: float) -> int | None:
    """dHash 64 bits de la frame à `t`, ou None si l'extraction échoue."""
    cmd = [
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-ss", f"{max(t, 0.0):.3f}", "-i", str(video_path),
        "-frames:v", "1", "-vf", f"scale={_HASH_W}:{_HASH_H},format=gray",
        "-f", "rawvideo", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    px = proc.stdout
    if len(px) != _HASH_W * _HASH_H:
        return None
    bits = 0
    for row in range(_HASH_H):
        base = row * _HASH_W
        for col in range(_HASH_W - 1):
            bits = (bits << 1) | (1 if px[base + col] < px[base + col + 1] else 0)
    return bits


def hamming(a: int, b: int) -> int:
    """Distance de Hamming entre deux hashes (nombre de bits différents)."""
    return (a ^ b).bit_count()


def dedup_keyframes(
    video_path: Path,
    keyframes: list[Keyframe],
    *,
    max_distance: int = 6,
) -> list[Keyframe]:
    """Retire les keyframes visuellement quasi identiques à la précédente gardée.

    `max_distance` : seuil de Hamming ; <= => considérées identiques (fusion).
    Les frames protégées (start/scene_change) sont toujours conservées.
    """
    # Signatures indépendantes → calcul parallèle ; la passe de fusion, elle,
    # reste séquentielle (chaque décision dépend de la dernière keyframe gardée).
    if len(keyframes) > 1:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            sigs = list(pool.map(lambda kf: frame_signature(video_path, kf.t), keyframes))
    else:
        sigs = [frame_signature(video_path, kf.t) for kf in keyframes]

    kept: list[Keyframe] = []
    last_sig: int | None = None
    for kf, sig in zip(keyframes, sigs, strict=True):
        if kf.reason in _PROTECTED or last_sig is None or sig is None:
            kept.append(kf)
            last_sig = sig if sig is not None else last_sig
            continue
        if hamming(sig, last_sig) > max_distance:
            kept.append(kf)
            last_sig = sig
        # sinon : quasi identique -> on la fusionne (absorbée par le span précédent)
    return kept
