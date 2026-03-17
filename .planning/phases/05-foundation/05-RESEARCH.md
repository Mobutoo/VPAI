# Phase 5: Foundation - Research

**Researched:** 2026-03-17
**Domain:** Kitsu/Zou deployment, NocoDB API provisioning, Qdrant collection seeding, Fal.ai n8n integration
**Confidence:** HIGH (infrastructure patterns from codebase), MEDIUM (CGWire Docker behavior)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Kitsu (CGWire) deployed as Docker Compose on Sese-AI, following VPAI patterns (pinned images, cap_drop ALL, resource limits, healthchecks)
- PostgreSQL: Shared instance, new database `kitsu_production`, user `zou` with `{{ postgresql_password }}` (shared password convention)
- Caddy: `boss.ewutelo.cloud` reverse proxy, VPN-only ACL (2 CIDRs: VPN + Docker frontend)
- Images: Official CGWire Docker images, versions pinned in `versions.yml`
- Resource limits: Zou ~300MB RAM, Kitsu frontend ~200MB RAM (total <500MB)
- Ansible role: `roles/kitsu/` following existing role patterns (tasks, handlers, defaults, templates)
- Healthcheck: Zou API endpoint `/api/health` or `/api/data/persons`
- Grafana: Add Kitsu to existing monitoring (cAdvisor metrics)
- Backup: `kitsu_production` database included in Zerobyte PostgreSQL dump
- Logs: stdout/stderr via Loki/Alloy (standard Docker log driver)
- Fal.ai: Inject `FAL_KEY` into n8n container env_file (vault key `vault_fal_ai_api_key`, variable `fal_ai_api_key`)
- NocoDB tables created via NocoDB API (not direct SQL) — idempotent, token from vault
- Tables: `brands`, `contents`, `scenes` with exact field definitions (see CONTEXT.md)
- Paul Taff brand profile: specific values defined
- Qdrant collection `brand-voice`: vector size 1536, cosine/dot TBD, payload fields defined
- Kitsu project structure via Zou REST API (Gazu Python client or HTTP requests)

### Claude's Discretion

- Exact Kitsu Docker image versions (research latest stable)
- Zou API authentication method for provisioning (API key vs admin credentials)
- NocoDB table creation approach (direct API calls vs n8n workflow)
- Qdrant distance metric for brand-voice (cosine vs dot product)
- Whether to create a dedicated n8n workflow for Qdrant seeding or use direct API calls

### Deferred Ideas (OUT OF SCOPE)

- ElevenLabs voiceover integration (Phase 2+)
- Instagram Graph API auto-publishing (Phase 3)
- Kitsu custom statuses beyond standard
- Kitsu webhook configuration (Phase 7, FLOW-07)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | Kitsu + Zou deployed at `boss.ewutelo.cloud` via Docker Compose on Sese-AI | cgwire/cgwire:1.0.17 all-in-one image; supervisord config override needed for external PG |
| INFRA-02 | Kitsu PostgreSQL database `kitsu_production` provisioned in shared instance | Add to provision-postgresql.sh.j2 pattern (docker exec + psql CREATE DATABASE) |
| INFRA-03 | Caddy reverse proxy with VPN-only ACL for Kitsu | Standard `import vpn_only` + `reverse_proxy zou:80` pattern in Caddyfile.j2 |
| INFRA-04 | Fal.ai API key integrated in Ansible vault and available to n8n | `FAL_KEY={{ fal_ai_api_key }}` in n8n.env.j2 (existing var in main.yml) |
| INFRA-05 | Kitsu healthcheck monitored in Grafana | cAdvisor autodiscovery; add Alloy scrape config for zou container metrics |
| INFRA-06 | Kitsu backup included in daily Zerobyte PostgreSQL dump | Extend pre-backup.sh.j2 loop to include `kitsu_production` DB |
| DATA-01 | NocoDB table `brands` with profile fields | NocoDB v2 API: POST /api/v2/meta/tables with field definitions |
| DATA-02 | NocoDB table `contents` with 14-step pipeline tracking | NocoDB v2 API: complex table with FK to brands, enum fields |
| DATA-03 | NocoDB table `scenes` with per-scene data | NocoDB v2 API: FK to contents, enum fields for provider/visual_type |
| DATA-04 | Qdrant collection `brand-voice` with embedding pipeline | Qdrant REST API: PUT /collections/brand-voice; recommend cosine distance |
| DATA-05 | Brand profile "Paul Taff" created | NocoDB v2 API: POST row to brands table after table creation |
| DATA-06 | Kitsu project structure mapped | Zou REST API: create production/episode/sequences/task-types via HTTP |
</phase_requirements>

