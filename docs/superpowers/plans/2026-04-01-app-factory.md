# App Factory Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the App Factory infrastructure — Ansible roles, playbooks, GitHub Actions workflow, NocoDB/Qdrant provisioning, and scaffold templates — so that the PRD-to-deploy pipeline is ready to use.

**Architecture:** Ansible provisioning role creates NocoDB tables + Qdrant collections on Sese-AI. A new `app-scaffold` role configures Hetzner for GHCR pull + Docker networks. A `deploy-app.yml` GitHub Actions workflow handles deploy via Ansible. Scaffold templates (CI, Dockerfile, CLAUDE.md) are stored as Jinja2 templates for `af-intake` to push to new repos. n8n workflows are built via n8n UI using the spec as reference (not coded here).

**Tech Stack:** Ansible 2.16+, Docker Compose V2, GitHub Actions, NocoDB API v2, Qdrant HTTP API, GHCR, Jinja2

**Spec:** `docs/superpowers/specs/2026-04-01-app-factory-design.md`

---

## File Structure

### New files

```
roles/app-factory-provision/
├── defaults/main.yml                      # NocoDB/Qdrant URLs, collection names, table config
├── tasks/main.yml                         # Deploy + execute provisioning scripts
└── templates/
    ├── provision-nocodb-tables.sh.j2      # Create 6 NocoDB tables (idempotent)
    └── provision-qdrant.sh.j2             # Create 2 Qdrant collections (idempotent)

roles/app-scaffold/
├── defaults/main.yml                      # GHCR user, resource limits, network config
├── tasks/main.yml                         # GHCR auth, base dirs, Docker networks
├── handlers/main.yml                      # Restart app handler (generic)
└── templates/
    ├── docker-config.json.j2              # GHCR pull credentials
    └── scaffold-templates/
        ├── ci.yml.j2                      # GitHub Actions CI template for new repos
        ├── CLAUDE.md.j2                   # Claude Code conventions template
        └── Dockerfile.j2                  # Multi-stage Dockerfile template

playbooks/app-prod.yml                     # App deployment playbook for Hetzner

.github/workflows/deploy-app.yml          # GitHub Actions deploy workflow for app-prod
```

### Modified files

```
inventory/group_vars/all/secrets.yml       # Add vault_ghcr_pull_token, vault_af_webhook_secret
playbooks/site.yml                         # Add app-factory-provision role (phase 4.6)
```

---

## Task 1: App Factory NocoDB Provisioning

Create the provisioning role for NocoDB tables (6 tables: projects, commits, phase_logs, decisions, deployments, error_logs).

**Files:**
- Create: `roles/app-factory-provision/defaults/main.yml`
- Create: `roles/app-factory-provision/tasks/main.yml`
- Create: `roles/app-factory-provision/templates/provision-nocodb-tables.sh.j2`

- [ ] **Step 1: Create defaults**

```yaml
# roles/app-factory-provision/defaults/main.yml
---
# app-factory-provision — defaults
app_factory_config_dir: "/opt/{{ project_name }}/configs/app-factory"

# NocoDB API (uses existing deployed instance)
app_factory_nocodb_base_url: "https://{{ nocodb_subdomain }}.{{ domain_name }}"
app_factory_nocodb_base_name: "app-factory"

# Qdrant API (uses existing deployed instance)
app_factory_qdrant_base_url: "https://{{ qdrant_subdomain }}.{{ domain_name }}"
app_factory_qdrant_rex_collection: "app-factory-rex"
app_factory_qdrant_patterns_collection: "app-factory-patterns"
app_factory_qdrant_vector_size: 1536
app_factory_qdrant_distance: "Cosine"
```

- [ ] **Step 2: Create tasks**

Follow the exact pattern from `roles/content-factory-provision/tasks/main.yml`:

