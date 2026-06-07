# Phase 10 — Track B : Stack 100% Maison (Remplacement Langfuse)

**Date :** 2026-04-12  
**Statut :** Spec complète — prête pour planification  
**Périmètre :** ETL sessions JSONL locales → observabilité distribuée sans Langfuse, sans interception API

---

## Principe fondamental

Claude Code tourne en OAuth Anthropic (Max). Zéro interception possible des appels API.  
Source de données unique : **fichiers JSONL** dans `~/.claude/projects/<project-slug>/<session-id>.jsonl` sur Waza.  
Déclencheur unique : **hook `SessionStop`** → `session-analyst.py --session <path>`.

**Périmètre : toutes les sessions Claude Code sur Waza** — pas seulement VPAI.

| Projet suivi | Slug JSONL |
|-------------|-----------|
| VPAI | `-home-mobuone-VPAI` |
| flash-studio/flash-infra | `-home-mobuone-flash-studio-flash-infra` |
| flash-studio/flash-admin | `-home-mobuone-flash-studio-flash-admin` |
| flash-studio/flash-public | `-home-mobuone-flash-studio-flash-public` |
| projects/session-analyst | `-home-mobuone-projects-session-analyst` |
| projects/storyengine | `-home-mobuone-projects-storyengine` |
| projects/videoref-engine | `-home-mobuone-projects-videoref-engine` |
| ~/.claude (claude-config) | `-home-mobuone--claude` |

Le champ `project_slug` est extrait du chemin `~/.claude/projects/<slug>/` — toutes les projets sont couverts sans configuration spécifique par projet.

Track B ne dépend pas de Track A (Langfuse Cloud). Il est conçu pour fonctionner seul.

---

## Mapping fonctionnel Langfuse → Track B

| Fonctionnalité Langfuse | Équivalent Track B | Service |
|------------------------|-------------------|---------|
| Trace viewer (spans timeline) | Span OTLP → Alloy → Tempo → Grafana Explore | Tempo |
| Logs structurés par session | HTTP push Loki → Grafana Explore | Loki |
| Dashboard métriques tokens/coût | Remote write → VictoriaMetrics → Grafana | VictoriaMetrics |
| Stockage structuré long terme | REST → NocoDB table `claude_sessions` | NocoDB |
| Prompt versioning / git correlation | Gitea webhook → sha court → NocoDB champ | Gitea + n8n |
| Scoring qualité / LLM eval | n8n webhook → LiteLLM juge → score → NocoDB | n8n + LiteLLM |
| Recherche sémantique sessions | Qdrant `sessions_v1` (embedding par résumé) | Qdrant |
| Alerte qualité dégradée | n8n → Telegram si score < 6 | n8n |
| Query on-demand | OpenClaw skill `session-stats` | OpenClaw |
| Dataset d'évaluation | Dossier `/home/mobuone/projects/session-analyst/data/` + NocoDB | Local + NocoDB |

---

## Architecture ETL

```
~/.claude/projects/<slug>/<session-id>.jsonl
          │
          │  SessionStop hook
          ▼
  session-analyst.py --session <path>
          │
          ├─── [1] Parser JSONL ──────────────── ExtractedSession (dataclass)
          │
          ├─── [2] Destinations parallèles (threads) ─────────────────────────┐
          │         │                                                          │
          │    ┌────┴────────────────────────────────────────────────────┐    │
          │    │  NocoDB REST        VictoriaMetrics    Loki HTTP push   │    │
          │    │  (stockage long     (remote write      (logs structurés │    │
          │    │   terme)            métriques)          corrélés)       │    │
          │    └─────────────────────────────────────────────────────────┘    │
          │                                                                    │
          ├─── [3] OTLP export ───────────────── Alloy → Tempo (trace viewer) │
          │                                                                    │
          ├─── [4] Qdrant upsert ─────────────── sessions_v1 (recherche sémantique)
          │                                                                    │
          └─── [5] n8n webhook ───────────────── LiteLLM juge → score → NocoDB + Telegram
```

