# REX — Session 15 — 2026-03-04b

**Durée** : ~3h (contexte compacté 1 fois, reprise en session continuée)
**Objectif initial** : Corriger le workflow CI/CD (ci.yml 9/23, integration.yml 0/9 smoke tests)
**Résultat** : CI 23/23 ✅ | Integration : Deploy+Idempotence PASS, External 9/9 PASS, Internal 37/40 (Sure crash-loop résiduel)

---

## Contexte

Session 14 avait atteint `changed=0` en idempotence (Run 18) mais les smoke tests (première exécution) révélaient 4 classes de problèmes : DNS root domain manquant, VPN ACL 403 mal interprétés, TLS ACME timing, et Sure crash-loop. De plus, le workflow CI (Molecule) ne passait que 9/23 rôles.

Cette session corrige l'ensemble des 3 workflows CI/CD : `ci.yml`, `integration.yml`, `deploy-preprod.yml`.

---

## Track A — Molecule (ci.yml) : 9/23 → 23/23

### REX-72 — Molecule `chown failed: failed to look up user molecule`

**Symptôme** : 14/23 rôles échouent avec `chown failed: failed to look up user molecule`.

**Cause** : L'image `geerlingguy/docker-debian12-ansible` ne contient pas l'utilisateur `molecule` référencé dans les rôles Ansible (ex: owner des fichiers déployés). Les tests Molecule créent un conteneur minimal sans les users applicatifs.

**Fix** : Ajout de `pre_tasks` dans les 24 fichiers `converge.yml` :
```yaml
pre_tasks:
  - name: Create molecule test user (not present in geerlingguy Docker image)
    ansible.builtin.user:
      name: molecule
      state: present
      create_home: true
```

### REX-73 — Docker role `No package matching 'curl' is available`

**Symptôme** : Le rôle `docker` échoue en Molecule car `curl` n'est pas installé.

**Cause** : En prod, le rôle `common` installe `curl` avant `docker`. En Molecule, chaque rôle est testé isolément → `curl` absent + cache apt périmé.

**Fix** : `pre_tasks` spécifique dans `roles/docker/molecule/default/converge.yml` :
```yaml
- name: Update apt cache (geerlingguy image may have stale cache)
  ansible.builtin.apt:
    update_cache: true
    cache_valid_time: 3600
- name: Install curl (normally installed by common role)
  ansible.builtin.apt:
    name: curl
    state: present
```

### REX-74 — Hardening `openssh-server` + `/run/sshd`

**Symptôme** : Le rôle `hardening` échoue : `No package matching 'openssh-server'` puis `Missing privilege separation directory: /run/sshd`.

**Cause** : L'image Docker Molecule n'a pas `openssh-server` ni le répertoire `/run/sshd`. En prod, SSH est déjà installé.

**Fix** : `pre_tasks` dans `roles/hardening/molecule/default/converge.yml` :
```yaml
- name: Install openssh-server (hardening role configures sshd)
  ansible.builtin.apt:
    name: openssh-server
    state: present
- name: Create sshd privilege separation directory
  ansible.builtin.file:
    path: /run/sshd
    state: directory
    mode: "0755"
```

---

## Track B — Integration (integration.yml) : 4/9 → 9/9 external

### REX-75 — Smoke tests : mauvais noms de sous-domaines (ROOT CAUSE)

**Symptôme** : 5/9 smoke tests externes HTTP 000 (n8n, Qdrant, NocoDB, OpenClaw, Plane).

**Cause** : Les URLs de smoke tests utilisaient les noms de services (`n8n.${D}`, `qdrant.${D}`, `nocodb.${D}`, `oc.${D}`, `plane.${D}`) au lieu des sous-domaines custom définis dans l'inventaire :

| Service | Mauvais subdomain | Bon subdomain | Variable |
|---------|-------------------|---------------|----------|
| n8n | `n8n` | `mayi` | `n8n_subdomain` |
| Qdrant | `qdrant` | `qd` | `qdrant_subdomain` |
| NocoDB | `nocodb` | `hq` | `nocodb_subdomain` |
| OpenClaw | `oc` | `javisi` | `admin_subdomain` |
| Plane | `plane` | `work` | (hardcodé Caddyfile) |

**Sections impactées** (4 endroits dans `integration.yml`) :
1. DNS validation loop (provision job, ligne ~168)
2. TLS pre-warm subdomain list (smoke-tests job)
3. External smoke test `check_https` URLs (smoke-tests job)
4. `/etc/hosts` entries pour internal smoke tests

**Fix** : Remplacé dans les 4 sections + `scripts/smoke-test.sh`.

