# Handoff Sonnet 4.6 — Workstation Pi + Prod Apps

> **Date** : 2026-02-18
> **De** : Session Opus (sessions 1-9)
> **Pour** : Sonnet 4.6 — creation des roles et playbooks pendant le flash du Pi
> **Etat** : Le Raspberry Pi 5 est en cours de flash (Ubuntu Server 24.04 LTS). Tout ce qui ne necessite PAS le Pi physique peut etre fait maintenant.

---

## 1. Contexte global

Le projet **VPAI** est un monorepo Ansible qui deploie une stack IA auto-hebergee sur plusieurs serveurs. L'infrastructure actuelle :

| Serveur | Provider | IP Tailscale | Role | Etat |
|---------|----------|-------------|------|------|
| **Sese-AI** | OVH VPS 8GB | 100.64.0.X | OpenClaw, LiteLLM, n8n, PG, Redis, Qdrant, Grafana, monitoring | **Operationnel** |
| **Seko-VPN** | Ionos | IP Headscale server | Headscale hub, webhook relay, Zerobyte backup | **Operationnel** |
| **Workstation Pi** | RPi5 16GB local | A enregistrer | Mission Control, OpenCode, Claude Code CLI | **A deployer** |
| **Prod Apps** | Hetzner CX22 | A provisionner | Publication SaaS/sites | **A provisionner** |

Architecture mesh VPN : tous les serveurs communiquent via Headscale/Tailscale (100.64.0.0/10). Les admin UIs sont VPN-only (Caddy ACL).

---

## 2. Ce que tu PEUX faire maintenant (pas bloque par le Pi)

### 2.1 Creer les roles Ansible

#### Role `workstation-common`

**But** : Setup de base du Pi (equivalent du role `common` mais adapte Ubuntu Server 24.04 + ARM64).

```
roles/workstation-common/
  tasks/main.yml
  defaults/main.yml
  handlers/main.yml
  templates/
    daemon.json.j2       # Docker daemon config (adapte Pi)
```

**`defaults/main.yml`** :
```yaml
---
# workstation-common — defaults

# Paquets de base pour le workstation Pi
workstation_packages:
  - curl
  - wget
  - jq
  - gnupg
  - ca-certificates
  - python3-pip
  - unzip
  - htop
  - ncdu
  - tmux                # OBLIGATOIRE (demande utilisateur)
  - lsb-release
  - net-tools
  - rsync
  - git
  - build-essential     # Pour npm native modules ARM64
  - nodejs              # Pour Mission Control + OpenCode
  - npm

workstation_hostname: "workstation-pi"
workstation_user: "{{ workstation_pi_user | default('pi') }}"
workstation_locale: "{{ locale }}"
workstation_timezone: "{{ timezone }}"

# Docker config Pi (pas de swap limit, ARM64)
workstation_docker_log_max_size: "10m"
workstation_docker_log_max_file: "3"

# Repertoire projets (SSD 256 Go)
workstation_projects_dir: "/home/{{ workstation_user }}/projects"
workstation_base_dir: "/opt/workstation"
```

**`tasks/main.yml`** — etapes cles :
1. Set hostname
2. Configure locale + timezone
3. Install paquets de base (dont tmux, git, build-essential)
4. Install Docker CE ARM64 (via role docker existant OU apt.docker.com)
5. Install Node.js 22 LTS (via NodeSource)
6. Creer arborescence `/opt/workstation/` (configs, data, logs)
7. Creer `/home/<user>/projects/` (repos git, workspace OpenCode)
8. Configurer sysctl (vm.swappiness=10)
9. UFW : deny all + allow Tailscale CIDR (100.64.0.0/10) + allow LAN (192.168.0.0/16)

**IMPORTANT** : Le Pi n'a PAS de SSH public. Tout passe par Tailscale ou le LAN local.

#### Role `mission-control`

**But** : Deployer Mission Control (Next.js 14 + SQLite).

Repo source : `https://github.com/crshdn/mission-control`

```
roles/mission-control/
  tasks/main.yml
  defaults/main.yml
  templates/
    mission-control.env.j2
    mission-control.service.j2   # systemd unit
```

