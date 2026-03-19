# Sure → Firefly III + Seko-Finance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the Sure service (crash-looping Maybe Finance fork) and replace it with Firefly III (accounting engine) + Seko-Finance dashboard (Next.js cockpit), deployed on Sese-AI via Ansible.

**Architecture:** Two new containers on Sese-AI: `firefly-iii` (Laravel, port 8080, `lola` subdomain) and `seko-finance` (Next.js, port 3000, `nzimbu` subdomain). Both VPN-only, sharing PostgreSQL and Redis. Dashboard proxies Firefly III API and connects to LiteLLM for chat.

**Tech Stack:** Ansible 2.16+, Docker Compose V2, Caddy (reverse proxy), PostgreSQL 18.1, Redis 8.0, Firefly III v6.5.3, Seko-Finance (GHCR pre-built image)

**Design doc:** `docs/plans/2026-03-04-sure-to-firefly-design.md`

---

## Task 1: Remove Sure from inventory variables

**Files:**
- Modify: `inventory/group_vars/all/main.yml:130-133` (secrets) and `:222` (subdomain)
- Modify: `inventory/group_vars/all/versions.yml:45-48` (image)
- Modify: `inventory/group_vars/all/docker.yml:90-96` (resource limits)

**Step 1: Remove Sure secrets from main.yml**

In `inventory/group_vars/all/main.yml`, replace lines 130-133:

```yaml
# Sure (personal finance)
sure_secret_key_base: "{{ vault_sure_secret_key_base }}"
sure_db_password: "{{ vault_sure_db_password | default(postgresql_password) }}"
sure_api_key: "{{ vault_sure_api_key | default('') }}"
```

With:

```yaml
# Firefly III (personal finance engine)
firefly_app_key: "{{ vault_firefly_app_key }}"

# Seko-Finance Dashboard (financial cockpit — connects to Firefly III + LiteLLM)
seko_finance_firefly_pat: "{{ vault_firefly_pat | default('') }}"
```

**Step 2: Replace Sure subdomain with new subdomains**

In `inventory/group_vars/all/main.yml`, replace line 222:

```yaml
# Sure (personal finance)
sure_subdomain: "nzimbu"
```

With:

```yaml
# Firefly III + Seko-Finance (personal finance)
firefly_subdomain: "lola"
seko_finance_subdomain: "nzimbu"
```

**Step 3: Replace Sure image in versions.yml**

In `inventory/group_vars/all/versions.yml`, replace lines 45-48:

```yaml
# --- Sure (personal finance — Maybe Finance fork) ---
# Multi-arch: amd64 + arm64 confirmé sur GHCR
# TODO: Pinner sur SHA digest après premier deploy validé
sure_image: "ghcr.io/we-promise/sure:nightly"
```

With:

```yaml
# --- Firefly III (personal finance engine) ---
firefly_image: "fireflyiii/core:version-6.5.3"

# --- Seko-Finance Dashboard (Next.js financial cockpit) ---
# TODO: Pinner sur SHA digest après premier deploy validé
seko_finance_image: "ghcr.io/mobutoo/seko-finance:latest"
```

**Step 4: Replace Sure resource limits in docker.yml**

In `inventory/group_vars/all/docker.yml`, replace lines 90-96:

```yaml
# Sure (web Rails + worker Sidekiq — personal finance)
sure_web_memory_limit: "{{ '768M' if target_env == 'prod' else '384M' }}"
sure_web_memory_reservation: "192M"
sure_web_cpu_limit: "1.0"
sure_worker_memory_limit: "{{ '384M' if target_env == 'prod' else '256M' }}"
sure_worker_memory_reservation: "128M"
sure_worker_cpu_limit: "0.5"
```

With:

```yaml
# Firefly III (Laravel — personal finance engine)
firefly_memory_limit: "{{ '512M' if target_env == 'prod' else '256M' }}"
firefly_memory_reservation: "128M"
firefly_cpu_limit: "1.0"

# Seko-Finance Dashboard (Next.js cockpit)
seko_finance_memory_limit: "{{ '384M' if target_env == 'prod' else '256M' }}"
seko_finance_memory_reservation: "128M"
seko_finance_cpu_limit: "0.5"
```

**Step 5: Run lint to verify YAML syntax**

Run: `source .venv/bin/activate && yamllint inventory/group_vars/all/main.yml inventory/group_vars/all/versions.yml inventory/group_vars/all/docker.yml`
Expected: 0 errors

