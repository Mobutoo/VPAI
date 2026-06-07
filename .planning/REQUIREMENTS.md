# Requirements: Content Factory

**Defined:** 2026-03-17
**Core Value:** Produire du contenu de qualite studio avec un workflow professionnel (14 etapes, 4 gates) pilotable depuis Telegram, avec invalidation ciblee par scene.

## v1 Requirements

### Infrastructure

- [x] **INFRA-01**: Kitsu + Zou deployed at `boss.ewutelo.cloud` via Docker Compose on Sese-AI
- [x] **INFRA-02**: Kitsu PostgreSQL database `kitsu_production` provisioned in shared instance
- [x] **INFRA-03**: Caddy reverse proxy with VPN-only ACL for Kitsu
- [x] **INFRA-04**: Fal.ai API key integrated in Ansible vault and available to n8n
- [x] **INFRA-05**: Kitsu healthcheck monitored in Grafana
- [x] **INFRA-06**: Kitsu backup included in daily Zerobyte PostgreSQL dump

### Data Model

- [x] **DATA-01**: NocoDB table `brands` with profile fields (name, tone, palette, typography, target, platforms)
- [x] **DATA-02**: NocoDB table `contents` with pipeline status tracking (14 steps, 4 phases)
- [x] **DATA-03**: NocoDB table `scenes` with per-scene assets, provider, version, status
- [x] **DATA-04**: Qdrant collection `brand-voice` with embedding pipeline (scripts via LiteLLM to Qdrant)
- [x] **DATA-05**: Brand profile "Paul Taff" created (Flash-Studio colors, sarcastic tone, Instagram)
- [x] **DATA-06**: Kitsu project structure mapped (Production=brand, Episode=drop, Sequence=phase, Shot=content, Task=step)

### OpenClaw Skill

- [x] **SKILL-01**: OpenClaw skill `content-director` created and loaded
- [x] **SKILL-02**: Telegram topic 7 routed to content-director skill
- [x] **SKILL-03**: Command `/content <format> <brief>` creates new content (launches step 1)
- [x] **SKILL-04**: Command `/ok` validates current step, advances to next
- [x] **SKILL-05**: Command `/adjust <instruction>` modifies current step (new version)
- [x] **SKILL-06**: Command `/back <step>` returns to earlier step with impact analysis
- [x] **SKILL-07**: Command `/preview` shows current project status
- [x] **SKILL-08**: Command `/impact` shows what would be invalidated
- [x] **SKILL-09**: Gate commands `/lock-preprod`, `/lock-script`, `/ok-rough`, `/ok-final`, `/published`

### Workflows

- [x] **FLOW-01**: n8n workflow `brief-to-concept` orchestrates steps 1-5 (brief, research, moodboard, concept, casting)
- [x] **FLOW-02**: n8n workflow `kitsu-sync` uploads previews and updates task statuses in Kitsu
- [x] **FLOW-03**: n8n workflow `script-to-storyboard` orchestrates steps 6-8 (script, storyboard, sound design)
- [x] **FLOW-04**: n8n workflow `generate-assets` dispatches to correct provider per scene
- [x] **FLOW-05**: n8n workflow `rough-cut` assembles scenes via Remotion
- [x] **FLOW-06**: n8n workflow `invalidation-engine` handles targeted scene invalidation cascades
- [x] **FLOW-07**: Kitsu webhooks to n8n integration (task status, comments, preview uploads)

### Remotion

- [x] **RMTN-01**: Composition `reel-motion-text` (9:16, 15-60s, animated text + gradients)
- [x] **RMTN-02**: Composition `reel-meme-skit` (9:16, 15-30s, meme/skit format)
- [x] **RMTN-03**: Composition `reel-feature-showcase` (9:16, 30-60s, product demo + overlays)
- [x] **RMTN-04**: Composition `reel-teaser` (9:16, 15s, hook + mystery + CTA)
- [x] **RMTN-05**: All compositions accept `scenes[]`, `brand`, `audio` props

### Calendar

