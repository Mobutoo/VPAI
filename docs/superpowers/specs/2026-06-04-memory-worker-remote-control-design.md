# SPEC — Contrôle distant & supervision du memory-worker (extension du bot n8n existant)

> Statut : **DESIGN — révisé 2026-06-04 (v2)**. Topologie changée : **extension du bot Telegram n8n existant**, plus de poller local.
> Origine : audit live 2026-06-04 — le memory-worker était **dormant ~6 semaines** (timer system `disabled`, lock zombie PID 385466 du 26/04, spool 2066 gelé, state figé au 12/04, Qdrant `memory_v1` tombé à 22 793 points). Personne ne l'a vu : le worker **pushe** un rapport quand il tourne mais rien ne détecte son **absence**, et la brique hot-grep de R0-Continu masquait le tier froid mort.
> Besoin utilisateur : **démarrer/arrêter/superviser le worker depuis l'iPhone, hors PC.**
> Cibles : rôle Ansible `roles/llamaindex-memory-worker/` (waza, RPi5) + workflow n8n `scripts/n8n-workflows/memory-telegram-bot.json` (Sese-AI).

---

## 0. CHANGEMENT DE TOPOLOGIE (v1 → v2) — pourquoi cette révision

La v1 (poller `getUpdates` local sur waza, `memory-bot.py`) a été **invalidée par une découverte** : il existe déjà un bot Telegram opérationnel — `scripts/n8n-workflows/memory-telegram-bot.json` — un workflow n8n (sur Sese-AI) branché sur le **token monitoring** via `setWebhook` (secret_token). Il sert déjà `/memory_status`, `/memory_last`, `/memory_health`, `/memory_help` en **lecture seule** (Postgres `memory_runs`/`memory_worker_state` + Qdrant).

**Conséquence dirimante** : `getUpdates` et `setWebhook` sont **mutuellement exclusifs** sur un même token (Telegram 409). Lancer un poller local créerait un conflit. La v1 est donc abandonnée.

**Décision utilisateur** : *étendre le bot n8n*. Ajouter les commandes d'action au workflow existant ; n8n (Sese) appelle `memctl` sur waza **via un nœud SSH sur Tailscale**. On réutilise le bot monitoring + le webhook + tout le code status déjà fait.

### Ce qui SURVIT de la v1 (déjà commité, encore valide)
- **Durcissement `index.py.j2`** (lock PID-validé, flag `acquired`) — c'est le **fix racine** de la dormance. Indépendant de la topologie.
- **`memctl.sh`** (surface d'action `status|start|stop|run|fix`, env-driven, sudo-free) — c'est exactement ce que le nœud SSH va invoquer. Inchangé.
- **Migration units worker `service`+`timer` → systemd-user** (linger) — nécessaire pour que `memctl`/SSH pilotent le worker **sans sudo**.
- Les tests `test_lock.py`, `test_memctl.sh`.

### Ce qui est ABANDONNÉ de la v1
- `memory-bot.py` (poller getUpdates) — **conflit webhook**. Supprimé.
- `memory-bot.service.user.j2` — plus de bot local.
- Nouveaux secrets Vault `vault_memory_worker_telegram_bot_token`/`_owner_chat_id` — **inutiles** : on réutilise `telegram_monitoring_bot_token` / `telegram_monitoring_chat_id` déjà branchés dans `roles/n8n/templates/n8n.env.j2`.

---

## 1. Objectifs / Non-objectifs

### Objectifs
- **G1** Piloter le worker depuis l'iPhone via le **bot Telegram n8n existant** : ajouter `/memory_start`, `/memory_stop`, `/memory_run`, `/memory_fix` (préfixe `/memory_` aligné sur l'existant).
- **G2** Une **surface d'action unique** (`memctl`) sur waza, réutilisable par n8n (SSH), l'utilisateur en CLI, et Claude.
- **G3** Passer les units worker en **systemd-user** (linger) → contrôle **sans sudo** (le SSH entrant arrive en tant que `mobuone`).
- **G4** **Tuer la cause racine** : lock auto-stale (PID mort → auto-clear) dans `index.py`.
- **G5** Conserver les commandes status/health existantes (lecture Postgres+Qdrant) intactes — zéro régression.

