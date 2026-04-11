# MOP Machinery Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a NOC MOP (Method of Procedure) generation pipeline on Sese-AI (OVH VPS, amd64) consisting of Gotenberg + Carbone (dual render engines), n8n Multi-step Form + Typebot (dual authoring frontends), CLI wrappers, an atomic CSV index, and an Excel+VBA offline search — all VPN-only behind Caddy.

**Architecture:** Three new Ansible roles (gotenberg, carbone, typebot) using the VPAI tiny-role pattern (dirs + env_file + handler), a fourth distribution role (mop-templates), service blocks added to `docker-stack/templates/docker-compose.yml.j2` (Phase B), a Caddy volume mount + file_server route in `docker-compose-infra.yml.j2` (Phase A), and workflow JSONs committed under `scripts/n8n-workflows/` and `scripts/typebot/`. A single bash helper (`alloc-and-append.sh`) under `flock` is the source of truth for MOP ID allocation and CSV append, called from n8n Code nodes (via `execSync`), CLI wrappers, and the Typebot→n8n webhook.

**Tech Stack:** Ansible 2.16+ (FQCN, community.docker), Docker Compose V2, Gotenberg 8.30.1, Carbone EE community 4.26.3, Typebot builder+viewer 3.16.1, n8n 2.7.3 (existing), Caddy 2.11.2-alpine (existing), PostgreSQL 18.3 (existing, shared cluster), bash 5+ with `flock`/`util-linux`, Python `jinja2-cli` for HTML template rendering, VBA for Excel macro.

**Reference spec:** `docs/superpowers/specs/2026-04-11-mop-machinery-design.md`

---

## File Structure

### Created

| Path | Responsibility |
|---|---|
| `roles/gotenberg/defaults/main.yml` | Resource limits, dir vars |
| `roles/gotenberg/tasks/main.yml` | Create dirs, idempotent |
| `roles/gotenberg/handlers/main.yml` | `Restart gotenberg stack` handler |
| `roles/carbone/defaults/main.yml` | Resource limits, dir vars |
| `roles/carbone/tasks/main.yml` | Create dirs, post-task upload template w/ SHA256 gate |
| `roles/carbone/handlers/main.yml` | `Restart carbone stack` handler |
| `roles/typebot/defaults/main.yml` | Subdomains, DB name, limits |
| `roles/typebot/tasks/main.yml` | Dirs, env_file, PG provisioning |
| `roles/typebot/templates/typebot.env.j2` | All required env vars (DATABASE_URL, ENCRYPTION_SECRET, NEXTAUTH_URL, NEXT_PUBLIC_VIEWER_URL, SMTP_*, NEXT_PUBLIC_SMTP_FROM, ADMIN_EMAIL, DISABLE_SIGNUP) |
| `roles/typebot/templates/provision-typebot-db.sh.j2` | PG database/user creation script |
| `roles/typebot/handlers/main.yml` | `Restart typebot stack` handler |
| `roles/mop-templates/defaults/main.yml` | Destination paths |
| `roles/mop-templates/tasks/main.yml` | Install jinja2-cli, copy templates + scripts, create dirs, init CSV |
| `roles/mop-templates/files/mop.html` | HTML template (Jinja2) |
| `roles/mop-templates/files/mop.css` | Print CSS |
| `roles/mop-templates/files/mop.odt` | ODT template (binary, via LibreOffice) |
| `roles/mop-templates/files/contacts.yml` | Placeholder contacts |
| `roles/mop-templates/templates/alloc-and-append.sh.j2` | flock-atomic ID allocator (allocate/confirm/rollback) — templated for project_name |
| `roles/mop-templates/templates/mop-render-html.j2` | CLI wrapper for Gotenberg — templated for project_name |
| `roles/mop-templates/templates/mop-render-odt.j2` | CLI wrapper for Carbone — templated for project_name |
| `roles/mop-templates/files/alloc-and-append.bats` | bats test suite (static, run on Sese-AI) |
| `scripts/n8n-workflows/mop-generator-v1.json` | n8n Multi-step Form workflow |
| `scripts/n8n-workflows/mop-webhook-render-v1.json` | n8n webhook for Typebot |
| `scripts/typebot/mop-generator-v1.json` | Typebot flow export |
| `scripts/mop/mops-index.csv` | CSV bootstrap (header only) |
| `scripts/mop/mop-search.xlsm` | Excel+VBA search workbook |

### Modified

| Path | Change |
|---|---|
| `inventory/group_vars/all/versions.yml` | Add gotenberg/carbone/typebot image pins |
| `inventory/group_vars/all/secrets.yml` | Add `vault_typebot_*` vars |
| `playbooks/site.yml` | Add 4 roles to Phase 3 (mop-templates first) |
| `roles/docker-stack/templates/docker-compose.yml.j2` | Add service blocks: gotenberg, carbone, typebot-builder, typebot-viewer; add volumes to existing n8n block |
| `roles/docker-stack/templates/docker-compose-infra.yml.j2` | Add Caddy volume mount `/opt/{{ project_name }}/data/mop/pdf:/srv/mop-pdf:ro` |
| `roles/caddy/templates/Caddyfile.j2` | Add 3 routes: `mop-build.<domain>`, `mop.<domain>`, `mop-dl.<domain>` — all VPN-only |

---

## Wave 1 — Ansible Roles (Infrastructure Scaffolding)

### Task 1.1: Pin image versions

**Files:**
- Modify: `inventory/group_vars/all/versions.yml`

- [ ] **Step 1: Add image pins**

Add after the existing services (near the `# --- Applications ---` or `# --- Reverse Proxy ---` section, preserving comment style):

```yaml
# --- MOP Machinery (NOC procedure generation) ---
gotenberg_image: "gotenberg/gotenberg:8.30.1"
carbone_image: "carbone/carbone-ee:full-4.26.3"
typebot_builder_image: "baptistearno/typebot-builder:3.16.1"
typebot_viewer_image: "baptistearno/typebot-viewer:3.16.1"
```

- [ ] **Step 2: yamllint**

Run: `source .venv/bin/activate && yamllint inventory/group_vars/all/versions.yml`
Expected: no errors (warnings OK on line length)

- [ ] **Step 3: Commit**

```bash
git add inventory/group_vars/all/versions.yml
git commit -m "feat(mop): pin gotenberg/carbone/typebot image versions"
```

---

### Task 1.2: Gotenberg role scaffold

**Files:**
- Create: `roles/gotenberg/defaults/main.yml`
- Create: `roles/gotenberg/tasks/main.yml`
- Create: `roles/gotenberg/handlers/main.yml`
- Create: `roles/gotenberg/meta/main.yml`

- [ ] **Step 1: Write defaults**

`roles/gotenberg/defaults/main.yml`:
```yaml
---
# roles/gotenberg/defaults/main.yml — Configuration Gotenberg (HTML→PDF)
gotenberg_config_dir: "/opt/{{ project_name }}/configs/gotenberg"
gotenberg_memory_limit: "1g"
gotenberg_memory_reservation: "256m"
gotenberg_cpu_limit: "1.0"
# Chromium recycles after N conversions (documented in runbook)
gotenberg_chromium_max_conversions: 100
```

- [ ] **Step 2: Write tasks**

`roles/gotenberg/tasks/main.yml`:
```yaml
---
# roles/gotenberg/tasks/main.yml — Gotenberg provisioning (dirs only, no env file)

- name: "gotenberg | Create config dir"
  ansible.builtin.file:
    path: "{{ gotenberg_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true
  tags: [gotenberg]
```

- [ ] **Step 3: Write handlers**

`roles/gotenberg/handlers/main.yml`:
```yaml
---
# roles/gotenberg/handlers/main.yml
- name: "Restart gotenberg stack"
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - gotenberg
    state: present
    recreate: always
  become: true
```

- [ ] **Step 4: Write meta**

`roles/gotenberg/meta/main.yml`:
```yaml
---
galaxy_info:
  role_name: gotenberg
  author: vpai
  description: "Gotenberg HTML/CSS→PDF service for MOP machinery"
  license: MIT
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm
        - trixie
dependencies: []
```

- [ ] **Step 5: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/gotenberg/ && yamllint roles/gotenberg/`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add roles/gotenberg/
git commit -m "feat(mop): add gotenberg role scaffold (dirs + handler)"
```

---

### Task 1.3: Carbone role scaffold + idempotent template upload

**Files:**
- Create: `roles/carbone/defaults/main.yml`
- Create: `roles/carbone/tasks/main.yml`
- Create: `roles/carbone/handlers/main.yml`
- Create: `roles/carbone/meta/main.yml`

- [ ] **Step 1: Write defaults**

`roles/carbone/defaults/main.yml`:
```yaml
---
carbone_config_dir: "/opt/{{ project_name }}/configs/carbone"
carbone_data_dir: "/opt/{{ project_name }}/data/carbone"
carbone_template_dir: "{{ carbone_data_dir }}/template"
carbone_render_dir: "{{ carbone_data_dir }}/render"
carbone_memory_limit: "1.5g"
carbone_memory_reservation: "512m"
carbone_cpu_limit: "1.5"
carbone_container_url: "http://carbone:4000"
# Source template file (distributed by mop-templates role)
carbone_source_template: "/opt/{{ project_name }}/data/mop/templates/mop.odt"
```

- [ ] **Step 2a: Write tasks/main.yml (dirs ONLY — safe to run before Carbone is up)**

`roles/carbone/tasks/main.yml`:
```yaml
---
- name: "carbone | Create config dir"
  ansible.builtin.file:
    path: "{{ carbone_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true
  tags: [carbone]

- name: "carbone | Create data dirs (UID 1000)"
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "1000"
    group: "1000"
    mode: "0755"
  loop:
    - "{{ carbone_template_dir }}"
    - "{{ carbone_render_dir }}"
  become: true
  tags: [carbone]
```

