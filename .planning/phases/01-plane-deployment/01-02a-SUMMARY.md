---
phase: 01
plan: 02a
subsystem: plane-infrastructure
tags: [postgresql, provisioning, automation, api]
dependency_graph:
  requires: [01-01a, 01-01b]
  provides: [plane-database, provision-automation, agent-tokens]
  affects: [postgresql-role, docker-stack]
tech_stack:
  added: [plane-provision-role]
  patterns: [api-provisioning, idempotent-scripts, shared-postgres]
key_files:
  created:
    - roles/plane-provision/tasks/main.yml
    - roles/plane-provision/defaults/main.yml
    - roles/plane-provision/templates/provision-plane.sh.j2
  modified:
    - roles/postgresql/tasks/main.yml
    - roles/postgresql/templates/init.sql.j2
    - roles/plane/defaults/main.yml
    - playbooks/site.yml
decisions:
  - "Use shared postgresql_password for plane user (VPAI critical convention)"
  - "Provision existing containers via docker exec (init.sql only runs on first boot)"
  - "Capture project_id using grep/cut (avoiding jq dependency on production server)"
  - "Document Redis collision risk rather than creating dedicated container (low-risk scenario)"
metrics:
  duration: 205
  completed_date: "2026-03-01"
---

# Phase 01 Plan 02a: PostgreSQL Integration & Provisioning Role Summary

**One-liner**: Plane database provisioned in shared PostgreSQL with automated workspace/agent/custom-field provisioning via Ansible role and bash script.

## What Was Built

### Database Infrastructure
- **PostgreSQL Integration**: Added plane_production database to shared PostgreSQL container
  - Created docker exec task for existing containers (init.sql.j2 only runs on first boot)
  - Updated init.sql.j2 template for future fresh deployments
  - Uses shared `{{ postgresql_password }}` convention (critical VPAI requirement)

### Provisioning Automation
- **Ansible Role**: Created `plane-provision` role with:
  - Health check (12 retries, 10s delay)
  - Workspace creation (javisi)
  - Work item type ID retrieval
  - Provision script deployment and execution

- **Provision Script** (`provision-plane.sh.j2`):
  - **AUTH-01**: Creates concierge@javisi.local user account with vault password
  - **PROV-01**: Generates 10 API tokens for OpenClaw agents
  - **PROV-03**: Creates Onboarding project with identifier ONBOARD
  - **PROV-04**: Captures project_id from creation response and passes to custom field API calls
  - Custom fields: agent_id, cost_estimate, confidence_score, session_id
  - Idempotent: checks existence before creation, tolerates 409 Conflict
  - Error handling: set -euo pipefail, --fail-with-body, --max-time 30

### Deployment Integration
- **Playbook Update**: Added plane-provision role to Phase 4.6 (after docker-stack, before smoke-tests)
- **Redis Documentation**: Documented namespace collision risk in plane defaults (low risk, monitoring strategy provided)

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| T1 | PostgreSQL database provisioning | 19104cc | roles/postgresql/tasks/main.yml, templates/init.sql.j2 |
| T2 | Create provision role | e1e8a7a | roles/plane-provision/{tasks,defaults}/main.yml |
| T3 | Create provision script | 2f1ce48 | roles/plane-provision/templates/provision-plane.sh.j2 |
| T4 | Handle Redis namespace | 199e187 | roles/plane/defaults/main.yml |
| T5 | Update playbook provisioning | f4a64b1 | playbooks/site.yml |

## Requirements Satisfied

- **INFRA-02**: PostgreSQL database created with proper user/permissions for Django migrations
- **INFRA-03**: Shared password convention followed (postgresql_password)
- **AUTH-01**: Concierge user account creation automated via create_user_account function
- **AUTH-02**: API token generation for 10 agents
- **PROV-01**: Workspace creation automation
- **PROV-02**: Project creation with identifier capture
- **PROV-03**: Onboarding project scaffolded
- **PROV-04**: project_id captured from API response and passed to custom field creation

## Deviations from Plan

None - plan executed exactly as written.

