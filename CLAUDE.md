# CLAUDE.md — Instructions pour Claude Code

## Identite du Projet

Projet **Ansible** qui deploie une stack AI/automatisation auto-hebergee sur un VPS avec Docker Compose.
Template portable : toutes les valeurs sont des variables Jinja2, aucun nom hardcode.

## Acces GitHub

- **Repository** : `Mobutoo/VPAI` (prive) | **Branche** : `main`
- **Remote** : `git@github-seko:Mobutoo/vpai.git`
- **SSH Host** : `github-seko` (alias dans `~/.ssh/config`, cle `~/.ssh/id_ed25519_seko`)

> Toujours utiliser `github-seko`, jamais `github.com` directement.

## Documents de Reference

**Lire OBLIGATOIREMENT avant de coder :**

1. `PRD.md` — Vision produit, wizard de config (variables), contraintes. **Dans `.gitignore`, jamais pushe.**
2. `PRD.md.example` — Template PRD (pushee sur GitHub)
3. `TECHNICAL-SPEC.md` — Architecture technique, configs, reseaux Docker, limites ressources
4. `docs/GOLDEN-PROMPT.md` — Plan de dev en 6 phases + checklists de review + REX
5. `docs/TROUBLESHOOTING.md` — **Pieges connus et REX par service** (lire si erreur ou travail sur un service)

## Stack Technique

| Categorie | Services |
|---|---|
| Orchestration | Ansible 2.16+ (community.general, community.docker, ansible.posix) |
| Conteneurs | Docker CE + Docker Compose V2 |
| Reverse Proxy | Caddy (TLS auto, ACL VPN) |
| Donnees | PostgreSQL 18.1, Redis 8.0, Qdrant v1.16.3 |
| Applications | n8n 2.7.3, OpenClaw (YYYY.M.DD), LiteLLM v1.81.3-stable |
| Observabilite | Grafana 12.3.2, VictoriaMetrics v1.135.0, Loki 3.6.5, Alloy v1.13.0, cAdvisor v0.55.1 |
| Systeme | DIUN 4.31.0, CrowdSec, Fail2ban, UFW |
| Backup | Zerobyte v0.16 (serveur VPN distant) |
| VPN | Headscale/Tailscale (mesh VPN) |
| CI/CD | GitHub Actions (lint → molecule → deploy preprod → smoke tests) |

## Commandes de Deploiement

```bash
source .venv/bin/activate && make lint           # Linting (toujours depuis le venv)
make deploy-prod                                  # Production (SSH port 804)
make deploy-prod EXTRA_VARS="ansible_port_override=22"  # Premier deploy (VPS neuf)
make deploy-role ROLE=caddy ENV=prod              # Role specifique
ansible-playbook playbooks/site.yml --check --diff       # Dry run
ansible-playbook playbooks/site.yml --tags monitoring    # Redeploy ciblé (ex: Grafana)
ansible-vault edit inventory/group_vars/all/secrets.yml  # Vault
```

## Conventions Strictes

### Ansible

- **FQCN obligatoire** : `ansible.builtin.apt`, `community.general.ufw` — jamais `apt` seul
- **`changed_when` / `failed_when`** explicites sur toutes les taches `command` et `shell`
- **`set -euo pipefail`** + **`executable: /bin/bash`** sur toutes les taches `shell` (Debian 13 = dash par defaut)
- **Pas de `command`/`shell`** si un module Ansible existe | **Idempotence** : 0 changed a la 2eme execution
- **Variables** : `defaults/main.yml` (overridable) ou `vars/main.yml` (fixes)
- **Tags** : chaque role a un tag correspondant a son nom | **Pas de `become: yes` global**
- **`inject_facts_as_vars = False`** : utiliser `ansible_facts['xxx']` au lieu de `ansible_xxx`

### Docker

