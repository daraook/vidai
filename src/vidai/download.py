"""Résolution de la source vidéo : fichier local ou téléchargement yt-dlp.

yt-dlp couvre 1800+ sites (YouTube, TikTok, Instagram, X, Vimeo…). Un chemin
local (ou file://) est accepté directement, sans téléchargement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from .errors import DownloadError
from .ffmpeg_utils import ffmpeg_dir_for_ytdlp, probe_duration


@dataclass
class VideoInfo:
    """Résultat de la résolution : fichier source + métadonnées.

    `path` vaut None quand il n'y a pas de fichier unique (mode plages, où seules
    des portions sont téléchargées séparément).
    """

    path: Path | None
    url: str
    title: str
    platform: str
    duration: float  # secondes ; 0.0 si inconnu
    is_local: bool = False  # True = source fournie par l'utilisateur (ne jamais supprimer)


def resolve_source(source: str, outdir: Path, *, cookies: str | None = None) -> VideoInfo:
    """Dispatcher : fichier local existant -> lecture directe, sinon téléchargement."""
    local = _as_local_path(source)
    if local is not None:
        return from_local_file(local)
    return download_video(source, outdir, cookies=cookies)


def is_local_source(source: str) -> bool:
    """True si `source` désigne un fichier local existant (et non une URL)."""
    return _as_local_path(source) is not None


def _as_local_path(source: str) -> Path | None:
    """Retourne un Path si `source` désigne un fichier local existant, sinon None."""
    if source.startswith("file://"):
        # url2pathname gère les spécificités d'OS (déquote, et sur Windows
        # transforme « /C:/x » en « C:\x » — un simple unquote laisse le / de tête).
        return Path(url2pathname(urlparse(source).path))
    # Une URL (http, https, ftp…) a un schéma : on ne la traite pas comme un fichier.
    if "://" in source:
        return None
    p = Path(source).expanduser()
    return p if p.is_file() else None


def from_local_file(path: Path) -> VideoInfo:
    """Construit un VideoInfo à partir d'un fichier local (aucun téléchargement)."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise DownloadError(f"Fichier introuvable : {path}")
    return VideoInfo(
        path=path,
        url=path.as_uri(),
        title=path.stem,
        platform="local",
        duration=probe_duration(path),
        is_local=True,
    )


def download_video(url: str, outdir: Path, *, cookies: str | None = None) -> VideoInfo:
    """Télécharge la meilleure vidéo dans `outdir`. Lève DownloadError sur échec.

    ffmpeg (bundlé) est fourni à yt-dlp pour le remux/merge éventuel.
    """
    try:
        import yt_dlp
    except ImportError as e:  # pragma: no cover
        raise DownloadError("yt-dlp non installé. `pip install yt-dlp`.") from e

    outdir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(outdir / "source.%(ext)s")

    opts = {
        "outtmpl": outtmpl,
        # Priorité à un résultat AVEC audio : merge vidéo+audio réel ; sinon,
        # repli sur un combiné h264 (TikTok classe "meilleur" un flux h265 dont
        # les métadonnées annoncent faussement de l'audio) ; sinon meilleur dispo.
        "format": "bv*+ba[acodec!=none]/b[vcodec*=264]/b",
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_dir_for_ytdlp(),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "restrictfilenames": True,
        "noplaylist": True,  # une URL de playlist -> uniquement la vidéo visée
    }
    if cookies:
        opts["cookiefile"] = cookies

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = Path(ydl.prepare_filename(info))
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(_friendly_download_error(str(e), bool(cookies))) from e
    except Exception as e:  # noqa: BLE001 — on remonte tout en erreur explicite
        raise DownloadError(f"Échec du téléchargement : {e}") from e

    # yt-dlp peut avoir remuxé vers .mp4 : on retrouve le fichier réel.
    filepath = _find_media(outdir, "source", filepath)
    if not filepath.exists():
        raise DownloadError(
            f"Téléchargement terminé mais fichier introuvable ({filepath})."
        )
    return _video_info(info, url, path=filepath)


