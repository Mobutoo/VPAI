---
phase: 01
plan: 01a
subsystem: plane-infrastructure
tags: [ansible, docker, plane, infrastructure]
dependency_graph:
  requires: [postgresql, redis, caddy]
  provides: [plane-role, plane-containers]
  affects: [docker-compose, versions, secrets]
tech_stack:
  added: [plane-v1.2.2]
  patterns: [django-celery, shared-uploads, egress-networking]
key_files:
  created:
    - roles/plane/tasks/main.yml
    - roles/plane/handlers/main.yml
    - roles/plane/defaults/main.yml
    - roles/plane/templates/plane.env.j2
  modified:
    - roles/docker-stack/templates/docker-compose.yml.j2
    - inventory/group_vars/all/versions.yml
    - inventory/group_vars/all/secrets.yml
decisions:
  - Use shared postgresql_password for plane_db_user (VPAI convention)
  - Disable MinIO (USE_MINIO=0) for v1, use local filesystem
  - Split Redis databases: 0 for cache, 1 for Celery queue
  - plane-api and plane-worker on egress network for webhook delivery (INFRA-01)
  - Resource allocation: 512MB total (256MB web + 384MB api + 256MB worker)
metrics:
  duration_seconds: 195
  tasks_completed: 4
  files_created: 4
  files_modified: 3
  commits: 4
  completed_at: "2026-02-28T23:26:49Z"
---

# Phase 01 Plan 01a: Ansible Role - Plane Core Infrastructure Summary

Created Plane Ansible role with v1.2.2 Docker images (web, api, worker) integrated into docker-compose.yml using shared PostgreSQL password, egress networking for webhooks, and 512MB total resource allocation.

## Objective

Create Plane Ansible role structure and integrate three containers (web, api, worker) into Docker Compose with proper security, resource limits, and network configuration following VPAI conventions.

## What Was Built

### 1. Ansible Role Structure (Task T1, T2)

Created complete `roles/plane/` structure:
- **defaults/main.yml**: 12 variables (directories, resource limits, ports, database config)
- **tasks/main.yml**: 3 tasks (config dir, data dir with UID 1000:1000, env template deployment)
- **handlers/main.yml**: Restart handler using `state: present + recreate: always` (env_file reload pattern)
- **templates/plane.env.j2**: Django/Plane environment with 11 configuration variables

### 2. Version Pinning (Task T1)

Added to `inventory/group_vars/all/versions.yml`:
```yaml
plane_web_image: "makeplane/plane-frontend:v1.2.2"
plane_api_image: "makeplane/plane-backend:v1.2.2"
plane_worker_image: "makeplane/plane-backend:v1.2.2"
```

### 3. Secrets Generation (Task T1)

Added to `inventory/group_vars/all/secrets.yml` (encrypted):
- `vault_plane_secret_key`: 50-char random string for Django SECRET_KEY (JWT signing, CSRF)
- `vault_plane_webhook_secret`: 32-char random string for webhook HMAC verification

### 4. Environment Template (Task T3)

Created `plane.env.j2` with:
- **Django**: SECRET_KEY from vault
- **Database**: Uses shared `{{ postgresql_password }}` (VPAI convention - NOT a separate plane password)
- **Redis**: Split databases (0=cache, 1=Celery queue)
- **Web URLs**: WEB_URL and CORS_ALLOWED_ORIGINS set to `https://work.{{ domain_name }}`
- **Storage**: USE_MINIO=0 (local filesystem), FILE_SIZE_LIMIT=50MB
- **Webhooks**: PLANE_WEBHOOK_SECRET from vault

### 5. Docker Compose Integration (Task T4)

Added 3 services to `docker-compose.yml.j2` in APPLICATION LAYER section:

**plane-web**:
- Networks: `[backend, frontend]` (frontend for Caddy reverse proxy access)
- Resources: 256MB memory, 0.25 CPU
- Healthcheck: HTTP GET on port 3000, 60s start_period
- Volume: Shared uploads mount `/plane/media`

**plane-api**:
- Networks: `[backend, egress]` (egress for webhook delivery per INFRA-01)
- Command: `gunicorn plane.wsgi --workers 2 --bind 0.0.0.0:8000`
- Resources: 384MB memory, 0.5 CPU
- Healthcheck: HTTP GET on `/api/health`, 90s start_period
- Volume: Shared uploads mount `/plane/media`

**plane-worker**:
- Networks: `[backend, egress]` (egress for external API calls and webhooks per INFRA-01)
- Command: `celery -A plane worker --loglevel=info`
- Resources: 256MB memory, 0.25 CPU
- Healthcheck: Celery inspect ping, 120s start_period
- Volume: Shared uploads mount `/plane/media`

