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
- [ ] **DATA-06**: Kitsu project structure mapped (Production=brand, Episode=drop, Sequence=phase, Shot=content, Task=step)

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

- [ ] **FLOW-01**: n8n workflow `brief-to-concept` orchestrates steps 1-5 (brief, research, moodboard, concept, casting)
- [ ] **FLOW-02**: n8n workflow `kitsu-sync` uploads previews and updates task statuses in Kitsu
- [ ] **FLOW-03**: n8n workflow `script-to-storyboard` orchestrates steps 6-8 (script, storyboard, sound design)
- [ ] **FLOW-04**: n8n workflow `generate-assets` dispatches to correct provider per scene
- [ ] **FLOW-05**: n8n workflow `rough-cut` assembles scenes via Remotion
- [ ] **FLOW-06**: n8n workflow `invalidation-engine` handles targeted scene invalidation cascades
- [ ] **FLOW-07**: Kitsu webhooks to n8n integration (task status, comments, preview uploads)

### Remotion

- [ ] **RMTN-01**: Composition `reel-motion-text` (9:16, 15-60s, animated text + gradients)
- [ ] **RMTN-02**: Composition `reel-meme-skit` (9:16, 15-30s, meme/skit format)
- [ ] **RMTN-03**: Composition `reel-feature-showcase` (9:16, 30-60s, product demo + overlays)
- [ ] **RMTN-04**: Composition `reel-teaser` (9:16, 15s, hook + mystery + CTA)
- [ ] **RMTN-05**: All compositions accept `scenes[]`, `brand`, `audio` props

### Calendar

- [ ] **CAL-01**: Editorial calendar visible in Plane (contents = work items with dates)
- [ ] **CAL-02**: Drops organized as Plane cycles
- [ ] **CAL-03**: n8n auto-creates Plane work items from NocoDB content entries

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
| DATA-06 | Phase 5 | Pending |
| SKILL-01 | Phase 6 | Complete |
| SKILL-02 | Phase 6 | Complete |
| SKILL-03 | Phase 6 | Complete |
| SKILL-04 | Phase 6 | Complete |
| SKILL-05 | Phase 6 | Complete |
| SKILL-06 | Phase 6 | Complete |
| SKILL-07 | Phase 6 | Complete |
| SKILL-08 | Phase 6 | Complete |
| SKILL-09 | Phase 6 | Complete |
| RMTN-01 | Phase 6 | Pending |
| RMTN-02 | Phase 6 | Pending |
| RMTN-03 | Phase 6 | Pending |
| RMTN-04 | Phase 6 | Pending |
| RMTN-05 | Phase 6 | Pending |
| FLOW-01 | Phase 7 | Pending |
| FLOW-02 | Phase 7 | Pending |
| FLOW-03 | Phase 7 | Pending |
| FLOW-04 | Phase 7 | Pending |
| FLOW-05 | Phase 7 | Pending |
| FLOW-06 | Phase 7 | Pending |
| FLOW-07 | Phase 7 | Pending |
| CAL-01 | Phase 7 | Pending |
| CAL-02 | Phase 7 | Pending |
| CAL-03 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0

---
*Requirements defined: 2026-03-17*
*Last updated: 2026-03-17 after roadmap creation (all 36 requirements mapped to phases 5-7)*