**`defaults/main.yml`** :
```yaml
---
# mission-control — defaults

mc_version: "latest"  # A pinner apres premier test
mc_port: 4000
mc_install_dir: "/opt/workstation/mission-control"
mc_data_dir: "/opt/workstation/data/mission-control"

# OpenClaw Gateway connection (via Tailscale mesh)
mc_openclaw_gateway_url: "wss://{{ admin_subdomain }}.{{ domain_name }}"
mc_openclaw_gateway_token: "{{ openclaw_gateway_token }}"

# SQLite DB path
mc_database_path: "{{ mc_data_dir }}/mission-control.db"
```

**`templates/mission-control.env.j2`** :
```
PORT={{ mc_port }}
OPENCLAW_GATEWAY_URL={{ mc_openclaw_gateway_url }}
OPENCLAW_GATEWAY_TOKEN={{ mc_openclaw_gateway_token }}
DATABASE_URL=file:{{ mc_database_path }}
NODE_ENV=production
```

**`tasks/main.yml`** — etapes cles :
1. Clone le repo Mission Control
2. `npm ci --omit=dev` + `npm run build` (standalone Next.js)
3. Creer repertoire data + SQLite
4. Template `.env` et service systemd
5. Enable + start service
6. Healthcheck : `curl http://localhost:{{ mc_port }}/api/health`

#### Role `opencode`

**But** : Deployer OpenCode server (terminal coding agent, headless HTTP API).

Repo source : `https://github.com/anomalyco/opencode`

```
roles/opencode/
  tasks/main.yml
  defaults/main.yml
  templates/
    opencode.json.j2     # Config → LiteLLM provider
    opencode.service.j2  # systemd unit
```

**`defaults/main.yml`** :
```yaml
---
# opencode — defaults

opencode_port: 3456
opencode_install_dir: "/opt/workstation/opencode"
opencode_workspace_dir: "/home/{{ workstation_pi_user | default('pi') }}/projects"

# LiteLLM proxy (accessible via Tailscale mesh)
opencode_litellm_base_url: "https://{{ litellm_subdomain }}.{{ domain_name }}/v1"
opencode_litellm_api_key: "{{ litellm_master_key }}"
opencode_default_model: "claude-sonnet"
```

**`tasks/main.yml`** — etapes cles :
1. Install OpenCode (npm global ou binaire ARM64 si disponible)
2. Creer workspace directory
3. Template opencode.json (provider = LiteLLM)
4. Service systemd : `opencode serve --port 3456`
5. Healthcheck : `curl http://localhost:3456/api/health`

#### Role `workstation-caddy`

**But** : Caddy local sur le Pi comme reverse proxy pour MC + OpenCode. TLS via Let's Encrypt (pas DNS-01 ici — le Pi est accessible via Split DNS Tailscale).

```
roles/workstation-caddy/
  tasks/main.yml
  defaults/main.yml
  templates/
    Caddyfile-workstation.j2
```

**`defaults/main.yml`** :
```yaml
---
# workstation-caddy — defaults

workstation_caddy_config_dir: "/opt/workstation/configs/caddy"
workstation_caddy_data_dir: "/opt/workstation/data/caddy"

# Subdomains pour le Pi (resolus via Split DNS Tailscale)
workstation_mc_domain: "mc.{{ domain_name }}"
workstation_oc_domain: "oc.{{ domain_name }}"
```

**`templates/Caddyfile-workstation.j2`** :

```caddyfile
{
    admin localhost:2019
    servers {
        trusted_proxies static private_ranges
    }
}

# Mission Control
{{ workstation_mc_domain }} {
    reverse_proxy localhost:{{ mc_port | default(4000) }}

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        -Server
    }
}

# OpenCode Server
{{ workstation_oc_domain }} {
    reverse_proxy localhost:{{ opencode_port | default(3456) }}

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        -Server
    }
}
```

**NOTE CRITIQUE** : Pas besoin de snippet `vpn_only` sur le Pi car le Pi est sur le LAN local + Tailscale. Pas de port public. UFW deny all sauf Tailscale CIDR. Caddy ici sert juste de reverse proxy TLS.

**NOTE TLS** : Caddy sur le Pi peut utiliser ACME DNS-01 (memes credentials OVH) pour obtenir les certificats TLS pour `mc.<domain>` et `oc.<domain>`. Les domaines sont resolus via Split DNS Tailscale vers l'IP Tailscale du Pi → le trafic HTTPS transite par le mesh VPN → Caddy sert le contenu. Alternative : TLS interne (Caddy local trust).

### 2.2 Creer le playbook workstation

**`playbooks/workstation.yml`** :

