# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ·
versionnage [SemVer](https://semver.org/lang/fr/).

## [Unreleased]

## [0.1.2] — 2026-07-07

### Modifié
- `--transcript-only` conserve désormais automatiquement la vidéo téléchargée
  (`source.mp4`) : c'est la phase 1 d'un triage, la phase 2 (`--frames-at`) la
  réutilise sans re-télécharger. `--keep-video` n'est plus nécessaire dans ce
  workflow.
- Aide CLI : `--png` précise que le cap `--frame-width` s'applique aussi au PNG
  (pleine résolution : ajouter `--frame-width 0`).

## [0.1.1] — 2026-07-07

### Corrigé
- Windows : les URI `file://` (ex. `file:///C:/…`) sont converties correctement
  (`url2pathname`).
- Extraction de frames : comportement uniforme quelle que soit la version de
  ffmpeg quand un timestamp tombe à/au-delà de la fin de la vidéo (retry en
  amont, puis erreur explicite avec le détail ffmpeg — jamais de chemin
  retourné sans fichier).
- `install.sh` : conformité shellcheck (SC2015).

## [0.1.0] — 2026-07-07

Première version publique.

### Ajouté
- Pipeline complet URL/fichier local → `output.json` : téléchargement (yt-dlp,
  1800+ sites), extraction audio, transcription horodatée **au mot**
  (faster-whisper, CPU int8), détection de changements de plan, sélection de
  keyframes (scènes + filet `--max-gap` + dédup perceptuelle dHash), extraction
  d'une image par keyframe, agrégation en timeline synchronisée
  `{texte, image, timestamp}`.
- **100% CPU** : aucun GPU requis ; ffmpeg bundlé via `imageio-ffmpeg`
  (fallback système), zéro dépendance système obligatoire au-delà de Python.
- Économie de tokens côté agent : `--transcript-only` / `--frames-at` (triage en
  2 phases), `--clip A-B` répétable avec **téléchargement partiel** des plages
  sur URL, `--visual-only`, filtre musique `--max-no-speech`,
  `--frame-width` (cap du plus grand côté des frames, défaut 1568 px,
  `0` = résolution source — compromis coût/qualité documenté et reporté dans
  `config`).
- Sorties : `output.json` (`source`, `config`, `timeline[]`, `transcript[]`),
  frames `frames/kf_NNNN.{jpg,png}`, `--markdown` optionnel.
- Robustesse : fichiers locaux jamais supprimés, vidéos muettes → timeline
  visuelle, messages d'erreur actionnables, codes retour stables (0/1/2),
  `--quiet`, `vidai --check`.
- Extraction de frames et signatures dédup **parallélisées** (borné à 4 workers).
- Installation sans PyPI : `install.sh` (Linux/macOS) et `install.ps1` (Windows),
  interactifs (aucune action sans confirmation), `--yes`/`-Yes` pour la CI.
- CI multi-OS (Linux/macOS/Windows), Python 3.10 → 3.14, test du wheel installé
  via pipx, workflow de release GitHub.

[Unreleased]: https://github.com/daraook/vidai/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/daraook/vidai/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/daraook/vidai/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/daraook/vidai/releases/tag/v0.1.0
