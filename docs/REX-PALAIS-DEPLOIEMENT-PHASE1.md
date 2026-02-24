# REX — Palais Phase 1 : Déploiement initial (2026-02-24)

> **A LIRE OBLIGATOIREMENT avant de démarrer chaque phase Palais.**
> Consulter aussi `docs/TROUBLESHOOTING.md` pour les pièges généraux de la stack.

---

## 1. Bugs critiques rencontrés

### 1.1 Login impossible — endpoint bloqué par le middleware auth

**Symptôme :** Aucun mot de passe ne fonctionne à `/login`. Ni `admin` ni le mot de passe configuré.

**Cause :** `hooks.server.ts` bloque TOUTES les routes `/api/*` non listées dans `publicPaths`. `/api/auth/login` n'y était pas, donc le middleware retournait 401 avant même que le handler vérifie le mot de passe.

**Fix :** Ajouter `/api/auth/login` (et toute route publique nouvelle) dans `publicPaths` dès la création.

```typescript
// TOUJOURS vérifier : chaque nouvelle route /api/* accessible sans auth doit être dans publicPaths
const publicPaths = ['/login', '/api/auth/login', '/api/health', '/dl/'];
```

**Règle DoD :** Tester le login AVANT de passer au déploiement. `POST /api/auth/login` avec mauvais mot de passe doit retourner `{"error":"Invalid password"}` et non `{"error":"Unauthorized"}`.

---

### 1.2 Tables DB absentes en prod — migrations non générées

**Symptôme :** 500 au chargement du dashboard. Logs : `Failed query: select ... from "agents"`.

**Cause :** `drizzle-kit generate` jamais exécuté. Le dossier `drizzle/` était vide. Les tables n'existent pas en base.

**Fix appliqué :** Génération manuelle du SQL `drizzle/0000_init.sql` + application via `docker exec -i javisi_postgresql psql -U palais -d palais < /tmp/init.sql`.

**Règle DoD :** Vérifier que `drizzle/` contient au moins un fichier `.sql` AVANT le déploiement. Après déploiement, tester `GET /api/health` (DB ping) et `GET /api/v1/agents` (query table).

**Pour les prochaines phases :** Si une phase ajoute des colonnes ou tables, générer le SQL de migration et l'appliquer :
```bash
# En local (si DB accessible) :
DATABASE_URL="..." npx drizzle-kit generate
# En prod :
scp migration.sql serveur:/tmp/ && ssh ... 'docker exec -i javisi_postgresql psql -U palais -d palais < /tmp/migration.sql'
```

---

### 1.3 Handler Ansible `state: restarted` ne rebuild pas l'image Docker

**Symptôme :** Deploy Ansible terminé avec succès, mais les changements de code source n'apparaissent pas en production. L'ancienne image continue de tourner.

**Cause :** `community.docker.docker_compose_v2` avec `state: restarted` redémarre le container **existant** sans reconstruire l'image. Les changements dans `palais-app/` (source copiée par `ansible.builtin.copy`) ne sont pas pris en compte.

**Fix appliqué :** Handler modifié avec `state: present + recreate: always + build: always`.

**Règle DoD :** Après un déploiement, vérifier que la version du code en prod correspond bien aux dernières modifications (ex: vérifier une chaîne de caractères récente dans les logs ou une réponse API).

---

### 1.4 `docker compose restart` ne recharge pas `env_file`

**Symptôme :** Changement de `PALAIS_ADMIN_PASSWORD` en vault + redéploiement Ansible, mais l'ancien mot de passe fonctionne toujours.

**Cause :** `docker compose restart` redémarre le container avec les anciennes variables d'environnement. `env_file` est chargé uniquement à la **création** du container, pas au restart.

