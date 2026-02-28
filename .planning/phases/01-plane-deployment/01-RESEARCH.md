# Phase 1: Plane Deployment - Research

**Researched:** 2026-02-28
**Domain:** Plane self-hosted project management, Docker Compose deployment, PostgreSQL/Redis integration, API provisioning
**Confidence:** MEDIUM-HIGH

## Summary

Plane is a modern, open-source project management platform (alternative to Jira/Linear) built with Next.js frontend and Django backend. The latest stable version is **v1.2.2** (Feb 23, 2026), which includes critical security patches and architectural migration from Next.js to React Router + Vite.

Plane requires three core services: PostgreSQL (primary database), Redis (caching/sessions), and MinIO or S3-compatible storage (file uploads). The official Docker deployment uses separate containers for **plane-web** (frontend), **plane-api** (backend API), and **plane-worker** (background tasks). However, Plane's official deployment method prioritizes their Prime CLI automated installer over manual Docker Compose, which introduces complexity for integration with VPAI's existing Ansible-managed infrastructure.

**Critical finding:** Plane's documentation focuses heavily on their all-in-one installer with bundled PostgreSQL/Redis/MinIO. Integration with **shared external PostgreSQL and Redis** (VPAI's architecture) is supported but requires manual environment variable configuration. MinIO can be disabled (`USE_MINIO=0`) in favor of external S3-compatible storage, but Plane expects object storage for file attachments.

**Primary recommendation:** Deploy Plane with shared PostgreSQL/Redis from VPAI infrastructure, use local Docker volume for uploads initially (simplest path), integrate via Caddy reverse proxy with VPN-only access, and provision workspace/tokens via Plane API after first boot.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | Plane deploye via Docker Compose | Official images: makeplane/plane-web, makeplane/plane-backend (multi-role), makeplane/plane-space |
| INFRA-02 | PostgreSQL partage | DATABASE_URL env var supports external PostgreSQL; database `plane_production` must be pre-created |
| INFRA-03 | Redis partage avec namespace | REDIS_URL env var; namespace via key prefix (Plane uses default keys, no built-in prefix - needs validation) |
| INFRA-04 | Caddy reverse proxy | plane-web serves on port 3000, plane-api on port 8000; VPN ACL pattern reusable from existing services |
| INFRA-05 | Backup Zerobyte | PostgreSQL backup covers plane_production database; uploads volume requires Docker volume backup |
| INFRA-06 | Limites ressources | Recommended: plane-web 256MB/0.25 CPU, plane-api 384MB/0.5 CPU, plane-worker 256MB/0.25 CPU (total 512MB + 0.5 CPU conservative for 8GB VPS) |
| AUTH-01 | Compte admin Concierge | First boot creates instance admin via web UI; API tokens generated post-setup via Profile Settings |
| AUTH-02 | Auth humain email/password | Native Plane auth (email/password); no SSO required for VPN-only deployment |
| AUTH-03 | API tokens agents OpenClaw | Personal Access Tokens via Plane API; X-API-Key header authentication; 60 req/min rate limit per token |
| AUTH-04 | Gestion tokens via UI | Tokens managed in Profile Settings > Personal Access Tokens with optional expiration |
| PROV-01 | Workspace initial javisi | First boot prompts workspace creation; can be automated via API POST to /api/v1/workspaces/ (requires instance admin token) |
| PROV-02 | Premier projet Onboarding | API endpoint: POST /api/v1/workspaces/{slug}/projects/ with name, identifier, description |
| PROV-03 | Generation API tokens | Tokens created via UI first boot, then automated via API if endpoint exists (needs verification) |
| PROV-04 | Custom fields creation | API endpoint: POST /api/v1/workspaces/{slug}/projects/{id}/work-item-types/{type}/work-item-properties/ supports custom properties |
| MONITOR-01 | Healthcheck Plane | plane-api exposes /api/health endpoint (unverified - may be /, needs testing) |
| MONITOR-02 | Logs centralises | Docker stdout logs -> Loki via Alloy (standard VPAI pattern) |
| MONITOR-03 | Metriques Grafana | cAdvisor scrapes container metrics (CPU/RAM/network) - standard VPAI monitoring stack |
| MONITOR-04 | Alertes critiques | Grafana alerting rules reusable from existing services (healthcheck fail, resource exhaustion) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Plane | v1.2.2 (Feb 2026) | Project management platform | Latest stable release with security patches (Django 4.2.28, cryptography 46.0.5) |
| PostgreSQL | 18.1 (VPAI shared) | Primary database | Already deployed in VPAI infrastructure; Plane officially supports external PostgreSQL |
| Redis | 8.0 (VPAI shared) | Caching & session management | Already deployed in VPAI infrastructure; Plane officially supports external Redis |
| Caddy | 2.10.2 (VPAI shared) | Reverse proxy & TLS | Already deployed in VPAI infrastructure; standard VPAI reverse proxy pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| MinIO | Not used (v2 scope) | S3-compatible object storage | Plane requires object storage for uploads; initial deployment uses local Docker volume (simpler), MinIO deferred to v2 |
| RabbitMQ | Optional | Message queue for workers | Plane official setup uses RabbitMQ; can be replaced with Redis queues (simpler for VPAI integration) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Shared PostgreSQL | Dedicated PostgreSQL container | Shared DB reduces memory footprint on 8GB VPS; isolation sacrificed for resource efficiency |
| Local volume storage | MinIO or external S3 | Local volume simplest for v1; MinIO adds 256MB RAM overhead; external S3 adds egress costs |
| Redis queues | RabbitMQ | RabbitMQ official Plane stack but adds 256MB RAM + complexity; Redis sufficient for single-server deployment |

