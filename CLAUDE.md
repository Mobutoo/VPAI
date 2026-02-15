# CLAUDE.md — Instructions pour Claude Code

## Identité du Projet

Ce repository est un projet **Ansible** qui déploie une stack AI/automatisation auto-hébergée sur un VPS unique avec Docker Compose. Le projet est conçu comme un **template portable** : toutes les valeurs sont des variables Jinja2, aucun nom de projet ou serveur n'est hardcodé.

## Accès GitHub

- **Repository** : `Mobutoo/VPAI` (privé)
- **Remote** : `git@github-seko:Mobutoo/vpai.git`
- **Host SSH** : `github-seko` (configuré dans `~/.ssh/config`, utilise la clé `~/.ssh/id_ed25519_seko`)
- **Branche principale** : `main`
- **Compte GitHub** : Mobutoo

> **Important** : Toujours utiliser `github-seko` comme host dans les commandes git, jamais `github.com` directement. C'est un alias SSH pour le bon couple clé/compte.

## Documents de Référence

**Lire OBLIGATOIREMENT avant de coder :**

1. `PRD.md` — Vision produit, wizard de configuration (variables), objectifs, contraintes, architecture fonctionnelle. **⚠️ Fichier sensible, dans `.gitignore`, jamais pushé sur GitHub.**
2. `PRD.md.example` — Version template du PRD avec les champs à remplir (pushée sur GitHub)
3. `TECHNICAL-SPEC.md` — Architecture technique détaillée, configs, réseaux Docker, limites ressources, CI/CD
4. `docs/GOLDEN-PROMPT.md` — Plan de développement en 6 phases avec checklists de review et **REX des erreurs rencontrées**

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
├── PRD.md                      # Product Requirements Document (LOCAL ONLY, dans .gitignore)
├── PRD.md.example              # Template PRD avec champs à remplir (pushé sur GitHub)
├── TECHNICAL-SPEC.md           # Spécification technique
├── docs/GOLDEN-PROMPT.md       # Plan de développement + REX erreurs
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

Suivre les 6 phases du `docs/GOLDEN-PROMPT.md` dans l'ordre. Chaque phase a un checkpoint de review.

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

---

## Pièges Connus et Règles de Qualité (REX)

Ces règles ont été découvertes lors du développement initial. **Les respecter élimine 100% des erreurs de lint rencontrées.**

### Encodage et Fins de Ligne

- **TOUS les fichiers YAML/Jinja2 doivent être en UTF-8 avec fins de ligne LF (Unix)**
- **Jamais de CRLF (Windows)** : yamllint échoue avec `wrong new line character: expected \n`
- **Jamais de Windows-1252** : yamllint crash avec `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97`
- **Attention au tiret long** : `—` (em dash, U+2014) est le piège principal. En Windows-1252 c'est le byte `0x97` qui casse le parsing UTF-8
- **Vérification** : `file roles/*/tasks/main.yml` doit afficher `UTF-8 Unicode text` pour tous les fichiers, jamais `ISO-8859` ou `CRLF`
- **Fix si besoin** : `find roles/ -name '*.yml' -exec sed -i 's/\r$//' {} \;` pour les CRLF

### ansible-lint — Pièges Spécifiques

- **`name:` du play et variables** : Les templates Jinja2 dans le champ `name:` d'un **play** ne peuvent PAS utiliser de variables d'inventaire
  - ❌ `- name: "Deploy {{ project_display_name }}"` (inventaire pas encore chargé)
  - ✅ `- name: "Deploy Full Stack"` (nom statique pour le play)
  - ✅ Dans les tasks : `msg: "Project: {{ project_display_name }}"` (variables disponibles)
  - **Pourquoi** : Le `name:` du play est parsé avant le chargement des variables d'inventaire
  - **Erreur rencontrée** : `Error processing keyword 'name': 'project_display_name' is undefined`
- **`schema[meta]`** : Le `role_name` dans `meta/main.yml` doit correspondre au pattern `^[a-z][a-z0-9_]+$`
  - ❌ `role_name: headscale-node` (tirets interdits)
  - ✅ `role_name: headscale_node` (underscores OK, le dossier peut garder le tiret)
- **`syntax-check`** : ansible-lint exécute un syntax-check sans inventaire. Les variables comme `project_display_name` sont indéfinies → configurer `extra_vars` dans `.ansible-lint`
- **`offline: true`** : Obligatoire dans `.ansible-lint` si pas de Galaxy configuré, sinon erreur `Required config 'url' for 'galaxy' galaxy_server plugin`
- **`playbooks_dir`** : Propriété supprimée dans ansible-lint 26.x, ne plus l'utiliser

### ansible.cfg — Callback Plugins

- **`community.general.yaml` supprimé** : Le callback plugin `community.general.yaml` a été retiré dans community.general 12.0.0+
  - ❌ `stdout_callback = yaml` (ancien plugin community.general)
  - ✅ `stdout_callback = ansible.builtin.default` + `callback_result_format = yaml` (ansible-core 2.13+)
- **Erreur rencontrée** : `[ERROR]: The 'community.general.yaml' callback plugin has been removed`
- **Solution** : Utiliser le plugin intégré avec l'option `result_format=yaml`

### yamllint — Configuration Requise

- **`octal-values`** : ansible-lint exige `forbid-implicit-octal: true` et `forbid-explicit-octal: true` dans `.yamllint.yml`
- **`secrets.yml`** : Le fichier Vault chiffré doit être dans le `ignore:` de `.yamllint.yml` ET exclu du `find` dans le Makefile

### Makefile — Commande Lint

- **Ne PAS utiliser** `yamllint .` directement — cela scanne les fichiers Vault chiffrés et crash
- **Utiliser** `find` avec exclusions et `xargs` :
  ```makefile
  find . \( -name '*.yml' -o -name '*.yaml' \) \
    ! -path './.git/*' ! -path './.venv/*' \
    ! -path '*/molecule/*' ! -path '*/collections/*' \
    ! -name 'secrets.yml' -print0 | xargs -0 yamllint -c .yamllint.yml
  ```
- **Grouper les `-o`** dans `find` avec `\( ... \)`, sinon le comportement est incorrect

### Grafana Alloy

- **Format HCL** (HashiCorp Configuration Language), pas YAML Prometheus
- **Monter `/proc` et `/sys`** en read-only pour les métriques node_exporter :
  ```yaml
  volumes:
    - /proc:/host/proc:ro
    - /sys:/host/sys:ro
  ```
- **Healthcheck** : `wget -qO- http://localhost:12345/-/ready`

### DIUN

- **Préférer un fichier de config** (`diun.yml.j2`) plutôt que des variables d'environnement — plus lisible et plus flexible pour la notification conditionnelle
- **Docker socket** monté en read-only : `/var/run/docker.sock:/var/run/docker.sock:ro`

### Environnement de Développement (WSL)

- **venv Python** : Utiliser `.venv/` pour installer ansible-lint et yamllint (`python3 -m venv .venv`)
- **Activer le venv** avant `make lint` : `source .venv/bin/activate && make lint`
- **`.venv/`** est dans `.gitignore`
