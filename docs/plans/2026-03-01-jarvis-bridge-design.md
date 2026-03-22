# Jarvis Bridge — Design Document

**Date** : 2026-03-01
**Auteur** : Erwin Mombili x Claude (Opus 4.6)
**Statut** : Approuve

---

## 1. Objectif

Construire une version maison d'OpenClaw : un agent autonome multi-agent accessible via Telegram, utilisant Claude Code CLI comme moteur d'execution. Deploye nativement sur Waza (RPi5 16GB ARM64).

### Ce que Jarvis remplace

| OpenClaw (Node.js Gateway) | Jarvis Bridge (Python + Claude CLI) |
|---|---|
| 10 agents Node.js dans sandboxes Docker | 5 agents via CLI sessions avec CLAUDE.md dedies |
| WebSocket control plane | Telegram long-polling + REST API locale |
| Palais (custom PM) | Plane (API REST) |
| File-based state (JSON) | Qdrant (memoire persistante) + fichiers etat chaud |
| LiteLLM multi-provider | Claude Code CLI (OAuth Max) |
| 1536MB RAM container | ~200-600MB natif (selon workers actifs) |

### Ce que Jarvis n'est PAS

- Un refactoring d'OpenClaw (qui reste sur Sese)
- Un remplacement de MacGyver (daemon Flash Studio)
- Un wrapper du Claude Agent SDK (on utilise le CLI directement)

---

## 2. Decisions architecturales

| Decision | Choix | Alternative rejetee | Raison |
|---|---|---|---|
| Moteur IA | Claude Code CLI (`claude -p`) | Claude Agent SDK Python | OAuth existant, outils built-in, MCP natif, zero dependance |
| Multi-agent | Foreground concierge + 2 background workers | CLI pool complet / Single CLI | Meilleur compromis UX/memoire sur RPi5 |
| Deploiement | Python venv + systemd | Docker container | Zero overhead, acces direct CLI/Tailscale/fichiers |
| State persistant | Qdrant (memoire, sessions, knowledge) | PostgreSQL / Redis / fichiers JSON | Deja en place, semantique, cross-session |
| State chaud | Fichiers JSON locaux (offset, PIDs) | Qdrant | Latence zero, pas de dependance reseau |
| PM tracking | Plane API REST | Kaneo MCP / NocoDB | Deja configure, projet Jarvis existant, API propre |
| Interface | Telegram (long polling) | Webhook / WebSocket | Waza pas expose publiquement, VPN only |
| Logs | JSON structure → Alloy → Loki | docker logs / fichiers plats | Integration monitoring existante |

---

## 3. Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                      WAZA (RPi5 16GB ARM64)                        │
│                                                                      │
│  jarvis-bridge.service (Python 3.12 venv, systemd)                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  TELEGRAM POLLER (long-poll 30s, whitelist chat_id)          │  │
│  │  REST API localhost:5000 (health, metrics, n8n trigger)      │  │
│  └───────────────────────────┬──────────────────────────────────┘  │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  DISPATCHER (queue FIFO max 5, commandes /agent /tasks etc.) │  │
│  └───────────┬──────────────────────────────┬───────────────────┘  │
│              ▼                              ▼                        │
│  ┌─────────────────────┐    ┌──────────────────────────────────┐  │
│  │  FOREGROUND          │    │  WORKER POOL (max 2 concurrent)  │  │
│  │  claude -p --resume  │    │  ┌── worker (claude -p --cwd)   │  │
│  │  agents/concierge/   │    │  └── worker (claude -p --cwd)   │  │
│  │  Reponse rapide <15s │    │  Timeout 30min, updates 30s     │  │
│  └─────────────────────┘    └──────────────────────────────────┘  │
│                                                                      │
│  STATE : Qdrant (sessions, knowledge, tasks) + local (offset, PIDs)│
└────────────────────────────────────────────────────────────────────┘
     │              │              │               │
     ▼              ▼              ▼               ▼
 Telegram      Plane API      Qdrant REST     Services locaux
 (messages)    (work items)   (Tailscale)     (ComfyUI, etc.)