```yaml
# roles/app-factory-provision/tasks/main.yml
---
# app-factory-provision — tasks

- name: Create app-factory config directory
  ansible.builtin.file:
    path: "{{ app_factory_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true
  tags: [app-factory-provision]

- name: Deploy NocoDB table provisioning script
  ansible.builtin.template:
    src: provision-nocodb-tables.sh.j2
    dest: "{{ app_factory_config_dir }}/provision-nocodb-tables.sh"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0750"
  become: true
  tags: [app-factory-provision]

- name: Execute NocoDB table provisioning
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: "{{ app_factory_config_dir }}/provision-nocodb-tables.sh"
    creates: "{{ app_factory_config_dir }}/.nocodb-provision-complete"
  become: true
  register: af_nocodb_provision_result
  changed_when: af_nocodb_provision_result.rc == 0
  failed_when: af_nocodb_provision_result.rc != 0
  when: not (common_molecule_mode | default(false))
  tags: [app-factory-provision]

- name: Display NocoDB provision summary
  ansible.builtin.debug:
    msg: "{{ af_nocodb_provision_result.stdout_lines }}"
  when: af_nocodb_provision_result.stdout_lines is defined
  tags: [app-factory-provision]

- name: Deploy Qdrant provisioning script
  ansible.builtin.template:
    src: provision-qdrant.sh.j2
    dest: "{{ app_factory_config_dir }}/provision-qdrant.sh"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0750"
  become: true
  tags: [app-factory-provision]

- name: Execute Qdrant provisioning
  ansible.builtin.shell:
    executable: /bin/bash
    cmd: "{{ app_factory_config_dir }}/provision-qdrant.sh"
    creates: "{{ app_factory_config_dir }}/.qdrant-provision-complete"
  become: true
  register: af_qdrant_provision_result
  changed_when: af_qdrant_provision_result.rc == 0
  failed_when: af_qdrant_provision_result.rc != 0
  when: not (common_molecule_mode | default(false))
  tags: [app-factory-provision]

- name: Display Qdrant provision summary
  ansible.builtin.debug:
    msg: "{{ af_qdrant_provision_result.stdout_lines }}"
  when: af_qdrant_provision_result.stdout_lines is defined
  tags: [app-factory-provision]
```

- [ ] **Step 3: Create NocoDB provisioning script**

Template: `roles/app-factory-provision/templates/provision-nocodb-tables.sh.j2`

Follow the pattern from `roles/content-factory-provision/templates/provision-nocodb-tables.sh.j2`. Key differences:
- Base name: `app-factory` (not `content-factory`)
- 6 tables: `projects`, `commits`, `phase_logs`, `decisions`, `deployments`, `error_logs`
- No seed data (unlike content-factory which seeds Paul Taff brand)

