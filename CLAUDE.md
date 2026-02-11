# CLAUDE.md — Instructions pour Claude Code

## Identité du Projet

Ce repository est un projet **Ansible** qui déploie une stack AI/automatisation auto-hébergée sur un VPS unique avec Docker Compose. Le projet est conçu comme un **template portable** : toutes les valeurs sont des variables Jinja2, aucun nom de projet ou serveur n'est hardcodé.

## Documents de Référence

**Lire OBLIGATOIREMENT avant de coder :**

1. `PRD.md` — Vision produit, wizard de configuration (variables), objectifs, contraintes, architecture fonctionnelle
2. `TECHNICAL-SPEC.md` — Architecture technique détaillée, configs, réseaux Docker, limites ressources, CI/CD
3. `GOLDEN-PROMPT.md` — Plan de développement en 6 phases avec checklists de review

## Stack Technique

- **Orchestration** : Ansible 2.16+ (collections community.general, community.docker, ansible.posix)
- **Conteneurisation** : Docker CE + Docker Compose V2 (plugin)
- **Reverse Proxy** : Caddy (TLS auto, rate limiting, ACL VPN)
- **Données** : PostgreSQL 18.1, Redis 8.0.10, Qdrant v1.16.3
- **Applications** : n8n 2.7.3, OpenClaw v2026.2.9, LiteLLM v1.81.3-stable
- **Observabilité** : Grafana 12.3.2, VictoriaMetrics v1.135.0, Loki 3.6.5, Alloy v1.13.0
- **Système** : DIUN 4.31.0, CrowdSec, Fail2ban, UFW
- **Backup** : Zerobyte v0.16 (sur serveur VPN distant, orchestré via cron local)
- **Monitoring externe** : Uptime Kuma (sur serveur VPN distant)
- **VPN** : Headscale/Tailscale (mesh VPN, déjà déployé sur serveur VPN)
- **CI/CD** : GitHub Actions (lint → molecule → deploy preprod → smoke tests)

## Conventions et Règles Strictes

### Ansible

- **FQCN obligatoire** pour tous les modules : `ansible.builtin.apt`, `community.general.ufw`, etc. Jamais `apt` ou `ufw` seul
- **`changed_when` / `failed_when`** explicites sur toutes les tâches `command` et `shell`
- **`set -euo pipefail`** en première ligne de tout script shell (inline ou template)
- **Pas de `command`/`shell`** si un module Ansible existe pour la tâche
- **Idempotence** : chaque rôle doit pouvoir s'exécuter 2 fois consécutives avec 0 changed à la 2ème
- **Variables** : toujours dans `defaults/main.yml` (overridable) ou `vars/main.yml` (fixes)
- **Handlers** : utiliser `notify` + handler pour tout restart de service
- **Tags** : chaque rôle a un tag correspondant à son nom (ex: `tags: [postgresql]`)
- **Pas de `become: yes` global** : le mettre au niveau de la tâche quand nécessaire

### Docker

- **Jamais `:latest`** ni `:stable` — toutes les images sont pinnées dans `inventory/group_vars/all/versions.yml`
- **4 réseaux nommés** : `frontend`, `backend` (internal), `monitoring` (internal), `egress` — voir TECHNICAL-SPEC section 2
- **Limites mémoire/CPU** sur chaque container — voir TECHNICAL-SPEC section 2.5
- **Healthchecks Docker** sur chaque service — voir TECHNICAL-SPEC section 8
- **`restart: unless-stopped`** sur tous les services
- **Log rotation** via daemon.json (max-size 10m, max-file 3)
- **Pas de `network_mode: host`** sauf DIUN (qui a besoin du Docker socket)

### Templates Jinja2

- **Toute valeur configurable** utilise une variable du wizard (`{{ project_name }}`, `{{ domain_name }}`, etc.)
- **Pas de valeur hardcodée** : `grep -r 'seko\|Seko' .` ne doit renvoyer que des variables/commentaires, jamais des valeurs en dur
- **Extension `.j2`** pour tous les templates

### Sécurité

- **SSH** : port custom, bind sur IP Headscale uniquement, clé publique only
- **Secrets** : tous dans `inventory/group_vars/all/secrets.yml` chiffré avec Ansible Vault
- **Jamais de secret en clair** dans les fichiers YAML, templates, ou scripts
- **Admin UIs** (n8n, Grafana, OpenClaw, Qdrant) : accessibles uniquement via VPN (Caddy ACL)
- **Seuls ports publics** : 80 (redirect HTTPS) et 443 (TLS)

