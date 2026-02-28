# External Integrations

**Analysis Date:** 2026-02-28

## APIs & External Services

**AI Model Providers (LiteLLM routing):**
- Anthropic (Claude) - Primary reasoning model
  - SDK/Client: LiteLLM router
  - Auth: `{{ vault_anthropic_api_key }}`
  - Budget: $0.75/day (15% of $5 daily cap)

- OpenAI (GPT-4o, etc.) - Fast inference models
  - SDK/Client: LiteLLM router
  - Auth: `{{ vault_openai_api_key }}`
  - Budget: $0.50/day (10% of $5 daily cap)

- OpenRouter (multi-provider aggregator) - 65% cost allocation
  - SDK/Client: LiteLLM router
  - Auth: `{{ vault_openrouter_api_key }}`
  - Models: Claude Opus/Sonnet, DeepSeek, Qwen, GLM via OpenRouter
  - Budget: $3.25/day (65% of $5 daily cap)

- Google Gemini - Multimodal models
  - SDK/Client: LiteLLM router
  - Auth: `{{ vault_google_gemini_api_key }}`
  - Budget: $0.25/day (5% of $5 daily cap)

- BytePlus (Seedance) - Video processing (monthly budget, separate)
  - SDK/Client: LiteLLM router
  - Auth: `{{ vault_byteplus_api_key }}`
  - Budget: $5.00/month (separate from daily $5 cap)

- Brave Search - Web search results for RAG
  - SDK/Client: LiteLLM context
  - Auth: `{{ vault_brave_search_api_key }}`

**Cost Monitoring:**
- Budget enforcement: LiteLLM `general_settings.max_budget: 5.00` + `budget_duration: "1d"`
- Alert thresholds: 70% warning (Telegram), 90% critical (auto eco-mode switch)
- Redis key: `litellm:budget:mode` (normal | eco | blocked)
- Eco models (always available): qwen3-coder, deepseek-v3, glm-5

**Communication:**
- Telegram Monitoring Bot - System alerts (uptime, CPU, disk)
  - Token: `{{ vault_telegram_monitoring_bot_token }}`
  - Chat ID: `{{ vault_telegram_monitoring_chat_id }}`

- Telegram OpenClaw Bot - Agent activity notifications
  - Token: `{{ vault_telegram_openclaw_bot_token }}`
  - Chat ID: `{{ vault_telegram_openclaw_chat_id }}`

## Data Storage

**Databases:**
- PostgreSQL 18.1 - Primary relational store
  - Connection: `postgresql://postgres:{{ postgresql_password }}@postgresql:5432`
  - Client: community.postgresql collection
  - Shared password: **All database users (n8n, litellm, nocodb, sure) use `{{ postgresql_password }}`**
  - Databases: n8n, litellm, nocodb, sure (separate DBs in single PG instance)

- Redis 8.0 - Session store and semantic cache
  - Connection: `redis://:{{ redis_password }}@redis:6379`
  - Client: Redis 8.0 CLI
  - Usage: n8n sessions, LiteLLM cache (exact match via Redis + semantic via Qdrant)

- Qdrant v1.16.3 - Vector database (semantic cache + RAG)
  - Connection: `http://qdrant:6333`
  - API Key: `{{ vault_qdrant_api_key }}`
  - Collections: `semantic_cache`, `content_index`
  - Embedding model: text-embedding-3-small (1536 dims)

**File Storage:**
- Hetzner Object Storage (S3-compatible) fsn1 region
  - Endpoint: `{{ s3_endpoint }}` (fsn1.your-objectstorage.com)
  - Buckets:
    - `{{ s3_bucket_backups }}` - Zerobyte backup archive (daily)
    - `{{ s3_bucket_shared }}` - NocoDB attachments (nc-attachments/ prefix)
  - Access: `{{ s3_access_key }}` / `{{ s3_secret_key }}`
  - Used by: NocoDB file uploads, Zerobyte incremental backups

**Local Data (on-disk):**
- `/opt/{{ project_name }}/data/` - All persistent volumes
  - postgresql/ - Database files
  - redis/ - dump.rdb (RDB snapshots)
  - qdrant/ - Vector data and snapshots
  - n8n/ - Workflows, credentials, execution history
  - openclaw/ - Agent state, sessions, memory
  - grafana/ - Dashboard definitions
  - couchdb/ - Obsidian LiveSync vault (Seko-VPN only)

**CouchDB (Obsidian LiveSync):**
- Provider: CouchDB 3.3.3 (on Seko-VPN)
- Admin user: `{{ vault_couchdb_admin_user }}`
- Admin password: `{{ vault_couchdb_admin_password }}`
- Obsidian user: `couchdb_obsidian_user` / `{{ vault_couchdb_obsidian_password }}`
- Database: `obsidian_vault`
- Sync target: iOS + Windows Obsidian clients via LiveSync plugin
- Public HTTPS: `https://{{ obsidian_subdomain }}.{{ domain_name }}` (no VPN required)

