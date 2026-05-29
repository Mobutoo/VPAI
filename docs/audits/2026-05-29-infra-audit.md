# Audit Infrastructure — waza + sese-ai + seko-vpn

**Date** : 2026-05-29
**Méthode** : 6 agents parallèles — 2 collecteurs live (waza local + sese-ai via SSH Tailscale), 3 auditeurs codebase (sécurité, versions/EOL, fiabilité), 1 recherche best-practices mai 2026.
**Périmètre** : repo Ansible `/home/mobuone/VPAI` + état runtime réel des 3 hosts.
**R0** : memory search effectué (headscale-node README/tasks, GUIDE-CADDY-VPN-ONLY, TROUBLESHOOTING, sese-running-topology).

---

## 0. Corrections de prémisse (avant toute conclusion)

| Croyance | Réalité vérifiée 2026-05-29 |
|---|---|
| Sese-AI = OVH VPS 8GB | **Debian 13 trixie, x86_64, 6 vCPU, 11 Gi RAM, 0 swap, uptime 80j.** Thèse « risque OOM 8GB » **INFIRMÉE** (3.3 Gi used, 8.1 Gi avail, load 0.6). |
| Stack VPAI unifié (26 svc) déployé | **JAMAIS `docker compose up`.** `/opt/javisi/docker-compose.yml` et `docker-compose-infra.yml` renvoient les **mêmes 5 conteneurs**. mayi/tala/llm = 502. Confirmé. |
| Seko-VPN = backup + relay opérationnel | **INJOIGNABLE depuis waza** : ping mort, ports 804/2222/22 filtrés, absent du mesh comme peer. Headscale control tourne (mesh sese↔waza up) mais host isolé du management. |
| versions.yml = état déployé | **Catalogue, pas l'état réel.** Retard de version sur services non-déployés = dette catalogue, pas vuln runtime active. |

**Implication** : la capacité n'est PAS le facteur limitant (11 Gi libres sur sese, 12 Gi sur waza). Les vrais risques sont **données (backups cassés)**, **angle mort (zéro monitoring)** et **CVE runtime (Redis/Caddy story-engine)**.

---

## 1. Synthèse exécutive — Top risques

| # | Risque | Sévérité | Effort | Host |
|---|---|---|---|---|
| 1 | **Backups PostgreSQL cassés depuis ≥ mars 2026** — `pg_dump` sans `PGPASSWORD`, dumps vides | 🔴 CRITIQUE | Quick-win | sese-ai |
| 2 | **Redis 8.4.0 → CVE-2026-23479 RCE** (CVSS 7.7) ; 8.4.3 dispo | 🔴 CRITIQUE | Quick-win | sese-ai (infra) |
| 3 | **Redis `7-alpine` non pinné** (flash-suite + story-engine) — même CVE, tag flottant | 🔴 CRITIQUE | Quick-win | sese-ai |
| 4 | **Credentials hardcodés** (Kitsu admin `Admin2026!` × 5 scripts, clé API LeBonCoin) | 🔴 CRITIQUE | Quick-win | repo |
| 5 | **Zéro monitoring déployé** — Grafana 502, aucun collecteur, 0 alerting | 🟠 HAUT | Moyen | sese-ai |
| 6 | **dufs exposé public sans auth** (`drop`, `vps`) — index fichiers ouvert | 🟠 HAUT | Quick-win | sese-ai |
| 7 | **Headscale = SPOF réseau** — DB non sauvegardée, pas de redondance | 🟠 HAUT | Quick-win | seko-vpn |
| 8 | **caddy `2.10-alpine` sur story-engine** — CVE haute-sévérité mars 2026 (≤2.11.1) | 🟠 HAUT | Quick-win | sese-ai |
| 9 | **Hardening role = prod uniquement** — waza/seko-vpn/story-engine/mediahall nus | 🟠 HAUT | Moyen | 4 hosts |
| 10 | **Handlers `state: restarted`** sur services env_file (viol. CLAUDE.md) × 4 rôles | 🟠 HAUT | Quick-win | repo |

---

## 2. État réel par host

### 2.1 waza (RPi5 16GB, ARM64, Ubuntu 24.04.4, Mission Control)

**Sain globalement.** 27 conteneurs Up, 0 restart-loop, 0 OOM historique, 0 service systemd en échec, temp 52.7°C, load très bas, 12 Gi RAM available.

