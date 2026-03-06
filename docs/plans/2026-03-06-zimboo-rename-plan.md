# Zimboo Rename Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename Seko-Finance → Zimboo across the entire VPAI Ansible codebase, update Docker image to `ghcr.io/mobutoo/zimboo:v1.10.0`, change subdomain from `nzimbu` to `zimboo`, and create DNS record via OVH API.

**Architecture:** Atomic rename of role, variables, templates, Docker service, Caddy config, CI/CD, smoke tests, molecule tests, and documentation. Firefly III (`lola`) is untouched.

**Tech Stack:** Ansible, Docker Compose, Caddy, OVH API, GitHub Actions

**Design doc:** `docs/plans/2026-03-06-zimboo-rename-design.md`

---

## Task 1: Create DNS record via OVH API

**Files:**
- Read: `inventory/group_vars/all/secrets.yml` (vault — OVH API credentials)

**Step 1: Extract OVH credentials from vault**

```bash
source .venv/bin/activate
ansible-vault view inventory/group_vars/all/secrets.yml | grep -i ovh
```

Expected: OVH API keys (application_key, application_secret, consumer_key)

**Step 2: Create A record zimboo.ewutelo.cloud → 137.74.114.167**

```bash
# Using OVH API — zone = ewutelo.cloud
curl -X POST "https://eu.api.ovh.com/1.0/domain/zone/ewutelo.cloud/record" \
  -H "X-Ovh-Application: <APP_KEY>" \
  -H "X-Ovh-Timestamp: $(date +%s)" \
  -H "X-Ovh-Signature: <computed>" \
  -H "X-Ovh-Consumer: <CONSUMER_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"fieldType":"A","subDomain":"zimboo","target":"137.74.114.167","ttl":300}'
```

Alternative: use Python `ovh` library if available.

**Step 3: Refresh DNS zone**

```bash
curl -X POST "https://eu.api.ovh.com/1.0/domain/zone/ewutelo.cloud/refresh" \
  -H "X-Ovh-Application: <APP_KEY>" \
  -H "X-Ovh-Timestamp: $(date +%s)" \
  -H "X-Ovh-Signature: <computed>" \
  -H "X-Ovh-Consumer: <CONSUMER_KEY>"
```

**Step 4: Verify DNS propagation**

```bash
dig zimboo.ewutelo.cloud +short
```

Expected: `137.74.114.167`

**Step 5: Commit**

No code change — DNS is external.

---

## Task 2: Rename Ansible role directory

