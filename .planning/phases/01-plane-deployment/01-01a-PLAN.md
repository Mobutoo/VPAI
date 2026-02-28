---
wave: 1
depends_on: []
files_modified:
  - roles/plane/tasks/main.yml
  - roles/plane/templates/plane.env.j2
  - roles/plane/handlers/main.yml
  - roles/plane/defaults/main.yml
  - roles/docker-stack/templates/docker-compose.yml.j2
  - inventory/group_vars/all/versions.yml
  - inventory/group_vars/all/secrets.yml
autonomous: true
---

# Plan 01-01a: Ansible Role - Plane Core Infrastructure (Role + Docker)

**Goal**: Create Plane Ansible role structure and integrate three containers (web, api, worker) into Docker Compose with proper security, resource limits, and network configuration.

**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-06

## Context

Plane is a modern project management platform (alternative to Jira/Linear) with Next.js frontend and Django backend. The official v1.2.2 release (Feb 23, 2026) requires three containers sharing the backend image with different commands. This plan creates the Ansible role structure following VPAI conventions and integrates Plane into the existing docker-compose.yml managed by the docker-stack role.

**Critical constraints:**
- VPS has 8GB RAM shared across 20+ services - Plane gets 512MB total (256MB web + 384MB api + 256MB worker)
- PostgreSQL password convention: ALL database users use `{{ postgresql_password }}` (shared convention, never create separate plane_password)
- Handlers with env_file: Must use `state: present` + `recreate: always` (not `state: restarted` which doesn't reload env files)
- Network configuration: plane-api and plane-worker need egress network for webhook delivery per INFRA-01

## Tasks

<task id="01-01a-T1" name="pin-plane-versions">
Add Plane Docker image versions to inventory/group_vars/all/versions.yml:
- plane_web_image: "makeplane/plane-frontend:v1.2.2"
- plane_api_image: "makeplane/plane-backend:v1.2.2"
- plane_worker_image: "makeplane/plane-backend:v1.2.2"

Add to inventory/group_vars/all/secrets.yml (Ansible Vault encrypted):
- vault_plane_secret_key: Generate 50-char random string for Django SECRET_KEY (JWT signing, CSRF)
- vault_plane_webhook_secret: Generate 32-char random string for webhook signature verification
</task>

<task id="01-01a-T2" name="create-plane-role">
Create Ansible role structure following VPAI pattern:

roles/plane/tasks/main.yml:
- Task: Create Plane config directory at /opt/{{ project_name }}/configs/plane/ (mode 0755, owner {{ prod_user }})
- Task: Create Plane data directory for uploads at /opt/{{ project_name }}/data/plane/uploads (mode 0755, owner 1000:1000 for container write)
- Task: Deploy plane.env template with notify handler "Restart plane stack"
- Tag: all tasks with [plane]

roles/plane/handlers/main.yml:
- Handler "Restart plane stack": Use community.docker.docker_compose_v2 with state: present + recreate: always (CRITICAL: state: restarted does NOT reload env_file)

roles/plane/defaults/main.yml:
- plane_config_dir: "/opt/{{ project_name }}/configs/plane"
- plane_data_dir: "/opt/{{ project_name }}/data/plane"
- plane_web_memory_limit: "256m"
- plane_web_cpu_limit: "0.25"
- plane_api_memory_limit: "384m"
- plane_api_cpu_limit: "0.5"
- plane_worker_memory_limit: "256m"
- plane_worker_cpu_limit: "0.25"
- plane_web_port: 3000
- plane_api_port: 8000
- plane_db_name: "plane_production"
- plane_db_user: "plane"

Use FQCN (ansible.builtin.file, community.docker.docker_compose_v2) and set changed_when/failed_when on any command/shell tasks.
</task>

<task id="01-01a-T3" name="create-plane-env-template">
Create roles/plane/templates/plane.env.j2 with Django/Plane configuration:

Required environment variables:
- SECRET_KEY={{ vault_plane_secret_key }} (Django cryptographic operations)
- DATABASE_URL=postgresql://{{ plane_db_user }}:{{ postgresql_password }}@postgresql:5432/{{ plane_db_name }} (shared PostgreSQL, CRITICAL: use postgresql_password NOT a separate variable)
- REDIS_URL=redis://redis:6379/0 (shared Redis, database 0 for cache)
- CELERY_BROKER_URL=redis://redis:6379/1 (Redis database 1 for Celery worker queue)
- WEB_URL=https://work.{{ domain_name }} (CORS origin, must match Caddy domain EXACTLY)
- CORS_ALLOWED_ORIGINS=https://work.{{ domain_name }}
- USE_MINIO=0 (disable MinIO, use local filesystem for v1)
- FILE_SIZE_LIMIT=52428800 (50MB attachment limit)
- PLANE_WEBHOOK_SECRET={{ vault_plane_webhook_secret }} (webhook HMAC signing)

All values must use Jinja2 variables (no hardcoded values per VPAI template convention).
</task>

<task id="01-01a-T4" name="integrate-docker-compose">
Add Plane services to roles/docker-stack/templates/docker-compose.yml.j2 in the APPLICATION LAYER section (after nocodb, before monitoring):

Service: plane-web
- image: {{ plane_web_image }}
- container_name: {{ project_name }}_plane_web
- restart: unless-stopped
- security_opt: no-new-privileges:true
- cap_drop: ALL / cap_add: [CHOWN, SETGID, SETUID] (standard VPAI pattern)
- env_file: {{ plane_config_dir }}/plane.env
- networks: [backend, frontend] (frontend for Caddy access, backend for API calls)
- deploy.resources.limits: memory {{ plane_web_memory_limit }}, cpus {{ plane_web_cpu_limit }}
- healthcheck: curl -f http://127.0.0.1:3000/ || exit 1 (interval 30s, timeout 10s, retries 5, start_period 60s)

Service: plane-api
- image: {{ plane_api_image }}
- container_name: {{ project_name }}_plane_api
- command: ["gunicorn", "plane.wsgi", "--workers", "2", "--bind", "0.0.0.0:8000"]
- restart: unless-stopped
- security_opt: no-new-privileges:true
- cap_drop: ALL / cap_add: [CHOWN, SETGID, SETUID]
- env_file: {{ plane_config_dir }}/plane.env
- networks: [backend, egress] (egress for webhook delivery per INFRA-01, backend for internal access)
- deploy.resources.limits: memory {{ plane_api_memory_limit }}, cpus {{ plane_api_cpu_limit }}
- healthcheck: curl -f http://127.0.0.1:8000/api/health || exit 1 (interval 30s, timeout 10s, retries 5, start_period 90s)

Service: plane-worker
- image: {{ plane_worker_image }}
- container_name: {{ project_name }}_plane_worker
- command: ["celery", "-A", "plane", "worker", "--loglevel=info"]
- restart: unless-stopped
- security_opt: no-new-privileges:true
- cap_drop: ALL / cap_add: [CHOWN, SETGID, SETUID]
- env_file: {{ plane_config_dir }}/plane.env
- networks: [backend, egress] (egress for external API calls and webhook delivery per INFRA-01)
- deploy.resources.limits: memory {{ plane_worker_memory_limit }}, cpus {{ plane_worker_cpu_limit }}
- healthcheck: celery -A plane inspect ping || exit 1 (interval 60s, timeout 20s, retries 3, start_period 120s)

All services mount /opt/{{ project_name }}/data/plane/uploads:/plane/media for shared upload storage.
Networks use "external: true" pattern (created by docker-compose-infra.yml).
</task>

## Verification Criteria

After execution:

1. **Role structure exists**:
   - `roles/plane/tasks/main.yml` contains 3 tasks (create dirs, deploy env)
   - `roles/plane/templates/plane.env.j2` has all required env vars with Jinja2 variables
   - `roles/plane/handlers/main.yml` has "Restart plane stack" handler with state: present + recreate: always
   - `roles/plane/defaults/main.yml` defines 12+ variables (directories, limits, ports)

2. **Docker Compose integration**:
   - `docker-compose.yml.j2` contains 3 new services: plane-web, plane-api, plane-worker
   - All services have security_opt, cap_drop/cap_add, resource limits, healthchecks
   - plane-web on networks [backend, frontend]
   - plane-api on networks [backend, egress] (INFRA-01 webhook delivery)
   - plane-worker on networks [backend, egress] (INFRA-01 webhook delivery)
   - Shared volume mount `/opt/.../data/plane/uploads:/plane/media` on all 3 services

3. **Versions pinned**:
   - versions.yml has plane_web_image, plane_api_image, plane_worker_image all set to v1.2.2
   - secrets.yml (encrypted) has vault_plane_secret_key (50 chars) and vault_plane_webhook_secret (32 chars)

4. **Code quality**:
   - All Ansible tasks use FQCN (ansible.builtin.*, community.docker.*)
   - No hardcoded values in templates (all use {{ variables }})
   - Handler uses correct pattern for env_file reload (state: present + recreate: always)
   - DATABASE_URL uses shared `{{ postgresql_password }}` (no separate plane_password variable)

## Must-Haves

Derived from phase goal: "Plane containers defined in Docker Compose with proper networking for webhook delivery"

1. **Plane role deployable**: Ansible role executes without errors (`ansible-playbook playbooks/site.yml --tags plane --check` passes lint)
2. **Egress network configured**: plane-api and plane-worker on egress network for webhook delivery (INFRA-01 requirement)
3. **Resource limits enforced**: Total Plane memory limit = 512MB (256+384+256) matches VPS constraints
4. **Shared infrastructure configured**: DATABASE_URL and REDIS_URL point to existing containers with correct credentials
5. **Security hardened**: All containers use cap_drop:ALL + minimal cap_add, no-new-privileges, non-root user (UID 1000)
6. **Template portability maintained**: Zero hardcoded values (seko, javisi, ewutelo) in any template - all use Jinja2 variables
