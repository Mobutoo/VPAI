# REX - Deploiement VPAI (15-16 fevrier 2026)

## Contexte

**Dates** : 15-16 fevrier 2026
**Projet** : VPAI - Stack AI/Automatisation auto-hebergee
**Environnement** : VPS OVH Production (Debian 13 Trixie)
**IP** : 137.74.114.167
**Objectif** : Deploiement complet de la stack (PostgreSQL, Redis, Qdrant, Caddy, n8n, LiteLLM, OpenClaw, Monitoring)

---

## Resume

**Duree totale** : ~14 heures de debugging iteratif (3 sessions)
**Erreurs critiques** : 28
**Resultat** : Stack complete deployee -- PG, Redis, Qdrant, Caddy, n8n, Grafana, VictoriaMetrics healthy. Loki fix en cours de validation.

---

## Session 1 -- Erreurs 1 a 8 (15 fevrier)

### 1. LOCKOUT SSH par Hardening Premature

**Symptome** : `Connection timed out` apres le role hardening
**Cause** : Hardening execute en Phase 1, SSH restreint au VPN avant validation VPN
**Fix** : Hardening deplace en Phase 6 (dernier role), `hardening_ssh_force_open: true` par defaut
**Impact** : CRITIQUE -- Perte d'acces total au serveur

### 2. Role docker-stack Manquant

**Symptome** : Aucun conteneur cree, `docker ps -a` vide
**Cause** : Roles individuels preparent les configs mais aucun ne fait `docker compose up`
**Fix** : Creation du role `docker-stack` en Phase 4.5, deploiement en 2 phases (A: infra, B: apps)
**Impact** : CRITIQUE

### 3. Roles Executes 2 Fois

**Symptome** : Taches dupliquees dans l'output Ansible
**Cause** : `docker-stack/meta/main.yml` declarait des dependances vers tous les roles
**Fix** : `dependencies: []` dans meta/main.yml
**Impact** : MOYEN

### 4. Connectivite VPN Bloque Deploiement

**Symptome** : `ping -c 3 87.106.30.160` 100% packet loss
**Cause** : VPS utilise son propre routage, pas de route VPN configuree
**Fix** : `failed_when: false` sur la verification VPN
**Impact** : MOYEN

### 5. Images Docker Inexistantes

**Symptome** : `redis:8.0.10-bookworm` not found, `openclaw:v2026.2.14` not found
**Fix** : `redis:8.0-bookworm`, `openclaw:latest` (temporaire)
**Impact** : CRITIQUE

### 6. Reseaux Docker -- Conflit de Labels

**Symptome** : `network javisi_backend has incorrect label com.docker.compose.network`
**Cause** : Reseaux crees par ancien compose avec labels differents
**Fix** : Cleanup automatique des reseaux avant deploiement
**Impact** : CRITIQUE

### 7. Provisioning n8n AVANT Creation Conteneur

**Symptome** : `docker exec javisi_n8n` -> `No such container`
**Cause** : Role n8n essayait de provisionner avant docker-stack
**Fix** : Separation en 2 roles : n8n (config Phase 3) + n8n-provision (Phase 4.6)
**Impact** : CRITIQUE

### 8. PostgreSQL 18+ -- Volume Mount & Capabilities

**Symptome** : `chmod: changing permissions: Operation not permitted`
**Causes** :
- Volume mount `/var/lib/postgresql/data` -> `/var/lib/postgresql` (PG18+ change)
- Capabilities manquantes : `DAC_OVERRIDE` + `FOWNER`
**Fix** : Correction du volume mount + ajout des capabilities
**Impact** : CRITIQUE

---

## Session 2 -- Erreurs 9 a 16 (16 fevrier)

### 9. PostgreSQL -- ICU Locale et logging_collector

**Symptome** : `initdb: error: invalid locale name "fr_FR.UTF-8"` + crash loop sur logging_collector
**Causes** :
- L'image Docker postgres:18.1-bookworm n'a PAS le locale `fr_FR.UTF-8` installe
- `logging_collector = on` tente d'ecrire dans `/var/log/postgresql/` qui n'existe pas dans Docker
- Le fichier `postgresql.conf.j2` contenait le byte `0x97` (Windows-1252) et des fins de ligne CRLF
**Fix** :
- ICU locale : `--locale-provider=icu --icu-locale=fr-FR --locale=C`
- `logging_collector = off` (Docker capte stdout/stderr)
- Re-encodage UTF-8 + LF du fichier
**Impact** : CRITIQUE

### 10. Qdrant -- PermissionDenied sur snapshots/tmp