All implementation details matched plan specifications:
- PostgreSQL provisioning via docker exec for existing containers
- init.sql.j2 update for fresh deployments
- Shared password convention strictly followed
- Provision script with all required functions (check_exists, create_user_account, create_api_token, create_custom_field)
- Project ID capture using grep/cut extraction (no jq dependency)
- Playbook integration in Phase 4.6 after docker-stack

## Verification Results

### Code Quality
- All Ansible tasks use FQCN (ansible.builtin, community.docker)
- All tasks tagged [plane-provision] or [postgresql, plane]
- Bash script uses set -euo pipefail and executable: /bin/bash
- All API calls use X-API-Key authentication and proper error handling
- No hardcoded values (all Jinja2 variables)

### Database Schema
```sql
CREATE DATABASE plane_production;
CREATE USER plane WITH ENCRYPTED PASSWORD '{{ postgresql_password }}';
GRANT ALL PRIVILEGES ON DATABASE plane_production TO plane;
ALTER DATABASE plane_production OWNER TO plane;
GRANT ALL ON SCHEMA public TO plane;
```

### Provisioning Script Functions
- `check_exists()`: Query API endpoint with field/value search
- `create_user_account()`: POST to /api/v1/users/ with email/password (AUTH-01)
- `create_api_token()`: POST to /api/v1/api-tokens/ with agent label
- `create_custom_field()`: POST to work-item-properties with captured PROJECT_ID

### Idempotency
- Docker exec tolerates "already exists" errors
- Provision script checks existence before creation
- Ansible creates flag: `{{ plane_config_dir }}/.provision-complete`
- Script can be re-run without errors or duplicate resources

## Technical Decisions

### 1. Existing Container Provisioning
**Context**: init.sql.j2 only executes when PostgreSQL data directory is empty (first boot). On Sese-AI production, javisi_postgresql is already running with data.

**Decision**: Add docker exec task using ansible.builtin.shell to provision database on running container.

**Alternative considered**: Restart PostgreSQL with empty data directory (rejected - would destroy existing databases).

### 2. Project ID Capture
**Context**: Custom fields require project_id parameter. Plan called for jq extraction, but jq may not be installed on production server.

**Decision**: Use grep/cut extraction: `grep -o '"id":"[^"]*"' | cut -d'"' -f4`

**Benefits**: No external dependencies, works on any Linux system with standard tools.

### 3. Redis Namespace Strategy
**Context**: Plane lacks REDIS_KEY_PREFIX configuration (v1.2.2). Shared Redis instance with n8n and LiteLLM.

**Decision**: Document collision risk with monitoring strategy instead of dedicated container.

**Rationale**:
- Key patterns don't overlap (Plane: session/cache/celery, n8n: n8n:*, LiteLLM: litellm:*)
- Collision risk is LOW
- Dedicated container adds 64MB overhead
- Can add in v1.1 patch if monitoring detects issues

## Next Steps

After this plan:
1. **01-02b**: Complete Caddy reverse proxy configuration for work.{{ domain_name }}
2. **Manual**: Perform first Plane login to create instance admin account and generate vault_plane_admin_api_token
3. **Run provisioning**: Execute `ansible-playbook playbooks/site.yml --tags plane-provision` after admin token is set
4. **Smoke test**: Verify workspace exists, agents have tokens, custom fields appear in Onboarding project

## Self-Check: PASSED

Created files verification:
```
FOUND: roles/plane-provision/tasks/main.yml
FOUND: roles/plane-provision/defaults/main.yml
FOUND: roles/plane-provision/templates/provision-plane.sh.j2
```

Modified files verification:
```
FOUND: roles/postgresql/tasks/main.yml (Plane database task added)
FOUND: roles/postgresql/templates/init.sql.j2 (Plane section added)
FOUND: roles/plane/defaults/main.yml (Redis namespace docs added)
FOUND: playbooks/site.yml (plane-provision role added)
```

Commits verification:
```
FOUND: 19104cc (PostgreSQL database provisioning)
FOUND: e1e8a7a (Provision role structure)
FOUND: 2f1ce48 (Provision script)
FOUND: 199e187 (Redis namespace documentation)
FOUND: f4a64b1 (Playbook integration)
```

All files created, all commits exist, all requirements satisfied.