- [ ] **Step 2b: Write tasks/template.yml (upload to running Carbone, gated `never` + explicit tag)**

`roles/carbone/tasks/template.yml`:
```yaml
---
# Included ONLY from playbooks/site.yml post_tasks with --tags carbone-template.
# Requires Carbone container to be running on {{ carbone_container_url }}.
- name: "carbone | Check source template exists"
  ansible.builtin.stat:
    path: "{{ carbone_source_template }}"
  register: carbone_tpl_stat
  tags: [carbone-template]

- name: "carbone | Compute SHA256 of source template"
  ansible.builtin.stat:
    path: "{{ carbone_source_template }}"
    checksum_algorithm: sha256
  register: carbone_tpl_hash
  when: carbone_tpl_stat.stat.exists
  tags: [carbone-template]

- name: "carbone | Read previous hash (if any)"
  ansible.builtin.slurp:
    src: "{{ carbone_config_dir }}/template-hash.txt"
  register: carbone_prev_hash_raw
  failed_when: false
  changed_when: false
  when: carbone_tpl_stat.stat.exists
  tags: [carbone-template]

- name: "carbone | Set hash comparison facts"
  ansible.builtin.set_fact:
    carbone_prev_hash: "{{ (carbone_prev_hash_raw.content | default('') | b64decode | trim) if (carbone_prev_hash_raw.content is defined) else '' }}"
    carbone_new_hash: "{{ carbone_tpl_hash.stat.checksum }}"
  when: carbone_tpl_stat.stat.exists
  tags: [carbone-template]

# Binary multipart upload via curl (ansible.builtin.uri file lookup corrupts ODT binaries)
- name: "carbone | Upload template via curl (binary-safe, only on hash change)"
  ansible.builtin.command:
    cmd: >
      curl -sS -o /tmp/carbone-upload.json -w '%{http_code}'
      -F 'template=@{{ carbone_source_template }};type=application/vnd.oasis.opendocument.text'
      {{ carbone_container_url }}/template
  register: carbone_upload_curl
  changed_when: carbone_upload_curl.stdout == '200'
  failed_when:
    - carbone_upload_curl.rc != 0 or carbone_upload_curl.stdout != '200'
  when:
    - carbone_tpl_stat.stat.exists
    - carbone_prev_hash | default('') != carbone_new_hash
  become: true
  tags: [carbone-template]

- name: "carbone | Parse templateId from upload response"
  ansible.builtin.slurp:
    src: /tmp/carbone-upload.json
  register: carbone_upload_blob
  when: carbone_upload_curl is changed
  tags: [carbone-template]

- name: "carbone | Persist new templateId"
  ansible.builtin.copy:
    content: "{{ (carbone_upload_blob.content | b64decode | from_json).data.templateId }}"
    dest: "{{ carbone_config_dir }}/template-id.txt"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  when: carbone_upload_curl is changed
  become: true
  tags: [carbone-template]

- name: "carbone | Persist new hash"
  ansible.builtin.copy:
    content: "{{ carbone_new_hash }}"
    dest: "{{ carbone_config_dir }}/template-hash.txt"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0644"
  when: carbone_upload_curl is changed
  become: true
  tags: [carbone-template]

- name: "carbone | Clean up upload response blob"
  ansible.builtin.file:
    path: /tmp/carbone-upload.json
    state: absent
  become: true
  tags: [carbone-template]
```

**Why split the role:**
- `tasks/main.yml` (dirs only) is safe during Phase 3 `docker-stack` run — no network calls, no container dependency
- `tasks/template.yml` is included ONLY from `playbooks/site.yml` `post_tasks` via `ansible.builtin.include_tasks`, AFTER `docker-stack` starts Carbone
- Running `make deploy-role ROLE=carbone` during Wave 1 smoke (Task 1.10) executes only `main.yml` (dirs) and will NOT fail with "connection refused" — the Carbone container isn't up yet and the upload lives in a separately-tagged include
- Binary-safe upload: `curl -F 'template=@path'` preserves the ODT zip byte-for-byte; `ansible.builtin.uri` + `lookup('file')` would corrupt it through YAML string coercion
- SHA256 hash gate prevents re-uploading on every deploy — template-hash.txt is the idempotence key

- [ ] **Step 3: Write handlers**

`roles/carbone/handlers/main.yml`:
```yaml
---
- name: "Restart carbone stack"
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - carbone
    state: present
    recreate: always
  become: true
```

- [ ] **Step 4: Write meta**

`roles/carbone/meta/main.yml` (mirror gotenberg meta).

- [ ] **Step 5: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/carbone/ && yamllint roles/carbone/`

- [ ] **Step 6: Commit**

```bash
git add roles/carbone/
git commit -m "feat(mop): add carbone role with idempotent SHA256-gated template upload"
```

---

### Task 1.4: Typebot role scaffold + PG provisioning

**Files:**
- Create: `roles/typebot/defaults/main.yml`
- Create: `roles/typebot/tasks/main.yml`
- Create: `roles/typebot/templates/typebot.env.j2`
- Create: `roles/typebot/templates/provision-typebot-db.sh.j2`
- Create: `roles/typebot/handlers/main.yml`
- Create: `roles/typebot/meta/main.yml`

- [ ] **Step 1: Defaults**

`roles/typebot/defaults/main.yml`:
```yaml
---
typebot_config_dir: "/opt/{{ project_name }}/configs/typebot"
typebot_data_dir: "/opt/{{ project_name }}/data/typebot"
typebot_db_name: "typebot"
typebot_db_user: "typebot"
typebot_builder_subdomain: "mop-build"
typebot_viewer_subdomain: "mop"
typebot_builder_url: "https://{{ typebot_builder_subdomain }}.{{ domain_name }}"
typebot_viewer_url: "https://{{ typebot_viewer_subdomain }}.{{ domain_name }}"
typebot_memory_limit: "512m"
typebot_memory_reservation: "128m"
typebot_cpu_limit: "1.0"
```

- [ ] **Step 2: provision-typebot-db.sh.j2**

`roles/typebot/templates/provision-typebot-db.sh.j2`:
```bash
#!/bin/bash
# {{ ansible_managed }}
# Provision Typebot database on shared PG cluster
set -euo pipefail

PG_CONTAINER="{{ project_name }}_postgresql"
DB_NAME="{{ typebot_db_name }}"
DB_USER="{{ typebot_db_user }}"
DB_PASSWORD="{{ postgresql_password }}"

# Idempotent user creation
docker exec -i "$PG_CONTAINER" psql -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
  docker exec -i "$PG_CONTAINER" psql -U postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"

# Idempotent DB creation
docker exec -i "$PG_CONTAINER" psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
  docker exec -i "$PG_CONTAINER" psql -U postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

# Grant all privileges
docker exec -i "$PG_CONTAINER" psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

echo "Typebot DB provisioned: $DB_NAME (user: $DB_USER)"
```

- [ ] **Step 3: typebot.env.j2**

`roles/typebot/templates/typebot.env.j2`:
```
# {{ ansible_managed }}
# Typebot environment — all vars required by Typebot 3.16.1

DATABASE_URL=postgresql://{{ typebot_db_user }}:{{ postgresql_password }}@{{ project_name }}_postgresql:5432/{{ typebot_db_name }}
ENCRYPTION_SECRET={{ vault_typebot_encryption_secret }}
NEXTAUTH_URL={{ typebot_builder_url }}
NEXT_PUBLIC_VIEWER_URL={{ typebot_viewer_url }}

# SMTP (magic link)
SMTP_HOST={{ vault_typebot_smtp_host }}
SMTP_PORT={{ vault_typebot_smtp_port }}
SMTP_USERNAME={{ vault_typebot_smtp_user }}
SMTP_PASSWORD={{ vault_typebot_smtp_password }}
NEXT_PUBLIC_SMTP_FROM={{ vault_typebot_smtp_from }}

# Admin
ADMIN_EMAIL={{ vault_typebot_admin_email }}
DISABLE_SIGNUP=true
```

- [ ] **Step 4: tasks**

`roles/typebot/tasks/main.yml`:
```yaml
---
- name: "typebot | Create dirs"
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  loop:
    - "{{ typebot_config_dir }}"
    - "{{ typebot_data_dir }}"
  become: true
  tags: [typebot]

- name: "typebot | Deploy env file"
  ansible.builtin.template:
    src: typebot.env.j2
    dest: "{{ typebot_config_dir }}/typebot.env"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0600"
  become: true
  notify: Restart typebot stack
  tags: [typebot]

- name: "typebot | Deploy PG provisioning script"
  ansible.builtin.template:
    src: provision-typebot-db.sh.j2
    dest: "{{ typebot_config_dir }}/provision-typebot-db.sh"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0750"
  become: true
  register: typebot_db_script
  tags: [typebot]

- name: "typebot | Run PG provisioning script"
  ansible.builtin.command:
    cmd: "{{ typebot_config_dir }}/provision-typebot-db.sh"
  become: true
  register: typebot_db_result
  changed_when: "'provisioned' in typebot_db_result.stdout"
  when: typebot_db_script.changed  # noqa no-handler
  tags: [typebot, typebot-db]
```

- [ ] **Step 5: handlers + meta**

Handlers and meta mirror the gotenberg pattern (handler name: `Restart typebot stack`, services: `[typebot-builder, typebot-viewer]`).

- [ ] **Step 6: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/typebot/ && yamllint roles/typebot/`

- [ ] **Step 7: Commit**

```bash
git add roles/typebot/
git commit -m "feat(mop): add typebot role with env_file + PG provisioning"
```

---

### Task 1.5: mop-templates role scaffold (tasks only, files in Wave 2)

**Files:**
- Create: `roles/mop-templates/defaults/main.yml`
- Create: `roles/mop-templates/tasks/main.yml`
- Create: `roles/mop-templates/meta/main.yml`