- [x] **CAL-01**: Editorial calendar visible in Plane (contents = work items with dates)
- [x] **CAL-02**: Drops organized as Plane cycles
- [x] **CAL-03**: n8n auto-creates Plane work items from NocoDB content entries

## v2 Requirements

### Voiceover

- **V2-01**: ElevenLabs voiceover integration

### Publishing

- **V2-02**: Instagram Graph API auto-publishing
- **V2-06**: Multi-platform support (TikTok, LinkedIn, X, YouTube Shorts)

### Advanced Production

- **V2-03**: Multi-format adaptation (step 13 — carousel, story, YouTube Shorts from single content)
- **V2-05**: Ad spot pipeline (organic content to Meta Ads variants)

### Analytics

- **V2-04**: Analytics feedback loop (Instagram metrics to content optimization)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Mobile app | Telegram + Kitsu web UI sufficient |
| Custom Kitsu plugins | Use REST API only, avoid maintenance burden |
| Real-time collaboration | Solo user, async Telegram sufficient |
| AI voice cloning | Legal/ethical concerns, use stock voices |
| Kubernetes | Docker Compose only (VPAI pattern) |
| Dedicated PostgreSQL for Kitsu | Shared instance mandatory (VPS 8GB constraint) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 5 | Complete |
| INFRA-02 | Phase 5 | Complete |
| INFRA-03 | Phase 5 | Complete |
| INFRA-04 | Phase 5 | Complete |
| INFRA-05 | Phase 5 | Complete |
| INFRA-06 | Phase 5 | Complete |
| DATA-01 | Phase 5 | Complete |
| DATA-02 | Phase 5 | Complete |
| DATA-03 | Phase 5 | Complete |
| DATA-04 | Phase 5 | Complete |
| DATA-05 | Phase 5 | Complete |
| DATA-06 | Phase 8 | Complete |
| SKILL-01 | Phase 6 | Complete |
| SKILL-02 | Phase 6 | Complete |
| SKILL-03 | Phase 6 | Complete |
| SKILL-04 | Phase 6 | Complete |
| SKILL-05 | Phase 6 | Complete |
| SKILL-06 | Phase 6 | Complete |
| SKILL-07 | Phase 6 | Complete |
| SKILL-08 | Phase 6 | Complete |
| SKILL-09 | Phase 6 | Complete |
| RMTN-01 | Phase 6 | Complete |
| RMTN-02 | Phase 6 | Complete |
| RMTN-03 | Phase 6 | Complete |
| RMTN-04 | Phase 6 | Complete |
| RMTN-05 | Phase 6 | Complete |
| FLOW-01 | Phase 7 | Complete |
| FLOW-02 | Phase 7 | Complete |
| FLOW-03 | Phase 7 | Complete |
| FLOW-04 | Phase 7 | Complete |
| FLOW-05 | Phase 7 | Complete |
| FLOW-06 | Phase 7 | Complete |
| FLOW-07 | Phase 7 | Complete |
| CAL-01 | Phase 7 | Complete |
| CAL-02 | Phase 7 | Complete |
| CAL-03 | Phase 7 | Complete |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0

---

## v2026.4 Requirements — AI Ops (Observabilité Continue)

*Defined: 2026-04-12 — exploration session + Advisor ULTRATHINK (3 passes)*

> **Principes architecturaux validés :**
> - Claude Code = Anthropic OAuth (Max) — pas LiteLLM. Ingestion = batch ETL depuis JSONL post-session.
> - Déclencheur : hook `SessionStop` (ULTIMATE-CONFIG Couche 5) — pas inotify, pas cron.
> - Stratégie : **Langfuse Cloud free tier d'abord** (0€, 50k traces/mois, validation immédiate) + stack maison en parallèle (NocoDB + VictoriaMetrics + Loki + LiteLLM juge). Nouveau serveur dédié uniquement si rétention 30j ou confidentialité deviennent bloquants.
> - Timeline sessions : Loki (déjà dans la stack) via push HTTP structuré — pas Tempo, pas nouveau service.
> - Arize Phoenix : hors scope (valeur marginale pour usage solo batch).
> - LiteLLM : rôle = **juge qualité** (modèle cheap évalue la session après coup), pas capturer les appels.