- **Jamais `:latest` ni `:stable`** — images pinnees dans `inventory/group_vars/all/versions.yml`
- **4 reseaux nommes** : `frontend`, `backend` (internal), `monitoring` (internal), `egress`
- **`cap_drop: ALL`** + `cap_add` minimal | **`DAC_OVERRIDE` + `FOWNER`** si container ecrit dans volumes
- **`restart: unless-stopped`** | **Log rotation** : max-size 10m, max-file 3 (daemon.json)
- **Limites memoire/CPU** sur chaque container (voir TECHNICAL-SPEC 2.5)
- **Healthchecks** sur chaque service (voir TECHNICAL-SPEC 8 et `docs/TROUBLESHOOTING.md` section 2)

### Templates Jinja2

- **Toute valeur configurable** = variable wizard (`{{ project_name }}`, `{{ domain_name }}`, etc.)
- **Pas de valeur hardcodee** : `grep -r 'seko\|Seko' .` ne doit renvoyer que variables/commentaires
- **Extension `.j2`** pour tous les templates

### Securite

- **SSH** : port custom (804), cle publique only, bind sur IP Headscale apres validation VPN
- **Secrets** : tous dans `secrets.yml` chiffre Ansible Vault — jamais en clair
- **Admin UIs** (n8n, Grafana, OpenClaw, Qdrant) : VPN uniquement (Caddy ACL)
- **Seuls ports publics** : 80 (redirect HTTPS) et 443 (TLS)

## Architecture de Deploiement

### Ordre des Phases

```
Phase 1  Fondations          : common, docker, headscale-node
Phase 2  Donnees + Proxy     : postgresql, redis, qdrant, caddy        (configs)
Phase 3  Applications        : n8n, litellm, openclaw                  (configs)
Phase 4  Observabilite       : monitoring, diun                         (configs)
Phase 4.5  Docker Stack      : Phase A (Infra: PG+Redis+Qdrant+Caddy) → Phase B (Apps)
Phase 4.6  Provisioning      : n8n-provision
Phase 5  Resilience          : backup-config, uptime-config, smoke-tests
Phase 6  Hardening (DERNIER) : hardening
```

### Docker Compose en 2 Fichiers

- **`docker-compose-infra.yml`** (Phase A) : PostgreSQL, Redis, Qdrant, Caddy + 4 reseaux. Pas de `depends_on`.
- **`docker-compose.yml`** (Phase B) : n8n, LiteLLM, OpenClaw, monitoring stack. Reseaux en `external: true`.

### Reseaux Docker

| Reseau | Subnet | Internal | Services principaux |
|---|---|---|---|
| `frontend` | 172.20.1.0/24 | Non | Caddy, Grafana |
| `backend` | 172.20.2.0/24 | Oui | PG, Redis, Qdrant, n8n, LiteLLM, OpenClaw, Caddy, Alloy, Grafana |
| `egress` | 172.20.4.0/24 | Non | n8n, LiteLLM, OpenClaw |
| `monitoring` | 172.20.3.0/24 | Oui | cAdvisor, VictoriaMetrics, Loki, Alloy, Grafana |
| `sandbox` | 172.20.5.0/24 | Oui | OpenClaw sous-agents isoles |

## Structure du Repository

```
.
+-- inventory/group_vars/all/
|   +-- main.yml          # Config wizard (variables projet)
|   +-- versions.yml      # Images Docker pinnees
|   +-- docker.yml        # Config Docker (daemon, reseaux, limites)
|   +-- secrets.yml       # Ansible Vault (chiffre)
+-- roles/                # 16+ roles Ansible (<role>/tasks, handlers, defaults, templates)
+-- playbooks/
+-- docs/
|   +-- GOLDEN-PROMPT.md             # Plan de dev + REX
|   +-- TROUBLESHOOTING.md           # Pieges connus par service (38 sections)
|   +-- REX-FIRST-DEPLOY-2026-02-15.md
+-- RUNBOOK.md            # Procedures operationnelles
+-- TECHNICAL-SPEC.md
+-- ansible.cfg | Makefile | .yamllint.yml | .ansible-lint
```

## REX

- **Pieges et solutions** : `docs/TROUBLESHOOTING.md` (organise par service)
- **Historique complet** : `docs/REX-FIRST-DEPLOY-2026-02-15.md`
- **Plan de dev + checklists** : `docs/GOLDEN-PROMPT.md`
