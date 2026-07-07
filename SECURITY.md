# Politique de sécurité

## Versions supportées

| Version | Supportée |
|---------|-----------|
| 0.1.x   | ✅        |

## Signaler une vulnérabilité

**Ne pas ouvrir d'issue publique.** Utilise l'onglet
[Security → Report a vulnerability](https://github.com/daraook/vidai/security/advisories/new)
de GitHub (signalement privé).

Inclure : version de VidAI (`vidai --version`), OS, scénario de reproduction, impact
estimé. Réponse visée sous 7 jours.

## Périmètre

VidAI exécute des binaires locaux (ffmpeg) et télécharge du contenu distant via yt-dlp.
Sont notamment dans le périmètre :

- injection de commande via une URL, un chemin, ou des métadonnées de vidéo ;
- écriture de fichiers hors du dossier de sortie choisi (path traversal) ;
- exécution de contenu téléchargé.

Hors périmètre : les vulnérabilités propres à `yt-dlp`, `faster-whisper`, `ffmpeg` ou
`imageio-ffmpeg` (à signaler en amont), et l'usage de VidAI sur du contenu que tu n'as
pas le droit de traiter.

## Bonnes pratiques d'usage

- Les fichiers cookies (`--cookies`) contiennent des secrets de session : ne les
  committe jamais, ne les partage pas.
- VidAI ne contourne ni DRM ni authentification, et n'ira jamais dans ce sens.