---

## Summary

Phase 5 deploys three independent infrastructure layers on Sese-AI and configures data foundations for the Content Factory pipeline.

**Layer 1 — Kitsu Infrastructure:** The official `cgwire/cgwire` all-in-one image (version 1.0.17, updated 2026-03-14) bundles Zou (Flask API), Kitsu (Vue.js frontend), nginx, internal PostgreSQL, and Redis under supervisord. **Critical constraint:** the image's internal supervisord config hardcodes `DB_USERNAME=root,DB_PASSWORD=''` for the gunicorn processes, which overrides Docker env vars for those two variables. To use the shared VPAI PostgreSQL, we must mount a custom supervisord.conf that removes those overrides. The image exposes port 80 (nginx serving both Kitsu frontend and proxying `/api` to Zou on 5000). Caddy reverse proxies to the container's port 80.

**Layer 2 — Data model:** NocoDB tables are created idempotently via the NocoDB v2 REST API using the existing `nocodb_api_token` from vault. The Qdrant `brand-voice` collection is created via Qdrant's REST API (cosine distance recommended for normalized text embeddings). Seeding Paul Taff brand profile is a single API call after table creation. Kitsu project structure is provisioned via Zou REST API (HTTP calls, no external dependencies).

**Layer 3 — Integration:** Fal.ai key injection into n8n requires a single line addition to `n8n.env.j2`. Backup extension requires adding `kitsu_production` to the pre-backup.sh.j2 database loop.

**Primary recommendation:** Create `roles/kitsu/` with a custom supervisord config override, deploy using `cgwire/cgwire:1.0.17`, mount zou.env file, and create a `roles/kitsu-provision/` for data seeding.

---

## Standard Stack

### Core
| Library/Image | Version | Purpose | Why Standard |
|---------------|---------|---------|--------------|
| `cgwire/cgwire` | `1.0.17` | All-in-one Kitsu+Zou container | Official CGWire Docker image, latest stable (2026-03-14) |
| Zou (embedded) | `1.0.18` | REST API backend (Flask + PostgreSQL) | Embedded in cgwire/cgwire:1.0.17 |
| Kitsu (embedded) | `1.0.17` | Vue.js project tracking frontend | Embedded in cgwire/cgwire:1.0.17 |
| PostgreSQL (shared) | `18.1-bookworm` | Database for `kitsu_production` | VPAI shared instance convention |
| NocoDB v2 API | `0.301.2` (deployed) | Table/row creation | Already deployed, use existing token |
| Qdrant REST API | `v1.16.3` (deployed) | Collection management | Already deployed, use existing key |

### Docker Image Version
```yaml
# To add to inventory/group_vars/all/versions.yml
kitsu_image: "cgwire/cgwire:1.0.17"
```

### Zou Environment Variables (CRITICAL)
| Variable | Default | VPAI Override |
|----------|---------|---------------|
| `DB_HOST` | `localhost` | `postgresql` (Docker service name) |
| `DB_PORT` | `5432` | `5432` |
| `DB_USERNAME` | `postgres` | `zou` |
| `DB_PASSWORD` | `mysecretpassword` | `{{ postgresql_password }}` |
| `DB_DATABASE` | `zoudb` | `kitsu_production` |
| `KV_HOST` | `localhost` | `redis` (Docker service name) |
| `KV_PASSWORD` | `None` | `{{ redis_password }}` |
| `SECRET_KEY` | `mysecretkey` | `{{ kitsu_secret_key }}` (new vault var) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `cgwire/cgwire` all-in-one | Separate Zou + Kitsu containers | More control but no official separate images on Docker Hub |
| Custom supervisord override | Accept embedded PG (ignore shared DB rule) | Violates locked VPAI decision |
| Ansible URI module | Shell script for NocoDB API | URI module is idempotent but complex for multi-step; shell script with idempotency check is cleaner |