```bash
#!/bin/bash
# {{ ansible_managed }}
# NocoDB App Factory table provisioning — idempotent
# Creates tables: projects, commits, phase_logs, decisions, deployments, error_logs

set -euo pipefail

BASE_URL="{{ app_factory_nocodb_base_url }}"
TOKEN="{{ nocodb_api_token }}"
SENTINEL="{{ app_factory_config_dir }}/.nocodb-provision-complete"

if [ -f "$SENTINEL" ]; then
  echo "NocoDB app-factory tables already provisioned (sentinel exists). Skipping."
  exit 0
fi

echo "[$(date)] Starting NocoDB App Factory provisioning..."

# Step 1: Find or create the app-factory base
echo "[$(date)] Looking for app-factory base..."
BASES=$(curl -sf -H "xc-token: ${TOKEN}" "${BASE_URL}/api/v2/meta/bases/")
BASE_ID=$(echo "$BASES" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for b in data.get('list', []):
    if b['title'] == '{{ app_factory_nocodb_base_name }}':
        print(b['id'])
        break
" 2>/dev/null || true)

if [ -z "$BASE_ID" ]; then
  echo "[$(date)] Creating app-factory base..."
  CREATE_RESULT=$(curl -sf -X POST \
    -H "xc-token: ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${BASE_URL}/api/v2/meta/bases/" \
    -d '{"title": "{{ app_factory_nocodb_base_name }}", "type": "database"}')
  BASE_ID=$(echo "$CREATE_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
  echo "[$(date)] Base created: $BASE_ID"
else
  echo "[$(date)] Base found: $BASE_ID"
fi

# Step 2: List existing tables
TABLES=$(curl -sf -H "xc-token: ${TOKEN}" "${BASE_URL}/api/v2/meta/bases/${BASE_ID}/tables")

table_exists() {
  echo "$TABLES" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('list', []):
    if t['title'] == '$1':
        print(t['id'])
        break
" 2>/dev/null || true
}

# Step 3: Create projects table
PROJECTS_ID=$(table_exists "projects")
if [ -z "$PROJECTS_ID" ]; then
  echo "[$(date)] Creating projects table..."
  RESULT=$(curl -sf -X POST \
    -H "xc-token: ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${BASE_URL}/api/v2/meta/bases/${BASE_ID}/tables" \
    -d '{
      "title": "projects",
      "columns": [
        {"title": "name", "uidt": "SingleLineText"},
        {"title": "repo", "uidt": "SingleLineText"},
        {"title": "stack", "uidt": "SingleLineText"},
        {"title": "plane_id", "uidt": "SingleLineText"},
        {"title": "status", "uidt": "SingleSelect", "dtxp": "intake,design,build,ci,ship,operate,learn,complete"},
        {"title": "started_at", "uidt": "DateTime"},
        {"title": "phases_completed", "uidt": "Number"},
        {"title": "total_duration", "uidt": "Number"},
        {"title": "total_commits", "uidt": "Number"},
        {"title": "last_rex_at", "uidt": "DateTime"}
      ]
    }')
  PROJECTS_ID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
  echo "[$(date)] projects table created: $PROJECTS_ID"
else
  echo "[$(date)] projects table exists: $PROJECTS_ID"
fi

# Step 4: Create commits table
COMMITS_ID=$(table_exists "commits")
if [ -z "$COMMITS_ID" ]; then
  echo "[$(date)] Creating commits table..."
  RESULT=$(curl -sf -X POST \
    -H "xc-token: ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${BASE_URL}/api/v2/meta/bases/${BASE_ID}/tables" \
    -d '{
      "title": "commits",
      "columns": [
        {"title": "hash", "uidt": "SingleLineText"},
        {"title": "repo", "uidt": "SingleLineText"},
        {"title": "message", "uidt": "LongText"},
        {"title": "plane_work_item", "uidt": "SingleLineText"},
        {"title": "files_changed", "uidt": "Number"},
        {"title": "timestamp", "uidt": "DateTime"}
      ]
    }')
  COMMITS_ID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
  echo "[$(date)] commits table created: $COMMITS_ID"
else
  echo "[$(date)] commits table exists: $COMMITS_ID"
fi

# Step 5: Create phase_logs table
PHASE_LOGS_ID=$(table_exists "phase_logs")
if [ -z "$PHASE_LOGS_ID" ]; then
  echo "[$(date)] Creating phase_logs table..."
  RESULT=$(curl -sf -X POST \
    -H "xc-token: ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${BASE_URL}/api/v2/meta/bases/${BASE_ID}/tables" \
    -d '{
      "title": "phase_logs",
      "columns": [
        {"title": "project", "uidt": "SingleLineText"},
        {"title": "phase", "uidt": "Number"},
        {"title": "phase_name", "uidt": "SingleLineText"},
        {"title": "duration_min", "uidt": "Number"},
        {"title": "files_count", "uidt": "Number"},
        {"title": "decisions_count", "uidt": "Number"},
        {"title": "timestamp", "uidt": "DateTime"}
      ]
    }')
  PHASE_LOGS_ID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
  echo "[$(date)] phase_logs table created: $PHASE_LOGS_ID"
else
  echo "[$(date)] phase_logs table exists: $PHASE_LOGS_ID"
fi

# Step 6: Create decisions table
DECISIONS_ID=$(table_exists "decisions")
if [ -z "$DECISIONS_ID" ]; then
  echo "[$(date)] Creating decisions table..."
  RESULT=$(curl -sf -X POST \
    -H "xc-token: ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${BASE_URL}/api/v2/meta/bases/${BASE_ID}/tables" \
    -d '{
      "title": "decisions",
      "columns": [
        {"title": "project", "uidt": "SingleLineText"},
        {"title": "phase", "uidt": "Number"},
        {"title": "context", "uidt": "LongText"},
        {"title": "options", "uidt": "JSON"},
        {"title": "choice", "uidt": "SingleLineText"},
        {"title": "reason", "uidt": "LongText"},
        {"title": "timestamp", "uidt": "DateTime"}
      ]
    }')
  DECISIONS_ID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
  echo "[$(date)] decisions table created: $DECISIONS_ID"
else
  echo "[$(date)] decisions table exists: $DECISIONS_ID"
fi

# Step 7: Create deployments table
DEPLOYMENTS_ID=$(table_exists "deployments")
if [ -z "$DEPLOYMENTS_ID" ]; then
  echo "[$(date)] Creating deployments table..."
  RESULT=$(curl -sf -X POST \
    -H "xc-token: ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${BASE_URL}/api/v2/meta/bases/${BASE_ID}/tables" \
    -d '{
      "title": "deployments",
      "columns": [
        {"title": "repo", "uidt": "SingleLineText"},
        {"title": "version", "uidt": "SingleLineText"},
        {"title": "env", "uidt": "SingleLineText"},
        {"title": "duration_sec", "uidt": "Number"},
        {"title": "smoke_result", "uidt": "SingleSelect", "dtxp": "pass,fail,rollback"},
        {"title": "ansible_rc", "uidt": "Number"},
        {"title": "timestamp", "uidt": "DateTime"}
      ]
    }')
  DEPLOYMENTS_ID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
  echo "[$(date)] deployments table created: $DEPLOYMENTS_ID"
else
  echo "[$(date)] deployments table exists: $DEPLOYMENTS_ID"
fi

# Step 8: Create error_logs table
ERROR_LOGS_ID=$(table_exists "error_logs")
if [ -z "$ERROR_LOGS_ID" ]; then
  echo "[$(date)] Creating error_logs table..."
  RESULT=$(curl -sf -X POST \
    -H "xc-token: ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${BASE_URL}/api/v2/meta/bases/${BASE_ID}/tables" \
    -d '{
      "title": "error_logs",
      "columns": [
        {"title": "workflow", "uidt": "SingleLineText"},
        {"title": "error_message", "uidt": "LongText"},
        {"title": "error_node", "uidt": "SingleLineText"},
        {"title": "project", "uidt": "SingleLineText"},
        {"title": "timestamp", "uidt": "DateTime"},
        {"title": "resolved_at", "uidt": "DateTime"}
      ]
    }')
  ERROR_LOGS_ID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
  echo "[$(date)] error_logs table created: $ERROR_LOGS_ID"
else
  echo "[$(date)] error_logs table exists: $ERROR_LOGS_ID"
fi

# Output table IDs for Ansible to capture
echo "NOCODB_AF_BASE_ID=${BASE_ID}"
echo "NOCODB_PROJECTS_TABLE_ID=${PROJECTS_ID}"
echo "NOCODB_COMMITS_TABLE_ID=${COMMITS_ID}"
echo "NOCODB_PHASE_LOGS_TABLE_ID=${PHASE_LOGS_ID}"
echo "NOCODB_DECISIONS_TABLE_ID=${DECISIONS_ID}"
echo "NOCODB_DEPLOYMENTS_TABLE_ID=${DEPLOYMENTS_ID}"
echo "NOCODB_ERROR_LOGS_TABLE_ID=${ERROR_LOGS_ID}"

# Write sentinel
touch "$SENTINEL"
echo "[$(date)] NocoDB App Factory provisioning complete."
```