**Leçon** : Toujours vérifier les sous-domaines dans `inventory/group_vars/all/main.yml` et `roles/caddy/templates/Caddyfile.j2` — ne JAMAIS deviner les noms à partir des noms de services.

### REX-76 — Sure Web crash-loop sur CX22 preprod

**Symptôme** : `FAIL Sure Web container (state: restarting)`, `FAIL Sure health (HTTP 502)`.

**Cause** : Le service Sure Web est en crash-loop sur un serveur CX22 frais. Le container démarre puis crashe. Probable cause : dépendance manquante ou configuration incomplète pour un déploiement preprod.

**Impact** : 3/40 tests internes échouent (Sure health, Sure Web container, Sure Web healthcheck).

**Status** : Non résolu — à investiguer avec `docker logs javisi_sure_web --tail 50` sur un CX22.

### REX-77 — Sure `start_period: 120s` et timing smoke tests

**Symptôme** : Même après 120s de wait, Sure est toujours `unhealthy` (pas juste `starting`).

**Cause** : Ce n'est pas un problème de timing — le container crash-loop réellement. Le `start_period: 120s` n'aide pas si l'application elle-même crashe.

**Fix** : Le wait de 120s avant les internal smoke tests est conservé (utile pour d'autres containers lents) mais ne résout pas le crash Sure.

---

## Track C — Deploy-preprod (deploy-preprod.yml)

### REX-78 — Inventaire inline ne charge pas group_vars

**Symptôme** : `deploy-preprod.yml` avec `-i "IP,"` ne charge pas `inventory/group_vars/all/*.yml`.

**Cause** : Ansible ne charge les `group_vars/` que si l'inventaire est un fichier dans le répertoire `inventory/`. Un inventaire inline (`-i "IP,"`) n'a pas de chemin de répertoire parent.

**Fix** : Création d'un fichier `inventory/preprod_hosts.ini` dynamiquement dans le workflow, avec ajout de `--vault-password-file .vault_password`.

---

## Résultats Finaux

### CI (ci.yml) — Run post-fixes
```
23/23 Molecule tests PASSED
Lint: 0 failures
```

### Integration (integration.yml) — Run 22
```
Provision CX22 + DNS     : SUCCESS
Deploy + Idempotence     : SUCCESS (changed=0)
External HTTPS (9 checks): 9/9 PASS
Internal (40 checks)     : 37/40 PASS (3 FAIL = Sure crash-loop)
Destroy CX22 + DNS       : SUCCESS
```

### Commits (6 total)
1. `5bd9dd3` — Main fix : 22 fichiers (Molecule pre_tasks + integration.yml + deploy-preprod + smoke-test.sh)
2. `f5e0ced` — Hardening openssh-server
3. `5455a48` — Hardening /run/sshd
4. `8fb45ca` — Retry logic HTTP 000 (3×30s)
5. `f8c50e5` — Sous-domaines custom (mayi, qd, hq, javisi, work)
6. `2c78868` — Wait 120s healthchecks avant internal smoke tests

---

## Principes Généraux REX

### Principe : Sous-domaines custom — ne jamais deviner

Ce projet utilise des sous-domaines custom (`mayi`, `qd`, `hq`, `javisi`, `work`), PAS les noms de services (`n8n`, `qdrant`, `nocodb`, `oc`, `plane`). Sources de vérité :
- `inventory/group_vars/all/main.yml` : définitions des variables `*_subdomain`
- `roles/caddy/templates/Caddyfile.j2` : mapping effectif domaines → upstreams
- `roles/caddy/defaults/main.yml` : construction `caddy_*_domain`

### Principe : Molecule pre_tasks pour dépendances inter-rôles

Quand un rôle Ansible dépend d'un autre (ex: `docker` dépend de `common` pour `curl`), les tests Molecule doivent installer ces dépendances dans `pre_tasks`. Pattern standard :
```yaml
pre_tasks:
  - name: Create molecule test user
    ansible.builtin.user:
      name: molecule
      state: present
      create_home: true
```

### Piège : `docker ps --format '{{.Names}}'` dans GitHub Actions

`{{.Names}}` (sans `$` devant) n'est PAS interprété par GitHub Actions (seul `${{ }}` l'est). MAIS l'échappement est complexe quand c'est imbriqué dans une commande SSH — préférer `docker ps | grep <pattern>` dans les scripts CI.

### Piège : Inventaire inline Ansible et group_vars

`ansible-playbook -i "1.2.3.4,"` ne charge PAS `inventory/group_vars/`. Toujours écrire l'inventaire dans un fichier sous `inventory/` pour que les group_vars soient chargés automatiquement.