---

## Architecture Patterns

### Critical: Supervisord Override for External PostgreSQL

The `cgwire/cgwire` image uses supervisord to manage processes. The gunicorn program block has:
```ini
[program:gunicorn]
environment=PREVIEW_FOLDER=/opt/zou/previews,DB_USERNAME=root,DB_PASSWORD=''
```

These `environment` directives **override Docker env vars** for those specific keys within the supervised process. To use the external shared PostgreSQL, mount a custom supervisord.conf that removes the `DB_USERNAME` and `DB_PASSWORD` from the gunicorn program block:

```ini
# Custom supervisord.conf override — replaces DB_USERNAME/DB_PASSWORD env in gunicorn
[program:gunicorn]
environment=PREVIEW_FOLDER=/opt/zou/previews
command=/opt/zou/env/bin/gunicorn -c /etc/zou/gunicorn.py -b 127.0.0.1:5000 --chdir /opt/zou/zou zou.app:app
directory=/opt/zou
autostart=true
autorestart=true
stdout_logfile=NONE
stderr_logfile=NONE
```

This allows Docker env vars (`DB_HOST=postgresql`, `DB_USERNAME=zou`, `DB_PASSWORD={{ postgresql_password }}`, `DB_DATABASE=kitsu_production`) to flow through to Zou's `config.py`.

### Important: Internal Redis vs External Redis

The `cgwire/cgwire` image also starts an internal Redis. Zou uses Redis for event streaming (KV_HOST). Options:
1. **Use external VPAI Redis** (set `KV_HOST=redis` and `KV_PASSWORD={{ redis_password }}`) — requires also patching the supervisord redis program or disabling it. **Recommended.**
2. **Accept internal Redis** — simpler but wastes resources and violates VPAI isolation. Not recommended.

To disable the internal Redis in supervisord and use external: set `KV_HOST=redis` in the Docker env and also patch the supervisord.conf to remove/disable the `[program:redis]` section.

### Recommended Project Structure for roles/kitsu/

```
roles/kitsu/
├── defaults/
│   └── main.yml          # kitsu_config_dir, kitsu_data_dir, ports, memory limits
├── handlers/
│   └── main.yml          # "Restart kitsu stack" → docker compose restart
├── meta/
│   └── main.yml          # role metadata
├── molecule/
│   └── default/          # molecule tests (converge, verify, molecule.yml)
├── tasks/
│   └── main.yml          # dirs, env file, supervisord override, notify handler
└── templates/
    ├── kitsu.env.j2       # Zou env vars (DB_HOST, KV_HOST, SECRET_KEY, etc.)
    └── supervisord.conf.j2  # Override: removes DB_USERNAME/DB_PASSWORD from gunicorn block
```

```
roles/kitsu-provision/
├── tasks/
│   └── main.yml          # Wait for health, create admin, create project structure
└── templates/
    └── provision-kitsu.sh.j2  # Bash script using zou CLI or HTTP
```

### Docker Compose Entry for Kitsu

Location: add to `docker-compose.yml.j2` (Phase B, application layer).

```yaml
  kitsu:
    image: {{ kitsu_image }}
    container_name: {{ project_name }}_kitsu
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
      - DAC_OVERRIDE
      - FOWNER
    env_file:
      - /opt/{{ project_name }}/configs/kitsu/kitsu.env
    volumes:
      - /opt/{{ project_name }}/data/kitsu/previews:/opt/zou/previews
      - /opt/{{ project_name }}/configs/kitsu/supervisord.conf:/etc/supervisord.conf:ro
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: {{ kitsu_memory_limit }}
          cpus: "{{ kitsu_cpu_limit }}"
        reservations:
          memory: {{ kitsu_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://127.0.0.1/api/data/persons | grep -q 'id' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s
```

NOTE: kitsu runs on port 80 internally (nginx). Caddy reverse_proxy points to `kitsu:80`.

