# Phase 5: Foundation - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning
**Source:** PRD Express Path (docs/PRD-CONTENT-FACTORY.md)

<domain>
## Phase Boundary

Phase 5 delivers all infrastructure and data layers for the Content Factory pipeline:
1. **Kitsu + Zou** deployed at `boss.ewutelo.cloud` on Sese-AI (Docker Compose, Caddy VPN-only, PostgreSQL shared, monitoring, backup)
2. **NocoDB tables** (`brands`, `contents`, `scenes`) created and populated with Paul Taff brand profile
3. **Qdrant collection** `brand-voice` with embedding pipeline for semantic brand memory
4. **Fal.ai integration** — API key available in n8n environment, test call succeeds
5. **Kitsu project structure** mapped to content pipeline (Production=brand, Episode=drop, Sequence=phase, Shot=content, Task=step)

This phase does NOT include OpenClaw skills, n8n workflows, or Remotion compositions (phases 6-7).

</domain>

<decisions>
## Implementation Decisions

### Kitsu Deployment (INFRA-01, INFRA-02, INFRA-03)
- Kitsu (CGWire) is an open-source production tracking tool (AGPL v3) designed for animation/VFX
- **Architecture**: Zou (Flask/PostgreSQL backend) + Kitsu (Vue.js frontend)
- **Deploy as Docker Compose** on Sese-AI, following VPAI patterns (pinned images, cap_drop ALL, resource limits, healthchecks)
- **PostgreSQL**: Shared instance, new database `kitsu_production`, user `zou` with `{{ postgresql_password }}` (shared password convention)
- **Caddy**: `boss.ewutelo.cloud` reverse proxy, VPN-only ACL (2 CIDRs: VPN + Docker frontend)
- **Images**: Use official CGWire Docker images — pin exact versions in `versions.yml`
- **Resource limits**: Zou ~300MB RAM, Kitsu frontend ~200MB RAM (total <500MB, VPS 8GB shared)
- **Ansible role**: `roles/kitsu/` following existing role patterns (tasks, handlers, defaults, templates)

### Kitsu Monitoring & Backup (INFRA-05, INFRA-06)
- **Healthcheck**: Zou API endpoint `/api/health` or `/api/data/persons` (authenticated)
- **Grafana**: Add Kitsu to existing monitoring dashboard (cAdvisor metrics)
- **Backup**: `kitsu_production` database automatically included in existing Zerobyte PostgreSQL dump (no changes needed if dump covers all DBs)
- **Logs**: stdout/stderr → Loki via Alloy (standard Docker log driver)

### Fal.ai Integration (INFRA-04)
- **API key**: Already added to Ansible vault as `vault_fal_ai_api_key`
- **Variable**: `fal_ai_api_key` in `main.yml` references vault
- **n8n access**: Inject `FAL_KEY` environment variable into n8n container env_file
- **Test**: n8n HTTP Request node to `https://fal.ai/api/v1/models` with API key header

### NocoDB Data Model (DATA-01, DATA-02, DATA-03, DATA-05)
- **Tables created via NocoDB API** (not direct SQL) — idempotent, API token from vault
- **Table `brands`**: name (text), tagline (text), tone (text), palette (json), typography (text), target_audience (text), platforms (json)
- **Table `contents`**: brand_id (FK), kitsu_project_id (text), title (text), format (enum: reel/carousel/post/story/ad), status (enum: brief→concept→script→storyboard→sound→assets→rough→fine→review→adapt→published), current_phase (int 1-4), current_step (int 1-14), brief (json), script (long text), storyboard (json), assets_urls (json), final_url (text), published_at (datetime), instagram_id (text)
- **Table `scenes`**: content_id (FK), scene_number (int), description (text), dialogue (text), screen_text (text), duration_sec (float), transition (text), visual_type (enum: motion_design/ai_generative/stock/meme), provider (enum: remotion/comfyui/fal_ai/seedance/seedream), asset_url (text), version (int), status (enum: draft/validated/invalidated)
- **Paul Taff brand**: name="Paul Taff", tagline="Des agents IA avec du caractere", tone="Decale, sarcastique, audacieux", palette=Flash-Studio colors, target_audience="Dev/founders 25-40, early adopters", platforms=["instagram"]