| Finding | Sév |
|---|---|
| Reboot en attente (`/var/run/reboot-required`) — MAJ kernel/libc installées non actives | 🟡 MOYEN |
| Pare-feu host **indéterminé** (ufw/fail2ban illisibles sans sudo) + ports 22/80/443/3456/1420/3001/4000 en `0.0.0.0` | 🟡 MOYEN |
| `50-cloud-init.conf` (27 octets, 0600) = très probablement `PasswordAuthentication yes` (à confirmer `sudo sshd -T`) | 🟡 MOYEN |
| 60 paquets apt upgradables (kernel +4 rév, docker-ce 29.2→29.5) ; `unattended-upgrades` actif | 🟢 BAS |
| Aucun swap (0B) — pas de soupape, mais 12 Gi libre + 0 OOM | 🟢 BAS |
| Pollution tailnet : ~16 nœuds `waza-*` éphémères offline (19-86j) | 🟢 BAS |

### 2.2 sese-ai (Debian 13, x86_64, 11 Gi RAM, host AI prod)

27 conteneurs Up, 0 exited, ~2.2 Gi RAM Docker / 11 Gi. Infra javisi (caddy/pg18.4/redis8.4.0/qdrant1.18.1/socket-proxy) healthy. **Le 26-svc unifié n'existe pas en runtime.**

| Finding | Sév |
|---|---|
| **Backups PG cassés** (`no password supplied`, dumps vides depuis mars) | 🔴 CRITIQUE |
| Monitoring inexistant (Grafana 502, aucun cAdvisor/Alloy/Loki) | 🟠 HAUT |
| dufs public sans auth (`drop`+`vps`) ; couchdb `biki` public mais 401 auth (mitigé) | 🟠 HAUT |
| Ports `0.0.0.0` : Redis 6379, Postgres 5433, API 8000, metube 8081 ; pas d'ufw/iptables observé (CrowdSec présent, config root-only) | 🟡 MOYEN ⚠️ |
| MAJ sécu OS en attente (bind9, exim4, crowdsec, docker-ce) | 🟡 MOYEN |
| Disque `/` à 81% + 0 swap ; 8 GB images Docker récupérables non purgées | 🟡 MOYEN |

> ⚠️ **Réserve méthodo** : joignabilité internet des ports `0.0.0.0` **non testée** (R7 bloque la sonde IP publique). Si Redis 6379 s'avère joignable depuis internet → reclasser **CRITIQUE**. Items non auditables sans root, signalés explicitement : sshd_config (600), firewall hôte, config CrowdSec, OOM kernel-log, tailles volumes.

### 2.3 seko-vpn (Ionos, Headscale hub + webhook-relay + backup)

**Injoignable en management** depuis waza. Le mesh fonctionne (donc Headscale tourne) mais SSH/ICMP filtrés ou box dégradée.

| Finding | Sév |
|---|---|
| Headscale = SPOF du mesh entier ; DB non sauvegardée, pas de redondance | 🟠 HAUT |
| Host injoignable SSH — pas de hardening Ansible appliqué au groupe `vpn`, pas de monitoring de connectivité | 🟠 HAUT |
| Backup offsite (Zerobyte) tourne sur ce SPOF ; restore jamais testé | 🟡 MOYEN |

---

## 3. Findings par domaine

### 3.1 Sécurité

- 🔴 **Credentials hardcodés** : `scripts/setup-kitsu-project.py:15-16`, `setup-kitsu-full.py:16-17`, `test-kitsu-preview-upload.py:8-9`, `test-kitsu-preview-upload2.py:12`, `kitsu-create-shot.py:51` → `Admin2026!` en clair. `scripts/n8n-workflows/immo-finder-gif-yvette.json:37` → clé API LeBonCoin.
- ✅ **Vault OK** : `secrets.yml`, `secrets-story-engine.yml`, `secrets-mediahall.yml` chiffrés AES256.
- 🟠 **vault_* sans `default()`** (REX-62) : ~8 critiques (`vault_kitsu_admin_password`, `vault_opencut_*`, `vault_story_engine_db_password`, `vault_plane_secret_key`, `vault_claude_api_key`, `vault_ghcr_pull_token`).
- ✅ **Caddy ACL VPN** : conforme (les deux CIDR présents sur chaque `not client_ip`/`import vpn_only`). Publics intentionnels documentés : MOP viewer/dl, GrapeJS, dufs. OpenClaw `transport http {versions 1.1}` présent.
- ✅ **Docker socket** : socket-proxy (POST=0, EXEC=0, read-only, cap_drop ALL) ; OpenClaw socket direct documenté.
- 🟠 **Hardening role = `prod` uniquement** : manque sshd/ufw/fail2ban/CrowdSec/auditd sur waza, seko-vpn, story-engine, mediahall. Manque aussi sysctl hardening + AppArmor profiles (vs CIS 2026).

### 3.2 Versions / EOL