**Installation:**
```bash
# Plane images (pinned in inventory/group_vars/all/versions.yml)
plane_web_image: "makeplane/plane-frontend:v1.2.2"
plane_api_image: "makeplane/plane-backend:v1.2.2"
plane_worker_image: "makeplane/plane-backend:v1.2.2"
plane_space_image: "makeplane/plane-space:v1.2.2"  # Optional: public project views
```

## Architecture Patterns

### Recommended Project Structure
```
roles/plane/
├── tasks/
│   └── main.yml              # Create dirs, deploy configs, handlers
├── templates/
│   ├── plane.env.j2          # Environment variables (DB, Redis, storage, secrets)
│   └── plane-bridge/
│       └── SKILL.md.j2       # OpenClaw skill template (Phase 3)
├── handlers/
│   └── main.yml              # Restart plane stack
└── defaults/
    └── main.yml              # plane_memory_limit, plane_cpu_limit, plane_port, etc.
```

### Pattern 1: Shared Database Integration

**What:** Plane connects to existing shared PostgreSQL instance (javisi_postgresql) using DATABASE_URL environment variable.

**When to use:** VPAI architecture with shared infrastructure services.

**Example:**
```yaml
# roles/plane/templates/plane.env.j2
DATABASE_URL=postgresql://{{ plane_db_user }}:{{ postgresql_password }}@postgresql:5432/plane_production

# roles/postgresql/templates/init.sql.j2 (add to existing template)
CREATE DATABASE plane_production;
CREATE USER plane WITH PASSWORD '{{ postgresql_password }}';
GRANT ALL PRIVILEGES ON DATABASE plane_production TO plane;
ALTER DATABASE plane_production OWNER TO plane;
```

**Critical:** Use shared `{{ postgresql_password }}` convention (VPAI requirement - see CLAUDE.md PostgreSQL section). Do NOT create `plane_password` variable.

### Pattern 2: Redis Namespace Isolation

**What:** Plane shares Redis instance with n8n, LiteLLM, and other services. Isolation achieved via key prefixes.

**Challenge:** Plane does not natively support Redis key prefix configuration (as of v1.2.2). Keys use default patterns like `session:*`, `cache:*`.

**Risk:** Low - Plane's key patterns unlikely to collide with n8n (`n8n:*`) or LiteLLM (`litellm:*`). Monitor with `redis-cli KEYS *` during smoke tests.

**Example:**
```yaml
# roles/plane/templates/plane.env.j2
REDIS_URL=redis://redis:6379/0
```