---

## Structure JSONL — Champs extraits

Basé sur l'analyse des sessions réelles `~/.claude/projects/`:

### Enregistrement `user` (type: "user")
```json
{
  "type": "user",
  "uuid": "<message-id>",
  "sessionId": "<session-id>",
  "timestamp": "2026-04-03T13:08:21.429Z",
  "cwd": "/home/mobuone/VPAI",
  "gitBranch": "main",
  "version": "2.1.91",
  "message": {
    "role": "user",
    "content": [{"type": "text", "text": "..."}]
  }
}
```

### Enregistrement `assistant` (type: "assistant")
```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "usage": {
      "input_tokens": 3,
      "cache_creation_input_tokens": 32976,
      "cache_read_input_tokens": 0,
      "output_tokens": 40,
      "service_tier": "standard"
    },
    "content": [
      {
        "type": "tool_use",
        "id": "toolu_...",
        "name": "Bash",
        "input": {"command": "...", "description": "..."},
        "caller": {"type": "direct"}
      }
    ],
    "model": "claude-sonnet-4-6"
  }
}
```

### Enregistrement `system` (type: "system", subtype: "compact_boundary")
Marqueur de compaction — incrémente `compact_count`.

---

## Dataclass ExtractedSession

```python
@dataclass
class ExtractedSession:
    # Identité
    session_id: str          # UUID extrait du nom de fichier
    project_slug: str        # "VPAI", "flash-studio", etc. (from path)
    cwd: str                 # /home/mobuone/VPAI
    git_branch: str          # main
    cc_version: str          # 2.1.91
    is_subagent: bool        # "subagents" in path

    # Timestamps
    timestamp_start: datetime
    timestamp_end: datetime
    duration_seconds: float

    # Tokens — agrégés sur tous les enregistrements assistant de la session
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int   # cache_creation_input_tokens
    cache_read_tokens: int       # cache_read_input_tokens
    total_tokens: int            # somme des 4
    cost_usd: float              # calculé (voir pricing ci-dessous)

    # Modèle
    model: str                   # claude-sonnet-4-6 (depuis message.model)

    # Outil calls
    tool_calls_count: int
    tool_distribution: dict      # {"Bash": 12, "Read": 8, "Grep": 3, ...}
    bash_calls_total: int
    bash_avoidable: int          # grep + find + cat + ls via Bash (anti-pattern)
    bash_commands: list[str]     # liste brute pour analyse

    # Qualité conversation
    user_turns: int
    assistant_turns: int
    correction_signals: int      # "non", "stop", "wrong", "arrête", etc.
    error_count: int             # tool_result.is_error == True
    max_repeated_tool_streak: int
    compact_count: int           # compact_boundary markers

    # Résumé LLM (généré après extraction)
    summary: str | None          # résumé 2-3 phrases pour Qdrant embedding

    # Git / hooks
    git_sha_hooks: str | None    # injecté via Gitea webhook (n8n) ou git log fallback

    # Scoring (rempli par n8n après push)
    quality_score: float | None  # 1.0–10.0
```

### Calcul coût (pricing claude-sonnet-4-6, avril 2026)
```python
PRICING = {
    "claude-sonnet-4-6": {
        "input": 3.00,           # $/M tokens
        "output": 15.00,
        "cache_creation": 3.75,
        "cache_read": 0.30,
    },
    "claude-opus-4-6": {
        "input": 15.00,
        "output": 75.00,
        "cache_creation": 18.75,
        "cache_read": 1.50,
    },
}

def compute_cost(session: ExtractedSession) -> float:
    p = PRICING.get(session.model, PRICING["claude-sonnet-4-6"])
    return (
        session.input_tokens * p["input"] +
        session.output_tokens * p["output"] +
        session.cache_creation_tokens * p["cache_creation"] +
        session.cache_read_tokens * p["cache_read"]
    ) / 1_000_000
```

