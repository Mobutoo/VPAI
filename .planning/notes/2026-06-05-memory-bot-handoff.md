# Handoff — Memory-worker control bot (Telegram @EkengeBot)

**Date** : 2026-06-05
**Pourquoi ce point** : MCP n8n session expirée (`-32000`). Quitter + relancer Claude pour resh MCP, puis reprendre à l'étape 6.

## État ingestion memory-worker — OPÉRATIONNEL ✅

Le fix dormancy du 2026-06-04 a marché.

| Indicateur | Valeur (live 2026-06-05 ~02:30) |
|---|---|
| Timer systemd-**user** | `active` + `enabled` |
| Run | en cours depuis 00:39, PID 1392579 vivant, mode `incremental --gc` |
| Lock | PID-validé, non-zombie (fix `index.py.j2`) |
| Qdrant `memory_v1` | 26 862 points (24 331 indexed), status green — remonte (était 22 793 avril) |
| `memory_state.json` | écrit atomiquement en **fin** de run (run pas terminé) |

→ **Ne pas tuer le run.** Premier full re-ingest après 6 sem.

## Bot Telegram = **@EkengeBot**

- name: Ekenge | id: `8379006406`
- token : `telegram_monitoring_bot_token` (env `TELEGRAM_MONITORING_BOT_TOKEN` dans `javisi_n8n`, def `roles/n8n/templates/n8n.env.j2:155`)
- C'est depuis **@EkengeBot** qu'on lance `/memory_status`.

## VÉRIFIÉ côté waza (tout en place) ✅

| Élément | Preuve |
|---|---|
| pubkey inventory | `inventory/group_vars/all/main.yml:388` (`memory_worker_ssh_pubkey_value`, RSA `n8n-memctl`) |
| authorized_keys waza forced-command | `~/.ssh/authorized_keys` ligne 3 : `command="…/memctl-remote.sh",no-pty,no-*-forwarding` |
| wrapper allow-list | `/opt/workstation/ai-memory-worker/memctl-remote.sh` : anti-multiline + first-token + `{status,start,stop,run,fix}` sudo-free, exporte XDG+DBUS |
| memctl.sh | présent `/opt/workstation/ai-memory-worker/memctl.sh` |
| credential câblé JSON | `scripts/n8n-workflows/memory-telegram-bot.json:224` id `P5ANiw6eFXBFP80f` name `n8n-memctl` (placeholder parti) |
| `make deploy-workstation` | confirmé fait par user |

## RÉSOLU 2026-06-05 ~02:55 — bot E2E OPÉRATIONNEL ✅

1. MCP n8n réparé (etc_hosts→vps_tailscale_ip, cf §FIX ci-dessus) + `/mcp` reconnect.
2. R1 validate: 3 "erreurs" = **faux-positifs** (Code retourne `[{json}]` partout; fan-out Send Reply+Respond 200 intentionnel). Wf déjà actif → **pas de redéploiement** (évite risque IF v2 R9).
3. Sibling R4: POST `/webhook/memory-telegram-bot` sans secret → 403 (front du wf vivant).
4. Archi: Caddyfile.j2:198 + live Caddy sese:155 exposent `/webhook/memory-telegram-bot` AVANT `vpn_only` → Telegram livre en public sur CE path (secret validé in-wf). Pas de relais pour ce path.
5. `setWebhook` armé: url=`https://mayi.ewutelo.cloud/webhook/memory-telegram-bot`, secret_token=`MEMORY_TELEGRAM_WEBHOOK_SECRET`, allowed=`[message]`. getWebhookInfo: url set, 0 pending, last_error none.
6. E2E `/memory_status` (secret OK, chat 6619155988): exec n8n 17154 **success**, Send Reply→Telegram `ok:true` **message_id 2156 livré**. Reply: Qdrant UP 27389 pts, worker waza RUNNING 129min.