**Step 6: Commit**

```bash
git add inventory/group_vars/all/main.yml inventory/group_vars/all/versions.yml inventory/group_vars/all/docker.yml
git commit -m "refactor(inventory): replace Sure variables with Firefly III + Seko-Finance"
```

---

## Task 2: Update Vault secrets

**Files:**
- Modify: `inventory/group_vars/all/secrets.yml` (Ansible Vault encrypted)

**Step 1: Generate Firefly APP_KEY**

Run: `echo "base64:$(openssl rand -base64 32)"`

Save the output — this becomes `vault_firefly_app_key`.

**Step 2: Edit the vault**

Run: `source .venv/bin/activate && ansible-vault edit inventory/group_vars/all/secrets.yml`

Remove:

```yaml
vault_sure_secret_key_base: "..."
vault_sure_db_password: "..."
vault_sure_api_key: "..."
```

Add:

```yaml
# Firefly III
vault_firefly_app_key: "base64:<the-value-from-step-1>"
# NOTE: vault_firefly_pat will be added after first Firefly III boot (PAT created in UI)
vault_firefly_pat: ""
```

**Step 3: Commit**

```bash
git add inventory/group_vars/all/secrets.yml
git commit -m "vault: replace Sure secrets with Firefly III APP_KEY"
```

---

## Task 3: Update PostgreSQL defaults

**Files:**
- Modify: `roles/postgresql/defaults/main.yml:26-30`

**Step 1: Replace Sure database with Firefly database**

In `roles/postgresql/defaults/main.yml`, replace lines 26-30:

```yaml
  - name: sure_production
    user: sure
    extensions:
      - uuid-ossp
      - pgcrypto
```

With:

```yaml
  - name: firefly
    user: firefly
    extensions: []
```

**Step 2: Run lint**

Run: `source .venv/bin/activate && yamllint roles/postgresql/defaults/main.yml`
Expected: 0 errors

**Step 3: Commit**

```bash
git add roles/postgresql/defaults/main.yml
git commit -m "refactor(postgresql): replace sure_production DB with firefly"
```

---

## Task 4: Delete the Sure role

**Files:**
- Delete: `roles/sure/` (entire directory — 5 files)

**Step 1: Remove the role directory**

Run: `rm -rf roles/sure/`

**Step 2: Remove Sure from playbook**

In `playbooks/site.yml`, remove lines 83-84:

```yaml
    - role: sure
      tags: [sure, phase3]
```

**Step 3: Commit**

```bash
git rm -r roles/sure/
git add playbooks/site.yml
git commit -m "chore: remove Sure role (replaced by Firefly III + Seko-Finance)"
```

---

## Task 5: Create the Firefly III role

**Files:**
- Create: `roles/firefly/defaults/main.yml`
- Create: `roles/firefly/tasks/main.yml`
- Create: `roles/firefly/templates/firefly.env.j2`
- Create: `roles/firefly/handlers/main.yml`
- Create: `roles/firefly/meta/main.yml`

**Step 1: Create defaults**

Write `roles/firefly/defaults/main.yml`:

```yaml
---
# firefly — defaults
# Firefly III personal finance engine (Laravel).
# Runs as Docker container on Sese-AI, shares PostgreSQL and Redis.

firefly_config_dir: "/opt/{{ project_name }}/configs/firefly"
firefly_data_dir: "/opt/{{ project_name }}/data/firefly"

# Internal web port (exposed via Caddy on lola.<domain>)
firefly_web_port: 8080

# PostgreSQL connection (shared instance)
firefly_db_name: "firefly"
firefly_db_user: "firefly"

# Redis DB numbers (shared Redis — avoid collision with db0=default, db1=former-sure)
firefly_redis_db: 2
firefly_redis_cache_db: 3

# Subdomain (VPN-only, served by Caddy)
# Overridden by firefly_subdomain in inventory/group_vars/all/main.yml
firefly_subdomain: "lola"
```

**Step 2: Create tasks**

Write `roles/firefly/tasks/main.yml`:

```yaml
---
# firefly — tasks
# Firefly III personal finance engine (Laravel in Docker)

- name: Create Firefly III config directory
  ansible.builtin.file:
    path: "{{ firefly_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Create Firefly III data directory
  ansible.builtin.file:
    path: "{{ firefly_data_dir }}/upload"
    state: directory
    owner: "www-data"
    group: "www-data"
    mode: "0755"
  become: true

- name: Deploy Firefly III environment file
  ansible.builtin.template:
    src: firefly.env.j2
    dest: "{{ firefly_config_dir }}/firefly.env"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0600"
  become: true
  notify: Restart firefly stack
```

