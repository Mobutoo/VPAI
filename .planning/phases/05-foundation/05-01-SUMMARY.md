---
phase: 05-foundation
plan: 01
subsystem: infra
tags: [ansible, docker-compose, caddy, postgresql, kitsu, cgwire, backup, fal-ai]

# Dependency graph
requires:
  - phase: 04-notifications
    provides: Plane milestone complete, existing docker-compose and Caddy patterns
provides:
  - Kitsu Ansible role (roles/kitsu/) with env, supervisord override, handler
  - Kitsu Docker Compose service definition with healthcheck and resource limits
  - Caddy VPN-only reverse proxy for boss.<domain>
  - PostgreSQL kitsu_production database with user zou
  - FAL_KEY injection into n8n container environment
  - Kitsu database included in daily Zerobyte backup dump
  - Kitsu container metrics via cAdvisor autodiscovery (no Alloy config change)
affects: [05-03-kitsu-provisioning, docker-stack, caddy, postgresql, backup-config]

# Tech tracking
tech-stack:
  added: [cgwire/cgwire:1.0.17]
  patterns: [supervisord-override-external-services, env-file-handler-recreate]

key-files:
  created:
    - roles/kitsu/tasks/main.yml
    - roles/kitsu/defaults/main.yml
    - roles/kitsu/handlers/main.yml
    - roles/kitsu/meta/main.yml
    - roles/kitsu/templates/kitsu.env.j2
    - roles/kitsu/templates/supervisord.conf.j2
  modified:
    - inventory/group_vars/all/versions.yml
    - roles/postgresql/defaults/main.yml
    - roles/postgresql/templates/init.sql.j2
    - roles/docker-stack/templates/docker-compose.yml.j2
    - roles/caddy/templates/Caddyfile.j2
    - roles/n8n/templates/n8n.env.j2
    - roles/backup-config/templates/pre-backup.sh.j2
    - playbooks/site.yml

key-decisions:
  - "Shared postgresql_password for zou user (project convention -- single password for all DB users)"
  - "Supervisord override disables internal PG/Redis and removes DB creds from gunicorn env line"
  - "Healthcheck uses shallow /api/health (nginx+gunicorn liveness) -- deep DB check deferred to Plan 03 zou upgrade-db"
  - "Added nocodb to backup dump loop (was missing -- Rule 2 fix from RESEARCH.md pitfall 6)"

patterns-established:
  - "Kitsu role follows nocodb role pattern: config dir, data dir, env template, handler with recreate: always"
  - "Supervisord override pattern: mount custom supervisord.conf:ro to disable internal services in all-in-one images"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06]

# Metrics
duration: 4min
completed: 2026-03-17
---

# Phase 5 Plan 01: Kitsu Ansible Role + Infra Config Summary

**Kitsu Ansible role with Docker Compose service, Caddy VPN proxy at boss.<domain>, PostgreSQL zou user, supervisord override for external DB/Redis, FAL_KEY in n8n, and backup integration**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-17T16:17:46Z
- **Completed:** 2026-03-17T16:22:06Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Complete roles/kitsu/ Ansible role with 6 files following VPAI conventions (FQCN, tags, become, handler recreate)
- Kitsu Docker Compose entry with cap_drop ALL, resource limits (512M/1.0 CPU), healthcheck, supervisord.conf volume mount
- Caddy boss.<domain> VPN-only site block using import vpn_only snippet (2-CIDR pattern)
- PostgreSQL kitsu_production DB + zou user added to provisioning loop (init.sql.j2 + provision-postgresql.sh.j2 auto-picks up)
- FAL_KEY environment variable injected into n8n container for content factory workflows
- Backup pre-backup.sh now dumps nocodb + kitsu_production (was only n8n + litellm)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create roles/kitsu/ Ansible role** - `f21fe99` (feat)
2. **Task 2: Integrate Kitsu into 8 existing files** - `15fa5d3` (feat)

