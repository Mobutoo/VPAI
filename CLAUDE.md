# CLAUDE.md — Instructions pour Claude Code

## Identite du Projet

Ce repository est un projet **Ansible** qui deploie une stack AI/automatisation auto-hebergee sur un VPS unique avec Docker Compose. Le projet est concu comme un **template portable** : toutes les valeurs sont des variables Jinja2, aucun nom de projet ou serveur n'est hardcode.

## Acces GitHub

- **Repository** : `Mobutoo/VPAI` (prive)
- **Remote** : `git@github-seko:Mobutoo/vpai.git`
- **Host SSH** : `github-seko` (configure dans `~/.ssh/config`, utilise la cle `~/.ssh/id_ed25519_seko`)
- **Branche principale** : `main`
- **Compte GitHub** : Mobutoo

> **Important** : Toujours utiliser `github-seko` comme host dans les commandes git, jamais `github.com` directement. C'est un alias SSH pour le bon couple cle/compte.

## Documents de Reference

**Lire OBLIGATOIREMENT avant de coder :**

1. `PRD.md` — Vision produit, wizard de configuration (variables), objectifs, contraintes, architecture fonctionnelle. **Fichier sensible, dans `.gitignore`, jamais pushe sur GitHub.**
2. `PRD.md.example` — Version template du PRD avec les champs a remplir (pushee sur GitHub)
3. `TECHNICAL-SPEC.md` — Architecture technique detaillee, configs, reseaux Docker, limites ressources, CI/CD
4. `docs/GOLDEN-PROMPT.md` — Plan de developpement en 6 phases avec checklists de review et **REX des erreurs rencontrees**

## Stack Technique

- **Orchestration** : Ansible 2.16+ (collections community.general, community.docker, ansible.posix)
- **Conteneurisation** : Docker CE + Docker Compose V2 (plugin)
- **Reverse Proxy** : Caddy (TLS auto, ACL VPN)
- **Donnees** : PostgreSQL 18.1, Redis 8.0, Qdrant v1.16.3
- **Applications** : n8n 2.7.3, OpenClaw, LiteLLM v1.81.3-stable
- **Observabilite** : Grafana 12.3.2, VictoriaMetrics v1.135.0, Loki 3.6.5, Alloy v1.13.0
- **Systeme** : DIUN 4.31.0, CrowdSec, Fail2ban, UFW
- **Backup** : Zerobyte v0.16 (sur serveur VPN distant, orchestre via cron local)
- **Monitoring externe** : Uptime Kuma (sur serveur VPN distant)
- **VPN** : Headscale/Tailscale (mesh VPN, deja deploye sur serveur VPN)
- **CI/CD** : GitHub Actions (lint -> molecule -> deploy preprod -> smoke tests)

## Commandes de Deploiement

```bash
# Linting (toujours depuis le venv)
source .venv/bin/activate && make lint

# Deploiement production (SSH sur port 804 par defaut)
make deploy-prod

# Premier deploiement (VPS neuf, SSH sur port 22)
make deploy-prod EXTRA_VARS="ansible_port_override=22"

# Deployer un role specifique
make deploy-role ROLE=caddy ENV=prod

# Dry run
ansible-playbook playbooks/site.yml --check --diff

# Vault
ansible-vault edit inventory/group_vars/all/secrets.yml
```

## Conventions et Regles Strictes

### Ansible

- **FQCN obligatoire** pour tous les modules : `ansible.builtin.apt`, `community.general.ufw`, etc. Jamais `apt` ou `ufw` seul
- **`changed_when` / `failed_when`** explicites sur toutes les taches `command` et `shell`
- **`set -euo pipefail`** en premiere ligne de tout script shell (inline ou template)
- **`executable: /bin/bash`** sur toutes les taches `ansible.builtin.shell` (Debian 13 utilise `dash` par defaut)
- **Pas de `command`/`shell`** si un module Ansible existe pour la tache
- **Idempotence** : chaque role doit pouvoir s'executer 2 fois consecutives avec 0 changed a la 2eme
- **Variables** : toujours dans `defaults/main.yml` (overridable) ou `vars/main.yml` (fixes)
- **Handlers** : utiliser `notify` + handler pour tout restart de service
- **Tags** : chaque role a un tag correspondant a son nom (ex: `tags: [postgresql]`)
- **Pas de `become: yes` global** : le mettre au niveau de la tache quand necessaire
- **`inject_facts_as_vars = False`** dans ansible.cfg : utiliser `ansible_facts['xxx']` au lieu de `ansible_xxx`