- [ ] **Step 1: Defaults**

`roles/mop-templates/defaults/main.yml`:
```yaml
---
mop_data_dir: "/opt/{{ project_name }}/data/mop"
mop_templates_dir: "{{ mop_data_dir }}/templates"
mop_pdf_dir: "{{ mop_data_dir }}/pdf"
mop_index_dir: "{{ mop_data_dir }}/index"
mop_dead_letter_dir: "{{ mop_data_dir }}/dead-letter"
mop_scripts_dir: "/opt/{{ project_name }}/scripts/mop"
mop_cli_bin_dir: "/usr/local/bin"
```

- [ ] **Step 2: Tasks**

`roles/mop-templates/tasks/main.yml`:
```yaml
---
- name: "mop-templates | Install system deps (pyyaml, jq, curl)"
  ansible.builtin.apt:
    name:
      - python3-yaml
      - jq
      - curl
    state: present
    update_cache: true
    cache_valid_time: 3600
  become: true
  tags: [mop-templates]
  # jinja2-cli is installed below via pipx (VPAI Python CLI convention);
  # python3-jinja2 apt package would be redundant and is not needed.

- name: "mop-templates | Ensure pipx is available (VPAI CLI tool convention)"
  ansible.builtin.apt:
    name: pipx
    state: present
  become: true
  tags: [mop-templates]

- name: "mop-templates | Install jinja2-cli via pipx system-wide"
  ansible.builtin.command:
    cmd: "pipx install --global jinja2-cli"
  register: mop_jinja2cli_install
  changed_when: "'installed package' in mop_jinja2cli_install.stdout"
  failed_when:
    - mop_jinja2cli_install.rc != 0
    - "'already installed' not in mop_jinja2cli_install.stderr"
  become: true
  tags: [mop-templates]

- name: "mop-templates | Verify jinja2 CLI reachable via PATH"
  ansible.builtin.command:
    cmd: jinja2 --version
  register: mop_jinja2cli_version
  changed_when: false
  become: true
  tags: [mop-templates]

- name: "mop-templates | Create data dirs (UID 1000)"
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "1000"
    group: "1000"
    mode: "0755"
  loop:
    - "{{ mop_data_dir }}"
    - "{{ mop_templates_dir }}"
    - "{{ mop_pdf_dir }}"
    - "{{ mop_index_dir }}"
    - "{{ mop_dead_letter_dir }}"
  become: true
  tags: [mop-templates]

- name: "mop-templates | Create scripts dir"
  ansible.builtin.file:
    path: "{{ mop_scripts_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true
  tags: [mop-templates]

- name: "mop-templates | Copy static template files (binary-safe via copy)"
  ansible.builtin.copy:
    src: "{{ item }}"
    dest: "{{ mop_templates_dir }}/{{ item }}"
    owner: "1000"
    group: "1000"
    mode: "0644"
  loop:
    - mop.html
    - mop.css
    - mop.odt
    - contacts.yml
    - alloc-and-append.bats
  become: true
  tags: [mop-templates]

- name: "mop-templates | Deploy alloc-and-append.sh (templated — bakes project_name)"
  ansible.builtin.template:
    src: alloc-and-append.sh.j2
    dest: "{{ mop_scripts_dir }}/alloc-and-append.sh"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true
  tags: [mop-templates]

- name: "mop-templates | Install CLI wrappers to /usr/local/bin (templated)"
  ansible.builtin.template:
    src: "{{ item }}.j2"
    dest: "{{ mop_cli_bin_dir }}/{{ item }}"
    owner: root
    group: root
    mode: "0755"
  loop:
    - mop-render-html
    - mop-render-odt
  become: true
  tags: [mop-templates]

- name: "mop-templates | Initialize CSV index (if absent)"
  ansible.builtin.copy:
    content: "\uFEFFid;title;keywords;severity;perimeter;filename;sub_procs;created_at\n"
    dest: "{{ mop_index_dir }}/mops-index.csv"
    owner: "1000"
    group: "1000"
    mode: "0644"
    force: false
  become: true
  tags: [mop-templates]
```

**Note on file layout:**
- `roles/mop-templates/files/` — static files copied byte-for-byte (mop.html, mop.css, mop.odt binary, contacts.yml, alloc-and-append.bats test suite)
- `roles/mop-templates/templates/` — Jinja2-templated scripts (alloc-and-append.sh.j2, mop-render-html.j2, mop-render-odt.j2)

The scripts become templates because they hardcode `/opt/{{ project_name }}/` paths that must render to `/opt/javisi/` at install time. Without templating, bash doesn't interpolate Jinja and the paths would be literal `/opt/{{ project_name }}/`.

- [ ] **Step 3: Create placeholder files**

Create empty/minimal placeholder files under both dirs so Wave 1 lints cleanly (Wave 2 overwrites the real content):

```bash
mkdir -p roles/mop-templates/files roles/mop-templates/templates
# Static files (copied byte-for-byte)
touch roles/mop-templates/files/mop.html
touch roles/mop-templates/files/mop.css
touch roles/mop-templates/files/mop.odt
touch roles/mop-templates/files/contacts.yml
touch roles/mop-templates/files/alloc-and-append.bats
# Templated scripts (.j2 suffix)
printf '#!/bin/bash\n# {{ ansible_managed }}\nset -euo pipefail\necho "placeholder for {{ project_name }}"\n' > roles/mop-templates/templates/alloc-and-append.sh.j2
printf '#!/bin/bash\n# {{ ansible_managed }}\nset -euo pipefail\necho "placeholder"\n' > roles/mop-templates/templates/mop-render-html.j2
printf '#!/bin/bash\n# {{ ansible_managed }}\nset -euo pipefail\necho "placeholder"\n' > roles/mop-templates/templates/mop-render-odt.j2
```

- [ ] **Step 4: meta**

`roles/mop-templates/meta/main.yml` — mirror gotenberg pattern.

- [ ] **Step 5: Lint**

Run: `source .venv/bin/activate && ansible-lint roles/mop-templates/ && yamllint roles/mop-templates/`

- [ ] **Step 6: Commit**

```bash
git add roles/mop-templates/
git commit -m "feat(mop): add mop-templates role scaffold with placeholders"
```

---

### Task 1.6: Add service blocks to docker-compose.yml.j2

**Files:**
- Modify: `roles/docker-stack/templates/docker-compose.yml.j2`

- [ ] **Step 1: Add volume mounts to n8n block**

Locate the existing n8n service block. In the `volumes:` section, add before `networks:`:

```yaml
      # MOP machinery: host filesystem access for alloc-and-append.sh + CSV + dead-letter
      - /opt/{{ project_name }}/data/mop:/data/mop
      - /opt/{{ project_name }}/scripts/mop:/scripts/mop:ro
      # Carbone template ID file (written by carbone-template post-task)
      - /opt/{{ project_name }}/configs/carbone:/configs/carbone:ro
```

The n8n workflow reads the templateId at webhook time from `/configs/carbone/template-id.txt` via a Code node — no env var gymnastics, no cross-role ordering fragility. If Carbone hasn't been provisioned yet the file is absent and the workflow fails fast with a clear error.

- [ ] **Step 2: Add gotenberg service block**

After the nocodb block (or at the end of the APPLICATION LAYER section), add:

```yaml
  # === MOP MACHINERY — Rendering engines ===
  gotenberg:
    image: {{ gotenberg_image }}
    container_name: {{ project_name }}_gotenberg
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp:size=256m
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: {{ gotenberg_memory_limit }}
          cpus: "{{ gotenberg_cpu_limit }}"
        reservations:
          memory: {{ gotenberg_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:3000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    # No custom command — Gotenberg 8.30.1 runs on defaults per spec §3.1.
    # If queue size or API timeout tuning is needed later, validate flag names
    # against upstream release notes first (several older flags have been renamed).
```

- [ ] **Step 3: Add carbone service block**

Right after gotenberg:

```yaml
  carbone:
    image: {{ carbone_image }}
    container_name: {{ project_name }}_carbone
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
      - DAC_OVERRIDE
      - FOWNER
    volumes:
      - /opt/{{ project_name }}/data/carbone/template:/app/template
      - /opt/{{ project_name }}/data/carbone/render:/app/render
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: {{ carbone_memory_limit }}
          cpus: "{{ carbone_cpu_limit }}"
        reservations:
          memory: {{ carbone_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://127.0.0.1:4000/status || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
```

- [ ] **Step 4: Add typebot service blocks**

Right after carbone:

```yaml
  typebot-builder:
    image: {{ typebot_builder_image }}
    container_name: {{ project_name }}_typebot_builder
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
      - /opt/{{ project_name }}/configs/typebot/typebot.env
    networks:
      - backend
      - frontend
    deploy:
      resources:
        limits:
          memory: {{ typebot_memory_limit }}
          cpus: "{{ typebot_cpu_limit }}"
        reservations:
          memory: {{ typebot_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:3000/api/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 90s

  typebot-viewer:
    image: {{ typebot_viewer_image }}
    container_name: {{ project_name }}_typebot_viewer
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
      - /opt/{{ project_name }}/configs/typebot/typebot.env
    networks:
      - backend
      - frontend
    deploy:
      resources:
        limits:
          memory: {{ typebot_memory_limit }}
          cpus: "{{ typebot_cpu_limit }}"
        reservations:
          memory: {{ typebot_memory_reservation }}
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:3000/api/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 90s
```

- [ ] **Step 5: Template sanity check**

Run: `source .venv/bin/activate && ansible-playbook playbooks/site.yml --check --diff --tags docker-stack -e target_env=prod`
Expected: dry-run completes without Jinja2 syntax errors. May fail on "cannot connect to host" — that's OK, we're only validating template rendering.

- [ ] **Step 6: Commit**