```yaml
---
# playbooks/workstation.yml — Deploiement Workstation Pi
#
# Usage:
#   ansible-playbook playbooks/workstation.yml
#   ansible-playbook playbooks/workstation.yml --tags "mission-control"

- name: Deploy Workstation
  hosts: workstation
  gather_facts: true

  pre_tasks:
    - name: Display deployment info
      ansible.builtin.debug:
        msg: |
          ========================================
          Workstation: {{ inventory_hostname }}
          Date: {{ ansible_facts['date_time']['iso8601'] }}
          ========================================
      tags: [always]

    - name: Verify ARM64 architecture
      ansible.builtin.assert:
        that:
          - ansible_facts['architecture'] == 'aarch64'
        fail_msg: "This playbook is for ARM64 (Raspberry Pi). Current: {{ ansible_facts['architecture'] }}"
      tags: [always]

  roles:
    - role: workstation-common
      tags: [workstation-common]
    - role: mission-control
      tags: [mission-control]
    - role: opencode
      tags: [opencode]
    - role: workstation-caddy
      tags: [workstation-caddy]
```

### 2.3 Creer le playbook Hetzner provisioning

**`playbooks/provision-hetzner.yml`** :

```yaml
---
# playbooks/provision-hetzner.yml — Provisioning automatique CX22
# Cree un serveur Hetzner Cloud via l'API hcloud
#
# Prerequis :
#   pip install hcloud
#   ansible-galaxy collection install hetzner.hcloud
#   vault: vault_hetzner_api_token
#
# Usage:
#   ansible-playbook playbooks/provision-hetzner.yml

- name: Provision Hetzner CX22
  hosts: localhost
  connection: local
  gather_facts: false

  vars:
    hetzner_api_token: "{{ vault_hetzner_api_token }}"
    server_name: "{{ app_prod_hostname | default('app-prod-01') }}"
    server_type: "cx22"
    server_location: "{{ app_prod_location | default('fsn1') }}"
    server_image: "ubuntu-24.04"
    ssh_key_name: "{{ app_prod_ssh_key_name | default('vpai-deploy') }}"

  tasks:
    - name: Ensure SSH key is registered in Hetzner
      hetzner.hcloud.ssh_key:
        api_token: "{{ hetzner_api_token }}"
        name: "{{ ssh_key_name }}"
        public_key: "{{ lookup('file', '~/.ssh/seko-vpn-deploy.pub') }}"
        state: present

    - name: Create CX22 server
      hetzner.hcloud.server:
        api_token: "{{ hetzner_api_token }}"
        name: "{{ server_name }}"
        server_type: "{{ server_type }}"
        location: "{{ server_location }}"
        image: "{{ server_image }}"
        ssh_keys:
          - "{{ ssh_key_name }}"
        state: present
      register: hetzner_server

    - name: Display server info
      ansible.builtin.debug:
        msg: |
          ========================================
          Server: {{ server_name }}
          IP: {{ hetzner_server.hcloud_server.ipv4_address }}
          Status: {{ hetzner_server.hcloud_server.status }}
          ========================================

    - name: Wait for SSH
      ansible.builtin.wait_for:
        host: "{{ hetzner_server.hcloud_server.ipv4_address }}"
        port: 22
        delay: 10
        timeout: 300
```

### 2.4 Mettre a jour `inventory/hosts.yml`

Ajouter les groupes `workstation` et `app_prod` :

```yaml
---
all:
  children:
    prod:
      hosts:
        prod-server:
          ansible_host: "{{ prod_ip }}"
          ansible_port: "{{ ansible_port_override | default(prod_ssh_port) }}"
          ansible_user: "{{ prod_user }}"
          target_env: "prod"
          prod_ssh_port_target: "{{ prod_ssh_port }}"

    preprod:
      hosts:
        preprod-server:
          ansible_host: "{{ preprod_ip | default('127.0.0.1') }}"
          ansible_port: 22
          ansible_user: "root"
          target_env: "preprod"

    vpn:
      hosts:
        vpn-server:
          ansible_host: "{{ vpn_headscale_ip }}"
          ansible_port: 22
          ansible_user: "{{ prod_user }}"
          target_env: "vpn"

    workstation:
      hosts:
        workstation-pi:
          ansible_host: "{{ workstation_pi_ip | default('127.0.0.1') }}"
          ansible_port: 22
          ansible_user: "{{ workstation_pi_user | default('pi') }}"
          target_env: "workstation"

    app_prod:
      hosts:
        app-prod-server:
          ansible_host: "{{ app_prod_ip | default('127.0.0.1') }}"
          ansible_port: 22
          ansible_user: "root"
          target_env: "app_prod"

  vars:
    ansible_python_interpreter: /usr/bin/python3
```