### Docker

- **Jamais `:latest`** ni `:stable` -- toutes les images sont pinnees dans `inventory/group_vars/all/versions.yml`
- **4 reseaux nommes** : `frontend`, `backend` (internal), `monitoring` (internal), `egress` -- voir TECHNICAL-SPEC section 2
- **Limites memoire/CPU** sur chaque container -- voir TECHNICAL-SPEC section 2.5
- **Healthchecks Docker** sur chaque service -- voir TECHNICAL-SPEC section 8
- **`restart: unless-stopped`** sur tous les services
- **Log rotation** via daemon.json (max-size 10m, max-file 3)
- **`cap_drop: ALL`** sur tous les services, puis `cap_add` minimal
- **`DAC_OVERRIDE` + `FOWNER`** necessaires pour tout container qui ecrit dans des volumes montes avec `cap_drop: ALL`

### Templates Jinja2

- **Toute valeur configurable** utilise une variable du wizard (`{{ project_name }}`, `{{ domain_name }}`, etc.)
- **Pas de valeur hardcodee** : `grep -r 'seko\|Seko' .` ne doit renvoyer que des variables/commentaires, jamais des valeurs en dur
- **Extension `.j2`** pour tous les templates

### Securite

- **SSH** : port custom (804), bind sur IP Headscale uniquement apres validation VPN, cle publique only
- **Secrets** : tous dans `inventory/group_vars/all/secrets.yml` chiffre avec Ansible Vault
- **Jamais de secret en clair** dans les fichiers YAML, templates, ou scripts
- **Admin UIs** (n8n, Grafana, OpenClaw, Qdrant) : accessibles uniquement via VPN (Caddy ACL)
- **Seuls ports publics** : 80 (redirect HTTPS) et 443 (TLS)

## Architecture de Deploiement

### Ordre d'Execution des Phases

```
Phase 1 -- Fondations
  common, docker, headscale-node

Phase 2 -- Donnees & Reverse Proxy (configs uniquement)
  postgresql, redis, qdrant, caddy

Phase 3 -- Applications (configs uniquement)
  n8n, litellm, openclaw

Phase 4 -- Observabilite (configs uniquement)
  monitoring, diun

Phase 4.5 -- Deploiement Docker Stack
  docker-stack :
    Phase A: Infra (PostgreSQL, Redis, Qdrant, Caddy) + Reseaux
    Phase B: Apps (n8n, LiteLLM, OpenClaw, Monitoring, DIUN)

Phase 4.6 -- Provisioning Post-Deploiement
  n8n-provision

Phase 5 -- Resilience
  backup-config, uptime-config, smoke-tests

Phase 6 -- Hardening (DERNIER)
  hardening
```

### Docker Compose en 2 Fichiers

- **`docker-compose-infra.yml`** (Phase A) : PostgreSQL, Redis, Qdrant, Caddy + 4 reseaux. Pas de `depends_on`. Chaque service demarre independamment.
- **`docker-compose.yml`** (Phase B) : n8n, LiteLLM, OpenClaw, VictoriaMetrics, Loki, Alloy, Grafana, DIUN. Reseaux en `external: true`.

### Reseaux Docker Isoles

| Reseau | Subnet | Internal | Services |
|--------|--------|----------|----------|
| `frontend` | 172.20.1.0/24 | Non | Caddy, Grafana |
| `backend` | 172.20.2.0/24 | Oui | PG, Redis, Qdrant, n8n, LiteLLM, OpenClaw, Caddy, Alloy |
| `egress` | 172.20.4.0/24 | Non | n8n, LiteLLM, OpenClaw |
| `monitoring` | 172.20.3.0/24 | Oui | VictoriaMetrics, Loki, Alloy, Grafana |

---

## Pieges Connus et Regles de Qualite (REX)

Ces regles ont ete decouvertes lors des deploiements. **Les respecter elimine les erreurs rencontrees.**