### Détection bash_avoidable
```python
AVOIDABLE_PATTERNS = [
    re.compile(r"\bgrep\b"),
    re.compile(r"\bfind\s"),
    re.compile(r"\bcat\s"),
    re.compile(r"\bhead\s"),
    re.compile(r"\btail\s"),
    re.compile(r"\bls\b"),
    re.compile(r"\bsed\s"),
    re.compile(r"\bawk\s"),
]

def count_avoidable(bash_commands: list[str]) -> int:
    count = 0
    for cmd in bash_commands:
        if any(p.search(cmd) for p in AVOIDABLE_PATTERNS):
            count += 1
    return count
```

---

## Destination 1 — NocoDB (stockage long terme)

**Table :** `claude_sessions`  
**API :** `POST /api/v2/tables/{TABLE_ID}/records` (R0 feedback_nocodb_api_v2.md — toujours v2)

### Schéma NocoDB
```
session_id              Text (PK, unique)
project_slug            Text
cwd                     Text
git_branch              Text
cc_version              Text
is_subagent             Checkbox
timestamp_start         DateTime
timestamp_end           DateTime
duration_seconds        Number
model                   Text
input_tokens            Number
output_tokens           Number
cache_creation_tokens   Number
cache_read_tokens       Number
total_tokens            Number
cost_usd                Decimal(8,6)
tool_calls_count        Number
bash_calls_total        Number
bash_avoidable          Number
user_turns              Number
assistant_turns         Number
correction_signals      Number
error_count             Number
max_repeated_tool_streak Number
compact_count           Number
quality_score           Decimal(4,2)   ← rempli par n8n, NULL à l'insert
git_sha_hooks           Text
summary                 LongText
```

### Push NocoDB
```python
def push_nocodb(session: ExtractedSession, nocodb_url: str, token: str, table_id: str):
    payload = {
        "session_id": session.session_id,
        "project_slug": session.project_slug,
        # ... tous les champs
        "quality_score": None,   # rempli par n8n après
    }
    resp = requests.post(
        f"{nocodb_url}/api/v2/tables/{table_id}/records",
        headers={"xc-token": token},
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
```

**Idempotence :** avant insert, vérifier si `session_id` existe déjà.
```python
check = requests.get(
    f"{nocodb_url}/api/v2/tables/{table_id}/records",
    params={"where": f"(session_id,eq,{session.session_id})", "limit": 1},
    headers={"xc-token": token},
)
if check.json().get("pageInfo", {}).get("totalRows", 0) > 0:
    return  # déjà inséré — idempotent
```

---

## Destination 2 — VictoriaMetrics (métriques Grafana)

**Protocole :** Prometheus remote_write vers `http://100.64.0.14:8428/api/v1/write`

### Métriques exportées (format Prometheus)
```
claude_session_tokens_total{project="VPAI", model="claude-sonnet-4-6", type="input"} 12450
claude_session_tokens_total{project="VPAI", model="claude-sonnet-4-6", type="output"} 1823
claude_session_tokens_total{project="VPAI", model="claude-sonnet-4-6", type="cache_creation"} 32976
claude_session_tokens_total{project="VPAI", model="claude-sonnet-4-6", type="cache_read"} 8201
claude_session_cost_usd{project="VPAI", model="claude-sonnet-4-6"} 0.000312
claude_session_bash_avoidable_total{project="VPAI"} 4
claude_session_tool_calls_total{project="VPAI", tool="Bash"} 12
claude_session_tool_calls_total{project="VPAI", tool="Read"} 8
claude_session_duration_seconds{project="VPAI"} 1842.5
claude_session_correction_signals{project="VPAI"} 2
claude_session_compact_count{project="VPAI"} 1
```