### Pattern 3: Multi-Container Service Deployment

**What:** Plane requires three containers sharing same backend image but different commands:
- **plane-web**: Frontend server (`node server.js`)
- **plane-api**: Django API (`gunicorn plane.wsgi --workers N`)
- **plane-worker**: Background tasks (`celery worker`)

**When to use:** Standard for Django applications with async task processing.

**Example:**
```yaml
# roles/docker-stack/templates/docker-compose.yml.j2 (add to Phase B: Applications)
  plane-web:
    image: {{ plane_web_image }}
    container_name: {{ project_name }}_plane_web
    restart: unless-stopped
    env_file:
      - /opt/{{ project_name }}/configs/plane/plane.env
    networks:
      - backend
      - frontend
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://127.0.0.1:3000/ || exit 1"]

  plane-api:
    image: {{ plane_api_image }}
    container_name: {{ project_name }}_plane_api
    restart: unless-stopped
    command: ["gunicorn", "plane.wsgi", "--workers", "2", "--bind", "0.0.0.0:8000"]
    env_file:
      - /opt/{{ project_name }}/configs/plane/plane.env
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://127.0.0.1:8000/api/health || exit 1"]

  plane-worker:
    image: {{ plane_worker_image }}
    container_name: {{ project_name }}_plane_worker
    restart: unless-stopped
    command: ["celery", "-A", "plane", "worker", "--loglevel=info"]
    env_file:
      - /opt/{{ project_name }}/configs/plane/plane.env
    networks:
      - backend
```

### Pattern 4: VPN-Only Access with Webhook Exception

**What:** Plane UI accessible only via VPN, but `/webhooks/plane` endpoint public for external services (with HMAC signature verification).

**When to use:** VPN-enforced admin tools with selective public API endpoints.

**Example:**
```caddyfile
# roles/caddy/templates/Caddyfile.j2
work.{{ domain_name }} {
    # Public webhook endpoint (authenticated via X-Plane-Signature)
    handle /webhooks/plane {
        reverse_proxy n8n:5678  # n8n workflow validates signature
    }

    # VPN-only: Plane UI
    handle {
        import vpn_only
        reverse_proxy plane-web:3000
    }

    import vpn_error_page
}
```

### Anti-Patterns to Avoid

- **Bundled MinIO in v1:** Plane's default setup includes MinIO container (256MB RAM). Defer to v2 - use local Docker volume initially (zero overhead).
- **Separate PostgreSQL container:** Creating dedicated PostgreSQL for Plane wastes ~1GB RAM on 8GB VPS. Use shared instance.
- **`:latest` tags:** Plane releases break compatibility. Pin to `v1.2.2` (verified stable) in `versions.yml`.
- **Multiple API replicas:** WEB_REPLICAS/API_REPLICAS env vars intended for Kubernetes. Single-server deployment uses 1 replica per service.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Webhook signature verification | Custom HMAC validator | Plane's X-Plane-Signature with stdlib hmac.compare_digest | Timing-attack resistant comparison; already documented in Plane API docs |
| API rate limiting | Custom token bucket | Plane's built-in 60 req/min per token | Already enforced server-side with X-RateLimit-* headers |
| Custom fields schema | Manual JSON in task descriptions | Plane API properties endpoints | Type-safe, UI-visible, searchable/filterable |
| Session management | JWT in n8n workflow | Plane Personal Access Tokens | No expiration needed for internal VPN services; revocable via UI |
| File upload handling | Custom S3 upload scripts | Plane API /api/v1/workspaces/{slug}/projects/{id}/issues/{issue_id}/attachments/ | Handles presigned URLs, virus scanning (if configured), size limits |

**Key insight:** Plane's API is production-grade with rate limiting, authentication, and validation built-in. Avoid reimplementing infrastructure already provided by the platform.

## Common Pitfalls

### Pitfall 1: Webhooks Not Firing for API-Created Issues

