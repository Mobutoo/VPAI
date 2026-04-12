# Phase 10: AI Ops — Research

**Researched:** 2026-04-12
**Domain:** Langfuse v3 self-hosted, Arize Phoenix, Claude Code JSONL ETL, Caddy VPN-only
**Confidence:** HIGH (Langfuse stack verified via official docs + GitHub), MEDIUM (Arize Phoenix resource data), HIGH (JSONL field mapping — verified from live sessions)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Serveur cible** : Nouveau serveur permanent — Hetzner CX32 (4 vCPU / 8 GB) ou Oracle VM (4 vCPU / 24 GB). Choix au moment du provisioning.
- **Groupe inventaire** `ai_ops`, host `ai-ops-prod`, port SSH 804, user `mobuone`
- **Mesh Tailscale** : rejoint via rôle `headscale-node` existant
- **Rôles à créer** : `langfuse`, `ai-ops-caddy`, optionnel `arize-phoenix`
- **Playbook** : `playbooks/hosts/ai-ops.yml`
- **Langfuse v3+** avec ClickHouse, PostgreSQL, Redis, MinIO
- **VPN-only** : `langfuse.ewutelo.cloud` accessible uniquement depuis mesh Tailscale
- **Ingestion JSONL** : hook SessionStop → batch ETL → Langfuse Python SDK. PAS d'interception OAuth. PAS de watcher inotify.
- **Corrélation git↔Langfuse (AIOPS-09)** : script custom, sha court comme metadata de trace
- **Bac à sable recette (AIOPS-06)** : remplace app-prod éphémère, playbook app-prod.yml réutilisable
- **Conventions VPAI** : images pinnées, FQCN, changed_when/failed_when, log rotation, réseaux nommés, healthchecks

### Claude's Discretion
- Choix Hetzner CX32 vs Oracle VM au provisioning
- Décision finale sur Arize Phoenix (déployer ou skiper) — confirmée par cette recherche : SKIP (voir section Arize Phoenix Verdict)

### Deferred Ideas (OUT OF SCOPE)
- Intégration LiteLLM → Langfuse (callback natif)
- Multi-platform publishing (Instagram, TikTok)
- Analytics feedback loop Instagram
- ElevenLabs voiceover
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AIOPS-01 | Nouveau serveur Hetzner CX32 permanent dans inventaire Ansible (`ai_ops` group) | Section inventaire + RAM budget |
| AIOPS-02 | Rôle `langfuse` — Langfuse + ClickHouse + Redis + MinIO via Docker Compose, VPN-only | Section Standard Stack + Architecture Patterns |
| AIOPS-03 | Rôle `arize-phoenix` — optionnel, valeur à confirmer | Section Arize Phoenix Verdict |
| AIOPS-04 | Reverse proxy Caddy VPN-only pour Langfuse (et Phoenix si déployé) | Section Caddy VPN-only Pattern |
| AIOPS-05 | Rejoint mesh Tailscale via `headscale-node` existant | Rôle existant, pas de nouvelle recherche nécessaire |
| AIOPS-06 | Bac à sable recette apps sur le même serveur | Section Architecture — Bac à sable |
| AIOPS-07 | Sessions Claude Code (JSONL) → Langfuse traces via hook SessionStop | Section JSONL Field Mapping + Code Examples |
| AIOPS-08 | Arize Phoenix — évaluation RAG Qdrant via instrumentation ai-memory-worker | Section Arize Phoenix Verdict (SKIP recommandé) |
| AIOPS-09 | Corrélation git↔Langfuse — sha court comme metadata trace | Section git↔Langfuse Correlation |
</phase_requirements>

---

## Summary

Phase 10 provisionne un nouveau serveur AI Ops hébergeant Langfuse v3 self-hosted (traces et evals pour sessions Claude Code), avec ingestion batch depuis les fichiers JSONL. Le stack Langfuse v3 est stable et bien documenté : 6 services Docker (langfuse-web, langfuse-worker, ClickHouse, PostgreSQL, Redis, MinIO). La contrainte critique est RAM : CX32 (8 GB) est **juste viable** avec ClickHouse tuné (config low-memory obligatoire), mais l'Oracle VM (24 GB) est préférable si disponible.

Arize Phoenix est **recommandé SKIP** pour cette phase : 2 GB RAM supplémentaires sur un CX32 déjà contraint, valeur marginale vs Langfuse seul pour le use case (ETL batch de sessions JSONL — pas de RAG live). Phoenix peut être ajouté en Phase 11 si le besoin d'évaluation RAG de `ai-memory-worker` se confirme.

Le SDK Python Langfuse est en v4 (avril 2026, basé OpenTelemetry). L'API a changé significativement vs v2/v3 — utiliser `start_as_current_observation` + `propagate_attributes()` au lieu de l'ancienne API `trace()` / `generation()`.

**Primary recommendation:** Déployer sur Oracle VM (24 GB) si disponible pour éviter le tuning ClickHouse. Sinon CX32 avec config low-memory ClickHouse obligatoire.

---

## RAM Budget Analysis (CRITICAL)