- [ ] **Step 4: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/app-factory-provision/`
Expected: 0 warnings, 0 errors

- [ ] **Step 5: Commit**

```bash
git add roles/app-factory-provision/defaults/main.yml \
  roles/app-factory-provision/tasks/main.yml \
  roles/app-factory-provision/templates/provision-nocodb-tables.sh.j2
git commit -m "feat(app-factory): add NocoDB provisioning role — 6 tables"
```

---

## Task 2: Qdrant Collections Provisioning

Add Qdrant collection creation to the provisioning role (2 collections: app-factory-rex, app-factory-patterns).

**Files:**
- Create: `roles/app-factory-provision/templates/provision-qdrant.sh.j2`

- [ ] **Step 1: Create Qdrant provisioning script**

Follow the pattern from `roles/content-factory-provision/templates/provision-qdrant.sh.j2` but simpler — no seed data, just collection creation.

```bash
#!/bin/bash
# {{ ansible_managed }}
# Qdrant App Factory collections provisioning — idempotent
# Creates collections: app-factory-rex, app-factory-patterns

set -euo pipefail

QDRANT_URL="{{ app_factory_qdrant_base_url }}"
QDRANT_KEY="{{ qdrant_api_key }}"
VECTOR_SIZE="{{ app_factory_qdrant_vector_size }}"
DISTANCE="{{ app_factory_qdrant_distance }}"
SENTINEL="{{ app_factory_config_dir }}/.qdrant-provision-complete"

if [ -f "$SENTINEL" ]; then
  echo "Qdrant app-factory already provisioned (sentinel exists). Skipping."
  exit 0
fi

echo "[$(date)] Starting Qdrant App Factory provisioning..."

create_collection() {
  local NAME="$1"
  echo "[$(date)] Creating/verifying collection ${NAME}..."
  HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' -X PUT \
    -H "api-key: ${QDRANT_KEY}" \
    -H "Content-Type: application/json" \
    "${QDRANT_URL}/collections/${NAME}" \
    -d "{\"vectors\": {\"size\": ${VECTOR_SIZE}, \"distance\": \"${DISTANCE}\"}}" \
    2>/dev/null || echo "000")

  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "409" ]; then
    echo "[$(date)] Collection ${NAME} ready (HTTP ${HTTP_CODE})"
  else
    echo "[$(date)] ERROR: Failed to create collection ${NAME} (HTTP ${HTTP_CODE})"
    exit 1
  fi
}

