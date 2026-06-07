# Plan — Montée en version Sese-AI (applications + Docker)

> **Date** : 2026-05-29
> **Auteur** : session Claude Code (waza)
> **Statut** : PLAN — à valider avant exécution
> **Source de vérité images** : `inventory/group_vars/all/versions.yml`
> **Origine** : audit upstream GitHub 2026-05-28 + topologie vérifiée 2026-05-29 (R0/R7/R8)

## 0. Découverte bloquante — réalité ≠ catalogue

La topologie réelle vérifiée le 2026-05-29 (`docker compose ls` + `docker inspect ...config_files` sur sese via Tailscale) contredit l'hypothèse « tout le stack VPAI tourne ».

**Le stack unifié `docker-stack` (`/opt/javisi/docker-compose.yml`, 26 services) n'a jamais été `docker compose up`.** Aucun conteneur ne le référence. Les 15 services à CVE de l'audit upstream (n8n, litellm, grafana, nocodb, plane, kitsu, victoriametrics, loki, alloy, cadvisor, diun, gotenberg, typebot, mealie, firefly) **ne tournent pas** sur Sese-AI.

### Preuve étanche (HTTP réel depuis sese, 2026-05-29)

Caddy *intend* de proxifier ces services mais les conteneurs n'existent pas → 502 :

| vhost | Cible Caddyfile.j2 | HTTP | État |
|---|---|---|---|
| mayi.ewutelo.cloud | `n8n:5678` | **502** | non déployé |
| tala.ewutelo.cloud | `grafana:3000` | **502** | non déployé |
| llm.ewutelo.cloud | `litellm:4000` | **502** | non déployé |
| kitsu.ewutelo.cloud | `kitsu:80` | **000** | non déployé |
| drop.ewutelo.cloud | `javisi_dufs` | 200 | vivant |
| wizy.ewutelo.cloud | `javisi_grapesjs` | 200 | vivant |

### Conséquence

1. Bumper `versions.yml` pour les 15 services non déployés = **cosmétique** (aucun conteneur à recréer).
2. **L'urgence CVE de l'audit 2026-05-28 est CADUQUE pour ces services** : pas de conteneur Grafana → pas de Grafana vulnérable. Les « 🔴 9 CVE Grafana / SSRF Gotenberg » ne concernent rien qui tourne.
3. Le vrai sujet pour eux est *« faut-il les déployer ? »*, pas *« les mettre à jour »* — décision produit, à trancher avant tout bump utile.

## 1. Surface réelle d'upgrade (conteneurs running)

Conteneurs `javisi_*` réellement en exécution, tags vérifiés :

| Conteneur | Compose propriétaire | Tag running | versions.yml | Upstream | Tier |
|---|---|---|---|---|---|
| javisi_caddy | `docker-compose-infra.yml` | `caddy:2.11.2-alpine` | 2.11.2 | **2.11.3** | A — reverse proxy (HAUT blast) |
| javisi_postgresql | `docker-compose-infra.yml` | `postgres:18.3-bookworm` | 18.3 | **18.4** (patch même majeur) | A — stateful (HAUT blast) |
| javisi_redis | `docker-compose-infra.yml` | `redis:8.4.0-bookworm` | 8.4.0 | **8.8.0** (4 minors, 2026-05-25) | A — stateful |
| javisi_qdrant | `docker-compose-infra.yml` | `qdrant/qdrant:v1.17.1` | v1.17.1 | **v1.18.1** | A — stateful (backe memory_v1) |
| javisi_socket_proxy | `docker-compose-infra.yml` | `tecnativa/docker-socket-proxy:v0.4.2` | v0.4.2 | v0.4.2 — **déjà à jour** | A — aucune action |
| javisi_dufs | `docker/dufs/docker-compose.yml` | `sigoden/dufs:v0.45.0` | v0.45.0 | **v0.46.0** | A — standalone (drop.) |
| javisi_grapesjs | `docker/grapesjs/docker-compose.yml` | `ghcr.io/mobutoo/grapesjs-editor:v1.2.0` | v1.2.0 | custom build | A — image maison |
| javisi_pandoc_api | `docker/pandoc-api/docker-compose.yml` | `pandoc-api:local` | local | local build | A — image locale |
| couchdb | `/opt/services/couchdb/docker-compose.yml` | `couchdb:3.3.3` | 3.5.1 | — | B — **hors Ansible VPAI** + mismatch |