| Service | RAM idle (min) | RAM idle (typical) | Source |
|---------|---------------|--------------------|--------|
| langfuse-web | ~200 MB | ~400 MB | [ASSUMED] Node.js Next.js |
| langfuse-worker | ~150 MB | ~300 MB | [ASSUMED] Node.js worker |
| ClickHouse (non tuné) | 2–4 GB | 4–8 GB | [CITED: clickhouse.com/docs/guides/sizing-and-hardware-recommendations] |
| ClickHouse (low-mem tuné) | ~800 MB | ~1.5 GB | [CITED: jamesoclaire.com/2024/12/20/clickhouse-in-less-than-2gb-ram-in-docker/] |
| PostgreSQL (Langfuse DB) | ~100 MB | ~200 MB | [ASSUMED] PG 16 idle |
| Redis | ~50 MB | ~100 MB | [ASSUMED] Redis 7 idle |
| MinIO | ~100 MB | ~200 MB | [ASSUMED] MinIO idle |
| Caddy | ~30 MB | ~50 MB | [ASSUMED] Caddy 2.x |
| OS + Docker | ~500 MB | ~800 MB | [ASSUMED] Debian bookworm |

**CX32 (8 GB) total avec ClickHouse tuné : ~2.0–3.5 GB — viable avec marge ~4 GB pour sandbox apps.**
**CX32 (8 GB) avec ClickHouse non tuné : ~5–8 GB — insuffisant avec sandbox.**

> **Le tuning ClickHouse est OBLIGATOIRE sur CX32.** Voir section Code Examples.

> **Oracle VM (24 GB) : aucun tuning requis, recommandé si disponible.**

---

## Standard Stack

### Core — Langfuse v3

| Service | Image | Version | Purpose |
|---------|-------|---------|---------|
| langfuse-web | `docker.io/langfuse/langfuse` | `3.68.0` | UI + API server |
| langfuse-worker | `docker.io/langfuse/langfuse-worker` | `3.68.0` | Async event processing |
| ClickHouse | `docker.io/clickhouse/clickhouse-server` | `24.3` | Analytics backend (traces) |
| PostgreSQL | `docker.io/postgres` | `16-bookworm` | Metadata + config (partagé) |
| Redis | `docker.io/redis` | `7-bookworm` | Queue + cache |
| MinIO | `cgr.dev/chainguard/minio` | latest stable | S3-compatible blob storage |
| Caddy | `caddy:2.11.2-alpine` | `2.11.2` | Reverse proxy VPN-only |

> **Version VPAI conflict** : L'image officielle Langfuse docker-compose.yml utilise le tag `:3` (floating). La convention VPAI interdit `:latest` et les tags flottants — utiliser `3.68.0` (dernière version stable vérifiée sur Docker Hub, tag `3.6.1` visible [CITED: hub.docker.com/r/langfuse/langfuse-worker/tags]). Vérifier la version exacte au moment du déploiement via `docker pull langfuse/langfuse:3 && docker inspect langfuse/langfuse:3 | grep RepoDigests`.

> **ClickHouse version** : `24.3` est le minimum supporté par Langfuse [CITED: langfuse.com/self-hosting/deployment/infrastructure/clickhouse]. Les versions 25.6+ ont des bugs de memory usage extrême lors des deletions. Utiliser `24.3` pour stabilité sur ressources contraintes.

> **PostgreSQL** : Le projet utilise déjà `postgres:18.3-bookworm` sur Sese-AI. Sur le nouveau serveur ai-ops, utiliser `postgres:16-bookworm` ou `postgres:17-bookworm` (Langfuse supporte >= 12). Partager l'instance PostgreSQL avec les apps sandbox : **oui, safe** — Langfuse utilise le schéma `public` d'une database dédiée `langfuse_db` [CITED: langfuse.com/self-hosting/deployment/infrastructure/postgres].

### Installation (pip — ETL script sur Waza)

```bash
pip install langfuse==4.2.0
```

> Langfuse Python SDK v4 (2026-04-10) — basé OpenTelemetry. Breaking changes vs v2/v3. [VERIFIED: pypi.org/project/langfuse/]

---

## Architecture Patterns

### Structure Docker Compose (roles/langfuse/)

```
roles/langfuse/
├── tasks/main.yml
├── handlers/main.yml
├── defaults/main.yml          # langfuse_image, clickhouse_image, etc.
├── templates/
│   ├── docker-compose.yml.j2  # 6 services
│   ├── langfuse.env.j2        # secrets + config
│   └── clickhouse-low-mem.xml.j2  # tuning mémoire CX32
└── vars/main.yml
```

### Pattern 1 : Services Langfuse v3