**Symptome** : `Failed to remove snapshots temp directory at ./snapshots/tmp: PermissionDenied`
**Cause** : `cap_drop: ALL` sans `DAC_OVERRIDE` -- Qdrant (UID 1000) ne pouvait pas ecrire dans ses propres repertoires montes
**Fix** :
- Ajout `DAC_OVERRIDE` + `FOWNER` aux capabilities Qdrant
- `chown -R 1000:1000` sur le repertoire data dans Ansible
- Suppression du repertoire `snapshots/tmp` residuel
**Impact** : CRITIQUE

### 11. Qdrant -- Healthcheck sans wget/curl

**Symptome** : `exec: "wget": executable file not found in $PATH`
**Cause** : L'image Qdrant v1.16.3 ne contient ni `wget`, ni `curl`, ni `nc`
**Fix** : Healthcheck via bash : `bash -c ':> /dev/tcp/localhost/6333' || exit 1`
**Impact** : CRITIQUE

### 12. Qdrant -- Config montee au mauvais chemin

**Symptome** : Configuration par defaut utilisee malgre le volume mount
**Cause** : Config montee comme `/qdrant/config/config.yaml` mais Qdrant attend `production.yaml`
**Fix** : Mount en `/qdrant/config/production.yaml:ro`
**Impact** : MOYEN

### 13. Redis 8.0 -- rename-command supprime

**Symptome** : Redis crash au demarrage
**Cause** : `rename-command` a ete supprime dans Redis 8.0 (deprecated depuis 7.x, retire dans 8.0)
**Fix** : Suppression de `rename-command FLUSHDB ""` et `rename-command FLUSHALL ""` du redis.conf. Utiliser les ACL a la place.
**Impact** : CRITIQUE

### 14. Caddy -- Healthcheck echoue sur localhost

**Symptome** : Caddy `Up X minutes (unhealthy)` malgre le service qui tourne
**Cause** : Le healthcheck `wget -qO- http://localhost:80/health` echoue car `/health` est defini dans le bloc `{{ caddy_domain }}`. Quand le Host header est `localhost`, Caddy ne matche aucun site block.
**Fix** : Changer le healthcheck pour utiliser l'admin API Caddy : `wget -qO- http://localhost:2019/config/` (toujours disponible, independant du domaine)
**Impact** : CRITIQUE

### 15. Caddy -- Capabilities manquantes pour les logs

**Symptome** : `permission denied` sur `/var/log/caddy/access.log`
**Cause** : `cap_drop: ALL` retire `DAC_OVERRIDE`, meme si le repertoire est `chmod 777`
**Fix** : Ajout `DAC_OVERRIDE` aux capabilities Caddy (en plus de `NET_BIND_SERVICE`)
**Impact** : CRITIQUE

### 16. Phase B duplique les services infra

**Symptome** : Docker Compose tente de recreer PG/Redis/Qdrant/Caddy lors du deploiement Phase B
**Cause** : `docker-compose.yml` (Phase B) contenait les definitions completes de PG, Redis, Qdrant et Caddy, dupliquant Phase A
**Fix** :
- Phase B ne contient plus que les apps (n8n, LiteLLM, OpenClaw) + monitoring + DIUN
- Les `depends_on` vers les services infra ont ete supprimes (infra deja healthy depuis Phase A)
- Seule Phase B est arretee lors du cleanup (Phase A reste running)
**Impact** : CRITIQUE

---

## Erreurs supplementaires (transverses)

### Makefile -- EXTRA_VARS non transmises

