# Content Factory — Pipeline de Creation de Contenu Automatise

## What This Is

Un pipeline automatise de creation de contenu pour les reseaux sociaux, pilote par Telegram (via OpenClaw) et suivi visuellement dans Kitsu (CGWire). Le systeme est multi-projet : le premier cas d'usage est la production de videos virales pour le lancement de **Paul Taff** (Flash Studio — plateforme IaaS, agents IA ton decale) sur Instagram.

Deploye sur l'ecosysteme VPAI existant : Kitsu + n8n + OpenClaw sur Sese-AI, ComfyUI + Remotion sur Waza, providers cloud (Fal.ai, Seedance, Seedream).

## Core Value

**Produire du contenu de qualite studio avec un workflow professionnel (14 etapes, 4 gates) pilotable depuis Telegram, avec invalidation ciblee par scene pour permettre les allers-retours creatifs sans tout reconstruire.**

## Current Milestone: v2026.3 Content Factory

**Goal:** Deployer l'infrastructure Content Factory (Kitsu, tables NocoDB, collection Qdrant, skill OpenClaw content-director, workflows n8n) et produire les premiers contenus pour Paul Taff.

**Target features:**
- Deploy Kitsu (CGWire) production tracking at `boss.ewutelo.cloud`
- Integrate Fal.ai as multi-model provider in n8n creative workflows
- Create NocoDB data model (brands, contents, scenes)
- Configure Qdrant brand-voice semantic memory
- Build OpenClaw content-director skill with Telegram topic 7 commands
- Build n8n orchestration workflows (brief-to-concept, kitsu-sync)
- Create Remotion Instagram compositions (motion-text, meme, feature-showcase, teaser)
- Implement full production pipeline (storyboard, asset generation, rough cut, fine cut)
- Enable editorial calendar in Plane

## Requirements

### Validated

- Plane deployed on `work.ewutelo.cloud` (operational, project Content Factory created)
- NocoDB deployed on `hq.ewutelo.cloud` (operational)
- Qdrant deployed on `qd.ewutelo.cloud` (operational, existing collections)
- OpenClaw deployed with Telegram topic routing (operational)
- n8n deployed with creative-pipeline and content-generate workflows (operational)
- ComfyUI deployed on Waza (operational)
- Remotion deployed on Waza (operational, HelloWorld only)
- LiteLLM budget system with Telegram alerts (operational)

### Active

- [ ] Kitsu + Zou deployed at `boss.ewutelo.cloud` (Sese-AI)
- [ ] Fal.ai integrated as provider in n8n + LiteLLM
- [ ] NocoDB tables: brands, contents, scenes
- [ ] Qdrant collection `brand-voice` with embedding pipeline
- [ ] OpenClaw skill `content-director` with Telegram topic 7
- [ ] Telegram commands: /content, /ok, /adjust, /back, /preview, /impact, /drop
- [ ] Gate commands: /lock-preprod, /lock-script, /ok-rough, /ok-final, /published
- [ ] n8n workflow `brief-to-concept` (pipeline steps 1-5)
- [ ] n8n workflow `kitsu-sync` (upload previews, update statuses)
- [ ] n8n workflow `script-to-storyboard` (steps 6-8)
- [ ] n8n workflow `generate-assets` (multi-provider dispatch per scene)
- [ ] n8n workflow `rough-cut` (Remotion assembly)
- [ ] n8n workflow `invalidation-engine` (targeted scene invalidation)
- [ ] Remotion compositions: reel-motion-text, reel-meme-skit, reel-feature-showcase, reel-teaser
- [ ] Scene-level invalidation mechanics (modify step N, only downstream dependents invalidated)
- [ ] Kitsu webhooks → n8n (task status, comments, previews)
- [ ] Editorial calendar visible in Plane (contents = work items, drops = cycles)
- [ ] Brand profile Paul Taff in NocoDB (Flash-Studio colors, sarcastic tone)

### Out of Scope