### Push remote_write (bibliothèque `prometheus_client`)
```python
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
# OU : push manuel via snappy + protobuf vers /api/v1/write
# Plus simple : utiliser le endpoint d'import Prometheus text de VictoriaMetrics
def push_victoriametrics(session: ExtractedSession, vm_url: str):
    lines = [
        f'claude_session_cost_usd{{project="{session.project_slug}",model="{session.model}"}} {session.cost_usd} {int(session.timestamp_start.timestamp() * 1000)}',
        f'claude_session_tokens_total{{project="{session.project_slug}",type="input"}} {session.input_tokens} {int(session.timestamp_start.timestamp() * 1000)}',
        # ... autres métriques
    ]
    body = "\n".join(lines)
    requests.post(
        f"{vm_url}/api/v1/import/prometheus",
        data=body,
        headers={"Content-Type": "text/plain"},
        timeout=10,
    )
```

**Endpoint VictoriaMetrics :** `/api/v1/import/prometheus` accepte le format Prometheus text directement — pas de snappy/protobuf requis.

### Dashboard Grafana — Panels planifiés
| Panel | Query VictoriaMetrics | Période |
|-------|-----------------------|---------|
| Coût IA / jour | `sum(claude_session_cost_usd) by (project)` | 30j |
| Tokens / jour | `sum(claude_session_tokens_total) by (type)` | 30j |
| Ratio cache_read/input | `rate(cache_read)/rate(input)` | 7j glissants |
| Bash évitables / semaine | `sum(claude_session_bash_avoidable_total)` | 7j |
| Sessions par projet | `count(claude_session_duration_seconds) by (project)` | 30j |
| Durée moyenne session | `avg(claude_session_duration_seconds) by (project)` | 30j |
| Score qualité tendance | `avg(claude_quality_score) by (project)` | 30j |

---

## Destination 3 — Loki (logs structurés)

**Push :** HTTP POST `http://100.64.0.14:3100/loki/api/v1/push`  
**Objectif :** timeline complète de la session — corrélée avec Tempo via `trace_id`

### Format push Loki
```python
def push_loki(session: ExtractedSession, trace_id: str, loki_url: str):
    payload = {
        "streams": [
            {
                "stream": {
                    "job": "claude-sessions",
                    "project": session.project_slug,
                    "model": session.model,
                    "session_id": session.session_id,
                    "trace_id": trace_id,           # corrélation Tempo
                },
                "values": [
                    # Une entrée par outil appelé
                    [
                        str(int(ts.timestamp() * 1e9)),  # nanoseconds
                        json.dumps({
                            "tool": tool_name,
                            "duration_ms": duration_ms,
                            "is_error": is_error,
                            "bash_avoidable": is_avoidable,
                            "session_id": session.session_id,
                            "trace_id": trace_id,
                        })
                    ]
                    for ts, tool_name, duration_ms, is_error, is_avoidable
                    in session.tool_timeline
                ]
            }
        ]
    }
    requests.post(f"{loki_url}/loki/api/v1/push", json=payload, timeout=10)
```

### Queries Loki utiles (Grafana Explore)
```logql
# Toutes les sessions avec erreurs sur VPAI
{project="VPAI"} | json | error_count > 0

# Sessions avec bash évitables cette semaine
{job="claude-sessions"} | json | bash_avoidable="true"

# Timeline d'une session spécifique
{session_id="c15bf40b-..."} | json

# Corrélation vers trace Tempo
{trace_id="abc123"}
```

---

## Destination 4 — Tempo (trace distribuée)

**Protocole :** OTLP/gRPC → Alloy (port 4317, déjà actif sur Sese-AI) → Tempo  
**Objectif :** Visualiser la séquence des tool calls avec durées — l'équivalent du trace viewer Langfuse

### Structure des spans
```
Trace: session-<session_id>   (durée = duration_seconds)
  └── Span: tool:<tool_name>  (1 span par tool call, avec durée estimée)
        Attributes:
          session.id = <uuid>
          session.project = VPAI
          tool.name = Bash
          tool.input_size = 142
          tool.is_error = false
          tool.bash_avoidable = true
          model = claude-sonnet-4-6
```