**Step 1: Rename roles/seko-finance/ → roles/zimboo/**

```bash
cd /home/asus/seko/VPAI
git mv roles/seko-finance roles/zimboo
```

**Step 2: Verify**

```bash
ls roles/zimboo/
```

Expected: `defaults/ tasks/ templates/ handlers/ meta/ molecule/`

---

## Task 3: Update role defaults/main.yml

**Files:**
- Modify: `roles/zimboo/defaults/main.yml` (all 16 lines)

**Step 1: Rewrite defaults**

Replace entire content with:

```yaml
---
# zimboo — defaults
# Zimboo Dashboard: Next.js financial cockpit connected to Firefly III + LiteLLM.
# Runs as Docker container (pre-built image from GHCR).

zimboo_config_dir: "/opt/{{ project_name }}/configs/zimboo"

# Internal web port (exposed via Caddy on zimboo.<domain>)
zimboo_port: 3000

# LLM model for chat feature (via LiteLLM proxy)
zimboo_llm_model: "deepseek-v3-free"

# Subdomain (VPN-only, served by Caddy)
# Overridden by zimboo_subdomain in inventory/group_vars/all/main.yml
zimboo_subdomain: "zimboo"
```

---

## Task 4: Update role tasks/main.yml

**Files:**
- Modify: `roles/zimboo/tasks/main.yml` (all 23 lines)

**Step 1: Rewrite tasks**

```yaml
---
# zimboo — tasks
# Zimboo Dashboard (Next.js — pre-built Docker image from GHCR)

- name: Create Zimboo config directory
  ansible.builtin.file:
    path: "{{ zimboo_config_dir }}"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true

- name: Deploy Zimboo environment file
  ansible.builtin.template:
    src: zimboo.env.j2
    dest: "{{ zimboo_config_dir }}/zimboo.env"
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0600"
  become: true
  notify: Restart zimboo stack
```

---

## Task 5: Rename and update env template

**Files:**
- Rename: `roles/zimboo/templates/seko-finance.env.j2` → `roles/zimboo/templates/zimboo.env.j2`

**Step 1: Rename file**

```bash
git mv roles/zimboo/templates/seko-finance.env.j2 roles/zimboo/templates/zimboo.env.j2
```

**Step 2: Update content**

```
# {{ ansible_managed }}
# Zimboo Dashboard environment configuration

NODE_ENV=production

# Firefly III API (internal Docker network)
FIREFLY_URL=http://firefly-iii:{{ firefly_web_port | default(8080) }}
FIREFLY_PAT={{ zimboo_firefly_pat }}

# LiteLLM proxy (internal Docker network — chat IA feature)
LITELLM_URL=http://litellm:4000
LITELLM_KEY={{ litellm_master_key }}
LLM_MODEL={{ zimboo_llm_model }}

# App
NEXT_PUBLIC_APP_NAME=Zimboo
NEXT_PUBLIC_CURRENCY=EUR

# Timezone
TZ={{ timezone }}
```

---

## Task 6: Update handlers/main.yml

**Files:**
- Modify: `roles/zimboo/handlers/main.yml` (all 28 lines)

**Step 1: Rewrite handlers**

```yaml
---
# zimboo — handlers
# Pattern: grep-guard + state: present + recreate: always (env_file reload).

- name: Check zimboo service is in compose file
  ansible.builtin.command:
    cmd: grep -q "zimboo" /opt/{{ project_name }}/docker-compose.yml
  register: _zimboo_in_compose
  failed_when: false
  changed_when: false
  listen: Restart zimboo stack

- name: Restart zimboo container
  community.docker.docker_compose_v2:
    project_src: "/opt/{{ project_name }}"
    files:
      - docker-compose.yml
    services:
      - zimboo
    state: present
    recreate: always
  become: true
  when:
    - not ansible_check_mode
    - _zimboo_in_compose.rc | default(1) == 0
    - not (common_molecule_mode | default(false))
  listen: Restart zimboo stack
```

---

## Task 7: Update meta/main.yml

**Files:**
- Modify: `roles/zimboo/meta/main.yml` (all 16 lines)

**Step 1: Rewrite meta**

```yaml
---
# zimboo — role metadata

galaxy_info:
  role_name: zimboo
  author: Mobutoo
  description: Deploy Zimboo Dashboard (Next.js financial cockpit)
  license: AGPL-3.0
  min_ansible_version: "2.16"
  platforms:
    - name: Debian
      versions:
        - bookworm
        - trixie

dependencies: []
```

---

## Task 8: Update molecule tests

**Files:**
- Modify: `roles/zimboo/molecule/default/converge.yml`

**Step 1: Rewrite converge.yml**

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
    zimboo_subdomain: zimboo
    zimboo_firefly_pat: "test_pat_token"
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
    - role: zimboo
```

**Step 2: Commit role rename**

```bash
git add roles/zimboo/
git commit -m "refactor: rename role seko-finance → zimboo"
```

---

## Task 9: Update inventory/group_vars/all/versions.yml

**Files:**
- Modify: `inventory/group_vars/all/versions.yml:48-50`

**Step 1: Replace seko_finance_image**

Old (lines 48-50):
```yaml
# --- Seko-Finance Dashboard (Next.js financial cockpit) ---
# TODO: Pinner sur SHA digest après premier deploy validé
seko_finance_image: "ghcr.io/mobutoo/seko-finance:latest"
```

New:
```yaml
# --- Zimboo Dashboard (Next.js financial cockpit) ---
zimboo_image: "ghcr.io/mobutoo/zimboo:v1.10.0"
```

---

## Task 10: Update inventory/group_vars/all/main.yml

**Files:**
- Modify: `inventory/group_vars/all/main.yml:133-134` and `:222-224`

**Step 1: Replace seko_finance_firefly_pat (line 133-134)**

Old:
```yaml
# Seko-Finance Dashboard (financial cockpit — connects to Firefly III + LiteLLM)
seko_finance_firefly_pat: "{{ vault_firefly_pat | default('') }}"
```

New:
```yaml
# Zimboo Dashboard (financial cockpit — connects to Firefly III + LiteLLM)
zimboo_firefly_pat: "{{ vault_firefly_pat | default('') }}"
```

**Step 2: Replace seko_finance_subdomain (line 222-224)**

Old:
```yaml
# Firefly III + Seko-Finance (personal finance)
firefly_subdomain: "lola"
seko_finance_subdomain: "nzimbu"
```

New:
```yaml
# Firefly III + Zimboo (personal finance)
firefly_subdomain: "lola"
zimboo_subdomain: "zimboo"
```

---

## Task 11: Update inventory/group_vars/all/docker.yml

**Files:**
- Modify: `inventory/group_vars/all/docker.yml:95-98`

**Step 1: Replace seko_finance resource limits**

Old:
```yaml
# Seko-Finance Dashboard (Next.js cockpit)
seko_finance_memory_limit: "{{ '384M' if target_env == 'prod' else '256M' }}"
seko_finance_memory_reservation: "128M"
seko_finance_cpu_limit: "0.5"
```

New:
```yaml
# Zimboo Dashboard (Next.js cockpit)
zimboo_memory_limit: "{{ '384M' if target_env == 'prod' else '256M' }}"
zimboo_memory_reservation: "128M"
zimboo_cpu_limit: "0.5"
```

**Step 2: Commit inventory changes**

```bash
git add inventory/group_vars/all/versions.yml inventory/group_vars/all/main.yml inventory/group_vars/all/docker.yml
git commit -m "refactor: rename seko_finance → zimboo variables in inventory"
```

---

## Task 12: Update Docker Compose template

**Files:**
- Modify: `roles/docker-stack/templates/docker-compose.yml.j2:184-209`

**Step 1: Replace seko-finance service block**

Old (lines 184-209):
```yaml
  seko-finance:
    image: {{ seko_finance_image }}
    container_name: {{ project_name }}_seko_finance
    ...
    env_file:
      - /opt/{{ project_name }}/configs/seko-finance/seko-finance.env
    ...
        memory: {{ seko_finance_memory_limit }}
        cpus: "{{ seko_finance_cpu_limit }}"
      reservations:
        memory: {{ seko_finance_memory_reservation }}
```

New:
```yaml
  zimboo:
    image: {{ zimboo_image }}
    container_name: {{ project_name }}_zimboo
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    env_file:
      - /opt/{{ project_name }}/configs/zimboo/zimboo.env
    networks:
      - backend
      - frontend
      - egress
    deploy:
      resources:
        limits:
          memory: {{ zimboo_memory_limit }}
          cpus: "{{ zimboo_cpu_limit }}"
        reservations:
          memory: {{ zimboo_memory_reservation }}
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

---

## Task 13: Update Caddy defaults

**Files:**
- Modify: `roles/caddy/defaults/main.yml:15`

**Step 1: Replace caddy_seko_finance_domain**

Old:
```yaml
caddy_seko_finance_domain: "{{ seko_finance_subdomain | default('nzimbu') }}.{{ domain_name }}"
```

New:
```yaml
caddy_zimboo_domain: "{{ zimboo_subdomain | default('zimboo') }}.{{ domain_name }}"
```

---

## Task 14: Update Caddyfile template

**Files:**
- Modify: `roles/caddy/templates/Caddyfile.j2:266-281`

**Step 1: Replace Seko-Finance section**

Old (lines 266-281):
```
# === Seko-Finance Dashboard (financial cockpit) — nzimbu.<domain> ===
{% if seko_finance_subdomain | default('') | length > 0 %}
{{ caddy_seko_finance_domain }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy seko-finance:{{ seko_finance_port | default(3000) }}

    header {
        ...
    }
}
{% endif %}
```

New:
```
# === Zimboo Dashboard (financial cockpit) — zimboo.<domain> ===
{% if zimboo_subdomain | default('') | length > 0 %}
{{ caddy_zimboo_domain }} {
    import vpn_only
    import vpn_error_page

    reverse_proxy zimboo:{{ zimboo_port | default(3000) }}

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }
}
{% endif %}
```

**Step 2: Commit Docker + Caddy changes**

```bash
git add roles/docker-stack/templates/docker-compose.yml.j2 roles/caddy/defaults/main.yml roles/caddy/templates/Caddyfile.j2
git commit -m "refactor: rename seko-finance → zimboo in Docker Compose and Caddy"
```

---

## Task 15: Update playbooks/site.yml

**Files:**
- Modify: `playbooks/site.yml:85-86`

**Step 1: Replace role reference**

Old:
```yaml
    - role: seko-finance
      tags: [seko-finance, phase3]
```

New:
```yaml
    - role: zimboo
      tags: [zimboo, phase3]
```

---

## Task 16: Update CI/CD workflow

**Files:**
- Modify: `.github/workflows/integration.yml:168, 316-317, 383`

**Step 1: Replace "nzimbu" with "zimboo" in DNS validation loop (line 168)**

Old:
```bash
for sub in "" "mayi" "llm" "tala" "qd" "hq" "javisi" "palais" "work" "nzimbu" "lola"; do
```

New:
```bash
for sub in "" "mayi" "llm" "tala" "qd" "hq" "javisi" "palais" "work" "zimboo" "lola"; do
```

**Step 2: Replace in TLS pre-warm (line 316-317)**

Old:
```bash
# hq(nocodb), javisi(openclaw/admin), palais, nzimbu(seko-finance), lola(firefly), work(plane)
for sub in "" "mayi" "llm" "tala" "qd" "hq" "javisi" "palais" "work" "nzimbu" "lola"; do
```

New:
```bash
# hq(nocodb), javisi(openclaw/admin), palais, zimboo(zimboo), lola(firefly), work(plane)
for sub in "" "mayi" "llm" "tala" "qd" "hq" "javisi" "palais" "work" "zimboo" "lola"; do
```

**Step 3: Replace in /etc/hosts line (line 383)**

Old:
```bash
HOSTS_LINE="127.0.0.1 ${D} mayi.${D} llm.${D} tala.${D} qd.${D} hq.${D} javisi.${D} palais.${D} work.${D} nzimbu.${D} lola.${D}"
```

New:
```bash
HOSTS_LINE="127.0.0.1 ${D} mayi.${D} llm.${D} tala.${D} qd.${D} hq.${D} javisi.${D} palais.${D} work.${D} zimboo.${D} lola.${D}"
```

---

## Task 17: Update smoke tests

**Files:**
- Modify: `roles/smoke-tests/templates/smoke-test.sh.j2:56-57, 175-178, 211-212, 231-232`

**Step 1: Replace all seko_finance references**

Line 56-57 — DNS resolve:
```
{% if zimboo_subdomain | default('') | length > 0 %}
  CURL_VPN_OPTS="${CURL_VPN_OPTS} --resolve {{ zimboo_subdomain }}.{{ domain_name }}:443:${TAILSCALE_IP}"
```

Line 175-178 — Health check:
```
{% if zimboo_subdomain | default('') | length > 0 %}
# shellcheck disable=SC2086
ZIMBOO_URL="https://{{ zimboo_subdomain }}.{{ domain_name }}"
check_http "Zimboo health" "${ZIMBOO_URL}/api/health" "200"
```

Line 211-212 — Container check:
```
{% if zimboo_subdomain | default('') | length > 0 %}
check_container "Zimboo" "zimboo"
```

Line 231-232 — Container health check:
```
{% if zimboo_subdomain | default('') | length > 0 %}
check_container_health "Zimboo" "zimboo"
```

---

## Task 18: Update VPN DNS defaults

**Files:**
- Modify: `roles/vpn-dns/defaults/main.yml:86-89`

**Step 1: Replace seko_finance_subdomain reference**

Old:
```yaml
    ([{"name": seko_finance_subdomain ~ "." ~ domain_name, "type": "A",
       "value": _vpn_dns_vps_ts_ip}]
     if (seko_finance_subdomain | default('')) | length > 0
     else [])
```

New:
```yaml
    ([{"name": zimboo_subdomain ~ "." ~ domain_name, "type": "A",
       "value": _vpn_dns_vps_ts_ip}]
     if (zimboo_subdomain | default('')) | length > 0
     else [])
```

**Step 2: Commit playbook + CI/CD + smoke tests + VPN DNS**

```bash
git add playbooks/site.yml .github/workflows/integration.yml roles/smoke-tests/ roles/vpn-dns/
git commit -m "refactor: rename seko-finance → zimboo in playbook, CI/CD, smoke tests, VPN DNS"
```

---

## Task 19: Update ALL molecule converge.yml files (25 files)

**Files (all at the same line pattern `seko_finance_subdomain: nzimbu`):**
- `roles/redis/molecule/default/converge.yml:104`
- `roles/n8n-provision/molecule/default/converge.yml:104`
- `roles/diun/molecule/default/converge.yml:104`
- `roles/vpn-dns/molecule/default/converge.yml:104`
- `roles/plane-provision/molecule/default/converge.yml:104`
- `roles/openclaw/molecule/default/converge.yml:104`
- `roles/backup-config/molecule/default/converge.yml:104`
- `roles/n8n/molecule/default/converge.yml:104`
- `roles/common/molecule/default/converge.yml:104`
- `roles/litellm/molecule/default/converge.yml:104`
- `roles/docker/molecule/default/converge.yml:104`
- `roles/monitoring/molecule/default/converge.yml:104`
- `roles/docker-stack/molecule/default/converge.yml:104`
- `roles/uptime-config/molecule/default/converge.yml:104`
- `roles/nocodb/molecule/default/converge.yml:104`
- `roles/plane/molecule/default/converge.yml:104`
- `roles/qdrant/molecule/default/converge.yml:104`
- `roles/headscale-node/molecule/default/converge.yml:104`
- `roles/obsidian-collector/molecule/default/converge.yml:104`
- `roles/palais/molecule/default/converge.yml:105`
- `roles/caddy/molecule/default/converge.yml:104`
- `roles/smoke-tests/molecule/default/converge.yml:104`
- `roles/postgresql/molecule/default/converge.yml:104`
- `roles/hardening/molecule/default/converge.yml:104`

**Step 1: Use sed to batch-replace all converge.yml files**

```bash
find roles/ -path "*/molecule/default/converge.yml" -exec sed -i 's/seko_finance_subdomain: nzimbu/zimboo_subdomain: zimboo/g' {} +
```

**Step 2: Verify no remaining references**

```bash
grep -r "seko_finance_subdomain" roles/*/molecule/
```

Expected: No output

**Step 3: Commit**

```bash
git add roles/*/molecule/
git commit -m "refactor: rename seko_finance_subdomain → zimboo_subdomain in all molecule tests"
```

---

## Task 20: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update Stack table**

Old:
```
| Applications | n8n 2.7.3, OpenClaw (YYYY.M.DD), LiteLLM v1.81.3-stable, NocoDB 0.301.2, Firefly III v6.5.3, Seko-Finance |
```

New:
```
| Applications | n8n 2.7.3, OpenClaw (YYYY.M.DD), LiteLLM v1.81.3-stable, NocoDB 0.301.2, Firefly III v6.5.3, Zimboo v1.10.0 |
```

**Step 2: Update CI/CD section**

Old:
```
- **Firefly III** : sous-domaine `lola`, Redis db2/db3, `TRUSTED_PROXIES=**` requis derrière Caddy
```

Add after it:
```
- **Zimboo** : sous-domaine `zimboo`, image `ghcr.io/mobutoo/zimboo:v1.10.0`
```

**Step 3: Update repo structure**

Replace `Seko-Finance` references with `Zimboo` in the structure tree and stack descriptions.

**Step 4: Update subdomain references**

Replace `nzimbu(seko-finance)` with `zimboo` in CI/CD piège section.

---

## Task 21: Update documentation files

**Files:**
- Modify: `docs/TROUBLESHOOTING.md` — Seko-Finance references
- Modify: `docs/ARCHITECTURE.md` — if references exist
- Modify: `docs/RUNBOOK.md` — if references exist

**Step 1: Search and replace Seko-Finance → Zimboo, seko-finance → zimboo, nzimbu → zimboo in docs**

```bash
grep -rl "seko.finance\|seko_finance\|Seko-Finance\|nzimbu" docs/ --include="*.md" | head -20
```

Replace in each file:
- `Seko-Finance` → `Zimboo`
- `seko-finance` → `zimboo`
- `seko_finance` → `zimboo`
- `nzimbu` → `zimboo` (only in subdomain context, not in plan history docs)

**Note:** Do NOT modify historical docs like `docs/plans/2026-03-04-sure-to-firefly-*.md` — they're historical records.

**Step 2: Commit docs**

```bash
git add CLAUDE.md docs/
git commit -m "docs: rename Seko-Finance → Zimboo in documentation"
```

---

## Task 22: Run linting to verify

**Step 1: Activate venv and lint**

```bash
source .venv/bin/activate && make lint
```

Expected: No errors (warnings OK)

**Step 2: Run grep verification — no remaining seko_finance in functional code**

```bash
# Should return ONLY historical docs and plan files
grep -r "seko_finance\|seko-finance\|Seko-Finance" . \
  --include="*.yml" --include="*.j2" --include="*.sh" --include="*.yaml" \
  | grep -v "docs/plans/" | grep -v ".planning/"