### Non-objectifs
- Dead-man's switch n8n (alerte sur absence de rapport) + dashboard Grafana — différés (la base `memory_health` existe déjà, l'alerte proactive est un bonus).
- MCP `memory_ops` dédié (Claude appelle `memctl` en direct).
- Refonte du pipeline d'ingestion (chunking, embeddings, hybrid search).
- Réintégration de VPAI dans l'index (décision séparée).

---

## 2. Topologie réseau (fondement) — VÉRIFIÉE

```
iPhone (Telegram) ──cloud──► api.telegram.org ──webhook POST──► Caddy/n8n (Sese, javisi_n8n)
                                                                      │
                          lecture (status/health) ◄── Postgres n8n + Qdrant (Docker-interne Sese)
                                                                      │
                          actions (start/stop/run/fix) ── nœud SSH ──► waza 100.64.0.1:22 (Tailscale)
                                                                      │  forced-command → memctl.sh
                                                                      ▼
                                                              [worker local user-units]
```

**Faits vérifiés le 2026-06-04** :
- `javisi_n8n` = `ghcr.io/mobutoo/n8n-enterprise:2.7.3`.
- **Le conteneur `javisi_n8n` atteint `100.64.0.1:22` (waza)** — testé `node net.connect` → `OK reachable`. C'est nouveau : le bot ne parlait jusqu'ici qu'à `postgresql`/`javisi_qdrant` (Docker-interne). Le conteneur route donc bien vers le tailnet via l'hôte, l'ACL Headscale autorise Sese→waza:22, et le sshd de waza répond.
- waza (RPi5) n'est **joignable que sur le tailnet** (accès VPN-only, cf CLAUDE.md). Le sshd n'est pas exposé publiquement.

---

## 3. Architecture

| Unité | Responsabilité | Lieu |
|---|---|---|
| **`memctl.sh`** | Bibliothèque d'actions `status\|start\|stop\|run\|fix`. SOURCE UNIQUE de la logique. Local, en tant que `mobuone`, `systemctl --user`. | `/opt/workstation/ai-memory-worker/memctl.sh` (waza) |
| **`memctl-remote.sh`** (NOUVEAU) | Wrapper **forced-command** : lit `$SSH_ORIGINAL_COMMAND`, valide qu'il appartient à {status,start,stop,run,fix} (all-list stricte, rejet sinon), exporte `XDG_RUNTIME_DIR`, appelle `memctl.sh`. Confinement du rayon de souffle de la clé SSH. | `/opt/workstation/ai-memory-worker/memctl-remote.sh` (waza) |
| **authorized_keys (waza)** | Une clé dédiée n8n-memctl, **épinglée** : `command="…/memctl-remote.sh",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty <pubkey>`. | `/home/mobuone/.ssh/authorized_keys` (waza) — gérée par Ansible (`ansible.posix.authorized_key`) |
| **Workflow n8n (étendu)** | Branche d'action : le nœud Code classifie action-vs-lecture → routage → **nœud SSH** (`memctl <action>` sur waza) → formatage réponse → `sendMessage`. Le secret webhook + l'auth chat-id existants couvrent déjà les actions. | `scripts/n8n-workflows/memory-telegram-bot.json` (Sese) |
| **Credential SSH n8n** (NOUVEAU) | La **clé privée** dédiée, stockée comme credential n8n (référencée par ID dans le workflow — PAS dans le JSON versionné). Provisionnée hors-JSON. | n8n (Sese) |
| **systemd-user units** | Migration `memory-worker.{service,timer}` system→user + `loginctl enable-linger mobuone`. | `~mobuone/.config/systemd/user/` (waza) |

**Pourquoi `memctl` + wrapper séparés** : `memctl` est l'action pure (testable, CLI, Claude). `memctl-remote.sh` est le **garde-frontière** du canal SSH (allow-list). Changer le transport (un Shortcut iOS plus tard) ne touche pas la logique ; durcir le canal ne touche pas l'action.

---

## 4. Composants — détail

### 4.1 `memctl.sh` — INCHANGÉ (déjà commité)
`status` (JSON santé), `start`/`stop` (timer enable/disable), `run` (service oneshot), `fix` (lock PID-mort → rm + run). `set -uo pipefail`, `systemctl --user`, `XDG_RUNTIME_DIR` défensif.