### Caddy VPN Block for Kitsu

Add to `Caddyfile.j2` following the existing pattern:

```
# === Kitsu (boss.<domain>) ===
{% if kitsu_subdomain | default('') | length > 0 %}
{{ kitsu_subdomain }}.{{ domain_name }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy kitsu:80

    import security_headers
}
{% endif %}
```

Also add to `caddy/defaults/main.yml`:
```yaml
caddy_kitsu_domain: "{{ kitsu_subdomain | default('boss') }}.{{ domain_name }}"
```

### PostgreSQL Provisioning

The `kitsu_production` database must be created in the shared PostgreSQL. Two places to add:

1. **`init.sql.j2`** — for fresh deployments (already creates other DBs):
```sql
CREATE DATABASE kitsu_production;
CREATE USER zou WITH ENCRYPTED PASSWORD '{{ postgresql_password }}';
GRANT ALL PRIVILEGES ON DATABASE kitsu_production TO zou;
ALTER DATABASE kitsu_production OWNER TO zou;
\c kitsu_production
GRANT ALL ON SCHEMA public TO zou;
```

2. **`provision-postgresql.sh.j2`** — for idempotent provisioning on existing deployments (add `kitsu_production` to the loop or as a standalone block, similar to how `plane_production` is handled).

### NocoDB Table Creation Pattern

Use Ansible `uri` module for idempotency (check-then-create pattern), following the `plane-provision` pattern:

```yaml
# Check if table exists
- name: Check if brands table exists in NocoDB
  ansible.builtin.uri:
    url: "https://{{ nocodb_subdomain }}.{{ domain_name }}/api/v2/meta/tables"
    method: GET
    headers:
      xc-token: "{{ nocodb_api_token }}"
    ...
  register: nocodb_tables_check

# Create table if not exists
- name: Create brands table in NocoDB
  ansible.builtin.uri:
    url: "https://{{ nocodb_subdomain }}.{{ domain_name }}/api/v2/meta/tables"
    method: POST
    headers:
      xc-token: "{{ nocodb_api_token }}"
    body_format: json
    body:
      title: "brands"
      columns: [...]
    status_code: [200, 201]
  when: brands_table_not_found
```

**Alternative (simpler, recommended for complexity):** Use a bash script template (`provision-nocodb.sh.j2`) that calls the NocoDB API via curl with idempotency checks (similar to `provision-plane.sh.j2`). This is more readable for the 3-table setup with FK relationships.

### Qdrant Collection Creation

```yaml
- name: Create brand-voice Qdrant collection
  ansible.builtin.uri:
    url: "https://{{ qdrant_subdomain }}.{{ domain_name }}/collections/brand-voice"
    method: PUT
    headers:
      api-key: "{{ qdrant_api_key }}"
      Content-Type: "application/json"
    body_format: json
    body:
      vectors:
        size: 1536
        distance: "Cosine"
    status_code: [200]
  # Qdrant returns 200 if already exists (idempotent)
```

**Distance metric decision:** Cosine distance for text embeddings from `text-embedding-3-small`. OpenAI normalizes these embeddings by default, so Dot and Cosine are equivalent on normalized vectors, but **Cosine is the industry standard** for semantic text similarity — clearer intent, same performance.

**Seeding approach:** Direct API calls via Ansible `uri` module (simpler than creating an n8n workflow for Phase 5; n8n workflow for ongoing seeding is Phase 7 scope). The initial seed of Paul Taff brand description + tone guidelines = 2-3 vectors, manageable via uri module.

### Anti-Patterns to Avoid