**Step 3: Create env template**

Write `roles/firefly/templates/firefly.env.j2`:

```
# {{ ansible_managed }}
# Firefly III environment configuration

# Laravel
APP_ENV=production
APP_KEY={{ firefly_app_key }}
APP_URL=https://{{ firefly_subdomain }}.{{ domain_name }}
TRUSTED_PROXIES=**
LOG_CHANNEL=stdout
APP_LOG_LEVEL=warning

# Database (PostgreSQL — shared instance)
DB_CONNECTION=pgsql
DB_HOST=postgresql
DB_PORT=5432
DB_DATABASE={{ firefly_db_name }}
DB_USERNAME={{ firefly_db_user }}
DB_PASSWORD={{ postgresql_password }}

# Cache & Sessions (Redis — shared instance)
CACHE_DRIVER=redis
SESSION_DRIVER=redis
REDIS_SCHEME=tcp
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD={{ redis_password }}
REDIS_DB={{ firefly_redis_db }}
REDIS_CACHE_DB={{ firefly_redis_cache_db }}

# Locale
DEFAULT_LANGUAGE=fr_FR
DEFAULT_LOCALE=fr_FR
TZ={{ timezone }}

# Security
COOKIE_SECURE=true
COOKIE_SAMESITE=strict
DISABLE_FRAME_HEADER=false
```

**Step 4: Create handlers**

Write `roles/firefly/handlers/main.yml`:

```yaml
---
# firefly — handlers
# Pattern: grep-guard before restart — checks that firefly-iii service is declared
# in docker-compose.yml (i.e. docker-stack Phase B has been deployed).
# Uses state: present + recreate: always to reload env_file (REX: restart ≠ recreate).

- name: Check firefly service is in compose file
  ansible.builtin.command:
    cmd: grep -q "firefly-iii" /opt/{{ project_name }}/docker-compose.yml
  register: _firefly_in_compose
  failed_when: false
  changed_when: false
  listen: Restart firefly stack

- name: Restart firefly containers
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - firefly-iii
    state: present
    recreate: always
  become: true
  when:
    - not ansible_check_mode
    - _firefly_in_compose.rc | default(1) == 0
    - not (common_molecule_mode | default(false))
  listen: Restart firefly stack
```

**Step 5: Create meta**

Write `roles/firefly/meta/main.yml`:

```yaml
---
# firefly — role metadata

galaxy_info:
  role_name: firefly
  author: Mobutoo
  description: Deploy Firefly III personal finance engine
  license: AGPL-3.0
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm
        - trixie

dependencies: []
```

**Step 6: Run lint on the new role**

Run: `source .venv/bin/activate && ansible-lint roles/firefly/`
Expected: 0 errors (or only warnings about missing molecule tests)

**Step 7: Commit**

```bash
git add roles/firefly/
git commit -m "feat(firefly): add Firefly III role (personal finance engine)"
```

---

## Task 6: Create the Seko-Finance role

**Files:**
- Create: `roles/seko-finance/defaults/main.yml`
- Create: `roles/seko-finance/tasks/main.yml`
- Create: `roles/seko-finance/templates/seko-finance.env.j2`
- Create: `roles/seko-finance/handlers/main.yml`
- Create: `roles/seko-finance/meta/main.yml`

**Step 1: Create defaults**

Write `roles/seko-finance/defaults/main.yml`:

```yaml
---
# seko-finance — defaults
# Seko-Finance Dashboard: Next.js financial cockpit connected to Firefly III + LiteLLM.
# Runs as Docker container (pre-built image from GHCR).

seko_finance_config_dir: "/opt/{{ project_name }}/configs/seko-finance"

# Internal web port (exposed via Caddy on nzimbu.<domain>)
seko_finance_port: 3000

# LLM model for chat feature (via LiteLLM proxy)
seko_finance_llm_model: "deepseek-v3-free"

# Subdomain (VPN-only, served by Caddy)
# Overridden by seko_finance_subdomain in inventory/group_vars/all/main.yml
seko_finance_subdomain: "nzimbu"
```

**Step 2: Create tasks**

Write `roles/seko-finance/tasks/main.yml`:

```yaml
---
# seko-finance — tasks
# Seko-Finance Dashboard (Next.js — pre-built Docker image from GHCR)

- name: Create Seko-Finance config directory
  ansible.builtin.file:
    path: "{{ seko_finance_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Deploy Seko-Finance environment file
  ansible.builtin.template:
    src: seko-finance.env.j2
    dest: "{{ seko_finance_config_dir }}/seko-finance.env"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0600"
  become: true
  notify: Restart seko-finance stack
```

**Step 3: Create env template**

Write `roles/seko-finance/templates/seko-finance.env.j2`:

```
# {{ ansible_managed }}
# Seko-Finance Dashboard environment configuration

NODE_ENV=production

# Firefly III API (internal Docker network)
FIREFLY_URL=http://firefly-iii:{{ firefly_web_port | default(8080) }}
FIREFLY_PAT={{ seko_finance_firefly_pat }}

# LiteLLM proxy (internal Docker network — chat IA feature)
LITELLM_URL=http://litellm:4000
LITELLM_KEY={{ litellm_master_key }}
LLM_MODEL={{ seko_finance_llm_model }}

# App
NEXT_PUBLIC_APP_NAME=Seko-Finance
NEXT_PUBLIC_CURRENCY=EUR

# Timezone
TZ={{ timezone }}
```

**Step 4: Create handlers**

Write `roles/seko-finance/handlers/main.yml`:

```yaml
---
# seko-finance — handlers
# Pattern: grep-guard + state: present + recreate: always (env_file reload).

- name: Check seko-finance service is in compose file
  ansible.builtin.command:
    cmd: grep -q "seko-finance" /opt/{{ project_name }}/docker-compose.yml
  register: _seko_finance_in_compose
  failed_when: false
  changed_when: false
  listen: Restart seko-finance stack

- name: Restart seko-finance container
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - seko-finance
    state: present
    recreate: always
  become: true
  when:
    - not ansible_check_mode
    - _seko_finance_in_compose.rc | default(1) == 0
    - not (common_molecule_mode | default(false))
  listen: Restart seko-finance stack
```

**Step 5: Create meta**

Write `roles/seko-finance/meta/main.yml`:

```yaml
---
# seko-finance — role metadata

galaxy_info:
  role_name: seko-finance
  author: Mobutoo
  description: Deploy Seko-Finance Dashboard (Next.js financial cockpit)
  license: AGPL-3.0
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm
        - trixie

dependencies: []
```

**Step 6: Run lint**

Run: `source .venv/bin/activate && ansible-lint roles/seko-finance/`
Expected: 0 errors

**Step 7: Commit**

```bash
git add roles/seko-finance/
git commit -m "feat(seko-finance): add Seko-Finance Dashboard role (Next.js cockpit)"
```

---

## Task 7: Register new roles in playbook

**Files:**
- Modify: `playbooks/site.yml:83-84` (already deleted Sure in Task 4)

**Step 1: Add Firefly III and Seko-Finance roles**

In `playbooks/site.yml`, where Sure was (after the `palais` role, line ~82), add:

```yaml
    - role: firefly
      tags: [firefly, phase3]
    - role: seko-finance
      tags: [seko-finance, phase3]
```

The Phase 3 block should now read:

```yaml
    # Phase 3 — Applications
    - role: n8n
      tags: [n8n, phase3]
    - role: litellm
      tags: [litellm, phase3]
    - role: nocodb
      tags: [nocodb, phase3]
    - role: plane
      tags: [plane, phase3]
    - role: openclaw
      tags: [openclaw, phase3]
    - role: palais
      tags: [palais, phase3]
    - role: firefly
      tags: [firefly, phase3]
    - role: seko-finance
      tags: [seko-finance, phase3]
```

**Step 2: Run lint**

Run: `source .venv/bin/activate && yamllint playbooks/site.yml`
Expected: 0 errors

**Step 3: Commit**

```bash
git add playbooks/site.yml
git commit -m "feat(site): register firefly + seko-finance roles in Phase 3"
```

---

## Task 8: Update Docker Compose template (Phase B)

**Files:**
- Modify: `roles/docker-stack/templates/docker-compose.yml.j2:144-209`

**Step 1: Replace Sure containers with Firefly III + Seko-Finance**

In `roles/docker-stack/templates/docker-compose.yml.j2`, replace lines 144-209 (the `# === PERSONAL FINANCE ===` section with `sure-web` and `sure-worker`):

```yaml
  # === PERSONAL FINANCE ===
  sure-web:
    ...
  sure-worker:
    ...
```

