# TROUBLESHOOTING.md — Pieges Connus et REX

> **Usage** : Ce fichier regroupe tous les pieges decouverts en production.
> Lire si tu travailles sur un service specifique ou si tu rencontres une erreur.
> Reference principale : `docs/REX-FIRST-DEPLOY-2026-02-15.md` (historique complet).

---

## Table des Matieres

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
11. [OpenClaw](#11-openclaw)
12. [Reseau & VPN](#12-reseau--vpn)
13. [Systeme & Debian 13](#13-systeme--debian-13)

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

- **Admin UIs (Grafana, n8n, OpenClaw, Qdrant)** : Accessibles UNIQUEMENT via VPN
- **ACL Caddy** : `remote_ip {{ caddy_vpn_cidr }}` (100.64.0.0/10) sur les domaines admin
- **Split DNS OBLIGATOIRE** : Les clients VPN doivent resoudre les sous-domaines admin vers l'IP Tailscale du VPS
- **Sans split DNS** : Le trafic passe par Internet → Caddy voit l'IP publique → blocage meme si VPN actif
- **Config Headscale** : `dns.extra_records` avec les sous-domaines admin → IP Tailscale du VPS
- **Alternative** : `/etc/hosts` cote client avec les entries admin → IP Tailscale du VPS
- **Smoke tests** : Utilisent `--resolve domain:443:<TAILSCALE_IP>` pour forcer le routage VPN
- **VPN error page** : `error @blocked 403` + `handle_errors` (retourne HTTP 403, pas 200)

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

### 11.3 openclaw.json — Pieges de Config

- **`agents.defaults.model`** : Doit etre un objet `{"primary": "provider/model"}`, PAS une string
- **`channels.telegram`** : La cle est `botToken` (pas `token`)
- **`controlUi.basePath`** : `/` quand sous-domaine dedie
- **`trustedProxies`** : Necessaire derriere Caddy pour X-Forwarded-For
- **`allowInsecureAuth`** : Necessaire car WebCrypto requiert HTTPS ou localhost

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

### 11.9 Modeles — Assignation Open-Source First

| Agent | Persona | Modele | Justification |
|---|---|---|---|
| Concierge | Mobutoo | minimax-m25 | Function Calling #1 (76.8%) — kimi-k2 ecarte (tokens leakage) |
| Builder | Imhotep | qwen3-coder | Code gen FREE, excellent SWE-bench |
| Writer | Thot | glm-5 | Agent-oriented, low hallucination |
| Artist | Basquiat | minimax-m25 | 1M context, multimodal |
| Tutor | Piccolo | minimax-m25 | kimi-k2 ecarte (tokens leakage) |
| Explorer | R2D2 | grok-search | #1 Search Arena, web+X natif |

**kimi-k2 ecarte** : Bug amont via OpenRouter — les tokens speciaux `<|tool_call_begin|>`, `<|tool_call_end|>` fuient dans le texte. Confirme charmbracelet/crush#725 + moonshotai/Kimi-K2-Instruct discussions#41.

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

### 12.2 Smoke Tests

- **Non-bloquants par defaut** : `failed_when: false`, resultats en warning
- **Mode strict** : `smoke_test_strict: true` pour bloquer le playbook sur echec
- **Qdrant connectivity** : Via `docker exec` + `bash -c ':> /dev/tcp/localhost/6333'`
- **VPN-protected endpoints** : Resolus via IP Tailscale avec `curl --resolve`
- **LiteLLM health** : Requiert le header `Authorization: Bearer` dans le smoke test

---

## 13. Systeme & Debian 13

### 13.1 Debian 13 (Trixie) — Specifique

- **`dash` par defaut** : Toutes les taches `shell` doivent avoir `executable: /bin/bash`
- **`apt_key` deprecie** : Utiliser `gpg --dearmor` + `signed-by=`
- **`apt-transport-https` supprime** : Ne pas l'inclure dans les paquets
- **Depots minimaux** : Verifier/corriger `/etc/apt/sources.list.d/debian.sources` avant le premier `apt update`

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

## 39. VPN-Only Mode — Variables Vault Requises

### Nouvelles clés à ajouter dans `secrets.yml` (ansible-vault edit)

```yaml
# === OVH API — ACME DNS-01 (mode VPN-only) ===
# URL: https://eu.api.ovh.com/createToken/
# Droits requis:
#   GET    /domain/zone
#   GET    /domain/zone/*
#   POST   /domain/zone/*/record
#   PUT    /domain/zone/*/record/*
#   DELETE /domain/zone/*/record/*
#   POST   /domain/zone/*/refresh
#   GET    /auth/currentCredential
vault_ovh_endpoint: "ovh-eu"
vault_ovh_application_key: "VOTRE_APP_KEY"
vault_ovh_application_secret: "VOTRE_APP_SECRET"
vault_ovh_consumer_key: "VOTRE_CONSUMER_KEY"

# === Cloudflare Tunnel — Webhooks Meta (mode VPN-only) ===
# URL: Cloudflare Dashboard > Zero Trust > Networks > Tunnels > Create tunnel
# Type: Cloudflared | Nom: seko-webhooks
# Public hostname: webhook.<domain> → Service: HTTP://localhost:443
# Copier le token affiché lors de la création
vault_cloudflare_tunnel_token: "VOTRE_TUNNEL_TOKEN"
```

### Ordre d'activation (PRÉREQUIS — ne pas brûler les étapes)

```
1. Créer les credentials OVH sur https://eu.api.ovh.com/createToken/
2. Ajouter les vault_ovh_* dans secrets.yml
3. Tester: ansible-playbook ... --tags caddy --extra-vars "caddy_vpn_only_mode=true" --check
4. Créer le Cloudflare Tunnel dans le dashboard (mode connecté)
5. Ajouter vault_cloudflare_tunnel_token dans secrets.yml
6. Activer: dans main.yml → caddy_vpn_only_mode: true, hardening_vpn_only_mode: true
7. Déployer: make deploy-prod
8. Vérifier: curl https://<domain>/health depuis l'extérieur → "OK" 200
9. Vérifier: curl https://<domain>/webhook/ig-comment depuis l'extérieur → atteint n8n
10. Vérifier SSH: connexion depuis Headscale uniquement (VPN requis)
```

### Variables conditionnelles (off par défaut)

| Variable | Défaut | Effet si true |
|---|---|---|
| `caddy_vpn_only_mode` | `false` | Image Caddy custom (OVH), acme_dns, no port 80, webhooks publics |
| `hardening_vpn_only_mode` | `false` | UFW: port 80 fermé, 443 restreint CIDR VPN |

> **Ne jamais activer** `hardening_vpn_only_mode=true` avant que `caddy_vpn_only_mode=true`
> soit déployé ET que les certificats DNS-01 soient valides — risque de lockout HTTP.

*Dernière mise à jour : 2026-02-18 — Session 6 (VPN-only préparation)*