### Export OTLP Python
```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def push_tempo(session: ExtractedSession, alloy_grpc_endpoint: str):
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=alloy_grpc_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    tracer = provider.get_tracer("claude-session-analyst")

    with tracer.start_as_current_span(
        f"session-{session.session_id[:8]}",
        start_time=int(session.timestamp_start.timestamp() * 1e9),
    ) as root_span:
        root_span.set_attribute("session.id", session.session_id)
        root_span.set_attribute("session.project", session.project_slug)
        root_span.set_attribute("session.model", session.model)
        root_span.set_attribute("session.cost_usd", session.cost_usd)
        root_span.set_attribute("session.total_tokens", session.total_tokens)

        for tool_event in session.tool_timeline:
            with tracer.start_as_current_span(
                f"tool:{tool_event.name}",
                start_time=int(tool_event.timestamp.timestamp() * 1e9),
            ) as span:
                span.set_attribute("tool.name", tool_event.name)
                span.set_attribute("tool.is_error", tool_event.is_error)
                span.set_attribute("tool.bash_avoidable", tool_event.is_avoidable)
```

**Note :** La durée individuelle par tool call n'est pas dans le JSONL (pas de timestamp de fin par outil). Approximation : durée totale / nombre de tool calls, ajustée par ordre chronologique des timestamps user/assistant.

---

## Destination 5 — Qdrant (recherche sémantique)

**Collection :** `sessions_v1`  
**Modèle embedding :** appel LiteLLM `text-embedding-3-small` (cheap, ~$0.0001/session)  
**Vecteur :** 1536 dimensions (OpenAI compatible via LiteLLM)

### Schéma point Qdrant
```python
{
    "id": "<uuid5 from session_id>",
    "vector": [...],   # embedding du champ `summary`
    "payload": {
        "session_id": session.session_id,
        "project_slug": session.project_slug,
        "timestamp_start": session.timestamp_start.isoformat(),
        "model": session.model,
        "cost_usd": session.cost_usd,
        "total_tokens": session.total_tokens,
        "bash_avoidable": session.bash_avoidable,
        "correction_signals": session.correction_signals,
        "quality_score": None,     # mis à jour par n8n
        "summary": session.summary,
    }
}
```

### Génération du résumé (input pour embedding)
Avant d'embedder, générer un résumé textuel de la session :
```python
def generate_summary(session: ExtractedSession) -> str:
    top_tools = sorted(session.tool_distribution.items(), key=lambda x: -x[1])[:3]
    tools_str = ", ".join(f"{k}×{v}" for k, v in top_tools)
    return (
        f"Session {session.project_slug} ({session.model}), "
        f"durée {int(session.duration_seconds/60)}min, "
        f"{session.total_tokens} tokens, "
        f"outils: {tools_str}, "
        f"erreurs: {session.error_count}, "
        f"corrections: {session.correction_signals}, "
        f"bash évitables: {session.bash_avoidable}."
    )
```

### Utilisation (R0 SessionStart hook)
```bash
$MEM --query "sessions avec SSH polling loops" --repo VPAI --doc-kind session
# → retourne sessions similaires passées pour injection contexte
```

### Push Qdrant
```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
import uuid

def push_qdrant(session: ExtractedSession, litellm_url: str, qdrant_url: str):
    summary = generate_summary(session)
    # Embedding via LiteLLM
    resp = requests.post(
        f"{litellm_url}/embeddings",
        json={"model": "text-embedding-3-small", "input": summary},
        headers={"Authorization": f"Bearer {litellm_key}"},
    )
    vector = resp.json()["data"][0]["embedding"]

    client = QdrantClient(url=qdrant_url)
    client.upsert(
        collection_name="sessions_v1",
        points=[PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, session.session_id)),
            vector=vector,
            payload={**session_payload(session), "summary": summary},
        )]
    )
```

---

## Destination 6 — n8n (scoring qualité LLM)