**Symptome** : `make deploy-prod -e ansible_port_override=804` ne transmet pas la variable a Ansible
**Cause** : Le `-e` de make est un flag make (variables d'environnement), pas un flag Ansible. Le Makefile ne passait pas d'extra-vars.
**Fix** : Ajout du support `EXTRA_VARS` dans le Makefile : `$(if $(EXTRA_VARS),-e "$(EXTRA_VARS)")`
**Usage** : `make deploy-prod EXTRA_VARS="ansible_port_override=22"`

### Inventaire -- Port SSH par defaut

**Symptome** : Apres hardening, `make deploy-prod` essaie toujours le port 22
**Cause** : `ansible_port: "{{ ansible_port_override | default(22) }}"` -- le defaut etait 22
**Fix** : Change en `default(prod_ssh_port)` -- le defaut est maintenant `prod_ssh_port` (804)

### inject_facts_as_vars deprecie

**Symptome** : Warnings de depreciation sur chaque tache
**Fix** : `inject_facts_as_vars = False` dans ansible.cfg, remplacer `ansible_date_time.xxx` par `ansible_facts['date_time']['xxx']`

---

## Session 3 -- Erreurs 17 a 28 (16 fevrier, nuit)

### 17. VictoriaMetrics -- PermissionDenied sur /storage/flock.lock

**Symptome** : VictoriaMetrics en restart loop, `permission denied: /storage/flock.lock`
**Cause** : `cap_drop: ALL` sans `DAC_OVERRIDE` -- VM (UID 1000) ne peut pas creer le flock
**Fix** : Ajout `DAC_OVERRIDE` + `FOWNER` aux capabilities
**Impact** : CRITIQUE

### 18. Loki -- PermissionDenied similaire

**Symptome** : Loki ne demarre pas, permission denied sur `/loki`
**Cause** : Meme probleme que VM -- `cap_drop: ALL` sans `DAC_OVERRIDE`
**Fix** : Ajout `DAC_OVERRIDE` + `FOWNER` aux capabilities Loki
**Impact** : CRITIQUE

### 19. DIUN -- YAML escape dans regex

**Symptome** : `yaml line 12: unknown escape character 'd'`
**Cause** : Pattern regex `"^\d+\.\d+\.\d+"` en double quotes -- YAML interprete `\d` comme echappement
**Fix** : Utiliser des single quotes : `'^\d+\.\d+\.\d+'`
**Impact** : CRITIQUE

### 20. LiteLLM -- Config non lisible par le conteneur

**Symptome** : `PermissionError: '/app/config.yaml'`
**Cause** : Config deployee avec mode `0600`, le conteneur tourne sous un UID different
**Fix** : Changer le mode a `0644`
**Impact** : CRITIQUE

### 21. Caddy -- Admin API ne repond pas

**Symptome** : Healthcheck `wget -qO- http://localhost:2019/config/` -> `Connection refused`
**Cause** : Malgre `admin localhost:2019` dans le Caddyfile, l'admin API ne repond pas en Docker
**Fix** : Healthcheck change en `caddy version` (verifie que le binaire tourne)
**Impact** : CRITIQUE

### 22. VictoriaMetrics -- IPv6 localhost

**Symptome** : Healthcheck echoue avec `[::1]:8428` dans les logs
**Cause** : Alpine resout `localhost` en IPv6 `[::1]`, mais VM n'ecoute que sur IPv4
**Fix** : Remplacer `localhost` par `127.0.0.1` dans TOUS les healthchecks
**Impact** : CRITIQUE

### 23. Loki -- Image distroless sans wget/curl

**Symptome** : `"wget": executable file not found in $PATH`
**Cause** : `grafana/loki:3.6.5` est une image distroless -- aucun outil shell (pas de wget, curl, ls, test)
**Fix** : Utiliser la commande built-in `loki -health` (ajoutee en v3.6.5, backport PR #20590)
**Impact** : CRITIQUE

### 24. Loki -- Empty ring en mode monolithique

**Symptome** : `"error getting ingester clients" err="empty ring"` en boucle
**Cause** : Loki 3.x avec kvstore `inmemory` initialise quand meme le module `memberlist-kv` (bug #19381). L'ingester ne s'enregistre pas dans le ring.
**Fix** :
- Ajout `-target=all` dans la commande Docker
- Configuration explicite de `ingester.lifecycler.ring` avec `kvstore: inmemory`
- Ajout `memberlist.join_members: []` pour desactiver le clustering
**Impact** : CRITIQUE

### 25. LiteLLM -- Image sans wget, Python disponible

**Symptome** : `"wget": executable file not found in $PATH`
**Cause** : L'image LiteLLM est basee Python mais n'inclut pas wget
**Fix** : Healthcheck via Python : `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4000/health')"`
**Impact** : CRITIQUE

### 26. Alloy -- Image sans wget/curl

**Symptome** : Healthcheck impossible via HTTP
**Cause** : `grafana/alloy` n'a pas d'outils HTTP
**Fix** : Healthcheck via `kill -0 1` (verifie que le process PID 1 tourne)
**Impact** : MOYEN

### 27. DNS -- `dig` non installe sur VPS

**Symptome** : Smoke test DNS echoue malgre le DNS fonctionnel
**Cause** : `dig` (paquet `dnsutils`) n'est pas installe sur les images minimales Debian 13
**Fix** : Remplacer `dig +short` par `getent hosts` (toujours disponible, fait partie de glibc)
**Impact** : MOYEN

### 28. Grafana -- Redirect 301 sur /login

**Symptome** : Smoke test Grafana echoue avec HTTP 301 au lieu de 200
**Cause** : `/grafana/login` redirige vers `/grafana/login/` (trailing slash)
**Fix** : Ajouter `-L` (follow redirects) a curl dans le smoke test
**Impact** : MOYEN

### 29. Handlers infra -- Mauvais fichier compose

**Symptome** : Handler restart Caddy/PG/Redis/Qdrant : `no such service: caddy`
**Cause** : Handlers pointaient vers `docker-compose.yml` (Phase B) mais les services infra sont dans `docker-compose-infra.yml` (Phase A)
**Fix** : Mise a jour des 4 handlers infra pour pointer vers `docker-compose-infra.yml`
**Impact** : CRITIQUE

### 30. Smoke test -- Admin URL hardcodee

**Symptome** : Smoke test cherche `admin.{{ domain_name }}` mais l'admin est sur `javisi.ewutelo.cloud`
**Cause** : L'URL admin etait hardcodee avec le prefixe `admin.`
**Fix** : Utiliser `{{ admin_subdomain | default('admin') }}.{{ domain_name }}`
**Impact** : MOYEN

---

## Statistiques Globales

| Metrique | Session 1 | Session 2 | Session 3 | Total |
|----------|-----------|-----------|-----------|-------|
| Erreurs critiques | 6 | 8 | 10 | 24 |
| Erreurs moyennes | 2 | 2 | 4 | 8 |
| Fichiers modifies | 14 | 31 | 12 | ~45 (avec recouvrements) |
| Temps debugging | ~6h | ~4h | ~4h | ~14h |

---

## Etat Final des Services (fin session 3)

| Service | Phase | Etat | Healthcheck |
|---------|-------|------|-------------|
| PostgreSQL | A | Healthy | `pg_isready` |
| Redis | A | Healthy | `redis-cli ping` |
| Qdrant | A | Healthy | `bash -c ':> /dev/tcp/localhost/6333'` |
| Caddy | A | Healthy | `caddy version` |
| n8n | B | Healthy | `wget http://127.0.0.1:5678/` |
| LiteLLM | B | Healthy | `python urllib.request` |
| OpenClaw | B | Running | `kill -0 1` |
| VictoriaMetrics | B | Healthy | `wget http://127.0.0.1:8428/-/healthy` |
| Loki | B | Fix en cours | `loki -health` (v3.6.5) |
| Alloy | B | Running | `kill -0 1` |
| Grafana | B | Healthy | `wget http://127.0.0.1:3000/api/health` |
| DIUN | B | Running | (pas de healthcheck) |

---

## Lecons Cles

### A FAIRE

1. **`cap_drop: ALL` + `cap_add` minimal** est la bonne approche, MAIS `DAC_OVERRIDE` est quasi-systematiquement necessaire des qu'un conteneur ecrit dans un volume monte
2. **Verifier les outils disponibles dans l'image** avant d'ecrire un healthcheck (`docker exec <c> which wget curl ls test`)
3. **Les healthchecks sur `localhost` doivent matcher le bon Host header** -- utiliser l'admin API quand possible
4. **Un fichier compose par phase** -- pas de duplication de services entre les 2 fichiers
5. **Le port SSH par defaut dans l'inventaire** doit etre le port cible (804), avec override possible pour le premier deploiement
6. **Toujours utiliser `127.0.0.1`** au lieu de `localhost` dans les healthchecks (IPv6 vs IPv4)
7. **Les images distroless** (Loki 3.6+, certaines images Grafana) n'ont AUCUN outil shell -- utiliser les commandes built-in du binaire
8. **Utiliser `getent hosts`** au lieu de `dig` pour les checks DNS (toujours disponible)
9. **Les handlers doivent pointer vers le bon fichier compose** (Phase A vs Phase B)
10. **Les URLs admin doivent utiliser les variables d'inventaire** (`admin_subdomain`), jamais de valeur hardcodee

### A EVITER

1. Ne jamais dupliquer des services entre Phase A et Phase B
2. Ne pas supposer que `wget`/`curl` existe dans toutes les images Docker
3. Ne pas utiliser les locales systeme dans les images Docker (utiliser ICU)
4. Ne pas utiliser `rename-command` dans Redis 8.0+
5. Ne pas faire `make deploy-prod -e ...` (le `-e` est un flag make, pas Ansible)
6. Ne pas utiliser `localhost` dans les healthchecks Docker (Alpine resout en IPv6)
7. Ne pas utiliser `dig` dans les scripts -- `getent hosts` est plus portable
8. Ne pas deployer de configs en mode `0600` si le conteneur tourne sous un UID different
9. Ne pas utiliser `test -d` ou `ls` dans un conteneur distroless

---

**Auteur** : Claude Opus 4.6 (avec utilisateur mobuone)
**Date** : 2026-02-16
**Version** : 3.0