**Notes critiques :**
- **couchdb** : tourne en `3.3.3`, `versions.yml` pin `3.5.1`, déploiement bloqué (migration Obsidian Sync). Compose **externe** non géré par l'Ansible VPAI → bumper `versions.yml` ne le touche pas. Hors scope montée auto.
- **grapesjs / pandoc-api** : images maison/locales → upgrade = rebuild, pas bump de tag upstream.
- **openclaw (main)** : absent du running set (seuls les sandboxes `openclaw-sandbox:bookworm-slim` tournent). À traiter séparément (cf. `docs/guides/GUIDE-OPENCLAW-UPGRADE.md`).

## 2. Pré-requis bloquants (à valider AVANT toute vague)

| # | Vérification | Commande | Critère GO |
|---|---|---|---|
| P1 | Tailscale up (R7) | `dig +short mayi.ewutelo.cloud` | == `100.64.0.14` |
| P2 | `make deploy-role` **pull** bien le tag (R4) | canary loki/cadvisor — voir §3 | nouveau digest tiré |
| P3 | Le rôle gère le conteneur running | confirmé §1 : seuls infra + dufs/grapesjs/pandoc | roles infra OK |
| P4 | Budget IA OK | `make` n/a — vérif manuelle | < cap $5/j |
| P5 | Dump DB stateful AVANT (forward-only) | `pg_dumpall`, snapshot qdrant, `BGSAVE` redis | dumps présents |

**P2 est le sibling-test (R4)** : valider que bumper `versions.yml` + `make deploy-role` recrée bien le conteneur avec le nouveau digest. Si un rôle fait `state: present` sans `pull: always`/`recreate`, le bump est inerte → corriger le rôle d'abord.

## 3. Vagues d'exécution (par blast radius, pas par delta semver)

### Vague 0 — Canary zéro-impact (valide la mécanique)
Aucun conteneur observabilité ne tourne actuellement (loki/cadvisor absents). **Donc le vrai premier canary réel est `dufs`** (standalone, drop. ; perte = upload fichiers temporaire, pas de DB).

1. Bump `dufs_image: v0.45.0 → v0.46.0` dans `versions.yml`
2. `make lint` (check-no-latest) → `make check` (dry-run --diff)
3. `make deploy-role ROLE=dufs ENV=prod`
4. Smoke : `https://drop.ewutelo.cloud/` répond 200 + upload test
5. `git commit` — sinon `git revert` versions.yml + redeploy (rollback propre, stateless)

### Vague 1 — qdrant (stateful, backe memory_v1)
1. **Backup** : snapshot qdrant (`POST /collections/memory_v1/snapshots`) AVANT
2. Bump `qdrant_image: v1.17.1 → v1.18.1`
3. lint → check → `make deploy-role ROLE=qdrant ENV=prod`
4. Smoke : `qdrant-find` MCP renvoie des résultats sur memory_v1
5. **Rollback** : revert tag PUIS restore snapshot si schéma cassé (forward-only possible)

### Vague 2 — Caddy (HAUT blast — reverse proxy + VPN ACL + DNS-01 ARM)
> ⚠️ Un mauvais restart Caddy = lockout total. 4 pièges CLAUDE.md (CIDR ACL, handle_errors, resolvers DNS-01, OpenClaw http/1.1).
1. **Garder une session SSH ouverte** (accès hors-Caddy en cas de lockout)
2. Bump `caddy_image: 2.11.2 → 2.11.3` (+ `workstation_caddy_image`, `flash_suite_caddy_image` si alignés)
3. lint → `make check` (relire le diff Caddyfile rendu **intégralement**)
4. `make deploy-role ROLE=caddy ENV=prod`
5. Smoke : toutes les URLs VPN répondent (drop., wizy., mayi., tala. …) + ACL VPN-only OK
6. Rollback immédiat si une route tombe : `git revert` + redeploy