### 2.5 Ajouter les variables dans `main.yml`

Ajouter a la fin de `inventory/group_vars/all/main.yml` :

```yaml
# --- Workstation Pi (RPi5 16GB) ---
workstation_pi_hostname: "workstation-pi"
workstation_pi_user: "pi"
workstation_pi_ip: "{{ vault_workstation_pi_ip | default('127.0.0.1') }}"
workstation_pi_ram_gb: 16
workstation_pi_disk_gb: 256

# Mission Control
mc_subdomain: "mc"

# OpenCode
oc_subdomain: "oc"

# --- Prod Apps (Hetzner CX22) ---
app_prod_hostname: "app-prod-01"
app_prod_location: "fsn1"
app_prod_server_type: "cx22"
app_prod_ip: "{{ vault_app_prod_ip | default('127.0.0.1') }}"
```

### 2.6 Mettre a jour le Split DNS (vpn-dns)

Ajouter `mc.<domain>` et `oc.<domain>` dans les extra_records Headscale.

Modifier `roles/vpn-dns/defaults/main.yml` — ajouter apres le bloc `qdrant_subdomain` :

```yaml
    +
    ([{"name": mc_subdomain ~ "." ~ domain_name, "type": "A",
       "value": _vpn_dns_workstation_ts_ip}]
     if (mc_subdomain | default('')) | length > 0
     else [])
    +
    ([{"name": oc_subdomain ~ "." ~ domain_name, "type": "A",
       "value": _vpn_dns_workstation_ts_ip}]
     if (oc_subdomain | default('')) | length > 0
     else [])
```

Ajouter la variable IP Tailscale du Pi :

```yaml
_vpn_dns_workstation_ts_ip: "{{ hostvars[groups['workstation'][0]]['tailscale_ip'] | default('') }}"
```

**ATTENTION** : L'IP Tailscale du Pi sera connue APRES l'enregistrement Tailscale (Phase W1). Pour l'instant, mettre un default vide et conditionner l'ajout.

### 2.7 Ajouter `allowedOrigins` dans OpenClaw

Modifier `roles/openclaw/templates/openclaw.json.j2`, section `controlUi.allowedOrigins` :

```json
"allowedOrigins": [
  "https://{{ admin_subdomain }}.{{ domain_name }}",
  "https://{{ mc_subdomain | default('mc') }}.{{ domain_name }}"
]
```

### 2.8 Ajouter l'agent `marketer` dans OpenClaw

Modifier `roles/openclaw/defaults/main.yml` — ajouter :

```yaml
openclaw_agent_marketer_name: "marketer"
openclaw_marketer_model: "custom-litellm/minimax-m25"
```

Modifier `roles/openclaw/templates/openclaw.json.j2` — ajouter dans `agents.list` :

```json
{
  "id": "{{ openclaw_agent_marketer_name }}",
  "model": {
    "primary": "{{ openclaw_marketer_model }}"
  },
  "workspace": "/home/node/.openclaw/workspace",
  "tools": {
    "fs": { "workspaceOnly": true },
    "elevated": { "enabled": false }
  }
}
```

Et dans le concierge `subagents.allowAgents`, ajouter `"{{ openclaw_agent_marketer_name }}"`.

### 2.9 Mettre a jour le Makefile

Ajouter les targets :

```makefile
# ====================================================================
# WORKSTATION
# ====================================================================

.PHONY: deploy-workstation
deploy-workstation: ## Deployer la workstation Pi
	@echo "$(GREEN)>>> Deploying Workstation Pi...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --diff

.PHONY: deploy-mc
deploy-mc: ## Deployer Mission Control uniquement
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "mission-control" --diff

.PHONY: deploy-opencode
deploy-opencode: ## Deployer OpenCode uniquement
	$(ANSIBLE_PLAYBOOK) playbooks/workstation.yml --tags "opencode" --diff

# ====================================================================
# PROD APPS (Hetzner)
# ====================================================================

.PHONY: provision-hetzner
provision-hetzner: ## Provisionner un serveur Hetzner CX22
	@echo "$(YELLOW)>>> Provisioning Hetzner CX22...$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/provision-hetzner.yml --diff

.PHONY: deploy-app-prod
deploy-app-prod: lint ## Deployer sur le serveur Prod Apps
	@echo "$(RED)>>> PROD APPS DEPLOYMENT$(NC)"
	$(ANSIBLE_PLAYBOOK) playbooks/app-prod.yml \
		-e "target_env=app_prod" \
		--diff
```