```yaml
# Source: github.com/langfuse/langfuse/blob/main/docker-compose.yml (verified 2026-04-12)
# 6 services : web + worker + clickhouse + postgres + redis + minio
# Toutes les dépendances via depends_on + healthchecks

services:
  langfuse-web:
    image: "{{ langfuse_image }}"          # docker.io/langfuse/langfuse:3.68.0
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    ports:
      - "127.0.0.1:3000:3000"             # exposé uniquement localement
    env_file:
      - langfuse.env
    depends_on:
      langfuse-postgres:
        condition: service_healthy
      langfuse-clickhouse:
        condition: service_healthy
      langfuse-redis:
        condition: service_healthy
      langfuse-minio:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000/api/public/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - frontend
      - backend
    mem_limit: "800m"

  langfuse-worker:
    image: "{{ langfuse_worker_image }}"   # docker.io/langfuse/langfuse-worker:3.68.0
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    env_file:
      - langfuse.env
    depends_on:
      langfuse-postgres:
        condition: service_healthy
      langfuse-clickhouse:
        condition: service_healthy
      langfuse-redis:
        condition: service_healthy
      langfuse-minio:
        condition: service_healthy
    networks:
      - backend
    mem_limit: "600m"

  langfuse-clickhouse:
    image: "{{ clickhouse_image }}"        # clickhouse/clickhouse-server:24.3
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    environment:
      CLICKHOUSE_DB: "{{ langfuse_clickhouse_db }}"
      CLICKHOUSE_USER: "{{ langfuse_clickhouse_user }}"
      CLICKHOUSE_PASSWORD: "{{ langfuse_clickhouse_password }}"
    volumes:
      - langfuse_clickhouse_data:/var/lib/clickhouse
      - langfuse_clickhouse_logs:/var/log/clickhouse-server
      - ./clickhouse-low-mem.xml:/etc/clickhouse-server/config.d/low-mem.xml:ro
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8123/ping"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks:
      - backend
    mem_limit: "2g"

  langfuse-postgres:
    image: "{{ postgresql_image }}"        # postgres:16-bookworm (ou instance partagée)
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    environment:
      POSTGRES_DB: "langfuse_db"
      POSTGRES_USER: "langfuse"
      POSTGRES_PASSWORD: "{{ postgresql_password }}"
      TZ: "UTC"
      PGTZ: "UTC"
    volumes:
      - langfuse_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse -d langfuse_db"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks:
      - backend

  langfuse-redis:
    image: "{{ redis_image }}"             # redis:7-bookworm
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    command: redis-server --requirepass "{{ langfuse_redis_password }}"
    healthcheck:
      test: ["CMD", "redis-cli", "--pass", "{{ langfuse_redis_password }}", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - langfuse_redis_data:/data
    networks:
      - backend

  langfuse-minio:
    image: "{{ minio_image }}"
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
    environment:
      MINIO_ROOT_USER: "{{ langfuse_minio_user }}"
      MINIO_ROOT_PASSWORD: "{{ langfuse_minio_password }}"
    command: server /data --console-address ":9001"
    ports:
      - "127.0.0.1:9090:9000"
      - "127.0.0.1:9091:9001"
    volumes:
      - langfuse_minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks:
      - backend
```

> **Note VPAI critique** : MinIO est **required** (pas optionnel) pour Langfuse v3 self-hosted. [CITED: langfuse.com/self-hosting/deployment/docker-compose] — "This docker compose setup by default uses MinIO for blob storage."

### Pattern 2 : Variables d'environnement Langfuse

```ini
# langfuse.env.j2 — variables required (marquées CHANGEME dans le compose officiel)
# Source: langfuse.com/self-hosting/configuration (verified 2026-04-12)

# Auth
NEXTAUTH_URL=https://langfuse.{{ domain_name }}
NEXTAUTH_SECRET={{ langfuse_nextauth_secret }}      # openssl rand -base64 32
SALT={{ langfuse_salt }}                             # openssl rand -base64 32
ENCRYPTION_KEY={{ langfuse_encryption_key }}        # openssl rand -hex 32 (64 chars hex)

# PostgreSQL
DATABASE_URL=postgresql://langfuse:{{ postgresql_password }}@langfuse-postgres:5432/langfuse_db
DIRECT_URL=postgresql://langfuse:{{ postgresql_password }}@langfuse-postgres:5432/langfuse_db

# ClickHouse
CLICKHOUSE_MIGRATION_URL=clickhouse://langfuse-clickhouse:9000
CLICKHOUSE_URL=http://langfuse-clickhouse:8123
CLICKHOUSE_USER={{ langfuse_clickhouse_user }}
CLICKHOUSE_PASSWORD={{ langfuse_clickhouse_password }}

# Redis
REDIS_CONNECTION_STRING=redis://:{{ langfuse_redis_password }}@langfuse-redis:6379

# MinIO / S3
LANGFUSE_S3_EVENT_UPLOAD_BUCKET=langfuse-events
LANGFUSE_S3_MEDIA_UPLOAD_BUCKET=langfuse-media
LANGFUSE_S3_BATCH_EXPORT_BUCKET=langfuse-exports
LANGFUSE_S3_ACCESS_KEY_ID={{ langfuse_minio_user }}
LANGFUSE_S3_SECRET_ACCESS_KEY={{ langfuse_minio_password }}
LANGFUSE_S3_ENDPOINT=http://langfuse-minio:9000
LANGFUSE_S3_FORCE_PATH_STYLE=true
LANGFUSE_S3_REGION=us-east-1

# Timezone (REQUIRED — Langfuse expects UTC)
TZ=UTC

# Optionnel — init org/user au premier démarrage
LANGFUSE_INIT_ORG_ID=vpai-org
LANGFUSE_INIT_ORG_NAME=VPAI
LANGFUSE_INIT_PROJECT_ID=claude-sessions
LANGFUSE_INIT_PROJECT_NAME=Claude Sessions
LANGFUSE_INIT_USER_EMAIL={{ langfuse_admin_email }}
LANGFUSE_INIT_USER_PASSWORD={{ langfuse_admin_password }}
```

### Anti-Patterns to Avoid
- **`:latest` sur langfuse/langfuse et langfuse/langfuse-worker** : le docker-compose officiel utilise `:3` (floating) — VIOLATION VPAI. Pinner à `3.x.y` exact.
- **MinIO optionnel** : Certains guides indiquent S3 comme optionnel — c'est FAUX pour le compose Docker self-hosted. MinIO est requis.
- **PostgreSQL sans TZ=UTC** : Langfuse plante si la timezone PostgreSQL n'est pas UTC.
- **ClickHouse sans tuning mémoire sur CX32** : défaut = allocate all RAM = OOM sur 8 GB.