- **Do NOT** use `cgwire/cgwire:latest` — pin to `1.0.17` per VPAI conventions
- **Do NOT** skip the supervisord.conf override — without it, Zou uses `DB_USERNAME=root` and `DB_PASSWORD=''`, connecting to the internal PostgreSQL instead of shared
- **Do NOT** use `become: yes` globally — use `become: true` per task per VPAI conventions
- **Do NOT** use bare `command`/`shell` for zou provisioning if a uri module call suffices
- **Do NOT** create separate `postgresql_kitsu_password` — use shared `postgresql_password`

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Kitsu project structure | Python script from scratch | `gazu` Python client or `zou` CLI | Official clients handle auth token refresh, error codes |
| NocoDB table schema | Direct PostgreSQL SQL | NocoDB REST API | Schema changes via API maintain NocoDB metadata consistency |
| Qdrant index management | Custom vector logic | Qdrant REST API | Qdrant handles HNSW index creation automatically on collection creation |
| Zou admin initialization | Parsing Zou internals | `zou create-admin` CLI (already in image) | CLI is the documented provisioning method |
| Idempotency checks | Re-running and accepting failures | Check-before-create pattern (uri module + `when:` condition) | Ansible best practice for REST API provisioning |

**Key insight:** The `cgwire/cgwire` image ships with a `zou` CLI (available via `/opt/zou/env/bin/zou`) that handles DB initialization (`zou upgrade-db`, `zou init-data`) and admin creation. The provisioning role should use `docker exec` to call these CLI commands, not re-implement the logic.

---

## Common Pitfalls

### Pitfall 1: Supervisord env overrides Docker env vars
**What goes wrong:** Zou connects to the internal PostgreSQL (localhost) instead of the shared `postgresql` container, even with correct `DB_HOST=postgresql` in Docker env_file.
**Why it happens:** The supervisord.conf `[program:gunicorn] environment=DB_USERNAME=root,DB_PASSWORD=''` overrides Docker env vars for those specific variables at process launch. `DB_HOST` is NOT in supervisord env so it reads from Docker env correctly — but `DB_USERNAME=root` causes authentication failures against the external PG.
**How to avoid:** Mount a custom `/etc/supervisord.conf` via Docker volume that omits `DB_USERNAME` and `DB_PASSWORD` from the gunicorn environment block.
**Warning signs:** Zou logs `FATAL: role "root" does not exist` or `FATAL: password authentication failed for user "root"`.

### Pitfall 2: Internal PostgreSQL and Redis still start
**What goes wrong:** Even with external PG/Redis configured, the image's supervisord starts internal PostgreSQL and Redis, consuming ~200MB RAM unnecessarily.
**Why it happens:** The image's supervisord.conf starts `[program:postgresql]` and `[program:redis]` unconditionally.
**How to avoid:** In the custom supervisord.conf, either remove the `[program:postgresql]` and `[program:redis]` blocks, or set `autostart=false` for them. **Important:** The `zou upgrade-db` and `zou init-data` commands need the DB reachable — ensure the external PostgreSQL is healthy before running provision.
**Warning signs:** Container using unexpectedly high memory; `docker exec ... ps aux` shows postgres processes.

### Pitfall 3: Zou healthcheck authentication
**What goes wrong:** `/api/health` returns 200 without auth but doesn't verify DB connectivity; `/api/data/persons` requires authentication.
**Why it happens:** Zou's `/api/health` endpoint is lightweight and doesn't test DB connection depth.
**How to avoid:** For the Docker healthcheck, use `curl -sf http://127.0.0.1/api/data/persons` with proper auth header, OR use `/api/health` and accept limited coverage. For Grafana monitoring, cAdvisor metrics are sufficient — no application-level healthcheck needed in Grafana.
**Warning signs:** Container reports healthy but Kitsu UI shows "API unreachable".

### Pitfall 4: env_file handler pattern for Kitsu
**What goes wrong:** Running `state: restarted` in the `community.docker.docker_compose_v2` handler does NOT reload env_file changes.
**Why it happens:** `docker compose restart` preserves the container environment from creation — it does NOT re-read env_file.
**How to avoid:** Per VPAI CLAUDE.md convention, use `state: present` + `recreate: always` for any service using `env_file`. This applies to Kitsu since it uses an env_file for Zou configuration.
**Warning signs:** Password changes in vault not reflected after deploy; Zou still connects with old credentials.