### 4.2 `memctl-remote.sh` — NOUVEAU (garde-frontière SSH)
```bash
#!/bin/bash
set -uo pipefail
# SSH non-login → poser le bus utilisateur explicitement (sinon `systemctl --user`
# peut échouer "Failed to connect to bus" même avec linger + XDG_RUNTIME_DIR).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
cmd="${SSH_ORIGINAL_COMMAND:-}"          # ce que n8n a "demandé"
cmd="$(printf '%s' "$cmd" | tr -d '\r' | awk 'NR==1{print $1}')"   # 1er mot de la 1re ligne
case "$cmd" in
  status|start|stop|run|fix) exec /opt/workstation/ai-memory-worker/memctl.sh "$cmd" ;;
  *) echo "denied: '$cmd' not in {status,start,stop,run,fix}" >&2; exit 2 ;;
esac
```
- `NR==1{print $1}` → seulement le 1er mot de la 1re ligne ; un input multiligne ou avec séparateur (`;`, `&&`, `|`) collé au token ne matche aucun pattern → **denied**. (Empiriquement : `status; rm -rf /` → `$1=status;` → denied ; `status ; rm` (espace) → `$1=status` → exécute status, jette le reste — `rm` ne tourne jamais dans les deux cas.)
- `exec` → pas de shell intermédiaire après validation.
- **Names des units** : `memctl.sh` hardcode `llamaindex-memory-worker.{timer,service}` (défauts L10-11). Le wrapper ne surcharge pas `MEMCTL_*_NAME` → **les user-units DOIVENT s'appeler exactement `llamaindex-memory-worker.service` / `.timer`** (cf §4.5/§8a), sinon `start|stop|run|fix` = no-op silencieux sur une unit inexistante.

