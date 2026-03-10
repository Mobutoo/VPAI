# REX — Session 16 — 2026-03-10

**Duree** : ~4h (session continuee, 1 compaction contexte)
**Objectif initial** : Terminer l'audit securite (items restants apres v2.3.1)
**Resultat** : Audit complet v2.4.0 — 25 containers healthy, 0 CRITICAL/HIGH restant

---

## Contexte

Session 15 avait stabilise le CI/CD (23/23 Molecule, 9/9 smoke tests). Les releases v2.3.0 (SSH/UFW) et v2.3.1 (6 fixes securite) couvraient les fondations. Restaient les items C3, M8, M6, H13 et la validation from-scratch.

---

## Track A — M8+M6+H13 : Hardening batch

### REX-74 — Caddy security headers DRY snippet

**Symptome** : 9 blocs `header { ... }` dupliques dans le Caddyfile, certains sans Referrer-Policy ni Permissions-Policy.

**Fix** : Snippet `(security_headers)` importe par toutes les 12 directives site. Headers normalises : HSTS, nosniff, X-Frame-Options SAMEORIGIN, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy camera/mic/geo/payment=(), -Server.

**Piege** : Le domaine principal override HSTS avec `preload` et X-Frame-Options avec `DENY` (empeche framing du portail admin). Les headers individuels apres `import security_headers` sont merges par Caddy (le dernier gagne pour un meme header).

**Principe** : DRY via snippets Caddy — un seul endroit a maintenir. Override individuel reste possible par header explicite apres l'import.

### REX-75 — read_only: true casse VictoriaMetrics et Alloy

**Symptome** : VictoriaMetrics crash `permission denied` sur fichiers cache. Alloy crash `mkdir data-alloy: read-only file system`.

**Cause VM** : `user: "65534:65534"` ajoute mais les fichiers data existants appartenaient a root. Le `recurse: true` dans Ansible chowne les repertoires mais les fichiers profonds restaient root.

**Fix VM** : `sudo chown -R 65534:65534 /opt/javisi/data/victoriametrics/` sur le VPS + tache Ansible avec `recurse: true`.

**Cause Alloy** : Alloy cree un repertoire `/data-alloy` au demarrage pour son etat interne. Avec `read_only: true`, impossible d'ecrire sur le rootfs.

**Fix Alloy** : Ajouter `tmpfs: [/data-alloy:size=50M]` en plus de `/tmp:size=10M`.

**Principe** : Quand on ajoute `read_only: true`, toujours verifier :
1. Les logs de premier demarrage (mkdir, write, mktemp)
2. Les repertoires que le process cree dynamiquement
3. Ajouter un tmpfs pour chaque path writable identifie
4. Si on change le user, chown -R recursivement les donnees EXISTANTES

### REX-76 — Grafana env_file permission denied

**Symptome** : `grafana.env` avec owner `472:472` (Grafana UID) et mode `0600` → Docker Compose ne peut pas lire le fichier.

**Cause** : Docker Compose lit les `env_file` cote HOST, pas dans le container. L'utilisateur qui lance `docker compose` (prod_user) doit pouvoir lire le fichier.

**Fix** : Owner `{{ prod_user }}:{{ prod_user }}` au lieu de `472:472`. Le fichier est lu par Docker Compose au deploy, pas par le container Grafana.

**Principe** : `env_file` ≠ volume mount. Les env_file sont lus par le daemon Docker Compose sur l'hote. Le container ne les voit jamais. Owner = utilisateur qui lance docker compose.

---

## Track B — C3 : Docker Socket Proxy (CRITICAL)

### REX-77 — 4 containers montent /var/run/docker.sock

**Analyse** : cAdvisor, Alloy, DIUN, OpenClaw — tous montaient le socket Docker en :ro. Seul OpenClaw a un besoin legitime d'ecriture (spawn sandbox containers via dockerode).