## Authentication & Identity

**Auth Provider:**
- Custom per application (no centralized OAuth)

**n8n:**
- Implementation: Database-backed (PostgreSQL)
- Owner provisioning: Email, first/last name, password (first deploy only)
- Password: `{{ vault_n8n_owner_password }}`
- Encryption key: `{{ vault_n8n_encryption_key }}` (32-char hex)

**LiteLLM:**
- Implementation: User/password basic auth for UI
- UI credentials: `{{ vault_litellm_ui_username }}` / `{{ vault_litellm_ui_password }}`
- Master key: `{{ vault_litellm_master_key }}` (for API access)
- Salt key: `{{ vault_litellm_salt_key }}`
- VPN-only access: Admin UI at `https://{{ litellm_subdomain }}.{{ domain_name }}`

**OpenClaw:**
- Implementation: Gateway token-based
- API Key: `{{ vault_openclaw_api_key }}`
- Gateway Token: `{{ vault_openclaw_gateway_token }}` (defaults to API key if not set)
- VPN-only access: Control UI at `https://{{ admin_subdomain }}.{{ domain_name }}`

**Qdrant:**
- Implementation: API key-based
- API Key: `{{ vault_qdrant_api_key }}`
- VPN-only access: Dashboard at `https://{{ qdrant_subdomain }}.{{ domain_name }}`

**NocoDB:**
- Implementation: JWT token-based
- JWT Secret: `{{ vault_nocodb_jwt_secret }}`
- API Token: `{{ vault_nocodb_api_token }}`
- Database auth: Uses `{{ postgresql_password }}` (shared PG password)
- S3 credentials for file uploads: `{{ s3_access_key }}` / `{{ s3_secret_key }}`
- VPN-only access: UI at `https://{{ nocodb_subdomain }}.{{ domain_name }}`

**Grafana:**
- Implementation: Admin user/password
- Admin user: `{{ vault_grafana_admin_user }}`
- Admin password: `{{ vault_grafana_admin_password }}`
- VPN-only access: Dashboard at `https://{{ grafana_subdomain }}.{{ domain_name }}`

**Sure (Personal Finance):**
- Implementation: Rails session-based
- Secret key base: `{{ vault_sure_secret_key_base }}`
- Database password: Uses `{{ postgresql_password }}` (shared PG password)
- API key (for integrations): `{{ vault_sure_api_key }}`

## Monitoring & Observability

**Error Tracking:**
- None configured - Fallback to Docker logs + Loki aggregation

**Logs:**
- Loki 3.6.5 (centralized log aggregation)
- Alloy v1.13.0 (log collector agent)
- Docker log driver: json-file with 10m max-size, 3 file rotation
- Exported to Grafana Loki for querying

**Metrics:**
- VictoriaMetrics v1.135.0 (time-series storage)
- Alloy v1.13.0 (metrics scraper)
- cAdvisor 0.55.1 (container CPU/memory metrics)
- node_exporter (Workstation Pi system metrics)
- Exported to Grafana for visualization

**Health Checks:**
- Container healthchecks in docker-compose (10-30s intervals)
- PostgreSQL: `pg_isready` check (start_period: 120s)
- Redis: PING via redis-cli
- Qdrant: TCP port 6333 check
- n8n: HTTP GET http://127.0.0.1:5678/
- LiteLLM: HTTP GET with bearer token auth
- All services: Grafana alerting rules

**Uptime Monitoring:**
- Uptime Kuma (external monitoring service on Tailscale mesh)
- Heartbeat URL: `{{ vault_backup_heartbeat_url }}`
- Monitored endpoints: Health check endpoints on prod domain

## CI/CD & Deployment

**Hosting:**
- Sese-AI (OVH VPS) - Production
- Seko-VPN (Ionos) - VPN hub + Obsidian CouchDB
- Waza (RPi5) - Workstation/Mission Control
- Prod Apps (Hetzner CX22) - Application deployment server
- Preprod (Hetzner ephemeral) - Testing

**CI Pipeline:**
- GitHub Actions (3 workflows)
  - `.github/workflows/ci.yml` - Lint (yamllint + ansible-lint) + Molecule tests
  - `.github/workflows/deploy-preprod.yml` - Auto-deploy to preprod on push to main
  - `.github/workflows/deploy-prod.yml` - Manual production deployment (requires approval)
