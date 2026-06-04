# SPEC — Contrôle distant & supervision du memory-worker (bot Telegram, systemd-user)

> Statut : **DESIGN — approuvé en brainstorm** (2026-06-04)
> Origine : audit live 2026-06-04 — le memory-worker était **dormant depuis ~6 semaines** (timer system `disabled`, lock zombie PID 385466 du 26/04, spool 2066 gelé, state figé au 12/04, Qdrant `memory_v1` tombé à 22 793 points). Personne ne l'a vu : le worker **pushe** un rapport quand il tourne mais rien ne détecte son **absence** (dead-man's switch manquant), et la brique hot-grep de R0-Continu masquait le tier froid mort.
> Besoin utilisateur : **démarrer/arrêter/superviser le worker rapidement depuis l'iPhone, hors PC.**
> Cible déploiement : rôle Ansible `roles/llamaindex-memory-worker/` → waza (RPi5).

---

## 1. Objectifs / Non-objectifs

### Objectifs
- **G1** Piloter le worker depuis l'iPhone via un **bot Telegram** : `/mem_status /mem_start /mem_stop /mem_run /mem_fix`.
- **G2** Une **surface d'action unique** (`memctl`) réutilisable par le bot, l'utilisateur en CLI, et Claude.
- **G3** Passer les units worker en **systemd-user** (linger) → contrôle **sans sudo**, self-contained.
- **G4** **Tuer la cause racine** de la panne : lock auto-stale (PID mort → auto-clear) dans `index.py`.
- **G5** `/mem_status` donne un **snapshot santé** unique (âge dernier run, spool, lock, points Qdrant, timer on/off).