**Architecture choisie** :
- Tecnativa/docker-socket-proxy:v0.4.2 dans Phase A (docker-compose-infra.yml)
- HAProxy en read-only : POST=0, CONTAINERS/IMAGES/INFO/VERSION/EVENTS/NETWORKS/PING = lecture seule
- 3 services migres : cAdvisor (DOCKER_HOST env), Alloy (config HCL tcp://), DIUN (DOCKER_HOST env)
- OpenClaw garde l'acces direct (exception documentee)

### REX-78 — Socket proxy crash read-only filesystem

**Symptome** : Container en restart loop — `can't create /tmp/haproxy.cfg: Read-only file system`

**Cause** : Le socket proxy utilise un entrypoint qui genere `haproxy.cfg` dans `/tmp` au demarrage. Avec `read_only: true`, `/tmp` est en lecture seule.

**Fix** : Ajouter `tmpfs: [/run:size=1M, /tmp:size=5M]`. HAProxy a besoin de `/tmp` pour sa config generee et `/run` pour son socket runtime.

**Principe** : Les images basees sur HAProxy (dont docker-socket-proxy) gerent leur config dynamiquement. Toujours verifier le Dockerfile/entrypoint avant d'appliquer read_only.

### REX-79 — Alloy discovery.docker 403 sur /networks

**Symptome** : `Unable to refresh target groups: 403 Forbidden` toutes les 30 secondes dans les logs Alloy.

**Cause** : `discovery.docker` appelle `GET /v1.51/networks` pour calculer les labels reseau des containers. Le socket proxy avait `NETWORKS=0`.

**Fix** : `NETWORKS=1` dans la config du socket proxy. Lecture seule (POST=0 global), donc pas de risque de modification.

**Principe** : Alloy docker discovery a besoin de : CONTAINERS, IMAGES, EVENTS, NETWORKS, INFO, VERSION, PING. Tester chaque consommateur individuellement apres activation du proxy.

### REX-80 — DIUN n'avait aucun reseau explicite

**Symptome** : DIUN etait sur `javisi_default` (reseau Docker Compose par defaut) sans acces au socket proxy (sur `monitoring`).

**Fix** : `networks: [monitoring, egress]`. Monitoring pour le socket proxy, egress pour les verifications de registres et notifications Telegram.

**Principe** : Tout container doit avoir des reseaux explicites. Le reseau default Docker Compose n'est pas controle et n'a pas de visibilite sur les services des autres compose files.

---

## Track C — Validation from-scratch

### Checklist 9 points verifiee

1. Docker networks (5/5 pre-crees par role docker)
2. Phase ordering (docker → monitoring → docker-stack)
3. Socket proxy dans Phase A
4. DIUN sur monitoring+egress
5. Variables definies (image + resource limits)
6. Alloy config tcp://socket-proxy:2375
7. cAdvisor sans docker.sock, avec DOCKER_HOST
8. OpenClaw garde docker.sock (sandbox exception)
9. PGPASSWORD dans tous les psql commands (4 roles, 16+ appels)

---

## Items non retenus (risque accepte)

### H13 partiel — NocoDB/Plane en root

Images tierces (nocodb/nocodb, makeplane/plane-*) ne supportent pas officiellement le non-root. Deja proteges par : no-new-privileges, cap_drop ALL, reseaux internes.

### M14/H6 — HMAC webhooks

Deja implemente au niveau applicatif : N8N_WEBHOOK_HMAC_SECRET, GITHUB_WEBHOOK_SECRET, PLANE_WEBHOOK_SECRET. Meta webhooks transitent par VPN mesh (Seko-VPN relay).

---

## Metriques

| Metrique | Valeur |
|---|---|
| Containers | 25 (24 + socket-proxy) |
| Unhealthy | 0 |
| Commits cette session | 2 (8c68f2a, 780ce38) |
| Fichiers modifies | 5 |
| Release | v2.4.0 |
| Items audit resolus | 13/15 (2 risques acceptes) |

---

## Enseignements cles

1. **read_only + user change = double verification** : chown les donnees existantes ET ajouter tmpfs pour tous les paths writables.
2. **env_file ≠ volume** : Docker Compose lit les env_file sur l'hote, pas dans le container. Owner = utilisateur systeme.
3. **Socket proxy : tester chaque consommateur** : Le 403 Alloy sur /networks n'etait pas evident. Toujours verifier les logs apres migration.
4. **HAProxy images = tmpfs obligatoire** : L'entrypoint genere des fichiers de config dynamiques.
5. **OpenClaw = exception documentee** : Le socket direct est justifie pour le DooD pattern (Docker-outside-of-Docker).
6. **LiteLLM incompatible read_only** : LiteLLM v1.81.3 ecrit des migrations dans site-packages (`litellm_proxy_extras/migrations/`) et restructure ses fichiers UI au demarrage. `read_only: true` bloque le container en `health: starting` indefiniment.