**Webhook :** `POST https://mayi.ewutelo.cloud/webhook/session-quality-eval`  
**Workflow :** `session-quality-eval` (à créer via scripts/n8n-workflows/)

### Payload webhook
```json
{
  "session_id": "c15bf40b-...",
  "project_slug": "VPAI",
  "model": "claude-sonnet-4-6",
  "summary": "Session VPAI (claude-sonnet-4-6), durée 31min...",
  "tool_calls_count": 47,
  "bash_avoidable": 4,
  "correction_signals": 2,
  "error_count": 1,
  "max_repeated_tool_streak": 3,
  "compact_count": 0,
  "cost_usd": 0.000312,
  "duration_seconds": 1842
}
```

### Workflow n8n `session-quality-eval`
```
Webhook (POST) → LiteLLM Chat (juge) → IF score < 6 → Telegram alerte
                                     → NocoDB PATCH quality_score
                                     → Qdrant update payload.quality_score
```

### Prompt juge LiteLLM (deepseek-v3 ou qwen3-coder, ~$0.001/session)
```
Tu es un juge expert en efficacité Claude Code.

Session : {summary}
Métriques :
- tool_calls: {tool_calls_count}, bash_avoidable: {bash_avoidable}
- correction_signals: {correction_signals}, error_count: {error_count}
- repeated_tool_streak: {max_repeated_tool_streak}, compact_count: {compact_count}

Critères de scoring (1-10) :
- Complétude tâche : a-t-on atteint un résultat ? (+3 pts)
- Efficacité outils : Bash utilisé à la place de Grep/Read/Glob ? (-1 pt par bash_avoidable)
- Loops : repeated_streak > 3 = loop détecté (-2 pts)
- Clarté directives : correction_signals > 2 = prompts ambigus (-1 pt)
- Gestion contexte : compact_count > 2 = fenêtre dépassée (-1 pt)

Réponds UNIQUEMENT avec un JSON : {"score": 7, "reason": "...une phrase..."}
```

### NocoDB PATCH (R0 — feedback_nocodb_patch_pattern.md : Id dans body)
```json
{ "Id": "<nocodb_row_id>", "quality_score": 7.0 }
```

**Note :** le PATCH NocoDB nécessite l'Id interne de la row, pas `session_id`. Le workflow n8n doit d'abord faire un GET pour récupérer l'Id, puis PATCH.

---

## Destination 7 — git_sha_hooks (corrélation hooks↔sessions)

**Objectif :** savoir quelle version de CLAUDE.md / hooks était active lors d'une session  
**Mécanisme :** `git log` local sur le repo `claude-config` (~/.claude) — **pas de webhook Gitea requis**

### Repo `claude-config` (Gitea privé)
- Périmètre : `~/.claude/CLAUDE.md`, `~/.claude/hooks/`, `~/.claude/skills/` (custom), `settings.json`, `mcp.json`, workers config
- Distant : `https://git.ewutelo.cloud/mobuone/claude-config` (privé, VPN-only)
- **Distinct** du code VPAI (GitHub public) — CLAUDE.md exclu de GitHub via `.gitignore`
- `session-analyst` lit ce repo en **lecture seule** — jamais d'écriture

### Champ `git_sha_hooks` dans session-analyst
```python
import subprocess
from pathlib import Path

CLAUDE_CONFIG_DIR = Path.home() / ".claude"   # repo git claude-config sur Waza

def get_current_hooks_sha() -> str | None:
    """SHA court de la dernière révision de CLAUDE.md/hooks au moment de la session."""
    try:
        result = subprocess.run(
            ["git", "-C", str(CLAUDE_CONFIG_DIR), "log", "--format=%h", "-1"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or None
    except Exception:
        return None
```

### Pourquoi pas de webhook Gitea ?
- Les hooks/CLAUDE.md sont modifiés sur Waza → committé localement → pusher sur Gitea
- Au `SessionStop`, `git log` retourne le sha local — identical au sha Gitea si le push a eu lieu
- Corrélation suffisante : sha local ≡ version active des hooks pendant la session
- Webhook Gitea n'apporte rien de plus (pas de delta entre local et remote au moment de la session)