With:

```yaml
  # === PERSONAL FINANCE ===
  firefly-iii:
    image: {{ firefly_image }}
    container_name: {{ project_name }}_firefly
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - DAC_OVERRIDE
      - FOWNER
      - SETUID
      - SETGID
    env_file:
      - /opt/{{ project_name }}/configs/firefly/firefly.env
    volumes:
      - /opt/{{ project_name }}/data/firefly/upload:/var/www/html/storage/upload
    networks:
      - backend
      - frontend
    deploy:
      resources:
        limits:
          memory: {{ firefly_memory_limit }}
          cpus: "{{ firefly_cpu_limit }}"
        reservations:
          memory: {{ firefly_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://127.0.0.1:8080/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  seko-finance:
    image: {{ seko_finance_image }}
    container_name: {{ project_name }}_seko_finance
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    env_file:
      - /opt/{{ project_name }}/configs/seko-finance/seko-finance.env
    networks:
      - backend
      - frontend
      - egress
    deploy:
      resources:
        limits:
          memory: {{ seko_finance_memory_limit }}
          cpus: "{{ seko_finance_cpu_limit }}"
        reservations:
          memory: {{ seko_finance_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:3000/api/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

**Step 2: Run lint**

Run: `source .venv/bin/activate && yamllint roles/docker-stack/templates/docker-compose.yml.j2`
Expected: 0 errors (ignore Jinja2 template warnings)

**Step 3: Commit**

```bash
git add roles/docker-stack/templates/docker-compose.yml.j2
git commit -m "feat(docker-stack): replace Sure containers with Firefly III + Seko-Finance"
```

---

## Task 9: Update Caddy configuration

**Files:**
- Modify: `roles/caddy/defaults/main.yml:14`
- Modify: `roles/caddy/templates/Caddyfile.j2:249-264`

**Step 1: Replace Caddy domain variable**

In `roles/caddy/defaults/main.yml`, replace line 14:

```yaml
caddy_sure_domain: "{{ sure_subdomain | default('nzimbu') }}.{{ domain_name }}"
```

With:

```yaml
caddy_firefly_domain: "{{ firefly_subdomain | default('lola') }}.{{ domain_name }}"
caddy_seko_finance_domain: "{{ seko_finance_subdomain | default('nzimbu') }}.{{ domain_name }}"
```

**Step 2: Replace Caddyfile Sure block**

In `roles/caddy/templates/Caddyfile.j2`, replace lines 249-264:

```caddyfile
# === Sure (personal finance) — dedicated subdomain (nzimbu) ===
{% if sure_subdomain | default('') | length > 0 %}
{{ caddy_sure_domain }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy sure-web:{{ sure_web_port | default(3000) }}

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }
}
{% endif %}
```

With:

```caddyfile
# === Firefly III (personal finance engine) — lola.<domain> ===
{% if firefly_subdomain | default('') | length > 0 %}
{{ caddy_firefly_domain }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy firefly-iii:{{ firefly_web_port | default(8080) }}

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }
}
{% endif %}