- 🔴 **Redis 8.4.0 → 8.4.3** (`versions.yml:14`) : CVE-2026-23479 RCE + CVE-2026-25243/23631. 8.4.x reste `-bookworm` → **pas de blocage setpriv** (REX 8.8). Patch trivial.
- 🔴 **`redis:7-alpine`** flottant : flash-suite (`docker-compose.yml.j2:43`) + story-engine (`defaults/main.yml:29`). CVE affecte 7.x ET 8.x → viser ≥7.4.9. Pinner dans versions.yml.
- 🟠 **story-engine désynchronisé** du catalogue (`roles/story-engine/defaults/main.yml`) : `caddy:2.10-alpine` (l.50, **vuln CVE Caddy mars 2026**), `qdrant v1.16.3` (l.32), `redis:7-alpine` (l.29). Drift de gouvernance hors versions.yml/diun.
- 🟠 **CouchDB réel 3.3.3** sous la fenêtre de patch (CouchDB ne patche que 3.5+3.4) → plus éligible aux correctifs. Pin catalogue 3.5.1 correct, migration bloquante.
- ✅ **À jour** : PostgreSQL 18.4, Caddy infra 2.11.3 (>2.11.1, au-delà des CVE mars 2026), Qdrant 1.18.1.
- 🟠 **Sans `mem_limit`** : flash-suite (×7), dufs, grapesjs. 🟡 **Sans healthcheck** : dufs, grapesjs.
- 🟡 Sprawl Postgres : `15-bookworm` (penpot), `16-alpine` (flash-suite), `pg16` (story-engine), `18.4` (stack). À standardiser.

### 3.3 Fiabilité / résilience

- 🔴 **Cause racine backup** : `roles/backup-config/templates/pre-backup.sh.j2:17-18` appelle `pg_dump` **sans** `export PGPASSWORD='{{ postgresql_password }}'` (présent dans `provision-postgresql.sh.j2:9`). Fix = ajouter la ligne d'export. DBs visées : n8n, litellm, nocodb, kitsu_production.
- 🟠 **Monitoring jamais déployé** : conteneurs Grafana/VM/Loki/Alloy vivent dans la Phase B (docker-compose.yml) jamais `up`. `notification_method` undefined → alertes déclarées (CPU/RAM/disk/restart) mais **0 notification sortante**.
- 🟠 **Handlers `state: restarted`** (viol. CLAUDE.md, doit être `present`+`recreate: always`) : `roles/{postgresql,qdrant,caddy,docker}/handlers/main.yml`.
- 🟡 **~40 violations idempotence** : `command`/`shell` sans `changed_when`/`failed_when` (obsidian-collector, kitsu-provision, plane-provision, qdrant, caddy, claude-code…) ; `webhook-relay/tasks/main.yml:18-39` sans `set -euo pipefail`.
- 🟡 **Smoke-tests non-bloquants** par défaut (`smoke-tests/tasks/main.yml`, `when: smoke_test_strict|default(false)`) → échecs silencieux.
- 🟡 **CI partielle** : Molecule en mode stub (pas de vrai compose up), provision roles + apps majeurs exclus, pas de deploy job.
- **SPOF** : Postgres unique partagé (n8n/litellm/nocodb/kitsu/plane), Headscale unique, Redis/Qdrant uniques, Caddy unique, Zerobyte sur seko-vpn. Aucune réplication. Restore jamais testé.

---

## 4. Best practices mai 2026 (recherche, sources citées)

### Alertes sécurité datées
- **Caddy** : CVE haute-sévérité mars 2026 sur v2.10.0→2.11.1. Infra javisi (2.11.3) OK ; **story-engine 2.10-alpine vulnérable**.
- **Redis** : 5 CVE 2026 dont CVE-2026-23479 RCE. Versions corrigées : 8.6.3 / **8.4.3** / 8.2.6 / **7.4.9** / 7.2.14.
- **pgBackRest archivé** (27 avr. 2026) — ne pas adopter pour du neuf.

