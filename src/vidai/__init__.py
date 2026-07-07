"""VidAI — rend n'importe quelle vidéo en ligne exploitable par un agent IA, sans GPU."""

__version__ = "0.1.2"

from .errors import DownloadError, FFmpegError, TranscriptionError, VidAIError

__all__ = ["VidAIError", "DownloadError", "TranscriptionError", "FFmpegError", "__version__"]