### Pitfall 5: NocoDB FK relationships require table IDs, not names
**What goes wrong:** Ansible provision script fails to create FK between `contents.brand_id` and `brands.id`.
**Why it happens:** NocoDB API v2 FK creation requires the target table's internal UUID, not its name. This UUID is only available after table creation.
**How to avoid:** The provision script must: (1) create `brands` table, (2) capture the returned table ID, (3) create `contents` table with FK referencing the brands table ID. Use a sequential provisioning approach (not parallel).
**Warning signs:** `contents` table missing `brand_id` FK link; FK column exists as plain integer without relation.

### Pitfall 6: Backup script only dumps n8n and litellm
**What goes wrong:** `kitsu_production` database is not included in the Zerobyte backup, losing all Kitsu project data on restore.
**Why it happens:** `pre-backup.sh.j2` has a hardcoded loop: `for DB in n8n litellm`.
**How to avoid:** Extend the loop to: `for DB in n8n litellm nocodb kitsu_production`. (Note: nocodb may also need adding if not already there.)
**Warning signs:** Database listed in PostgreSQL but missing from backup dumps.

### Pitfall 7: Zou DB init runs on every container start
**What goes wrong:** `zou upgrade-db` is slow (~30s) and `zou init-data` may conflict with existing data.
**Why it happens:** The `init_zou.sh` runs during `docker build` (image init time) not at container start — the `start_zou.sh` just runs supervisord. So this is NOT a problem at runtime.
**Clarification:** DB initialization (`zou upgrade-db`, `zou init-data`, `zou create-admin`) must be run ONCE via `docker exec` in the provisioning role, guarded by a `.provision-complete` sentinel file.

---

## Code Examples

### kitsu.env.j2 (Zou environment file)
```bash
# {{ ansible_managed }}
# Kitsu/Zou environment configuration

# Database (shared VPAI PostgreSQL)
DB_HOST=postgresql
DB_PORT=5432
DB_USERNAME=zou
DB_PASSWORD={{ postgresql_password }}
DB_DATABASE=kitsu_production
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# Redis (shared VPAI Redis)
KV_HOST=redis
KV_PORT=6379
KV_PASSWORD={{ redis_password }}

# Security
SECRET_KEY={{ kitsu_secret_key }}

# Storage
PREVIEW_FOLDER=/opt/zou/previews
TMP_DIR=/tmp

# Locale
DEFAULT_TIMEZONE=Europe/Paris
DEFAULT_LOCALE=fr_FR
```

### NocoDB API v2 — Table creation example
```bash
# Source: NocoDB API docs (https://hq.ewutelo.cloud/api/v2/meta/tables)
# Check table exists
TABLES=$(curl -sf -H "xc-token: $TOKEN" \
  "https://hq.ewutelo.cloud/api/v2/meta/bases/$BASE_ID/tables")
# brands table not found → create
curl -sf -X POST \
  -H "xc-token: $TOKEN" \
  -H "Content-Type: application/json" \
  "https://hq.ewutelo.cloud/api/v2/meta/bases/$BASE_ID/tables" \
  -d '{"title": "brands", "columns": [
    {"title": "name", "uidt": "SingleLineText"},
    {"title": "tagline", "uidt": "SingleLineText"},
    {"title": "tone", "uidt": "LongText"},
    {"title": "palette", "uidt": "JSON"},
    {"title": "typography", "uidt": "SingleLineText"},
    {"title": "target_audience", "uidt": "SingleLineText"},
    {"title": "platforms", "uidt": "JSON"}
  ]}'
```

### Qdrant collection creation
```bash
# Source: Qdrant REST API (https://qdrant.github.io/qdrant/redoc/)
curl -sf -X PUT \
  -H "api-key: $QDRANT_API_KEY" \
  -H "Content-Type: application/json" \
  "https://qd.ewutelo.cloud/collections/brand-voice" \
  -d '{"vectors": {"size": 1536, "distance": "Cosine"}}'
# Returns 200 if already exists (idempotent)
```

### Kitsu provisioning via docker exec
```bash
# Provision Zou DB (idempotent with sentinel file)
# Source: cgwire/zou CLI documentation
docker exec javisi_kitsu /opt/zou/env/bin/zou upgrade-db
docker exec javisi_kitsu /opt/zou/env/bin/zou init-data
docker exec javisi_kitsu /opt/zou/env/bin/zou create-admin \
  admin@ewutelo.cloud --password "$KITSU_ADMIN_PASSWORD"
touch /opt/javisi/configs/kitsu/.provision-complete
```