---

## ClickHouse Low-Memory Config (CX32 OBLIGATOIRE)

```xml
<!-- Source: jamesoclaire.com/2024/12/20/clickhouse-in-less-than-2gb-ram-in-docker/ -->
<!-- templates/clickhouse-low-mem.xml.j2 -->
<?xml version="1.0"?>
<clickhouse>
  <!-- Réduit cache allocation sur hosts mémoire contraints -->
  <cache_size_to_ram_max_ratio replace="replace">0.2</cache_size_to_ram_max_ratio>
  <!-- Autorise usage swap sur hosts low-memory -->
  <max_server_memory_usage_to_ram_ratio replace="replace">2</max_server_memory_usage_to_ram_ratio>
  <!-- Nuclear option si encore des OOM : décommenter -->
  <!-- <mark_cache_size>1073741824</mark_cache_size> -->
</clickhouse>
```

> Avec cette config, ClickHouse reste sous ~1.5 GB RAM sur 8 GB. [CITED: jamesoclaire.com/2024/12/20/clickhouse-in-less-than-2gb-ram-in-docker/]

---

## JSONL Field Mapping → Langfuse Trace

### Chemin exact des sessions

```
~/.claude/projects/<project-slug>/<session-uuid>.jsonl
```

**Exemples vérifiés :**
```
~/.claude/projects/-home-mobuone-VPAI/00ebde54-92bd-49e5-bfef-7f64624e20a6.jsonl
~/.claude/projects/-home-mobuone-flash-studio/...
```
[VERIFIED: ls ~/.claude/projects/ — 2026-04-12, 5 project slugs]

### Champs disponibles (vérifiés sur sessions réelles)

```python
# Source: analyse directe de sessions JSONL — 2026-04-12

# --- Par ligne JSONL ---
record = {
    "type": "user|assistant|system|attachment|file-history-snapshot|queue-operation",
    "uuid": "str",
    "parentUuid": "str|null",
    "timestamp": "2026-04-12T10:03:48.365Z",    # ISO8601 sur chaque record
    "isSidechain": bool,
    
    # Pour type="assistant" :
    "message": {
        "role": "assistant",
        "model": "claude-sonnet-4-6",            # modèle exact
        "content": [
            {"type": "text", "text": "..."},
            {
                "type": "tool_use",
                "name": "Bash",                   # nom de l'outil
                "id": "...",
                "input": {...}
            }
        ],
        "usage": {
            "input_tokens": 3,
            "cache_creation_input_tokens": 23724,
            "cache_read_input_tokens": 14269,
            "output_tokens": 229,
            "server_tool_use": {
                "web_search_requests": 0,
                "web_fetch_requests": 0
            },
            "service_tier": "standard",
            "cache_creation": {
                "ephemeral_1h_input_tokens": 23724,
                "ephemeral_5m_input_tokens": 0
            },
            "speed": "standard"
        }
    }
}
```
[VERIFIED: python3 analyse sessions JSONL — 2026-04-12]

### Mapping JSONL → Champs Trace Langfuse

| Champ Langfuse | Source JSONL | Calcul |
|----------------|-------------|--------|
| `session_id` | UUID du fichier JSONL (`<session-uuid>.jsonl`) | nom de fichier sans extension |
| `user_id` | `"mobuone"` (fixe — single user) | hardcoded |
| `name` | `projet/<slug>` | dérivé du chemin parent |
| `start_time` | `min(record.timestamp)` sur tous les records | premier timestamp |
| `end_time` | `max(record.timestamp)` | dernier timestamp |
| `input_tokens` | `sum(msg.usage.input_tokens)` pour type=assistant | agrégation |
| `cache_creation_tokens` | `sum(msg.usage.cache_creation_input_tokens)` | agrégation |
| `cache_read_tokens` | `sum(msg.usage.cache_read_input_tokens)` | agrégation |
| `output_tokens` | `sum(msg.usage.output_tokens)` | agrégation |
| `model` | `msg.message.model` (premier assistant record) | valeur directe |
| `tool_calls_count` | `count(content[].type == "tool_use")` | agrégation |
| `tool_calls_by_type` | dict groupé par `content[].name` | ex: `{"Bash":21, "Read":25}` |
| `metadata.git_sha` | AIOPS-09 : injection par script commit | voir section git↔Langfuse |
| `metadata.project_slug` | path `~/.claude/projects/<slug>/` | extrait du chemin |

### Code ETL (SessionStop hook)