RESTE (non bloquant): commandes **action** (`/memory_start|stop|run|fix` → SSH memctl waza) câblées mais non testées (worker en plein 1er full re-ingest, on ne le perturbe pas). Tester `/memory_health`/`/memory_last` (reads) librement. La ligne "Last worker run 53d FAILED" = données historiques memory_runs (le run live n'a pas encore posté son rapport de fin), pas un bug.

## ~~BLOQUEUR E2E : webhook Telegram NON armé~~ ❌ → levé (voir ci-dessus)

`getWebhookInfo` @EkengeBot → `url: VIDE`, 0 pending, pas d'erreur.
→ Le workflow live n'a jamais posé son `setWebhook`. `/memory_status` reste sans réponse tant que ce n'est pas fait. **Ce n'est PAS un bug SSH** — c'est l'étape 6 pas faite.

## FIX MCP n8n injoignable (2026-06-05 ~02:43) ✅

Symptôme: `n8n_health_check` → `NO_RESPONSE` alors que n8n+caddy sains (mayi /healthz 200, /api/v1 401).
Cause: le conteneur **`n8n-mcp`** (waza, bridge 172.17.0.2) avait `/etc/hosts: 100.64.0.1 mayi.ewutelo.cloud` → pointait sur **waza lui-même**, pas sese. Forcé sur 100.64.0.14 → 200/0.17s.
Origine: `roles/n8n-mcp/tasks/main.yml:41` (`etc_hosts`) + `defaults/main.yml:33` utilisaient `workstation_pi_tailscale_ip` (=100.64.0.1) au lieu de `vps_tailscale_ip` (=100.64.0.14, où tournent n8n/Caddy).
Fix: les 2 lignes → `vps_tailscale_ip`. Redéployé (`ansible-playbook playbooks/hosts/workstation.yml --tags n8n-mcp`), conteneur recréé, mayi→100.64.0.14, 200/70ms. Serveur MCP initialize OK (nouvelle session).
**ACTION RESTANTE**: conteneur recréé → ancienne session SSE périmée (`-32000`). Faire **`/mcp`** reconnect dans Claude pour repartir, PUIS reprendre étape 6 ci-dessous.

Bug secondaire (non bloquant, préexistant): `playbooks/hosts/workstation.yml:112` post_task "Deploy Windows Claude mcp.json" → chemin template relatif cassé (`playbooks/hosts/../roles/n8n-mcp/templates/windows-mcp.json.j2` introuvable). Échoue en fin de play sans impacter le conteneur. À corriger séparément.

## REPRISE après relance Claude (MCP OK)

1. **R0** : `search_memory.py --query "n8n memctl ssh forced-command bot telegram"` (déjà fait cette session, à refaire après /clear).
2. **R1** : `n8n_validate_workflow` sur le JSON avant tout push.
3. **Drift-check** : `n8n_get_workflow` (id du workflow `memory telegram bot`) vs `scripts/n8n-workflows/memory-telegram-bot.json`.
   - Note credential R9 : déployer via `n8n_update_full_workflow` (MCP), **pas** `deploy-workflow.sh` (hard-block IF v2 faux-positif sur ce build 2.7.3 — cf memory `project-memory-worker-control`).
4. **Push live** : `n8n_update_full_workflow` par id → puis `publish` (R10).
5. **Armer webhook** : déclencher le `setWebhook` (nœud du wf ou appel manuel `setWebhook` URL n8n + secret) → revérifier `getWebhookInfo` (url non-vide).
6. **E2E** : depuis @EkengeBot → `/memory_status` → doit répondre (n8n→SSH waza `100.64.0.1`→memctl `status`).

## Réfs
- Memory : `project-memory-worker-control` (Task 5 = ce qui reste)
- Spec v2 : `docs/superpowers/specs/2026-06-04-memory-worker-remote-control-design.md`
- Workflow : `scripts/n8n-workflows/memory-telegram-bot.json`
- Reinit MCP si re-expire (R1-bis) : POST `localhost:3001/mcp` initialize → mcp-session-id header.
