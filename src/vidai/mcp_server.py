"""Serveur MCP : expose VidAI comme outils natifs pour un agent (stdio).

Trois outils calqués sur le workflow économe en tokens (voir README) :
  1. `video_transcript` — phase 1 : texte seul, 0 image (0 token d'image) ;
  2. `video_frames_at`  — phase 2 : uniquement les images demandées ;
  3. `video_timeline`   — pipeline complet {texte, image, timestamp}.
Plus `check_dependencies` pour diagnostiquer l'environnement.

Les outils retournent un résumé compact + le chemin de `output.json` : l'agent
lit le fichier (et ne charge que les frames utiles) au lieu de recevoir tout le
contenu dans la réponse — c'est le cœur de l'économie de tokens.

Lancement : `vidai-mcp` (nécessite l'extra `pip install "vidai[mcp]"`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import VidAIError
from .pipeline import PipelineOptions, run_pipeline

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "SDK MCP absent. Installe l'extra : pip install \"vidai[mcp]\" "
        "(ou pipx install \"vidai[mcp]\")."
    ) from e

# Note transparence (ADR-012) : le cap de résolution des frames est un compromis
# coût/qualité assumé et MODEL-AGNOSTIC — chaque modèle consommateur a sa propre
# tokenisation/seuils. Le réglage effectif est toujours reporté dans
# `output.json` (config.frame_width). Documenté dans chaque outil ci-dessous.
_FRAME_WIDTH_DOC = (
    "frame_width : plafonne le plus grand côté des frames en px (downscale seul, "
    "jamais d'upscale). Défaut 1568 (bon compromis coût/qualité, texte à l'écran "
    "lisible) ; 0 = résolution source (qualité max, coût token max). Le coût exact "
    "dépend du modèle qui lira les images."
)

mcp = FastMCP("vidai")


def _quiet(_msg: str) -> None:
    """Pas de logs stderr : le protocole MCP stdio doit rester propre."""


def _summary(json_path: Path) -> dict[str, Any]:
    """Résumé compact de output.json (l'agent lit le fichier pour le détail)."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    tl = data["timeline"]
    frames = [e["frame"] for e in tl if e.get("frame")]
    text_chars = sum(len(s["text"]) for s in data["transcript"])
    return {
        "output_json": str(json_path),
        "title": data["source"]["title"],
        "duration_s": data["source"]["duration"],
        "language": data["source"]["language"],
        "keyframes": len(tl),
        "frames_extracted": len(frames),
        "transcript_segments": len(data["transcript"]),
        "transcript_chars": text_chars,
        "frame_width_cap_px": data["config"]["frame_width"] or "source (aucun cap)",
        "how_to_read": (
            "Lis output.json : `timeline[]` (une entrée par keyframe : t, span, frame, "
            "text) se déroule comme la vidéo ; `transcript[]` donne le texte horodaté au "
            "mot. Ne charge une image de frames/ que si le texte ne suffit pas — chaque "
            "image coûte des tokens."
        ),
    }


def _parse_clips_arg(clips: list[str] | None) -> list[tuple[float, float]] | None:
    if not clips:
        return None
    from .cli import _parse_clips

    return _parse_clips(clips)


@mcp.tool()
def video_transcript(
    source: str,
    outdir: str,
    model: str = "base",
    language: str | None = None,
    clips: list[str] | None = None,
    keep_video: bool = True,
) -> dict[str, Any]:
    """Phase 1 (triage) : transcription horodatée SEULE, aucune image extraite — 0 token d'image.

    À utiliser en premier sur toute vidéo : lis le transcript, repère les instants
    où le visuel compte, puis appelle `video_frames_at` sur ces instants seulement.

    source : URL (YouTube, TikTok, X… tout ce que yt-dlp supporte) ou chemin local.
    outdir : dossier de sortie (output.json y sera écrit).
    model : tiny/base/small/medium (whisper CPU ; plus grand = plus précis, plus lent).
    language : code ISO pour forcer (ex. "fr") ; None = auto-détection.
    clips : intervalles "A-B" optionnels (ex. ["1:00-2:30"]) pour ne transcrire que
        ces plages — sur URL, seules ces plages sont téléchargées.
    keep_video : la vidéo téléchargée (source.mp4) est de toute façon conservée en
        transcript-only (phase 1 d'un triage) ; ce paramètre est gardé pour
        compatibilité d'appel. Une fois le triage fini, supprime source.mp4 si
        l'espace disque compte.
    """
    opts = PipelineOptions(
        url=source,
        outdir=Path(outdir).resolve(),
        model=model,
        language=language,
        transcript_only=True,
        keep_video=keep_video,
        clips=_parse_clips_arg(clips),
    )
    try:
        return _summary(run_pipeline(opts, log=_quiet))
    except VidAIError as e:
        return {"error": str(e)}


@mcp.tool()
def video_frames_at(
    source: str,
    outdir: str,
    timestamps: list[float],
    frame_width: int = 1568,
    png: bool = False,
) -> dict[str, Any]:
    """Phase 2 (triage) : extrait UNIQUEMENT les frames aux instants donnés (secondes).

    À utiliser après `video_transcript` : ne demande que les instants où l'image
    apporte quelque chose que le texte ne dit pas. Chaque frame coûtera des tokens
    au chargement.

    source : de préférence le fichier local conservé en phase 1 (ex. outdir/source.mp4)
        pour éviter un re-téléchargement ; une URL fonctionne aussi.
    timestamps : instants en secondes (ex. [12, 45.5, 90]).
    frame_width : plafonne le plus grand côté des frames en px (downscale seul,
        jamais d'upscale). Défaut 1568 — compromis coût/qualité raisonnable et
        model-agnostic ; 0 = résolution source (qualité max, coût max). Reporté
        dans output.json (config.frame_width).
    png : True = PNG sans perte (défaut JPG, plus léger).
    """
    opts = PipelineOptions(
        url=source,
        outdir=Path(outdir).resolve(),
        frames_at=list(timestamps),
        frame_width=frame_width,
        frame_format="png" if png else "jpg",
    )
    try:
        return _summary(run_pipeline(opts, log=_quiet))
    except VidAIError as e:
        return {"error": str(e)}


@mcp.tool()
def video_timeline(
    source: str,
    outdir: str,
    model: str = "base",
    language: str | None = None,
    clips: list[str] | None = None,
    visual_only: bool = False,
    frame_width: int = 1568,
    png: bool = False,
    max_gap_s: float = 5.0,
) -> dict[str, Any]:
    """Pipeline complet : timeline synchronisée {texte, image, timestamp} de la vidéo.

    Réserve cet outil aux vidéos courtes ou aux plages `clips` ciblées : sur un long
    format, préfère le duo `video_transcript` puis `video_frames_at` (beaucoup moins
    de tokens). Sur URL avec `clips`, seules les plages demandées sont téléchargées.

    source : URL ou fichier local. outdir : dossier de sortie.
    clips : intervalles "A-B" (ex. ["10-30", "1:30-2:15"]) pour ne traiter que ces plages.
    visual_only : True = ignorer l'audio (musique/parasite) → timeline purement visuelle.
    frame_width : cap du plus grand côté des frames en px, downscale seul. Défaut 1568
        (compromis coût/qualité model-agnostic) ; 0 = résolution source. Reporté dans
        output.json (config.frame_width).
    png : frames PNG sans perte (défaut JPG). max_gap_s : au moins 1 image toutes les N s.
    """
    opts = PipelineOptions(
        url=source,
        outdir=Path(outdir).resolve(),
        model=model,
        language=language,
        clips=_parse_clips_arg(clips),
        visual_only=visual_only,
        frame_width=frame_width,
        frame_format="png" if png else "jpg",
        max_gap_s=max_gap_s,
    )
    try:
        return _summary(run_pipeline(opts, log=_quiet))
    except VidAIError as e:
        return {"error": str(e)}


@mcp.tool()
def check_dependencies() -> dict[str, Any]:
    """Vérifie que ffmpeg (bundlé ou système), yt-dlp et faster-whisper sont opérationnels."""
    from .doctor import check_dependencies as _check

    statuses = _check()
    return {
        "ok": all(s.ok for s in statuses),
        "dependencies": [{"name": s.name, "ok": s.ok, "detail": s.detail} for s in statuses],
    }


def main() -> None:
    """Point d'entrée `vidai-mcp` : serveur MCP sur stdio."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