### 2.10 Mettre a jour `versions.yml`

Ajouter les versions Pi :

```yaml
# --- Workstation Pi ---
# mission_control_version: "v1.0.0"  # A pinner apres premier test
# opencode_version: "v0.1.0"         # A pinner apres premier test
workstation_caddy_image: "caddy:2.10.2-alpine"
```

### 2.11 Ajouter `hetzner.hcloud` aux requirements

Modifier `requirements.yml` pour ajouter :

```yaml
collections:
  - name: hetzner.hcloud
    version: ">=4.0.0"
```

Et ajouter `vault_hetzner_api_token` dans le vault (via `make vault-edit`).

---

## 3. Ce qui est BLOQUE jusqu'au Pi

| Tache | Pourquoi bloquee | Prerequis |
|-------|------------------|-----------|
| Phase W1 : Tailscale registration | Le Pi doit etre UP | Flash Ubuntu + boot |
| Phase W2 : Deploy Mission Control | Ansible doit atteindre le Pi | Tailscale + SSH |
| Phase W3 : Deploy OpenCode | Idem | Idem |
| Split DNS update (mc/oc records) | IP Tailscale du Pi inconnue | Tailscale registration |
| Test E2E MC → OpenClaw | MC doit tourner | Phase W2 |

---

## 4. Conventions obligatoires (extrait de CLAUDE.md)

### Ansible
- **FQCN obligatoire** : `ansible.builtin.apt`, `community.general.ufw` — jamais `apt` seul
- **`changed_when` / `failed_when`** explicites sur toutes les taches `command` et `shell`
- **`set -euo pipefail`** + **`executable: /bin/bash`** sur toutes les taches `shell`
- **Pas de `command`/`shell`** si un module Ansible existe
- **Idempotence** : 0 changed a la 2eme execution
- **Variables** : `defaults/main.yml` (overridable) ou `vars/main.yml` (fixes)
- **Tags** : chaque role a un tag correspondant a son nom
- **`inject_facts_as_vars = False`** : utiliser `ansible_facts['xxx']` au lieu de `ansible_xxx`
- **Pas de `become: yes` global** — `become: true` par tache

### Docker
- **Jamais `:latest` ni `:stable`** — images pinnees dans `versions.yml`
- **`cap_drop: ALL`** + `cap_add` minimal
- **Healthchecks** sur chaque service
- **Log rotation** : max-size 10m, max-file 3

### Templates Jinja2
- **Toute valeur configurable** = variable (`{{ project_name }}`, `{{ domain_name }}`, etc.)
- **Pas de valeur hardcodee** : `grep -r 'seko\|Seko' .` ne doit renvoyer que variables/commentaires
- **Extension `.j2`** pour tous les templates

### Securite
- **Secrets** : tous dans `secrets.yml` chiffre Ansible Vault — jamais en clair
- **Le Pi n'a PAS de SSH public** — uniquement Tailscale ou LAN

---

## 5. Pieges connus a eviter

### Caddy VPN ACL (REX-34)
- Toute regle `not client_ip` doit inclure **2 CIDRs** : VPN + Docker bridge frontend
- Voir `docs/GUIDE-CADDY-VPN-ONLY.md` pour le guide complet
- Sur le Pi, ce n'est PAS necessaire car pas de Docker bridge pour Caddy (Caddy est en natif)

### LiteLLM (REX)
- `health_check_interval` appartient a `general_settings`, PAS `router_settings`
- OpenRouter facture `max_tokens` a la reservation
- Health checks desactives (`health_check_interval: 0`)

### Ansible WSL
- `docker ps --format "{{.Names}}"` echoue via `ansible -m shell -a` (Jinja2 interprete `{{`)
- Toujours activer le venv : `source .venv/bin/activate`

### Split DNS
- `override_local_dns: true` OBLIGATOIRE dans Headscale config
- Sans ca, Windows ignore les `extra_records` Headscale
- Les domaines du Pi (`mc.<domain>`, `oc.<domain>`) doivent pointer vers l'IP Tailscale du Pi (PAS de Sese-AI)