### Track A — Langfuse Cloud (démarrage immédiat, 0€)

- [ ] **AIOPS-01**: `session-analyst` enhanced — parse JSONL complet, extrait métriques (tokens, coût, tool_calls, bash_évitables, modèle, durée, git_sha CLAUDE.md)
- [ ] **AIOPS-02**: Hook `SessionStop` déclenche `session-analyst` → Langfuse Python SDK → Langfuse Cloud (free tier). Zéro nouveau serveur, rétention 30 jours.
- [ ] **AIOPS-03**: Corrélation git ↔ traces — `session-analyst` lit `git log -1 --format=%h` sur CLAUDE.md/hooks au moment de la session, injecte le sha comme metadata Langfuse.

### Track B — Stack maison (parallèle, 0€, long terme)

- [ ] **AIOPS-04**: `session-analyst` → NocoDB (table `claude_sessions`) — stockage long terme structuré, remplace la limite rétention 30j de Langfuse Cloud.
- [ ] **AIOPS-05**: `session-analyst` → VictoriaMetrics push (remote write) → Grafana dashboard — tokens/jour, coût/jour, bash_évitables/semaine, qualité score tendance.
- [ ] **AIOPS-06**: Grafana Tempo ajouté au monitoring stack Sese-AI (service Docker dans `docker-compose-infra.yml`, ~300MB RAM). `session-analyst` envoie les traces OpenTelemetry (OTLP) → Alloy (déjà en place, receiver OTLP 4317) → Tempo → Grafana datasource. Timeline complète par session : spans par tool call avec durées + relations parent-child. Corrélation Loki↔Tempo via `trace_id`.
- [ ] **AIOPS-07**: n8n workflow `session-quality-eval` — reçoit résumé session depuis `session-analyst`, appelle LiteLLM (deepseek-v3 ou qwen3-coder) comme juge qualité (score 1-10 : complétion tâche, outils inutiles, loops), écrit score dans NocoDB, alerte Telegram si score < 6.
- [ ] **AIOPS-10**: `session-analyst` → Qdrant collection `sessions_v1` — embedding du résumé session (modèle via LiteLLM). Complète NocoDB : NocoDB pour requêtes SQL structurées, Qdrant pour recherche sémantique (*"sessions avec SSH polling loops"*, *"sessions similaires à celle-ci"*). Hook R0 SessionStart peut interroger `sessions_v1` en plus de `memory_v1`.
- [ ] **AIOPS-11**: Gitea webhook (Seko-VPN) sur push CLAUDE.md / hooks → n8n → tag version dans NocoDB + Langfuse (sha court + fichiers modifiés). Corrélation git↔qualité event-driven, remplace le polling `git log` dans `session-analyst`.
- [ ] **AIOPS-12**: OpenClaw skill `session-stats` — requêtes Telegram on-demand : *"qualité sessions cette semaine"*, *"coût IA aujourd'hui"*, *"sessions dégradées ce mois"* → query NocoDB/VictoriaMetrics → réponse formatée dans Telegram.

### Track C — Optionnel, déclenché si besoin confirmé

- [ ] **AIOPS-08**: Langfuse self-hosted (CX32 ou Oracle VM) — déclenché si : rétention 30j bloquante ET stack maison insuffisante, OU données trop sensibles pour Cloud. Prérequis : 4 semaines de données réelles pour décider.
- [ ] **AIOPS-09**: Bac à sable recette apps — serveur permanent pour recette applicative. Décision indépendante de l'AI Ops, peut être un CX22 dédié ou l'Oracle VM si disponible.

---
*Requirements defined: 2026-03-17*
*Last updated: 2026-04-12 — réécriture complète AI Ops après Advisor ULTRATHINK : stack maison + Langfuse Cloud, zéro nouveau serveur obligatoire, Loki pour timeline, LiteLLM comme juge qualité*
