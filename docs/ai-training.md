# VidAI et l'entraînement des modèles multimodaux (Video-LLM)

> **Résumé honnête.** VidAI n'est pas un générateur de dataset « en un clic », ni un
> crawler à l'échelle industrielle. C'est une **couche d'extraction et d'alignement**,
> déterministe et **sans GPU**, qui transforme une vidéo en un substrat
> `{frame, texte, timestamp}` — précisément le **format d'entrée** que consomment les
> pipelines de données pour Video-LLM. Sa vraie utilité pour l'entraînement est réelle
> mais **circonscrite** : préparer des jeux de données **ciblés et curés** (fine-tuning,
> temporal grounding, sets d'évaluation, RAG vidéo), pas remplacer WebVid/InternVid.

---

## 1. Ce dont l'entraînement d'un Video-LLM a besoin

Les modèles de langage multimodaux « vidéo » ne consomment pas des pixels en continu :
ils raisonnent sur un **petit nombre de frames échantillonnées + du texte horodaté**.
La littérature récente est convergente sur trois points :

- **Échantillonnage de frames (sparse).** Les Video-LLM échantillonnent typiquement
  **8 à 64 frames** par vidéo (LLaVA-OneVision ≤ 32, LLaVA-Vid ~20, Video-LLaVA 8 ;
  1–2 FPS pour les annotations denses). **La stratégie de sélection est critique** :
  un benchmark montre l'exactitude passer de ~65 % à ~80 % selon le protocole
  d'échantillonnage — le choix des frames compte autant que leur nombre.
  ([Frame Sampling Strategies Matter, 2025](https://arxiv.org/html/2509.14769v1) ;
  [LLaVA-Video, 2024](https://llava-vl.github.io/blog/2024-09-30-llava-video/))
- **Texte horodaté (temporal grounding / dense captioning).** L'entraînement au
  raisonnement temporel repose sur des descriptions **temporellement ancrées** :
  ActivityNet Captions = 20 000 vidéos, ~3,65 phrases localisées/vidéo (100 000 phrases) ;
  YouCook2 ; DenseStep2M (~100 k vidéos → 2 M étapes procédurales horodatées).
  ([Dense Video Captioning: A Survey, 2025](https://dl.acm.org/doi/full/10.1145/3712059) ;
  [DenseStep2M, 2026](https://arxiv.org/html/2604.26565v1))
- **Frames et parole entrelacées.** Une famille d'approches performantes
  **entrelace densément les mots ASR avec les frames** le long de l'axe temporel
  (tokens visuels-textuels interleaved), en s'appuyant sur la transcription pour la
  cohérence. ([MiniGPT4-Video, 2024](https://arxiv.org/pdf/2404.03413) ;
  [Live: Learning Video LLM with Streaming Speech Transcription](https://varworkshop.github.io/assets/pdf/10.pdf) ;
  [TimeMarker, 2024](https://arxiv.org/pdf/2411.18211))

Le schéma dominant reste **pré-entraînement** (alignement vision-langage) puis
**instruction-tuning** sur des tâches horodatées (dense captioning, segment captioning,
temporal grounding). ([From Image to Video, 2024](https://arxiv.org/html/2404.11865v2))

---

## 2. Ce que VidAI produit — et pourquoi ça correspond

La sortie de VidAI (`output.json`) est exactement un flux **frame-centré, entrelacé,
horodaté** :

```json
"timeline": [
  {"t": 12.3, "span": [12.3, 15.0], "frame": "frames/kf_0007.jpg",
   "reason": "scene_change", "text": "on ouvre le terminal et on lance le build"}
],
"transcript": [
  {"start": 12.3, "end": 15.0, "text": "...",
   "words": [{"start": 12.3, "end": 12.5, "word": "on"}]}
]
```

| Besoin d'entraînement (§1) | Ce que VidAI fournit nativement |
|---|---|
| Frames échantillonnées, sélection soignée | Keyframes par **détection de plans + filet temporel + déduplication** (ADR-007) — un échantillonnage **content-aware**, pas un `fps=1` aveugle |
| Texte temporellement ancré | Chaque keyframe porte le texte de son `span` (dense-captioning-ready) |
| Parole entrelacée aux frames | Transcription **au mot** (`words[]`) alignée sur les timestamps des frames |
| Format machine-lisible reproductible | JSON structuré + `config` (tous les réglages du run, reproductibilité) |

Autrement dit : VidAI produit **le substrat** que les pipelines de §1 attendent en entrée.
Son échantillonnage par changement de plan est même un **atout mesurable** — puisque « la
stratégie de sélection est critique », remplacer un échantillonnage uniforme par une
sélection guidée par le contenu est une piste légitime d'amélioration de dataset.

---

## 3. Cas d'usage concrets et défendables

1. **Datasets d'instruction-tuning ciblés / de niche.** Construire un jeu SFT
   domaine-spécifique (tutoriels d'un logiciel, gestes techniques, sport, cuisine…) à
   partir de quelques centaines/milliers de vidéos, là où les grands corpus web sont
   trop génériques.
2. **Données de temporal grounding / dense captioning.** Le couple `span`↔`text`↔`frame`
   est directement un échantillon « décris/localise l'événement à cet instant ».
3. **Alignement ASR↔frames au mot** pour les approches interleaved parole-vision.
4. **Sets d'évaluation / benchmarks maison** horodatés, reproductibles (la `config`
   fige les paramètres).
5. **Corpus RAG « sur vidéo ».** Indexer `{texte, frame, timestamp}` pour une recherche
   sémantique multimodale — usage voisin de l'entraînement, même substrat.
6. **Accessibilité.** 100 % CPU, `pip`/script d'install, **respect des ToS** (pas de DRM,
   pas de scraping derrière login sans cookies fournis) → à portée d'un chercheur indé
   ou d'un petit labo, sans ferme GPU ni infrastructure de crawl.

---

## 4. Limites — franches et assumées

VidAI est un **maillon** d'une chaîne de données, pas la chaîne entière. Ne pas survendre :

- **Ce n'est pas un crawler à l'échelle web.** Outil **par-vidéo, CPU**. Les corpus type
  Panda-70M / InternVid / HD-VILA-100M (dizaines de millions de clips) relèvent d'une
  infrastructure industrielle. VidAI vise le **curé et le ciblé** (10²–10⁴ vidéos), pas le
  massif.
- **Ce n'est pas un annotateur sémantique.** VidAI fournit la **transcription (ASR)** et
  les **frames**, pas des **descriptions/captions** riches. Générer des annotations de type
  « dense caption » exige encore une étape de captioning (un VLM/LLM en aval). VidAI est la
  couche **extraction + alignement déterministe**, en amont de l'annotation.
- **Qualité = qualité de Whisper.** La transcription hérite des forces et erreurs de
  faster-whisper (bruit, chevauchements, langues rares). Les erreurs ASR se propagent au
  dataset — à contrôler.
- **Sélection de keyframes heuristique.** Détection de plans (seuil réglable), pas un
  échantillonneur appris ; peut manquer des transitions sur aplats de couleur unie
  (voir gotchas). Réglable, pas magique.
- **Droits et licences.** Respecter les ToS ne confère **aucun droit** sur le contenu
  source. La légalité d'entraîner sur des vidéos tierces (droit d'auteur, licences,
  consentement) relève de **l'utilisateur** — VidAI ne l'accorde pas et ne s'y substitue pas.
- **Résolution.** Le plafond `--frame-width` (défaut 1568) vise l'**économie de tokens à
  l'inférence** côté agent ; pour l'entraînement, adapte la résolution à ton modèle cible
  (souvent `--frame-width 0` pour garder la source, la qualité prime alors sur le coût).

---

## 5. Exemple de pipeline de préparation

```bash
# 1. Extraire le substrat {frame, texte, timestamp} en pleine résolution (qualité training)
vidai "<url>" -o ./ds/clip001 --frame-width 0 --png --markdown

# 2. (aval, hors VidAI) un VLM/LLM lit ./ds/clip001/output.json et génère les captions
#    denses / paires instruction-réponse à partir des {frame, span, text}.

# 3. Répéter/scripter sur ta liste de sources curées, puis agréger en dataset SFT.
```

VidAI garantit l'étape 1 : **reproductible, sans GPU, alignée, horodatée**. Le reste
(annotation, filtrage qualité, formatage au schéma de ton modèle) reste ton travail — et
c'est là que réside la valeur éditoriale du dataset.

---

## Sources

- [MiniGPT4-Video: Interleaved Visual-Textual Tokens (2024)](https://arxiv.org/pdf/2404.03413)
- [TimeMarker: Temporal Localization in Video-LLMs (2024)](https://arxiv.org/pdf/2411.18211)
- [From Image to Video, what do we need in multimodal LLMs? (2024)](https://arxiv.org/html/2404.11865v2)
- [Dense Video Captioning: A Survey (ACM Computing Surveys, 2025)](https://dl.acm.org/doi/full/10.1145/3712059)
- [DenseStep2M: Training-Free Dense Instructional Video Annotation (2026)](https://arxiv.org/html/2604.26565v1)
- [Live: Learning Video LLM with Streaming Speech Transcription](https://varworkshop.github.io/assets/pdf/10.pdf)
- [Frame Sampling Strategies Matter: benchmark for small VLMs (2025)](https://arxiv.org/html/2509.14769v1)
- [LLaVA-Video: Video Instruction Tuning with Synthetic Data (2024)](https://llava-vl.github.io/blog/2024-09-30-llava-video/)

*Les liens ci-dessus étaient valides à la rédaction ; la recherche évolue vite, vérifie les
versions récentes.*