- Smoke tests: Curl-based endpoint validation (site:// and VPN healthchecks)

**IaC Management:**
- Git repository: `git@github-seko:Mobutoo/VPAI.git` (SSH-only, private)
- Default branch: main
- Deployment: `make deploy-prod` (manual + confirmation prompt)

**Hetzner Cloud Integration:**
- Provider: hcloud collection (ansible.hcloud)
- Auto-provisioning: Playbook `playbooks/provision-hetzner.yml`
- Server type: CX22 (app-prod server)
- Image: Ubuntu 24.04
- Location: fsn1 (Nuremberg)
- SSH key provisioning: `{{ deploy_ssh_key_name }}-deploy` (created at init)

**GitHub Webhooks:**
- Auto-fix pipeline: GitHub Issues → Claude Code → Auto-PR
- Webhook secret: `{{ vault_github_webhook_secret }}`
- Label: `auto-fix` (triggers on labeled issues)
- Target repos: VPAI (+ archived kaneo-vpai reference)

## Environment Configuration

**Required env vars:**
- All secrets stored in `inventory/group_vars/all/secrets.yml` (Ansible Vault, never committed)
- Production deployment requires vault password file: `.vault_password`
- OVH API credentials (DNS-01): `OVH_ENDPOINT`, `OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`, `OVH_CONSUMER_KEY`
- PostgreSQL shared password: `{{ postgresql_password }}`
- Redis password: `{{ redis_password }}`
- Qdrant API key: `{{ vault_qdrant_api_key }}`
- All AI provider keys: anthropic, openai, openrouter, google, byteplus, brave
- Telegram bot tokens and chat IDs (2 bots: monitoring + openclaw)

**Secrets location:**
- Ansible Vault: `inventory/group_vars/all/secrets.yml` (encrypted, loaded by ansible-vault)
- Never in `.env` files (except for template expansion)
- Passed to containers via `env_file` directive (expanded from vault at deploy time)
- SSH keys: `~/.ssh/seko-vpn-deploy` (private key for all servers)

**S3 Credentials:**
- Access key: `{{ vault_s3_access_key }}`
- Secret key: `{{ vault_s3_secret_key }}`
- Region: fsn1
- Endpoint: fsn1.your-objectstorage.com
- Used by: Zerobyte (backup), NocoDB (file attachments)

## Webhooks & Callbacks

**Incoming Webhooks:**
- n8n webhook ingress: `http://{{ n8n_subdomain }}.{{ domain_name }}/webhook/` (Caddy-proxied)
- Meta Graph API webhooks: `hook.{{ domain_name }}` via webhook-relay (Seko-VPN port 80/443 → VPN mesh → VPS)
- OpenClaw agent callbacks: n8n-integrated triggers

**Outgoing Webhooks:**
- n8n → OpenClaw: HTTP POST to `{{ openclaw_gateway_url }}` (internal, encrypted with token)
- Telegram alerts: Outbound to Telegram API (via egress network)
- GitHub auto-fix: Outbound to GitHub API (create PRs, close issues)
- Zerobyte backup: Outbound to Hetzner S3 API
- Uptime Kuma heartbeat: Outbound to heartbeat URL (tunnel via Tailscale)

**Webhook Relay Architecture:**
- Location: Seko-VPN (Ionos, IP 87.106.30.160)
- Caddy reverse proxy: `hook.{{ domain_name }}` → Tailscale mesh → VPS (Sese-AI)
- No Cloudflare Tunnel - 100% self-hosted via Headscale mesh
- DNS A record required: `hook.{{ domain_name }}` → `{{ vault_vpn_server_public_ip }}`

## Network Isolation

**Docker Networks (4 named networks + 1 egress):**
- `frontend` (172.20.1.0/24) - Caddy, Grafana (internet-accessible)
- `backend` (172.20.2.0/24, internal) - PostgreSQL, Redis, Qdrant, n8n, LiteLLM, OpenClaw, NocoDB (no outbound)
- `monitoring` (172.20.3.0/24, internal) - VictoriaMetrics, Loki, Alloy (metrics/logs only)
- `egress` (172.20.4.0/24) - n8n, LiteLLM, OpenClaw (outbound internet for APIs)
- `sandbox` (172.20.5.0/24, internal) - OpenClaw sub-agents (isolated execution)

**VPN Mesh:**
- Headscale server: Seko-VPN (87.106.30.160)
- Network CIDR: 100.64.0.0/10 (Tailscale IP range)
- Members: Sese-AI (VPS), Seko-VPN (hub), Waza (RPi), operators' machines
- VPN enforcement: Caddy ACL rules require 2 CIDRs (`{{ caddy_vpn_cidr }}` + `{{ caddy_docker_frontend_cidr }}`)

**Firewall:**
- UFW on all hosts - explicit allow rules only
- Public ports: 80 (redirect), 443 (HTTPS TLS)
- SSH: Custom port 804 (prod), accessible only via Tailscale after hardening
- Internal: Docker networks, Tailscale mesh

---

*Integration audit: 2026-02-28*