---

## OpenClaw — Skill `session-stats`

**Commande Telegram :** `/session-stats` ou topic dédié  
**Pattern :** identique à `content-director` (skill OpenClaw existant)

### Queries supportées
```
"qualité sessions cette semaine"
  → NocoDB: avg(quality_score) WHERE timestamp_start > now()-7j, groupé par project

"coût IA aujourd'hui"
  → VictoriaMetrics: sum(claude_session_cost_usd)[1d]

"sessions dégradées ce mois"
  → NocoDB: count(*) WHERE quality_score < 6 AND timestamp_start > now()-30j

"bash évitables ce mois par projet"
  → NocoDB: sum(bash_avoidable) GROUP BY project_slug WHERE timestamp_start > now()-30j

"sessions longues > 1h"
  → NocoDB: list WHERE duration_seconds > 3600 ORDER BY cost_usd DESC LIMIT 5
```

---

## session-analyst.py enhanced — Architecture module

```
/home/mobuone/projects/session-analyst/
├── src/
│   ├── parser.py           # iter_jsonl + extraction ExtractedSession
│   ├── cost.py             # compute_cost() + PRICING table
│   ├── destinations/
│   │   ├── nocodb.py       # push_nocodb()
│   │   ├── victoriametrics.py  # push_victoriametrics()
│   │   ├── loki.py         # push_loki()
│   │   ├── tempo.py        # push_tempo()
│   │   ├── qdrant.py       # push_qdrant()
│   │   └── n8n.py          # push_n8n_webhook()
│   └── session_analyst.py  # main() + CLI --session / --batch
├── config/
│   └── destinations.env    # NOCODB_URL, NOCODB_TOKEN, VM_URL, LOKI_URL, etc.
└── requirements.txt
    # requests, opentelemetry-sdk, opentelemetry-exporter-otlp,
    # qdrant-client, prometheus-client
```

### CLI
```bash
# Appelé par SessionStop hook
python3 session-analyst.py --session ~/.claude/projects/-home-mobuone-VPAI/<id>.jsonl

# Rattrapage batch (sessions non encore indexées)
python3 session-analyst.py --batch ~/.claude/projects/ --since 2026-04-01 --dry-run
```

### SessionStop hook (appel)
```bash
#!/usr/bin/env bash
# ~/.claude/hooks/session-stop.sh
set -euo pipefail
SESSION_FILE="$CLAUDE_PROJECTS_DIR/$CLAUDE_PROJECT_SLUG/$CLAUDE_SESSION_ID.jsonl"
if [[ -f "$SESSION_FILE" ]]; then
    /home/mobuone/projects/session-analyst/.venv/bin/python3 \
        /home/mobuone/projects/session-analyst/src/session_analyst.py \
        --session "$SESSION_FILE" &    # background — ne bloque pas la fermeture
fi
```

---

## Nouveaux services à déployer sur Sese-AI

### Tempo (ajout au monitoring stack)
```yaml
# roles/monitoring/templates/docker-compose.yml.j2 (ajout)
tempo:
  image: "{{ tempo_image }}"    # grafana/tempo:2.7.2 — pinné dans versions.yml
  restart: unless-stopped
  logging:
    driver: json-file
    options: { max-size: "10m", max-file: "3" }
  command: ["-config.file=/etc/tempo.yaml"]
  volumes:
    - ./tempo.yaml:/etc/tempo.yaml:ro
    - tempo_data:/var/tempo
  networks:
    - monitoring
  healthcheck:
    test: ["CMD", "wget", "-q", "--spider", "http://localhost:3200/ready"]
    interval: 10s
    timeout: 5s
    retries: 5
```