### 4.3 Extension du workflow n8n
Structure ajoutée (réutilise les patterns IF v2 **déjà éprouvés en prod** sur ce workflow) :
1. **Code « Handle Command »** (existant) : ajouter au routage les 4 nouvelles commandes → poser un champ `{action: 'start'|'stop'|'run'|'fix'}` quand c'est une commande d'action, sinon comportement lecture inchangé. L'auth chat-id en tête de handler **couvre déjà** les actions.
2. **Routage action vs lecture** : **NE PAS ajouter de nouveau nœud IF `typeVersion: 2`** (R9 prudence — bien que les IF v2 existants tournent live, on n'en ajoute pas). Utiliser un nœud **Switch** (hors périmètre R9) OU un champ posé par le Code node, pour router les updates `action` vers la branche SSH ; le reste (status/health/last/help) garde la branche actuelle. Les 2 IF v2 existants restent inchangés (éprouvés live).
3. **Nœud SSH** (`n8n-nodes-base.ssh`, nouveau) : host `100.64.0.1`, port 22, user `mobuone`, credential = clé privée n8n-memctl ; commande = `={{ $json.action }}` ; **timeout court explicite** (≈10 s) pour ne pas bloquer l'ack webhook. Le forced-command côté waza ré-valide.
4. **Code « Format Action Reply »** (nouveau) : transforme la sortie `memctl` (JSON pour status, texte sinon) en réponse Telegram lisible → rejoint le `sendMessage` existant.
5. **Timeout/échec SSH** : `onError: continueRegularOutput` + message « action injoignable (waza down ?) » plutôt que crash silencieux.
6. **Ack webhook indépendant de la latence SSH** (anti-double-action) : le webhook est `responseMode: responseNode`. Calquer le pattern lecture existant — `Respond 200` doit s'acquitter **sans attendre** la chaîne SSH (sinon un SSH lent/bloqué retarde l'ack → Telegram **retry** → `run` dupliqué). Soit `Respond 200` est branché en parallèle dès la classification action (le résultat SSH ne fait que conditionner le `sendMessage`, pas l'ack), soit le timeout SSH court (point 3) garantit un ack < fenêtre de retry Telegram. L'auteur de plan dessine le recâblage exact (cf §6).

**Préfixe** : `/memory_start|stop|run|fix` (aligné sur `/memory_status` existant). PAS `/mem_*`.

### 4.4 Durcissement `index.py` (G4) — INCHANGÉ (déjà commité)
Lock PID-validé (stale→auto-reclaim) + flag `acquired` dans `main().finally`. Modifier le **template** `index.py.j2`, jamais le fichier live.

### 4.5 Migration systemd system → user — INCHANGÉ vs v1 (sans le bot)
- Désinstaller proprement les system-units d'abord, puis installer les **user units** (`~mobuone/.config/systemd/user/`) + `loginctl enable-linger mobuone`.
- **Noms d'unités** : les user-units gardent **exactement** les noms `llamaindex-memory-worker.service` / `llamaindex-memory-worker.timer` (= défauts hardcodés de `memctl.sh`, cf §4.2 issue noms).
- **Réactivation explicite du timer** : le déploiement fait `systemctl --user enable --now llamaindex-memory-worker.timer`. C'est non-négociable : la dormance d'origine venait d'un timer `disabled` ; migrer sans réactiver ne ferait que **déplacer** la panne. (`/memory_stop` reste le moyen volontaire de le désactiver.)
- **Gotcha Ansible** : `systemctl --user` exige `become_user: {{ memory_worker_user }}` + `environment: { XDG_RUNTIME_DIR: "/run/user/{{ uid }}" }`.
- **Plus de `memory-bot.service`** (supprimé du périmètre v1).

---

## 5. Sécurité

- **Auth applicative** : double barrière déjà en place — (1) `secret_token` du webhook Telegram (`MEMORY_TELEGRAM_WEBHOOK_SECRET`), (2) `chat.id === TELEGRAM_MONITORING_CHAT_ID` en tête de handler. Les actions héritent des deux gratuitement.
- **Nouveau canal entrant SSH waza** — c'est l'**inversion assumée** de l'invariant « zéro inbound » de la v1. Confinement en profondeur :
  1. **Réseau** : sshd de waza déjà tailnet-only (VPN). L'ACL Headscale limite à Sese→waza:22.
  2. **Clé** : clé dédiée n8n-memctl, **forced-command** épinglé sur `memctl-remote.sh` + `no-pty,no-*-forwarding`. Même volée, la clé n'exécute QUE les 5 sous-commandes (allow-list dans le wrapper).
  3. **Action** : `memctl` est sudo-free, idempotent ; `fix` ne supprime un lock que si le PID est mort ; `run` est incrémental.
- **Secrets** : **aucun nouveau secret Vault**. Token+chat-id = `telegram_monitoring_*` existants. La clé privée SSH = credential n8n (hors JSON versionné) ; la clé publique = `authorized_key` déployée par Ansible (la **privée** ne transite pas par le repo).
- **R-LOI** : R1 `validate_workflow` avant import ; R3 file-first (éditer le JSON → valider → commit → deploy) ; R3-bis le workflow porte `webhookId`+`onError` → déployer via **REST PUT (R11)**, jamais `import:workflow` (qui les strip) ; R9 IF v2 : réutiliser le pattern v2 **déjà éprouvé live** sur ce workflow (n8n 2.7.3) — vérifier au déploiement qu'aucune IF ajoutée ne casse, sinon repli `typeVersion: 1`.

---

## 6. Robustesse / erreurs
- Nœud SSH `onError: continueRegularOutput` → réponse « waza injoignable » au lieu d'un échec muet d'exécution n8n.
- `memctl-remote.sh` rejette toute commande hors allow-list (exit 2, loggé côté waza via sshd).
- `memctl` fail-safe par sous-commande (échec Qdrant dans `status` → `qdrant_reachable:false`, pas de crash).
- Le formateur de réponse tolère un JSON `status` malformé (repli sur texte brut).

---

## 7. Tests
1. `memctl status` hors-ligne (Qdrant injoignable) → JSON valide, `qdrant_reachable:false`, exit 0. *(déjà vert)*
2. `memctl fix` : lock PID-mort → supprimé ; PID-vivant → préservé. *(déjà vert)*
3. `index.py` lock : PID mort → auto-clear+continue ; PID vivant → refuse. *(déjà vert)*
4. **`memctl-remote.sh`** (nouveau test, allow-list) : `SSH_ORIGINAL_COMMAND=run` → appelle `memctl run` ; `="status; rm -rf /"` → **denied, exit 2** (le `;` reste collé → `$1=status;` → no-match) ; `="status ; rm -rf /"` (espace) → exécute `status`, jette `rm` ; input multiligne → denied ; `="evil"` → exit 2. Dans tous les cas `rm` ne tourne jamais. (Stub `memctl.sh` pour capturer l'argument passé.)
5. **Chemin SSH réel** (pas seulement les tests locaux en session login) : depuis Sese, `ssh -i <clé-forced-command> mobuone@100.64.0.1 run` → doit exécuter l'action (valide que `systemctl --user` marche en SSH non-login : XDG_RUNTIME_DIR + DBUS_SESSION_BUS_ADDRESS posés par le wrapper). À vérifier **avant** le smoke E2E Telegram.
6. **Workflow** : `validate_workflow` → 0 erreur bloquante. Smoke E2E : `/memory_run` depuis Telegram → SSH → `memctl run` → réponse.
7. Idempotence Ansible : 2e run = 0 changed ; user-units présentes, timer `enabled`+`active`, linger actif, `authorized_key` présent une seule fois.

---

## 8. Déploiement

### 8a. waza (rôle `llamaindex-memory-worker`, workstation playbook)
- Templates/fichiers : `memctl.sh` (existant), **`memctl-remote.sh`** (nouveau, `files/`), `index.py.j2` (durci), user-units worker+timer. **Plus de `memory-bot.*`.**
- Déposer la **clé publique** n8n-memctl via `ansible.posix.authorized_key` avec `key_options: 'command="…/memctl-remote.sh",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding'`.
- Désinstaller system-units → installer user-units (noms `llamaindex-memory-worker.{service,timer}`) → `enable-linger` → `systemctl --user daemon-reload` puis **`enable --now llamaindex-memory-worker.timer`** (réactivation explicite, cf §4.5) — sous `become_user`+`XDG_RUNTIME_DIR`.
- Conventions VPAI : FQCN, `changed_when`/`failed_when`, `set -euo pipefail`, idempotence 0-changed, tags `[llamaindex-memory-worker, memory_remote]`.

### 8b. Sese (workflow n8n) — étapes manuelles/gate humain

> **Mécanisme de déploiement** : le JSON du repo est une **source canonique sans `id`** (vérifié : pas de top-level `id`/`active`). Il a été déployé par un chemin qui assigne un id (MCP `n8n_create_workflow` ou `import:workflow`). Le bon outil d'UPDATE = **`mcp__n8n-docs__n8n_update_full_workflow` par l'id live** (sémantique REST PUT R11, préserve `webhookId`+`onError` que `import:workflow` strip — R3-bis). **PAS** `deploy-workflow.sh` : il exige un top-level `id` ET hard-block les IF v2 (`:76`) → mauvais outil pour ce workflow id-less + IF v2.

1. **Réinit MCP n8n-docs si expirée** (R1-bis, `-32000`) puis `n8n_health_check` → le MCP de gestion atteint l'instance live ? `n8n_list_workflows`/`n8n_get_workflow` → **récupérer l'id live** du `memory-telegram-bot`.
2. **Contrôle de dérive (R3 préalable)** : `n8n_get_workflow` la version live et confirmer qu'elle correspond au JSON repo *modulo* id/active. Si dérive (édition UI depuis `3e35300`/v0.7.0) → **réconcilier live→repo d'abord**, sinon le push écrase silencieusement le bot qui marche.
3. **Générer la paire de clés** n8n-memctl (ed25519). Clé **publique** → repo (var/`authorized_key`). Clé **privée** → **créer le credential SSH dans n8n** pour en obtenir l'**ID** (avant édition JSON) — la privée n'est jamais commitée.
4. Éditer `scripts/n8n-workflows/memory-telegram-bot.json` (file-first) : ajouter classifier + **Switch** (pas de nouvelle IF v2) + nœud SSH (credential par l'ID de l'étape 3) + formateur.
5. `mcp__n8n-docs__validate_workflow` (R1) → 0 erreur bloquante.
6. Déployer via **`mcp__n8n-docs__n8n_update_full_workflow`** (id live de l'étape 1). PUT met à jour entité + history simultanément (R10).
7. Le `setWebhook` existant reste inchangé (même token, même secret).

---

## 9. Hors-scope tracé
- Dead-man's switch n8n (alerte si aucun rapport >X) — bonus supervision (la table `memory_runs` + `/memory_health` existent déjà).
- Dashboard Grafana + Alloy/Prometheus.
- MCP `memory_ops` pour Claude (appelle `memctl` directement).
- Raccourci iOS / transport alternatif (`memctl` le permet sans changer la logique).
- Réindexation VPAI.
