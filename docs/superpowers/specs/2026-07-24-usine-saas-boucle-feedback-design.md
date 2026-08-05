# SPEC — Boucle feedback client autonome (usine SaaS IA)

> Date : 2026-07-24 (amendé 2026-08-05)
> Statut : brainstorm validé, en attente de relecture avant plan d'implémentation
> Sous-projet de : vision "usine de création de SaaS assistée par IA" (voir mémoire `project_usine_saas_ia_factory.md`)
>
> **Amendement 2026-08-05** : intègre les 2 findings HIGH de la consolidation Codex du
> 2026-07-25 (`optimus/.planning/reviews/2026-07-25-consolidation-revue-codex-specs.md`,
> §1), GO opérateur du 2026-08-05 — H1 atomicité du déclenchement n8n (§3, §5, §6) et
> H2 scrubbing des secrets avant tout envoi LLM (§3, §4, §5, §7). Cohérence légère avec
> la spec fondatrice `optimus/docs/specs/2026-08-05-modele-livraison-360-design.md` :
> les données de capture vivent dans l'espace privé client (§7 de la 360, `tenant_id`+
> `project_id`, MinIO du data plane client).

## 1. Contexte et périmètre

Le projet "usine SaaS" vise à transformer une idée client en SaaS déployé et itéré en quelques jours, avec un minimum de friction. La chaîne complète comporte plusieurs briques indépendantes (intake/templates, provisioning, veille marché, pipeline mobile, cette brique feedback). Ce spec couvre **uniquement la brique feedback** : la boucle entre la livraison du premier prototype et le vrai MVP.

**Objectif** : remplacer les sessions de discussion live avec le client ("je n'ai pas aimé telle chose, je veux que ce truc soit à tel endroit") par une capture autonome, analysée par IA, qui alimente directement le pipeline de développement.

**Hors périmètre de ce spec** (sous-projets séparés ou évolutions v2 documentées mais non conçues ici) :
- Intake / choix de templates / génération du premier cahier des charges
- Nouvelle infrastructure dédiée (où héberger tout ceci) — ce spec suppose MinIO/LiteLLM/n8n/Gitea ou GitHub/`flash-daemon` déjà accessibles
- Pipeline mobile Android/iOS
- v2 : capture continue (OpenReplay), analyse UX prod (PostHog/Hotjar-like), dashboard client custom-brandé, interface de validation en cartes glissées (swipe animé), modèle vidéo natif pour l'analyse visuelle, pods GPU dédiés via PodPilot, portage `flash-daemon` de GitHub vers Gitea self-hosted

## 2. Recherche préalable — outils évalués

Trois outils proposés en référence, vérifiés avant conception :