### Encodage et Fins de Ligne

- **TOUS les fichiers YAML/Jinja2 doivent etre en UTF-8 avec fins de ligne LF (Unix)**
- **Jamais de CRLF (Windows)** : yamllint echoue avec `wrong new line character: expected \n`
- **Jamais de Windows-1252** : yamllint crash avec `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97`
- **Attention au tiret long** : em dash (U+2014) est le piege principal. En Windows-1252 c'est le byte `0x97` qui casse le parsing UTF-8
- **Verification** : `file roles/*/tasks/main.yml` doit afficher `UTF-8 Unicode text` pour tous les fichiers
- **Fix** : `find roles/ -name '*.yml' -exec sed -i 's/\r$//' {} \;`

### ansible-lint -- Pieges Specifiques

- **`name:` du play et variables** : Les templates Jinja2 dans le champ `name:` d'un **play** ne peuvent PAS utiliser de variables d'inventaire. Utiliser un nom statique.
- **`schema[meta]`** : Le `role_name` dans `meta/main.yml` doit correspondre au pattern `^[a-z][a-z0-9_]+$`. Underscores uniquement, pas de tirets.
- **`syntax-check`** : configurer `extra_vars` dans `.ansible-lint` pour les variables utilisees dans les `name:` de plays
- **`offline: true`** : Obligatoire dans `.ansible-lint` si pas de Galaxy configure
- **`playbooks_dir`** : Propriete supprimee dans ansible-lint 26.x, ne plus l'utiliser

### ansible.cfg

- **`community.general.yaml` supprime** dans community.general 12.0.0+. Utiliser `stdout_callback = ansible.builtin.default` + `callback_result_format = yaml`
- **`inject_facts_as_vars = False`** : Utiliser `ansible_facts['date_time']['iso8601']` au lieu de `ansible_date_time.iso8601`
- **`deprecation_warnings = False`** : Supprime les warnings de collections tierces (ansible.posix)

### yamllint

- **`octal-values`** : ansible-lint exige `forbid-implicit-octal: true` et `forbid-explicit-octal: true`
- **`secrets.yml`** : Exclu du `find` dans le Makefile ET dans le `ignore:` de `.yamllint.yml`

### Makefile

- **Ne PAS utiliser** `yamllint .` directement. Utiliser `find` avec exclusions et `xargs`
- **`EXTRA_VARS`** : Variable Make pour passer des extra-vars Ansible. Ex: `make deploy-prod EXTRA_VARS="ansible_port_override=22"`

### PostgreSQL 18+ -- Breaking Changes

