# TROUBLESHOOTING.md — Pieges Connus et REX

> **Usage** : Ce fichier regroupe tous les pieges decouverts en production.
> Lire si tu travailles sur un service specifique ou si tu rencontres une erreur.
> Reference principale : `docs/REX-FIRST-DEPLOY-2026-02-15.md` (historique complet).

---

## Table des Matieres

0. [Workstation Pi — Pièges Spécifiques](#0-workstation-pi--pièges-spécifiques)
1. [Ansible & Linting](#1-ansible--linting)
2. [Docker & Healthchecks](#2-docker--healthchecks)
3. [PostgreSQL 18+](#3-postgresql-18)
4. [Redis 8.0](#4-redis-80)
5. [Qdrant v1.16+](#5-qdrant-v116)
6. [Caddy](#6-caddy)
7. [Loki 3.6.5](#7-loki-365)
8. [Grafana](#8-grafana)
9. [n8n 2.0+](#9-n8n-20)
10. [LiteLLM](#10-litellm)
11. [OpenClaw](#11-openclaw) — 11.16 workspaceAccess · 11.17 provider openai direct · 11.18 handler recreate · 11.19 heartbeat/cron · 11.20 status slugs · 11.21 external-link read-only · 11.22 comment field · 11.23 sandbox DinD ENOENT
12. [Reseau & VPN](#12-reseau--vpn)
13. [Systeme & Debian 13](#13-systeme--debian-13)

---

## 0. Workstation Pi — Pièges Spécifiques

### 0.1 npm prefix NodeSource v22

NodeSource v22 installe les packages globaux dans `/usr/bin`, **pas** `/usr/local/bin`.

```yaml
# FAUX — binary introuvable
opencode_npm_prefix: "/usr/local"

# CORRECT
opencode_npm_prefix: "/usr"  # → /usr/bin/opencode, /usr/bin/claude
```

### 0.2 Mission Control — next.config.mjs sans standalone

`crshdn/mission-control` n'a pas `output: 'standalone'` → pas de `.next/standalone/server.js`.

```ini
# FAUX — fichier inexistant
ExecStart=/usr/bin/node {{ mc_install_dir }}/.next/standalone/server.js

# CORRECT — utiliser next start directement
ExecStart=/usr/bin/node {{ mc_install_dir }}/node_modules/.bin/next start -p {{ mc_port }}
```

- Artefact idempotence : `.next/BUILD_ID` (pas `.next/standalone/server.js`)
- Healthcheck : URL `/` avec status 200/301/302 (pas `/api/health` — 404 en v1.1.0)
- Build : `npm ci` obligatoire (pas `--omit=dev`) — tailwindcss est devDep requis pour `next build`

### 0.3 OpenCode v1.2.8 — config schema changé

Les clés `providers` et `workspace` ne sont plus valides au niveau root du JSON.

```json
// FAUX — crash ConfigInvalidError
{ "providers": {...}, "workspace": {...} }

// CORRECT — config minimale valide v1.2.8
{ "$schema": "https://opencode.ai/config.json", "username": "mobuone" }
```

Provider LiteLLM custom (OpenAI-compatible) :
```json
{
  "provider": {
    "litellm": {
      "npm": "@ai-sdk/openai",
      "api": "https://llm.domain.com/v1",
      "env": ["LITELLM_API_KEY"],
      "models": { "claude-sonnet": { "id": "anthropic/claude-sonnet-4-5", "tool_call": true } }
    }
  }
}
```

### 0.4 xcaddy ARM64 — Go version insuffisante

Ubuntu 24.04 ARM64 fournit Go 1.22. `caddy-dns/ovh v1.1.0` requiert Go >= 1.24.

```yaml
# Installer Go 1.24.2 depuis go.dev AVANT xcaddy
- name: Download and install Go ARM64
  ansible.builtin.shell:
    cmd: |
      curl -fsSL "https://dl.google.com/go/go1.24.2.linux-arm64.tar.gz" -o /tmp/go.tar.gz
      rm -rf /usr/local/go
      tar -C /usr/local -xzf /tmp/go.tar.gz
  args:
    creates: /usr/local/go/bin/go
```

Build complet : `xcaddy build v2.10.2 --with github.com/caddy-dns/ovh`

### 0.5 Claude Code OAuth Max Plan — ne pas mélanger avec API key

Si `ANTHROPIC_API_KEY` est défini dans l'environnement → Claude Code CLI utilise l'API (billing par token).
Pour forcer OAuth Max Plan : **ne pas injecter** `ANTHROPIC_API_KEY` dans l'env du service ou du shell.

Auth manuelle (une seule fois) :
```bash
# En SSH sur le Pi (ou dans tmux)
claude
# → affiche une URL dans le terminal
# → copier l'URL dans le navigateur Windows
# → se connecter avec le compte Max Plan
# → tokens sauvegardés dans ~/.claude/ (persistants, auto-renouvelés)
```

### 0.6 tailscale up bloque si Headscale down

`tailscale up --login-server=...` attend indéfiniment si le serveur Headscale est inaccessible.
→ Vérifier `https://singa.ewutelo.cloud` avant de lancer le rôle `headscale-node`.
→ Sur Seko-VPN, Headscale tourne via Docker Compose : `cd /opt/services/headscale && sudo docker compose up -d`

### 0.7 Headscale preauth key — usage unique

La clé `headscale_auth_key` dans le vault est à **usage unique ET expirante**.
Après utilisation ou expiration, en générer une nouvelle :

```bash
# Sur Seko-VPN (via Docker Compose exec)
cd /opt/services/headscale
sudo docker compose exec headscale headscale preauthkeys create --user mobuone --expiration 24h
# Mettre à jour dans le vault
ansible-vault edit inventory/group_vars/all/secrets.yml
```

### 0.8 headscale-node — repo Tailscale Debian vs Ubuntu

Le rôle `headscale-node` était hardcodé sur le repo Debian. Utiliser `ansible_facts['distribution'] | lower` :

```yaml
# CORRECT — générique Debian/Ubuntu
DISTRO="{{ ansible_facts['distribution'] | lower }}"
url: "https://pkgs.tailscale.com/stable/${DISTRO}/..."
```

### 0.9 ansible_become_pass pour le Pi

Le Pi nécessite un mot de passe sudo. Configurer dans `hosts.yml` via vault :
```yaml
# inventory/hosts.yml
ansible_become_pass: "{{ workstation_pi_become_pass | default('') }}"

# inventory/group_vars/all/main.yml
workstation_pi_become_pass: "{{ vault_workstation_become_pass }}"
```

### 0.10 SSH key — chemins selon environnement

| Environnement | Chemin clé SSH |
|---|---|
| WSL Ubuntu (Ansible) | `~/.ssh/seko-vpn-deploy` = `/home/asus/.ssh/seko-vpn-deploy` |
| Git Bash / PowerShell | `/c/Users/mmomb/.ssh/seko-vpn-deploy` |
| SSH depuis Git Bash | `ssh -i /c/Users/mmomb/.ssh/seko-vpn-deploy mobuone@192.168.1.8` |

### 0.11 Tailscale — reconnexion automatique au démarrage du Pi

**C'est en place automatiquement.** Le rôle `headscale-node` active `tailscaled` en tant que service systemd `enabled: true` :

```yaml
- name: Enable and start Tailscale service
  ansible.builtin.systemd:
    name: tailscaled
    state: started
    enabled: true   # démarre automatiquement à chaque boot
```

**Comportement au reboot du Pi :**
1. systemd démarre `tailscaled` automatiquement
2. Tailscale lit sa clé de session depuis `/var/lib/tailscale/` (persistée après le 1er `tailscale up`)
3. Le Pi se reconnecte au réseau Headscale **sans intervention** — la pre-auth key vault n'est plus nécessaire

**Vérifier la connexion après reboot :**
```bash
# Sur le Pi
tailscale status         # doit afficher "workstation-pi ... active"
tailscale ip -4          # IP Tailscale assignée (100.64.x.x)
ping <headscale_vpn_ip>  # ping vers Seko-VPN via VPN
```

**Cas où la reconnexion échoue :**
- Headscale est down → voir 0.6
- La session Tailscale a été révoquée depuis le serveur Headscale → régénérer une pre-auth key (voir 0.7) et redéployer `--tags headscale-node`
- Vérifier l'état du daemon : `sudo systemctl status tailscaled`

### 0.12 Caddy Workstation — service et chemins

Le Pi utilise un service Caddy **custom** (pas le paquet standard) :

| Element | Valeur |
|---|---|
| Service systemd | `caddy-workstation.service` (PAS `caddy.service`) |
| Caddyfile | `/opt/workstation/configs/caddy/Caddyfile` |
| Binary | `/usr/bin/caddy` (xcaddy build avec module OVH DNS) |
| Data | `/opt/workstation/data/caddy` |

```bash
# FAUX — service inexistant
sudo systemctl status caddy
sudo caddy validate --config /etc/caddy/Caddyfile

# CORRECT
sudo systemctl status caddy-workstation
sudo systemctl reload caddy-workstation
sudo caddy validate --config /opt/workstation/configs/caddy/Caddyfile
```

### 0.13 OpenCut — service on-demand (pas autostart)

OpenCut est deploye mais **pas demarre** par defaut (`opencut_autostart: false`).
Le controle se fait via Telegram (workflow n8n `opencut-control`).

```bash
# Demarrer manuellement sur le Pi
sudo docker compose -f /opt/workstation/docker-compose-opencut.yml up -d

# Arreter
sudo docker compose -f /opt/workstation/docker-compose-opencut.yml down

# Status
sudo docker compose -f /opt/workstation/docker-compose-opencut.yml ps
```

Une erreur 502 sur `cut.ewutelo.cloud` est **normale** quand le service est arrete — la page bleue "Service en veille" s'affiche.

---

## 1. Ansible & Linting

### 1.1 Encodage et Fins de Ligne

- **TOUS les fichiers YAML/Jinja2 doivent etre en UTF-8 avec fins de ligne LF (Unix)**
- **Jamais de CRLF (Windows)** : yamllint echoue avec `wrong new line character: expected \n`
- **Jamais de Windows-1252** : yamllint crash avec `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97`
- **Piege principal** : em dash (U+2014) = byte `0x97` en Windows-1252 — casse le parsing UTF-8
- **Verification** : `file roles/*/tasks/main.yml` doit afficher `UTF-8 Unicode text`
- **Fix** : `find roles/ -name '*.yml' -exec sed -i 's/\r$//' {} \;`

### 1.2 ansible-lint — Pieges Specifiques

- **`name:` du play** : Les templates Jinja2 dans le champ `name:` d'un **play** ne peuvent PAS utiliser des variables d'inventaire. Utiliser un nom statique.
- **`schema[meta]`** : Le `role_name` dans `meta/main.yml` doit correspondre a `^[a-z][a-z0-9_]+$`. Underscores uniquement, pas de tirets.
- **`syntax-check`** : configurer `extra_vars` dans `.ansible-lint` pour les variables dans les `name:` de plays
- **`offline: true`** : Obligatoire dans `.ansible-lint` si pas de Galaxy configure
- **`playbooks_dir`** : Propriete supprimee dans ansible-lint 26.x — ne plus l'utiliser

### 1.3 ansible.cfg

- **`community.general.yaml` supprime** dans community.general 12.0.0+. Utiliser :
  `stdout_callback = ansible.builtin.default` + `callback_result_format = yaml`
- **`inject_facts_as_vars = False`** : Utiliser `ansible_facts['date_time']['iso8601']` au lieu de `ansible_date_time.iso8601`
- **`deprecation_warnings = False`** : Supprime les warnings de collections tierces (ansible.posix)

### 1.4 yamllint

- **`octal-values`** : ansible-lint exige `forbid-implicit-octal: true` et `forbid-explicit-octal: true`
- **`secrets.yml`** : Exclu du `find` dans le Makefile ET dans le `ignore:` de `.yamllint.yml`
- **Ne PAS utiliser** `yamllint .` directement — utiliser `find` avec exclusions et `xargs`

### 1.5 Port SSH et Deploiement

- **Inventaire** : `ansible_port: "{{ ansible_port_override | default(prod_ssh_port) }}"` — port 804 par defaut
- **Premier deploiement** (VPS neuf, port 22) : `make deploy-prod EXTRA_VARS="ansible_port_override=22"`
- **Deploiements suivants** (port 804) : `make deploy-prod`
- **Hardening** : TOUJOURS en Phase 6 (DERNIER). Garder une fenetre SSH ouverte pendant le deploiement.

---

## 2. Docker & Healthchecks

### 2.1 Healthchecks — Regles Generales

- **Toujours `127.0.0.1`** au lieu de `localhost` — Alpine resout `localhost` en IPv6 `[::1]`, les services n'ecoutent qu'IPv4
- **Verifier les outils disponibles** avant d'ecrire un healthcheck :
  `docker exec <container> which wget curl ls test bash`
- **Images distroless** (Loki) : utiliser les commandes built-in du binaire (`loki -health`, `caddy version`)
- **Images Python** (LiteLLM) : utiliser `python -c "import urllib.request; ..."`
- **Fallback universel** : `kill -0 1` verifie que le process principal tourne

### 2.2 Docker-Stack — Architecture 2 Fichiers

- **`docker-compose-infra.yml`** (Phase A) : PG, Redis, Qdrant, Caddy + 4 reseaux. Pas de `depends_on`.
- **`docker-compose.yml`** (Phase B) : Apps uniquement. Reseaux en `external: true`.
- **Cleanup** : Seule Phase B est arretee avant redeploy (infra reste running)
- **Healthchecks individuels** : Chaque service Phase A a un check + diagnostic logs si unhealthy
- **Caddy unhealthy non-bloquant** : Warning au lieu de fail (Caddy recupere quand les backends demarrent)

### 2.3 Capabilities Docker

- **`cap_drop: ALL`** sur tous les services, puis `cap_add` minimal
- **`DAC_OVERRIDE` + `FOWNER`** necessaires pour tout container qui ecrit dans des volumes montes
- **Services Root** : cAdvisor uniquement (volumes /sys, /var/lib/docker en read-only)

### 2.4 DNS dans les Scripts

- **Ne PAS utiliser `dig`** : `dnsutils` n'est pas installe sur les images minimales Debian 13
- **Utiliser `getent hosts`** : Fait partie de glibc, toujours disponible
- **Syntaxe** : `getent hosts "domain.tld" | awk '{print $1}' | head -1`

---

## 3. PostgreSQL 18+

### 3.1 Breaking Changes vs PG 17

- **Volume Mount** : `/var/lib/postgresql` (pas `/var/lib/postgresql/data` comme avant PG 18)
- **Capabilities** : `DAC_OVERRIDE` + `FOWNER` obligatoires en plus de `CHOWN`, `SETGID`, `SETUID`
- **ICU Locale** : `--locale-provider=icu --icu-locale=fr-FR --locale=C`
  (le locale `fr_FR.UTF-8` n'est PAS installe dans l'image Docker)
- **`logging_collector = off`** dans postgresql.conf — Docker capte stdout/stderr, le collector tente d'ecrire dans un dir non-existant
- **Migration depuis PG 17** : Necessite `pg_upgrade` si donnees existantes

### 3.2 Provisioning Idempotent

- **`init.sql` ne s'execute que lors de la PREMIERE initialisation** (data dir vide)
- **Script `provision-postgresql.sh`** : Verifie et cree les DBs/users a chaque deploy — execute apres Phase A
- **LiteLLM restart** : Restart automatique si pas healthy apres Phase B (timing DB provisioning)

### 3.3 Table model_scores

- **Localisation** : Base `n8n`, creee par `provision-postgresql.sh`
- **Schema** : `model` (PK), `total_calls`, `successful_calls`, `failed_calls`, `total_tokens` (bigint),
  `total_cost` (double precision), `total_latency_ms` (double precision), `likes`, `dislikes`,
  `score` (int, default 50), `avg_cost_per_call`, `avg_latency_ms` (double precision),
  `source`, `first_seen`, `last_updated` (timestamptz)
- **Source de verite** pour le workflow n8n `ai-model-scoring` et les dashboards Grafana

### 3.4 ROUND() sur double precision — Piege SQL

- **`ROUND(double_precision, integer)`** n'existe PAS en PostgreSQL
- **Fix** : Caster en `::numeric` avant `ROUND()` : `ROUND(column::numeric, 2)`
- **Piege CASE** : Si les branches CASE retournent des types mixtes (`numeric` + `double precision`), ROUND() echoue
- **Fix CASE** : Caster TOUTES les branches, y compris ELSE : `0.5::numeric`, `1::numeric`, `(1 - expr)::numeric`

---

## 4. Redis 8.0

### 4.1 Breaking Changes

- **`rename-command` supprime** : Utiliser ACL a la place. `rename-command FLUSHDB ""` cause un crash au demarrage.
- **`protected-mode yes`** : Ajouter explicitement dans redis.conf

---

## 5. Qdrant v1.16+

### 5.1 Configuration

- **Pas de `wget`/`curl`** dans l'image : Healthcheck via `bash -c ':> /dev/tcp/localhost/6333'`
- **Config** : Monter comme `/qdrant/config/production.yaml` (pas `config.yaml`)
- **API Key** : Passer via `QDRANT__SERVICE__API_KEY` en env var (evite les problemes d'echappement YAML)
- **Capabilities** : `DAC_OVERRIDE` + `FOWNER` necessaires pour ecrire dans storage/snapshots
- **Snapshots/tmp** : Nettoyer `snapshots/tmp` avant redemarrage si erreur `PermissionDenied`

---

## 6. Caddy

### 6.1 Healthcheck et Capabilities

- **Healthcheck** : Utiliser `caddy version` — l'admin API `:2019` ne repond pas en Docker malgre la config
- **Capabilities** : `NET_BIND_SERVICE` + `DAC_OVERRIDE` (pour ecrire dans le volume logs)
- **rate_limit** : Plugin NON inclus dans `caddy:alpine`. Commenter ou builder une image custom.
- **Logs** : Volume `/var/log/caddy` monte et accessible en ecriture

### 6.2 VPN ACL et Admin Access

- **Admin UIs (Grafana, n8n, OpenClaw, Qdrant)** : Accessibles UNIQUEMENT via VPN (`caddy_vpn_enforce: true` permanent depuis v1.2.0)
- **ACL Caddy** : snippet `vpn_only` → `@blocked not client_ip {{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}`
- **Split DNS OBLIGATOIRE** : Les clients VPN doivent résoudre les sous-domaines admin vers l'IP Tailscale du VPS
- **Sans split DNS** : Le trafic passe par Internet → Caddy voit l'IP publique → blocage même si VPN actif
- **Config Headscale** : `dns.extra_records` + `override_local_dns: true` dans config.yaml — déployé via rôle `vpn-dns`
- **REX HTTP/3 QUIC/UDP** : Connexions Tailscale via HTTP/3 arrivent avec `client_ip=172.20.1.1` (gateway Docker bridge, DNAT UDP). Caddy ne voit jamais l'IP Tailscale directement → ajouter `caddy_docker_frontend_cidr: 172.20.1.0/24` au snippet `vpn_only`. Cette plage est inatteignable depuis Internet → sûr.
- **VPN error page** : `error @blocked 403` + `handle_errors` (retourne HTTP 403, pas 200)

### 6.2.1 Bug Caddyfile — heredoc respond 200

- **Symptôme** : Caddy crash en boucle : `unrecognized directive: 200`
- **Cause** : Dans un heredoc Caddyfile `respond <<MARKER ... MARKER`, le code HTTP doit être **sur la même ligne** que le marqueur de fin : `MARKER 200` (pas `MARKER\n 200`)
- **Impact** : 1525 timeouts DNS `lookup n8n: i/o timeout` consécutifs (Caddy redémarrait avant que le DNS Docker soit initialisé)
- **Fix** : `BOOTSTRAP 200` sur une ligne dans `Caddyfile.j2`

### 6.3 Architecture Sous-domaines (1 service = 1 sous-domaine)

| Variable | Valeur prod | Service | Note |
|---|---|---|---|
| `admin_subdomain` | javisi | OpenClaw Gateway | basePath=/, pas de strip_prefix |
| `grafana_subdomain` | tala | Grafana | pas de SERVE_FROM_SUB_PATH |
| `n8n_subdomain` | mayi | n8n | ne supporte pas le sub-path (#19635) |
| `litellm_subdomain` | llm | LiteLLM | UI buggy en sub-path (#11451/#11865) |
| `qdrant_subdomain` | qd | Qdrant | dashboard sans support sub-path (#94) |

**Regle** : Chaque service a son propre sous-domaine. Plus de sub-path.

### 6.4 Grafana — Sub-path avec SERVE_FROM_SUB_PATH

- **Ne PAS strip_prefix** quand Grafana utilise `GF_SERVER_SERVE_FROM_SUB_PATH=true`
- Strip prefix + SERVE_FROM_SUB_PATH = boucle de redirection infinie
- Grafana gere le prefix `/grafana/` lui-meme, Caddy doit juste proxifier sans modifier l'URI

---

## 7. Loki 3.6.5

### 7.1 Image Distroless — Pieges

- **Distroless** : `grafana/loki:3.6.5` n'a AUCUN outil shell (pas de wget, curl, ls, test, bash)
- **Healthcheck** : Utiliser `loki -health` (commande built-in ajoutee en v3.6.5, backport PR #20590)

### 7.2 Bug "Empty Ring"

- **Bug** #19381 : le module `memberlist-kv` s'initialise meme avec kvstore `inmemory`
- **Fix** : Ajouter `-target=all` dans la commande + `ingester.lifecycler.ring` explicite + `memberlist.join_members: []`
- **Config monolithique** : `replication_factor: 1` + `kvstore.store: inmemory` dans `common.ring` ET `ingester.lifecycler.ring`

---

## 8. Grafana

### 8.1 UIDs Conteneurs (chown obligatoire)

| Service | UID | Note |
|---|---|---|
| VictoriaMetrics | 1000 | pas `{{ prod_user }}` |
| Loki | 10001 | pas `{{ prod_user }}` |
| Grafana | 472 | — |
| cAdvisor | root | volumes en read-only, pas de data persistant |

**Regle** : Les dirs de data doivent etre `chown` avec l'UID du conteneur, pas l'utilisateur systeme.

### 8.2 Flux de Donnees Monitoring

```
Container metrics  →  cAdvisor → Alloy → VictoriaMetrics → Grafana
Logs               →  Docker socket → Alloy → Loki → Grafana
AI scoring         →  model_scores (PostgreSQL) → Grafana
```

**Metriques LiteLLM** : `litellm_requests_total`, `litellm_tokens_total`, `litellm_spend_total`, `litellm_request_duration_seconds_bucket`

**Metriques Qdrant** : `qdrant_points_total`, `qdrant_search_avg_duration_seconds`, `qdrant_rest_responses_total`

### 8.3 cAdvisor — Notes Specifiques

- **Image** : `ghcr.io/google/cadvisor:0.55.1` (depuis v0.53.0, migre de `gcr.io` vers `ghcr.io`)
- **ATTENTION** : les tags cAdvisor n'ont PAS de prefixe `v` (ex: `0.55.1`, pas `v0.55.1`)
- **Reseau** : `monitoring` uniquement — pas besoin de `backend`
- **Optimisation** : `--docker_only=true` + `--disable_metrics=advtcp,...`

### 8.4 Datasources Provisionnes

- **VictoriaMetrics** (prometheus, default), **Loki** (logs), **PostgreSQL-n8n** (model_scores)
- **PostgreSQL datasource** : Grafana doit etre sur le reseau `backend` (en plus de `frontend` + `monitoring`)
- **Dashboards (9 fichiers)** : system-overview, docker-containers, postgresql, litellm-proxy, logs-explorer, ai-pipeline, qdrant-collections, ai-model-scoring, ai-cost-cockpit

### 8.5 PIEGE CRITIQUE — Provisioning Datasource PostgreSQL

- **`user` au niveau RACINE** : Grafana 12 postgres plugin exige `user:` au niveau racine du datasource
  — PAS dans `jsonData` ni `secureJsonData`. Seul `password` va dans `secureJsonData`.

```yaml
# FORMAT CORRECT pour datasources.yaml.j2
- name: PostgreSQL-n8n
  uid: PostgreSQL-n8n
  type: postgres
  access: proxy
  url: postgresql:5432
  user: "n8n"           # <- RACINE — pas dans jsonData ni secureJsonData
  editable: false
  jsonData:
    database: "n8n"
    sslmode: "disable"
    maxOpenConns: 5
    maxIdleConns: 2
    connMaxLifetime: 14400
    postgresVersion: 1800
    timescaledb: false
  secureJsonData:
    password: "{{ postgresql_password }}"  # <- seul le password ici
```

- **Symptome** : `"pq: no PostgreSQL user name specified in startup packet"` dans les logs Grafana
  + `config_user_length: 0` dans le detail de l'erreur health check
- **Diagnostic** :
  ```bash
  # Obtenir l'IP du container Grafana
  docker inspect javisi_grafana | grep '"IPAddress"'
  # Tester la connexion datasource
  docker exec javisi_grafana wget -qO- --post-data="{}" \
    "http://admin:PASSWORD@<IP_CONTAINER>:3000/api/datasources/uid/PostgreSQL-n8n/health"
  # Reponse OK : {"message":"Database Connection OK","status":"OK"}
  ```
- **Redeploy minimal** : `ansible-playbook playbooks/site.yml --tags monitoring`

### 8.6 Requetes SQL dans les Dashboards

- **Filtres temporels** : `$__timeFrom()` et `$__timeTo()` (pas de variables custom)
- **Time-series grouping** : `$__timeGroup(column, interval)`
- **Projections de couts** : Calculees via `AVG()` sur la periode, extrapolees a 1/3/12 mois
- **WHERE clause** : Pour les panels listing/ranking, inclure les modeles avec feedback mais 0 appels :
  `WHERE total_calls > 0 OR likes > 0 OR dislikes > 0`
- **Panels couts/latence** : Garder `WHERE total_calls > 0` (metriques sans appels = sans sens)

---

## 9. n8n 2.0+

### 9.1 Sous-domaine Dedie Obligatoire

- **n8n NE supporte PAS le sub-path** (GitHub issue #19635)
- **Variable** : `n8n_subdomain` dans l'inventaire (ex: `mayi`)
- **Caddyfile** : Bloc dedie `{{ caddy_n8n_domain }}` avec `import vpn_only` + `import vpn_error_page`

### 9.2 Task Runners et Code Node Sandbox

- **Task Runners** : Actives par defaut en n8n 2.0+ (`N8N_RUNNERS_ENABLED=true`, `N8N_RUNNERS_MODE=internal`)
- **`require()` BLOQUE** par defaut. Pour utiliser `fs`, `path`, `crypto` : `NODE_FUNCTION_ALLOW_BUILTIN=fs,path,crypto`
- **`$env` BLOQUE** par defaut. Pour lire les env vars dans les Code nodes : `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`
- **Symptome d'echec silencieux** : Le webhook retourne HTTP 200 avec body vide (`responseMode=responseNode`), aucune erreur visible
- **`NODE_FUNCTION_ALLOW_EXTERNAL=pg`** : Autorise le module `pg` (deja installe en tant que dependance interne)

### 9.3 Webhooks v2

- **Structure** : `{ headers, body, query, params }` — acceder au body via `$input.first().json.body`
- **Headers** : `$input.first().json.headers['x-header-name']` (lowercase)
- **Validation secret** : Verifier header d'abord, puis `body.secret` en fallback (ceinture+bretelles)

### 9.4 Import et Suppression de Workflows

- **Import** : `n8n import:workflow` SKIP si le workflow existe deja (par nom)
- **Pour mettre a jour** : supprimer via UI/API puis reimporter + `n8n publish:workflow --id=<ID>` + restart
- **Suppression v2.7+** : Deactivate → Archive → Delete (sans archive, DELETE retourne 400)
- **Login API v2.7+** : Le champ est `emailOrLdapLoginId` (pas `email`)
- **Pas de curl** dans le container n8n : Uniquement BusyBox wget (sans --method)
- **Provisioning checksum-based** : MD5 stockes dans `/opt/<project>/configs/n8n/workflow-checksums/`

### 9.5 Workflow ai-model-scoring

- **4 branches** : feedback webhook (UPSERT + score recalc), scores webhook (SELECT), cron 6h (LiteLLM logs), weekly discovery
- **Connection pg dans Code node** : `host: 'postgresql', port: 5432, database: 'n8n'`
- **Score formula** : `score = (likeRatio * 40) + (successRate * 30) + (costEfficiency * 20) + (speedScore * 10)`

---

## 10. LiteLLM

### 10.1 Config Syntax

- **`fallbacks`** : Format liste de dicts : `[{"model_name": ["fallback_model"]}]`
  PAS `- model: ... fallback: [...]`
- **`os.environ/`** : Preferer `os.environ/VAR_NAME` dans config.yaml pour referencer les env vars (pas de secrets en clair)
- **Redis cache** : Ajouter `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` dans le `.env`, puis `os.environ/REDIS_*` dans cache_params
- **`general_settings`** : `master_key` et `database_url` via `os.environ/`
- **Modele `default`** : Supprime — le client choisit le modele

### 10.2 Ressources et Acces

- **Memoire minimum** : 1024M (pas 768M) pour PostgreSQL + Redis cache + model routing
- **UI sub-path** : `SERVER_ROOT_PATH` buggy (issues #11451, #11865, #10761) — sous-domaine dedie obligatoire
- **Health endpoint** : `/health` requiert `Authorization: Bearer <master_key>` quand master_key configure

### 10.3 Metriques LiteLLM (pour Alloy/VictoriaMetrics)

- `litellm_requests_total` — nombre de requetes
- `litellm_tokens_total` — tokens consommes
- `litellm_spend_total` — cout total
- `litellm_request_duration_seconds_bucket` — latences (histogram)

### 10.4 Health Checks — Désactiver pour les modèles payants

- **Par défaut** : LiteLLM exécute des health checks sur **tous** les modèles toutes les ~38 secondes
- **Impact** : Perplexity Sonar Pro seul = **$11.64 en 16h** (1488 health checks × $0.01/appel)
- **Fix** : `health_check_interval: 0` dans `router_settings` du fichier config LiteLLM
- **Alternative** : `health_check_interval: 3600` pour un check horaire (acceptable sur modèles gratuits)
- **Détection des pannes** : Utiliser les fallbacks + métriques Prometheus (plus fiable que les health checks)

### 10.5 max_tokens OpenRouter — Réservation vs Consommation

- **Problème** : Sans `max_tokens` explicite dans `litellm_params`, LiteLLM utilise la valeur par défaut du modèle (ex: 16000 pour minimax-m1)
- **Impact OpenRouter** : OpenRouter facture sur la **réservation** au moment de la requête, pas sur la consommation réelle. Si les crédits disponibles < `max_tokens` → erreur 402 "not enough credits"
- **Fix** : Ajouter `max_tokens: 4096` dans `litellm_params` pour tous les modèles OpenRouter
- **Valeur recommandée** : 4096 tokens suffisent pour les workflows Telegram/résumé/traduction
- **Modèles concernés** : minimax-m25, deepseek-v3, deepseek-r1, glm-5, kimi-k2, grok-search, perplexity-pro, qwen3-coder, seedream

### 10.6 N8N_PROXY_HOPS — Express Rate Limit

- **Erreur** : `ERR_ERL_UNEXPECTED_X_FORWARDED_FOR` dans les logs n8n
- **Cause** : Caddy ajoute `X-Forwarded-For` mais Express (n8n) a `trust proxy = false` par défaut
- **Fix** : `N8N_PROXY_HOPS=1` dans `n8n.env.j2` (1 hop = Caddy)
- **Impact sans fix** : Rate limiting incorrect, warnings continus dans les logs

---

## 11. OpenClaw

### 11.1 Architecture Gateway WebSocket

- **OpenClaw = agent IA Gateway WebSocket** sur port **18789**, PAS un serveur HTTP REST
- **Architecture** : OpenClaw → LiteLLM → (Anthropic, OpenAI, OpenRouter)
- **Pas de base de donnees** : File-based (sessions JSON)
- **Config** : `openclaw.json` — provider custom LiteLLM via `models.providers`

**Env vars VALIDES** : `OPENCLAW_GATEWAY_TOKEN`, `LITELLM_API_KEY`, `TELEGRAM_BOT_TOKEN`, `NODE_OPTIONS`

**Env vars INEXISTANTES** (ne pas ajouter) : `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `HOST`, `PORT`, `API_KEY`

### 11.2 Docker et Ressources

- **Container user** : `node` (UID 1000) — dirs data doivent etre `chown 1000:1000`
- **`init: true`** dans docker-compose (le process Node.js Gateway a besoin d'init)
- **`NODE_OPTIONS=--max-old-space-size=768`** dans openclaw.env.j2
- **Memoire minimum** : 1536M
- **Volume** : Monter `/home/node/.openclaw` en RW — OpenClaw ecrit canvas/, cron/, sessions/, plugins/
- **Image** : `ghcr.io/openclaw/openclaw:YYYY.M.DD` (tags date, pas de prefixe v)

### 11.2b Caddy + HTTP/2 = WebSocket Upgrade cassé

**Symptôme** : Mission Control affiche "offline" — connexion `wss://javisi.ewutelo.cloud` échoue.

**Cause** : HTTP/2 ignore le header `Upgrade: websocket` (RFC 6455). Caddy en H2 répond `200` au lieu de `101 Switching Protocols`.

**Diagnostic** : tester depuis le Pi avec HTTP/1.1 explicite (Python, pas curl) :
```bash
# 101 = OK, 200 = H2 problem
python3 -c "
import http.client, ssl
conn = http.client.HTTPSConnection('javisi.ewutelo.cloud', context=ssl.create_default_context())
conn.request('GET', '/', headers={'Connection':'Upgrade','Upgrade':'websocket','Sec-WebSocket-Key':'dGhlIHNhbXBsZSBub25jZQ==','Sec-WebSocket-Version':'13'})
print(conn.getresponse().status)
"
```

**Fix** : forcer HTTP/1.1 dans le `reverse_proxy` Caddy pour OpenClaw :
```caddyfile
reverse_proxy openclaw:18789 {
    transport http {
        versions 1.1
    }
}
```

### 11.3 openclaw.json — Pieges de Config

- **`agents.defaults.model`** : Doit etre un objet `{"primary": "provider/model"}`, PAS une string
- **`channels.telegram`** : La cle est `botToken` (pas `token`)
- **`controlUi.basePath`** : `/` quand sous-domaine dedie
- **`trustedProxies`** : Necessaire derriere Caddy pour X-Forwarded-For
- **`allowInsecureAuth`** : Necessaire car WebCrypto requiert HTTPS ou localhost
- **`heartbeat`** : **CLE INCONNUE en v2026.2.22** — cause crash-loop immédiat
- **`cron`** comme array `[{...}]` : **NON SUPPORTÉ en v2026.2.22** — "expected object, received array"
  → Ces deux clés sont documentées dans le plan mais pas encore implémentées dans cette version.
  → Ne jamais les ajouter sans vérifier d'abord avec `docker logs javisi_openclaw 2>&1 | head -5` qu'elles sont acceptées.
  → Règle générale : toute nouvelle clé dans `openclaw.json.j2` → tester en dry-run ou vérifier les logs immédiatement après deploy.

### 11.4 tools.web — Cles Valides

- **`tools.web.fetch.readability`** : Cle NON RECONNUE — cause crash-loop du container
- **Cles valides pour `tools.web.fetch`** : `enabled`, `maxChars`, `timeoutSeconds`, `cacheTtlMinutes`, `maxRedirects`
- **`tools.web.search.provider`** : `"brave"` (seul provider supporte actuellement)
- **Regle** : Toujours verifier les cles de config contre la doc avant d'ajouter des options

### 11.5 Bootstrap Token (Premier Acces UI)

- Le Control UI stocke le gateway token dans `localStorage` du navigateur
- Au premier acces, localStorage vide → l'UI boucle sur "token missing" sans prompt de saisie
- **Fix** : Route `/__bootstrap__` dans Caddy qui injecte le token via JS et redirige
- **Premier acces** : `https://<admin_subdomain>.<domain>/__bootstrap__`

### 11.6 Telegram Pairing

- **Par defaut** `dmPolicy: "pairing"` — le bot envoie un code a approuver :
  `docker exec <c> node openclaw.mjs pairing approve telegram <CODE>`
- **Automatisation** : si `telegram_openclaw_chat_id` est renseigne → `dmPolicy: "allowlist"` avec `allowFrom: [chat_id]` — plus de pairing interactif

### 11.7 Skills — Format Obligatoire

- **Structure** : Dossier `skills/<name>/SKILL.md`, PAS un fichier plat `skills/<name>.md`
- **Decouverte** : OpenClaw scanne `~/.openclaw/skills/` pour des sous-dossiers contenant `SKILL.md`
- **Frontmatter YAML OBLIGATOIRE** :
  ```yaml
  ---
  name: mon-skill
  description: What this skill does (trigger phrase for the model).
  metadata: { "openclaw": { "emoji": "icon", "always": true } }
  ---
  ```
- **Sans `description`** : le skill est charge puis **silencieusement rejete** — n'apparait ni dans l'UI ni dans le system prompt
- **`always: true`** : Force l'inclusion meme si les binaires requis ne sont pas presents (utile pour skills webhook-only)
- **Fichiers plats `.md`** directement dans `skills/` : IGNORES silencieusement
- **Test rapide** :
  ```bash
  docker exec <c> node --input-type=module -e \
    "import{loadSkillsFromDir}from'@mariozechner/pi-coding-agent'; \
    const r=loadSkillsFromDir({dir:'/home/node/.openclaw/skills',source:'t'}); \
    console.log(r.skills.length,r.diagnostics)"
  ```

### 11.8 Sandbox — Isolation des Workspaces

- **2 couches** : Gateway dans Docker + outils dans conteneurs sandbox separes
- **Docker socket** : Monte en read-only pour spawner les sandbox
- **Modes** : `"off"` / `"non-main"` / `"all"` (configuré dans `agents.defaults.sandbox`)
- **`tools.elevated.enabled`** : TOUJOURS `false`
- **`tools.fs.workspaceOnly`** : `true`
- **CVE** : GHSA-gv46-4xfq-jv58 (RCE bypass), GHSA-xw4p-pw82-hqr7 (path traversal)
- **Reseau sandbox** : `{{ project_name }}_sandbox` (internal, 172.20.5.0/24) — seul LiteLLM accessible

### 11.9 Modeles — Assignation Open-Source First (Free Tier)

| Agent | Persona | Modele | Justification |
|---|---|---|---|
| Concierge | Mobutoo | deepseek-v3-free | DeepSeek V3 :free OpenRouter — 0 credit requis |
| Builder | Imhotep | qwen3-coder | Qwen3 Coder :free OpenRouter — 0 credit requis |
| Writer | Thot | deepseek-v3-free | Generaliste, 0 credit |
| Artist | Basquiat | deepseek-v3-free | Fallback libre quand credits vides |
| Tutor | Piccolo | deepseek-v3-free | 0 credit requis |
| Explorer | R2D2 | deepseek-v3-free | Fallback (grok-search si credits dispo) |
| Messenger | — | qwen3-coder | Taches courtes, 0 credit |

**Modeles payants OpenRouter** (utiliser uniquement si credits disponibles) : `minimax-m25`, `glm-5`, `kimi-k2`, `grok-search`, `perplexity-pro`, `deepseek-v3` (sans `:free`).

**kimi-k2 ecarte** : Bug amont via OpenRouter — les tokens speciaux `<|tool_call_begin|>`, `<|tool_call_end|>` fuient dans le texte. Confirme charmbracelet/crush#725 + moonshotai/Kimi-K2-Instruct discussions#41.

**OpenRouter :free vs payant** : Les IDs de modeles OpenRouter ont une variante `:free` (ex: `openrouter/deepseek/deepseek-chat:free`) qui ne consomme pas de credits mais a des rate-limits de 20 req/min. Sans le suffixe `:free`, le modele est payant et echoue en 402 si le solde est epuise.

---

### 11.10 Plugins — Activation Obligatoire depuis v2026.2.22

**Breaking change v2026.2.22** : Tous les plugins "channel" (telegram, discord, whatsapp, slack…) sont desactives par defaut. Seuls ces 3 plugins sont charges automatiquement :
```
device-pair | phone-control | talk-voice
```

**Symptome** : Bot Telegram silencieux malgre `channels.telegram` correctement configure. Aucun log `[telegram]`. `channels list` retourne vide.

**Diagnostic** :
```bash
docker exec javisi_openclaw node /app/openclaw.mjs plugins list
# Si "telegram | disabled | bundled (disabled by default)" → fix requis
```

**Fix dans `openclaw.json.j2`** (OBLIGATOIRE depuis v2026.2.22) :
```json
"plugins": {
  "entries": {
    "telegram": { "enabled": true }
  }
}
```
Pour WhatsApp : ajouter `"whatsapp": { "enabled": true }`.

**Regle** : Apres chaque montee de version OpenClaw, verifier `plugins list`. Tout plugin `disabled (bundled by default)` doit etre active explicitement.

---

### 11.11 Doctor — Config Overwrite au Demarrage

**Symptome** : `[reload] config change detected … changedPaths=1` dans les logs a chaque redemarrage.

**Cause** : Le "doctor" OpenClaw ajoute les defaults de migration absents (ex: `agents.defaults.compaction: {mode: "safeguard"}`). Comportement normal.

**Regle** :
- `changedPaths=1` = doctor a ajoute 1 default de migration → **normal, ignorer**
- `changedPaths > 3` → investiguer (doctor corrige une config corrompue)
- Le doctor ne supprime jamais de cles existantes

---

### 11.12 Diagnostic "No API key found for provider openrouter" — Message Trompeur

**Symptome** : `[diagnostic] lane task error: No API key found for provider "openrouter"` en boucle dans les logs, meme si `OPENROUTER_API_KEY` est bien present dans l'env LiteLLM.

**Cause reelle** : Ce n'est PAS une cle manquante. C'est une erreur 402 (credits epuises) retournee par OpenRouter via LiteLLM, que le moteur d'auth OpenClaw (model-auth) reformate maladroitement en "No API key found".

**Verification** :
```bash
# Inspecter les sessions du concierge pour voir l'erreur reelle
docker exec javisi_openclaw sh -c \
  "grep -l openrouter /home/node/.openclaw/agents/concierge/sessions/*.jsonl | head -3 | \
   xargs -I{} grep 'OpenrouterException\|402\|credits' {} | head -10"
```

**Fix** : Changer les modeles des agents vers des variantes `:free` (voir 11.9) OU recharger le compte OpenRouter.

---

### 11.13 Subagent "spawn docker EACCES" — Sandbox non fonctionnel

**Symptome** : Logs `Error: spawn docker EACCES` dans les lanes `subagent` et `session:agent:<name>:subagent:*`. Le Concierge rapporte "Subagent writer failed" sans detail. Aucun sous-agent ne peut demarrer.

**Il y a 2 causes racines independantes — les deux doivent etre corrigees.**

#### Cause #1 — group_add manquant (socket inaccessible)

Le container OpenClaw tourne avec le user `node:1000`. Le socket Docker `/var/run/docker.sock` appartient au groupe `docker` (GID variable selon la distro, ex: 989 sur Debian). Sans `group_add`, le container ne peut pas acceder au socket.

**Diagnostic** :
```bash
# GID du groupe docker sur le host
getent group docker
ls -la /var/run/docker.sock  # srw-rw---- 1 root docker ...

# Groupes du container
docker exec javisi_openclaw id
# AVANT : uid=1000(node) gid=1000(node) groups=1000(node)        ← PAS de groupe docker
# APRES : uid=1000(node) gid=1000(node) groups=1000(node),989    ← OK
```

**Fix** : `group_add` dans `docker-compose.yml.j2`. Le GID est detecte dynamiquement par le role `docker-stack` ("Detect docker socket GID") :
```yaml
group_add:
  - "{{ docker_socket_gid | default('989') }}"
```
Redeploiement : `make deploy-role ROLE=docker-stack ENV=prod`

#### Cause #2 — Image `openclaw-sandbox:bookworm-slim` absente (CAUSE PRINCIPALE)

OpenClaw utilise `dockerode` (SDK Node.js) pour creer les containers sandbox via HTTP REST sur `/var/run/docker.sock`. Il ne fait PAS appel au binaire `docker` CLI. Quand il essaie de creer un sandbox, il cherche l'image `openclaw-sandbox:bookworm-slim` — si elle n'existe pas, la creation echoue avec `EACCES` (erreur generique de dockerode sur image not found).

L'image sandbox est embarquee dans l'image principale OpenClaw (`/app/Dockerfile.sandbox`) mais n'est PAS disponible en pull direct sur ghcr.io — elle doit etre construite localement sur le host.

**Note sur le PATH** : L'image OpenClaw inclut `/root/.bun/bin` dans le PATH (mode 700, inaccessible a node:1000). Si OpenClaw appelait `child_process.spawn("docker")`, le systeme retournerait EACCES lors du parcours du PATH. Mais OpenClaw utilise `dockerode` et non le CLI `docker`, donc cet EACCES PATH n'est PAS la cause du probleme de spawn des sous-agents.

**Diagnostic** :
```bash
# Verifier si l'image est presente
docker images | grep openclaw-sandbox
# Si absent → cause confirmee

# Verifier les logs pour les erreurs sandbox
docker logs javisi_openclaw 2>&1 | grep -i 'spawn\|sandbox\|EACCES'
```

**Fix** : Le role `openclaw` extrait maintenant `Dockerfile.sandbox` de l'image principale et construit l'image sandbox automatiquement. Redeploiement :
```bash
make deploy-role ROLE=openclaw ENV=prod
```
Les taches Ansible ajoutees (`roles/openclaw/tasks/main.yml`) :
1. `Check if openclaw-sandbox image already exists` — skip si deja construite (idempotent)
2. `Create openclaw-sandbox build directory` — `{{ openclaw_config_dir }}/build/openclaw-sandbox/`
3. `Extract Dockerfile.sandbox from openclaw image` — `docker run --rm --entrypoint cat`
4. `Write Dockerfile.sandbox to build directory`
5. `Build openclaw-sandbox image from embedded Dockerfile` — `community.docker.docker_image`

**Force rebuild apres upgrade OpenClaw** :
```bash
# Supprimer l'image pour forcer le rebuild au prochain deploy
docker rmi openclaw-sandbox:bookworm-slim
make deploy-role ROLE=openclaw ENV=prod
```

**Pourquoi le Concierge ne voit pas l'erreur** : Les erreurs de spawn sont dans la lane `diagnostic`, pas propagees au contexte de la session principale. Normal — si le sous-agent echoue immediatement (< 2s), la fenetre de poll `sessions_get` est manquee.

---

### 11.14 Kaneo — Endpoint d'Auth BetterAuth (Route Correcte) ⚠️ ARCHIVÉ — Kaneo remplacé par Palais

**Symptome** : Messenger Hermes ne crée rien dans Kaneo. Aucune tâche, aucun projet. Pas d'erreur visible (curl avec `-sf` masque les 404).

**Cause** : Kaneo utilise BetterAuth qui expose `/api/auth/sign-in/email` (pas `/api/auth/sign-in`). L'ancien endpoint retourne 404, le cookie n'est jamais extrait, toutes les opérations Kaneo échouent silencieusement.

```bash
# Mauvais (404)
curl -X POST http://kaneo-api:1337/api/auth/sign-in ...

# Correct (200 + Set-Cookie)
curl -X POST http://kaneo-api:1337/api/auth/sign-in/email ...
```

**Fichiers affectés** :
- `roles/openclaw/templates/agents/messenger/IDENTITY.md.j2` (2 occurrences)
- `roles/n8n-provision/files/workflows/code-review.json`
- `roles/n8n-provision/files/workflows/error-to-task.json`
- `roles/n8n-provision/files/workflows/github-autofix.json`
- `roles/n8n-provision/files/workflows/kaneo-agents-sync.json`
- `roles/n8n-provision/files/workflows/project-status.json`
- `roles/n8n-provision/templates/workflows/plan-dispatch.json.j2`

**Cookie Kaneo** : Format `__Secure-better-auth.session_token=<value>`. Le flag `__Secure-` est pour les navigateurs — `curl` l'utilise en HTTP interne sans problème.

**Diagnostic rapide** :
```bash
# Tester l'auth depuis le container openclaw
docker exec javisi_openclaw curl -s -o /dev/null -w '%{http_code}' \
  -X POST http://kaneo-api:1337/api/auth/sign-in/email \
  -H 'Content-Type: application/json' \
  -d '{"email":"<kaneo_agent_email>","password":"<kaneo_agent_password>"}'
# Attendu : 200
# Si 404 : mauvais endpoint
```

---

### 11.15 Kaneo — Doublons workspace_member (Double Provisioning) ⚠️ ARCHIVÉ

**Symptome** : Chaque agent apparait deux fois dans la liste des membres de l'espace de travail Kaneo.

**Cause** : Double provisioning — le rôle Ansible `roles/kaneo/tasks/main.yml` insère des membres avec des IDs hardcodés (`kaneo-agent-member-XX-XX`) ET le workflow n8n `kaneo-agents-sync` en insère avec des IDs dynamiques (`agXXagXX...`).

**Diagnostic** :
```bash
docker exec <project>_postgresql psql -U kaneo -d kaneo -t -c \
  "SELECT u.email, COUNT(*) FROM workspace_member m
   JOIN \"user\" u ON u.id = m.user_id
   GROUP BY u.email HAVING COUNT(*) > 1;"
```

**Fix ponctuel** :
```bash
# Supprimer les entrées hardcodées (les IDs dynamiques agXX sont les valides)
docker exec <project>_postgresql psql -U kaneo -d kaneo -t -c \
  "DELETE FROM workspace_member WHERE id LIKE 'kaneo-agent-member-%';"
```

**Fix permanent** : Supprimer la tâche `Add OpenClaw agents to workspace` de `roles/kaneo/tasks/main.yml` (la déléguer uniquement au workflow n8n `kaneo-agents-sync`).

---

### 11.16 workspaceAccess — Valeurs Valides et Écriture Sandbox

**Symptôme** : `write failed: Sandbox path is read-only; cannot create directories: /workspace`
Les sous-agents (writer, builder) ne peuvent pas créer de fichiers dans le sandbox.

**Cause** : `workspaceAccess: "none"` + `readOnlyRoot: true` = `/workspace` inaccessible en écriture.

**Valeurs valides** (schéma Zod OpenClaw v2026.2.22 — enum z.union z.literal) :
```
"none"  → pas d'accès workspace (défaut)
"ro"    → workspace monté en lecture seule
"rw"    → workspace monté en lecture/écriture
```
**⚠️ Piège** : `"write"`, `"read"`, `"readwrite"` → `Invalid input` (erreur config, container refuse de démarrer).

**Config correcte** :
```json
// defaults sandbox (agents qui écrivent: writer, builder, artist, explorer)
"workspaceAccess": "rw"

// override pour Messenger (API calls only, pas de FS)
"workspaceAccess": "none"
```

**Fichier** : `roles/openclaw/templates/openclaw.json.j2`

---

### 11.17 Provider openai Direct — OPENAI_API_KEY Requise dans le Container

**Symptôme** : `MissingEnvVarError: Missing env var "OPENAI_API_KEY" referenced at config path: models.providers.openai.apiKey`
Le container refuse de démarrer après l'ajout du provider `openai` dans `openclaw.json`.

**Cause** : Le provider `openai` dans `openclaw.json.j2` référence `${OPENAI_API_KEY}` mais cette variable n'était pas dans `openclaw.env.j2`.

**Architecture** :
- `custom-litellm/xxx` → via proxy LiteLLM → n'a besoin que de `LITELLM_API_KEY`
- `openai/xxx` → appel direct OpenAI → nécessite `OPENAI_API_KEY` dans l'env OpenClaw

**Fix** : Ajouter dans `openclaw.env.j2` :
```
OPENAI_API_KEY={{ openai_api_key }}
```
Variable `openai_api_key` déjà présente dans les secrets (utilisée par LiteLLM).

**Avantage** : Bypass LiteLLM = pas de dépendance aux crédits OpenRouter/Anthropic pour les appels OpenAI.
**Inconvénient** : Budget tracking LiteLLM inactif pour ces appels — surveiller dashboard OpenAI directement.

---

### 11.18 Handler `state: restarted` ne Relit pas env_file

**Symptôme** : Env file mis à jour (ex: `OPENAI_API_KEY` ajouté), handler déclenché, mais le container repart avec l'ancien environnement → `MissingEnvVarError`.

**Cause** : `state: restarted` = `docker compose restart` — commande qui redémarre le processus DANS le container existant. Le container existant garde son environnement initial. **Les `env_file` ne sont PAS relus.**

Pour relire un `env_file`, il faut recréer le container = `docker compose up -d`.

**Fix dans le handler** :
```yaml
# INCORRECT (ne relit pas env_file)
state: restarted

# CORRECT (force recreation, relit env_file)
state: present
recreate: always
```

**Fichier** : `roles/openclaw/handlers/main.yml`

**Note** : `recreate: always` force la recreation à chaque deploy même si rien n'a changé. Acceptable pour un handler (ne se déclenche que sur `changed`). Pour les autres services, préférer `state: present` sans `recreate: always` (Docker Compose détecte les changements d'env automatiquement).

### 11.19 Heartbeat + Cron — Non Supportes en v2026.2.22

**Symptome** : Les sections `heartbeat` et `cron` (array) dans `openclaw.json` sont ignorees silencieusement ou provoquent une erreur de validation au demarrage.

**Cause** : OpenClaw v2026.2.22 n'implemente pas encore les fonctionnalites heartbeat et cron planifie. Ces champs existent dans la documentation mais ne sont pas supportes par le runtime.

**Workaround** : Utiliser n8n cron comme alternative (ex: `kaneo-agents-sync` cron daily 6h).

**Fichier** : `roles/openclaw/templates/openclaw.json.j2` (commentaire ligne 490)

---

### 11.20 Kaneo API — Status Slug = Nom de Colonne Slugifie ⚠️ ARCHIVÉ

**Symptome** : `PUT /api/task/status/<id>` avec `{"status":"todo"}` retourne 400 ou ne deplace pas la tache.

**Cause** : Kaneo v2.2.1 utilise le **slug** de la colonne comme valeur de `status`. Le slug est genere automatiquement a partir du nom de la colonne (slugification).

**Mapping par defaut** :
| Nom colonne | Slug (valeur status) |
|---|---|
| Backlog | `backlog` |
| In Progress | `in-progress` |
| Review | `review` |
| Done | `done` |
| Draft | `draft` |
| Approved | `approved` |
| Rejected | `rejected` |

**Regle** : Le slug est le nom en minuscules avec espaces remplaces par des tirets. "To Do" → `to-do`, "In Review" → `in-review`.

**Impact** : Toute operation `create_task` (champ `status`) et `update_status` doit utiliser le slug exact de la colonne cible.

---

### 11.21 Kaneo API — external-link = Read-Only (GitHub Integrations) ⚠️ ARCHIVÉ

**Symptome** : `POST /api/external-link` retourne 404 ou "Method not allowed".

**Cause** : L'API `external-link` de Kaneo v2.2.1 est **read-only**. Seul `GET /api/external-link/task/:taskId` existe, pour lire les liens GitHub generes automatiquement par les integrations.

Il n'y a PAS de `POST` pour creer des liens manuellement.

**Workaround V1** (actif) : Stocker les livrables comme commentaires structures :
```
POST /api/activity/comment
{"taskId":"<id>","comment":"[DELIVERABLE] <titre> — <url>"}
```
Lire avec `GET /api/activity?taskId=<id>` et filtrer les commentaires `[DELIVERABLE]`.

**V2 (fork)** : Ajouter `POST /api/external-link` au fork Mobutoo/kaneo :
- Fichier : `apps/api/src/external-link/index.ts` (ajouter route POST)
- Controller : `apps/api/src/external-link/controllers/create-external-link.ts`
- Schema : table `external_link` a deja `taskId`, `url`, `title`, `integrationId` (nullable)
- Retirer contrainte FK `integrationId NOT NULL` si presente (liens manuels sans integration)

---

### 11.22 Kaneo API — Comment Field = `comment` pas `content` ⚠️ ARCHIVÉ

**Symptome** : `POST /api/activity/comment` avec `{"taskId":"...","content":"..."}` retourne 400 ou cree un commentaire vide.

**Cause** : L'endpoint attend le champ `comment`, pas `content`.

**Correct** :
```json
{"taskId":"<id>","comment":"<texte>"}
```

**Fichiers impactes** : IDENTITY messenger, workflows n8n (code-review, error-to-task).

---

### 11.23 Sandbox DinD — AGENTS.md/TOOLS.md/BOOTSTRAP.md ENOENT

**Symptome** : Sub-agents (messenger, builder, etc.) ne peuvent pas lire `AGENTS.md`, `TOOLS.md`, `BOOTSTRAP.md` dans leur sandbox. Logs :
```
[tools] read failed: Sandbox FS error (ENOENT): /home/node/.openclaw/sandboxes/agent-messenger-XXXX/AGENTS.md
```

**Cause** : Docker-in-Docker (DooD) path mismatch. Le Gateway OpenClaw ecrit les fichiers sandbox dans son filesystem containerise (`/home/node/.openclaw/sandboxes/`). Quand il spawn le sandbox container avec `-v /home/node/.openclaw/sandboxes/agent-X:/workspace`, Docker daemon resout ce path sur le **HOST** — ou il n'existe pas (le vrai path host est `/opt/<project>/data/openclaw/system/sandboxes/agent-X`).

**Fix** : Monter le volume OpenClaw en "identity mount" — le path container = le path host :
```yaml
# docker-compose.yml — avant (broken)
- /opt/javisi/data/openclaw/system:/home/node/.openclaw

# docker-compose.yml — apres (fixed)
- /opt/javisi/data/openclaw/system:/opt/javisi/data/openclaw/system
```
Et adapter `OPENCLAW_STATE_DIR` dans `openclaw.env` pour pointer vers le path host (`/opt/<project>/data/openclaw/system`).

**Fichiers modifies** : `docker-compose.yml.j2`, `openclaw.env.j2`, `openclaw.json.j2` (workspace paths).

**Verification** :
```bash
# Dans le sandbox, les fichiers doivent etre visibles
docker exec openclaw-sbx-agent-messenger-XXXX ls /workspace/AGENTS.md
# Attendu : /workspace/AGENTS.md (pas ENOENT)
```

---

## 12. Reseau & VPN

### 12.1 Reseaux Docker Isoles

| Reseau | Subnet | Internal | Services |
|---|---|---|---|
| `frontend` | 172.20.1.0/24 | Non | Caddy, Grafana |
| `backend` | 172.20.2.0/24 | Oui | PG, Redis, Qdrant, n8n, LiteLLM, OpenClaw, Caddy, Alloy, Grafana |
| `egress` | 172.20.4.0/24 | Non | n8n, LiteLLM, OpenClaw |
| `monitoring` | 172.20.3.0/24 | Oui | cAdvisor, VictoriaMetrics, Loki, Alloy, Grafana |
| `sandbox` | 172.20.5.0/24 | Oui | LiteLLM, OpenClaw sandbox containers |

### 12.2 Split DNS — Headscale extra_records

- **Objectif** : Les clients Tailscale résolvent les domaines admin vers l'IP Tailscale du VPS (100.64.x.x), pas l'IP publique
- **Config Headscale** (dans `config.yaml`) :
  ```yaml
  dns:
    override_local_dns: true   # CRITIQUE — force le DNS Tailscale sur les clients
    extra_records:
      - {name: "domain.tld", type: "A", value: "100.64.0.14"}
      - {name: "subdomain.domain.tld", type: "A", value: "100.64.0.14"}
  ```
- **`override_local_dns: false`** (défaut) : Tailscale ne force pas son DNS → Windows utilise le DNS de la box → résolution publique → ACL Caddy bloque
- **Architecture Docker** : Headscale tourne dans Docker sur Seko-VPN. Chemin host : `/opt/services/headscale/config/config.yaml`
- **Rôle Ansible** : `vpn-dns` — stratégie slurp/parse YAML/combine/write (pas de fichier JSON séparé)
- **Handler** : `community.docker.docker_compose_v2` (restart Headscale Docker, pas systemd)
- **Vérification client Windows** :
  ```powershell
  # Doit retourner 100.64.x.x (IP Tailscale), pas l'IP publique
  Resolve-DnsName mayi.ewutelo.cloud
  # Forcer via DNS Tailscale
  Resolve-DnsName mayi.ewutelo.cloud -Server 100.100.100.100
  ```
- **Si résolution retourne encore l'IP publique** : Vérifier "Use Tailscale DNS" = ON dans les settings Tailscale Windows

### 12.3 Headscale dans Docker — Chemins

| Chemin | Description |
|---|---|
| `/opt/services/headscale/config/config.yaml` | Config Headscale (host) |
| `/opt/services/headscale/` | Répertoire docker-compose |
| `/etc/headscale/config.yaml` | Même fichier vu depuis le container |

**Ne PAS** utiliser `/etc/headscale/` depuis l'hôte — c'est le chemin dans le container.

### 12.4 Smoke Tests

- **Non-bloquants par defaut** : `failed_when: false`, resultats en warning
- **Mode strict** : `smoke_test_strict: true` pour bloquer le playbook sur echec
- **Qdrant connectivity** : Via `docker exec` + `bash -c ':> /dev/tcp/localhost/6333'`
- **VPN-protected endpoints** : Resolus via IP Tailscale avec `curl --resolve`
- **LiteLLM health** : Requiert le header `Authorization: Bearer` dans le smoke test

---

### 12.5 Caddy Workstation — DNS-01 ACME echoue avec NOTIMP

**Symptome** : `ERR_SSL_PROTOCOL_ERROR` sur tous les subdomains du Pi. Logs Caddy :
```
could not determine zone for domain "_acme-challenge.studio.ewutelo.cloud":
unexpected response code 'NOTIMP' for ewutelo.cloud.
```

**Cause** : systemd-resolved (`127.0.0.53`) ne supporte pas les requetes NS/SOA
qu'envoie certmagic (Caddy) pour decouvrir la zone autoritaire avant le challenge
DNS-01. Le resolver local repond NOTIMP, bloquant toute emission de certificat.

**Verification** :
```bash
dig NS ewutelo.cloud          # status: NOTIMP — confirme le bug
dig NS ewutelo.cloud @8.8.8.8 # status: NOERROR, retourne dns20.ovh.net — domaine OK
```

**Solution** : Dans le Caddyfile workstation, utiliser `tls { dns ovh { ... } resolvers 8.8.8.8 1.1.1.1 }`
par site au lieu de `acme_dns ovh` global. La directive `resolvers` dans le bloc `tls`
force certmagic a utiliser des resolvers externes pour la decouverte de zone NS.

**Syntaxes invalides testees** :
- `resolvers 8.8.8.8` dans le bloc global → `unrecognized global option: resolvers`
- `acme_resolvers 8.8.8.8` dans le bloc global → `unrecognized global option: acme_resolvers`
- `resolvers 8.8.8.8` dans `acme_dns ovh { }` → `unrecognized subdirective 'resolvers'`
- `tls { issuer acme { resolvers ... } }` + `acme_dns` global → config "unchanged" (global surpasse le per-site)

**Syntaxe correcte** (Caddy v2.10, caddy-dns/ovh) :
```caddyfile
example.domain {
    tls {
        dns ovh {
            endpoint ovh-eu
            application_key {env.OVH_APPLICATION_KEY}
            application_secret {env.OVH_APPLICATION_SECRET}
            consumer_key {env.OVH_CONSUMER_KEY}
        }
        resolvers 8.8.8.8 1.1.1.1
    }
    reverse_proxy localhost:PORT
}
```

---

### 12.6 Split DNS — Subdomains Pi absents de Headscale extra_records

**Symptome** : `oc.ewutelo.cloud`, `studio.ewutelo.cloud`, `cut.ewutelo.cloud` resolvent
vers l'IP publique du VPS (`87.106.30.160`) depuis un client Headscale au lieu du Pi (`100.64.0.1`).
Les URLs restent inaccessibles meme avec Headscale VPN actif.

**Cause** : Le role `vpn-dns` tourne dans `site.yml` (sur prod-server) et lit
`hostvars[groups['workstation'][0]]['tailscale_ip']`. Mais `workstation.yml` est
un playbook **separe** — quand `site.yml` s'execute, le Pi n'a jamais tourne
`headscale-node`, donc le fait `tailscale_ip` est absent. Le guard defensif dans
`vpn-dns/defaults/main.yml` renvoie `''` → les records Pi sont silencieusement omis.

**Verification** :
```bash
# Sur le client Headscale (PC Windows via PowerShell) :
Resolve-DnsName oc.ewutelo.cloud
# Si "Address" = IP publique VPS → records Pi manquants dans Headscale

# Sur le Pi directement :
tailscale ip -4   # donne l'IP Tailscale du Pi (ex: 100.64.0.1)
```

**Solution** : Utiliser le playbook dedie `playbooks/vpn-dns.yml` qui collecte
d'abord les IPs Tailscale de TOUS les noeuds (prod + workstation), puis deploie
`vpn-dns` sur `vpn-server` avec les hostvars complets.

```bash
make deploy-vpn-dns
# ou : ansible-playbook playbooks/vpn-dns.yml
```

**Architecture du correctif** :
- Play 1 : `hosts: prod:workstation` — `tailscale ip -4` sur chaque noeud → fait `tailscale_ip`
- Play 2 : `hosts: vpn` — role `vpn-dns` avec `hostvars` complets incluant le Pi

**Pourquoi pas dans workstation.yml** : Le role `vpn-dns` tourne sur `vpn-server` (Seko-VPN),
pas sur le Pi. Ajouter un play `vpn` a `workstation.yml` coupleraient les deux playbooks.
Un playbook dedie est plus propre et reciblable independamment.

### 12.7 handle_response vs handle_errors — backend down

**Symptome** : `handle_response` dans Caddy ne capture pas les erreurs 502/503 quand le backend est arrete.

**Cause** : `handle_response` intercepte les **reponses HTTP** de l'upstream. Quand l'upstream est down,
il n'y a pas de reponse — c'est une **erreur Caddy interne**. Il faut `handle_errors`.

```caddyfile
# FAUX — ne fonctionne pas quand le backend est arrete
reverse_proxy localhost:3100 {
    handle_response @502 {
        respond "Service stopped" 502
    }
}

# CORRECT — capture les erreurs Caddy (backend unreachable)
reverse_proxy localhost:3100
handle_errors {
    @stopped expression `{http.error.status_code} in [502, 503]`
    respond @stopped "Service stopped" 502
}
```

### 12.8 Caddy handle_errors — ordre des matchers et fallback

Quand `handle_errors` doit gerer **differents types d'erreur** (502 pour service arrete, 403 pour VPN),
utiliser des matchers nommes avec `expression` pour filtrer, puis un fallback sans matcher :

```caddyfile
handle_errors {
    @stopped expression `{http.error.status_code} in [502, 503]`
    respond @stopped "Service en veille" 502

    # Fallback pour les autres erreurs (403, etc.)
    respond "Acces refuse" {http.error.status_code}
}
```

**Piege** : Ne pas mettre `import vpn_error_page` sur un site qui a deja un `handle_errors` custom —
deux blocs `handle_errors` au meme niveau causent un conflit. Integrer le fallback VPN directement
dans le `handle_errors` du site.

---

## 13. Systeme & Debian 13

### 13.1 Debian 13 (Trixie) — Specifique

- **`dash` par defaut** : Toutes les taches `shell` doivent avoir `executable: /bin/bash`
- **`apt_key` deprecie** : Utiliser `gpg --dearmor` + `signed-by=`
- **`apt-transport-https` supprime** : Ne pas l'inclure dans les paquets
- **Depots minimaux** : Verifier/corriger `/etc/apt/sources.list.d/debian.sources` avant le premier `apt update`

---

## 14. Palais (SvelteKit Dashboard)

### 14.1 Deploy bloqué — ansible.builtin.copy copie node_modules (204MB)

**Symptome** : `make deploy-role ROLE=palais` bloqué 10+ minutes sur `TASK [palais : Copy palais application source]`, aucune sortie.

**Cause** : `ansible.builtin.copy` avec `src: "{{ palais_app_dir }}/"` copie TOUT le répertoire y compris `node_modules` (204MB, ~40 000 fichiers). Ansible calcule un checksum pour chaque fichier via SSH → extrêmement lent. Or le Dockerfile fait `npm ci` lui-même, donc copier `node_modules` est inutile.

**Fix** : Remplacer `ansible.builtin.copy` par `ansible.posix.synchronize` avec exclusions :

```yaml
- name: Ensure palais app directory is writable by deploy user
  ansible.builtin.file:
    path: "/opt/{{ project_name }}/palais-app"
    state: directory
    owner: "{{ prod_user }}"
    group: "{{ prod_user }}"
    mode: "0755"
  become: true
  tags: [palais]

- name: Sync palais application source
  ansible.posix.synchronize:
    src: "{{ palais_app_dir }}/"
    dest: "/opt/{{ project_name }}/palais-app/"
    rsync_opts:
      - "--exclude=node_modules"
      - "--exclude=.svelte-kit"
      - "--exclude=build"
    delete: true
    dest_port: "{{ prod_ssh_port | int }}"
  notify: Restart palais
  tags: [palais]
```

**Résultat** : Copie 400KB de sources au lieu de 204MB → deploy en ~5s au lieu de timeout.

**Règle** : Pour tout rôle avec un `Dockerfile` qui fait `npm ci`, ne jamais copier `node_modules` via Ansible.

---

### 14.2 ansible.posix.synchronize — dest_port non résolu (Jinja2 template dans ansible_port)

**Symptome** :
```
argument 'dest_port' is of type str and we were unable to convert to int:
"'{{ ansible_port_override | default(prod_ssh_port) }}'" cannot be converted to an int
```

**Cause** : `ansible_port` dans `inventory/hosts.yml` est défini comme template Jinja2 (`{{ ansible_port_override | default(prod_ssh_port) }}`). Le module `synchronize` lit cette valeur avant résolution complète → reçoit la chaîne brute.

**Fix** : Spécifier `dest_port` explicitement avec la variable source résolue en entier :

```yaml
ansible.posix.synchronize:
  dest_port: "{{ prod_ssh_port | int }}"  # Pas ansible_port, mais prod_ssh_port directement
```

---

### 14.3 ansible.posix.synchronize + --rsync-path=sudo rsync — echec sudo

**Symptome** :
```
sudo: unrecognized option '--server'
rsync error: error in rsync protocol data stream (code 12)
```

**Cause** : `--rsync-path=sudo rsync` passe `sudo rsync --server ...` au shell remote. Certaines versions de sudo interprètent `--server` comme une option sudo au lieu de l'argument de la commande `rsync`.

**Fix** : Ne pas utiliser `--rsync-path=sudo rsync`. Créer le répertoire destination owned par `prod_user` (avec `become: true`) AVANT le sync, puis lancer `synchronize` sans `become` ni `--rsync-path`. Le rsync remote s'exécute en tant que `prod_user` qui a les droits en écriture.

---

### 14.4 SvelteKit + Drizzle ORM — position: number | null dans les composants

**Symptome** :
```
Type 'number | null' is not assignable to type 'number'.
Type 'null' is not assignable to type 'number'.
```
Au niveau du passage de `data.tasks` (Drizzle) → `<KanbanBoard tasks={data.tasks}>`.

**Cause** : Drizzle ORM retourne `position: number | null` (colonne nullable en DB), mais les types locaux des composants Svelte déclaraient `position: number`.

**Fix** : Mettre `position: number | null` dans TOUS les types de composants qui reçoivent des tasks (KanbanBoard, KanbanColumn, TaskCard, TaskDetail). Adapter les tris :

```typescript
// Avant (crash TypeScript)
.sort((a, b) => a.position - b.position)

// Après
.sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
```

---

## Commandes de Diagnostic Rapide

```bash
# Sante de tous les containers
docker ps --format "table {{.Names}}\t{{.Status}}"

# Logs d'un service (remplacer javisi_ par {{ project_name }}_)
docker logs --tail 50 javisi_grafana
docker logs --tail 50 javisi_n8n
docker logs --tail 50 javisi_litellm
docker logs --tail 50 javisi_openclaw

# Redeploy ciblé sans toucher au reste
ansible-playbook playbooks/site.yml --tags monitoring    # Grafana datasources + dashboards
ansible-playbook playbooks/site.yml --tags openclaw      # OpenClaw config
ansible-playbook playbooks/site.yml --tags litellm       # LiteLLM models
ansible-playbook playbooks/site.yml --tags n8n-provision # Workflows n8n

# Verifier la connexion PostgreSQL depuis Grafana
docker inspect javisi_grafana | grep '"IPAddress"'
docker exec javisi_grafana wget -qO- --post-data="{}" \
  "http://admin:PASSWORD@<IP_CONTAINER>:3000/api/datasources/uid/PostgreSQL-n8n/health"

# Tester un skill OpenClaw
docker exec javisi_openclaw node --input-type=module -e \
  "import{loadSkillsFromDir}from'@mariozechner/pi-coding-agent'; \
  const r=loadSkillsFromDir({dir:'/home/node/.openclaw/skills',source:'t'}); \
  console.log(r.skills.length,r.diagnostics)"

# LiteLLM — lister les modeles disponibles
docker exec javisi_litellm curl -sH \
  "Authorization: Bearer $(grep master_key /opt/javisi/configs/litellm/config.yaml | awk '{print $2}')" \
  http://localhost:4000/v1/models | jq '.data[].id'

# n8n — verifier la table model_scores
docker exec javisi_postgresql psql -U n8n -d n8n -c \
  "SELECT model, total_calls, likes, dislikes, score FROM model_scores ORDER BY score DESC;"
```

---


---

## 39. VPN-Only Mode — Bascule en un clic

### Architecture

```
Mode PUBLIC (make vpn-off) :
  Internet → ports 80+443 ouverts → Caddy (HTTP-01 ACME) → services
  /health public, webhooks directs sur le domaine principal

Mode VPN-ONLY (make vpn-on) :
  Admin UIs → VPN clients → Tailscale IP → port 443 (CIDR VPN) → Caddy (DNS-01 OVH)
  Webhooks  → Meta → hook.<domain> (Seko-VPN) → reverse proxy via mesh → VPS → n8n
  /health   → VPN-only (Uptime Kuma via mesh)
  Port 80   → fermé (ACME DNS-01)
  Port 443  → restreint au CIDR VPN par UFW
  ZERO dépendance tiers (Cloudflare Tunnel retiré)
```

### Commandes

```bash
make vpn-on       # Bascule mode VPN-only (confirmation requise)
make vpn-off      # Retour mode public
make vpn-status   # Affiche l'état actuel (safety-check)
```

### Clés Vault requises dans `secrets.yml`

```yaml
# === OVH API — ACME DNS-01 (mode VPN-only) ===
# URL: https://eu.api.ovh.com/createToken/
# Droits requis: GET/POST/PUT/DELETE /domain/zone/*, GET /auth/currentCredential
vault_ovh_endpoint: "ovh-eu"
vault_ovh_application_key: "VOTRE_APP_KEY"
vault_ovh_application_secret: "VOTRE_APP_SECRET"
vault_ovh_consumer_key: "VOTRE_CONSUMER_KEY"

# === Webhook Relay (Seko-VPN) ===
# IP publique de Seko-VPN (pour le DNS A record hook.<domain>)
vault_vpn_server_public_ip: "X.X.X.X"
# IP Tailscale du VPS (destination du relay via mesh)
vault_vps_tailscale_ip: "100.64.X.X"
```

### Ordre d'activation (PRÉREQUIS)

```
1. Créer les credentials OVH sur https://eu.api.ovh.com/createToken/
2. Ajouter les vault_ovh_* et vault_vpn_server_public_ip/vault_vps_tailscale_ip dans secrets.yml
3. Créer le DNS A record : hook.<domain> → IP publique Seko-VPN
4. Déployer le relay : make deploy-role ROLE=webhook-relay ENV=vpn
5. Vérifier : curl https://hook.<domain>/health → "relay-ok" 200
6. Basculer : make vpn-on
7. Vérifier : curl https://hook.<domain>/webhook/ig-comment → atteint n8n
8. Mettre à jour les URL webhook dans le dashboard Meta
```

### Variables atomiques (découplement de caddy_vpn_only_mode)

| Variable | Défaut | Effet si true |
|---|---|---|
| `caddy_acme_dns01` | `false` | Image Caddy custom (OVH), ACME DNS-01 |
| `caddy_no_port80` | `false` | Port 80 non exposé dans Docker |
| `caddy_webhook_relay` | `false` | Webhook paths acceptent trafic du relay |
| `caddy_vpn_only_mode` | `false` | Raccourci : active les 3 ci-dessus |
| `hardening_vpn_only_mode` | `false` | UFW: port 80 fermé, 443 restreint CIDR VPN |

### Sécurité — Dead Man Switch

Le playbook `vpn-toggle.yml` inclut un dead man switch :
- Avant le toggle : programme un revert UFW automatique dans 15 minutes via `at`
- Après le toggle réussi : annule le job `at`
- Si lockout : UFW revient en mode ouvert (ports 80+443) après 15 min

> Le paquet `at` est installé par le rôle `common`.

> **Ne jamais activer** `hardening_vpn_only_mode=true` manuellement sans le playbook
> `vpn-toggle.yml` — utiliser `make vpn-on` qui inclut les safety checks.

*Derniere mise a jour : 2026-02-25 — Session 11 (Phase 16 : Kaneo archivé, section Palais ajoutée)*

---

## 40. Palais (Cockpit IA — Remplace Kaneo)

> Palais est déployé sur `https://{{ palais_subdomain }}.{{ domain_name }}` (VPN-only).
> Container : `palais`, DB : `palais` (PostgreSQL partagé), Port interne : 3300.

### 40.1 Healthcheck

```bash
curl -sf https://palais.<domain>/api/health
# → {"status":"ok","db":"ok","version":"..."}
```

### 40.2 Logs

```bash
docker logs palais --tail 50 --follow
```

### 40.3 Base de données

```bash
# Compter les tâches
docker exec postgresql psql -U palais -d palais -c 'SELECT count(*) FROM tasks;'

# Lister les projets
docker exec postgresql psql -U palais -d palais -c 'SELECT id, name, slug FROM projects;'

# Réinitialiser une tâche bloquée en in-progress
docker exec postgresql psql -U palais -d palais -c \
  "UPDATE tasks SET status='backlog' WHERE id=<id>;"
```

### 40.4 Redémarrage

```bash
docker restart palais
# Vérifier la santé après restart
sleep 5 && curl -sf https://palais.<domain>/api/health
```

### 40.5 Migration Kaneo → Palais (one-shot)

```bash
# Dry run d'abord
cd /opt/<project>/palais/app
KANEO_DATABASE_URL="postgresql://kaneo:...@localhost:5432/kaneo" \
DATABASE_URL="postgresql://palais:...@localhost:5432/palais" \
npx tsx scripts/migrate-kaneo.ts --dry-run --verbose

# Migration réelle
npx tsx scripts/migrate-kaneo.ts --verbose
```

### 40.6 Rebuild image Palais (si code modifié)

```bash
# Via Ansible
ansible-playbook playbooks/site.yml --tags palais

# Manuel (urgence)
cd /opt/<project>/palais
docker build -t palais-local . && docker restart palais
```

---

## 41. NocoDB (Pipeline Production IA)

### 41.1 NocoDB crash-loop : password authentication failed for user "nocodb"

**Symptôme** : Container NocoDB en restart loop, logs :
```
ERROR [ExceptionHandler] error: password authentication failed for user "nocodb"
```

**Cause** : NocoDB utilisait une variable de mot de passe DIFFÉRENTE de celle avec laquelle
l'user PostgreSQL a été créé. Le projet utilise **un seul mot de passe partagé** pour tous
les users DB (`postgresql_password`), mais le template `nocodb.env.j2` référençait
`postgresql_nocodb_password` (variable distincte introduite par erreur).

**Règle** : Tous les users PostgreSQL (n8n, litellm, nocodb, etc.) utilisent `{{ postgresql_password }}`.
Ne jamais créer une variable `postgresql_xxx_password` séparée — `init.sql.j2` et
`provision-postgresql.sh.j2` créent tous les users avec `{{ postgresql_password }}`.

**Fix** :
```bash
# Dans roles/nocodb/templates/nocodb.env.j2
# AVANT (FAUX) :
NC_DB=pg://postgresql:5432?u=nocodb&p={{ postgresql_nocodb_password }}&d=nocodb
# APRÈS (CORRECT) :
NC_DB=pg://postgresql:5432?u=nocodb&p={{ postgresql_password }}&d=nocodb
```

**Vérifier le container actif** (le handler restart ne relit pas l'env_file — voir 11.18) :
```bash
docker inspect javisi_nocodb | python3 -c \
  'import sys,json; [print(e) for e in json.load(sys.stdin)[0]["Config"]["Env"] if "NC_DB" in e]'
# Si l'ancienne valeur apparaît → force recreate :
cd /opt/javisi && docker compose -f docker-compose.yml up -d --force-recreate nocodb
```

---

### 41.2 env_file non-rechargé après deploy (NocoDB ou autre service)

**Symptôme** : Le deploy Ansible montre `changed` sur le fichier env, le handler tourne,
mais le container utilise encore l'ancienne valeur d'env (`docker inspect` le confirme).

**Cause** : `state: restarted` = `docker compose restart` = recycle le processus SANS
recréer le container. L'env_file n'est relue qu'à la **création** du container.

**Fix handler** (voir aussi section 11.18) :
```yaml
# FAUX
state: restarted

# CORRECT
state: present
recreate: always  # force docker compose up --force-recreate
```

**Fix d'urgence manuel** :
```bash
cd /opt/javisi && docker compose -f docker-compose.yml up -d --force-recreate <service>
```

---

### 41.3 403 sur hq.ewutelo.cloud (comportement normal)

`hq.ewutelo.cloud` est VPN-only (`import vpn_only` dans Caddyfile).
La 403 est le comportement ATTENDU si tu n'es pas connecté à Tailscale.

**Checklist accès** :
1. Tailscale connecté sur le client
2. Split DNS actif (headscale `override_local_dns: true`)
3. `hq.ewutelo.cloud` doit résoudre vers l'IP Tailscale du VPS (100.x.x.x), pas l'IP publique

---

### 41.4 Provisioning NC_API_TOKEN

Voir `docs/GUIDE-NOCODB-TOKEN-AUTOMATION.md` pour les options d'automatisation.

Procédure manuelle :
```bash
# 1. UI : hq.ewutelo.cloud → Team & Auth → API Tokens → New Token → copier
# 2. ansible-vault edit inventory/group_vars/all/secrets.yml
#    → vault_nocodb_api_token: "valeur-réelle"
# 3. make deploy-role ROLE=nocodb ENV=prod
```

---

## 99. Archive — Kaneo (remplacé par Palais en Phase 16, 2026-02-25)

> Les sections 11.14, 11.15, 11.20, 11.21, 11.22 du chapitre OpenClaw/Kaneo sont marquées
> **⚠️ ARCHIVÉ** et conservées pour référence historique.
>
> Kaneo (usekaneo/kaneo fork Mobutoo) a été utilisé du 2026-02-15 au 2026-02-25 comme PM tool.
> Il est remplacé par **Palais** (SvelteKit dashboard custom) déployé en Phase 1-16 VPAI.
>
> Le rôle Ansible `roles/kaneo/` est conservé en archive mais désactivé dans `playbooks/site.yml`.
> La DB Kaneo est conservée en lecture seule (`docker exec postgresql psql -U kaneo -d kaneo`).
> Un backup final est disponible dans le répertoire backup Zerobyte.
