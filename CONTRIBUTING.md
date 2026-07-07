# Contribuer à VidAI

Merci de vouloir contribuer ! Voici les règles du jeu — courtes et strictes.

## Mise en place

```bash
git clone https://github.com/daraook/vidai && cd vidai
python -m venv .venv && . .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
vidai --check   # vérifie ffmpeg (bundlé), yt-dlp, faster-whisper
```

## Avant d'ouvrir une PR

1. **Lint** : `ruff check src tests` doit passer sans erreur.
2. **Tests** : `pytest -q` doit être vert. Toute nouvelle fonctionnalité ou correction
   de bug arrive **avec ses tests**.
3. **Validation réelle** : si le changement touche le pipeline (download, transcription,
   frames), valide-le sur une vidéo réelle courte et documente le résultat dans la PR.

## Principes non négociables

- **100% CPU** : aucune dépendance GPU, jamais. La cible tourne sur des machines sans
  carte graphique.
- **Zéro dépendance système obligatoire** : ffmpeg est résolu via `imageio-ffmpeg`
  d'abord, système en fallback. Ne jamais supposer un ffmpeg installé.
- **Erreurs explicites** : pas d'exception avalée, messages actionnables, codes retour
  clairs (0 succès, 1 erreur pipeline, 2 erreur d'usage).
- **Qualité par défaut transparente** : tout réglage qui affecte la qualité de sortie
  (ex. `--frame-width`) doit être documenté, reporté dans `output.json` (`config`) et
  visible dans les logs. Pas de dégradation silencieuse.
- **Model-agnostic** : la sortie est consommée par n'importe quel agent/modèle. Ne pas
  optimiser pour un modèle précis.
- **Style** : Python ≥ 3.10, lignes ≤ 100, annotations de types, modules purs et
  testables, docstrings en français.

## Structure

```
src/vidai/
  cli.py         # parsing + validation des options
  pipeline.py    # orchestration (mode complet + mode plages)
  download.py    # résolution source : fichier local ou yt-dlp
  audio.py       # extraction WAV 16 kHz mono
  transcribe.py  # faster-whisper CPU int8, timestamps au mot
  scenes.py      # détection de changements de plan (ffmpeg)
  keyframes.py   # sélection des instants (start/scene/max_gap)
  dedup.py       # fusion des images quasi identiques (dHash)
  frames.py      # extraction des images (cap de résolution)
  aggregate.py   # output.json + output.md
  ffmpeg_utils.py, doctor.py, errors.py
```

## Signaler un bug

Ouvre une issue avec le template — inclure la commande exacte, l'OS, la sortie de
`vidai --check` et les logs stderr. Pour une faille de sécurité, voir
[SECURITY.md](SECURITY.md) (pas d'issue publique).