## Files Created/Modified
- `roles/kitsu/defaults/main.yml` - Kitsu config/data dirs and resource limits defaults
- `roles/kitsu/tasks/main.yml` - 4 tasks: config dir, data dirs (loop), env template, supervisord override
- `roles/kitsu/handlers/main.yml` - Restart handler with recreate: always (env_file convention)
- `roles/kitsu/meta/main.yml` - Galaxy metadata matching project conventions
- `roles/kitsu/templates/kitsu.env.j2` - Zou env: external PG (zou user), Redis, secret key, locale
- `roles/kitsu/templates/supervisord.conf.j2` - Disables internal PG/Redis, removes DB creds from gunicorn env
- `inventory/group_vars/all/versions.yml` - Pinned kitsu_image cgwire/cgwire:1.0.17
- `roles/postgresql/defaults/main.yml` - Added kitsu_production to postgresql_databases list
- `roles/postgresql/templates/init.sql.j2` - Added Kitsu DB block for fresh PG deployments
- `roles/docker-stack/templates/docker-compose.yml.j2` - Kitsu service with all security/resource/healthcheck settings
- `roles/caddy/templates/Caddyfile.j2` - boss.<domain> VPN-only reverse proxy to kitsu:80
- `roles/n8n/templates/n8n.env.j2` - FAL_KEY conditional injection for Fal.ai API
- `roles/backup-config/templates/pre-backup.sh.j2` - Added nocodb + kitsu_production to pg_dump loop
- `playbooks/site.yml` - Added kitsu role in Phase 3 applications section

## Decisions Made
- Used shared postgresql_password for zou user (project convention: single password for all DB users)
- Supervisord override removes DB_USERNAME/DB_PASSWORD from gunicorn environment line to allow Docker env vars to flow through
- Docker healthcheck uses shallow /api/health endpoint (nginx+gunicorn liveness only); deep DB connectivity verified during provisioning (Plan 03)
- Added nocodb to backup dump loop alongside kitsu_production (was missing from original backup config -- pitfall from RESEARCH.md)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed meta/main.yml to pass ansible-lint schema validation**
- **Found during:** Task 2 (lint verification)
- **Issue:** Plan's meta/main.yml template was missing required galaxy_info fields (author, license, namespace, min_ansible_version, platforms)
- **Fix:** Added all required fields matching nocodb role pattern
- **Files modified:** roles/kitsu/meta/main.yml
- **Verification:** make lint passes with 0 failures
- **Committed in:** 15fa5d3 (Task 2 commit)

**2. [Rule 2 - Missing Critical] Added nocodb to backup dump loop**
- **Found during:** Task 2 (backup-config modification)
- **Issue:** Plan specified adding nocodb to backup loop alongside kitsu_production (pitfall 6 from RESEARCH.md -- nocodb was missing from dumps)
- **Fix:** Changed loop from `n8n litellm` to `n8n litellm nocodb kitsu_production`
- **Files modified:** roles/backup-config/templates/pre-backup.sh.j2
- **Verification:** grep confirms kitsu_production in backup loop
- **Committed in:** 15fa5d3 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both fixes necessary for correctness. Nocodb backup addition was explicitly planned. No scope creep.

## Issues Encountered
None -- plan executed cleanly after meta/main.yml lint fix.

## User Setup Required
None - no external service configuration required. The kitsu_secret_key and fal_ai_api_key must already be in Ansible Vault (added during project setup per STATE.md decisions).

## Next Phase Readiness
- Kitsu role ready for deployment via `ansible-playbook playbooks/site.yml --tags kitsu,docker-stack,caddy,postgresql,backup-config`
- Plan 05-02 (NocoDB data model) can proceed independently
- Plan 05-03 (Kitsu provisioning: zou upgrade-db, admin user, project structure) depends on this plan being deployed first

---
*Phase: 05-foundation*
*Completed: 2026-03-17*
