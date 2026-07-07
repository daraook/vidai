# VidAI

[![CI](https://github.com/daraook/vidai/actions/workflows/ci.yml/badge.svg)](https://github.com/daraook/vidai/actions/workflows/ci.yml)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![CPU only](https://img.shields.io/badge/GPU-non%20requis-orange.svg)

**Rends n'importe quelle vidéo en ligne exploitable par un agent IA — sans GPU.**

Les LLM ne « voient » pas une vidéo : ils traitent du texte (et des images fixes). VidAI comble ce trou. À partir d'une simple URL, il produit un jeu de données **`{texte, image, timestamp}`** qu'un agent (Claude Code, Codex, Openclaw, Hermès…) peut lire directement : transcription horodatée + une image extraite au bon instant pour chaque segment.

100% CPU. Aucune carte graphique requise. Un script d'installation et c'est prêt (ffmpeg bundlé).

## Pipeline
```
URL ──yt-dlp──▶ vidéo ──ffmpeg──▶ audio.wav ──faster-whisper──▶ transcription au mot
                                                                     │
                                              scènes + filet + dédup → keyframes
                                                                     │
                                                     ffmpeg (1 frame/keyframe)
                                                                     ▼
                              output.json  { source, config, timeline[], transcript[] }
```

## Installation

**Le plus simple — un seul script (vérifie et installe tout).** Il contrôle Python, propose
d'installer ce qui manque, puis installe l'outil. Il ne fait **rien sans te demander**.

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/daraook/vidai/main/install.sh | bash
```
```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/daraook/vidai/main/install.ps1 | iex
```

Le script vérifie **Python ≥ 3.10** (seule dépendance système obligatoire), propose `pipx`, et
installe VidAI depuis la dernière release GitHub (ou les sources en repli). Ajoute `--yes`
(bash) / `-Yes` (PowerShell) pour un mode non-interactif. `ffmpeg` système est **optionnel** —
VidAI en embarque un via `imageio-ffmpeg`.

<details>
<summary>Alternatives (manuel)</summary>

```bash
# A) pipx (environnement isolé, recommandé) — depuis les sources
pipx install "git+https://github.com/daraook/vidai.git"

# B) venv de dev
git clone https://github.com/daraook/vidai && cd vidai
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

# C) wheel d'une release
pipx install ./vidai-<version>-py3-none-any.whl
```
</details>

Aucune dépendance système obligatoire au-delà de Python : `yt-dlp`, `faster-whisper` et un
`ffmpeg` bundlé sont tirés automatiquement par le paquet.

## Usage
```bash
vidai "https://www.youtube.com/watch?v=..." -o ./out   # URL
vidai ./ma-video.mp4 -o ./out                           # fichier local
vidai "<url>" -o ./out --markdown --model small
```
L'entrée peut être une **URL** (toute plateforme yt-dlp) ou un **fichier local**.
Une source locale n'est jamais supprimée. Une vidéo muette produit une timeline
purement visuelle (transcription ignorée proprement).

### Options
| Option | Effet |
|---|---|
| `-o, --outdir` | Dossier de sortie (défaut `./vidai-out`) |
| `--model` | Modèle Whisper : `tiny`/`base`/`small`/`medium` (défaut `base`) |
| `--lang` | Forcer la langue (sinon auto-détection) |
| `--markdown` | Écrire aussi un `output.md` lisible humain |
| `--png` | Frames en PNG sans perte (défaut JPG, plus léger) |
| `--frame-width PX` | Plafonne le **plus grand côté** des frames à PX px (downscale seul, jamais d'upscale). Défaut `1568`. `0` = résolution source. Voir [Résolution des frames](#résolution-des-frames-coût-en-tokens-vs-qualité) |
| `--max-gap` | Filet : au moins 1 image toutes les N s (défaut 5) |
| `--scene-threshold` | Sensibilité détection de plan `]0,1[` (défaut 0.4) |
| `--no-dedup` | Désactiver la fusion des images quasi identiques |
| `--dedup-distance` | Seuil de similarité visuelle (Hamming 0-64, défaut 6 ; plus haut = plus agressif) |
| `--visual-only` | Ignorer l'audio (ex: musique sur vidéo de code) → timeline visuelle seule |
| `--max-no-speech` | Filtrer les segments non-parlés/musique (proba 0-1, défaut 0.85 ; 1.0 = off) |
| `--transcript-only` | Phase 1 triage : transcript + positions candidates, **sans** extraire d'image |
| `--frames-at "12,45"` | Phase 2 triage : extraire uniquement ces timestamps (secondes) |
| `--clip A-B` | Ne traiter que l'intervalle A-B (répétable). Temps en `SS`, `MM:SS` ou `HH:MM:SS` |
| `--keep-video` | Conserver la vidéo téléchargée |
| `--cookies` | Fichier cookies pour contenu nécessitant login |
| `-q, --quiet` | Supprimer les logs de progression (stderr) ; les erreurs restent affichées |
| `--check` | Vérifier les dépendances (ffmpeg, yt-dlp, whisper) et quitter |

### Workflow triage en deux phases (économie de tokens maximale)
```bash
# Phase 1 — texte seul, aucune image (0 token d'image).
# La vidéo téléchargée est conservée automatiquement (source.mp4) pour la phase 2.
vidai "<url>" -o ./out --transcript-only
#   → l'agent lit out/output.json (transcript horodaté), repère les instants clés

# Phase 2 — n'extraire QUE les images utiles, depuis la vidéo déjà locale
vidai ./out/source.mp4 -o ./out --frames-at "12,45,90"
```

### Ne traiter que des passages précis (longs formats)
```bash
vidai "<url>" -o ./out --clip 10-30 --clip 1:30-2:15
vidai "<url>" -o ./out --clip 8:32:00-8:34:00 --visual-only --png   # deep dans une vidéo 9h
```
Sur une **URL**, seules ces plages sont **téléchargées** (fragments DASH, pistes
séparées) — pas la vidéo entière. Exemple mesuré : cibler 2 min à 8h32 dans une
vidéo de 9h51 ne télécharge que **~13 Mo** (au lieu de plusieurs Go). Les
timestamps restent **absolus** et un span ne traverse jamais le trou entre deux `--clip`.

> **Format des temps** : `SS`, `MM:SS` ou `HH:MM:SS`. Attention : `8:32` = 8 min 32 s.
> Pour 8 h 32 min, écrire `8:32:00`.

### Audio musical / non pertinent
Une vidéo de code avec une chanson en fond : l'audio n'apporte rien.
```bash
vidai "<url>" -o ./out --visual-only    # ignore l'audio, timeline visuelle dense
```
Sinon, les hallucinations de paroles sur musique sont filtrées automatiquement
(`--max-no-speech`).

## Intégration agent : serveur MCP et skill

**Serveur MCP** — VidAI s'expose comme outils natifs pour tout client MCP
(Claude Code, autres agents) :

```bash
pip install "vidai[mcp]"      # ou pipx install "vidai[mcp]"
# côté client MCP, déclarer le serveur stdio :
#   { "command": "vidai-mcp" }
# exemple Claude Code :
claude mcp add vidai -- vidai-mcp
```

Outils exposés : `video_transcript` (phase 1, texte seul), `video_frames_at`
(phase 2, images ciblées), `video_timeline` (pipeline complet), `check_dependencies`.
Chaque outil retourne un **résumé compact + le chemin de `output.json`** — l'agent
lit le fichier et ne charge que les frames utiles (économie de tokens), et le
compromis `frame_width` est documenté dans la description même des outils.

**Skill** — [`skills/vidai/SKILL.md`](skills/vidai/SKILL.md) apprend à un agent
*quand et comment* utiliser VidAI sans gaspiller : triage 2 phases, `--clip`,
`--visual-only`, compromis résolution↔tokens, pièges connus. Pour Claude Code :

```bash
mkdir -p ~/.claude/skills && cp -r skills/vidai ~/.claude/skills/
```

## Économie de tokens (important pour les longs formats)
Le pipeline (download, audio, transcription, découpe) tourne **100% en local sur CPU
— zéro token LLM**. Whisper est un modèle local, pas une API. Traiter une vidéo de 3 h
ne coûte que du temps CPU.

Les tokens ne sont dépensés que lorsqu'un **agent lit la sortie**. Le texte est bon
marché ; **les images sont le vrai coût** (~500-1500 tokens chacune). Deux leviers :

1. **Dédup automatique** — les images visuellement identiques (plan fixe, talking-head)
   sont fusionnées ; le texte reste intégral. Règle via `--dedup-distance`.
2. **Triage texte-d'abord** (côté agent) — la sortie sépare `transcript` (cheap) des
   `frames` (référencées par chemin, chargées à la demande). Un agent lit d'abord le
   texte, repère les moments où l'image compte, puis ne charge **que** ces frames.
   → un 1 h se lit en ~15k tokens de texte + une poignée d'images ciblées.
3. **Plafond de résolution des frames** (`--frame-width`, ci-dessous) — moins de pixels
   par image = moins de tokens, sans toucher au nombre d'images ni au texte.

### Résolution des frames (coût en tokens vs qualité)

VidAI plafonne par défaut le **plus grand côté** de chaque frame à **1568 px**
(`--frame-width 1568`), sans jamais agrandir une image plus petite. C'est un compromis
**coût/qualité** assumé, et voici l'analyse complète — pour que le réglage soit un choix
éclairé, pas une surprise.

**Comment un modèle facture une image.** La plupart des modèles multimodaux découpent
l'image en tuiles et facturent un nombre de tokens ≈ proportionnel à la **surface en
pixels**, jusqu'à un **seuil de résolution** au-delà duquel le modèle **réduit lui-même**
l'image avant de la traiter. Concrètement :

- **Au-dessus du seuil du modèle** (grosses images 4K…), plafonner est **gratuit** en
  qualité : le modèle jetait ces pixels de toute façon.
- **En dessous du seuil**, il n'y a **pas de repas gratuit** : réduire les pixels réduit
  le détail réellement transmis au modèle. Le compromis coût↔qualité est direct.

**Pourquoi 1568 px par défaut.** C'est un point de redimensionnement courant chez de
nombreux modèles (au-delà, beaucoup réduisent d'eux-mêmes), le **texte à l'écran y reste
lisible**, et il coupe nettement le coût sur les sources 1080p/4K. Ordre de grandeur du
coût par frame 16:9 (formule à titre indicatif, ~surface/patch) :

| Plus grand côté | Dimensions ~16:9 | Effet |
|---|---|---|
| source (aucun cap) | 1920×1080 | qualité max, coût max |
| **1568 (défaut)** | 1568×882 | **bon compromis**, texte lisible |
| 1024 | 1024×576 | plus léger, texte fin plus limite |
| 768 | 768×432 | mini-coût, détails fins perdus |

**⚠️ Model-agnostic — lire ceci.** VidAI produit un jeu de données consommable par
**n'importe quel** agent (Claude, GPT, Gemini, Llama-vision, Qwen-VL…), et **chaque modèle
a sa propre tokenisation et ses propres seuils de resize**. VidAI ne peut donc pas
optimiser pour un modèle précis : il vise un défaut éco raisonnable et neutre. Le **coût
exact en tokens et le seuil réel dépendent du modèle** qui lit la sortie — la qualité
finale d'exploitation dépend aussi de l'intelligence de ce modèle. Ajuste selon ta cible :

```bash
vidai "<url>" -o ./out                      # défaut 1568 px (bon compromis)
vidai "<url>" -o ./out --frame-width 768    # priorité coût (texte fin limite)
vidai "<url>" -o ./out --frame-width 0      # priorité qualité : résolution source, aucun cap
vidai "<url>" -o ./out --frame-width 0 --png  # qualité maximale absolue (sans perte)
```

Le réglage effectif est **reporté dans `output.json`** (`config.frame_width`) et **rappelé
sur stderr** à chaque exécution, pour une traçabilité totale.

## Sortie
`output.json` — le livrable exploitable par l'agent :

```json
{
  "source": {"url": "...", "title": "...", "platform": "youtube", "duration": 92.4, "language": "fr"},
  "config": {"model": "base", "frame_format": "jpg", "frame_width": 1568, "dedup": true, "...": "..."},
  "timeline": [
    {"index": 0, "t": 0.0, "span": [0.0, 4.2], "frame": "frames/kf_0001.jpg",
     "reason": "start", "text": "Bonjour et bienvenue..."}
  ],
  "transcript": [
    {"start": 0.0, "end": 4.2, "text": "Bonjour et bienvenue...",
     "words": [{"start": 0.0, "end": 0.4, "word": "Bonjour"}]}
  ]
}
```

- **`timeline`** — flux frame-centré : chaque keyframe porte son image (`frame`), son intervalle (`span`), la raison de sa sélection (`reason` : `start`/`scene_change`/`max_gap`/`manual`) et le texte prononcé sur cet intervalle. C'est ce que l'agent « déroule » pour suivre la vidéo.
- **`transcript`** — transcription au mot (horodatage fin `words[]`), pour l'alignement précis.
- **`config`** — tous les réglages effectifs du run (traçabilité).
- Les images sont dans `frames/kf_NNNN.{jpg,png}`, référencées par chemin relatif (chargées à la demande par l'agent).

## Préparer des données d'entraînement multimodales
Le format de sortie de VidAI — frames + parole entrelacées et **horodatées** — est
précisément le substrat qu'attendent les pipelines de données pour **Video-LLM**
(instruction-tuning, temporal grounding, dense captioning, sets d'éval, RAG vidéo).
Sa sélection de keyframes *content-aware* (changements de plan + dédup) est un
échantillonnage plus fin qu'un `fps` aveugle, et tout tourne **sans GPU**.

C'est une **couche d'extraction et d'alignement**, pas un annotateur ni un crawler massif —
usages, valeur réelle **et limites franches** détaillés, sources à l'appui, dans
**[docs/ai-training.md](docs/ai-training.md)**.

## Plateformes
Tout ce que [yt-dlp](https://github.com/yt-dlp/yt-dlp) supporte (1800+ sites : YouTube, TikTok, Instagram, X, Vimeo, Reddit…). Exclus : les services DRM (Netflix, Disney+…). La qualité livrée est bornée par ce que la plateforme propose (une vieille vidéo 240p reste du 240p).

## Codes retour
Pensés pour être consommés par un agent : `0` succès (dernière ligne stdout = chemin absolu de `output.json`), `1` erreur pipeline (download/transcription/ffmpeg, message actionnable sur stderr), `2` erreur d'usage (options invalides).

## Contribuer
Les PR sont bienvenues — lis [CONTRIBUTING.md](CONTRIBUTING.md) (principes non négociables : 100% CPU, zéro dépendance système obligatoire, erreurs explicites, transparence des réglages de qualité). Historique des versions : [CHANGELOG.md](CHANGELOG.md). Faille de sécurité : [SECURITY.md](SECURITY.md) — signalement privé, pas d'issue publique.

## Licence
[MIT](LICENSE).