create_collection "{{ app_factory_qdrant_rex_collection }}"
create_collection "{{ app_factory_qdrant_patterns_collection }}"

touch "$SENTINEL"
echo "[$(date)] Qdrant App Factory provisioning complete."
```

- [ ] **Step 2: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/app-factory-provision/`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add roles/app-factory-provision/templates/provision-qdrant.sh.j2
git commit -m "feat(app-factory): add Qdrant provisioning — 2 collections"
```

---

## Task 3: Register Provisioning Role in site.yml

Add `app-factory-provision` to the main playbook alongside other provisioning roles.

**Files:**
- Modify: `playbooks/site.yml:100-108`

- [ ] **Step 1: Add role to site.yml**

After the `content-factory-provision` entry (line 108), add:

```yaml
    - role: app-factory-provision
      tags: [app-factory-provision, phase4]
```

- [ ] **Step 2: Lint full playbook**

Run: `source .venv/bin/activate && ansible-lint playbooks/site.yml`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add playbooks/site.yml
git commit -m "feat(app-factory): register provisioning role in site.yml"
```

---

## Task 4: App Scaffold Role — GHCR Auth & Base Dirs

Create the `app-scaffold` role that prepares a Hetzner server for app deployment: GHCR pull credentials, base directories, Docker networks.

**Files:**
- Create: `roles/app-scaffold/defaults/main.yml`
- Create: `roles/app-scaffold/tasks/main.yml`
- Create: `roles/app-scaffold/handlers/main.yml`
- Create: `roles/app-scaffold/templates/docker-config.json.j2`

- [ ] **Step 1: Create defaults**

```yaml
# roles/app-scaffold/defaults/main.yml
---
# app-scaffold — defaults
# Base infrastructure for App Factory apps on Hetzner

# GHCR pull authentication
app_scaffold_ghcr_user: "Mobutoo"
app_scaffold_ghcr_token: "{{ vault_ghcr_pull_token }}"

# Docker config location (for GHCR pull)
app_scaffold_docker_config_dir: "/root/.docker"

# Base directory for app configs on Hetzner
app_scaffold_apps_dir: "/opt/apps"

# Default resource limits (overridable per app)
app_scaffold_default_memory_limit: "512M"
app_scaffold_default_cpu_limit: "0.5"

# Docker networks for app-prod server
app_scaffold_frontend_network: "app_frontend"
app_scaffold_backend_network: "app_backend"
app_scaffold_frontend_subnet: "172.21.1.0/24"
app_scaffold_backend_subnet: "172.21.2.0/24"
```

- [ ] **Step 2: Create tasks**

```yaml
# roles/app-scaffold/tasks/main.yml
---
# app-scaffold — tasks
# Prepares Hetzner server for App Factory deployments

- name: Create Docker config directory
  ansible.builtin.file:
    path: "{{ app_scaffold_docker_config_dir }}"
    state: directory
    owner: root
    group: root
    mode: "0700"
  become: true
  tags: [app-scaffold]

- name: Deploy GHCR pull credentials
  ansible.builtin.template:
    src: docker-config.json.j2
    dest: "{{ app_scaffold_docker_config_dir }}/config.json"
    owner: root
    group: root
    mode: "0600"
  become: true
  tags: [app-scaffold]

- name: Create apps base directory
  ansible.builtin.file:
    path: "{{ app_scaffold_apps_dir }}"
    state: directory
    owner: root
    group: root
    mode: "0755"
  become: true
  tags: [app-scaffold]

- name: Create app frontend Docker network
  community.docker.docker_network:
    name: "{{ app_scaffold_frontend_network }}"
    driver: bridge
    ipam_config:
      - subnet: "{{ app_scaffold_frontend_subnet }}"
  become: true
  tags: [app-scaffold]

- name: Create app backend Docker network
  community.docker.docker_network:
    name: "{{ app_scaffold_backend_network }}"
    driver: bridge
    internal: true
    ipam_config:
      - subnet: "{{ app_scaffold_backend_subnet }}"
  become: true
  tags: [app-scaffold]
```

- [ ] **Step 3: Create handlers**

```yaml
# roles/app-scaffold/handlers/main.yml
---
# app-scaffold — handlers (generic app restart)
# Per-app roles define their own handlers. This is a fallback.

- name: Restart app container
  ansible.builtin.debug:
    msg: "app-scaffold handler: restart delegated to per-app role handler"
  listen: Restart app stack
```

- [ ] **Step 4: Create Docker config template**

```json
{# {{ ansible_managed }} #}
{
  "auths": {
    "ghcr.io": {
      "auth": "{{ (app_scaffold_ghcr_user + ':' + app_scaffold_ghcr_token) | b64encode }}"
    }
  }
}
```

