"""Agrégation finale : keyframes + transcription -> output.json (+ output.md).

Produit la timeline frame-centrée (chaque keyframe possède le texte de son span)
et le transcript au mot, conformément au modèle cible (ADR-006/008).
"""

from __future__ import annotations

import json
from pathlib import Path

from .download import VideoInfo
from .keyframes import Keyframe
from .transcribe import Transcript


def _fmt_ts(seconds: float) -> str:
    """Formate des secondes en mm:ss (ou hh:mm:ss au-delà d'une heure)."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_timeline(
    keyframes: list[Keyframe],
    frame_paths: list[Path],
    transcript: Transcript,
    *,
    outdir: Path,
) -> list[dict]:
    """Construit la liste des entrées de timeline.

    Chaque entrée = {index, t, span, frame, reason, text}. `span = [t_i, span_end)`
    où `span_end = min(t_{i+1}, window_end_i)` : le span est borné par la fin de
    la fenêtre de la keyframe, donc ne traverse jamais un trou entre deux `--clip`.
    """
    words = transcript.all_words()
    timeline: list[dict] = []
    for i, kf in enumerate(keyframes):
        next_t = keyframes[i + 1].t if i + 1 < len(keyframes) else float("inf")
        span_end = max(min(next_t, kf.window_end), kf.t)
        text = " ".join(w.word for w in words if kf.t <= w.start < span_end).strip()
        frame_rel = None
        if i < len(frame_paths):
            frame_rel = frame_paths[i].relative_to(outdir).as_posix()
        timeline.append(
            {
                "index": i,
                "t": round(kf.t, 3),
                "span": [round(kf.t, 3), round(span_end, 3)],
                "frame": frame_rel,
                "reason": kf.reason,
                "text": text,
            }
        )
    return timeline


def build_output(
    outdir: Path,
    info: VideoInfo,
    keyframes: list[Keyframe],
    frame_paths: list[Path],
    transcript: Transcript,
    config: dict,
    *,
    write_markdown: bool = False,
) -> Path:
    """Écrit output.json (et output.md si demandé). Retourne le chemin du JSON."""
    timeline = build_timeline(keyframes, frame_paths, transcript, outdir=outdir)

    payload = {
        "source": {
            "url": info.url,
            "title": info.title,
            "platform": info.platform,
            "duration": round(info.duration, 3),
            "language": transcript.language,
        },
        "config": config,
        "timeline": timeline,
        "transcript": [
            {
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text,
                "words": [
                    {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
                    for w in seg.words
                ],
            }
            for seg in transcript.segments
        ],
    }

    json_path = outdir / "output.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if write_markdown:
        _write_markdown(outdir, payload)

    return json_path


def _write_markdown(outdir: Path, payload: dict) -> None:
    src = payload["source"]
    lines = [
        f"# {src['title']}",
        "",
        f"- **Source** : {src['url']}",
        f"- **Plateforme** : {src['platform']}",
        f"- **Durée** : {_fmt_ts(src['duration'])}",
        f"- **Langue** : {src['language']}",
        "",
        "---",
        "",
    ]
    for kf in payload["timeline"]:
        stamp = f"`{_fmt_ts(kf['span'][0])} → {_fmt_ts(kf['span'][1])}`"
        lines.append(f"### {stamp} · _{kf['reason']}_")
        if kf.get("frame"):
            lines.append(f"![kf {kf['index']}]({kf['frame']})")
        lines.append("")
        lines.append(kf["text"] or "_(pas de parole sur ce plan)_")
        lines.append("")
    (outdir / "output.md").write_text("\n".join(lines), encoding="utf-8")