# === Seko-Finance Dashboard (financial cockpit) — nzimbu.<domain> ===
{% if seko_finance_subdomain | default('') | length > 0 %}
{{ caddy_seko_finance_domain }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy seko-finance:{{ seko_finance_port | default(3000) }}

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }
}
{% endif %}
```

**Step 3: Run lint**

Run: `source .venv/bin/activate && yamllint roles/caddy/defaults/main.yml`
Expected: 0 errors

**Step 4: Commit**

```bash
git add roles/caddy/defaults/main.yml roles/caddy/templates/Caddyfile.j2
git commit -m "feat(caddy): replace Sure block with Firefly III + Seko-Finance reverse proxy"
```

---

## Task 10: Update smoke tests

**Files:**
- Modify: `roles/smoke-tests/templates/smoke-test.sh.j2` (lines 53-54, 167-171, 200-203, 218-220)

**Step 1: Replace Sure DNS resolve**

In `smoke-test.sh.j2`, replace lines 53-55:

```bash
{% if sure_subdomain | default('') | length > 0 %}
  CURL_VPN_OPTS="${CURL_VPN_OPTS} --resolve {{ sure_subdomain }}.{{ domain_name }}:443:${TAILSCALE_IP}"
{% endif %}
```

With:

```bash
{% if firefly_subdomain | default('') | length > 0 %}
  CURL_VPN_OPTS="${CURL_VPN_OPTS} --resolve {{ firefly_subdomain }}.{{ domain_name }}:443:${TAILSCALE_IP}"
{% endif %}
{% if seko_finance_subdomain | default('') | length > 0 %}
  CURL_VPN_OPTS="${CURL_VPN_OPTS} --resolve {{ seko_finance_subdomain }}.{{ domain_name }}:443:${TAILSCALE_IP}"
{% endif %}
```

**Step 2: Replace Sure health check URL**

Replace lines 167-171:

```bash
{% if sure_subdomain | default('') | length > 0 %}
# shellcheck disable=SC2086
SURE_URL="https://{{ sure_subdomain }}.{{ domain_name }}"
check_http "Sure health" "${SURE_URL}/" "200"
{% endif %}
```

With:

```bash
{% if firefly_subdomain | default('') | length > 0 %}
# shellcheck disable=SC2086
FIREFLY_URL="https://{{ firefly_subdomain }}.{{ domain_name }}"
check_http "Firefly III health" "${FIREFLY_URL}/health" "200"
{% endif %}
{% if seko_finance_subdomain | default('') | length > 0 %}
# shellcheck disable=SC2086
SEKO_FINANCE_URL="https://{{ seko_finance_subdomain }}.{{ domain_name }}"
check_http "Seko-Finance health" "${SEKO_FINANCE_URL}/api/health" "200"
{% endif %}
```

**Step 3: Replace Sure container checks**

Replace lines 200-203:

```bash
{% if sure_subdomain | default('') | length > 0 %}
check_container "Sure Web" "sure_web"
check_container "Sure Worker" "sure_worker"
{% endif %}
```

With:

```bash
{% if firefly_subdomain | default('') | length > 0 %}
check_container "Firefly III" "firefly"
{% endif %}
{% if seko_finance_subdomain | default('') | length > 0 %}
check_container "Seko-Finance" "seko_finance"
{% endif %}
```

**Step 4: Replace Sure healthcheck checks**

Replace lines 218-220:

```bash
{% if sure_subdomain | default('') | length > 0 %}
check_container_health "Sure Web" "sure_web"
{% endif %}
```

With:

```bash
{% if firefly_subdomain | default('') | length > 0 %}
check_container_health "Firefly III" "firefly"
{% endif %}
{% if seko_finance_subdomain | default('') | length > 0 %}
check_container_health "Seko-Finance" "seko_finance"
{% endif %}
```

**Step 5: Commit**

```bash
git add roles/smoke-tests/templates/smoke-test.sh.j2
git commit -m "feat(smoke-tests): replace Sure checks with Firefly III + Seko-Finance"
```

---

## Task 11: Update CI workflows

**Files:**
- Modify: `.github/workflows/integration.yml` (lines 168, 316-317, 383-384)

**Step 1: Update DNS validation loop**

In `integration.yml` line 168, replace:

```bash
          for sub in "" "mayi" "llm" "tala" "qd" "hq" "javisi" "palais" "work" "nzimbu"; do
```

With:

```bash
          for sub in "" "mayi" "llm" "tala" "qd" "hq" "javisi" "palais" "work" "nzimbu" "lola"; do
```

**Step 2: Update TLS pre-warm comment and loop**

Replace lines 316-317:

```bash
          # hq(nocodb), javisi(openclaw/admin), palais, nzimbu(sure), work(plane)
          for sub in "" "mayi" "llm" "tala" "qd" "hq" "javisi" "palais" "work" "nzimbu"; do
```

With:

```bash
          # hq(nocodb), javisi(openclaw/admin), palais, nzimbu(seko-finance), lola(firefly), work(plane)
          for sub in "" "mayi" "llm" "tala" "qd" "hq" "javisi" "palais" "work" "nzimbu" "lola"; do
```

**Step 3: Update /etc/hosts line and comment**

Replace lines 383-384:

```bash
          HOSTS_LINE="127.0.0.1 ${D} mayi.${D} llm.${D} tala.${D} qd.${D} hq.${D} javisi.${D} palais.${D} work.${D} nzimbu.${D}"
          # Wait for slow-starting containers (Sure has start_period: 120s)
```

With:

```bash
          HOSTS_LINE="127.0.0.1 ${D} mayi.${D} llm.${D} tala.${D} qd.${D} hq.${D} javisi.${D} palais.${D} work.${D} nzimbu.${D} lola.${D}"
          # Wait for slow-starting containers (Firefly III has start_period: 60s)
