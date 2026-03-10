# Flash-Agent

Agent Go local tournant sur chaque VPS client Flash Studio. Binaire statique, service systemd.

> Dernière mise à jour : Mars 2026

---

## Architecture — 2 destinations

```
flash-agent (sur chaque VPS client)
    │
    ├── [1] MASTER (source de vérité)
    │   │   Protocole : HTTPS via NetBird VPN
    │   │   Auth      : JWT signé par le Master
    │   │   Domaine   : api.paultaffe.com (Phase 3) / IP NetBird (Phase 1-2)
    │   │
    │   ├── POST /api/heartbeat        → signe de vie (60s)
    │   ├── GET  /api/config/{id}      → pull config (manifest.json)
    │   ├── POST /api/heartbeat        → métriques (CPU, RAM, disk, services)
    │   └── (futur) POST /api/billing/usage → métriques facturation
    │
    └── [2] EVENT ROUTER (Service Desk)
        │   Protocole : HTTPS via NetBird VPN
        │   Auth      : API key sk-pt-{64hex}
        │   Domaine   : event-router interne (sd-stg:8092 via NetBird)
        │
        ├── POST /api/events           → événements structurés (info/warning/critical)
        └── POST /api/tickets          → création intelligente de ticket support
            → Pipeline 10 étapes (dedup, LLM, enrichissement, Zammad)

Pourquoi 2 destinations :
  - Master = identité, config, orchestration, billing. JWT car claims + expiry + refresh.
  - Event Router = événements opérationnels, tickets. API key car stateless, hash lookup.
  - Séparation des responsabilités : le Master ne gère PAS le support.
  - Le Service Desk (help/terrasse/status) est exposé au trafic public.
    Le Master (auth/vpn/monitor) est isolé sur .net.
```

---

## Structure cible

```
flash-agent/
├── main.go                 Entry point, config loading, signal handling
├── go.mod / go.sum
├── config/
│   └── config.go           Structures de config, chargement manifest
├── core/
│   ├── heartbeat.go        Heartbeat périodique vers le Master (60s)
│   ├── auth.go             JWT validation, token refresh depuis Master
│   └── sync.go             Pull config (manifest.json) depuis Master au boot
├── transport/
│   ├── master_client.go    Client HTTPS vers Master (JWT auth)
│   ├── event_client.go     Client HTTPS vers Event Router (API key auth)
│   └── transport_test.go
├── modules/
│   ├── health/
│   │   ├── docker.go       Docker stats via /var/run/docker.sock
│   │   ├── system.go       Disk, RAM, CPU monitoring
│   │   └── health_test.go
│   ├── events/
│   │   ├── emitter.go      Émission d'événements vers Event Router
│   │   ├── collector.go    Collecte locale + buffer si réseau down
│   │   └── events_test.go
│   ├── tickets/
│   │   ├── creator.go      Création de tickets via Event Router /api/tickets
│   │   └── tickets_test.go
│   ├── backup/
│   │   ├── restic.go       Pilotage resticprofile (backup, check, forget)
│   │   ├── schedule.go     Cron scheduling
│   │   └── backup_test.go
│   ├── exec/
│   │   ├── exec.go         Exécution commandes du Master (whitelist)
│   │   └── exec_test.go
│   ├── meter/
│   │   ├── meter.go        Métriques d'usage (CPU-time, RAM-time par container)
│   │   └── meter_test.go
│   └── update/
│       ├── update.go       Self-update binaire signé (GitHub Releases)
│       └── update_test.go
├── mcps/                   [Phase 3 — pas MVP]
│   ├── server.go           Serveur MCP Unix socket
│   ├── n8n.go              mcp-n8n (CRUD workflows via localhost:5678)
│   ├── nocodb.go           mcp-nocodb (CRUD tables)
│   ├── postgresql.go       mcp-postgresql (SQL lecture seule)
│   ├── qdrant.go           mcp-qdrant (search/upsert)
│   ├── obsidian.go         mcp-obsidian (CRUD fichiers vault)
│   ├── flash.go            mcp-flash (proxy vers Master)
│   ├── docs.go             mcp-docs (Qdrant "flash-docs")
│   ├── review.go           mcp-review (API flash-review)
│   └── mcps_test.go
├── Dockerfile
├── .github/
│   └── workflows/
│       └── ci.yml
└── README.md
```

---

## Conventions Go