| Outil | Constat |
|---|---|
| [RUXAILAB](https://github.com/ruxailab/RUXAILAB) | Dépend de Firebase en prod (cloud propriétaire) ; tests non supervisés solo écran+voix non documentés comme fonctionnalité de base (plutôt tests modérés en visio ou heuristiques). MIT. |
| [OpenReplay](https://github.com/openreplay/openreplay) | Self-hosted OK, mais session replay **silencieux** (DOM/réseau/console) — aucune capture audio/voix native documentée. |
| [RemoteGazeUX](https://github.com/FIUNER-LICA/RemoteGazeUX) | Projet académique eye-tracking, avertissement explicite "pas pour la production", 1 développeur, 2 stars. |

**Conclusion** : aucun des trois ne couvre le besoin (capture autonome solo, écran+voix+clics, façon fin de meeting). Le widget de capture est construit sur des APIs navigateur standard (`MediaRecorder`), pas sur un de ces frameworks.

**Assets internes réutilisés** :
- `~/work/saas/flash-studio/flash-infra/scripts/flash-daemon.sh` (v3/v4) — daemon autonome plan→implémentation→PR, a traité ~140 issues GitHub réelles en prod, avec circuit-breaker (3 échecs consécutifs → STOP). **Copie locale active**, pas la copie archivée `VPAI/archive/flash-studio-complete/` (obsolète, roles Ansible restés à l'état de squelette).
- Pattern QC de Content Factory (`take.qc={"score":...}` via vision+LLM judge, gate `CF_QC_LIVE` prod) — réutilisé pour l'étape d'analyse visuelle.
- MinIO, LiteLLM (Whisper + routing LLM), NocoDB (déjà utilisés dans la stack existante).

## 3. Architecture

```
Client teste son prototype déployé
      │
      ▼
Widget de capture (baked dans le template SaaS partagé)
  — MediaRecorder (écran+micro, 1 flux vidéo)
  — listener clics (sélecteur + timestamp)
      │  fin de session → upload
      ▼
MinIO (stockage objet, espace privé client — tenant_id+project_id, cf. modèle-livraison §7)
  ← vidéo brute = preuve/traçabilité humaine, jamais analysée frame-par-frame en entrée IA par défaut
      │  vidéo + clics écrits, PUIS manifeste `complete.json` écrit en dernier (H1 Codex)
      ▼
Manifeste de complétion `complete.json` (session_id, checksums vidéo+clics) → SEUL déclencheur du workflow n8n
      │  n8n vérifie présence + checksum des artefacts référencés avant de poursuivre
      ▼
Workflow n8n : scrubbing (H2 Codex) → Whisper (LiteLLM) transcrit l'audio + vision-LLM échantillonne des frames
      │
      ▼
LLM (LiteLLM) : transcript scrubbé + clics + observations vision → JSON structuré de user stories
      │  + screenshot extrait (ffmpeg) par card
      ▼
Cards stockées dans NocoDB (`feedback_cards`)
      │
      ▼
Interface de validation (page simple : go / no-go / modifier+note par card)
      │  cards go + modifier-avec-note
      ▼
Consolidation IA (étape n8n)
  — relit le lot de cards validées ensemble
  — dédoublonne, fusionne les cards liées, résout les contradictions
      │
      ▼
Issues GitHub (repo client, labels `ready`+`feedback-loop`) + statut miroir NocoDB
      │
      ▼
flash-daemon : plan → implémentation → PR → merge → redéploiement
      │
      ▼
Dashboard client : vue Kanban NocoDB partagée (lecture seule)
```

Décisions clés :
- **(H1 Codex, RETENU)** Le déclenchement du workflow n'est jamais un événement d'upload brut — c'est un manifeste de complétion `complete.json` écrit en dernier, après vidéo+audio+clics, référençant les checksums de chaque artefact. n8n vérifie présence ET intégrité (checksum) avant de traiter. Idempotence par `session_id` : un manifeste retraité (retry, replay webhook) ne recrée pas de cards/issues en double — recherche d'un enregistrement `session_id` existant avant création.
- **(H2 Codex, RETENU)** Aucun contenu brut (transcript, frames) ne part vers un LLM sans passer par l'étape de scrubbing (§4, §5). Le critère de succès §7 correspondant devient vérifiable techniquement, pas seulement documenté comme risque.
- L'IA n'analyse **jamais la vidéo brute frame par frame en continu** — transcript audio + log de clics + frames échantillonnées (1/5s + 1/clic) + screenshots ponctuels. Vidéo brute = preuve de secours consultable par un humain.
- Le widget de capture est écrit une seule fois, embarqué dans le template SaaS partagé — disponible automatiquement sur chaque nouveau projet client.
- Les artefacts de capture (vidéo, clics, manifeste, transcript, cards) vivent dans l'espace **privé client** (`tenant_id`+`project_id`), MinIO du data plane client — cf. `optimus/docs/specs/2026-08-05-modele-livraison-360-design.md` §7 (les trois espaces de connaissance).
- **v1 démarre sur GitHub** (réutilisation directe de `flash-daemon` sans portage) pour valider vite la boucle bout-en-bout. **Cible documentée : Gitea self-hosted** (déjà déployé et opérationnel sur Seko-VPN, `git.<domain>`, SSH interne `:2222` alias `seko-git` — confirmé par `docs/specs/SPEC-GITEA-SEKO-VPN.md` et usage réel dans `Seko-VPN/docs/05-troubleshooting.md`). Le portage `flash-daemon` (actuellement ~15 appels `gh` CLI GitHub-only) vers l'API Gitea/`tea` CLI est testé comme étape intermédiaire séparée, pas dans ce premier lot.
- Kanban client = vue NocoDB partagée en lecture seule (pas d'UI custom construite en v1) — solution intermédiaire assumée, une vraie interface pro est un objectif v2 non conçu ici.

## 4. Composants

| Composant | Choix | Détail |
|---|---|---|
| Capture | Widget JS maison, embarqué au template SaaS partagé | `MediaRecorder` (écran+micro) + listener clics (sélecteur CSS + timestamp) |
| Manifeste de complétion | `complete.json` (session_id, checksums vidéo+clics+métadonnées) écrit en dernier | **(H1)** Seul déclencheur du workflow n8n ; n8n vérifie présence+checksum avant de traiter ; idempotence par `session_id` |
| Stockage vidéo | MinIO, espace privé client (`tenant_id`+`project_id`) | Vidéo brute, traçabilité humaine uniquement — cf. modèle-livraison §7 |
| Scrubbing pré-LLM | Étape n8n dédiée, patterns type `~/work/saas/fantrad/services/scheduler/scrub.py` (léger, validé ARM64, cf. étude Presidio 2026-07-22) | **(H2)** Détection clés API/tokens/IBAN/mots de passe visibles à l'écran + PII de base, AVANT tout envoi à Whisper/vision-LLM/synthèse |
| Analyse audio | Whisper via LiteLLM | Transcript horodaté, sur contenu scrubbé |
| Analyse clics | Log JSON du widget | Corrélé au transcript par timestamp |
| Analyse visuelle (v1) | Vision-LLM via LiteLLM sur frames échantillonnées, post-scrubbing | Réutilise le pattern `take.qc` Content Factory |
| Analyse visuelle (v2, non engagé) | Modèle multimodal vidéo native | À évaluer selon modèle/taille de fichier |
| Synthèse | LLM (LiteLLM) | Transcript + clics + observations vision → JSON user stories |
| Cards | Table NocoDB `feedback_cards` | Texte + screenshot extrait (ffmpeg) |
| Validation | Page simple go/no-go/modifier+note | Pas de swipe animé en v1 |
| Consolidation IA | Étape n8n post-validation | Dédoublonne/fusionne/résout contradictions |
| Issues | GitHub (v1) → Gitea (cible documentée) | 1 issue par user story consolidée, label `ready` (déclencheur réel de `flash-daemon`) + `feedback-loop` (traçabilité de la source) |
| Exécution | `flash-daemon` (`~/work/saas/flash-studio`) | plan → implémentation → PR → merge |
| Dashboard client | Vue Kanban NocoDB partagée (lien lecture seule) | v1 seulement |

## 5. Flux de données

| Étape | Format |
|---|---|
| 1. Upload widget → MinIO (espace privé client) | vidéo (webm écran+micro) + JSON clics `[{selector, text, x, y, ts_ms}]` |
| 1bis. Manifeste de complétion **(H1)** | `complete.json` écrit en dernier : `{session_id, client_id, video_url, video_sha256, clicks_url, clicks_sha256, created_at}` |
| 2. Trigger n8n **(H1)** | déclenché uniquement sur l'écriture du manifeste ; n8n récupère `complete.json`, vérifie présence + checksum de chaque artefact référencé, puis résout `{session_id, client_id, video_url, clicks_url}` ; recherche préalable d'un `session_id` déjà traité (idempotence — pas de doublon de cards/issues) |
| 3. Scrubbing pré-LLM **(H2)** | entrée : transcript brut + frames échantillonnées ; sortie : `{transcript_scrubbed, redactions: [{type, ts_ms, span}]}` — patterns clé API/token/IBAN/mot de passe visible + PII de base ; segment ambigu → exclu de l'envoi |
| 4. Transcription (Whisper/LiteLLM) | `{transcript: [{text, ts_start, ts_end}]}`, sur contenu scrubbé |
| 5. Vision QC (frames échantillonnées : 1/5s + 1/clic, post-scrubbing) | `{observations: [{ts_ms, finding, severity}]}` — une détection de secret par le scrubbing devient une `observation` de sévérité sécurité, visible dans l'issue finale |
| 6. Synthèse LLM | `{user_stories: [{title, description, ui_element, verbatim, screenshot_ts}]}` |
| 7. Screenshots (ffmpeg) | image par `screenshot_ts`, stockée MinIO (espace privé client) |
| 8. Cards → NocoDB `feedback_cards` | statut initial `pending_review` |
| 9. Validation client | statut → `approved`/`rejected`/`needs_edit` + note |
| 10. Consolidation IA | dédoublonne/fusionne `approved`+`needs_edit` → `final_stories`, mapping `card_id→final_story_id` (traçabilité) |
| 11. Issues GitHub | 1 par `final_story`, labels `ready`+`feedback-loop` |
| 12. `flash-daemon` sur label `ready` (mécanisme existant — état `ready`→`in-progress`→`done`/`blocked`, `feedback-loop` sert uniquement de filtre de traçabilité) | plan → implémentation → PR → merge |
| 13. Miroir statut NocoDB | webhook GitHub → n8n → kanban à-faire (`ready`)/en-cours (`in-progress`)/fait (`done`)/bloqué (`blocked`) |

## 6. Gestion d'erreurs

| Panne | Comportement |
|---|---|
| Upload coupé/échoué | Retry local widget, sinon session `upload_failed` + notif interne. **(H1)** Sans manifeste `complete.json` écrit, n8n ne se déclenche jamais — pas de traitement sur upload partiel par construction |
| Manifeste présent mais checksum invalide **(H1)** | Traitement refusé, session `manifest_invalid` + notif interne — pas de fallback silencieux sur artefact potentiellement corrompu |
| Manifeste retraité (retry/replay webhook) **(H1)** | Idempotence par `session_id` : `session_id` déjà traité → no-op, pas de doublon de cards/issues |
| Scrubbing détecte un secret **(H2)** | Segment masqué dans le transcript envoyé au LLM ET remonté comme `observation` sécurité dans la card/issue finale (visible côté client, pas juste supprimé) |
| Scrubbing incertain sur un segment **(H2)** | Segment exclu de l'envoi LLM par défaut (fail-closed) — pas d'analyse sur un contenu potentiellement sensible non résolu |
| Transcription échoue | 1 retry, sinon `needs_manual_review` — jamais de blocage silencieux |
| Budget IA ($5/j) dépassé | Session `queued_budget`, reprise au reset (pattern déjà existant dans la stack) |
| Consolidation incohérente (JSON invalide/contradictions non résolues) | 1 retry, puis escalade humaine (`notify-gate.sh`) — jamais d'issue cassée publiée automatiquement |
| `flash-daemon` bloqué | Circuit-breaker existant : 3 échecs consécutifs → STOP + notif |
| Client ne valide jamais ses cards | Pas de timeout auto-validation — reste `pending_review`, visible tel quel dans le kanban |

## 7. Critères de succès v1

- Session réelle bout-en-bout : enregistrement → manifeste de complétion → transcript exploitable → ≥1 user story cohérente générée → visible comme card NocoDB → validée → devient une issue GitHub → `flash-daemon` produit une PR mergeable
- **(H1, amendé)** Un upload partiel (vidéo seule, clics manquants, manifeste absent) ne déclenche jamais le workflow n8n — vérifié par test : couper l'upload à mi-vidéo ne doit produire aucune card
- **(H2, amendé)** Aucun secret/credential visible à l'écran n'atterrit en clair dans un prompt LLM — **garantie technique**, pas seulement documentaire : étape de scrubbing (patterns clé API/token/IBAN/mot de passe + PII de base, cf. §4/§5) exécutée avant tout appel Whisper/vision-LLM/synthèse, avec fail-closed sur segment ambigu et remontée en finding de sécurité côté client
- Coût par session cible : quelques centimes, pas plusieurs euros (transcription + vision + synthèse + consolidation)

## 8. Roadmap v2 (non conçu ici)

- Portage `flash-daemon` : GitHub → Gitea self-hosted (Seko-VPN)
- Capture continue (OpenReplay self-hosted)
- Analyse UX prod (PostHog ou Hotjar-like)
- Dashboard client dédié, interface professionnelle (remplace la vue Kanban NocoDB)
- Interface de validation en cartes glissées (swipe animé), avec génération d'images par card (Stitch/ComfyUI)
- Modèle multimodal vidéo native pour l'analyse visuelle (si concluant, remplace l'échantillonnage de frames)
- Pods GPU dédiés via PodPilot (pour les besoins compute plus lourds de la v2, ex. analyse vidéo native)