### Config Alloy — récepteur OTLP (ajout)
```alloy
# roles/monitoring/templates/alloy-config.alloy.j2 (ajout)
otelcol.receiver.otlp "default" {
  grpc { endpoint = "0.0.0.0:4317" }
  output {
    traces = [otelcol.exporter.otlphttp.tempo.input]
  }
}

otelcol.exporter.otlphttp "tempo" {
  client {
    endpoint = "http://tempo:4318"
  }
}
```

### Grafana datasources (ajout)
```yaml
- name: Tempo
  type: tempo
  url: http://tempo:3200
  jsonData:
    lokiSearch:
      datasourceUid: loki    # corrélation Loki ↔ Tempo via trace_id
```

---

## Dépendances Track B

| Dépendance | Statut | Action |
|-----------|--------|--------|
| VictoriaMetrics sur Sese-AI | Déjà déployé | Vérifier endpoint `/api/v1/import/prometheus` actif |
| Loki sur Sese-AI | Déjà déployé | Vérifier push HTTP port 3100 |
| Alloy sur Sese-AI | Déjà déployé | Ajouter config OTLP receiver + Tempo exporter |
| Tempo | **Nouveau** | Ajouter dans docker-compose monitoring |
| NocoDB sur Sese-AI | Déjà déployé | Créer table `claude_sessions` + récupérer TABLE_ID |
| Qdrant sur Sese-AI | Déjà déployé | Créer collection `sessions_v1` (dim 1536) |
| n8n sur Sese-AI | Déjà déployé | Créer workflow `session-quality-eval` |
| LiteLLM sur Sese-AI | Déjà déployé | Vérifier accès `text-embedding-3-small` + juge |
| session-analyst enhanced | **À écrire** | Refactoring + destinations/ + scrubber sécurité |
| SessionStop hook | ULTIMATE-CONFIG Couche 5 | Dépendance critique — doit être déployé avant |
| Repo `claude-config` sur Gitea | **À créer** | Token via UI `git.ewutelo.cloud` ou CLI Seko-VPN |

### Accès Gitea depuis Waza

`https://git.ewutelo.cloud` → HTTPS accessible depuis Waza (confirmé HTTP 200).  
SSH ports 22/804 fermés depuis Waza → git push via HTTPS uniquement.  
Token : créer via UI Gitea Settings > Applications, **ou** `docker exec gitea gitea admin user generate-access-token` depuis Seko-VPN.

### Sécurité — scrubber obligatoire (Plan 10-B1)

Voir `.planning/notes/security-jsonl-credentials-leak.md`.  
`scrub_secrets()` appliqué sur tout contenu textuel avant push Loki/NocoDB summary/Qdrant/n8n/Langfuse.  
Sessions avec credentials détectés → métriques seules (VictoriaMetrics), pas de summary ingéré.

---

## Plans d'implémentation Track B (3 plans)

### Plan 10-B1 — Tempo + Alloy + session-analyst enhanced
- Ajouter Tempo au docker-compose monitoring Sese-AI
- Config Alloy: OTLP receiver + exporter Tempo
- Refactoring session-analyst: parser.py + destinations/
- Implémenter destinations: NocoDB, VictoriaMetrics, Loki, Tempo
- Hook SessionStop → appel session-analyst

### Plan 10-B2 — Qdrant sessions_v1 + embeddings
- Créer collection `sessions_v1` sur Qdrant
- Implémenter destination qdrant.py + generate_summary()
- Batch import sessions historiques (~2,240 sessions)
- Vérifier recherche sémantique R0 SessionStart

### Plan 10-B3 — n8n juge qualité + Grafana + OpenClaw
- Créer workflow n8n `session-quality-eval`
- Dashboard Grafana (7 panels)
- Gitea webhook → `hook_deployments`
- OpenClaw skill `session-stats`
- Alertes Telegram score < 6

---

*Spec écrite le 2026-04-12 — basée sur analyse JSONL réels `~/.claude/projects/` et session-analyst existant*  
*Langfuse: hors scope Track B — toutes les fonctions couvertes sans dépendance externe*