### Zou REST API — Project structure creation
```bash
# Get auth token
TOKEN=$(curl -sf -X POST \
  -H "Content-Type: application/json" \
  http://kitsu/api/auth/login \
  -d '{"email": "admin@ewutelo.cloud", "password": "..."}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create production (brand project)
curl -sf -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  http://kitsu/api/data/projects \
  -d '{"name": "Paul Taff — Lancement", "project_type": "tvshow", "fps": "25"}'
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| cgwire/cgwire:0.x | cgwire/cgwire:1.0.x | 2025-2026 | New versioning scheme, now ~weekly releases |
| NocoDB v1 API (`/api/v1/`) | NocoDB v2 API (`/api/v2/`) | NocoDB 0.200+ | v1 deprecated; use v2 base/table endpoints |
| Separate Zou + Kitsu images | All-in-one `cgwire/cgwire` | CGWire 2025 | Only official Docker option on Docker Hub |

**Deprecated/outdated:**
- `cgwire/cgwire:latest` tag: do not use, pin to `1.0.17`
- NocoDB `/api/v1/db/meta/projects/` endpoints: replaced by `/api/v2/meta/bases/`

---

## Open Questions

1. **NocoDB Base ID for API calls**
   - What we know: NocoDB API v2 requires a `baseId` for table operations. The existing NocoDB instance at `hq.ewutelo.cloud` has an existing base.
   - What's unclear: Whether there is an existing base to use, or whether to create a new base named "content-factory". The `baseId` is visible in the NocoDB UI URL or via `GET /api/v2/meta/bases`.
   - Recommendation: In the provisioning script, first call `GET /api/v2/meta/bases` to list bases, find or create "content-factory" base, then use its ID for table creation.

2. **Kitsu admin credentials storage**
   - What we know: Zou's `create-admin` command sets the admin user's email and password. This admin is needed for Kitsu UI access and for provisioning API tokens.
   - What's unclear: Whether to store the admin email/password in Ansible vault or generate API tokens for programmatic access.
   - Recommendation: Add `vault_kitsu_admin_email` and `vault_kitsu_admin_password` to the vault. After `create-admin`, use the email/password to get a JWT token for the provisioning script.

3. **Zou API token vs JWT for project provisioning**
   - What we know: Zou supports JWT auth (login → access_token). Gazu client handles this automatically.
   - What's unclear: Whether Zou has API key support (like NocoDB's `xc-token`) or only JWT.
   - Recommendation: Use JWT auth (login + Bearer token) for provisioning. Store the admin credentials in vault. The provisioning shell script should handle token refresh if needed.

4. **Internal PostgreSQL disable in cgwire/cgwire image**
   - What we know: The image starts an internal PostgreSQL via supervisord. The custom supervisord.conf can disable it with `autostart=false`.
   - What's unclear: Whether disabling internal PostgreSQL causes any side effects (zombie processes, socket file conflicts) when Zou connects to external PG.
   - Recommendation: Set `autostart=false` for `[program:postgresql]` in custom supervisord.conf. Monitor with `docker exec ... ps aux` after first deploy.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Molecule (Ansible) + Docker driver |
| Config file | `roles/kitsu/molecule/default/molecule.yml` — Wave 0 gap |
| Quick run command | `cd /home/mobuone/VPAI && source .venv/bin/activate && molecule test -s default -- roles/kitsu` |
| Full suite command | `source .venv/bin/activate && molecule test` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | Kitsu role creates config dirs and env file | unit (molecule) | `molecule converge -s default -- roles/kitsu` | ❌ Wave 0 |
| INFRA-02 | PostgreSQL provisioning script contains kitsu_production | unit (assert file content) | `molecule verify -s default -- roles/kitsu` | ❌ Wave 0 |
| INFRA-03 | Caddy config contains boss.ewutelo.cloud block | unit (assert template render) | `molecule verify -s default -- roles/caddy` | ✅ exists |
| INFRA-04 | n8n env file contains FAL_KEY | unit (assert file content) | `molecule verify -s default -- roles/n8n` | ✅ exists |
| INFRA-05 | cAdvisor discovers kitsu container (runtime test) | smoke | `ssh ... docker stats --no-stream | grep kitsu` | manual |
| INFRA-06 | pre-backup.sh contains kitsu_production | unit (assert template) | `molecule verify -s default -- roles/backup-config` | ✅ exists |
| DATA-01..05 | NocoDB tables and Paul Taff row exist | smoke | `curl -H "xc-token:..." /api/v2/meta/bases/xxx/tables` | manual |
| DATA-04 | Qdrant brand-voice collection exists | smoke | `curl -H "api-key:..." https://qd.../collections/brand-voice` | manual |
| DATA-06 | Kitsu project exists via API | smoke | `curl http://kitsu/api/data/projects | grep Paul` | manual |

