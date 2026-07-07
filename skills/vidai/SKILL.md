---
name: vidai
description: >
  Analyser une vidéo en ligne (YouTube, TikTok, Instagram, X… 1800+ sites) ou un
  fichier vidéo local sans GPU : transcription horodatée + frames synchronisées
  {texte, image, timestamp}. À utiliser quand l'utilisateur demande de résumer,
  analyser, vérifier ou extraire quelque chose d'une vidéo. Déclencheurs :
  "regarde cette vidéo", "résume cette vidéo", "que dit-il à…", "analyse ce
  tuto/cette conf", une URL de vidéo à exploiter.
---

# VidAI — exploiter une vidéo en agent économe

VidAI transforme une vidéo en données lisibles par un agent : `output.json` avec
`timeline[]` (une entrée par keyframe : `t`, `span`, `frame`, `text`) et
`transcript[]` (texte horodaté **au mot**). Tout le pipeline tourne **en local, 0
token** — tu ne dépenses des tokens que quand tu **lis** la sortie. Le texte est
bon marché ; **les images sont le vrai coût** (~500-1500+ tokens chacune, selon le
modèle). Toute la stratégie découle de ça.

## Prérequis

```bash
vidai --check   # ffmpeg (bundlé), yt-dlp, faster-whisper — tout doit être ✓
```

Absent ? Installer : `curl -fsSL https://raw.githubusercontent.com/daraook/vidai/main/install.sh | bash`
(Windows : `irm https://raw.githubusercontent.com/daraook/vidai/main/install.ps1 | iex`).
Serveur MCP disponible aussi : `vidai-mcp` (extra `vidai[mcp]`) expose
`video_transcript`, `video_frames_at`, `video_timeline`, `check_dependencies`.

## Règle d'or : triage en 2 phases

**Ne jamais avaler une vidéo entière en images.** D'abord le texte, ensuite
seulement les images utiles.

```bash
# Phase 1 — texte seul, 0 token d'image. La vidéo est conservée automatiquement
# (source.mp4) pour la phase 2.
vidai "<url>" -o ./out --transcript-only
# → lis out/output.json : transcript horodaté ; repère les instants où l'image compte

# Phase 2 — UNIQUEMENT les frames utiles, depuis la vidéo déjà locale
vidai ./out/source.mp4 -o ./out --frames-at "12,45,90"
```

Interprétation : `0` = succès, dernière ligne stdout = chemin absolu de
`output.json`. `1` = erreur pipeline (message actionnable sur stderr, ex. vidéo
privée → proposer `--cookies`). `2` = erreur d'usage (option invalide).

## Choisir la stratégie selon la tâche

| Situation | Commande |
|---|---|
| Résumé, "que dit-il ?" | Phase 1 seule (`--transcript-only`) — le texte suffit souvent |
| Question sur un passage précis | `--clip A-B` (répétable ; sur URL, ne télécharge QUE ces plages — ~13 Mo pour 2 min dans une vidéo de 10 h) |
| Vidéo courte (< 3-4 min) à couvrir entièrement | pipeline complet par défaut |
| Screencast/tuto code avec musique parasite | `--visual-only` (timeline d'images, audio ignoré) |
| Détail visuel fin (texte à l'écran, schéma) | recharge la frame en meilleure qualité : `--frames-at <t> --frame-width 0 --png` |
| Vidéo nécessitant login | seulement si l'utilisateur fournit `--cookies FILE` — jamais de contournement |

Temps en `SS`, `MM:SS` ou `HH:MM:SS` (attention : `8:32` = 8 min 32 s ; 8 h 32 = `8:32:00`).

## Lire la sortie sans gaspiller

1. Lis `output.json` en entier côté texte (`timeline[].text`, `transcript[]`) —
   c'est bon marché.
2. Ne charge une image `frames/kf_NNNN.jpg` **que** si le texte ne répond pas
   (schéma, code à l'écran, action visuelle). Chaque image chargée coûte des tokens.
3. `timeline[].reason` te dit pourquoi la frame existe : `scene_change` = information
   visuelle nouvelle (prioritaire), `max_gap` = filet de couverture (souvent redondant).

## Résolution des frames = coût ↔ qualité (à connaître)

Par défaut VidAI plafonne le plus grand côté des frames à **1568 px**
(`--frame-width`, downscale seul, jamais d'upscale) : bon compromis, texte à
l'écran lisible. C'est **model-agnostic** — chaque modèle a sa propre tokenisation
et ses propres seuils de redimensionnement, donc le coût exact dépend du modèle
qui lit (toi ou un autre). Ajuste en connaissance de cause :

- `--frame-width 768` : priorité coût (détails fins perdus) ;
- `--frame-width 0` : résolution source, aucun cap (qualité max, coût max) ;
- `--frame-width 0 --png` : qualité maximale absolue (sans perte).

Le réglage effectif est toujours reporté dans `output.json` → `config.frame_width` :
vérifie-le avant de conclure qu'un détail est illisible « dans la vidéo » — il est
peut-être juste illisible **à cette résolution**.

## Pièges connus

- La qualité est bornée par la source : une vieille vidéo 240p reste du 240p.
- `--transcript-only` conserve automatiquement la vidéo téléchargée (`source.mp4`)
  pour la phase 2. Une fois le triage fini, supprime-la si l'espace disque compte.
- Contenu DRM (Netflix, Disney+…) : non supporté, ne pas insister.
- Vidéo muette ou 100% musique : transcript vide est NORMAL — la timeline visuelle
  reste exploitable (`language: "none"` + log explicite).
- Le filtre anti-hallucination (`--max-no-speech 0.85`) retire les faux sous-titres
  sur fond musical ; si un passage parlé semble manquer, relance avec
  `--max-no-speech 1.0` pour vérifier.
