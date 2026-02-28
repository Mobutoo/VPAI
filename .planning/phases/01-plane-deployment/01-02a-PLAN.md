---
wave: 2
depends_on: ["01-01a", "01-01b"]
files_modified:
  - roles/postgresql/templates/init.sql.j2
  - roles/plane-provision/tasks/main.yml
  - roles/plane-provision/defaults/main.yml
  - roles/plane-provision/templates/provision-plane.sh.j2
  - playbooks/site.yml
autonomous: true
---

# Plan 01-02a: PostgreSQL Integration & Provisioning Role

**Goal**: Create Plane database in shared PostgreSQL and build Ansible role structure for workspace/agent provisioning.

**Requirements**: INFRA-02, INFRA-03, AUTH-01, AUTH-02, PROV-01, PROV-02, PROV-03, PROV-04

## Context

Plane requires a PostgreSQL database and Redis instance to function. VPAI architecture uses shared infrastructure services - PostgreSQL and Redis containers serve multiple applications (n8n, LiteLLM, NocoDB, Plane). Database provisioning follows VPAI convention: all database users share a single password `{{ postgresql_password }}` (documented in CLAUDE.md PostgreSQL section).

After infrastructure is running, Plane requires initial provisioning:
1. First boot creates instance admin account via web UI wizard (MANUAL)
2. Workspace "javisi" creation
3. API tokens for 10 OpenClaw agents
4. Custom fields (agent_id, cost_estimate, confidence_score, session_id)

**Critical constraints:**
- Database password convention: Use shared `{{ postgresql_password }}` for plane user (NEVER create plane_password)
- Provisioning is ONE-TIME operation - script must be idempotent (check existence before creation)
- API tokens require instance admin token - must be created after first manual login
- Custom fields require project_id from Onboarding project creation (PROV-04) - must capture and pass to field creation function

## Tasks

<task id="01-02a-T1" name="postgresql-database-provisioning">
**CRITICAL**: init.sql.j2 only executes on FIRST PostgreSQL container initialization (empty data directory). On Sese-AI production, javisi_postgresql is ALREADY running with existing data. The SQL in init.sql.j2 will NEVER execute.

**Solution**: Create database on live container using docker_container_exec.

Add to roles/postgresql/tasks/main.yml (AFTER container start task):

```yaml
- name: Create Plane database on existing PostgreSQL container
  community.docker.docker_container_exec:
    container: javisi_postgresql
    command: |
      psql -U postgres -c "CREATE DATABASE IF NOT EXISTS plane_production;"
      psql -U postgres -c "DO \$\$ BEGIN CREATE USER plane WITH PASSWORD '{{ postgresql_password }}'; EXCEPTION WHEN duplicate_object THEN null; END \$\$;"
      psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE plane_production TO plane;"
      psql -U postgres -c "ALTER DATABASE plane_production OWNER TO plane;"
      psql -U postgres -d plane_production -c "GRANT ALL ON SCHEMA public TO plane;"
  register: plane_db_create
  changed_when: "'already exists' not in plane_db_create.stderr"
  tags: [postgresql, plane]
```

ALSO update roles/postgresql/templates/init.sql.j2 for future fresh deployments:

```sql
-- Plane production database (for fresh PostgreSQL deployments only)
CREATE DATABASE plane_production;
CREATE USER plane WITH PASSWORD '{{ postgresql_password }}';
GRANT ALL PRIVILEGES ON DATABASE plane_production TO plane;
ALTER DATABASE plane_production OWNER TO plane;
\c plane_production
GRANT ALL ON SCHEMA public TO plane;
```

CRITICAL: User password MUST be `{{ postgresql_password }}` (shared convention, not a separate variable).
</task>

<task id="01-02a-T2" name="create-provision-role">
Create new Ansible role for Plane provisioning following VPAI pattern:

roles/plane-provision/tasks/main.yml:
- Task: Wait for Plane API health check (uri module, GET https://work.{{ domain_name }}/api/health, retry 12x delay 10s until status 200)
- Task: Check if workspace "javisi" exists (uri module, GET /api/v1/workspaces/, parse JSON response for slug match)
- Task: Create workspace "javisi" if not exists (uri module, POST /api/v1/workspaces/ with body {name: "javisi", slug: "javisi"}, status_code [201, 409])
- Task: Get default work item type ID for "Issue" (uri module, GET /api/v1/workspaces/javisi/work-item-types/, register fact)
- Task: Deploy provision script template
- Task: Execute provision script (shell module with creates flag for idempotence)
- Tag: all tasks with [plane-provision]

roles/plane-provision/defaults/main.yml:
- plane_workspace_slug: "javisi"
- plane_workspace_name: "javisi"
- plane_admin_email: "{{ admin_email }}" (from wizard variables)
- plane_concierge_email: "concierge@javisi.local"
- plane_concierge_password: "{{ vault_plane_concierge_password }}" (from secrets.yml, random-generated)
- plane_agent_names: ["concierge", "imhotep", "thot", "basquiat", "r2d2", "shuri", "piccolo", "cfo", "maintainer", "hermes"]
- plane_custom_fields: [{name: "agent_id", type: "text"}, {name: "cost_estimate", type: "number"}, {name: "confidence_score", type: "number"}, {name: "session_id", type: "text"}]

Use FQCN for all modules.
</task>

<task id="01-02a-T3" name="create-provision-script">
Create roles/plane-provision/templates/provision-plane.sh.j2 bash script for API provisioning:

Script structure:
1. Shebang: #!/bin/bash with set -euo pipefail
2. Variables: API_URL="https://work.{{ domain_name }}", ADMIN_TOKEN="{{ vault_plane_admin_api_token }}", WORKSPACE="javisi", CONCIERGE_PASSWORD="{{ vault_plane_concierge_password }}"
3. Function check_exists: Query API endpoint, return 0 if exists, 1 if not
4. Function create_user_account: POST to instance admin API /api/v1/users/ to create Plane user account (concierge@javisi.local) with generated password
5. Function create_api_token: POST to /api/v1/api-tokens/ with agent name label, store token in response
6. Function create_custom_field: POST to /api/v1/workspaces/${WORKSPACE}/projects/${PROJECT_ID}/work-item-types/${TYPE_ID}/work-item-properties/
7. Main logic:
   - Create Concierge user account (concierge@javisi.local) if not exists (AUTH-01 requirement)
   - Check if Onboarding project exists (GET /api/v1/workspaces/javisi/projects/)
   - If not: Create project "Onboarding" with identifier "ONBOARD", CAPTURE project_id from response using jq .id
   - Loop through plane_agent_names: create API token for each if not exists
   - Get work item type ID for "Issue"
   - Loop through plane_custom_fields: create each field using captured PROJECT_ID variable (PROV-04 fix)
   - Echo summary: "Created X tokens, Y custom fields, Z projects, Concierge user account"

CRITICAL (AUTH-01): create_user_account function creates Plane user via instance admin API:
```bash
create_user_account() {
  local email="$1"
  local password="$2"
  # Check if user exists
  if check_exists "/api/v1/users/?email=${email}"; then
    echo "User ${email} already exists, skipping"
    return 0
  fi
  # Create user account
  curl -X POST "${API_URL}/api/v1/users/" \
    -H "X-API-Key: ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    --data "{\"email\":\"${email}\",\"password\":\"${password}\",\"role\":\"member\"}" \
    --fail-with-body --max-time 30
}
```
Call in main logic: `create_user_account "concierge@javisi.local" "$CONCIERGE_PASSWORD"`

CRITICAL (PROV-04): When creating Onboarding project, capture the project_id from the API response:
```bash
PROJECT_ID=$(curl ... | jq -r '.id')
```
Then pass $PROJECT_ID to create_custom_field function calls:
```bash
create_custom_field "agent_id" "text" "$PROJECT_ID" "$TYPE_ID"
```

All curl commands use:
- -H "X-API-Key: ${ADMIN_TOKEN}"
- -H "Content-Type: application/json"
- --fail-with-body for error visibility
- --max-time 30 for timeout

Script must be idempotent (check before create, tolerate 409 Conflict responses).
</task>

<task id="01-02a-T4" name="handle-redis-namespace">
Document Redis key collision risk in roles/plane/defaults/main.yml:

Add comment block:
```yaml
# Redis namespace isolation
# Plane does NOT support REDIS_KEY_PREFIX configuration (as of v1.2.2).
# Shared Redis instance with n8n, LiteLLM. Collision risk is LOW:
# - Plane uses patterns: session:*, cache:*, celery:*
# - n8n uses: n8n:*
# - LiteLLM uses: litellm:*
# Monitor during smoke tests with: redis-cli KEYS '*' | grep -E '^(session|cache):'
# If collisions detected: add dedicated Redis container (64MB overhead) in v1.1 patch.
```

No code changes - documentation only for future troubleshooting.
</task>

<task id="01-02a-T5" name="update-playbook-provisioning">
Add plane-provision role to playbooks/site.yml in Phase 4.6 (Provisioning):

```yaml
# Phase 4.6: Provisioning (post-stack deployment)
- name: Provision Plane workspace and accounts
  hosts: prod
  roles:
    - role: plane-provision
      tags: [plane-provision]
```

Add after n8n-provision role (if exists) or create new Phase 4.6 section.

IMPORTANT: Provisioning runs AFTER docker-stack deployment (Phase 4.5) - Plane containers must be running before API calls.
</task>

## Verification Criteria

After execution:

1. **PostgreSQL integration**:
   - `init.sql.j2` contains CREATE DATABASE plane_production, CREATE USER plane, GRANT statements
   - User plane password is `{{ postgresql_password }}` (shared convention, no separate variable)
   - Schema privileges granted for Django migrations

2. **Provisioning role structure**:
   - `roles/plane-provision/tasks/main.yml` has 6+ tasks (health check, workspace check/create, provision script)
   - `roles/plane-provision/defaults/main.yml` defines workspace slug, concierge email/password, agent names list (10 agents), custom fields list (4 fields)
   - All tasks tagged [plane-provision] and use FQCN

3. **Provision script**:
   - `provision-plane.sh.j2` is valid bash with set -euo pipefail
   - Script has check_exists, create_user_account, and create_* helper functions
   - create_user_account function creates concierge@javisi.local with random password (AUTH-01 fix)
   - Onboarding project creation captures project_id using jq .id (PROV-04 fix)
   - create_custom_field calls use captured $PROJECT_ID variable
   - Main logic creates user account, then loops through agents and custom fields
   - All API calls use X-API-Key header authentication and --fail-with-body
   - Script is idempotent (checks existence before creation)

4. **Playbook integration**:
   - site.yml includes plane-provision role in Phase 4.6 with [plane-provision] tag
   - Provisioning runs after docker-stack deployment

5. **Code quality**:
   - All Ansible modules use FQCN
   - uri tasks handle [201, 409] status codes (created + already exists)
   - Bash script uses proper error handling and timeouts
   - No hardcoded domain/project names (all Jinja2 variables)

## Must-Haves

Derived from phase goal: "Database schema ready and provisioning automation scaffolded with project_id capture"

1. **Database schema ready**: PostgreSQL plane_production database created with correct user/permissions for Django migrations
2. **Shared password convention followed**: plane user uses `{{ postgresql_password }}` (violation would cause crash-loop authentication failures)
3. **Provisioning automation scaffolded**: Ansible role and bash script exist with user account creation, project_id capture for custom fields
4. **Concierge user account creation**: provision-plane.sh.j2 includes create_user_account function that creates concierge@javisi.local with vault_plane_concierge_password (AUTH-01 requirement)
5. **Project ID captured**: provision-plane.sh.j2 extracts project_id from Onboarding creation response and passes to custom field API calls (PROV-04 requirement)
6. **Idempotency guaranteed**: Provision script can be run multiple times without errors (checks existence before creation)
7. **Agent integration prepared**: 10 agent API token creation logic in script ready for execution