- Go 1.22+
- CGO_ENABLED=0 (binaire statique, pas de dépendance C)
- Build : `CGO_ENABLED=0 GOOS=linux go build -o flash-agent .`
- Errors : `fmt.Errorf("module.function: %w", err)` — toujours wrapper avec contexte
- Logging : `log/slog` (structured logging, JSON en production)
- Tests : table-driven, mocks HTTP avec `httptest`
- Config : env vars + JSON manifest du Master
- Process MCP : socket Unix `/var/run/flash-mcp.sock` (Phase 3)
- Immutabilité : passer des structs par valeur, pas de mutation in-place
- Fichiers : 200-400 lignes max, 800 absolument max

---

## Dépendances autorisées

```
go.mod :
  github.com/docker/docker/client    (Docker API)
  github.com/robfig/cron/v3          (Cron scheduling)
  github.com/golang-jwt/jwt/v5       (JWT auth vers Master)
  (Le reste : standard library uniquement)
```

---

## Variables d'environnement

```bash
# --- Identité ---
FLASH_CLIENT_ID           # ID unique du client (ex: "client-42")
FLASH_STUDIO_ID           # ID du studio (synonyme legacy)

# --- Master (destination 1) ---
FLASH_MASTER_URL          # URL du Master via NetBird (ex: http://100.64.x.x:3000)
FLASH_AGENT_TOKEN         # JWT signé par le Master (refresh automatique)

# --- Event Router (destination 2) ---
FLASH_EVENT_ROUTER_URL    # URL de l'Event Router via NetBird (ex: http://100.64.x.x:8092)
FLASH_API_KEY             # Clé API sk-pt-{64hex} pour l'Event Router

# --- Local ---
FLASH_MCP_SOCKET          # /var/run/flash-mcp.sock (Phase 3)
FLASH_DATA_DIR            # /mnt/data
FLASH_LOG_FORMAT          # json | text (défaut: json)

# --- Optionnel ---
FLASH_HEARTBEAT_INTERVAL  # Intervalle heartbeat en secondes (défaut: 60)
FLASH_EVENT_BUFFER_SIZE   # Taille du buffer local si réseau down (défaut: 1000)
```

---

## Règles

- Ne jamais importer de C (CGO_ENABLED=0 toujours)
- Ne jamais écrire hors de `/mnt/data/` et `/opt/flash-studio/`
- Ne jamais stocker de secrets dans le code ou les logs
- Le socket MCP est accessible par tous les users du VPS (mode 0666) [Phase 3]
- Si un module crashe, les autres continuent (isolation par goroutine + recover)
- Le heartbeat ne doit JAMAIS s'arrêter (c'est le signe de vie pour le Master)
- L'API key `sk-pt-*` est stockée dans `/opt/flash-studio/.env`, jamais dans les logs
- Le JWT Master est refreshé automatiquement avant expiration
- Le buffer local (`/mnt/data/.flash-studio/event-buffer.json`) stocke les événements si le réseau est down

---

## Transport — 2 clients distincts

### MasterClient (transport/master_client.go)

```go
// MasterClient communique avec le flash-master.
// Auth: JWT dans le header Authorization: Bearer <token>
// Utilisé pour: heartbeat, config sync, exec commands

type MasterClient struct {
    baseURL    string        // FLASH_MASTER_URL
    token      string        // JWT (refreshable)
    httpClient *http.Client
    logger     *slog.Logger
}

// Endpoints Master:
//   POST /api/heartbeat     → { client_id, services, cpu, ram, disk, agent_version }
//   GET  /api/config/{id}   → manifest.json (config complète du studio)
```

### EventClient (transport/event_client.go)

```go
// EventClient communique avec l'Event Router du Service Desk.
// Auth: API key dans le header Authorization: Bearer sk-pt-{64hex}
// Utilisé pour: événements opérationnels, création de tickets

type EventClient struct {
    baseURL    string        // FLASH_EVENT_ROUTER_URL
    apiKey     string        // sk-pt-{64hex}
    clientID   string        // FLASH_CLIENT_ID
    httpClient *http.Client
    logger     *slog.Logger
    buffer     *EventBuffer  // Buffer local si réseau down
}

// Endpoints Event Router:
//   POST /api/events    → { client_id, type, category, message, metadata }
//   POST /api/tickets   → { client_id, message, source, event_id }
```

---

## Module Events — Émission vers Event Router

### Types d'événements

| Type | Usage | Exemple |
|------|-------|---------|
| `info` | Opération normale | "Backup completed successfully" |
| `warning` | Attention requise, pas critique | "Disk usage above 80%" |
| `critical` | Action immédiate nécessaire | "Container postgres crashed" |