### Vague 3 — Data tier (postgres / redis) — SUR DÉCISION EXPLICITE
> Stateful, forward-only, plus haut risque. Ne PAS inclure en montée routinière.
- **postgres 18.3 → 18.4** : **patch même majeur** (REL_18_4) → upgrade in-place, **pas de dump/restore** requis (binaire-compatible same major). `pg_dumpall` quand même par sécurité. PG 18 volume = `/var/lib/postgresql`. Mot de passe unique partagé `{{ postgresql_password }}` (jamais de variante). Risque : FAIBLE.
- **redis 8.4.0 → 8.8.0** : **4 minors** (8.5→8.6→8.7→8.8, GA 2026-05-25, nouvelles features). Pas un patch. `BGSAVE` avant. RDB/AOF forward-compatible mais vérifier la conf (nouveaux defaults). Pour un saut de cette ampleur, suivre le runbook volume-swap (`flash-studio/docs/RUNBOOK-major-version-upgrades.md`, surfacé R0). Risque : MOYEN. Alternative conservatrice : rester sur la ligne 8.4.x (patch only).
- **GO uniquement** sur demande explicite + fenêtre de maintenance + dumps validés.

### Vague 4 — Images maison (rebuild, pas bump)
- **grapesjs** : `docker buildx build --platform linux/amd64 -t ghcr.io/mobutoo/grapesjs-editor:vX --push` puis bump tag.
- **pandoc-api** : rebuild image locale.
- **n8n** (custom enterprise) : rebuild `roles/n8n/files/Dockerfile` (`N8N_VERSION=`) — **mais n8n ne tourne pas** → décision déploiement d'abord.

### Différé / hors scope
- **couchdb 3.3.3 → 3.5.1** : compose externe + migration Obsidian Sync à planifier séparément.
- **15 services catalogue non déployés** : décision « déployer le stack `docker-stack` ? » à trancher avant tout bump utile (sinon cosmétique).
- **openclaw main** : suivre `GUIDE-OPENCLAW-UPGRADE.md` quand le service sera (re)déployé.

## 4. Boucle d'exécution standard (par service)

```
1. R0 memory search sur le service (gotchas connus)
2. Bump tag dans inventory/group_vars/all/versions.yml
3. make lint            # check-no-latest + ansible-lint
4. make check           # dry-run --check --diff (relire diff)
5. [stateful] backup/dump AVANT
6. make deploy-role ROLE=<role> ENV=prod
7. Smoke test (URL 200 / MCP / artefact)
8. git commit -m "chore(versions): bump <svc> X→Y"
   OU rollback: git revert versions.yml + make deploy-role (+ restore dump si stateful)
```

## 5. Rollback — règle par nature

| Nature | Rollback |
|---|---|
| Stateless (caddy, dufs, socket_proxy) | `git revert` versions.yml + `make deploy-role` → propre |
| Stateful (postgres, redis, qdrant) | **forward-only** : revert image NE revert PAS le schéma migré → restore depuis dump |

`playbooks/ops/rollback.yml` re-pull depuis les templates **courants** → ne revert PAS tout seul ; il faut `git revert` la `versions.yml` d'abord.

## 6. Périmètre retenu (décision utilisateur 2026-05-29) : **surface running uniquement**

| Service | Action | Vague |
|---|---|---|
| dufs v0.45.0 → v0.46.0 | bump + deploy | 0 (canary) |
| qdrant v1.17.1 → v1.18.1 | snapshot + bump + deploy | 1 |
| caddy 2.11.2 → 2.11.3 | bump + deploy (SSH ouvert) | 2 |
| postgres 18.3 → 18.4 | dump + bump (in-place, faible risque) | 3 (sur GO) |
| redis 8.4.0 → 8.8.0 | BGSAVE + runbook (ou rester 8.4.x) | 3 (sur GO) |
| socket_proxy v0.4.2 | **aucune** (déjà à jour) | — |
| grapesjs / pandoc-api | rebuild image maison | 4 (sur GO) |

**Hors périmètre retenu :** 15 services catalogue non déployés, couchdb externe, openclaw main.

### Reste à vérifier à l'exécution
- Alignement `workstation_caddy_image` / `flash_suite_caddy_image` lors du bump caddy
- kitsu (si un jour déployé) : source `cgwire/cgwire` renvoyait 404 le 2026-05-28 → re-vérifier registry