- [ ] **Step 5: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/app-scaffold/`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add roles/app-scaffold/
git commit -m "feat(app-factory): add app-scaffold role — GHCR auth + Docker networks"
```

---

## Task 5: App-Prod Playbook

Create the `playbooks/app-prod.yml` playbook for deploying apps to Hetzner.

**Files:**
- Create: `playbooks/app-prod.yml`

- [ ] **Step 1: Create playbook**

```yaml
# playbooks/app-prod.yml — Deploy apps to Hetzner (app-prod server)
#
# Usage:
#   ansible-playbook playbooks/app-prod.yml -e "target_env=app_prod"
#   ansible-playbook playbooks/app-prod.yml -e "target_env=app_prod" --tags "my-app"

---
- name: Deploy App Factory Apps
  hosts: "{{ target_env | default('app_prod') }}"
  gather_facts: true

  pre_tasks:
    - name: Display deployment info
      ansible.builtin.debug:
        msg: |
          ========================================
          App Factory Deploy
          Environment: {{ target_env | default('app_prod') }}
          Target: {{ inventory_hostname }}
          Date: {{ ansible_facts['date_time']['iso8601'] }}
          ========================================
      tags: [always]

  roles:
    # Phase 1 — Base infrastructure (run once, then skip via tags)
    - role: common
      tags: [common, phase1]
    - role: docker
      tags: [docker, phase1]
    - role: app-scaffold
      tags: [app-scaffold, phase1]

    # Per-app roles are added below as apps are created.
    # Deploy a specific app with: --tags <app-name>
    # Example:
    #   - role: my-app
    #     tags: [my-app, phase3]
```

- [ ] **Step 2: Lint**

Run: `source .venv/bin/activate && ansible-lint playbooks/app-prod.yml`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add playbooks/app-prod.yml
git commit -m "feat(app-factory): add app-prod.yml playbook for Hetzner deploys"
```

---

## Task 6: Deploy GitHub Actions Workflow

Create `.github/workflows/deploy-app.yml` based on the existing `deploy-prod.yml` pattern, adapted for Hetzner app-prod.

**Files:**
- Create: `.github/workflows/deploy-app.yml`

- [ ] **Step 1: Create workflow**

```yaml
# .github/workflows/deploy-app.yml — Deploy app to Hetzner (manual)
---
name: Deploy App (Hetzner)

on:
  workflow_dispatch:
    inputs:
      confirm:
        description: 'Type "deploy-app" to confirm'
        required: true
        type: string
      app_name:
        description: 'App name (Ansible role tag)'
        required: true
        type: string
      image_tag:
        description: 'Docker image SHA tag to deploy'
        required: true
        type: string
      plane_project_id:
        description: 'Plane project ID (for n8n callback)'
        required: false
        type: string
        default: ''

env:
  ANSIBLE_FORCE_COLOR: "1"

