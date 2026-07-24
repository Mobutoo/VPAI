# SPEC — Boucle feedback client autonome (usine SaaS IA)

> Date : 2026-07-24
> Statut : brainstorm validé, en attente de relecture avant plan d'implémentation
> Sous-projet de : vision "usine de création de SaaS assistée par IA" (voir mémoire `project_usine_saas_ia_factory.md`)

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
MinIO (stockage objet)  ← vidéo brute = preuve/traçabilité humaine, jamais analysée frame-par-frame en entrée IA par défaut
      │  déclenche
      ▼
Workflow n8n : Whisper (LiteLLM) transcrit l'audio + vision-LLM échantillonne des frames
      │
      ▼
LLM (LiteLLM) : transcript + clics + observations vision → JSON structuré de user stories
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
- L'IA n'analyse **jamais la vidéo brute frame par frame en continu** — transcript audio + log de clics + frames échantillonnées (1/5s + 1/clic) + screenshots ponctuels. Vidéo brute = preuve de secours consultable par un humain.
- Le widget de capture est écrit une seule fois, embarqué dans le template SaaS partagé — disponible automatiquement sur chaque nouveau projet client.
- **v1 démarre sur GitHub** (réutilisation directe de `flash-daemon` sans portage) pour valider vite la boucle bout-en-bout. **Cible documentée : Gitea self-hosted** (déjà déployé et opérationnel sur Seko-VPN, `git.<domain>`, SSH interne `:2222` alias `seko-git` — confirmé par `docs/specs/SPEC-GITEA-SEKO-VPN.md` et usage réel dans `Seko-VPN/docs/05-troubleshooting.md`). Le portage `flash-daemon` (actuellement ~15 appels `gh` CLI GitHub-only) vers l'API Gitea/`tea` CLI est testé comme étape intermédiaire séparée, pas dans ce premier lot.
- Kanban client = vue NocoDB partagée en lecture seule (pas d'UI custom construite en v1) — solution intermédiaire assumée, une vraie interface pro est un objectif v2 non conçu ici.

## 4. Composants

| Composant | Choix | Détail |
|---|---|---|
| Capture | Widget JS maison, embarqué au template SaaS partagé | `MediaRecorder` (écran+micro) + listener clics (sélecteur CSS + timestamp) |
| Stockage vidéo | MinIO | Vidéo brute, traçabilité humaine uniquement |
| Analyse audio | Whisper via LiteLLM | Transcript horodaté |
| Analyse clics | Log JSON du widget | Corrélé au transcript par timestamp |
| Analyse visuelle (v1) | Vision-LLM via LiteLLM sur frames échantillonnées | Réutilise le pattern `take.qc` Content Factory |
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
| 1. Upload widget → MinIO | vidéo (webm écran+micro) + JSON clics `[{selector, text, x, y, ts_ms}]` |
| 2. Trigger n8n | `{session_id, client_id, video_url, clicks_url}` |
| 3. Transcription (Whisper/LiteLLM) | `{transcript: [{text, ts_start, ts_end}]}` |
| 4. Vision QC (frames échantillonnées : 1/5s + 1/clic) | `{observations: [{ts_ms, finding, severity}]}` |
| 5. Synthèse LLM | `{user_stories: [{title, description, ui_element, verbatim, screenshot_ts}]}` |
| 6. Screenshots (ffmpeg) | image par `screenshot_ts`, stockée MinIO |
| 7. Cards → NocoDB `feedback_cards` | statut initial `pending_review` |
| 8. Validation client | statut → `approved`/`rejected`/`needs_edit` + note |
| 9. Consolidation IA | dédoublonne/fusionne `approved`+`needs_edit` → `final_stories`, mapping `card_id→final_story_id` (traçabilité) |
| 10. Issues GitHub | 1 par `final_story`, labels `ready`+`feedback-loop` |
| 11. `flash-daemon` sur label `ready` (mécanisme existant — état `ready`→`in-progress`→`done`/`blocked`, `feedback-loop` sert uniquement de filtre de traçabilité) | plan → implémentation → PR → merge |
| 12. Miroir statut NocoDB | webhook GitHub → n8n → kanban à-faire (`ready`)/en-cours (`in-progress`)/fait (`done`)/bloqué (`blocked`) |

## 6. Gestion d'erreurs

| Panne | Comportement |
|---|---|
| Upload coupé/échoué | Retry local widget, sinon session `upload_failed` + notif interne |
| Transcription échoue | 1 retry, sinon `needs_manual_review` — jamais de blocage silencieux |
| Budget IA ($5/j) dépassé | Session `queued_budget`, reprise au reset (pattern déjà existant dans la stack) |
| Consolidation incohérente (JSON invalide/contradictions non résolues) | 1 retry, puis escalade humaine (`notify-gate.sh`) — jamais d'issue cassée publiée automatiquement |
| `flash-daemon` bloqué | Circuit-breaker existant : 3 échecs consécutifs → STOP + notif |
| Client ne valide jamais ses cards | Pas de timeout auto-validation — reste `pending_review`, visible tel quel dans le kanban |

## 7. Critères de succès v1

- Session réelle bout-en-bout : enregistrement → transcript exploitable → ≥1 user story cohérente générée → visible comme card NocoDB → validée → devient une issue GitHub → `flash-daemon` produit une PR mergeable
- Aucun secret/credential visible à l'écran ne doit atterrir en clair dans un prompt LLM (risque produit à documenter — pas une garantie technique de la capture elle-même)
- Coût par session cible : quelques centimes, pas plusieurs euros (transcription + vision + synthèse + consolidation)

## 8. Roadmap v2 (non conçu ici)

- Portage `flash-daemon` : GitHub → Gitea self-hosted (Seko-VPN)
- Capture continue (OpenReplay self-hosted)
- Analyse UX prod (PostHog ou Hotjar-like)
- Dashboard client dédié, interface professionnelle (remplace la vue Kanban NocoDB)
- Interface de validation en cartes glissées (swipe animé), avec génération d'images par card (Stitch/ComfyUI)
- Modèle multimodal vidéo native pour l'analyse visuelle (si concluant, remplace l'échantillonnage de frames)
- Pods GPU dédiés via PodPilot (pour les besoins compute plus lourds de la v2, ex. analyse vidéo native)