### Node.js sur ARM64
- Utiliser NodeSource repos pour Node.js 22 LTS
- `npm ci` peut etre lent sur Pi (compilation modules natifs)
- Mission Control est pur Next.js — pas de modules natifs, compatible ARM64

---

## 6. Fichiers existants de reference

Pour comprendre les patterns du projet, consulter :

| Fichier | Pour quoi |
|---------|-----------|
| `roles/common/tasks/main.yml` | Pattern de taches (apt, locale, timezone, sysctl) |
| `roles/common/defaults/main.yml` | Pattern de defaults |
| `roles/caddy/templates/Caddyfile.j2` | Pattern Caddyfile (vpn_only, reverse_proxy) |
| `roles/openclaw/templates/openclaw.json.j2` | Config OpenClaw (agents, models, tools) |
| `roles/openclaw/defaults/main.yml` | Config agents multi-model |
| `roles/vpn-dns/defaults/main.yml` | Pattern Split DNS records |
| `playbooks/site.yml` | Pattern playbook (pre_tasks, roles, tags) |
| `inventory/hosts.yml` | Pattern inventaire multi-groupes |
| `Makefile` | Pattern targets make |
| `docs/GUIDE-CADDY-VPN-ONLY.md` | Guide complet VPN ACL Caddy |

---

## 7. Ordre de travail recommande

1. **Modifier `inventory/hosts.yml`** — ajouter groupes `workstation` + `app_prod`
2. **Ajouter variables** dans `main.yml` — section workstation Pi + Prod Apps
3. **Creer role `workstation-common`** — `defaults/main.yml` + `tasks/main.yml`
4. **Creer role `mission-control`** — `defaults/main.yml` + `tasks/main.yml` + templates
5. **Creer role `opencode`** — `defaults/main.yml` + `tasks/main.yml` + templates
6. **Creer role `workstation-caddy`** — `defaults/main.yml` + `tasks/main.yml` + Caddyfile template
7. **Creer `playbooks/workstation.yml`**
8. **Creer `playbooks/provision-hetzner.yml`**
9. **Modifier OpenClaw** — ajouter marketer agent + allowedOrigins mc.<domain>
10. **Modifier vpn-dns** — ajouter records mc/oc (conditionnel sur IP Tailscale)
11. **Mettre a jour Makefile** — targets deploy-workstation, deploy-mc, deploy-opencode, provision-hetzner
12. **Mettre a jour versions.yml** — versions Pi
13. **Ajouter `hetzner.hcloud`** a `requirements.yml`
14. **Lancer `make lint`** — tout doit passer

---

## 8. Validation finale

Avant de commit, verifier :
```bash
source .venv/bin/activate && make lint
grep -r 'raspberry\|raspb' roles/ playbooks/  # Pas de valeur hardcodee
grep -r 'seko\|Seko' roles/ playbooks/          # Pas de valeur hardcodee
```

Tout doit etre parametrable via variables.

---

## 9. Organisation Startup — Agents

Pour reference, l'organisation cible des agents OpenClaw :

| Agent | Role | Modele | Taches |
|-------|------|--------|--------|
| **concierge** (Mobutoo) | CEO/COO | minimax-m25 | Dispatch, coordination, Telegram |
| **builder** | Ingenieur | qwen3-coder | Code, API, SaaS, CI/CD |
| **writer** (Thot) | Redacteur | glm-5 | Livres, BD, copywriting |
| **artist** (Basquiat) | Creatif | minimax-m25 | Films IA, storyboard, design |
| **tutor** (Piccolo) | Formateur | minimax-m25 | Education, tutoriels, WhatsApp |
| **explorer** (R2D2) | Recherche | grok-search | Veille, concurrence, Brave Search |
| **marketer** (CMO) | Marketing | minimax-m25 | Prospection, community, analytics |

L'identite du marketer (nom personnalise) sera choisie par l'utilisateur plus tard.

---

## 10. Git workflow

- **Branche** : `main` (pas de feature branches pour l'instant)
- **Remote** : `git@github-seko:Mobutoo/vpai.git`
- **Convention commit** : `feat(role): description` ou `fix(role): description`
- **Tag** : `vX.Y.Z` (derniere release = v1.3.0)
- Commiter par lots logiques (1 commit par role cree, ou 1 commit pour toutes les modifications d'inventaire)