jobs:
  validate:
    name: Validate Confirmation
    runs-on: ubuntu-latest
    steps:
      - name: Check confirmation
        run: |
          if [ "${{ github.event.inputs.confirm }}" != "deploy-app" ]; then
            echo "ERROR: You must type 'deploy-app' to confirm"
            exit 1
          fi
          echo "Confirmation validated for app: ${{ github.event.inputs.app_name }}"

  lint:
    name: Lint
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install ansible ansible-lint yamllint
      - run: ansible-galaxy install -r requirements.yml
      - name: Create dummy vault password (lint only)
        run: echo "dummy" > .vault_password
      - run: ansible-lint playbooks/app-prod.yml

  deploy:
    name: Deploy to Hetzner
    needs: lint
    runs-on: ubuntu-latest
    environment: app-prod
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install ansible jmespath
          ansible-galaxy install -r requirements.yml

      - name: Configure SSH key
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.APP_PROD_SSH_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -p ${{ secrets.APP_PROD_SSH_PORT || 22 }} \
            -H "${{ secrets.APP_PROD_SERVER_IP }}" >> ~/.ssh/known_hosts 2>/dev/null

      - name: Create vault password file
        run: |
          printf '%s' "${{ secrets.ANSIBLE_VAULT_PASSWORD }}" > .vault_password
          chmod 600 .vault_password

      - name: Deploy app
        run: |
          ansible-playbook playbooks/app-prod.yml \
            -e "target_env=app_prod" \
            --tags "${{ github.event.inputs.app_name }}" \
            --diff

  smoke-tests:
    name: Smoke Tests
    needs: deploy
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure SSH key
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.APP_PROD_SSH_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -p ${{ secrets.APP_PROD_SSH_PORT || 22 }} \
            -H "${{ secrets.APP_PROD_SERVER_IP }}" >> ~/.ssh/known_hosts 2>/dev/null

      - name: Wait for services to stabilize
        run: sleep 15

      - name: Check container is running
        run: |
          ssh -p ${{ secrets.APP_PROD_SSH_PORT || 22 }} root@${{ secrets.APP_PROD_SERVER_IP }} \
            "docker ps --filter 'name=${{ github.event.inputs.app_name }}' --format 'table {{ '{{' }}.Names{{ '}}' }}\t{{ '{{' }}.Status{{ '}}' }}'"

      - name: Notify n8n (deploy complete)
        if: always()
        run: |
          STATUS="pass"
          if [ "${{ job.status }}" != "success" ]; then
            STATUS="fail"
          fi
          curl -sf -X POST "${{ secrets.N8N_DEPLOY_WEBHOOK }}" \
            -H "Content-Type: application/json" \
            -H "X-AF-Secret: ${{ secrets.AF_WEBHOOK_SECRET }}" \
            -d "{\"repo\":\"${{ github.event.inputs.app_name }}\",\"image_tag\":\"${{ github.event.inputs.image_tag }}\",\"event\":\"deploy_complete\",\"smoke_result\":\"${STATUS}\",\"plane_project_id\":\"${{ github.event.inputs.plane_project_id }}\"}" || true
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-app.yml'))"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-app.yml
git commit -m "feat(app-factory): add deploy-app.yml GitHub Actions workflow"
```

---

## Task 7: Scaffold Templates

Create the templates that `af-intake` pushes to new repos: CI workflow, CLAUDE.md, Dockerfile.

**Files:**
- Create: `roles/app-scaffold/templates/scaffold-templates/ci.yml.j2`
- Create: `roles/app-scaffold/templates/scaffold-templates/CLAUDE.md.j2`
- Create: `roles/app-scaffold/templates/scaffold-templates/Dockerfile.j2`

- [ ] **Step 1: Create CI template**

This is the template n8n's `af-intake` uses to scaffold `.github/workflows/ci.yml` in new repos.

```yaml
# roles/app-scaffold/templates/scaffold-templates/ci.yml.j2
# {{ ansible_managed }}
# CI pipeline for {{ app_name }} — Lint, Test, Build, Push to GHCR
---
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup
        # TODO: Stack-specific setup (Node, Python, Go, etc.)
        run: echo "Setup placeholder — replace with stack-specific steps"
      - name: Lint
        run: echo "Lint placeholder — replace with stack-specific linter"
      - name: Test
        run: echo "Test placeholder — replace with stack-specific test runner"

  build-push:
    needs: lint-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Login GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: {% raw %}${{ github.actor }}{% endraw %}
          password: {% raw %}${{ secrets.GITHUB_TOKEN }}{% endraw %}
      - name: Build & Push
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/mobutoo/{% raw %}${{ github.event.repository.name }}:${{ github.sha }}{% endraw %}
      - name: Notify n8n
        run: |
          curl -sf -X POST "{% raw %}${{ secrets.N8N_DEPLOY_WEBHOOK }}{% endraw %}" \
            -H "Content-Type: application/json" \
            -H "X-AF-Secret: {% raw %}${{ secrets.AF_WEBHOOK_SECRET }}{% endraw %}" \
            -d '{"repo":"{% raw %}${{ github.event.repository.name }}{% endraw %}","image_tag":"{% raw %}${{ github.sha }}{% endraw %}","event":"image_pushed"}'