### Qdrant Brand-Voice Collection (DATA-04)
- **Collection**: `brand-voice` with vector size 1536 (text-embedding-3-small via LiteLLM)
- **Schema**: payload fields — `brand_id`, `content_type` (script/reference/brief), `text`, `created_at`
- **Embedding pipeline**: n8n webhook triggered on script validation in NocoDB → LiteLLM embedding → Qdrant upsert
- **Initial seed**: embed Paul Taff brand description + tone guidelines as first vectors

### Kitsu Project Structure (DATA-06)
- **Via Zou REST API** (Python client Gazu or HTTP requests)
- **Production**: "Paul Taff — Lancement" (brand project)
- **Episode**: "Drop 1" (first content batch)
- **Sequences**: 4 sequences = 4 phases (Pre-production, Ecriture, Production, Post-production)
- **Task types**: 14 task types matching pipeline steps (Brief, Recherche, Moodboard, Concept, Casting, Script, Storyboard, Sound Design, Assets, Rough Cut, Fine Cut, Review, Multi-format, Publication)
- **Task statuses**: todo, wip, pending_review, retake, done, locked, invalidated

### Claude's Discretion
- Exact Kitsu Docker image versions (research latest stable)
- Zou API authentication method for provisioning (API key vs admin credentials)
- NocoDB table creation approach (direct API calls vs n8n workflow)
- Qdrant distance metric for brand-voice (cosine vs dot product)
- Whether to create a dedicated n8n workflow for Qdrant seeding or use direct API calls

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project PRD
- `docs/PRD-CONTENT-FACTORY.md` — Full pipeline design (14 steps, 4 phases, Kitsu mapping, provider costs, data model)

### Infrastructure Patterns
- `CLAUDE.md` — Ansible conventions, Docker patterns, PostgreSQL shared password, Caddy VPN ACL rules
- `TECHNICAL-SPEC.md` — Network architecture (4 Docker networks), resource limits, healthcheck patterns
- `inventory/group_vars/all/versions.yml` — Docker image version pinning
- `inventory/group_vars/all/main.yml` — Variable references (kitsu_subdomain, fal_ai_api_key)
- `inventory/group_vars/all/docker.yml` — Docker daemon config, network definitions
- `docs/GUIDE-CADDY-VPN-ONLY.md` — Caddy VPN ACL patterns (2 CIDRs critical)
- `docs/TROUBLESHOOTING.md` — Known pitfalls by service

### Existing Role Patterns (reference for new Kitsu role)
- `roles/nocodb/` — Similar service pattern (Docker Compose, PostgreSQL shared, Caddy, env_file)
- `roles/plane/` — Latest role pattern (multi-container, provisioning)
- `roles/caddy/templates/Caddyfile.j2` — Caddy config with VPN ACL snippets

### Data Layer
- `inventory/group_vars/all/secrets.yml` — Vault with fal_ai_api_key, nocodb_api_token, qdrant_api_key

</canonical_refs>

<specifics>
## Specific Ideas

- Kitsu official Docker: `cgwire/cgwire` (all-in-one) or separate `cgwire/kitsu` + `cgwire/zou`
- Zou default port: 5000 (Flask), Kitsu frontend: 80 (nginx)
- Gazu Python client available for Zou API scripting: `pip install gazu`
- NocoDB API base: `https://hq.ewutelo.cloud/api/v2/` with `xc-token` header
- Qdrant API: `https://qd.ewutelo.cloud` with `api-key` header
- Existing Qdrant collections: `semantic_cache`, `content_index` — add `brand-voice` alongside

</specifics>

<deferred>
## Deferred Ideas

- ElevenLabs voiceover integration (Phase 2+, user request to skip)
- Instagram Graph API auto-publishing (Phase 3)
- Kitsu custom statuses beyond standard (can be added later via API)
- Kitsu webhook configuration (Phase 7, FLOW-07)

</deferred>

---

*Phase: 05-foundation*
*Context gathered: 2026-03-17 via PRD Express Path*