- **ElevenLabs voiceover** — Skip in Phase 1, defer to Phase 2+
- **Instagram Graph API auto-publish** — Manual publish first (Phase 3)
- **TikTok/LinkedIn/X/YouTube Shorts** — Instagram only for v1
- **Analytics feedback loop** — No Instagram API metrics integration yet
- **Ad spot pipeline** — Organic content first
- **Multi-format adaptation (step 13)** — Phase 3
- **Mobile app** — Telegram + Kitsu web UI only

## Context

**PRD:** `docs/PRD-CONTENT-FACTORY.md` (672 lines, committed `4c7cbe2`)

**Plane project:** Content Factory (`e0cb95f0-0ea5-41b8-a3e3-aec45e8cc37e`)
- Phase 1 module: `c04ac29e-9842-4eec-8ff6-6923e9fe75d7` (Fondations, Mar 17-31)
- Phase 2 module: `0ff668ce-cf0d-40a7-82bc-1e2de4a50fe3` (Production, Apr 1-14)
- Phase 3 module: `2347a591-77ad-4c52-ba68-786100353dad` (Autonomie, Apr 15-30)

**Architecture:**
- Kitsu = production tracking board (vue globale, annotations, previews)
- n8n = orchestrateur central (workflows, dispatch providers, sync)
- OpenClaw = cerveau creatif (skill content-director, raisonnement, Telegram)
- Providers = ComfyUI/Remotion (local Waza, gratuit) + Fal.ai/Seedance/Seedream (cloud, payant)

**Brand:** Paul Taff — Flash Studio IaaS platform with sarcastic AI agents
- Colors: Flash-Studio palette (TBD precise values)
- Tone: Decale, sarcastique, audacieux
- Target: Dev/founders 25-40, early adopters
- Platform: Instagram (Reels, Stories, Carousels)

**Provider keys:**
- Fal.ai: added to vault as `vault_fal_ai_api_key`
- Telegram topic: 7 (content-director)
- Kitsu subdomain: `boss.ewutelo.cloud`

## Constraints

- **Tech stack**: Ansible + Docker Compose (pattern VPAI), all on Sese-AI + Waza
- **Memory**: Kitsu + Zou < 500MB RAM (VPS 8GB shared with 20+ services)
- **Budget**: $5/day LiteLLM hard cap for LLM; Fal.ai separate budget
- **PostgreSQL**: Shared instance, new DB `kitsu_production` for Zou
- **Network**: VPN-only for Kitsu UI (Caddy ACL standard)
- **Versions**: All Docker images pinned in versions.yml
- **Local providers first**: ComfyUI + Remotion (free) before cloud providers (paid)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **Kitsu (CGWire) as production tracker** | Open-source (AGPL v3), designed for animation/VFX production, REST API, webhooks, Vue.js UI. Maps perfectly to content pipeline. | — Pending |
| **Kitsu on Sese-AI (not Waza)** | Needs to be accessible via VPN from anywhere, close to PostgreSQL/n8n/OpenClaw. Waza is local-only. | — Pending |
| **NocoDB as source of truth (not Kitsu)** | Kitsu = tracking/preview board. NocoDB = CRUD, calendar, structured data. Avoids Kitsu lock-in. | — Pending |
| **Dual storage NocoDB + Qdrant** | NocoDB for CRUD/status, Qdrant for semantic search/brand-voice memory. Each does what it does best. | — Pending |
| **Scene-level invalidation** | Modify step N → only downstream dependents invalidated, not full rebuild. Critical for creative iteration. | — Pending |
| **Telegram as primary pilot** | Mobile-friendly, instant, integrated with OpenClaw. Kitsu for detailed review only. | — Pending |
| **Skip ElevenLabs Phase 1** | User request. Voiceover via Fal.ai TTS or text-only content first. | — Pending |
| **Fal.ai for multi-model access** | Single API key gives access to Kling, Minimax, HunyuanVideo, Flux. Complements local providers. | — Pending |

---
*Last updated: 2026-03-17 after Content Factory milestone start*
