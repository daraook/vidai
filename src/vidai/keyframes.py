"""Sélection des timestamps de keyframes (ADR-007), fenêtre par fenêtre.

Union de trois sources dans une fenêtre `[start, end]`, puis dédoublonnage :
  - `start`        : toujours un point au début de la fenêtre ;
  - `scene_change` : changements de plan détectés (visuel) ;
  - `max_gap`      : filet de sécurité, un point forcé tous les `max_gap_s`.
Quand deux points sont plus proches que `min_gap_s`, on garde le plus informatif
(start > scene_change > max_gap).

Chaque Keyframe retient `window_end` : la borne de fin de SA fenêtre. Ainsi un
span ne traverse jamais le trou entre deux intervalles `--clip` (ADR-010).
"""

from __future__ import annotations

from dataclasses import dataclass

# Priorité de conservation en cas de points trop proches.
_PRIORITY = {"start": 3, "scene_change": 2, "max_gap": 1, "manual": 3}


@dataclass
class Keyframe:
    """Un point de la timeline : instant, origine, et fin de sa fenêtre."""

    t: float
    reason: str
    window_end: float


def select_keyframes(
    scene_times: list[float],
    *,
    start: float,
    end: float,
    max_gap_s: float = 5.0,
    min_gap_s: float = 1.0,
) -> list[Keyframe]:
    """Retourne les keyframes de la fenêtre `[start, end]`, triées par `t`.

    `scene_times` : timestamps absolus des changements de plan (filtrés à la fenêtre).
    """
    if end <= start:
        return [Keyframe(start, "start", end)]

    candidates: list[tuple[float, str]] = [(start, "start")]

    for t in scene_times:
        if start < t < end:
            candidates.append((float(t), "scene_change"))

    if max_gap_s > 0:
        t = start + max_gap_s
        while t < end:
            candidates.append((round(t, 3), "max_gap"))
            t += max_gap_s

    candidates.sort(key=lambda c: (c[0], -_PRIORITY[c[1]]))

    kept: list[tuple[float, str]] = []
    for t, reason in candidates:
        if not kept:
            kept.append((t, reason))
            continue
        last_t, last_reason = kept[-1]
        if t - last_t >= min_gap_s:
            kept.append((t, reason))
        elif _PRIORITY[reason] > _PRIORITY[last_reason]:
            kept[-1] = (t, reason)
    return [Keyframe(t, reason, end) for t, reason in kept]