```bash
git add roles/docker-stack/templates/docker-compose.yml.j2
git commit -m "feat(mop): add gotenberg/carbone/typebot service blocks + n8n mop volumes"
```

---

### Task 1.7: Add Caddy routes + file_server volume mount

**Files:**
- Modify: `roles/docker-stack/templates/docker-compose-infra.yml.j2`
- Modify: `roles/caddy/templates/Caddyfile.j2`

- [ ] **Step 1: Add volume mount to Caddy in docker-compose-infra.yml.j2**

Locate the existing `caddy:` service block. In `volumes:`, add:

```yaml
      - /opt/{{ project_name }}/data/mop/pdf:/srv/mop-pdf:ro
```

- [ ] **Step 2: Add 3 Caddy routes**

Locate the existing VPN-only route block (search for `(vpn_only)` snippet usage). Add, following the same pattern as existing routes:

```
# MOP Machinery — Typebot builder (VPN-only)
{{ typebot_builder_subdomain }}.{{ domain_name }} {
    import vpn_only
    reverse_proxy {{ project_name }}_typebot_builder:3000
}

# MOP Machinery — Typebot viewer (VPN-only)
{{ typebot_viewer_subdomain }}.{{ domain_name }} {
    import vpn_only
    reverse_proxy {{ project_name }}_typebot_viewer:3000
}

# MOP Machinery — Static PDF delivery (VPN-only)
mop-dl.{{ domain_name }} {
    import vpn_only
    root * /srv/mop-pdf
    file_server browse off
}
```

Note: The exact snippet name must match VPAI convention. If the existing snippet is `(vpn_only)` with parentheses, use `import vpn_only`. Verify with `grep -n "vpn_only" roles/caddy/templates/Caddyfile.j2`.

- [ ] **Step 3: yamllint + caddy fmt check**

Run: `source .venv/bin/activate && yamllint roles/docker-stack/templates/docker-compose-infra.yml.j2`
Run: `ansible-playbook playbooks/site.yml --check --diff --tags caddy -e target_env=prod` (Jinja render only)

- [ ] **Step 4: Commit**

```bash
git add roles/docker-stack/templates/docker-compose-infra.yml.j2 roles/caddy/templates/Caddyfile.j2
git commit -m "feat(mop): add Caddy routes for Typebot + mop-dl file_server"
```

---

### Task 1.8: Wire roles into playbooks/site.yml

**Files:**
- Modify: `playbooks/site.yml`

- [ ] **Step 1: Add roles in Phase 3, mop-templates first**

Locate the `# Phase 3 — Applications` section. After the existing apps (after `- role: flash-suite`), add:

```yaml
    - role: mop-templates
      tags: [mop-templates, phase3]
    - role: gotenberg
      tags: [gotenberg, phase3]
    - role: carbone
      tags: [carbone, phase3]
    - role: typebot
      tags: [typebot, phase3]
```

- [ ] **Step 2: Add post-docker-stack carbone template upload**

The carbone role has two task files: `tasks/main.yml` (creates config dirs, runs during Phase 3 role ordering — safe anytime) and `tasks/template.yml` (uploads the ODT template via curl — must run AFTER docker-stack starts the Carbone container). Add a `post_tasks` entry at the bottom of `playbooks/site.yml` that explicitly includes `tasks_from: template`:

```yaml
  post_tasks:
    - name: "mop | Upload Carbone template after docker-stack up"
      ansible.builtin.include_role:
        name: carbone
        tasks_from: template
      tags: [carbone-template, phase4]
```

Note: `tasks_from: template` loads `roles/carbone/tasks/template.yml` (Ansible auto-appends `.yml`). This is the file created in Task 1.3 Step 2b containing the curl-based binary upload logic. Do NOT use `tasks_from: main` — that file only creates directories and would silently skip the upload.

- [ ] **Step 3: yamllint + ansible-lint**

Run: `source .venv/bin/activate && yamllint playbooks/site.yml && ansible-lint playbooks/site.yml`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add playbooks/site.yml
git commit -m "feat(mop): wire mop roles into site.yml phase 3 + carbone template post-task"
```

---

### Task 1.9: Add Typebot secrets to vault

**Files:**
- Modify: `inventory/group_vars/all/secrets.yml` (Ansible Vault encrypted)

- [ ] **Step 1: Generate random values**

Run: `openssl rand -base64 24` → use for `vault_typebot_encryption_secret`

- [ ] **Step 2: Edit vault**

Run: `source .venv/bin/activate && ansible-vault edit inventory/group_vars/all/secrets.yml`

Add at the bottom:

```yaml
# --- Typebot (MOP machinery) ---
vault_typebot_encryption_secret: "<PASTE openssl output>"
vault_typebot_smtp_host: "smtp.sendgrid.net"  # TO BE REPLACED
vault_typebot_smtp_port: 587
vault_typebot_smtp_user: "apikey"  # SMTP_USERNAME
vault_typebot_smtp_password: "<TO BE FILLED>"
vault_typebot_smtp_from: "mop-noreply@{{ domain_name }}"
vault_typebot_admin_email: "<YOUR EMAIL>"
```

- [ ] **Step 3: Commit**

```bash
git add inventory/group_vars/all/secrets.yml
git commit -m "feat(mop): add typebot secrets to vault"
```

---

### Task 1.10: Wave 1 smoke deploy (dirs + lint only, no services up)

- [ ] **Step 1: Deploy dry-run**

Run: `source .venv/bin/activate && ansible-playbook playbooks/site.yml --check --diff --tags "mop-templates,gotenberg,carbone,typebot" -e target_env=prod`
Expected: tasks listed, no syntax errors.

- [ ] **Step 2: Deploy for real (scaffold only)**

Run: `make deploy-role ROLE=mop-templates ENV=prod`

Then: `make deploy-role ROLE=gotenberg ENV=prod`
Then: `make deploy-role ROLE=carbone ENV=prod`
Then: `make deploy-role ROLE=typebot ENV=prod`

Expected: 4 roles applied, idempotent on re-run, changed=0 on second run.

- [ ] **Step 3: Verify on Sese-AI**

Run over SSH (Tailscale):
```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 'ls -la /opt/{{ project_name }}/data/mop/ /opt/{{ project_name }}/configs/typebot/ /opt/{{ project_name }}/configs/carbone/'
```
Expected: directories exist, typebot.env present and mode 0600.

---

## Wave 2 — Templates + CLI Wrappers (Real Content)

### Task 2.1: Write alloc-and-append.sh (source of truth)

**Files:**
- Modify: `roles/mop-templates/templates/alloc-and-append.sh.j2` (templated script — host path bakes `project_name`)
- Create: `roles/mop-templates/files/alloc-and-append.bats` (static bats test — runs on Sese-AI)

- [ ] **Step 1: Write the bats test (TDD — Sese-AI only)**

`bats` is not installed on Waza. The bats suite is distributed by the `mop-templates` role as a static file next to the deployed script, then executed on Sese-AI during Wave 1 smoke (Task 1.10) and Wave 2 acceptance (Task 2.6). Waza devs: `shellcheck` is sufficient locally.

`roles/mop-templates/files/alloc-and-append.bats`:

```bash
#!/usr/bin/env bats

setup() {
  TMPDIR_ROOT="$(mktemp -d)"
  export MOP_DATA_DIR="$TMPDIR_ROOT/mop"
  mkdir -p "$MOP_DATA_DIR/index"
  printf '\xef\xbb\xbfid;title;keywords;severity;perimeter;filename;sub_procs;created_at\n' > "$MOP_DATA_DIR/index/mops-index.csv"
  SCRIPT="$BATS_TEST_DIRNAME/alloc-and-append.sh"
}

teardown() {
  rm -rf "$TMPDIR_ROOT"
}

@test "allocate returns first ID as MOP-YYYY-0001" {
  local year
  year=$(date +%Y)
  run "$SCRIPT" allocate '{"title":"test","keywords":["a"],"severity":"minor","perimeter":"test"}'
  [ "$status" -eq 0 ]
  [[ "$output" == "MOP-${year}-0001" ]]
}

@test "allocate increments sequentially" {
  "$SCRIPT" allocate '{"title":"t1","keywords":["a"],"severity":"minor","perimeter":"p"}'
  "$SCRIPT" confirm MOP-$(date +%Y)-0001 '{"title":"t1","keywords":["a"],"severity":"minor","perimeter":"p","filename":"t1.pdf","sub_procs":""}'
  run "$SCRIPT" allocate '{"title":"t2","keywords":["b"],"severity":"minor","perimeter":"p"}'
  [ "$status" -eq 0 ]
  [[ "$output" == "MOP-$(date +%Y)-0002" ]]
}

@test "confirm appends CSV line" {
  "$SCRIPT" allocate '{"title":"t","keywords":["a"],"severity":"minor","perimeter":"p"}'
  run "$SCRIPT" confirm MOP-$(date +%Y)-0001 '{"title":"t","keywords":["a"],"severity":"minor","perimeter":"p","filename":"t.pdf","sub_procs":"SP-01"}'
  [ "$status" -eq 0 ]
  run wc -l "$MOP_DATA_DIR/index/mops-index.csv"
  [[ "$output" =~ ^2\  ]]
}

@test "rollback removes pending without CSV change" {
  "$SCRIPT" allocate '{"title":"t","keywords":["a"],"severity":"minor","perimeter":"p"}'
  run "$SCRIPT" rollback MOP-$(date +%Y)-0001
  [ "$status" -eq 0 ]
  run wc -l "$MOP_DATA_DIR/index/mops-index.csv"
  [[ "$output" =~ ^1\  ]]
}

@test "10 parallel allocates produce 10 distinct IDs" {
  for i in {1..10}; do
    ( "$SCRIPT" allocate "{\"title\":\"t$i\",\"keywords\":[\"x\"],\"severity\":\"minor\",\"perimeter\":\"p\"}" ) &
  done
  wait
  # Count .pending files
  local count
  count=$(ls "$MOP_DATA_DIR/index/.pending/" 2>/dev/null | wc -l)
  [ "$count" -eq 10 ]
}