### Catégories

| Catégorie | Déclencheur |
|-----------|------------|
| `health` | Module health (CPU, RAM, disk, Docker) |
| `backup` | Module backup (success, failure, skip) |
| `service` | Container start/stop/crash |
| `security` | Login SSH, tentative d'accès suspecte |
| `update` | Self-update agent, docker compose update |
| `system` | Reboot, kernel panic, OOM killer |

### Buffer local (résilience réseau)

```go
// Si l'Event Router est injoignable, les événements sont bufferisés
// localement dans /mnt/data/.flash-studio/event-buffer.json
// Capacité: FLASH_EVENT_BUFFER_SIZE (défaut: 1000)
// Stratégie: FIFO, les plus anciens sont droppés si le buffer est plein
// Flush: goroutine retry toutes les 30s quand le réseau revient
```

### Payload événement

```json
{
    "client_id": "client-42",
    "type": "warning",
    "category": "health",
    "message": "Disk usage at 87% on /mnt/data",
    "metadata": {
        "disk_total_gb": 80,
        "disk_used_gb": 69.6,
        "disk_path": "/mnt/data",
        "threshold": 85
    },
    "source": "agent",
    "event_id": "evt-client42-health-1710072000"
}
```

### Convention event_id

Format: `evt-{client_id}-{category}-{unix_timestamp}`

Permet l'idempotency côté Event Router (Redis SETNX 1h). Si l'agent retry un événement après un timeout réseau, l'Event Router le déduplique automatiquement.

---

## Module Tickets — Création intelligente

L'agent peut créer des tickets support directement via l'Event Router.

### Quand créer un ticket automatiquement

| Condition | Action |
|-----------|--------|
| Container critique down > 5 min | Ticket `technical` / `high` |
| Backup échoué 3 fois consécutives | Ticket `technical` / `high` |
| Disk > 95% | Ticket `technical` / `urgent` (plafond `high` par source agent) |
| Agent ne peut pas joindre le Master > 30 min | Ticket `technical` / `high` |

### Payload ticket

```json
{
    "client_id": "client-42",
    "message": "Le container PostgreSQL a crashé et n'a pas redémarré après 3 tentatives automatiques. Dernière erreur: OOM killed. RAM usage: 94%. Le service n8n est aussi impacté car il dépend de PostgreSQL.",
    "source": "agent",
    "event_id": "evt-client42-service-1710072000",
    "language": "fr"
}
```

Le pipeline Event Router (10 étapes) se charge de :
- Extraire titre, catégorie, priorité via LLM
- Dédupliquer (hash + sémantique)
- Résoudre le customer Zammad
- Enrichir avec le health score + historique
- Créer le ticket Zammad avec les bons groupes/tags

**Note :** La priorité `urgent` est plafonnée à `high` pour les sources `agent`/`voice`/`openclaw`. Seul `source:"monitor"` peut créer des tickets `urgent`.

---

## Module Health — Collecte et émission

```go
// Le module health collecte les métriques et fait 2 choses :
//
// 1. Heartbeat → Master (via MasterClient)
//    Intervalle: 60s
//    Payload: { services, cpu, ram, disk, agent_version }
//    But: le Master sait si l'agent est vivant + état des services
//
// 2. Événements → Event Router (via EventClient)
//    Déclenchement: seulement si un seuil est franchi
//    Types: warning (80% disk), critical (container down)
//    But: créer des alertes + potentiellement des tickets

// Les seuils sont configurables dans le manifest.json du Master
type HealthThresholds struct {
    DiskWarning   float64 `json:"disk_warning"`   // défaut: 80
    DiskCritical  float64 `json:"disk_critical"`  // défaut: 95
    RAMWarning    float64 `json:"ram_warning"`    // défaut: 85
    RAMCritical   float64 `json:"ram_critical"`   // défaut: 95
    CPUWarning    float64 `json:"cpu_warning"`    // défaut: 80
    CPUCritical   float64 `json:"cpu_critical"`   // défaut: 95
}
```

---

## Cycle de vie complet