```

Expected: No output (all functional references renamed)

**Step 3: Fix any remaining references found**

If grep finds remaining references, update those files.

---

## Task 23: Final commit and summary

**Step 1: Verify git status**

```bash
git status
git diff --stat HEAD~5
```

**Step 2: Tag for reference**

```bash
git log --oneline -6
```

Expected: Clean series of refactor commits renaming seko-finance → zimboo.

---

## Summary of all changes

| Category | Old | New |
|----------|-----|-----|
| Role directory | `roles/seko-finance/` | `roles/zimboo/` |
| Variable prefix | `seko_finance_*` | `zimboo_*` |
| Docker image | `ghcr.io/mobutoo/seko-finance:latest` | `ghcr.io/mobutoo/zimboo:v1.10.0` |
| Docker service | `seko-finance` | `zimboo` |
| Container name | `javisi_seko_finance` | `javisi_zimboo` |
| Subdomain | `nzimbu.ewutelo.cloud` | `zimboo.ewutelo.cloud` |
| Caddy variable | `caddy_seko_finance_domain` | `caddy_zimboo_domain` |
| App name (env) | `NEXT_PUBLIC_APP_NAME=Seko-Finance` | `NEXT_PUBLIC_APP_NAME=Zimboo` |
| Playbook tag | `seko-finance` | `zimboo` |
| Molecule var | `seko_finance_subdomain: nzimbu` | `zimboo_subdomain: zimboo` |
| DNS A record | (none for nzimbu) | `zimboo.ewutelo.cloud → 137.74.114.167` |

**Files modified:** ~35 functional files + 25 molecule converge.yml = ~60 files