**Fix :** Utiliser `docker compose up -d <service>` pour forcer la recréation du container (recharge l'env_file).

**Règle DoD :** Après changement de variable d'environnement, toujours vérifier avec `docker exec <container> env | grep <VAR>`.

---

### 1.5 `ansible.posix.synchronize` échoue avec port SSH Jinja2

**Symptôme :** Tâche "Copy palais application source" échoue avec une erreur de conversion `int`.

**Cause :** `ansible.posix.synchronize` (rsync) tente de convertir `ansible_port` en entier mais la variable est un template Jinja2, pas encore résolu.

**Fix :** Remplacé par `ansible.builtin.copy` qui utilise la connexion SSH existante sans ouvrir une nouvelle connexion rsync.

**Règle DoD :** Ne jamais utiliser `ansible.posix.synchronize` dans ce projet. Utiliser `ansible.builtin.copy`.

---

### 1.6 GID/UID 1000 déjà pris dans `node:22-alpine`

**Symptôme :** Build Docker échoue : `addgroup: gid '1000' in use`.

**Cause :** L'image `node:22-alpine` réserve le GID/UID 1000 pour l'utilisateur `node`.

**Fix :** Utiliser GID/UID 1001 pour l'utilisateur applicatif.

**Règle DoD :** Toujours utiliser UID/GID 1001 pour les users créés dans les images basées sur `node:*-alpine`.

---

### 1.7 `DATABASE_URL` requis au build-time SvelteKit

**Symptôme :** Build Docker échoue avec `Error: DATABASE_URL environment variable is required` pendant `npm run build`.

**Cause :** SvelteKit SSR analyse les imports au build-time. Le pool PostgreSQL est importé dans un fichier serveur, ce qui déclenche la validation de `DATABASE_URL` même si la connexion n'est jamais établie.

**Fix :** Ajout d'un ARG Dockerfile fictif passé comme ENV avant le build :
```dockerfile
ARG DATABASE_URL=postgresql://build:build@localhost:5432/build
ENV DATABASE_URL=$DATABASE_URL
RUN npm run build
```

**Règle DoD :** Toute image SvelteKit avec `$env/dynamic/private` dans les imports server doit avoir ce pattern dans le Dockerfile.

---

### 1.8 `import security_headers` absent dans Caddyfile

**Symptôme :** Caddy crash au démarrage : `File to import not found: security_headers`.

**Cause :** Le template Caddyfile.j2 pour Palais incluait `import security_headers` mais ce snippet n'est pas défini dans le Caddyfile global.

**Fix :** Retirer l'import inexistant. Utiliser uniquement les snippets définis : `vpn_only`, `vpn_error_page`.

**Règle DoD :** Avant d'utiliser un `import` dans le Caddyfile, vérifier qu'il est défini dans le Caddyfile via `grep -r "^(snippet_name)" roles/caddy/templates/`.

---

### 1.9 `palais_subdomain` absent des roles vpn-dns et headscale

**Symptôme :** `palais.ewutelo.cloud` ne résout pas sur le réseau Headscale/Tailscale.

**Cause :** Le sous-domaine n'était pas ajouté dans `roles/vpn-dns/defaults/main.yml`. Le DNS magique Headscale n'avait pas d'entrée `A` pour `palais.ewutelo.cloud`.

**Fix :** Ajouter le pattern dans vpn-dns/defaults après chaque nouveau sous-domaine :
```yaml
([{"name": palais_subdomain ~ "." ~ domain_name, "type": "A", "value": _vpn_dns_vps_ts_ip}]
 if (palais_subdomain | default('')) | length > 0 else [])
+
```

**Règle DoD :** Pour chaque nouvelle application avec sous-domaine VPN-only, vérifier que le sous-domaine est dans `vpn-dns/defaults/main.yml`. Tester avec `nslookup <subdomain>.<domain>` depuis la machine connectée à Headscale.

---

### 1.10 Trop de connexions SSH rapides → fail2ban ban temporaire

**Symptôme :** `ssh: connect to host X port 804: Connection refused` après ~15 commandes SSH en rafale.

**Cause :** Fail2ban sur le serveur ban l'IP source si trop de connexions SSH en peu de temps, même si elles réussissent toutes.

**Fix comportemental :** Regrouper les commandes SSH en une seule session :
```bash
# MAUVAIS : une connexion par commande
ssh ... 'cmd1' && ssh ... 'cmd2' && ssh ... 'cmd3'

# BON : tout en une connexion
ssh ... 'cmd1 && cmd2 && cmd3'
```

**Règle DoD :** Ne jamais enchaîner plus de 5 connexions SSH séparées en moins d'une minute. Grouper les opérations.

---

## 2. Définition of Done (DoD) — Phase N de Palais

Avant de déclarer une phase terminée, vérifier TOUJOURS ces points :

### 2.1 Code
- [ ] `npm run lint` passe sans erreur dans `roles/palais/files/app/`
- [ ] `npm run check` (svelte-check) passe sans erreur TypeScript
- [ ] Chaque `{#each}` a une clé `(item.id)` ou `(item.href)`
- [ ] Chaque nouvelle route `/api/*` publique est dans `publicPaths` de `hooks.server.ts`
- [ ] Aucun snippet Caddy inexistant dans les nouveaux blocs Caddyfile

### 2.2 Base de données
- [ ] Si la phase ajoute des tables/colonnes : SQL de migration créé dans `drizzle/` et appliqué en prod
- [ ] Après migration : `GET /api/health` retourne `{"status":"ok"}`
- [ ] Les nouvelles tables sont peuplées si nécessaire (seed)

### 2.3 Docker
- [ ] Build Docker local réussi : `docker build -t palais:test roles/palais/files/app/`
- [ ] Dockerfile utilise UID/GID 1001 pour l'utilisateur applicatif
- [ ] `ARG DATABASE_URL=postgresql://build:build@localhost:5432/build` présent si db importée au build-time

### 2.4 Déploiement Ansible
- [ ] `make lint` passe (yamllint + ansible-lint)
- [ ] Ansible `--check --diff` ne montre pas d'erreur inattendue
- [ ] Après `ansible-playbook --tags palais` : container rebuilde et tourne (vérifier avec `docker ps`)
- [ ] `docker exec javisi_palais env | grep PALAIS_ADMIN_PASSWORD` montre la bonne valeur

### 2.5 Tests fonctionnels POST-déploiement
- [ ] `GET /api/health` → `{"status":"ok"}`
- [ ] `POST /api/auth/login` avec mauvais mot de passe → `{"error":"Invalid password"}` (pas `Unauthorized`)
- [ ] `POST /api/auth/login` avec bon mot de passe → `{"success":true}` + cookie `palais_session`
- [ ] `GET /` avec cookie → 200 (pas 500, pas 302)
- [ ] Endpoint(s) principal(aux) de la phase testés avec `curl -H 'x-api-key: ...'`

### 2.6 Git
- [ ] Tous les changements commités et poussés sur `main`
- [ ] Migration SQL versionnée dans `drizzle/`
- [ ] Tag `vX.Y.Z` créé après déploiement réussi

---

## 3. Checklist pré-déploiement (à faire AVANT `ansible-playbook`)

```bash
# 1. Lint
make lint

# 2. Build local
docker build -t palais:test roles/palais/files/app/

# 3. Vérifier les nouveaux snippets Caddy
grep -r "import " roles/caddy/templates/Caddyfile.j2 | grep palais

# 4. Vérifier les publicPaths si nouvelles routes API publiques
grep publicPaths roles/palais/files/app/src/hooks.server.ts

# 5. Vérifier les migrations DB
ls roles/palais/files/app/drizzle/
```

---

## 4. Commandes de diagnostic en prod

```bash
# Logs du container
ssh ... 'cd /opt/javisi && docker compose logs palais --tail=50'

# Variables d'environnement chargées
ssh ... 'docker exec javisi_palais env | grep -E "DATABASE|PALAIS|PORT"'

# Test health
curl -s https://palais.ewutelo.cloud/api/health

# Test login
curl -s -X POST https://palais.ewutelo.cloud/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"wrongpass"}'
# → doit retourner {"error":"Invalid password"}, pas {"error":"Unauthorized"}

# Test API avec clé
curl -s -H 'x-api-key: <key>' https://palais.ewutelo.cloud/api/v1/agents
```