### Non-objectifs
- Dead-man's switch n8n + dashboard Grafana (couches C2b/C2c proposées, **différées** — bonus).
- MCP `memory_ops` dédié pour Claude (Claude appelle `memctl` en direct ; pas besoin d'un MCP neuf en v1).
- Réindexation/refonte du pipeline d'ingestion lui-même (chunking, embeddings, hybrid search) — autre chantier.
- Réintégration de VPAI dans l'index (décision séparée).

---

## 2. Clarification réseau (fondement de la topologie)

Le poller **n'utilise pas Tailscale** pour Telegram. Il fait des appels **sortants** vers `api.telegram.org` (cloud public) ; waza a déjà l'égress internet (pull d'images Docker). Chaîne : iPhone → cloud Telegram ← (long-poll) waza. Ils se rejoignent chez Telegram, **sans inbound vers waza, sans VPN sur l'iPhone**. `/mem_status` interroge Qdrant en HTTPS public (`qd.ewutelo.cloud`). Tout le contrôle worker est **local sur waza**. Tailscale ne sert qu'au mesh privé waza↔Sese — hors-scope ici.

---

## 3. Architecture

Trois unités à responsabilité unique :

```
iPhone (Telegram) ──cloud──► api.telegram.org ◄──long-poll── memory-bot.py ──► memctl.sh ──► [worker local]
                                                              (auth chat-id)    (status|start|stop|run|fix)
```

| Unité | Responsabilité | Lieu |
|---|---|---|
| **`memctl.sh`** | Bibliothèque d'actions — `status\|start\|stop\|run\|fix`. SOURCE UNIQUE de la logique. Tout local, en tant que `mobuone`, sortie JSON (status) ou texte. Aucune dépendance Telegram. | `/opt/workstation/ai-memory-worker/memctl.sh` |
| **`memory-bot.py`** | Front Telegram mince : long-poll `getUpdates`, **vérifie le chat-id**, dispatch → `memctl`, répond via `sendMessage`. Aucune logique métier. | `/opt/workstation/ai-memory-worker/memory-bot.py` (venv worker) |
| **systemd-user units** | `memory-bot.service` (Restart=always) + migration des units worker `memory-worker.{service,timer}` en **`--user`**. `loginctl enable-linger mobuone`. | `~/.config/systemd/user/` (mobuone) |

**Pourquoi `memctl` isolé du bot** : le bot est un transport ; `memctl` est l'action. On peut tester `memctl` sans Telegram, l'appeler en CLI (`memctl status`), et Claude l'invoque en direct. Changer le transport (ajouter un Shortcut iOS plus tard) ne touche pas la logique.

---

## 4. Composants — détail

### 4.1 `memctl.sh` (interface : `memctl.sh <action>`)
- `status` → émet un JSON santé :
  `{last_run_ts, age_seconds, last_status, indexed, errors, skipped, spool_depth, lock_pid, lock_alive, state_entries, qdrant_points, qdrant_reachable, timer_enabled, timer_active}`.
  Dérivé (lecture seule) de : tail log, `ls spool | wc -l`, lock + `ps -p`, state json, `curl qd.ewutelo.cloud` (clé depuis env), `systemctl --user is-enabled/is-active memory-worker.timer`.
- `start` → `systemctl --user enable --now memory-worker.timer`.
- `stop` → `systemctl --user disable --now memory-worker.timer`.
- `run` → `systemctl --user start memory-worker.service` (run ponctuel — le service est `Type=oneshot`). **Méthode unique** : passer par le service préserve l'EnvironmentFile, `Nice=19` et le pré-check loadavg ; NE PAS invoquer `index.py` en direct (contournerait ces garde-fous). Non bloquant.
- `fix` → (a) si lock présent ET PID mort → supprimer le lock ; (b) re-trigger un run pour drainer le spool. Rapporte ce qui a été fait.
- `set -euo pipefail`, chaque sous-commande fail-safe, exit codes clairs. Idempotent.

### 4.2 `memory-bot.py`
- Long-poll `getUpdates` (timeout long, offset persistant pour ne pas rejouer).
- **Auth** : ignore tout message dont `chat.id != OWNER_CHAT_ID` (loggé). 
- Map commande→`memctl <action>` ; capture stdout ; formate une réponse lisible (status → tableau compact) ; `sendMessage`.
- Backoff exponentiel sur erreur réseau ; jamais de crash sur input malformé.
- `/mem_run` répond « run lancé » immédiatement puis (optionnel v1) le rapport final quand dispo.

### 4.3 Durcissement `index.py` (G4)
- À l'acquisition du lock (`ensure_lock()`, ~ligne 108) : si le fichier existe, lire le PID ; si `os.kill(pid, 0)` indique PID mort → **lock stale → supprimer et continuer** (au lieu de RuntimeError). Loggé. Empêche la récidive exacte du zombie observé. Changement chirurgical (~5 lignes).
- **IMPORTANT** : `index.py` est généré depuis un template `index.py.j2` dans le rôle. Modifier le **template**, pas le fichier live `/opt/.../index.py` (écrasé au prochain déploiement). Idem `memctl`/`memory-bot` = templates `.j2`.

### 4.4 Migration systemd system → user
- **Désinstaller proprement les system-units d'abord** (sinon double-unit active) : `systemctl disable --now llamaindex-memory-worker.timer llamaindex-memory-worker.service` (root) PUIS supprimer `/etc/systemd/system/llamaindex-memory-worker.{service,timer}` + `daemon-reload`.
- Installer les units **user** (`~/.config/systemd/user/`) + `loginctl enable-linger mobuone` (nécessaire ET suffisant pour fire sans session active).
- **Gotcha Ansible** : `systemctl --user` dans une tâche exige `become_user: {{ memory_worker_user }}` + `environment: { XDG_RUNTIME_DIR: "/run/user/{{ uid }}" }` (sinon "Failed to connect to bus"). Le `uid` est récupéré via `getent`/`ansible_facts`. À anticiper dans le plan.
- Le bot tourne aussi en user-unit. Tout pilotable par `mobuone` sans sudo.
- Les dirs `/opt/workstation/{ai-memory-worker,configs,data}` sont déjà propriété de `mobuone` → accès OK depuis user-units (vérifié).

---

## 5. Sécurité
- **Auth** : un seul `OWNER_CHAT_ID` autorisé (variable). Messages tiers ignorés + loggés.
- **Secrets** : `TELEGRAM_BOT_TOKEN` + `OWNER_CHAT_ID` sont des **NOUVEAUX secrets à provisionner** — vérifié : ils n'existent PAS dans `memory-worker.env` aujourd'hui (le fichier n'a qu'un commentaire). Le plan doit : (1) ajouter `vault_telegram_bot_token` + `telegram_owner_chat_id` dans `secrets.yml` (Vault) ; (2) les injecter dans `memory-worker.env.j2`. Réutiliser le bot Telegram existant (celui des notifications) si l'utilisateur fournit son token, sinon en créer un via @BotFather. Jamais en clair dans le code/templates.
- **Surface** : aucun port inbound ouvert sur waza (poller sortant uniquement). Pas de SSH cross-host, pas de sudoers.
- **Risk-tier** : `/mem_fix` ne supprime un lock que si le PID est mort (jamais un run vivant). `/mem_run` est incrémental.

---

## 6. Robustesse / erreurs
- `memory-bot.service` : `Restart=always`, `RestartSec`.
- getUpdates : retry backoff borné ; offset persistant.
- Chaque commande wrappée try/catch → répond le message d'erreur, continue à poller.
- `memctl` fail-safe par sous-commande (un échec Qdrant dans `status` → champ `qdrant_reachable:false`, pas de crash).

---

## 7. Tests
1. `memctl status` hors-ligne (Qdrant injoignable) → JSON valide, `qdrant_reachable:false`, exit 0.
2. `memctl fix` : lock PID-mort → supprimé ; lock PID-vivant simulé → NON supprimé.
3. `index.py` lock : PID mort → auto-clear+continue ; PID vivant → refuse (RuntimeError).
4. `memory-bot` dispatch : faux update JSON owner → action appelée + réponse ; chat-id étranger → ignoré.
5. Format status → tableau lisible (mock memctl JSON).
6. Idempotence Ansible : 2e run = 0 changed ; units user présentes + linger actif.

---

## 8. Déploiement (rôle `llamaindex-memory-worker`)
- Templates neufs : `memctl.sh.j2`, `memory-bot.py.j2`, `memory-bot.service.j2`, units worker user-level.
- Tasks (ordre) : (1) provisionner secrets Vault → `memory-worker.env.j2` ; (2) **désinstaller** system-units ; (3) installer templates + user-units ; (4) `enable-linger` ; (5) `systemctl --user daemon-reload` + enable bot/timer — toutes les tâches `systemctl --user` sous `become_user` + `XDG_RUNTIME_DIR`.
- Conventions VPAI : FQCN, `changed_when`/`failed_when` explicites, `set -euo pipefail`, idempotence 0-changed au 2e run, tags `[llamaindex-memory-worker, phaseN]`.
- Secrets : ajouter `vault_telegram_bot_token` + `telegram_owner_chat_id` dans `secrets.yml` (Vault) — **nouveaux** (absents aujourd'hui). Vérifier qu'ils existent avant deploy (REX-62 `vault_*` sans default).

---

## 9. Hors-scope tracé
- Dead-man's switch n8n (alerte si aucun rapport reçu >X) — bonus supervision.
- Dashboard Grafana + Alloy/Prometheus.
- MCP `memory_ops` pour Claude (Claude appelle `memctl` directement en v1).
- Raccourci iOS / Tailscale (transport alternatif ; `memctl` le permettrait sans changer la logique).
