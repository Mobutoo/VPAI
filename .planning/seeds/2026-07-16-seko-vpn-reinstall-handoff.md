# Seed — Réinstallation Seko-VPN (handoff session 2026-07-16)

## Pourquoi
1. **SSH mort** (2026-07-16 ~15h) : `Connection refused` ports 22 ET 804, IP publique 87.106.30.160 (= ce que résout `fongola.ewutelo.cloud`). **Box UP** : HTTPS 200 (`/alive` Vaultwarden via Caddy). sshd down ou firewall REJECT. Dégradation récente : un subagent de revue exécutait encore `sudo docker exec` via SSH ~3 h avant. Point d'entrée : `docs/runbooks/RUNBOOK-SEKO-VPN-RECOVERY-CONSOLE-IONOS.md` (console Ionos).
2. **Bug web-vault** : création d'organisation → « Cannot read properties of undefined (reading 'find') ». Non diagnostiqué côté serveur (SSH down). Test 30 s AVANT de conclure : navigation privée/hard-refresh (même classe que le REX cache cf-studio) ; sinon, une réinstall avec version plus récente couvre.

## À PRÉSERVER absolument avant/pendant réinstall
| Donnée | Où | Criticité |
|---|---|---|
| **Volume Vaultwarden** (`<projet>_vaultwarden_data`, nom préfixé compose) | docker volume Seko | le coffre — filet : **export T0 fait par l'humain 2026-07-16** (hors Seko) |
| **Headscale state** (db + clés noise) | rôle headscale | TOUT le mesh — sans lui, ré-enrôler chaque nœud |
| Caddy data (certs) | volume caddy | régénérable (ACME) mais éviter le rate-limit |
| Zerobyte data | `/opt/services/zerobyte` | selon usage |

Repo IaC : `~/work/infra/Seko-VPN` (14 rôles, molecule partout, `docs/05-troubleshooting.md` = 42 pièges). Vault Ansible : `vault_vaultwarden_admin_token` etc. — **pas de `.vault_password` sur waza** (le fournir en session).

## À REPLIER dans la réinstall (synergie plan coffre)
- **T1/T2 du plan `docs/superpowers/plans/2026-07-16-vaultwarden-p0-p1b.md`** (backup builtin `/vaultwarden backup` → restic → offsite + restore prouvé `count(users)≥1`) : différées faute de creds S3 — les intégrer directement au rôle lors de la réinstall. Corrections revue DANS le plan (volume préfixé, alpine:3.21, purge dumps, sqlite3+restic apt).
- **T3** (org `javisi-agents` + collections `infra-agents`/`strong-secrets`/`canary` + comptes `agent-waza`/`resolver`, invitations sans SMTP = signup manuel email invité) — c'est là que le bug org a frappé.
- **T5** canary (workflow n8n `canary-alert` sur mayi + item coffre).
- mobuone pas dans le groupe docker sur Seko (sudo requis) — à décider à la réinstall.

## État du chantier coffre (ne PAS refaire)
- **P1a + P1a-bis FAITS sur waza** : 5 fichiers + `~/.claude.json` (9 littéraux dont postgres DSN) → store `~/.config/claude/secrets.env` 600 (14 clés) ; gate `scripts/secrets-migration-check.sh` = 0 violation. **Gate définitif = re-run post-boot d'une session `claude` fraîche** (hazard clobber `~/.claude.json` + validation `${VAR}` headers MCP n8n-docs/canva/qdrant/postgres/github/trek). Script réexécutable si clobber : `scripts/migrate-claudejson-secrets.sh`.
- **rbw 1.15.0 installé+configuré waza** (`base_url` fongola, `lock_timeout 3600` provisoire — T5b humain : 3600 vs 28800 à trancher). `rbw login` attend que les comptes machine existent (T3).
- **P1b** (secret-run TDD 9 tests + migration MACGYVER/HCLOUD/NAMECHEAP/LITELLM + rotation 🔒) : prêt dans le plan, attend T3/T5b.
- Backups rollback : `.bak-P1a-20260716-131851` (×5) + `~/.claude.json.bak-P1abis-20260716-143609`. ⚠️ post-rotation future : ces .bak = creds révoqués.

## Checklist 1re session réinstall
1. Console Ionos (runbook) → diagnostiquer sshd/firewall → décision réparer vs réinstaller.
2. Si réinstall : sauvegarder les volumes (headscale + vaultwarden) AVANT (tar depuis console), puis IaC replay.
3. Post-réinstall : T3 (retester le bug org sur version fraîche) → T1/T2 (avec creds S3) → T5 → reprise P1b.
4. En parallèle (waza, indépendant) : re-run `scripts/secrets-migration-check.sh` post-boot + vérifier auth MCP = clôture définitive P1a/P1a-bis.

---

## ⛔ CADUC 2026-07-16 (même jour)
SSH était un FAUX NÉGATIF (ban fail2ban transitoire, pas de panne). Seko-VPN SAIN : SSH ok port 22, 33j uptime, box HTTPS 200. **Réinstallation ANNULÉE** (décision humaine). Doc conservé comme runbook de secours si vraie panne future. Le bug restant = création org web-vault (front JS), traité en session courante via version web-vault.

## ✅ CLÔTURE nuit 2026-07-16 (session test-ban)
- **Vraie cause des bans récurrents** : crontab waza `*/5 * * * * git push` (workflows ComfyUI) vers `git@seko-vpn:` → user `git` inexistant sur Seko → 2 échecs/5 min → ban 1h en boucle (depuis mars). **Cron désactivé** (`#DISABLED-2026-07-16-ban-seko-invalid-user-git#`). Le push était mort-né : repo absent de Gitea + SSH Gitea loopback-only (127.0.0.1:2222).
- Secours anti-ban prouvé : `ssh -J sese-ai seko` (jamais `-i` brut sur le hop).
- fail2ban validé par test contrôlé (banip/unbanip TEST-NET 192.0.2.1, règle nft vérifiée). Waza débanni.
- **Vaultwarden convergé 1.35.8-alpine** (= pin IaC, fix bug org #6638) — healthy, `/alive` 200. Reste : valider création org en navigation privée (humain, master password) → puis T3.