@test "malformed JSON fails with non-zero exit" {
  run "$SCRIPT" allocate 'not json'
  [ "$status" -ne 0 ]
}
```

- [ ] **Step 2: Write the script (as Jinja2 template)**

`roles/mop-templates/templates/alloc-and-append.sh.j2`:

```bash
#!/usr/bin/env bash
# {{ ansible_managed }}
# alloc-and-append.sh — Atomic MOP ID allocator and CSV index writer
# Usage:
#   alloc-and-append.sh allocate '<json_payload>'
#     → prints new ID MOP-YYYY-NNNN on stdout, creates .pending/<id>
#   alloc-and-append.sh confirm <id> '<json_payload_with_filename>'
#     → appends CSV line, removes .pending/<id>
#   alloc-and-append.sh rollback <id>
#     → removes .pending/<id>, no CSV write
#
# Environment:
#   MOP_DATA_DIR — base path (default: /data/mop inside containers, /opt/{{ project_name }}/data/mop on host)
#
# All operations run under flock -x on MOP_DATA_DIR/index/.lock

set -euo pipefail

MOP_DATA_DIR="${MOP_DATA_DIR:-/data/mop}"
INDEX_DIR="$MOP_DATA_DIR/index"
CSV="$INDEX_DIR/mops-index.csv"
LOCK="$INDEX_DIR/.lock"
PENDING_DIR="$INDEX_DIR/.pending"

CMD="${1:-}"
shift || true

die() { echo "ERROR: $*" >&2; exit 1; }

ensure_dirs() {
  mkdir -p "$INDEX_DIR" "$PENDING_DIR"
  [[ -f "$CSV" ]] || printf '\xef\xbb\xbfid;title;keywords;severity;perimeter;filename;sub_procs;created_at\n' > "$CSV"
  [[ -f "$LOCK" ]] || touch "$LOCK"
}

validate_json() {
  local j="$1"
  echo "$j" | jq empty 2>/dev/null || die "invalid JSON"
}