### Recommandations clés
| Thème | Reco 2026 | Tag |
|---|---|---|
| Backup PG | Quitter `pg_dump`-seul → backup physique + WAL/PITR (**Barman** EDB v3.18, ou `pg_basebackup`+WAL si minimaliste). Test restore automatisé. | Stratégique |
| Headscale | Garder **SQLite** (pas PG). Backup = `sqlite3 .backup` + clés DERP/noise dans rsync offsite. Clients **restent en P2P** si control down. Multi-DERP régions. | Quick-win |
| Docker | `no-new-privileges` + `cap_drop:ALL` + `read_only`+tmpfs + `mem_limit` partout. **userns-remap** (pas rootless, casse socket-proxy). Vigilance CVE userns Ubuntu (Pi). | Quick-win |
| Caddy | MAJ >2.11.1 ; snippet headers (HSTS, strip `Server`) ; admin API en `localhost:2019` ; rate-limit (xcaddy). | Quick-win |
| Monitoring | **Beszel** (<10 MB/agent) + **Dozzle** (logs) → observabilité 3 hosts contraints sans la lourdeur Grafana. VictoriaMetrics seulement si rétention longue requise. | Quick-win |
| Redis | ≥8.4.3 + ACL + `protected-mode` + `bind` interne + UFW. CVE post-auth → durcir l'auth. | Quick-win |
| Ansible | `ansible-lint profile: production` ; Molecule happy+failure+régression sur caddy/pg/redis ; évaluer **SOPS+age** si diffs vault gênants. | Mixte |
| Secrets | SOPS+age = sweet-spot petite équipe self-host 2026. ansible-vault reste valide si Ansible-only. Infisical/OpenBao si UI/rotation/audit. | Stratégique |

Sources principales : redis.io (advisory CVE-2026-23479), thebuild.com (after pgBackRest), headscale.net + gawsoft.com (HA), OWASP Docker Cheat Sheet, caddyserver.com, instapods.com (Beszel), infisical.com (secrets 2026).

---

## 5. Roadmap priorisée (impact × effort)

### Sprint 0 — Quick-wins sécurité immédiats (< 1 j)
1. **Fixer le backup PG** : ajouter `export PGPASSWORD='{{ postgresql_password }}'` dans `pre-backup.sh.j2`, redéployer, lancer un dump manuel, **vérifier le `.dump` non vide**.
2. **Redis ≥ 8.4.3** : bump `versions.yml:14` + pinner `redis:7-alpine` → `7.4.9-alpine` (flash-suite + story-engine), redéployer.
3. **Caddy story-engine** : `2.10-alpine` → aligner sur 2.11.3 (`roles/story-engine/defaults/main.yml:50`).
4. **Purger les credentials hardcodés** : déplacer `Admin2026!` et la clé LeBonCoin vers vault/env ; **rotation des secrets exposés** (présents dans l'historique git).
5. **dufs** : ajouter une auth (`--auth`) ou passer `drop`/`vps` en `import vpn_only`.

### Sprint 1 — Résilience & visibilité (2-4 j)
6. **Monitoring Beszel + Dozzle** sur les 3 hosts (nouveau rôle léger) + alertes → webhook n8n/Telegram.
7. **Backup Headscale** : ajouter le dump SQLite + clés au job offsite ; documenter le plan de reprise control-server.
8. **Test de restore PG automatisé** (cron sur host throwaway) — un backup non testé n'est pas un backup.
9. **Handlers `restarted` → `present`+`recreate: always`** sur postgresql/qdrant/caddy/docker.
10. **vault_* sans default** : audit complet + ajout des vars manquantes dans secrets.yml (REX-62).

### Sprint 2 — Durcissement & dette (1-2 sem)
11. **Étendre le rôle hardening** à waza/seko-vpn/story-engine/mediahall (au minimum sshd key-only + ufw + fail2ban) + ajouter sysctl hardening.
12. **Diagnostiquer seko-vpn injoignable** (accès console Ionos) — risque SPOF actif.
13. **mem_limit** sur flash-suite/dufs/grapesjs ; **healthchecks** dufs/grapesjs.
14. **Docker hardening généralisé** (`no-new-privileges`, `cap_drop`, `read_only` + tmpfs).
15. **Migration CouchDB 3.3.3 → 3.5.1** (hors fenêtre de patch).
16. **Qualité Ansible** : `changed_when`/`failed_when` sur les ~40 violations ; `set -euo pipefail` webhook-relay ; smoke-tests bloquants ; CI integration test.

### Backlog stratégique
17. Backup PG physique + WAL/PITR (Barman) en remplacement de pg_dump.
18. Évaluer SOPS+age vs ansible-vault.
19. Réplication Postgres (standby) si RTO/RPO le justifient.
20. Standardiser les versions Postgres (15/16/18 → 1 ligne directrice).

---

## 6. Items non auditables (transparence)

Requièrent un accès root/console non disponible en lecture seule :
- **sese-ai** : sshd_config (600), firewall hôte réel (pas d'iptables/ufw observé), config CrowdSec, OOM kernel-log, tailles volumes Docker, joignabilité internet des ports `0.0.0.0`.
- **waza** : ufw/fail2ban status, `sudo sshd -T`, contenu `50-cloud-init.conf`.
- **seko-vpn** : tout (host injoignable) — audit fait sur le code Ansible uniquement.