def _video_info(info: dict, url: str, *, path: Path | None, is_local: bool = False) -> VideoInfo:
    """Construit un VideoInfo à partir d'un dict d'info yt-dlp."""
    return VideoInfo(
        path=path,
        url=url,
        title=info.get("title") or "sans-titre",
        platform=info.get("extractor_key") or info.get("extractor") or "inconnu",
        duration=float(info.get("duration") or 0.0),
        is_local=is_local,
    )


@dataclass
class ClipFiles:
    """Fichiers 0-based d'une plage téléchargée (pistes séparées, pas de merge)."""

    video_path: Path
    audio_path: Path | None


def probe_meta(url: str, *, cookies: str | None = None) -> VideoInfo:
    """Métadonnées (titre, plateforme, durée) sans télécharger (path=None)."""
    try:
        import yt_dlp
    except ImportError as e:  # pragma: no cover
        raise DownloadError("yt-dlp non installé. `pip install yt-dlp`.") from e
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    if cookies:
        opts["cookiefile"] = cookies
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(_friendly_download_error(str(e), bool(cookies))) from e
    return _video_info(info, url, path=None)


def download_clip(
    url: str,
    outdir: Path,
    abs_start: float,
    abs_end: float,
    index: int,
    *,
    cookies: str | None = None,
    want_audio: bool = True,
    height: int = 1080,
) -> ClipFiles:
    """Télécharge UNIQUEMENT la plage [abs_start, abs_end] (fragments DASH).

    Pistes séparées (vidéo seule, audio seule) pour éviter le merge ffmpeg —
    qui segfault sur seek profond. Les fichiers produits sont 0-based.
    """
    try:
        import yt_dlp
    except ImportError as e:  # pragma: no cover
        raise DownloadError("yt-dlp non installé. `pip install yt-dlp`.") from e

    outdir.mkdir(parents=True, exist_ok=True)
    try:
        video_path = _download_stream(
            url, outdir, f"clip{index}_v", f"bv*[height<={height}]/bv*/b",
            abs_start, abs_end, cookies,
        )
        audio_path: Path | None = None
        if want_audio:
            try:
                audio_path = _download_stream(
                    url, outdir, f"clip{index}_a", "ba/bestaudio", abs_start, abs_end, cookies
                )
            except (yt_dlp.utils.DownloadError, DownloadError):
                audio_path = None  # pas de piste audio séparée -> timeline visuelle
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(_friendly_download_error(str(e), bool(cookies))) from e

    return ClipFiles(video_path=video_path, audio_path=audio_path)


def _download_stream(
    url: str, outdir: Path, stem: str, fmt: str, a: float, b: float, cookies: str | None
) -> Path:
    """Télécharge une piste unique sur la plage [a,b] via le downloader natif (fragments)."""
    import yt_dlp
    from yt_dlp.utils import download_range_func

    opts = {
        "outtmpl": str(outdir / f"{stem}.%(ext)s"),
        "format": fmt,
        "download_ranges": download_range_func(None, [(a, b)]),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
    }
    if cookies:
        opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = _find_media(outdir, stem, Path(ydl.prepare_filename(info)))
    if not path.exists():
        raise DownloadError(f"Plage téléchargée mais fichier introuvable ({stem}).")
    return path


def _find_media(outdir: Path, stem: str, guessed: Path) -> Path:
    """Retrouve le média produit pour `stem` (extension éventuellement différente)."""
    if guessed.exists():
        return guessed
    cands = sorted(
        c for c in outdir.glob(f"{stem}.*")
        if c.suffix.lower() not in {".json", ".txt", ".part", ".ytdl"}
    )
    return cands[0] if cands else guessed


def _friendly_download_error(raw: str, has_cookies: bool) -> str:
    """Traduit une erreur yt-dlp en message actionnable."""
    low = raw.lower()
    if "private" in low or "login" in low or "sign in" in low:
        hint = "" if has_cookies else " Fournis un fichier cookies via --cookies."
        return f"Vidéo privée ou nécessitant une authentification.{hint}"
    if "drm" in low:
        return "Contenu protégé par DRM (Netflix, Disney+…) : non supporté."
    if "not available" in low or "removed" in low or "unavailable" in low:
        return "Vidéo indisponible (supprimée ou géo-bloquée)."
    if "unsupported url" in low or "no video" in low:
        return "URL non supportée ou ne pointant pas vers une vidéo."
    return f"Échec du téléchargement : {raw.strip()}"
