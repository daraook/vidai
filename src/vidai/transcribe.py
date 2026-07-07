"""Transcription horodatée via faster-whisper (CPU int8, aucun GPU requis).

Timestamps au mot (word_timestamps) pour permettre de coller le bon texte à
la bonne image dans la timeline (ADR-008).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .errors import TranscriptionError


@lru_cache(maxsize=2)
def _load_model(model: str):
    """Charge (et met en cache) un WhisperModel CPU int8.

    Le cache évite de recharger le modèle à chaque fenêtre/clip transcrit.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise TranscriptionError(
            "faster-whisper non installé. `pip install faster-whisper`."
        ) from e
    return WhisperModel(model, device="cpu", compute_type="int8")


@dataclass
class Word:
    """Un mot transcrit avec ses bornes temporelles (secondes)."""

    start: float
    end: float
    word: str


@dataclass
class Segment:
    """Segment de transcription : bornes + texte + mots horodatés.

    `no_speech_prob` : probabilité estimée que le segment ne contienne PAS de
    parole (élevée sur de la musique/du silence) — sert à filtrer les
    hallucinations de paroles sur fond musical.
    """

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    no_speech_prob: float = 0.0


@dataclass
class Transcript:
    """Résultat de transcription : segments + langue détectée."""

    segments: list[Segment]
    language: str

    def all_words(self) -> list[Word]:
        """Tous les mots de la transcription, à plat et ordonnés."""
        return [w for seg in self.segments for w in seg.words]


def transcribe(
    audio_path: Path,
    *,
    model: str = "base",
    language: str | None = None,
) -> Transcript:
    """Transcrit `audio_path` en segments horodatés avec timestamps au mot.

    `model` : tiny/base/small/medium (téléchargé au 1er usage).
    `language` : code ISO (fr, en…) pour forcer ; None = auto-détection.
    Tourne en CPU avec quantification int8.
    """
    whisper = _load_model(model)
    try:
        seg_iter, info = whisper.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,       # coupe les silences -> segments plus propres
            word_timestamps=True,  # bornes par mot (ADR-008)
        )
        segments: list[Segment] = []
        for s in seg_iter:
            words = [
                Word(start=float(w.start), end=float(w.end), word=w.word.strip())
                for w in (s.words or [])
                if w.start is not None and w.end is not None
            ]
            segments.append(
                Segment(
                    start=float(s.start),
                    end=float(s.end),
                    text=s.text.strip(),
                    words=words,
                    no_speech_prob=float(getattr(s, "no_speech_prob", 0.0)),
                )
            )
    except Exception as e:  # noqa: BLE001
        raise TranscriptionError(f"Échec de la transcription : {e}") from e

    return Transcript(segments=segments, language=getattr(info, "language", None) or "?")


def offset_transcript(transcript: Transcript, delta: float) -> Transcript:
    """Décale tous les temps de `delta` secondes (fenêtre locale -> temps absolu)."""
    if delta == 0.0:
        return transcript
    segs = [
        Segment(
            start=s.start + delta,
            end=s.end + delta,
            text=s.text,
            words=[Word(w.start + delta, w.end + delta, w.word) for w in s.words],
            no_speech_prob=s.no_speech_prob,
        )
        for s in transcript.segments
    ]
    return Transcript(segments=segs, language=transcript.language)


def filter_speech(transcript: Transcript, max_no_speech: float) -> tuple[Transcript, int]:
    """Retire les segments dont `no_speech_prob` dépasse `max_no_speech`.

    Cible les hallucinations de paroles sur fond musical/silence. Retourne le
    transcript filtré et le nombre de segments retirés. `max_no_speech >= 1.0`
    ne filtre rien.
    """
    if max_no_speech >= 1.0:
        return transcript, 0
    kept = [s for s in transcript.segments if s.no_speech_prob <= max_no_speech]
    removed = len(transcript.segments) - len(kept)
    return Transcript(segments=kept, language=transcript.language), removed
