"""Interface ligne de commande : `vidai <source> [options]`.

stdout : dernière ligne = chemin absolu de output.json (pour parsing par un agent).
stderr : logs de progression.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import VidAIError
from .pipeline import PipelineOptions, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vidai",
        description="Transforme une vidéo (URL ou fichier local) en {texte, image, timestamp} "
        "exploitable par un agent IA. 100% CPU, sans GPU.",
    )
    p.add_argument(
        "url",
        metavar="SOURCE",
        nargs="?",
        help="URL (YouTube, TikTok, Instagram, X, Vimeo…) OU chemin d'un fichier vidéo local",
    )
    p.add_argument(
        "-o", "--outdir", default="vidai-out", help="Dossier de sortie (défaut: vidai-out)"
    )
    p.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium"],
        help="Modèle Whisper (défaut: base). Plus grand = plus précis mais plus lent en CPU.",
    )
    p.add_argument(
        "--lang", default=None, help="Forcer la langue (code ISO, ex: fr, en). Défaut: auto."
    )
    p.add_argument(
        "--markdown", action="store_true", help="Écrire aussi output.md (lecture humaine)."
    )
    p.add_argument("--keep-video", action="store_true", help="Conserver la vidéo téléchargée.")
    p.add_argument(
        "--png",
        action="store_true",
        help="Frames en PNG sans perte (défaut: JPG, plus léger). Le cap --frame-width "
        "s'applique aussi au PNG : pour la pleine résolution, ajouter --frame-width 0.",
    )
    p.add_argument(
        "--frame-width",
        type=int,
        default=1568,
        metavar="PX",
        help="Plafonne le plus grand côté des frames à PX px (downscale seul, jamais d'upscale) "
        "pour réduire le coût en tokens côté agent (défaut: 1568). 0 = résolution source. "
        "Seuils/coût exacts variables selon le modèle consommateur (voir README).",
    )
    p.add_argument(
        "--max-gap",
        type=float,
        default=5.0,
        help="Filet de sécurité : au moins 1 image toutes les N s (défaut: 5).",
    )
    p.add_argument(
        "--min-gap",
        type=float,
        default=1.0,
        help="Distance minimale entre 2 images pour éviter les doublons (défaut: 1).",
    )
    p.add_argument(
        "--scene-threshold",
        type=float,
        default=0.4,
        help="Sensibilité détection de plan, ]0,1[ (bas=sensible, défaut: 0.4).",
    )
    p.add_argument(
        "--no-dedup",
        action="store_true",
        help="Désactiver la fusion des images visuellement quasi identiques.",
    )
    p.add_argument(
        "--dedup-distance",
        type=int,
        default=6,
        help="Seuil de similarité visuelle (Hamming, 0-64 ; plus bas = plus strict, défaut: 6).",
    )
    p.add_argument(
        "--visual-only",
        action="store_true",
        help="Ignorer l'audio (ex: musique parasite sur vidéo de code) → timeline visuelle seule.",
    )
    p.add_argument(
        "--max-no-speech",
        type=float,
        default=0.85,
        help="Filtre les segments non-parlés/musique (proba 0-1 ; 1.0 = off ; défaut: 0.85).",
    )
    p.add_argument(
        "--transcript-only",
        action="store_true",
        help="Phase 1 triage : transcript + positions candidates, SANS extraire d'image. "
        "La vidéo téléchargée est conservée (source.mp4) pour la phase 2 (--frames-at).",
    )
    p.add_argument(
        "--frames-at",
        default=None,
        metavar="T1,T2,…",
        help="Phase 2 triage : extraire uniquement ces timestamps (secondes, séparés par virgule).",
    )
    p.add_argument(
        "--clip",
        action="append",
        default=None,
        metavar="A-B",
        help="Ne traiter que l'intervalle A-B (répétable). Temps en SS, MM:SS ou HH:MM:SS. "
        "Ex: --clip 10-30 --clip 1:30-2:15",
    )
    p.add_argument(
        "--cookies", default=None, help="Fichier cookies pour contenu nécessitant login."
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Supprimer les logs de progression (stderr). Les erreurs restent affichées.",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Vérifier les dépendances (ffmpeg, yt-dlp, whisper) et quitter.",
    )
    p.add_argument("--version", action="version", version=f"vidai {__version__}")
    return p


def _parse_timestamps(raw: str) -> list[float]:
    """Parse '12,45,90.5' -> [12.0, 45.0, 90.5]. Lève ValueError si invalide."""
    out: list[float] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.append(_parse_time_token(part))
    if not out:
        raise ValueError("aucun timestamp valide")
    return out


def _parse_time_token(tok: str) -> float:
    """Parse un instant : 'SS', 'SS.s', 'MM:SS' ou 'HH:MM:SS' -> secondes (float)."""
    tok = tok.strip()
    if ":" not in tok:
        return float(tok)
    parts = tok.split(":")
    if len(parts) > 3:
        raise ValueError(f"format temporel invalide : {tok!r}")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + float(p)
    return seconds


def _parse_clips(raw_list: list[str]) -> list[tuple[float, float]]:
    """Parse ['10-30', '1:30-2:15'] -> [(10.0, 30.0), (90.0, 135.0)]."""
    clips: list[tuple[float, float]] = []
    for raw in raw_list:
        if "-" not in raw:
            raise ValueError(f"intervalle invalide (attendu A-B) : {raw!r}")
        a_str, b_str = raw.split("-", 1)
        a, b = _parse_time_token(a_str), _parse_time_token(b_str)
        if b <= a:
            raise ValueError(f"intervalle vide ou inversé : {raw!r}")
        clips.append((a, b))
    return clips


def _validate(args: argparse.Namespace, frames_at, clips) -> str | None:
    """Contrôles de cohérence des options ; retourne un message d'erreur ou None."""
    if frames_at and clips:
        return "--frames-at et --clip ne se combinent pas (positions explicites OU fenêtres)."
    if not 0.0 < args.scene_threshold < 1.0:
        return "--scene-threshold doit être dans ]0, 1[."
    if args.max_gap <= 0:
        return "--max-gap doit être > 0."
    if args.min_gap < 0:
        return "--min-gap doit être >= 0."
    if not 0.0 <= args.max_no_speech <= 1.0:
        return "--max-no-speech doit être dans [0, 1]."
    if not 0 <= args.dedup_distance <= 64:
        return "--dedup-distance doit être dans [0, 64]."
    if args.frame_width < 0:
        return "--frame-width doit être >= 0 (0 = résolution source)."
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.check:
        from .doctor import check_dependencies, format_report

        statuses = check_dependencies()
        print(format_report(statuses), file=sys.stderr)
        return 0 if all(s.ok for s in statuses) else 1

    if not args.url:
        print("[vidai] ERREUR : SOURCE manquante (URL ou fichier). Voir --help.", file=sys.stderr)
        return 2

    frames_at = None
    if args.frames_at:
        try:
            frames_at = _parse_timestamps(args.frames_at)
        except ValueError as e:
            print(f"[vidai] ERREUR : --frames-at invalide ({e}).", file=sys.stderr)
            return 2

    clips = None
    if args.clip:
        try:
            clips = _parse_clips(args.clip)
        except ValueError as e:
            print(f"[vidai] ERREUR : --clip invalide ({e}).", file=sys.stderr)
            return 2

    problem = _validate(args, frames_at, clips)
    if problem:
        print(f"[vidai] ERREUR : {problem}", file=sys.stderr)
        return 2

    opts = PipelineOptions(
        url=args.url,
        outdir=Path(args.outdir).resolve(),
        model=args.model,
        language=args.lang,
        markdown=args.markdown,
        keep_video=args.keep_video,
        cookies=args.cookies,
        scene_threshold=args.scene_threshold,
        max_gap_s=args.max_gap,
        min_gap_s=args.min_gap,
        frame_format="png" if args.png else "jpg",
        frame_width=args.frame_width,
        dedup=not args.no_dedup,
        dedup_distance=args.dedup_distance,
        visual_only=args.visual_only,
        max_no_speech=args.max_no_speech,
        transcript_only=args.transcript_only,
        frames_at=frames_at,
        clips=clips,
    )

    try:
        json_path = (
            run_pipeline(opts, log=lambda _msg: None) if args.quiet else run_pipeline(opts)
        )
    except VidAIError as e:
        print(f"[vidai] ERREUR : {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\n[vidai] interrompu.", file=sys.stderr)
        return 130

    # stdout : chemin final, seul, pour capture par un agent.
    print(str(json_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