```

**Step 4: Commit**

```bash
git add .github/workflows/integration.yml
git commit -m "ci(integration): replace Sure with Firefly III + Seko-Finance subdomains"
```

---

## Task 12: Update Molecule converge files

**Files:**
- Modify: `roles/common/molecule/default/converge.yml:103`
- Modify: `roles/smoke-tests/molecule/default/converge.yml:103`

**Step 1: Update common converge.yml**

In `roles/common/molecule/default/converge.yml`, replace line 103:

```yaml
    sure_subdomain: nzimbu
```

With:

```yaml
    firefly_subdomain: lola
    seko_finance_subdomain: nzimbu
```

**Step 2: Update smoke-tests converge.yml**

In `roles/smoke-tests/molecule/default/converge.yml`, replace line 103:

```yaml
    sure_subdomain: nzimbu
```

With:

```yaml
    firefly_subdomain: lola
    seko_finance_subdomain: nzimbu
```

**Step 3: Commit**

```bash
git add roles/common/molecule/default/converge.yml roles/smoke-tests/molecule/default/converge.yml
git commit -m "test(molecule): replace sure_subdomain with firefly + seko_finance subdomains"
```

---

## Task 13: Create Molecule tests for new roles

**Files:**
- Create: `roles/firefly/molecule/default/molecule.yml`
- Create: `roles/firefly/molecule/default/converge.yml`
- Create: `roles/seko-finance/molecule/default/molecule.yml`
- Create: `roles/seko-finance/molecule/default/converge.yml`

**Step 1: Create Firefly molecule.yml**

Write `roles/firefly/molecule/default/molecule.yml`:

```yaml
---
dependency:
  name: galaxy
driver:
  name: docker
platforms:
  - name: instance
    image: geerlingguy/docker-debian12-ansible
    pre_build_image: true
    privileged: true
    override_command: false
provisioner:
  name: ansible
verifier:
  name: ansible
```

**Step 2: Create Firefly converge.yml**

Write `roles/firefly/molecule/default/converge.yml`:

```yaml
---
- name: Converge
  hosts: all
  become: true
  vars:
    common_molecule_mode: true
    project_name: javisi
    prod_user: molecule
    domain_name: test.local
    firefly_subdomain: lola
    firefly_app_key: "base64:dGVzdGtleWZvcm1vbGVjdWxldGVzdGluZzEyMzQ1Ng=="
    postgresql_password: "molecule_test_password"
    redis_password: "molecule_test_redis"
    timezone: "Europe/Paris"
  pre_tasks:
    - name: Create molecule test user (not present in geerlingguy Docker image)
      ansible.builtin.user:
        name: molecule
        state: present
        create_home: true
  roles:
    - role: firefly
```

**Step 3: Create Seko-Finance molecule.yml**

Write `roles/seko-finance/molecule/default/molecule.yml`:

```yaml
---
dependency:
  name: galaxy
driver:
  name: docker
platforms:
  - name: instance
    image: geerlingguy/docker-debian12-ansible
    pre_build_image: true
    privileged: true
    override_command: false
provisioner:
  name: ansible
verifier:
  name: ansible
```

**Step 4: Create Seko-Finance converge.yml**

Write `roles/seko-finance/molecule/default/converge.yml`:

```yaml
---
- name: Converge
  hosts: all
  become: true
  vars:
    common_molecule_mode: true
    project_name: javisi
    prod_user: molecule
    domain_name: test.local
    seko_finance_subdomain: nzimbu
    seko_finance_firefly_pat: "test_pat_token"
    firefly_web_port: 8080
    litellm_master_key: "sk-test-key"
    timezone: "Europe/Paris"
  pre_tasks:
    - name: Create molecule test user (not present in geerlingguy Docker image)
      ansible.builtin.user:
        name: molecule
        state: present
        create_home: true
  roles:
    - role: seko-finance
```

**Step 5: Run Molecule tests**

Run: `source .venv/bin/activate && cd roles/firefly && molecule test && cd ../seko-finance && molecule test`
Expected: Both converge successfully (directories created, templates deployed)

**Step 6: Commit**

```bash
git add roles/firefly/molecule/ roles/seko-finance/molecule/
git commit -m "test(molecule): add Firefly III + Seko-Finance molecule tests"
```

---

## Task 14: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/TROUBLESHOOTING.md`

**Step 1: Update CLAUDE.md stack table**