- **Volume Mount** : `/var/lib/postgresql` (pas `/var/lib/postgresql/data` comme avant 18)
- **Capabilities** : `DAC_OVERRIDE` + `FOWNER` obligatoires en plus de `CHOWN`, `SETGID`, `SETUID`
- **ICU Locale** : `--locale-provider=icu --icu-locale=fr-FR --locale=C` (le locale systeme `fr_FR.UTF-8` n'est PAS installe dans l'image Docker)
- **postgresql.conf** : `logging_collector = off` obligatoire (Docker capte stdout/stderr, le collector tente d'ecrire dans un dir non-existant)
- **Migration depuis PG 17** : Necessite `pg_upgrade` si donnees existantes

### Redis 8.0 -- Breaking Changes

- **`rename-command` supprime** : Utiliser ACL a la place. `rename-command FLUSHDB ""` cause un crash au demarrage.
- **`protected-mode yes`** : Ajouter explicitement dans redis.conf

### Qdrant v1.16+ -- Specifique

- **Pas de `wget`/`curl`** dans l'image : Healthcheck via `bash -c ':> /dev/tcp/localhost/6333'`
- **Config** : Monter comme `/qdrant/config/production.yaml` (pas `config.yaml`)
- **API Key** : Passer via `QDRANT__SERVICE__API_KEY` en env var (evite les problemes d'echappement YAML)
- **Capabilities** : `DAC_OVERRIDE` + `FOWNER` necessaires pour ecrire dans storage/snapshots
- **Snapshots/tmp** : Nettoyer `snapshots/tmp` avant redemarrage si erreur `PermissionDenied`

### Caddy -- Healthcheck et Capabilities

- **Healthcheck** : Utiliser `caddy version` (l'admin API `:2019` ne repond pas en Docker malgre la config)
- **Capabilities** : `NET_BIND_SERVICE` + `DAC_OVERRIDE` (pour ecrire dans le volume logs)
- **rate_limit** : Plugin non inclus dans l'image stock `caddy:alpine`. Commenter ou builder une image custom.
- **Logs** : Volume `/var/log/caddy` monte et accessible en ecriture

### Monitoring -- UIDs Conteneurs

- **VictoriaMetrics** : UID 1000 (pas `{{ prod_user }}`)
- **Loki** : UID 10001 (pas `{{ prod_user }}`)
- **Grafana** : UID 472
- **Regle** : Les dirs de data doivent etre `chown` avec l'UID du conteneur, pas l'utilisateur systeme

### Loki 3.6.5 -- Image Distroless

- **Distroless** : `grafana/loki:3.6.5` n'a AUCUN outil shell (pas de wget, curl, ls, test, bash)
- **Healthcheck** : Utiliser `loki -health` (commande built-in ajoutee en v3.6.5, backport PR #20590)
- **Empty ring** : Bug #19381 -- le module `memberlist-kv` s'initialise meme avec kvstore `inmemory`
- **Fix empty ring** : Ajouter `-target=all` dans la commande + `ingester.lifecycler.ring` explicite + `memberlist.join_members: []`
- **Config monolithique** : `replication_factor: 1` + `kvstore.store: inmemory` dans `common.ring` ET `ingester.lifecycler.ring`

### Healthchecks Docker -- Regles Generales

- **Toujours `127.0.0.1`** au lieu de `localhost` (Alpine resout en IPv6 `[::1]`, services n'ecoutent qu'IPv4)
- **Verifier les outils** avant d'ecrire un healthcheck : `docker exec <c> which wget curl ls test bash`
- **Images distroless** : utiliser les commandes built-in du binaire (ex: `loki -health`, `caddy version`)
- **Images Python** (LiteLLM) : utiliser `python -c "import urllib.request; ..."`
- **Fallback universel** : `kill -0 1` verifie que le process principal tourne

### DNS dans les Scripts

- **Ne PAS utiliser `dig`** : Le paquet `dnsutils` n'est pas installe sur les images minimales Debian 13
- **Utiliser `getent hosts`** : Fait partie de glibc, toujours disponible
- **Syntaxe** : `getent hosts "domain.tld" | awk '{print $1}' | head -1`

### Port SSH et Deploiement

- **Inventaire** : `ansible_port: "{{ ansible_port_override | default(prod_ssh_port) }}"` -- utilise le port 804 par defaut
- **Premier deploiement** (VPS neuf, port 22) : `make deploy-prod EXTRA_VARS="ansible_port_override=22"`
- **Deploiements suivants** (port 804) : `make deploy-prod`
- **Hardening en Phase 6** : DERNIER role, `hardening_ssh_force_open: true` par defaut
- **TOUJOURS garder une fenetre SSH ouverte** pendant le deploiement

### Docker-Stack -- Architecture

- **Phase A (Infra)** : Services demarrent independamment, pas de `depends_on`
- **Phase B (Apps)** : Ne contient PAS les services infra (pas de duplication PG/Redis/Qdrant/Caddy)
- **Cleanup** : Seule Phase B est arretee avant redeploy (infra reste running)
- **Healthchecks individuels** : Chaque service Phase A a un check + diagnostic logs si unhealthy
- **Caddy unhealthy non-bloquant** : Warning au lieu de fail (Caddy recupere quand les backends demarrent)

### VPN ACL et Admin Access -- Architecture

- **Admin UIs (Grafana, n8n, OpenClaw, Qdrant)** : Accessibles UNIQUEMENT via VPN
- **ACL Caddy** : `remote_ip {{ caddy_vpn_cidr }}` (100.64.0.0/10) sur les domaines admin
- **Split DNS OBLIGATOIRE** : Les clients VPN doivent resoudre les sous-domaines admin vers l'IP Tailscale du VPS (pas l'IP publique)
- **Sans split DNS** : Le trafic passe par Internet et Caddy voit l'IP publique du client -> blocage meme si VPN actif
- **Config Headscale** : `dns.extra_records` avec les sous-domaines admin -> IP Tailscale du VPS
- **Alternative** : `/etc/hosts` cote client avec les entries admin -> IP Tailscale du VPS
- **Smoke tests** : Utilisent `--resolve domain:443:<TAILSCALE_IP>` pour forcer le routage VPN
- **VPN error page** : `error @blocked 403` + `handle_errors` (retourne HTTP 403, pas 200)

### Grafana -- Sub-path avec SERVE_FROM_SUB_PATH

- **Ne PAS strip_prefix** quand Grafana utilise `GF_SERVER_SERVE_FROM_SUB_PATH=true`
- Grafana gere le prefix `/grafana/` lui-meme, Caddy doit juste proxifier sans modifier l'URI
- Strip prefix + SERVE_FROM_SUB_PATH = boucle de redirection infinie

### n8n -- Sous-domaine dedie obligatoire

- **n8n NE supporte PAS le sub-path** (GitHub issue #19635)
- **Variable** : `n8n_subdomain` dans l'inventaire (ex: `mayi`)
- **Caddyfile** : Bloc dedie `{{ caddy_n8n_domain }}` avec `import vpn_only` + `import vpn_error_page`
- **Fallback** : Si `n8n_subdomain` vide, n8n est monte en sub-path sur le domaine admin (page blanche probable)

### PostgreSQL -- Provisioning Idempotent

- **`init.sql` ne s'execute que lors de la PREMIERE initialisation** (data dir vide)
- **Script `provision-postgresql.sh`** : Verifie et cree les DBs/users a chaque deploy
- **Execute apres Phase A** dans les tasks docker-stack
- **LiteLLM restart** : Restart automatique si pas healthy apres Phase B (timing DB provisioning)

### OpenClaw -- Gateway Architecture (WebSocket, NOT HTTP REST)

- **OpenClaw est un agent IA Gateway WebSocket** sur port **18789**, PAS un serveur HTTP REST sur 8080
- **Architecture** : OpenClaw -> LiteLLM -> (Anthropic, OpenAI, OpenRouter)
- **Pas de base de donnees** : OpenClaw est file-based (sessions JSON), pas PostgreSQL/Redis/Qdrant
- **Config** : `openclaw.json` (pas des env vars DB), provider custom LiteLLM via `models.providers`
- **Env vars valides** : `OPENCLAW_GATEWAY_TOKEN`, `LITELLM_API_KEY`, `TELEGRAM_BOT_TOKEN`, `NODE_OPTIONS`
- **Env vars INEXISTANTES** : `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `HOST`, `PORT`, `API_KEY`
- **Container user** : `node` (UID 1000), dirs data doivent etre `chown 1000:1000`
- **`init: true`** dans docker-compose (le process Node.js Gateway a besoin d'init)
- **`NODE_OPTIONS=--max-old-space-size=768`** dans openclaw.env.j2
- **Limite Docker** : 1536M minimum pour OpenClaw
- **Control UI** : Servie directement par le Gateway sur le meme port (18789)
- **Caddy proxy** : `reverse_proxy openclaw:18789` avec `uri strip_prefix /openclaw`
- **Onboarding** : Le flag `--allow-unconfigured` dans le Dockerfile permet de demarrer sans onboarding interactif
- **Image** : `ghcr.io/openclaw/openclaw:2026.2.15` (tags: YYYY.M.DD, pas de prefixe v)
- **Volume** : Monter `/home/node/.openclaw` en RW (pas readonly) — OpenClaw ecrit canvas/, cron/, sessions/, plugins/
- **`agents.defaults.model`** : Doit etre un objet `{"primary": "provider/model"}`, PAS une string
- **`channels.telegram`** : La cle est `botToken` (pas `token`)
- **`controlUi.basePath`** : Doit correspondre au chemin public (`/openclaw`), PAS au chemin interne
- **Reverse proxy** : Ne PAS strip_prefix quand basePath est configure — le Gateway attend le full path
- **`trustedProxies`** : Necessaire derriere un reverse proxy pour X-Forwarded-For
- **`allowInsecureAuth`** : Necessaire car WebCrypto requiert HTTPS ou localhost

### LiteLLM -- Config Syntax

- **`fallbacks`** : Format correct `[{"model_name": ["fallback_model"]}]`, PAS `- model: ... fallback: [...]`
- **`os.environ/`** : Preferer `os.environ/VAR_NAME` dans config.yaml pour referencer les env vars
- **Redis cache** : Ajouter `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` dans le `.env`, puis `os.environ/REDIS_*` dans cache_params
- **`general_settings`** : `master_key` et `database_url` via `os.environ/` (pas de secrets en clair dans la config)
- **Modele `default`** : Supprime — un seul mapping par modele, le client choisit le modele a utiliser
- **Memoire** : 1024M minimum (pas 768M) pour PostgreSQL + Redis cache + model routing
- **UI sub-path** : `SERVER_ROOT_PATH` est buggy (issues #11451, #11865, #10761) — UI web non-fonctionnelle en sub-path
- **Health endpoint** : `/health` requiert le header `Authorization: Bearer <master_key>` quand master_key est configure

### Sub-path Hosting -- Limites Connues

- **LiteLLM UI** : Ne supporte PAS le sub-path (`SERVER_ROOT_PATH` buggy). API fonctionne, UI non.
- **Qdrant Dashboard** : Ne supporte PAS le sub-path (issue qdrant-web-ui#94 ouverte depuis 2023). API fonctionne, dashboard non.
- **OpenClaw Control UI** : Supporte le sub-path via `controlUi.basePath` + pas de strip_prefix dans Caddy
- **Grafana** : Supporte le sub-path via `GF_SERVER_SERVE_FROM_SUB_PATH=true` + pas de strip_prefix
- **n8n** : Ne supporte PAS le sub-path (issue #19635) — utilise un sous-domaine dedie
- **Regle generale** : Quand une app ne supporte pas le sub-path, utiliser un sous-domaine dedie ou accepter API-only

### Smoke Tests

- **Non-bloquants par defaut** : `failed_when: false`, resultats affiches en warning
- **Mode strict** : `smoke_test_strict: true` pour bloquer le playbook sur echec
- **Qdrant connectivity** : Via `docker exec` + `bash -c ':> /dev/tcp/localhost/6333'`
- **VPN-protected endpoints** : Resolus via IP Tailscale avec `curl --resolve`
- **LiteLLM health** : Requiert le header auth Bearer dans le smoke test et le healthcheck Docker

### Debian 13 (Trixie) -- Specifique

- **`dash` par defaut** : Toutes les taches `shell` doivent avoir `executable: /bin/bash`
- **`apt_key` deprecie** : Utiliser `gpg --dearmor` + `signed-by=`
- **`apt-transport-https` supprime** : Ne pas l'inclure dans les paquets
- **Depots minimaux** : Verifier/corriger `/etc/apt/sources.list.d/debian.sources` avant le premier `apt update`

---

## Structure du Repository

```
.
+-- .github/workflows/          # CI/CD pipelines
+-- inventory/
|   +-- hosts.yml               # Inventaire (prod + preprod + vpn)
|   +-- group_vars/all/
|       +-- main.yml            # Config wizard
|       +-- versions.yml        # Images Docker pinnees
|       +-- docker.yml          # Config Docker (daemon, reseaux, limites)
|       +-- secrets.yml         # Ansible Vault (chiffre)
+-- roles/                      # 16+ roles Ansible
|   +-- <role>/
|       +-- tasks/main.yml
|       +-- handlers/main.yml
|       +-- defaults/main.yml
|       +-- templates/
|       +-- meta/main.yml
|       +-- molecule/default/
|       +-- README.md
+-- playbooks/
+-- docs/
|   +-- GOLDEN-PROMPT.md        # Plan de dev + REX
|   +-- REX-FIRST-DEPLOY-2026-02-15.md
+-- COMMANDES_DEPLOIEMENT.md    # Guide deploiement
+-- TECHNICAL-SPEC.md
+-- ansible.cfg
+-- Makefile
+-- .yamllint.yml
+-- .ansible-lint
```

## REX Complet

Voir `docs/REX-FIRST-DEPLOY-2026-02-15.md` pour l'historique detaille des erreurs et corrections de deploiement.
