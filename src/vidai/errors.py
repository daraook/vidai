"""Exceptions VidAI — explicites, jamais swallow (OWASP A10)."""


class VidAIError(Exception):
    """Erreur de base VidAI. Message actionnable attendu."""


class DownloadError(VidAIError):
    """Échec du téléchargement (vidéo privée, supprimée, géo-bloquée, DRM, URL invalide)."""


class FFmpegError(VidAIError):
    """Échec d'une opération ffmpeg (extraction audio ou frames)."""


class TranscriptionError(VidAIError):
    """Échec de la transcription."""