In `CLAUDE.md`, in the Stack Technique table, replace any mention of Sure with:

```markdown
| Applications | n8n 2.7.3, OpenClaw (YYYY.M.DD), LiteLLM v1.81.3-stable, NocoDB 0.301.2, Firefly III v6.5.3, Seko-Finance |
```

**Step 2: Update TROUBLESHOOTING.md**

In `docs/TROUBLESHOOTING.md`, replace the Sure crash-loop section (42.4) with a Firefly III section documenting:

- Redis DB numbers (db2, db3) to avoid collision
- `TRUSTED_PROXIES=**` required behind Caddy
- `APP_KEY` must be `base64:` prefixed (Laravel requirement)
- Data volume: only `/var/www/html/storage/upload` needs persistence
- Healthcheck: `curl -sf http://127.0.0.1:8080/health` (image has curl)

**Step 3: Commit**

```bash
git add CLAUDE.md docs/TROUBLESHOOTING.md
git commit -m "docs: update CLAUDE.md and TROUBLESHOOTING.md for Firefly III + Seko-Finance"
```

---

## Task 15: Run full lint + dry-run validation

**Step 1: Full lint**

Run: `source .venv/bin/activate && make lint`
Expected: 0 errors

**Step 2: Ansible dry-run (check mode)**

Run: `source .venv/bin/activate && ansible-playbook playbooks/site.yml --check --diff -e "target_env=prod" --tags firefly,seko-finance,caddy,postgresql`
Expected: Tasks show as "changed" (expected — new configs), no errors

**Step 3: Verify no remaining Sure references**

Run: `grep -rn 'sure_\|sure-web\|sure-worker\|sure_production\|caddy_sure' roles/ inventory/ playbooks/ .github/ --include='*.yml' --include='*.j2' --include='*.yaml'`
Expected: 0 matches (all Sure references removed)

**Step 4: Commit any fixes from lint/check**

If lint found issues, fix and commit:

```bash
git add -A
git commit -m "fix: address lint issues from Sure→Firefly migration"
```

---

## Task 16: Create DNS record via OVH API

**Step 1: Create OVH DNS record for `lola` subdomain**

This requires the OVH API credentials (already used by the project for DNS). Run from the VPS or workstation with OVH API access:

```bash
# Check existing records
curl -s "https://eu.api.ovh.com/1.0/domain/zone/<domain>/record?subDomain=lola" \
  -H "X-Ovh-Application: <app_key>" \
  -H "X-Ovh-Consumer: <consumer_key>" \
  -H "X-Ovh-Timestamp: $(date +%s)" \
  -H "X-Ovh-Signature: <signature>"

# Create A record pointing to VPS IP
# (Use the same method as existing CI provisioning in integration.yml)
```

Alternatively, add this to the `provision-hetzner.yml` playbook or run via the OVH web console.

**Step 2: Verify DNS resolution**

Run: `dig +short lola.ewutelo.cloud`
Expected: `137.74.114.167` (VPS public IP)

---

## Summary — Execution Order

| Task | Description | Files changed | Commit |
|------|-------------|---------------|--------|
| 1 | Remove Sure inventory vars, add Firefly/Seko-Finance | 3 | `refactor(inventory)` |
| 2 | Update Vault secrets | 1 | `vault:` |
| 3 | Update PostgreSQL DB definition | 1 | `refactor(postgresql)` |
| 4 | Delete Sure role + remove from playbook | 6 deleted, 1 modified | `chore:` |
| 5 | Create Firefly III role | 5 created | `feat(firefly)` |
| 6 | Create Seko-Finance role | 5 created | `feat(seko-finance)` |
| 7 | Register roles in site.yml | 1 modified | `feat(site)` |
| 8 | Update docker-compose template | 1 modified | `feat(docker-stack)` |
| 9 | Update Caddy config | 2 modified | `feat(caddy)` |
| 10 | Update smoke tests | 1 modified | `feat(smoke-tests)` |
| 11 | Update CI workflows | 1 modified | `ci(integration)` |
| 12 | Update Molecule converge files | 2 modified | `test(molecule)` |
| 13 | Create Molecule tests for new roles | 4 created | `test(molecule)` |
| 14 | Update documentation | 2 modified | `docs:` |
| 15 | Full lint + dry-run validation | 0-1 | `fix:` (if needed) |
| 16 | Create DNS record via OVH API | 0 (external) | N/A |

**Total: ~18 files modified/created, 6 files deleted, 14 commits**