alloc() {
  local payload="${1:-}"
  [[ -n "$payload" ]] || die "allocate requires JSON payload"
  validate_json "$payload"
  ensure_dirs

  local year last_id last_num next_num new_id
  year=$(date +%Y)

  # Scan CSV for current year's max seq, plus pending files.
  # IMPORTANT: force base-10 parsing with `10#...` — bash arithmetic treats
  # leading-zero strings like "0010" as octal (→ 8), and "0009" fails entirely.
  # Using `10#${BASH_REMATCH[1]}` strips leading zeros as a base-10 integer.
  last_num=0
  while IFS= read -r line; do
    [[ "$line" =~ ^MOP-${year}-([0-9]+) ]] || continue
    local n=$((10#${BASH_REMATCH[1]}))
    (( n > last_num )) && last_num=$n
  done < <(awk -F';' 'NR>1 {print $1}' "$CSV")

  # Also check pending
  if [[ -d "$PENDING_DIR" ]]; then
    for f in "$PENDING_DIR"/MOP-"$year"-*; do
      [[ -e "$f" ]] || continue
      local bn=$(basename "$f")
      [[ "$bn" =~ ^MOP-${year}-([0-9]+)$ ]] || continue
      local n=$((10#${BASH_REMATCH[1]}))
      (( n > last_num )) && last_num=$n
    done
  fi

  next_num=$((last_num + 1))
  new_id=$(printf "MOP-%s-%04d" "$year" "$next_num")

  # Record pending
  echo "$payload" > "$PENDING_DIR/$new_id"
  echo "$new_id"
}

confirm() {
  local id="${1:-}"
  local payload="${2:-}"
  [[ -n "$id" && -n "$payload" ]] || die "confirm requires <id> <json>"
  validate_json "$payload"
  [[ -f "$PENDING_DIR/$id" ]] || die "no pending entry for $id"

  local title keywords severity perimeter filename sub_procs created_at
  title=$(echo "$payload" | jq -r '.title // ""')
  keywords=$(echo "$payload" | jq -r '.keywords // [] | join(",")')
  severity=$(echo "$payload" | jq -r '.severity // "minor"')
  perimeter=$(echo "$payload" | jq -r '.perimeter // ""')
  filename=$(echo "$payload" | jq -r '.filename // ""')
  sub_procs=$(echo "$payload" | jq -r '.sub_procs // ""')
  created_at=$(date -Iseconds)

  # Escape double-quotes in title
  title_esc=${title//\"/\"\"}

  printf '%s;"%s";"%s";%s;%s;%s;%s;%s\n' \
    "$id" "$title_esc" "$keywords" "$severity" "$perimeter" "$filename" "$sub_procs" "$created_at" >> "$CSV"

  rm -f "$PENDING_DIR/$id"
}

rollback() {
  local id="${1:-}"
  [[ -n "$id" ]] || die "rollback requires <id>"
  rm -f "$PENDING_DIR/$id"
}

ensure_dirs

# All commands run under flock
exec 9> "$LOCK"
flock -x 9

case "$CMD" in
  allocate) alloc "$@" ;;
  confirm)  confirm "$@" ;;
  rollback) rollback "$@" ;;
  *) die "unknown command: $CMD (allocate|confirm|rollback)" ;;
esac
```

- [ ] **Step 3: Run the bats tests (Sese-AI only — bats not required on Waza)**

The bats test suite is the acceptance gate for `alloc-and-append.sh`. Because Waza (Raspberry Pi workstation) doesn't ship with `bats`, the test run happens on Sese-AI after Wave 1 deploys the script file. Skip local execution on Waza.

```bash
# On Sese-AI via Tailscale:
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 '
  sudo apt-get install -y bats &&
  cd /opt/javisi/scripts/mop &&
  sudo cp /opt/javisi/data/mop/templates/alloc-and-append.bats . 2>/dev/null || true &&
  MOP_DATA_DIR=/tmp/mop-bats-$$ bats alloc-and-append.bats
'
```
Expected: all 6 bats tests pass. (Waza developers: run `shellcheck` locally instead — `shellcheck roles/mop-templates/files/alloc-and-append.sh.j2` catches most regressions.)

The `mop-templates` role distributes `alloc-and-append.bats` alongside the script so the test suite stays reproducible on the target host. Task 1.5 `mop-templates/tasks/main.yml` must add the `.bats` file to the copy loop.

- [ ] **Step 4: Commit**

```bash
git add roles/mop-templates/templates/alloc-and-append.sh.j2 roles/mop-templates/files/alloc-and-append.bats
git commit -m "feat(mop): atomic alloc-and-append.sh.j2 with bats test suite"
```

---

### Task 2.2: Write mop.html template

**Files:**
- Modify: `roles/mop-templates/files/mop.html`
- Modify: `roles/mop-templates/files/mop.css`

- [ ] **Step 1: Write mop.html (Jinja2)**

Content: A4 print-ready HTML with header (title, incident metadata), decision tree, numbered steps, REX zone (3 columns: causes fréquentes, pièges, mean time), escalation contacts footer. Use `{{ ... }}` Jinja2 syntax.

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>{{ id }} — {{ title }}</title>
  <link rel="stylesheet" href="mop.css">
</head>
<body>
  <header class="mop-header">
    <h1>{{ title }}</h1>
    <div class="mop-meta">
      <span class="mop-id">{{ id }}</span>
      <span class="mop-severity severity-{{ severity }}">{{ severity | upper }}</span>
      <span class="mop-perimeter">{{ perimeter }}</span>
    </div>
  </header>

  <section class="incident">
    <h2>Incident</h2>
    <dl>
      <dt>Ticket</dt><dd>{{ incident.ticket }}</dd>
      <dt>Date</dt><dd>{{ incident.date }}</dd>
      <dt>Équipement</dt><dd>{{ incident.equipment }}</dd>
      <dt>Site</dt><dd>{{ incident.site }}</dd>
    </dl>
    <details>
      <summary>Mail source</summary>
      <p><strong>{{ incident.raw_email_subject }}</strong></p>
      <pre>{{ incident.raw_email_body }}</pre>
    </details>
  </section>

  <section class="steps">
    <h2>Procédure</h2>
    <ol>
    {% for step in steps %}
      <li>
        <strong>{{ step.title }}</strong>
        <p>{{ step.desc }}</p>
        {% if step.link_sp %}<a href="#{{ step.link_sp }}" class="sp-link">→ {{ step.link_sp }}</a>{% endif %}
      </li>
    {% endfor %}
    </ol>
  </section>

  <section class="rex">
    <h2>REX — Retour d'expérience ({{ rex.similar_cases_count }} cas similaires)</h2>
    <div class="rex-grid">
      <div class="rex-col">
        <h3>Causes fréquentes</h3>
        <ul>
        {% for c in rex.root_causes %}<li>{{ c }}</li>{% endfor %}
        </ul>
      </div>
      <div class="rex-col">
        <h3>Pièges</h3>
        <ul>
        {% for p in rex.pitfalls %}<li>{{ p }}</li>{% endfor %}
        </ul>
      </div>
      <div class="rex-col">
        <h3>Temps moyen</h3>
        <p class="mean-time">{{ rex.mean_resolution_time }}</p>
      </div>
    </div>
  </section>

  <footer class="escalation">
    <h2>Escalade</h2>
    <p><strong>Contact primaire :</strong> {{ escalation.primary_contact }}</p>
    <p><strong>Fallback :</strong> {{ escalation.fallback }}</p>
    <p><strong>Coordinateur site distant :</strong> {{ escalation.coordinator_site_distant }}</p>
  </footer>
</body>
</html>
```

- [ ] **Step 2: Write mop.css**

```css
@page { size: A4; margin: 1.5cm; }

body {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 11pt;
  color: #222;
  line-height: 1.4;
}

.mop-header {
  border-bottom: 2px solid #333;
  padding-bottom: 0.5em;
  margin-bottom: 1em;
}

.mop-header h1 { margin: 0; font-size: 18pt; }

.mop-meta {
  margin-top: 0.3em;
  display: flex;
  gap: 1em;
  font-size: 10pt;
}

.mop-id { font-family: monospace; font-weight: bold; }

.mop-severity {
  padding: 2px 8px;
  border-radius: 3px;
  font-weight: bold;
}
.severity-minor    { background: #e0f3e0; color: #1a5a1a; }
.severity-major    { background: #fff4d6; color: #8a5a00; }
.severity-critical { background: #ffdcdc; color: #8a0000; }

section { margin-bottom: 1.2em; break-inside: avoid; }

section h2 {
  font-size: 13pt;
  border-left: 4px solid #4a6fa5;
  padding-left: 0.5em;
  margin: 0.6em 0 0.4em 0;
}

.incident dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; }
.incident dt { font-weight: bold; color: #555; }

.incident details { margin-top: 0.5em; }
.incident pre {
  background: #f5f5f5;
  padding: 0.5em;
  border: 1px solid #ddd;
  font-size: 9pt;
  white-space: pre-wrap;
}

.steps ol { padding-left: 1.5em; }
.steps li { margin-bottom: 0.6em; break-inside: avoid; }
.sp-link { color: #4a6fa5; text-decoration: none; font-family: monospace; font-size: 10pt; }

.rex-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  border: 1px solid #ccc;
  padding: 0.6em;
  background: #fafafa;
}
.rex-col h3 {
  font-size: 10pt;
  margin: 0 0 0.3em 0;
  color: #4a6fa5;
}
.rex-col ul { padding-left: 1.2em; margin: 0; font-size: 9.5pt; }
.mean-time { font-size: 16pt; font-weight: bold; margin: 0.2em 0; color: #4a6fa5; }

.escalation {
  border-top: 1px solid #ccc;
  padding-top: 0.5em;
  margin-top: 1.5em;
  font-size: 9.5pt;
}
.escalation h2 { border-left: 4px solid #8a5a00; }
```

- [ ] **Step 3: Test Jinja2 render locally**

```bash
cat > /tmp/sample.json <<'EOF'
{
  "id": "MOP-2026-0001",
  "title": "Test",
  "severity": "major",
  "perimeter": "test",
  "incident": {"ticket": "INC-1", "date": "2026-04-11", "equipment": "Ribbon-X", "site": "TH2", "raw_email_subject": "sub", "raw_email_body": "body"},
  "steps": [{"title": "s1", "desc": "d1", "link_sp": "SP-01"}],
  "rex": {"similar_cases_count": 3, "root_causes": ["a"], "pitfalls": ["b"], "mean_resolution_time": "1h"},
  "escalation": {"primary_contact": "x", "fallback": "y", "coordinator_site_distant": "TH2"}
}
EOF
jinja2 roles/mop-templates/files/mop.html /tmp/sample.json > /tmp/rendered.html
grep -q "MOP-2026-0001" /tmp/rendered.html && echo PASS || echo FAIL
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add roles/mop-templates/files/mop.html roles/mop-templates/files/mop.css
git commit -m "feat(mop): bootstrap mop.html + mop.css print template"
```

---

### Task 2.3: Create mop.odt with LibreOffice

**Files:**
- Modify: `roles/mop-templates/files/mop.odt`

- [ ] **Step 1: Create the ODT**

Open LibreOffice Writer and create a document with the same structure as `mop.html` but using Carbone syntax placeholders:
- Title: `{d.title}` with `{d.id}` in a smaller font
- Severity with `{d.severity:ifEQ(major):show(MAJEUR):elseShow(mineur)}`
- Steps loop: `{d.steps[i].title}` ... `{d.steps[i+1].title}`
- REX loop for causes: `{d.rex.root_causes[i]}`
- Escalation fields: `{d.escalation.primary_contact}` etc.

Save as `roles/mop-templates/files/mop.odt`.

Alternative (non-interactive): use a minimal seed ODT from a template generator (fodt XML hand-written) and convert with `soffice --headless --convert-to odt`.

- [ ] **Step 2: Validate ODT is a valid zip**

Run: `file roles/mop-templates/files/mop.odt`
Expected: `OpenDocument Text`

- [ ] **Step 3: Commit (git-lfs not required, ODT is small)**

```bash
git add roles/mop-templates/files/mop.odt
git commit -m "feat(mop): bootstrap mop.odt ODT template with Carbone syntax"
```

---

### Task 2.4: Write CLI wrappers

**Files:**
- Modify: `roles/mop-templates/templates/mop-render-html.j2`
- Modify: `roles/mop-templates/templates/mop-render-odt.j2`

Both are Jinja2 templates — Ansible renders `{{ project_name }}` to `javisi` at deploy time, producing static bash scripts at `/usr/local/bin/mop-render-html` and `/usr/local/bin/mop-render-odt` on the target host. Keep the `{{ project_name }}` literal in the `.j2` source; never hardcode `javisi`.

- [ ] **Step 1: mop-render-html.j2**

```bash
#!/usr/bin/env bash
# {{ ansible_managed }}
# mop-render-html — Render MOP JSON → PDF via Gotenberg
# Usage: mop-render-html [-o output.pdf] [input.json]
#        cat input.json | mop-render-html -o out.pdf
set -euo pipefail

GOTENBERG_URL="${GOTENBERG_URL:-http://localhost:3000}"
TEMPLATE_HTML="/opt/{{ project_name }}/data/mop/templates/mop.html"
TEMPLATE_CSS="/opt/{{ project_name }}/data/mop/templates/mop.css"
MOP_DATA_DIR="${MOP_DATA_DIR:-/opt/{{ project_name }}/data/mop}"
ALLOC_SCRIPT="/opt/{{ project_name }}/scripts/mop/alloc-and-append.sh"

OUT=""
INPUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) OUT="$2"; shift 2 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)  INPUT="$1"; shift ;;
  esac
done

if [[ -z "$INPUT" ]]; then
  JSON=$(cat)
else
  JSON=$(cat "$INPUT")
fi

# Validate
echo "$JSON" | jq empty

# Allocate ID
ID=$(MOP_DATA_DIR="$MOP_DATA_DIR" "$ALLOC_SCRIPT" allocate "$JSON")
JSON_WITH_ID=$(echo "$JSON" | jq --arg id "$ID" '. + {id: $id}')

# Render HTML
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
echo "$JSON_WITH_ID" > "$TMPDIR/data.json"
jinja2 "$TEMPLATE_HTML" "$TMPDIR/data.json" > "$TMPDIR/index.html"
cp "$TEMPLATE_CSS" "$TMPDIR/mop.css"

# POST to Gotenberg
[[ -z "$OUT" ]] && OUT="$MOP_DATA_DIR/pdf/$ID.pdf"
HTTP=$(curl -sS -o "$OUT" -w "%{http_code}" \
  --form "files=@$TMPDIR/index.html" \
  --form "files=@$TMPDIR/mop.css" \
  "$GOTENBERG_URL/forms/chromium/convert/html")

if [[ "$HTTP" != "200" ]]; then
  MOP_DATA_DIR="$MOP_DATA_DIR" "$ALLOC_SCRIPT" rollback "$ID"
  echo "Gotenberg HTTP $HTTP" >&2
  exit 1
fi

# Confirm
CONFIRM_PAYLOAD=$(echo "$JSON_WITH_ID" | jq --arg fn "$(basename "$OUT")" '. + {filename: $fn, sub_procs: ([.steps[]?.link_sp] | map(select(. != null)) | join(","))}')
MOP_DATA_DIR="$MOP_DATA_DIR" "$ALLOC_SCRIPT" confirm "$ID" "$CONFIRM_PAYLOAD"

echo "$ID → $OUT"
```

- [ ] **Step 2: mop-render-odt.j2**

```bash
#!/usr/bin/env bash
# {{ ansible_managed }}
# mop-render-odt — Render MOP JSON → PDF via Carbone
# Usage: mop-render-odt [-o out.pdf] input.json
set -euo pipefail

CARBONE_URL="${CARBONE_URL:-http://localhost:4000}"
TEMPLATE_ID_FILE="/opt/{{ project_name }}/configs/carbone/template-id.txt"
MOP_DATA_DIR="${MOP_DATA_DIR:-/opt/{{ project_name }}/data/mop}"
ALLOC_SCRIPT="/opt/{{ project_name }}/scripts/mop/alloc-and-append.sh"

OUT=""
INPUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) OUT="$2"; shift 2 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)  INPUT="$1"; shift ;;
  esac
done

[[ -n "$INPUT" ]] || { echo "usage: mop-render-odt [-o out.pdf] input.json" >&2; exit 2; }
[[ -f "$TEMPLATE_ID_FILE" ]] || { echo "template-id.txt not found; run ansible -t carbone-template" >&2; exit 3; }
TEMPLATE_ID=$(cat "$TEMPLATE_ID_FILE")

JSON=$(cat "$INPUT")
echo "$JSON" | jq empty

ID=$(MOP_DATA_DIR="$MOP_DATA_DIR" "$ALLOC_SCRIPT" allocate "$JSON")
JSON_WITH_ID=$(echo "$JSON" | jq --arg id "$ID" '. + {id: $id}')
[[ -z "$OUT" ]] && OUT="$MOP_DATA_DIR/pdf/$ID.pdf"

# Step 1: POST render job
RENDER_BODY=$(jq -n --argjson data "$JSON_WITH_ID" '{data: $data, convertTo: "pdf", converter: "L"}')
RENDER_RESP=$(curl -sS -H "Content-Type: application/json" -d "$RENDER_BODY" "$CARBONE_URL/render/$TEMPLATE_ID")
RENDER_ID=$(echo "$RENDER_RESP" | jq -r '.data.renderId // empty')
if [[ -z "$RENDER_ID" ]]; then
  MOP_DATA_DIR="$MOP_DATA_DIR" "$ALLOC_SCRIPT" rollback "$ID"
  echo "Carbone render failed: $RENDER_RESP" >&2
  exit 1
fi

# Step 2: GET render result
HTTP=$(curl -sS -o "$OUT" -w "%{http_code}" "$CARBONE_URL/render/$RENDER_ID")
if [[ "$HTTP" != "200" ]]; then
  MOP_DATA_DIR="$MOP_DATA_DIR" "$ALLOC_SCRIPT" rollback "$ID"
  echo "Carbone GET HTTP $HTTP" >&2
  exit 1
fi

CONFIRM_PAYLOAD=$(echo "$JSON_WITH_ID" | jq --arg fn "$(basename "$OUT")" '. + {filename: $fn, sub_procs: ([.steps[]?.link_sp] | map(select(. != null)) | join(","))}')
MOP_DATA_DIR="$MOP_DATA_DIR" "$ALLOC_SCRIPT" confirm "$ID" "$CONFIRM_PAYLOAD"

echo "$ID → $OUT"
```

- [ ] **Step 3: Shellcheck via a rendered copy**

`shellcheck` cannot parse `.j2` templates directly (the `{{ ... }}` breaks bash syntax). Render a test copy with a dummy project_name substitution:

```bash
for f in roles/mop-templates/templates/alloc-and-append.sh.j2 \
         roles/mop-templates/templates/mop-render-html.j2 \
         roles/mop-templates/templates/mop-render-odt.j2; do
  sed 's|{{ project_name }}|javisi|g; s|{{ ansible_managed }}|MANAGED|g' "$f" \
    | shellcheck -s bash -
done
```
Expected: 0 errors (warnings OK).

- [ ] **Step 4: Commit**

```bash
git add roles/mop-templates/templates/mop-render-html.j2 roles/mop-templates/templates/mop-render-odt.j2
git commit -m "feat(mop): CLI wrapper templates mop-render-html.j2 + mop-render-odt.j2"
```

---

### Task 2.5: Write contacts.yml placeholder

**Files:**
- Modify: `roles/mop-templates/files/contacts.yml`

- [ ] **Step 1: Write placeholder**

```yaml
# contacts.yml — NOC escalation directory (placeholder — user fills)
sites:
  TH3: { address: "{{ À REMPLIR }}", coordinator: "{{ À REMPLIR }}" }
  TH2: { address: "{{ À REMPLIR }}", coordinator: "{{ À REMPLIR }}" }
  LF:  { address: "{{ À REMPLIR }}", coordinator: "{{ À REMPLIR }}" }

maintainers:
  ribbon_voice: { name: "{{ À REMPLIR }}", phone: "{{ À REMPLIR }}", email: "{{ À REMPLIR }}" }
  it_supervision: { name: "{{ À REMPLIR }}", phone: "{{ À REMPLIR }}", email: "{{ À REMPLIR }}" }

operators:
  voie_TH_A: "{{ À REMPLIR }}"
  voie_LF_A: "{{ À REMPLIR }}"
  oob_supervision: "{{ À REMPLIR }}"

email_templates:
  acknowledge: |
    Bonjour,
    Nous accusons réception de votre incident {{ incident.ticket }}...
  closure: |
    Bonjour,
    L'incident {{ incident.ticket }} est clos...
```

- [ ] **Step 2: Commit**

```bash
git add roles/mop-templates/files/contacts.yml
git commit -m "feat(mop): contacts.yml placeholder directory"
```

---

### Task 2.6: Wave 2 deploy + smoke test

- [ ] **Step 1: Redeploy mop-templates**

Run: `make deploy-role ROLE=mop-templates ENV=prod`
Expected: files copied, scripts have mode 0755.

- [ ] **Step 2: Verify scripts on Sese-AI**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 \
  'ls -la /opt/{{ project_name }}/scripts/mop/ /usr/local/bin/mop-render-* && head -1 /opt/{{ project_name }}/data/mop/index/mops-index.csv'
```

- [ ] **Step 3: Commit tag**

```bash
git tag -a mop-wave2 -m "MOP machinery Wave 2 complete"
```

---

## Wave 3 — Docker-stack Deploy + Workflows

### Task 3.1: First full docker-stack deploy

- [ ] **Step 1: Deploy docker-stack**

Run: `make deploy-role ROLE=docker-stack ENV=prod`
Expected: gotenberg, carbone, typebot-builder, typebot-viewer pulled and started.

- [ ] **Step 2: Verify containers up**

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@137.74.114.167 \
  'docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "gotenberg|carbone|typebot"'
```
Expected: 4 containers running with `Up` and `(healthy)` after start_period.

- [ ] **Step 3: Run Carbone template upload post-task**

Run: `source .venv/bin/activate && ansible-playbook playbooks/site.yml --tags carbone-template -e target_env=prod`
Expected: `template-id.txt` and `template-hash.txt` written in `/opt/{{ project_name }}/configs/carbone/`.

- [ ] **Step 4: Probe Gotenberg and Carbone from inside backend**

```bash
ssh ... 'docker exec vpai_n8n wget -qO- http://gotenberg:3000/health'
ssh ... 'docker exec vpai_n8n curl -sf http://carbone:4000/status'
```
Expected: both 200.

- [ ] **Step 5: Commit (if any template drift from ansible-managed)**

```bash
git status  # review any drift
```

---

### Task 3.2: Typebot first-login smoke test

- [ ] **Step 1: Verify Typebot builder over VPN**

On Tailscale-connected host: `curl -I https://mop-build.<domain>/`
Expected: HTTP 200.

- [ ] **Step 2: Log in to Typebot builder**

Visit `https://mop-build.<domain>/` in browser. Enter admin email. Check SMTP inbox for magic link.

Expected: magic link received within 30s, clicking it logs in.

**Fallback if SMTP fails:**
```bash
ssh ... 'docker exec -i vpai_postgresql psql -U postgres typebot' <<SQL
INSERT INTO "User" (id, name, email, "emailVerified", "createdAt")
VALUES (gen_random_uuid()::text, 'Admin', '<your-email>', now(), now());
SQL
```
(Exact table names depend on Typebot 3.16.1 schema; adjust with `\dt` first.)

---

### Task 3.3: Write n8n webhook workflow (render-only, for Typebot)

**Files:**
- Create: `scripts/n8n-workflows/mop-webhook-render-v1.json`

- [ ] **Step 1: Build the workflow in n8n UI**

Nodes:
1. **Webhook** — path `mop/render`, HTTP POST, response mode: `last node`
2. **Code node** (allocate) — `execSync('/scripts/mop/alloc-and-append.sh', ['allocate', JSON.stringify($json)])` → capture ID
3. **IF** — `$json.engine === 'gotenberg'`
4. **Branch A: Gotenberg**
   - Code node: render HTML from Jinja-like template literal (or via `execSync` calling `jinja2-cli`)
   - HTTP Request: POST multipart to `http://gotenberg:3000/forms/chromium/convert/html`
5. **Branch B: Carbone**
   - **Code node (Read Template ID)** — reads `/configs/carbone/template-id.txt` from the mounted volume (Task 1.6 Step 1 mounts `/opt/{{ project_name }}/configs/carbone:/configs/carbone:ro` into n8n). Logic:
     ```javascript
     const fs = require('fs');
     const templateId = fs.readFileSync('/configs/carbone/template-id.txt', 'utf8').trim();
     return [{ json: { ...$json, templateId } }];
     ```
   - HTTP Request POST: `http://carbone:4000/render/{{$node["Read Template ID"].json.templateId}}` — body is the consolidated JSON payload
   - HTTP Request GET: `http://carbone:4000/render/{{$json.data.renderId}}`
   - **Do NOT use `$env.CARBONE_TEMPLATE_ID`** — the template ID lives in a mounted file, not an environment variable. This avoids cross-role deploy ordering fragility (n8n does not need to be restarted when the Carbone template is re-uploaded).
6. **Merge** branches
7. **Write Binary File** → `/data/mop/pdf/{{id}}.pdf`
8. **Code node** (confirm) — `execSync('/scripts/mop/alloc-and-append.sh', ['confirm', id, JSON.stringify(payload)])`
9. **Set** node: build response `{ ok: true, url: "https://mop-dl.<domain>/{{id}}.pdf", id }`
10. **Respond to Webhook** with the JSON

Error branches: on any HTTP failure → Code node `execSync('alloc-and-append.sh', ['rollback', id])` → Telegram alert → respond with 500.

- [ ] **Step 2: Export JSON via n8n API or UI**

```bash
# Via API
curl -sS -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "https://mayi.<domain>/api/v1/workflows/<id>" \
  | jq '.data' > scripts/n8n-workflows/mop-webhook-render-v1.json
```

- [ ] **Step 3: Commit**

```bash
git add scripts/n8n-workflows/mop-webhook-render-v1.json
git commit -m "feat(mop): n8n webhook workflow for Typebot PDF render"
```

---

### Task 3.4: Build `mop-generator-v1` multi-step form workflow

**Superseded by:** `docs/superpowers/plans/2026-04-11-mop-workflow-n8n-multistep.md`
— focused plan with canonical JSON, clean-import protocol (publish:workflow), E2E harness.

**Status: COMPLETE** (2026-04-11)
- Workflow `CP5gJrn1e2zZbPxh` active on Sese-AI, 8 nodes, `workflow_history` published.
- Happy path (exec 11759): `MOP-2026-0016.pdf` 32 KB, `status=success`, `lastNode=Done (PDF)`.
- Error branch (exec 11761, Gotenberg stopped): `EAI_AGAIN gotenberg`, `lastNode=Done (Error)`.
- Key findings documented in `.planning/research/mop-gotenberg-n8n.md` (Addendum MOP2, P11-P15).

---

### Task 3.5: Build Typebot flow + export

**Files:**
- Create: `scripts/typebot/mop-generator-v1.json`

- [ ] **Step 1: Build in Typebot builder UI**

Flow:
1. Start
2. Text Input: ticket_id
3. Text Input: raw_email (multiline)
4. Choice Input: severity (minor|major|critical)
5. Choice Input: engine (gotenberg|carbone)
6. Choice Input: perimeter → Condition blocks branching per perimeter
7. Per-perimeter Text/Choice inputs
8. Set Variable: build consolidated JSON
9. HTTP Request: POST `http://n8n:5678/webhook/mop/render` with body from variable
10. Condition: response.ok == true
11. Text Bubble: `Votre MOP est prête : {{response.url}}`

- [ ] **Step 2: Export flow from UI**

UI → 3-dot menu → Export flow → save as `scripts/typebot/mop-generator-v1.json`

- [ ] **Step 3: Commit**

```bash
mkdir -p scripts/typebot
git add scripts/typebot/mop-generator-v1.json
git commit -m "feat(mop): Typebot MOP generator flow export"
```

---

## Wave 4 — CSV Index Bootstrap + Excel Macro

### Task 4.1: CSV bootstrap file

**Files:**
- Create: `scripts/mop/mops-index.csv`

- [ ] **Step 1: Create with header only**

```
id;title;keywords;severity;perimeter;filename;sub_procs;created_at
```

(Include UTF-8 BOM byte `\xef\xbb\xbf` at start.)

- [ ] **Step 2: Commit**

```bash
git add scripts/mop/mops-index.csv
git commit -m "feat(mop): CSV index bootstrap file with header"
```

---

### Task 4.2: Excel+VBA search workbook

**Files:**
- Create: `scripts/mop/mop-search.xlsm`

- [ ] **Step 1: Build in Excel**

Sheets:
- `index` — Power Query connected to the CSV (file path: `%USERPROFILE%\mop-index\mops-index.csv`)
- `recherche` — cell B2 = keyword input, button "Chercher" runs VBA macro

VBA macro (`Module1.bas`):
```vba
Sub SearchMOP()
    Dim keyword As String
    Dim idxSheet As Worksheet, resSheet As Worksheet
    Dim lastRow As Long, i As Long, resRow As Long

    keyword = LCase(Trim(Worksheets("recherche").Range("B2").Value))
    If keyword = "" Then
        MsgBox "Entrez un mot-clé en B2."
        Exit Sub
    End If

    Set idxSheet = Worksheets("index")
    Set resSheet = Worksheets("recherche")

    resSheet.Range("A5:H100").ClearContents
    lastRow = idxSheet.Cells(idxSheet.Rows.Count, 1).End(xlUp).Row
    resRow = 5

    For i = 2 To lastRow
        If InStr(1, LCase(idxSheet.Cells(i, 3).Value), keyword) > 0 _
           Or InStr(1, LCase(idxSheet.Cells(i, 2).Value), keyword) > 0 Then
            resSheet.Cells(resRow, 1).Value = idxSheet.Cells(i, 1).Value  ' id
            resSheet.Cells(resRow, 2).Value = idxSheet.Cells(i, 2).Value  ' title
            resSheet.Cells(resRow, 3).Value = idxSheet.Cells(i, 3).Value  ' keywords
            resSheet.Cells(resRow, 4).Value = idxSheet.Cells(i, 4).Value  ' severity
            resSheet.Cells(resRow, 5).Value = idxSheet.Cells(i, 6).Value  ' filename
            resSheet.Cells(resRow, 6).Formula = "=HYPERLINK(""" & idxSheet.Cells(i, 6).Value & """, ""Ouvrir"")"
            resRow = resRow + 1
        End If
    Next i

    MsgBox (resRow - 5) & " MOP trouvés."
End Sub
```

- [ ] **Step 2: Save as .xlsm (macro-enabled)**

- [ ] **Step 3: Commit**

```bash
git add scripts/mop/mop-search.xlsm
git commit -m "feat(mop): Excel search workbook with VBA macro"
```

---

## Wave 5 — E2E Tests + Deployment Audit

### Task 5.1: Run all 16 E2E tests from spec §7

- [ ] **Step 1: CLI Gotenberg test (#5)**

On Sese-AI via Tailscale:
```bash
ssh ... 'cat > /tmp/t.json <<EOF
{"title":"Test LOS TH2","keywords":["los","voie-th","th2"],"severity":"major","perimeter":"lien_optique_prod","incident":{"ticket":"TST-1","date":"2026-04-11","equipment":"Ribbon","site":"TH2","raw_email_subject":"x","raw_email_body":"y"},"steps":[{"n":1,"title":"s1","desc":"d1","link_sp":"SP-01"}],"rex":{"similar_cases_count":3,"root_causes":["a"],"pitfalls":["b"],"mean_resolution_time":"1h"},"escalation":{"primary_contact":"op1","fallback":"mx","coordinator_site_distant":"TH2"}}
EOF
mop-render-html /tmp/t.json -o /tmp/out.pdf && file /tmp/out.pdf'
```
Expected: `PDF document, version 1.x`

- [ ] **Step 2: CLI Carbone test (#6)**

Run same with `mop-render-odt`. Expected: PDF.

- [ ] **Step 3: Concurrency test (#7)**

```bash
ssh ... 'for i in $(seq 1 10); do (cat /tmp/t.json | jq ".incident.ticket=\"TST-$i\"" | mop-render-html -o /tmp/out-$i.pdf) & done; wait'
ssh ... 'awk -F\; "NR>1 {print \$1}" /opt/{{ project_name }}/data/mop/index/mops-index.csv | sort -u | wc -l'
```
Expected: 10+ unique IDs (possibly more if prior runs seeded data), all distinct.

- [ ] **Step 4: JSON malformed test (#8)**

```bash
ssh ... 'echo "not json" | mop-render-html -o /tmp/bad.pdf; echo "exit=$?"'
```
Expected: exit non-zero, no PDF created.

- [ ] **Step 5: Caddy ACL test (#16)**

From non-VPN host: `curl -I https://mop-dl.<domain>/` → 403
From VPN host: `curl -I https://mop-dl.<domain>/MOP-2026-0001.pdf` → 200

- [ ] **Step 6: ODT template re-upload test (#11)**

```bash
ssh ... 'cat /opt/{{ project_name }}/configs/carbone/template-hash.txt'
# Edit mop.odt locally, push via git, redeploy mop-templates role
# Run ansible with --tags carbone-template
# Verify hash changed
```

- [ ] **Step 7: Typebot SMTP fallback (#13)**

Done in Task 3.2.

- [ ] **Step 8: Excel search (#15)**

Copy `mop-search.xlsm` + CSV + PDFs to a Windows host. Open Excel, search "los", verify matching MOPs appear with working hyperlinks.

- [ ] **Step 9: Document results**

Create `docs/REX-MOP-DEPLOY-2026-04-11.md` with each test result (PASS/FAIL, notes).

- [ ] **Step 10: Commit REX**

```bash
git add docs/REX-MOP-DEPLOY-2026-04-11.md
git commit -m "docs(mop): REX deployment E2E test results"
```

---

### Task 5.2: Opus audit pass

- [ ] **Step 1: Re-read spec + plan + code diffs**

Review:
- `git log --oneline main~<n>..main` for all MOP-related commits
- Each role's `tasks/main.yml` for VPAI compliance (FQCN, changed_when, cap_drop, env_file pattern)
- docker-compose blocks for security (read_only, cap_add minimal, healthcheck present)
- Caddy routes for VPN-only snippet usage
- n8n workflow JSON for error handling completeness

- [ ] **Step 2: Produce audit report**

`docs/REX-MOP-AUDIT-2026-04-11.md` with a checklist of VPAI conventions verified and any deviations/technical debt flagged for followup.

- [ ] **Step 3: Commit audit**

```bash
git add docs/REX-MOP-AUDIT-2026-04-11.md
git commit -m "docs(mop): Opus audit pass + technical debt inventory"
```

- [ ] **Step 4: Tag release**

```bash
git tag -a mop-v1.0 -m "MOP machinery v1.0 — all waves + audit"
git push github-seko main --tags
```

---

## Appendix A — Relevant Skills

- `@superpowers:subagent-driven-development` — preferred execution approach (fresh subagent per task)
- `@superpowers:executing-plans` — fallback if subagents unavailable
- `@superpowers:test-driven-development` — Wave 2 Task 2.1 bats tests
- `@superpowers:root-cause-tracing` — when debugging failed E2E tests
- `@superpowers:writing-clearly-and-concisely` — REX reports in Task 5.1, 5.2

## Appendix B — Rollback Procedure

If any wave breaks production:

1. `git revert <commit-range>`
2. `make deploy-role ROLE=docker-stack ENV=prod` (reapplies previous template)
3. For emergencies: `ssh ... "cd /opt/${PROJECT_NAME:-javisi} && docker compose stop gotenberg carbone typebot-builder typebot-viewer"` (substitute the real `project_name` value from `inventory/group_vars/all/main.yml` — default is `javisi`)
4. Caddy routes auto-removed when the template re-renders.

## Appendix C — Post-deployment Housekeeping

- Add MOP runbook to `docs/RUNBOOK.md` with daily operation guidance
- Wire a `diun` watcher for gotenberg/carbone/typebot image updates
- Schedule weekly `rsync` of `/opt/{{ project_name }}/data/mop/pdf/` + CSV to user workstation (Waza) via Tailscale
- Document Phase 2 spec skeleton at `docs/superpowers/specs/2026-XX-XX-mop-email-ingest-design.md`