### Documentation

- Chaque rôle a un `README.md` avec : description, variables (tableau), dépendances, exemple
- Chaque rôle a un répertoire `molecule/default/` avec converge.yml et verify.yml

## Structure du Repository

```
.
├── .github/workflows/          # CI/CD pipelines
├── inventory/
│   ├── hosts.yml               # Inventaire (prod + preprod)
│   └── group_vars/all/         # Variables globales
│       ├── main.yml            # Config wizard (depuis PRD.md section 2.1)
│       ├── versions.yml        # Images Docker pinnées (depuis PRD.md section 2.3)
│       ├── docker.yml          # Config Docker (daemon, réseaux, limites)
│       └── secrets.yml         # Ansible Vault (chiffré)
├── roles/                      # 16 rôles Ansible
│   └── <role>/
│       ├── tasks/main.yml
│       ├── handlers/main.yml
│       ├── defaults/main.yml
│       ├── vars/main.yml       # (si nécessaire)
│       ├── templates/
│       ├── files/
│       ├── meta/main.yml
│       ├── molecule/default/
│       │   ├── molecule.yml
│       │   ├── converge.yml
│       │   └── verify.yml
│       └── README.md
├── playbooks/                  # Playbooks utilitaires
├── scripts/                    # Scripts helper
├── templates/                  # Templates partagés (docker-compose.yml.j2)
├── docs/                       # Documentation opérationnelle
├── PRD.md                      # Product Requirements Document
├── TECHNICAL-SPEC.md           # Spécification technique
├── GOLDEN-PROMPT.md            # Plan de développement
├── ansible.cfg
├── requirements.yml
├── Makefile
├── .yamllint.yml
├── .ansible-lint
└── README.md
```

## Commandes Utiles

```bash
# Linting
make lint                                    # yamllint + ansible-lint
ansible-lint playbooks/site.yml              # Lint complet

# Tests Molecule
make test                                    # Tous les rôles
molecule test -s default -- roles/common     # Un rôle spécifique

# Déploiement
make deploy-preprod                          # Pré-production Hetzner
make deploy-prod                             # Production (avec confirmation)

# Vault
ansible-vault edit inventory/group_vars/all/secrets.yml
ansible-vault encrypt_string 'my_secret' --name 'variable_name'

# Vérification
ansible-playbook playbooks/site.yml --check --diff   # Dry run
ansible-inventory --list                              # Vérifier l'inventaire
```

## Ordre de Développement

Suivre les 6 phases du `GOLDEN-PROMPT.md` dans l'ordre. Chaque phase a un checkpoint de review.

**Phase 1** → common, hardening, docker, headscale-node  
**Phase 2** → caddy, postgresql, redis, qdrant  
**Phase 3** → n8n, openclaw, litellm  
**Phase 4** → monitoring (VM + Loki + Alloy + Grafana), diun  
**Phase 5** → backup-config, uptime-config, smoke-tests  
**Phase 6** → CI/CD workflows, documentation, polish  

## Points d'Attention Spécifiques

### PostgreSQL 18.1
C'est un **major upgrade** depuis 17.x. Si migration d'un système existant, `pg_upgrade` est requis. Pour un nouveau déploiement, pas de problème.

### Redis 8.0
**Major upgrade** depuis 7.x. Nouvelles features : I/O threading (+30% perf), JSON memory (-92%). Vérifier la compatibilité des clients.

### Réseau `egress`
LiteLLM, n8n et OpenClaw ont besoin d'**accès internet sortant** (appels API OpenAI/Anthropic, webhooks). Le réseau `backend` est `internal: true` donc pas d'internet. Ces 3 services doivent aussi être sur le réseau `egress` (non-internal).

### Zerobyte sur Seko-VPN
Zerobyte n'est **pas** déployé par ce projet. Il tourne déjà sur le serveur VPN. Ce projet :
1. Prépare les scripts pre-backup (pg_dump, redis save, etc.) sur le VPS prod
2. Documente la configuration Zerobyte dans le RUNBOOK

### Uptime Kuma sur Seko-VPN
Même logique : déjà déployé. Ce projet documente les monitors à créer manuellement.