```

### Flux d'un message

1. Telegram `getUpdates` recoit un message
2. Whitelist check (`TELEGRAM_CHAT_ID`)
3. `sendChatAction("typing")` en background
4. Dispatcher analyse : commande built-in (`/status`) ou message agent
5. Si commande → traitement direct
6. Si message → determine routing :
   a. Commande explicite (`/builder Fix auth.py`) → spawn worker builder
   b. Message normal → foreground concierge repond
   c. Concierge repond avec `[DELEGATE:builder]` → bridge spawn worker
7. CLI execute : `claude -p --output-format stream-json --resume <session_id> "message"`
8. Bridge parse le stream JSON, envoie chunks a Telegram
9. Si `tool_use` Bash detecte → approval gate check
10. Resultat final envoye a Telegram
11. Session sauvee dans Qdrant `jarvis-sessions`

### Flux approval gate (modele post-hoc)

> **NOTE (C1 fix):** `claude -p` est non-interactif — pas de stdin pour approuver/refuser.
> La securite est appliquee PRE-EXECUTION via `--settings` JSON (allow/deny par agent).
> Le bridge ne fait que notifier POST-HOC.

1. **PRE-EXECUTION** : `--settings config/settings-<agent>.json` definit les outils autorises
2. CLI execute la tache avec les permissions pre-configurees
3. Si le CLI refuse un outil (hors settings), il retourne `permission_denials` dans le resultat JSON
4. Bridge notifie l'utilisateur des operations refusees via Telegram
5. Utilisateur peut cliquer [Reessayer avec permissions] → bridge relance avec settings etendus
6. Les BLOCKED_PATTERNS restent pour la detection post-hoc et les alertes

---

## 4. Agents

5 agents, chacun avec un CLAUDE.md dedie dans `agents/<name>/CLAUDE.md`.

| Agent | Role | Foreground/Worker | MCP Servers |
|---|---|---|---|
| **concierge** | Chat rapide, routing, classification, small tasks | Foreground (toujours) | context7, filesystem |
| **builder** | Code, refacto, debug, Git, tests | Worker | context7, filesystem, n8n-docs |
| **ops** | Ansible, Docker, SSH, monitoring, deploy | Worker | context7, filesystem |
| **writer** | Redaction, docs, copywriting, traduction | Worker | context7 |
| **explorer** | Recherche web, synthese, veille techno | Worker | context7 |

### CLAUDE.md du concierge (resume)

- Persona : assistant polyvalent, repond en francais
- Routing : si la tache prend > 2 minutes ou necessite des outils specialises, repondre `[DELEGATE:<agent>] <instructions>`
- Regles : pas d'execution de commandes dangereuses, toujours resumer avant de deleguer
- Acces : Qdrant (memoire), Plane (suivi), services Waza (healthcheck)

### CLAUDE.md des workers (resume)

- Persona specialisee par role
- `cwd` : `/home/mobuone/jarvis/workspace/<task-id>/` (cree dynamiquement)
- Timeout : 30 minutes max
- A la fin : resumer le travail en 3 lignes pour notification Telegram
- Regles de securite specifiques au role (ex: ops ne touche pas aux fichiers code)

---

## 5. Memoire Qdrant (4 collections)

| Collection | Schema payload | Vecteur | Usage |
|---|---|---|---|
| `jarvis-sessions` | `{chat_id, agent, session_id, summary, updated_at}` | Embedding du summary (384d) | Persistence sessions CLI |
| `jarvis-knowledge` | `{pattern, solution, agent, confidence, source_task_id, created_at}` | Embedding du pattern (384d) | Patterns appris (REX) |
| `jarvis-docs` | `{source, title, content, ingested_at}` | Embedding du content (384d) | Docs de reference (deja 11 chunks) |
| `jarvis-tasks` | `{task_id, agent, status, summary, plane_issue_id, created_at, completed_at}` | Non (payload-only) | Tracking workers |

Embeddings via `all-MiniLM-L6-v2` local (deja installe sur Waza pour `ingest_docs.py`).

---

## 6. Securite

### Secrets

- Fichier `~/.jarvis.env` (gitignored, chmod 600) :
  ```
  TELEGRAM_BOT_TOKEN=<token>
  TELEGRAM_CHAT_ID=<id>
  QDRANT_API_KEY=<key>
  PLANE_API_TOKEN=<token>
  PLANE_WORKSPACE=ewutelo
  PLANE_PROJECT_ID=71de60ae-4218-4581-bacb-057b1436effb
  JARVIS_API_KEY=<key-interne-pour-rest-api>
  ```
- Jamais de secrets dans le PRD, les logs, ou le code
- Masquage automatique dans les logs (regex patterns tokens)

### Approval gates (3 niveaux)

| Niveau | Patterns | Action |
|---|---|---|
| Bloque | `rm -rf /`, `mkfs`, `dd if=`, `> /dev/sd`, `sudo rm -rf` | Refus immediat + notification |
| Approval | `docker restart`, `systemctl`, `ansible`, `git push`, `ssh`, `pip install` | Boutons Telegram, timeout 5min |
| Auto | Tout le reste (read, write, edit, grep, git status, etc.) | Execution directe |

### Anti-injection

- Messages Telegram sanitizes : max 4000 chars, pas de caracteres de controle
- CLAUDE.md des agents incluent des instructions anti-injection explicites
- Workers isoles dans leur propre `cwd` (pas d'acces au code du bridge)
- Pas de `--permission-mode bypassPermissions` (jamais)

---

## 7. Resilience

| Scenario | Comportement |
|---|---|
| Qdrant down | Sessions en memoire locale, warning Telegram, retry 30s |
| Plane down | Skip tracking, log warning, pas de crash |
| CLI timeout (60s sans output) | Kill, message Telegram, retry 1x |
| Worker zombie (>30min) | Kill auto, notification, Plane → Cancelled |
| Bridge crash | systemd Restart=on-failure, RestartSec=5 |
| RPi reboot | systemd WantedBy=multi-user.target |
| Queue pleine (>5 messages) | Drop anciens, notification "file d'attente pleine" |
| Telegram API down | Backoff exponentiel 1s→60s max |

---

## 8. Observabilite

- **Logs** : JSON structure (`{ts, level, module, msg, agent, task_id, duration_ms}`)
- **Fichier** : `/var/log/jarvis-bridge/jarvis.log` (logrotate 10MB x 5)
- **Alloy** : scrape logs → Loki (Sese)
- **Metriques** : `localhost:9200/metrics` (Prometheus format)
  - `jarvis_messages_total{agent}` — compteur
  - `jarvis_response_duration_seconds` — histogramme
  - `jarvis_workers_active` — gauge
  - `jarvis_errors_total{type}` — compteur
- **Health** : `localhost:5000/health` → `{"status":"ok","uptime":...,"workers":N}`

---

## 9. Stack technique

| Composant | Version | Role |
|---|---|---|
| Python | 3.12 | Runtime bridge |
| Claude Code CLI | 2.1.62+ | Moteur IA (OAuth Max) |
| httpx | 0.28+ | Client HTTP async (Qdrant, Plane, Telegram) |
| python-dotenv | 1.0+ | Chargement secrets |
| sentence-transformers | 3.x | Embeddings locaux (all-MiniLM-L6-v2) |
| prometheus-client | 0.21+ | Metriques |
| pytest | 8.x | Tests |
| pytest-asyncio | 0.24+ | Tests async |

Pas de framework web (pas Flask/FastAPI) — `aiohttp` serveur minimal pour health/metrics.

---

## 10. Phases d'implementation

| Phase | Livrable | Validation | Dependance |
|---|---|---|---|
| **0** | Prerequisites (bot Telegram, secrets, CLI check) | `claude -p "hello"` OK | Aucune |
| **1** | Core bridge (Telegram ↔ Claude CLI) | Message → reponse < 15s | Phase 0 |
| **2** | Approval gates | `rm -rf` intercepte → boutons | Phase 1 |
| **3** | Multi-agent (workers) | `/builder` → worker → resultat | Phase 2 |
| **4** | Integrations (Plane + Qdrant memory) | Issue Plane creee/fermee | Phase 3 |
| **5** | Deploy + Tests | `make test` OK, systemd OK | Phase 4 |

---

*Design approuve 2026-03-01 — Prochain : plan d'implementation detaille*