### Sampling Rate
- **Per task commit:** `source .venv/bin/activate && molecule lint -- roles/kitsu`
- **Per wave merge:** `source .venv/bin/activate && molecule test -- roles/kitsu`
- **Phase gate:** All smoke tests green + Kitsu UI accessible at boss.ewutelo.cloud via VPN

### Wave 0 Gaps
- [ ] `roles/kitsu/molecule/default/molecule.yml` — Kitsu role molecule config
- [ ] `roles/kitsu/molecule/default/converge.yml` — converge playbook with stub vars
- [ ] `roles/kitsu/molecule/default/verify.yml` — verify playbook (assert dirs, env file content)
- [ ] `roles/kitsu-provision/molecule/default/` — provision role molecule tests

*(Existing backup-config, n8n, and caddy molecule tests need to have their verify.yml updated to check the new content once those files are modified.)*

---

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `roles/nocodb/`, `roles/plane-provision/`, `roles/docker-stack/templates/`, `roles/n8n-provision/tasks/main.yml` — existing provisioning patterns
- `roles/caddy/templates/Caddyfile.j2` — Caddy VPN-only ACL pattern
- `inventory/group_vars/all/main.yml` — `fal_ai_api_key` already defined (line 132)
- `inventory/group_vars/all/versions.yml` — pinned image pattern
- https://raw.githubusercontent.com/cgwire/kitsu-docker/master/Dockerfile — verified image structure
- https://raw.githubusercontent.com/cgwire/kitsu-docker/master/docker/supervisord.conf — verified supervisord behavior (gunicorn env overrides)
- https://raw.githubusercontent.com/cgwire/kitsu-docker/master/docker/start_zou.sh — verified startup behavior
- https://raw.githubusercontent.com/cgwire/zou/main/zou/app/config.py — verified all DB config via os.getenv()
- Docker Hub API: `https://hub.docker.com/v2/repositories/cgwire/cgwire/tags/` — verified `1.0.17` is latest (2026-03-14)

### Secondary (MEDIUM confidence)
- https://zou.cg-wire.com/configuration/ — Zou environment variables documentation (verified against config.py)
- https://blog.cg-wire.com/cgwire-software-suite-available-on-the-docker-hub/ — official confirmation all-in-one image is for trial, not production
- GitLab mathbou/docker-cgwire — version badge confirms Zou 1.0+E18, Kitsu 1.0+E17

### Tertiary (LOW confidence)
- WebSearch results on Gazu Python client — version 0.10.14 (PyPI), functional but exact API surface for task type creation not verified

---

## Metadata

**Confidence breakdown:**
- Standard stack (cgwire image): HIGH — verified via Docker Hub API + Dockerfile inspection
- PostgreSQL integration approach: MEDIUM — supervisord override is the logical solution, verified by reading config.py and supervisord.conf, but not tested
- Architecture patterns: HIGH — directly mirrors existing roles (nocodb, plane-provision, n8n-provision)
- NocoDB/Qdrant provisioning: HIGH — API patterns documented and existing in codebase
- Kitsu project structure via Zou API: MEDIUM — Zou REST API endpoints are documented but Gazu client not verified for task type names

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (CGWire releases frequently — verify image version before implement)