```

- [ ] **Step 2: Create CLAUDE.md template**

```markdown
# roles/app-scaffold/templates/scaffold-templates/CLAUDE.md.j2
{# {{ ansible_managed }} #}
# CLAUDE.md — {{ app_name }}

## Project

{{ app_description }}

**Stack:** {{ app_stack }}
**Deploy target:** Hetzner ({{ app_env }})

## Conventions

- All commits MUST include `[PLANE-<id>]` suffix (8 first chars of Plane work item UUID)
- Commit format: `<type>(<scope>): <description> [PLANE-<id>]`
- Types: feat, fix, test, chore, docs, deploy
- Docker images: tagged with full git SHA, pushed to GHCR
- No `:latest` tags
- TDD: write failing test first, then implement

## Deploy

Images auto-push to GHCR on merge to main.
Deploy is triggered manually via `deploy-app` GitHub Actions workflow in VPAI repo.

## Testing

```bash
# Run tests
# TODO: replace with stack-specific commands
npm test      # or pytest, go test, etc.
```
```

- [ ] **Step 3: Create Dockerfile template**

```dockerfile
# roles/app-scaffold/templates/scaffold-templates/Dockerfile.j2
{# {{ ansible_managed }} #}
# Multi-stage Dockerfile for {{ app_name }}
# Stack: {{ app_stack }}

# --- Build stage ---
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --production=false
COPY . .
RUN npm run build

# --- Production stage ---
FROM node:22-alpine AS production
WORKDIR /app
RUN addgroup -g 1001 -S appuser && adduser -S appuser -u 1001
COPY --from=builder --chown=appuser:appuser /app/dist ./dist
COPY --from=builder --chown=appuser:appuser /app/node_modules ./node_modules
COPY --from=builder --chown=appuser:appuser /app/package.json ./
USER appuser
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD node -e "const http=require('http');const r=http.get('http://localhost:3000/health',{timeout:3000},res=>{process.exit(res.statusCode<400?0:1)});r.on('error',()=>process.exit(1))"
CMD ["node", "dist/index.js"]
```

> Note: This is a Node.js default. `af-intake` should swap the template based on `stack` input (next.js, python, go, etc.). The n8n workflow handles template selection at runtime.

- [ ] **Step 4: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/app-scaffold/`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add roles/app-scaffold/templates/scaffold-templates/
git commit -m "feat(app-factory): add scaffold templates — CI, CLAUDE.md, Dockerfile"
```

---

## Task 8: Vault Secrets

Add the required secrets to Ansible Vault.

**Files:**
- Modify: `inventory/group_vars/all/secrets.yml` (encrypted)

- [ ] **Step 1: Add secrets to vault**

Run: `ansible-vault edit inventory/group_vars/all/secrets.yml`

Add these entries:

```yaml
# === APP FACTORY ===
vault_ghcr_pull_token: "ghp_PLACEHOLDER"  # Generate: GitHub → Settings → PAT → read:packages
vault_af_webhook_secret: "GENERATE_RANDOM_SECRET"  # openssl rand -hex 32
```

> **IMPORTANT**: The user must generate the actual GitHub PAT (`read:packages` scope) and replace `ghp_PLACEHOLDER`. The webhook secret can be generated with `openssl rand -hex 32`.

- [ ] **Step 2: Verify vault decrypts**

Run: `ansible-vault view inventory/group_vars/all/secrets.yml | grep vault_ghcr_pull_token`
Expected: shows the placeholder value

- [ ] **Step 3: Commit**

```bash
git add inventory/group_vars/all/secrets.yml
git commit -m "chore(app-factory): add GHCR + webhook secrets to vault (placeholders)"
```

---

## Task 9: Dry Run Validation

Validate the entire implementation with lint and dry-run.

**Files:** None (validation only)

- [ ] **Step 1: Full lint**

Run: `source .venv/bin/activate && ansible-lint playbooks/site.yml playbooks/app-prod.yml`
Expected: PASS

- [ ] **Step 2: Dry run provisioning role**

Run: `source .venv/bin/activate && ansible-playbook playbooks/site.yml --tags app-factory-provision --check --diff -e "target_env=prod"`
Expected: Shows planned changes without executing

- [ ] **Step 3: Dry run app-prod playbook**

Run: `source .venv/bin/activate && ansible-playbook playbooks/app-prod.yml --check --diff -e "target_env=app_prod"`
Expected: Shows planned changes (may warn about unreachable host if app-prod not provisioned yet)

- [ ] **Step 4: Verify GitHub Actions YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-app.yml')); print('OK')"`
Expected: `OK`

---

## What's NOT in this plan (deferred to runtime)

These components are built when the App Factory is **used for the first time**, not now:

1. **n8n workflows (af-intake, af-ci-hook, af-phase-complete, af-rex-indexer)** — Built via n8n UI on Sese-AI using the spec as reference. The webhook URLs are configured in n8n and shared as GitHub secrets.
2. **GSD hook** — Configured in `.claude/settings.json` when the first project starts. The hook calls the `af-phase-complete` webhook at each GSD phase completion.
3. **Hetzner server provisioning** — The `app-prod` server must exist before deploys. Use `provision-hetzner.yml` to create the CX22 VM.
4. **GitHub secrets** — `APP_PROD_SSH_KEY`, `APP_PROD_SERVER_IP`, `N8N_DEPLOY_WEBHOOK`, `AF_WEBHOOK_SECRET` must be added to the VPAI repo's GitHub settings.