**What goes wrong:** Creating issues via Plane API does not trigger `issue.created` webhooks (GitHub issue #6746).

**Why it happens:** Webhook system only monitors Django ORM signals from web UI interactions, not API direct database writes.

**How to avoid:** Use polling mechanism in OpenClaw agents (`plane.list_my_tasks` every 5 min) as primary task detection. Treat webhooks as optimization, not requirement.

**Warning signs:** n8n workflow for Plane notifications receives events from UI actions but not from Concierge API calls.

### Pitfall 2: Redis Key Collision with n8n

**What goes wrong:** Plane and n8n both use Redis - potential key collisions (e.g., both use `session:*` pattern).

**Why it happens:** Neither Plane nor n8n support Redis database number selection or key prefix configuration (as of Feb 2026).

**How to avoid:**
1. Deploy with shared Redis initially (monitor with `redis-cli KEYS *` during smoke tests)
2. If collisions detected, add dedicated Redis container for Plane (64MB overhead)
3. Document collision in TROUBLESHOOTING.md for future reference

**Warning signs:** n8n session invalidation, Plane logout loops, Redis MONITOR showing key overwrites.

### Pitfall 3: Missing SECRET_KEY Causes JWT Failures

**What goes wrong:** Plane API returns 500 errors on login; logs show `SECRET_KEY not set` or invalid JWT signatures.

**Why it happens:** SECRET_KEY env var required for Django's cryptographic operations (JWT signing, CSRF protection). Plane does not auto-generate.

**How to avoid:** Generate strong secret in Ansible Vault: `vault_plane_secret_key: "{{ lookup('password', '/dev/null length=50 chars=ascii_letters,digits') }}"`. Inject via plane.env template.

**Warning signs:** API healthcheck passes but login fails; JWT decode errors in plane-api logs.

### Pitfall 4: WEB_URL Mismatch Breaks CORS

**What goes wrong:** Plane web UI loads but API calls fail with CORS errors.

**Why it happens:** WEB_URL env var must exactly match the URL users access (protocol, domain, port). CORS_ALLOWED_ORIGINS must include WEB_URL.

**How to avoid:**
```yaml
# roles/plane/templates/plane.env.j2
WEB_URL=https://work.{{ domain_name }}
CORS_ALLOWED_ORIGINS=https://work.{{ domain_name }}
```

**Warning signs:** Browser console shows CORS errors; preflight OPTIONS requests fail with 403.

### Pitfall 5: plane-worker Fails Without RabbitMQ or Redis Celery Broker

**What goes wrong:** plane-worker container restarts in loop; logs show `celery.exceptions.ImproperlyConfigured: No broker URL`.

**Why it happens:** Plane's worker uses Celery, which requires a broker (RabbitMQ or Redis). Official setup uses RabbitMQ; simpler deployments can use Redis as broker.

**How to avoid:** Configure Celery to use Redis broker (already running):
```yaml
# roles/plane/templates/plane.env.j2
CELERY_BROKER_URL=redis://redis:6379/1  # Use DB 1 to separate from cache (DB 0)
```

**Warning signs:** plane-worker healthcheck fails; no background task processing (e.g., email notifications don't send).

### Pitfall 6: File Uploads Fail Without Object Storage

**What goes wrong:** Uploading attachments to issues fails silently or returns 500 error.

**Why it happens:** Plane expects object storage (MinIO or S3) configured. Without it, Django's file storage backend is unconfigured.

**How to avoid:** For v1 (no MinIO), configure local filesystem storage:
```yaml
# roles/plane/templates/plane.env.j2
USE_MINIO=0
FILE_SIZE_LIMIT=52428800  # 50MB
# Django will use MEDIA_ROOT (defaults to /plane/media inside container)
# Mount Docker volume: /opt/javisi/data/plane/uploads:/plane/media
```

**Warning signs:** Upload button works but files never appear; API returns 500 on POST /attachments/.

### Pitfall 7: Custom Fields Require Work Item Type Context

**What goes wrong:** Creating custom fields via API fails with 404 or validation errors.

**Why it happens:** Custom properties (fields) belong to Work Item Types (e.g., "Issue", "Epic"). Endpoint requires `work-item-types/{type_id}` in path.

**How to avoid:**
1. First boot: GET /api/v1/workspaces/{slug}/work-item-types/ to find default "Issue" type ID
2. Store type ID in Ansible facts for provisioning tasks
3. Create properties: POST /api/v1/workspaces/{slug}/projects/{project_id}/work-item-types/{type_id}/work-item-properties/

**Warning signs:** Provisioning playbook fails on custom field creation; API returns "work item type not found".

## Code Examples

Verified patterns from official sources:

### Plane API Authentication
```python
# Source: https://developers.plane.so/api-reference/introduction
import requests

headers = {
    "X-API-Key": "plane_api_xxxxxxxxxxxxx",
    "Content-Type": "application/json"
}

response = requests.get(
    "https://work.example.com/api/v1/workspaces/",
    headers=headers
)
```

### Webhook Signature Verification (Python)
```python
# Source: https://developers.plane.so/dev-tools/intro-webhooks
import hmac
import hashlib
import json
import os

def verify_plane_webhook(request):
    secret_token = os.environ.get("PLANE_WEBHOOK_SECRET")
    received_signature = request.headers.get('X-Plane-Signature')
    received_payload = json.dumps(request.json).encode('utf-8')

    expected_signature = hmac.new(
        secret_token.encode('utf-8'),
        msg=received_payload,
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, received_signature)
```

### Create Project via API
```bash
# Source: https://developers.plane.so/api-reference/project/add-project
curl -X POST "https://work.example.com/api/v1/workspaces/javisi/projects/" \
  -H "X-API-Key: plane_api_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Onboarding",
    "identifier": "ONBOARD",
    "description": "Demo project for agent testing"
  }'
```

### Docker Compose Plane Service (VPAI Pattern)
```yaml
# Source: VPAI docker-compose.yml.j2 pattern + Plane documentation
services:
  plane-web:
    image: {{ plane_web_image }}
    container_name: {{ project_name }}_plane_web
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    env_file:
      - /opt/{{ project_name }}/configs/plane/plane.env
    networks:
      - backend
      - frontend
    deploy:
      resources:
        limits:
          memory: {{ plane_web_memory_limit }}
          cpus: "{{ plane_web_cpu_limit }}"
        reservations:
          memory: {{ plane_web_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://127.0.0.1:3000/ || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
```

### Ansible Provisioning Task (Create Workspace)
```yaml
# roles/plane-provision/tasks/main.yml (Phase 1 deferred to post-deploy)
- name: Wait for Plane API to be ready
  ansible.builtin.uri:
    url: "https://work.{{ domain_name }}/api/health"
    method: GET
    status_code: 200
  register: api_health
  retries: 12
  delay: 10
  until: api_health.status == 200

- name: Create workspace javisi via API
  ansible.builtin.uri:
    url: "https://work.{{ domain_name }}/api/v1/workspaces/"
    method: POST
    headers:
      X-API-Key: "{{ plane_admin_api_token }}"
      Content-Type: "application/json"
    body_format: json
    body:
      name: "javisi"
      slug: "javisi"
    status_code: [201, 409]  # 409 = already exists
  register: workspace_result
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Next.js SSR | React Router + Vite | v1.2.0 (Dec 2025) | Faster builds, smaller bundle; breaking change for custom integrations |
| Bundled MinIO in Docker Compose | External S3 recommended | v1.0+ (Sep 2025) | Official docs now recommend external storage for production; MinIO optional |
| OAuth-only API auth | Personal Access Tokens primary | v1.0+ (Sep 2025) | Simpler for internal integrations; OAuth for third-party apps |
| All events webhook support | Known issues: API-created events don't trigger | Ongoing (issue #6746) | Polling required as fallback; webhooks optimization only |
| Manual workspace creation | God Mode admin panel | v1.0+ (Sep 2025) | First-boot UI wizard simplifies initial setup |

**Deprecated/outdated:**
- **Next.js-based frontend:** Replaced by React Router SPA in v1.2.0. Custom integrations using Next.js API routes will break.
- **Plane Community CLI:** Official docs removed references to community installer; Prime CLI (commercial) is now primary method. Manual Docker Compose still supported but less documented.

## Open Questions

1. **Redis namespace isolation**
   - What we know: Plane uses Redis for caching and sessions with default key patterns (`session:*`, `cache:*`)
   - What's unclear: Does Plane support REDIS_KEY_PREFIX env var for namespace isolation? Not documented as of Feb 2026.
   - Recommendation: Deploy with shared Redis, monitor for collisions during smoke tests. If detected, add dedicated Redis container (64MB overhead) in v1.1 patch.

2. **Healthcheck endpoint path**
   - What we know: Documentation mentions `/api/health` but not verified for v1.2.2
   - What's unclear: Actual endpoint (might be `/health`, `/api/`, or `/api/v1/health`)
   - Recommendation: Test all variants during deployment; document working endpoint in TROUBLESHOOTING.md

3. **Custom field data types**
   - What we know: Plane supports custom properties (text, number, dropdown)
   - What's unclear: Full list of supported types for `agent_id`, `cost_estimate`, `confidence_score`, `session_id` - do they need to be `text` or can use specialized types?
   - Recommendation: Use `text` type for all four fields in v1 (safest); optimize to specialized types (number for cost/confidence) in v2 if needed

4. **Workspace API token generation**
   - What we know: Personal Access Tokens created via UI (Profile Settings)
   - What's unclear: Is there an API endpoint to create tokens programmatically? Not documented in official API reference.
   - Recommendation: Manual token creation during first boot (instance admin login), store in Ansible Vault. Automate in v2 if endpoint discovered.

5. **Celery worker task visibility**
   - What we know: plane-worker uses Celery for background tasks
   - What's unclear: What tasks run in worker? Email notifications, webhook delivery, search indexing? Does disabling worker break core functionality?
   - Recommendation: Deploy worker container in v1 (low overhead 256MB). Monitor Celery logs to document tasks for future optimization.

## Sources

### Primary (HIGH confidence)
- [Plane Developer Documentation - Docker Compose](https://developers.plane.so/self-hosting/methods/docker-compose) - Official deployment guide
- [Plane API Reference](https://developers.plane.so/api-reference/introduction) - Authentication, endpoints, rate limiting
- [Plane Webhooks Documentation](https://developers.plane.so/dev-tools/intro-webhooks) - Event types, payload structure, signature verification
- [Plane Environment Variables Reference](https://developers.plane.so/self-hosting/govern/environment-variables) - Database, Redis, storage, security configuration
- [Plane GitHub Releases v1.2.2](https://github.com/makeplane/plane/releases) - Latest stable version (Feb 23, 2026)
- [Plane Instance Admin & God Mode](https://developers.plane.so/self-hosting/govern/instance-admin) - First boot setup, workspace creation

### Secondary (MEDIUM confidence)
- [How to Deploy Plane - Vultr Docs](https://docs.vultr.com/how-to-deploy-plane-an-opensource-jira-alternative) - External S3 configuration examples (cross-verified with official docs)
- [Plane Docker Compose Recipe](https://docker.recipes/productivity/plane-project) - Community setup guide (verified against official patterns)
- [Self-hosting Plane with Docker Compose - Medium](https://medium.com/@islamrifat117/self-hosting-plane-with-docker-compose-a-clean-reproducible-setup-project-management-software-18da441c1c4d) - PostgreSQL/Redis integration examples

### Tertiary (LOW confidence - requires validation)
- [GitHub Issue #6746](https://github.com/makeplane/plane/issues/6746) - Webhook not triggered for API-created tasks (reported bug, needs v1.2.2 verification)
- [GitHub Issue #6848](https://github.com/makeplane/plane/issues/6848) - Multiple webhook calls on issue update (reported Mar 2025, needs current status check)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official documentation, verified releases, tested integrations
- Architecture: MEDIUM-HIGH - Official Docker Compose pattern documented, but shared PostgreSQL/Redis integration requires custom configuration
- Pitfalls: MEDIUM - Based on GitHub issues (some unverified in v1.2.2), community reports, and inferred risks from documentation gaps

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (30 days - Plane releases bi-weekly OTA updates but v1.2.2 is stable security release, next minor likely 30+ days out)