```
1. BOOT
   ├── Charger env vars (FLASH_CLIENT_ID, FLASH_MASTER_URL, FLASH_EVENT_ROUTER_URL, etc.)
   ├── Valider la présence de FLASH_AGENT_TOKEN et FLASH_API_KEY
   ├── Initialiser MasterClient (JWT) + EventClient (API key)
   ├── Sync config depuis Master → GET /api/config/{id} → manifest.json
   ├── Émettre événement "agent_started" → Event Router
   └── Démarrer les goroutines modules

2. RUNNING (boucle principale)
   ├── [goroutine] Heartbeat → Master toutes les 60s
   ├── [goroutine] Health check toutes les 30s
   │   ├── Si seuil franchi → événement warning/critical → Event Router
   │   └── Si container critique down > 5 min → ticket → Event Router
   ├── [goroutine] Backup cron (configurable via manifest)
   │   ├── Success → événement info → Event Router
   │   └── Failure → événement critical → Event Router (+ ticket si 3 échecs)
   ├── [goroutine] Event buffer flush (retry 30s si réseau down)
   ├── [goroutine] JWT refresh (avant expiration)
   └── [goroutine] Self-update check (toutes les 6h)

3. SHUTDOWN (SIGTERM/SIGINT)
   ├── Flush le buffer d'événements
   ├── Émettre événement "agent_stopping" → Event Router
   ├── Dernier heartbeat → Master
   ├── Attendre les goroutines (graceful, timeout 10s)
   └── Exit 0
```

---

## Domaines et réseau

```
Domaines (source: domain-strategy.md) :
  paultaffe.com  → Client-facing (help, terrasse, agence, status, app)
  paultaffe.net  → Infrastructure ops (auth, vpn, monitor, registry)
  paultaffe.fr   → Per-client subdomains (agent.{id}, hooks.{id})

L'agent communique UNIQUEMENT via NetBird VPN (réseau privé) :
  → Master    : http://100.64.x.x:3000 (IP NetBird du Master)
  → Event Router : http://100.64.x.x:8092 (IP NetBird du Service Desk)

Aucun trafic internet direct. Tout passe par le mesh VPN.

En Phase 3 (DNS interne NetBird) :
  → master.netbird.cloud → Master
  → events.netbird.cloud → Event Router
```

---

## Sécurité

| Couche | Mécanisme | Cible |
|--------|-----------|-------|
| Auth Master | JWT signé (HS256), refresh auto | Heartbeat, config, exec |
| Auth Event Router | API key `sk-pt-{64hex}`, SHA-256 hash | Événements, tickets |
| Réseau | NetBird VPN (WireGuard mesh), pas d'IP publique | Tout |
| Exec | Whitelist de commandes autorisées | Commandes Master |
| Fichiers | Restriction `/mnt/data/` + `/opt/flash-studio/` | Écritures |
| Secrets | Env vars uniquement, jamais dans les logs | Tout |
| Update | Binaire signé, checksum SHA-256 | Self-update |
| Isolation | Goroutine + recover par module | Crash isolation |

### Whitelist exec (commandes autorisées par le Master)

```go
var allowedCommands = map[string]bool{
    "docker compose up -d":       true,
    "docker compose pull":        true,
    "docker compose restart":     true,
    "docker compose stop":        true,
    "resticprofile backup":       true,
    "resticprofile check":        true,
    "systemctl restart flash-agent": true,
}
// Toute commande hors whitelist → rejet + événement security → Event Router
```

---

## Phases d'implémentation

### Phase 1 — MVP (~800 lignes Go)

| Module | Lignes | Priorité |
|--------|--------|----------|
| main.go (config, signal, goroutines) | ~100 | P0 |
| config/config.go | ~80 | P0 |
| transport/master_client.go | ~120 | P0 |
| transport/event_client.go | ~150 | P0 |
| core/heartbeat.go | ~60 | P0 |
| core/auth.go (JWT refresh) | ~80 | P0 |
| core/sync.go (config pull) | ~60 | P0 |
| modules/health/docker.go | ~80 | P0 |
| modules/health/system.go | ~70 | P0 |
| modules/events/emitter.go | ~100 | P0 |

**Résultat Phase 1 :** L'agent démarre, envoie des heartbeats au Master, émet des événements au Event Router, et alerte si un container tombe.

### Phase 2 — Opérations (~400 lignes)

| Module | Lignes | Priorité |
|--------|--------|----------|
| modules/events/collector.go (buffer) | ~120 | P1 |
| modules/tickets/creator.go | ~80 | P1 |
| modules/backup/restic.go | ~100 | P1 |
| modules/backup/schedule.go | ~60 | P1 |
| modules/exec/exec.go (whitelist) | ~80 | P1 |
| modules/update/update.go | ~100 | P1 |
| modules/meter/meter.go | ~80 | P1 |

**Résultat Phase 2 :** L'agent gère les backups, peut exécuter des commandes du Master, se met à jour automatiquement, et crée des tickets quand nécessaire.