```python
# Source: analyse JSONL + SDK Langfuse v4 docs (2026-04-12)
# Compatible avec langfuse==4.2.0 (SDK v4, OpenTelemetry-based)

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from langfuse import Langfuse

def parse_session_jsonl(jsonl_path: str) -> dict:
    """Parse un fichier JSONL de session Claude Code en métriques agrégées."""
    records = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not records:
        return None

    # Agrégation tokens
    input_tokens = 0
    output_tokens = 0
    cache_creation_tokens = 0
    cache_read_tokens = 0
    tool_calls = {}
    model = None
    timestamps = []

    for rec in records:
        ts = rec.get("timestamp")
        if ts:
            try:
                timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except ValueError:
                pass

        if rec.get("type") == "assistant":
            msg = rec.get("message", {})
            usage = msg.get("usage", {})
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
            cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            if not model:
                model = msg.get("model")
            for content in msg.get("content", []):
                if isinstance(content, dict) and content.get("type") == "tool_use":
                    name = content.get("name", "unknown")
                    tool_calls[name] = tool_calls.get(name, 0) + 1

    total_tokens = input_tokens + output_tokens
    user_turn_count = sum(1 for r in records if r.get("type") == "user" and not r.get("isMeta"))

    return {
        "session_id": Path(jsonl_path).stem,
        "model": model or "unknown",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "cache_read_tokens": cache_read_tokens,
        "total_tokens": total_tokens,
        "tool_calls": tool_calls,
        "tool_calls_count": sum(tool_calls.values()),
        "user_turns": user_turn_count,
        "start_time": min(timestamps) if timestamps else None,
        "end_time": max(timestamps) if timestamps else None,
        "duration_seconds": (max(timestamps) - min(timestamps)).total_seconds() if len(timestamps) >= 2 else 0,
    }


def ingest_session_to_langfuse(jsonl_path: str, project_slug: str, git_sha: str = None):
    """Ingère une session Claude Code dans Langfuse comme trace."""
    metrics = parse_session_jsonl(jsonl_path)
    if not metrics:
        return

    langfuse = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", "https://langfuse.ewutelo.cloud"),
    )

    metadata = {
        "project": project_slug,
        "tool_calls": json.dumps(metrics["tool_calls"]),  # dict→str pour validation v4
        "user_turns": str(metrics["user_turns"]),
        "duration_seconds": str(int(metrics["duration_seconds"])),
        "cache_creation_tokens": str(metrics["cache_creation_tokens"]),
        "cache_read_tokens": str(metrics["cache_read_tokens"]),
    }
    if git_sha:
        metadata["git_sha_hooks"] = git_sha  # AIOPS-09

    # SDK v4 : context manager + propagate_attributes pour session_id/metadata
    with langfuse.start_as_current_observation(
        as_type="span",
        name=f"session/{project_slug}",
        input={"session_id": metrics["session_id"]},
        start_time=metrics["start_time"],
    ) as root_span:
        from langfuse import propagate_attributes
        with propagate_attributes(
            user_id="mobuone",
            session_id=metrics["session_id"],
            metadata=metadata,
            tags=[project_slug, metrics["model"]],
        ):
            # Génération = la session Claude complète
            with langfuse.start_as_current_observation(
                as_type="generation",
                name="claude-session",
                model=metrics["model"],
                start_time=metrics["start_time"],
            ) as gen:
                gen.update(
                    end_time=metrics["end_time"],
                    usage_details={
                        "input_tokens": metrics["input_tokens"],
                        "output_tokens": metrics["output_tokens"],
                    },
                    output={"tool_calls_count": metrics["tool_calls_count"]},
                )
        root_span.update(
            end_time=metrics["end_time"],
            output={"total_tokens": metrics["total_tokens"]},
        )

    langfuse.flush()
```

> **Note SDK v4** : La méthode `propagate_attributes()` est le remplacement v4 de l'ancienne API `trace(session_id=..., metadata=...)`. `usage_details` prend `input_tokens`/`output_tokens` (snake_case). `metadata` doit être `dict[str, str]` avec valeurs ≤ 200 chars. [CITED: langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4]

> **SDK v2/v3 legacy** : Si on préfère l'ancienne API (plus simple pour ETL) :
> ```python
> # Langfuse SDK v2 (pip install "langfuse<3")
> lf = Langfuse(public_key=..., secret_key=..., host=...)
> trace = lf.trace(name="session", session_id=sid, metadata=meta, tags=[...])
> gen = trace.generation(name="claude", model=model, usage={"input": n, "output": m})
> lf.flush()
> ```
> L'ancienne API `trace()` / `generation()` fonctionne toujours avec `langfuse<3` mais est deprecated. [ASSUMED — à vérifier si compatibilité v2 SDK encore maintenue avec Langfuse server v3+]

### Gestion sessions volumineuses (>100k tokens)

Pour les sessions >100k tokens (audité : ~100 sessions dans le projet VPAI), le script ETL tourne en post-session → pas de contrainte temps-réel. Traitement séquentiel record par record (pas de chargement complet en mémoire) avec le pattern `for line in f:` ci-dessus. Sur Waza (RPi5 16 GB), pas de risque OOM même sur les plus grosses sessions.

---

## Arize Phoenix Verdict

### SKIP recommandé pour Phase 10

| Critère | Langfuse seul | Langfuse + Phoenix |
|---------|--------------|-------------------|
| Sessions Claude Code → traces | ✅ complet | ✅ (doublon) |
| Eval RAG Qdrant (ai-memory-worker) | ⚠️ possible via traces manuelles | ✅ instrumentation native |
| RAM sur CX32 | ~2.5 GB | ~4.5 GB (+2 GB Phoenix) |
| Complexité déploiement | 6 services | 8 services |
| Use case actuel | ETL batch JSONL | ETL batch + RAG eval live |