All services follow VPAI security pattern:
- `security_opt: no-new-privileges:true`
- `cap_drop: ALL`
- `cap_add: [CHOWN, SETGID, SETUID]`
- `restart: unless-stopped`

## Verification Results

✅ **Role structure exists**: All 4 files present (tasks, handlers, defaults, templates)
✅ **Docker Compose integration**: 3 services added in correct section with proper networks
✅ **Versions pinned**: All 3 images set to v1.2.2
✅ **Secrets exist**: Both vault variables present (50-char secret_key, 32-char webhook_secret)
✅ **Code quality**: All tasks use FQCN (ansible.builtin.*, community.docker.*)
✅ **PostgreSQL convention**: DATABASE_URL uses shared `{{ postgresql_password }}`
✅ **Egress networking**: plane-api and plane-worker on egress network for webhook delivery

## Deviations from Plan

None - plan executed exactly as written.

## Key Technical Decisions

1. **Shared PostgreSQL Password**: Following VPAI convention, all database users (including `plane`) use the single `{{ postgresql_password }}` variable. This avoids the password authentication crash-loop issue documented in CLAUDE.md line 99-101.

2. **Handler Pattern for env_file Reload**: Used `state: present + recreate: always` instead of `state: restarted` because `docker compose restart` does NOT reload env_file changes. This is a critical VPAI pattern documented in CLAUDE.md line 111.

3. **Egress Network for Webhooks**: Both plane-api and plane-worker are connected to the `egress` network (in addition to `backend`) to enable webhook delivery to external services, satisfying requirement INFRA-01.

4. **Redis Database Separation**: Used Redis database 0 for cache and database 1 for Celery broker to avoid key collision between cache operations and task queue.

5. **Resource Allocation**: Total 512MB matches VPS constraint (8GB shared across 20+ services). Gave plane-api highest allocation (384MB) as it handles Django ORM queries and API requests.

## Implementation Notes

- All Jinja2 variables use `{{ variable }}` pattern - zero hardcoded values
- Plane database user `plane` will be created by postgresql provisioning task (separate plan)
- Shared uploads volume ensures file attachments accessible across web/api/worker
- Healthcheck start_period values account for Django migrations and Celery worker startup
- UID 1000:1000 for uploads directory matches Plane container non-root user

## Files Modified

| File | Lines | Change Type |
|------|-------|-------------|
| inventory/group_vars/all/versions.yml | +3 | Added 3 plane image versions |
| inventory/group_vars/all/secrets.yml | +2 | Added 2 vault secrets (encrypted) |
| roles/plane/defaults/main.yml | +17 | Created defaults |
| roles/plane/tasks/main.yml | +24 | Created tasks |
| roles/plane/handlers/main.yml | +7 | Created handlers |
| roles/plane/templates/plane.env.j2 | +23 | Created env template |
| roles/docker-stack/templates/docker-compose.yml.j2 | +96 | Added 3 Plane services |

**Total**: 4 files created, 3 files modified, 172 lines added

## Commits

| Task | Commit | Message |
|------|--------|---------|
| T1 | fc9f536 | chore(01-01a): pin Plane v1.2.2 images and generate secrets |
| T2 | 5c4c02b | feat(01-01a): create Plane Ansible role structure |
| T3 | 30fc8b8 | feat(01-01a): create Plane environment template |
| T4 | 872fc4b | feat(01-01a): integrate Plane services into Docker Compose |

## Next Steps (Plan 01-01b)

1. Add Plane to PostgreSQL init.sql.j2 (create `plane_production` database and `plane` user)
2. Configure Caddy reverse proxy for `https://work.{{ domain_name }}`
3. Add Plane VPN-only ACL rules to Caddyfile
4. Deploy and verify containers start successfully

## Self-Check: PASSED

✅ All created files exist:
- roles/plane/tasks/main.yml
- roles/plane/handlers/main.yml
- roles/plane/defaults/main.yml
- roles/plane/templates/plane.env.j2

✅ All modified files exist:
- roles/docker-stack/templates/docker-compose.yml.j2
- inventory/group_vars/all/versions.yml
- inventory/group_vars/all/secrets.yml

✅ All commits exist:
- fc9f536: pin Plane v1.2.2 images and generate secrets
- 5c4c02b: create Plane Ansible role structure
- 30fc8b8: create Plane environment template
- 872fc4b: integrate Plane services into Docker Compose