### Phase 3 — MCPs (~600 lignes)

| Module | Lignes | Priorité |
|--------|--------|----------|
| mcps/server.go (Unix socket) | ~150 | P2 |
| mcps/n8n.go, nocodb.go, etc. | ~450 | P2 |

**Résultat Phase 3 :** Les clients MCP (OpenClaw, Claude Code, etc.) peuvent interagir avec les services locaux via le socket Unix de l'agent.

---

## Manifest.json (config depuis le Master)

```json
{
    "client_id": "client-42",
    "studio_name": "Studio Paul",
    "plan": "CREATOR",
    "profiles": ["base", "creation"],
    "agent_version_min": "1.2.0",
    "thresholds": {
        "disk_warning": 80,
        "disk_critical": 95,
        "ram_warning": 85,
        "ram_critical": 95,
        "cpu_warning": 80,
        "cpu_critical": 95
    },
    "backup": {
        "cron": "0 */6 * * *",
        "retention_days": 30,
        "s3_bucket": "flash-backups-client42"
    },
    "exec_whitelist": [
        "docker compose up -d",
        "docker compose pull",
        "docker compose restart",
        "resticprofile backup"
    ],
    "services_critical": ["postgres", "caddy", "litellm"],
    "updated_at": "2026-03-10T14:30:00Z"
}
```

---

## systemd service

```ini
# /etc/systemd/system/flash-agent.service
[Unit]
Description=Flash Agent — VPS client monitoring & management
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/opt/flash-studio/.env
ExecStart=/opt/flash-studio/flash-agent
Restart=always
RestartSec=5
LimitNOFILE=65535

# Sécurité systemd
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/mnt/data /opt/flash-studio
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

---

## CI/CD (GitHub Actions)

```yaml
name: CI

on:
  push:
    branches: [main, 'feat/**', 'fix/**']
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - run: go vet ./...
      - run: go test -v -race -coverprofile=coverage.out ./...
      - run: CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o flash-agent .

  release:
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - name: Build binaries
        run: |
          CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o flash-agent-linux-amd64 .
          CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o flash-agent-linux-arm64 .
          sha256sum flash-agent-linux-* > checksums.txt
      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: agent-v${{ github.run_number }}
          files: |
            flash-agent-linux-amd64
            flash-agent-linux-arm64
            checksums.txt
          generate_release_notes: true
```

---

## Diagramme de flux complet

```
                    ┌─────────────────────────────────────────────────┐
                    │              VPS Client                          │
                    │                                                  │
                    │  ┌──────────────────────────────────────────┐   │
                    │  │           flash-agent (Go)                │   │
                    │  │                                           │   │
                    │  │  ┌──────────┐  ┌──────────┐  ┌────────┐ │   │
                    │  │  │Heartbeat │  │  Health   │  │ Backup │ │   │
                    │  │  │  (60s)   │  │  (30s)   │  │ (cron) │ │   │
                    │  │  └────┬─────┘  └──┬───┬───┘  └──┬──┬──┘ │   │
                    │  │       │           │   │          │  │     │   │
                    │  │       │ JWT       │   │ API key  │  │     │   │
                    │  │       ▼           │   ▼          │  ▼     │   │
                    │  │  ┌─────────┐   ┌──────────────┐          │   │
                    │  │  │ Master  │   │ Event Router │          │   │
                    │  │  │ Client  │   │    Client    │          │   │
                    │  │  └────┬────┘   └──────┬───────┘          │   │
                    │  │       │               │                   │   │
                    │  └───────┼───────────────┼───────────────────┘   │
                    │          │               │                       │
                    └──────────┼───────────────┼───────────────────────┘
                               │               │
                     NetBird VPN (mesh privé)
                               │               │
               ┌───────────────┘               └───────────────┐
               ▼                                               ▼
    ┌──────────────────┐                         ┌──────────────────────┐
    │   MASTER (Next.js)│                         │ SERVICE DESK          │
    │  *.paultaffe.net  │                         │ *.paultaffe.com       │
    │                    │                         │                       │
    │ • Config sync      │                         │ • Event Router (Go)   │
    │ • Heartbeat store  │                         │ • Zammad (ticketing)  │
    │ • Provisioning     │                         │ • Discourse (terrasse)│
    │ • Billing (Stripe) │                         │ • Gatus (status)      │
    │ • Agent tokens JWT │                         │ • Portail (dashboard) │
    │ • Source de vérité │                         │ • Support Agent (RAG) │
    └──────────────────┘                         └──────────────────────┘
```