**Verdict** : Phoenix apporte une valeur réelle uniquement si on instrumente `ai-memory-worker` pour capturer les appels Qdrant en temps réel. Ce use case est dans AIOPS-08 mais non critique pour Phase 10 (le batch ETL des sessions Claude Code suffit pour l'observabilité immédiate). Phoenix peut être ajouté en Phase 11 quand l'évaluation RAG devient un besoin opérationnel confirmé.

**Si Phoenix est déployé en Phase 11 :**
- Image : `arizephoenix/phoenix` — pinner à une version spécifique (ex: `4.0.0`) [ASSUMED — vérifier sur hub.docker.com/r/arizephoenix/phoenix/tags]
- RAM : ~2 GB idle avec SQLite embarqué [CITED: community.arize.com, Arize interne use 2GB/1 CPU]
- Base de données : SQLite embarqué suffisant pour ce volume (sessions Claude Code = faible débit)
- Instrumentation Qdrant : `arize-phoenix` package PyPI + `openinference` instrumentors pour qdrant-client

---

## Caddy VPN-only Pattern (ai-ops)

### Config minimale pour `langfuse.ewutelo.cloud`

```caddyfile
# Source: roles/caddy/ + GUIDE-CADDY-VPN-ONLY.md (verified 2026-04-12)
# À adapter dans roles/ai-ops-caddy/templates/Caddyfile.j2

{
    admin localhost:2019
    servers {
        # OBLIGATOIRE pour client_ip correct en Docker (DNAT)
        trusted_proxies static private_ranges
    }
}

(vpn_only) {
    # DEUX CIDRs obligatoires : Tailscale + Docker bridge frontend
    # REX-34 : HTTP/3 QUIC/UDP → DNAT → client_ip = gateway Docker (172.20.1.1)
    @blocked not client_ip {{ caddy_vpn_cidr }} {{ caddy_docker_frontend_cidr }}
    error @blocked 403
}

(vpn_error_page) {
    handle_errors {
        root * /srv
        rewrite * /restricted-zone.html
        file_server
    }
}

langfuse.{{ domain_name }} {
    import vpn_only
    import vpn_error_page
    reverse_proxy langfuse-web:3000
}
```

> **Variables Ansible** (même pattern que `roles/caddy/defaults/main.yml`) :
> ```yaml
> caddy_vpn_cidr: "{{ vpn_network_cidr }}"        # 100.64.0.0/10
> caddy_docker_frontend_cidr: "172.20.1.0/24"     # adapter si subnet différent
> ```

> **Split DNS obligatoire** : ajouter `langfuse.<domain>` → IP Tailscale du serveur ai-ops dans les `extra_records` Headscale. [CITED: GUIDE-CADDY-VPN-ONLY.md section 2.1]

---

## git↔Langfuse Correlation (AIOPS-09)

### Pattern script custom

```python
# Script : scripts/langfuse-tag-commit.py
# Déclenchement : git hook post-commit sur CLAUDE.md / hooks/
# Source: pattern custom basé sur AIOPS-09 spec

import subprocess
import os
from langfuse import Langfuse

def get_git_sha_short() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def tag_langfuse_version(git_sha: str, changed_files: list[str]):
    langfuse = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", "https://langfuse.ewutelo.cloud"),
    )
    # Écrire dans un fichier lu par le hook SessionStop
    state_file = os.path.expanduser("~/.claude/langfuse-git-sha")
    with open(state_file, "w") as f:
        f.write(git_sha)
    langfuse.flush()

if __name__ == "__main__":
    sha = get_git_sha_short()
    tag_langfuse_version(sha, [])
    print(f"Langfuse: tagged commit {sha}")
```

Le hook SessionStop lit `~/.claude/langfuse-git-sha` et injecte la valeur dans `metadata["git_sha_hooks"]` de chaque trace ingérée.

---

## Architecture — Bac à sable recette (AIOPS-06)

Le bac à sable recette partage le même serveur ai-ops. Structure :

```
/opt/{{ project_name }}/
├── ai-ops/                    # Langfuse stack
│   ├── docker-compose.yml
│   └── langfuse.env
└── sandbox/                   # Apps recette
    ├── docker-compose.yml     # réutilise app-prod.yml pattern
    └── .env
```

PostgreSQL est partagé entre Langfuse (`langfuse_db`) et les apps sandbox (databases séparées). Pattern validé : Langfuse utilise uniquement le schéma `public` de sa propre database. [CITED: langfuse.com/self-hosting/deployment/infrastructure/postgres]

---

## Inventaire Ansible — Pattern

```yaml
# inventory/hosts.yml — ajouter le groupe ai_ops
ai_ops:
  hosts:
    ai-ops-prod:
      ansible_host: "{{ ai_ops_ip | default('127.0.0.1') }}"
      ansible_port: 804
      ansible_user: "mobuone"
      target_env: "ai_ops"
```

---

## Don't Hand-Roll

| Problème | Ne pas construire | Utiliser | Pourquoi |
|----------|------------------|----------|----------|
| Tracing + UI observabilité | Dashboard custom | Langfuse v3 | Session grouping, datasets, evals natifs |
| Queue async events | Queue Python custom | Redis + langfuse-worker | Déjà intégré dans le stack |
| S3 blob storage | Filesystem local | MinIO | Langfuse worker upload async media, obligatoire |
| ClickHouse memory tuning | Capping Docker seul | config.d/low-mem.xml | Docker mem_limit ne contrôle pas l'allocateur ClickHouse |
| Session cost tracking | Calcul custom | usage_details SDK | Langfuse calcule le coût automatiquement depuis le model name |

---

## Common Pitfalls

### Pitfall 1 : ClickHouse OOM sur CX32
**What goes wrong :** ClickHouse démarre et consomme toute la RAM disponible (défaut = 80% RAM pour page cache), le système swap, les autres services sont OOM-killed.
**Why :** Le comportement par défaut de ClickHouse est d'allouer le maximum possible de RAM.
**How to avoid :** Monter `clickhouse-low-mem.xml` via volume avec `cache_size_to_ram_max_ratio=0.2`.
**Warning signs :** `dmesg | grep -i oom` sur le host.

### Pitfall 2 : Images langfuse tag flottant `:3`
**What goes wrong :** Violation convention VPAI (images non pinnées), risque de breaking change silencieux entre déploiements.
**Why :** L'image officielle utilise `:3` par défaut (major version flottant).
**How to avoid :** Pinner à `langfuse/langfuse:3.68.0` et `langfuse/langfuse-worker:3.68.0` dans `versions.yml`. Vérifier la version exacte disponible via `docker pull langfuse/langfuse:3 && docker inspect`.
**Warning signs :** `versions.yml` contient `:3` sans patch version.

### Pitfall 3 : PostgreSQL timezone non-UTC
**What goes wrong :** Langfuse plante au démarrage ou les timestamps sont corrompus.
**Why :** Langfuse exige UTC sur tous ses composants infra.
**How to avoid :** Ajouter `TZ=UTC` et `PGTZ=UTC` dans l'env PostgreSQL, et `TZ=UTC` dans les containers Langfuse.
**Warning signs :** Erreurs de migration Langfuse au premier démarrage.

### Pitfall 4 : MinIO absent ou mal configuré
**What goes wrong :** langfuse-worker crash loop — ne peut pas uploader les events vers S3.
**Why :** MinIO est required pour Langfuse v3 self-hosted, pas optionnel.
**How to avoid :** Créer les buckets MinIO avant le premier démarrage de langfuse-worker (task Ansible `mc mb`).
**Warning signs :** Logs `S3 connection refused` dans langfuse-worker.

### Pitfall 5 : SDK Langfuse v4 vs v3 API cassée
**What goes wrong :** Le script ETL utilise l'ancienne API `langfuse.trace()` / `langfuse.generation()` (v2) qui n'existe plus en v4.
**Why :** SDK v4 a été réécrit sur OpenTelemetry (mars 2026), API complètement changée.
**How to avoid :** Installer `langfuse==4.2.0` et utiliser `start_as_current_observation` + `propagate_attributes()`.
**Warning signs :** `AttributeError: 'Langfuse' object has no attribute 'trace'`.

### Pitfall 6 : Split DNS manquant pour le serveur ai-ops
**What goes wrong :** `langfuse.ewutelo.cloud` ne se résout pas vers l'IP Tailscale du nouveau serveur — les clients VPN tombent sur l'IP publique et sont bloqués par Caddy (ou pire, le port 3000 est exposé publiquement).
**Why :** Chaque nouveau serveur nécessite un `extra_records` dans la config Headscale.
**How to avoid :** Ajouter l'entrée DNS dans le rôle `vpn-dns` ou `headscale` existant avant le déploiement Caddy.
**Warning signs :** `Resolve-DnsName langfuse.ewutelo.cloud` retourne l'IP publique (pas `100.64.x.x`).

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Langfuse v2 (PostgreSQL seul) | Langfuse v3 (PostgreSQL + ClickHouse) | Dec 2024 | ClickHouse obligatoire pour analytics — stack plus lourd |
| Langfuse Python SDK v2 `trace()` | SDK v4 `start_as_current_observation()` | Mars 2026 | API complètement réécrite sur OTel |
| ClickHouse tag `:latest` | ClickHouse `24.3` (minimum Langfuse) | — | Versions 25.6+ ont memory bug |
| Arize Phoenix in-process `px.launch_app()` | Phoenix Docker serveur | 2024 | Mode serveur recommandé pour production |

**Deprecated/outdated :**
- `langfuse.trace()` / `langfuse.generation()` : API v2, dépréciée en SDK v4
- Langfuse v2 (PostgreSQL seul) : plus supporté pour les nouvelles installations

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | langfuse-web idle RAM ~200-400 MB | RAM Budget | Peut être plus si beaucoup de sessions chargées — monitorer |
| A2 | PostgreSQL idle ~100-200 MB (instance dédiée ai-ops) | RAM Budget | OK — PG est très stable à l'idle |
| A3 | MinIO idle ~100-200 MB | RAM Budget | Peut être moins — MinIO est léger |
| A4 | Version exacte langfuse 3.68.0 | Standard Stack | Vérifier `docker pull langfuse/langfuse:3` au déploiement — le patch version peut avoir changé |
| A5 | SDK v2 `trace()` API encore disponible avec `langfuse<3` | Code Examples | Si abandonnée, utiliser uniquement v4 API |
| A6 | Phoenix `4.0.0` version tag valide | Arize Phoenix | Vérifier hub.docker.com/r/arizephoenix/phoenix/tags |

---

## Open Questions

1. **Hetzner CX32 vs Oracle VM**
   - What we know : CX32 (8 GB) viable avec tuning ClickHouse. Oracle VM (24 GB) comfortable.
   - What's unclear : Disponibilité Oracle Free Tier au moment du provisioning.
   - Recommendation : Tenter Oracle VM en premier. Si indisponible → CX32 avec low-mem config obligatoire.

2. **PostgreSQL partagé ou dédié pour sandbox**
   - What we know : Langfuse supporte PostgreSQL partagé (databases séparées). Convention VPAI utilise un PG partagé sur Sese-AI.
   - What's unclear : Volume apps sandbox sur ai-ops — risque de contention PG.
   - Recommendation : Instance PG dédiée au serveur ai-ops (pas partagée avec Sese-AI) — déjà dans le scope du rôle `langfuse`.

3. **MinIO buckets creation automation**
   - What we know : Langfuse nécessite 3 buckets MinIO créés avant démarrage.
   - What's unclear : Comment créer les buckets automatiquement (task Ansible `docker exec mc mb` ou init container).
   - Recommendation : Task Ansible `ansible.builtin.command: docker exec langfuse-minio mc mb langfuse-events` avec `creates: /data/langfuse-events` pour idempotence.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | langfuse SDK v4 | ✓ | 3.11 (Waza RPi5) | — |
| Docker + Compose V2 | Rôle langfuse | ✓ | Via rôle `docker` existant | — |
| Hetzner CX32 | AIOPS-01 | [ASSUMED] | À provisionner | Oracle VM 24 GB |
| Tailscale mesh | AIOPS-05 | ✓ | Via headscale-node | — |
| pip3 | ETL script install | ✓ | pip 23.x sur Waza | — |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (si tests Python ETL) / molecule (rôle Ansible) |
| Config file | `roles/langfuse/molecule/` à créer |
| Quick run command | `molecule converge` |
| Full suite command | `molecule test` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AIOPS-02 | Langfuse containers démarrent et sont healthy | smoke | `docker compose ps --format json | python3 -c "..."` | ❌ Wave 0 |
| AIOPS-04 | Caddy bloque accès non-VPN | manual | `curl -k https://langfuse.ewutelo.cloud` hors VPN → 403 | manual |
| AIOPS-07 | ETL script ingère session JSONL sans erreur | unit | `pytest tests/test_etl.py -x` | ❌ Wave 0 |
| AIOPS-09 | git sha apparaît dans trace metadata Langfuse | integration | `pytest tests/test_git_correlation.py` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `scripts/session-to-langfuse/tests/test_etl.py` — couvre AIOPS-07
- [ ] `scripts/session-to-langfuse/tests/test_git_correlation.py` — couvre AIOPS-09
- [ ] Framework install: `pip install pytest langfuse==4.2.0` dans venv dédié

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Langfuse NEXTAUTH + admin password via Vault |
| V3 Session Management | no | Interne Langfuse |
| V4 Access Control | yes | Caddy VPN-only (100.64.0.0/10 + Docker frontend CIDR) |
| V5 Input Validation | yes | JSONL parsing — valider `json.JSONDecodeError`, limiter taille fichier |
| V6 Cryptography | yes | NEXTAUTH_SECRET + ENCRYPTION_KEY via `openssl rand` — jamais hardcodé |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Langfuse UI accessible depuis Internet | Spoofing/Info Disclosure | Caddy VPN-only (double CIDR) |
| MinIO accessible depuis Docker network | Elevation of Privilege | Bind sur 127.0.0.1, pas de port public |
| Secrets en clair dans env | Info Disclosure | Variables Vault Ansible, env_file avec owner `mobuone` |
| JSONL contenant des secrets (token values) | Info Disclosure | Parser extrait uniquement les métriques agrégées — jamais le contenu des messages |

---

## Sources

### Primary (HIGH confidence)
- `github.com/langfuse/langfuse/blob/main/docker-compose.yml` — services, images, volumes (verified 2026-04-12)
- `langfuse.com/self-hosting/configuration` — environment variables requis (verified 2026-04-12)
- `langfuse.com/self-hosting/deployment/infrastructure/clickhouse` — version ClickHouse >= 24.3 (verified 2026-04-12)
- `langfuse.com/self-hosting/deployment/infrastructure/postgres` — PostgreSQL partagé, schéma public, TZ=UTC (verified 2026-04-12)
- `langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4` — SDK v4 breaking changes (verified 2026-04-12)
- `pypi.org/project/langfuse/` — version 4.2.0 (2026-04-10) [VERIFIED]
- `~/.claude/projects/-home-mobuone-VPAI/*.jsonl` — structure JSONL champs disponibles [VERIFIED 2026-04-12]
- `GUIDE-CADDY-VPN-ONLY.md` — pattern Caddy VPN, deux CIDRs obligatoires [VERIFIED from codebase]

### Secondary (MEDIUM confidence)
- `jamesoclaire.com/2024/12/20/clickhouse-in-less-than-2gb-ram-in-docker/` — ClickHouse low-mem config XML
- `hub.docker.com/r/langfuse/langfuse-worker/tags` — versions 3.5.0, 3.6.1 visibles
- `community.arize.com` + Arize docs — Phoenix 2 GB RAM idle

### Tertiary (LOW confidence)
- RAM estimations pour langfuse-web, langfuse-worker, MinIO, Redis, OS — estimations training knowledge, à mesurer en prod

---

## Metadata

**Confidence breakdown :**
- Standard stack : HIGH — docker-compose officiel vérifié, versions ClickHouse documentées
- Architecture : HIGH — pattern calqué sur rôles existants VPAI
- JSONL mapping : HIGH — vérifié sur sessions réelles
- Pitfalls : HIGH — basé sur REX VPAI existant + docs officielles
- RAM budget : MEDIUM — ClickHouse vérifié, autres services ASSUMED

**Research date :** 2026-04-12
**Valid until :** 2026-05-12 (SDK v4 est récent — vérifier si new breaking changes avant implémentation)
