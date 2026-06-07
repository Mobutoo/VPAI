# Phase 10: AI Ops — Context

**Gathered:** 2026-04-12
**Status:** Ready for planning
**Source:** Exploration session + Advisor ULTRATHINK (3 passes) + inventaire stack complète

<domain>
## Phase Boundary

Implémenter un cycle d'amélioration continue des sessions Claude Code en exploitant exclusivement la stack existante — zéro nouveau serveur obligatoire.

**Deux tracks parallèles :**
- **Track A** (semaine 1) : Langfuse Cloud free tier branché sur le hook SessionStop → trace UI immédiate
- **Track B** (semaines 2-4) : stack maison (NocoDB + VictoriaMetrics + Tempo + Loki + Qdrant + n8n + LiteLLM + Gitea + OpenClaw) → observabilité complète, stockage long terme, scoring qualité automatique

**Track C** (optionnel, déclenché après 4 semaines si besoin confirmé) : Langfuse self-hosted sur CX32 ou Oracle VM — uniquement si rétention 30j ou confidentialité deviennent bloquants.

Ce que cette phase NE fait PAS :
- Déployer Arize Phoenix (hors scope, valeur marginale)
- Modifier l'architecture Sese-AI au-delà de l'ajout de Tempo au monitoring stack
- Implémenter les 6 couches ULTIMATE-CONFIG (projet parallèle en cours — cette phase dépend de la Couche 5)

</domain>

<decisions>
## Implementation Decisions

### Architecture ETL — principe fondamental
- **Locked** : Claude Code = Anthropic OAuth (Max). Zéro interception des appels possible.
- **Locked** : Déclencheur unique = hook `SessionStop` (ULTIMATE-CONFIG Couche 5, `session-memory-writer.sh`)
- **Locked** : `session-analyst` (enhanced) est le seul parser JSONL → pousse vers toutes les destinations
- **Locked** : PAS d'inotify, PAS de cron, PAS de watcher fichier

### Track A — Langfuse Cloud
- **Locked** : Free tier (50k traces/mois, 1 dev = ~600/mois — bien dans les limites)
- **Locked** : Limite rétention 30j compensée par NocoDB (Track B)
- **Locked** : Langfuse Python SDK — version à vérifier en live via `pip index versions langfuse`
- **Claude's Discretion** : Si données trop sensibles → passer directement à Track C

### Track B — Stack maison

#### NocoDB (table `claude_sessions`)
- **Locked** : Stockage structuré long terme. Champs : session_id, project_slug, timestamp, total_tokens, input_tokens, output_tokens, cache_tokens, cost_usd, tool_calls_count, bash_calls_total, bash_avoidable, model, duration_seconds, quality_score, git_sha_hooks
- **Locked** : Remplace la limite de rétention 30j Langfuse Cloud

#### VictoriaMetrics + Grafana
- **Locked** : Push métriques agrégées par session (remote write). Dashboard : tokens/jour, coût/jour, bash_évitables/semaine, qualité score tendance 30j glissants

#### Grafana Tempo (nouveau service, Sese-AI monitoring stack)
- **Locked** : Ajouté dans `docker-compose-infra.yml` Sese-AI (~300MB RAM, stockage filesystem local)
- **Locked** : `session-analyst` envoie traces OTLP → Alloy (receiver OTLP port 4317, déjà en place) → Tempo
- **Locked** : Spans : 1 trace par session, 1 span par tool call (nom outil, durée, input/output size)
- **Locked** : Corrélation Loki↔Tempo via `trace_id` injecté dans les logs

#### Loki
- **Locked** : Logs structurés corrélés aux traces Tempo. Push HTTP direct depuis `session-analyst`.

#### Qdrant (collection `sessions_v1`)
- **Locked** : Embedding du résumé session via LiteLLM (modèle embedding cheap). Collection séparée de `memory_v1`.
- **Locked** : Complément NocoDB — Qdrant pour recherche sémantique ("sessions avec SSH polling loops"), NocoDB pour requêtes SQL structurées
- **Locked** : Hook R0 SessionStart peut interroger `sessions_v1` en plus de `memory_v1` (contexte sessions similaires passées)

#### n8n — workflow `session-quality-eval`
- **Locked** : Reçoit résumé session depuis `session-analyst` (webhook)
- **Locked** : Appelle LiteLLM avec deepseek-v3 ou qwen3-coder comme juge (coût ~$0.001/session)
- **Locked** : Prompt juge : score 1-10 sur complétion tâche, outils inutiles, loops détectés, clarté
- **Locked** : Écrit score dans NocoDB, alerte Telegram si score < 6

#### Gitea (Seko-VPN) — corrélation git↔qualité
- **Locked** : Webhook Gitea sur push touchant CLAUDE.md ou `~/.claude/hooks/`
- **Locked** : Payload → n8n → extrait sha court + liste fichiers modifiés → écrit dans NocoDB + Langfuse metadata
- **Locked** : Event-driven, remplace le polling `git log` dans `session-analyst`
- **Claude's Discretion** : Si CLAUDE.md n'est pas dans Gitea → fallback `git log` dans session-analyst

#### OpenClaw — skill `session-stats`
- **Locked** : Skill Telegram on-demand : "qualité sessions cette semaine", "coût IA aujourd'hui", "sessions dégradées ce mois"
- **Locked** : Pattern identique à `content-director` — topic Telegram dédié ou commande slash
- **Claude's Discretion** : Choix du topic Telegram et des commandes exactes

### Track C — Langfuse self-hosted (optionnel)
- **Locked** : Déclenché uniquement si : rétention 30j bloquante ET stack maison insuffisante, OU données trop sensibles pour Cloud
- **Locked** : Décision après minimum 4 semaines de données réelles Track A+B
- **Locked** : Serveur cible si déclenché : Hetzner CX32 (4 vCPU / 8GB, ~10€/mois) ou Oracle VM (4 vCPU / 24GB, gratuit si disponible)

### Conventions VPAI obligatoires
- Images Docker pinnées dans `versions.yml` (jamais `:latest`) — Tempo inclus
- FQCN Ansible, `changed_when`/`failed_when`, `set -euo pipefail`
- Log rotation json-file max-size 10m max-file 3 sur Tempo
- Healthcheck sur le service Tempo

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Conventions
- `CLAUDE.md` — Conventions Ansible, Docker, Caddy VPN, conventions strictes
- `TECHNICAL-SPEC.md` — Architecture technique, réseaux Docker, limites ressources Sese-AI
- `docs/guides/GUIDE-CADDY-VPN-ONLY.md` — 4 pièges critiques Caddy VPN
- `docs/standards/ANSIBLE-ROLE-CHECKLIST.md` — Checklist création rôle

### Monitoring stack existante (à étendre avec Tempo)
- `roles/monitoring/` — Rôle monitoring Sese-AI (Grafana, VictoriaMetrics, Loki, Alloy, cAdvisor)
- `roles/monitoring/templates/docker-compose.yml.j2` — Compose monitoring (ajouter Tempo ici)
- `roles/monitoring/templates/alloy-config.alloy.j2` — Config Alloy (ajouter receiver OTLP + exporter Tempo)

### Inventaire & Variables
- `inventory/hosts.yml` — Structure inventaire (Sese-AI, Seko-VPN, Waza)
- `inventory/group_vars/all/versions.yml` — Images Docker pinnées (ajouter Tempo)

### Services réutilisés
- `roles/n8n/` — Pattern workflow n8n (référence pour session-quality-eval)
- `roles/openclaw/` — Pattern skill OpenClaw (référence pour session-stats)
- `/opt/workstation/ai-memory-worker/` — Worker Qdrant sur Waza (modèle pour sessions_v1)
- `/home/mobuone/projects/session-analyst/` — Scripts audit sessions JSONL (à enrichir)

### Requirements
- `.planning/REQUIREMENTS.md` — Section v2026.4 AI Ops (AIOPS-01 à AIOPS-12)

</canonical_refs>

<specifics>
## Specific Ideas

### session-analyst enhanced — sorties par destination
```python
# SessionStop hook → session-analyst.py --session <path>
# Sorties parallèles :
# 1. langfuse_client.trace(...)           → Langfuse Cloud (Track A)
# 2. nocodb_post("/claude_sessions", ...) → NocoDB REST API
# 3. vm_push(metrics)                     → VictoriaMetrics remote_write
# 4. otlp_exporter.export(spans)          → Alloy → Tempo
# 5. loki_push(logs)                      → Loki HTTP push
# 6. qdrant_client.upsert("sessions_v1")  → Qdrant embedding
# 7. n8n_webhook(summary)                 → LiteLLM juge qualité
```

### Champs trace Langfuse / NocoDB
- `session_id`, `project_slug`, `timestamp_start`, `timestamp_end`
- `total_tokens`, `input_tokens`, `output_tokens`, `cache_creation_tokens`, `cache_read_tokens`
- `cost_usd` (calculé depuis model pricing)
- `tool_calls_count`, `bash_calls_total`, `bash_avoidable` (grep/find/cat évitables)
- `model` (claude-sonnet-4-6, etc.)
- `duration_seconds`
- `quality_score` (rempli par n8n/LiteLLM après coup)
- `git_sha_hooks` (via Gitea webhook ou git log fallback)

### Tempo dans docker-compose-infra.yml
```yaml
tempo:
  image: "{{ tempo_image }}"    # grafana/tempo:x.y.z — pinné dans versions.yml
  restart: unless-stopped
  logging:
    driver: json-file
    options: { max-size: "10m", max-file: "3" }
  command: ["-config.file=/etc/tempo.yaml"]
  volumes:
    - ./tempo.yaml:/etc/tempo.yaml:ro
    - tempo_data:/tmp/tempo
  networks:
    - monitoring
  healthcheck:
    test: ["CMD", "wget", "-q", "--spider", "http://localhost:3200/ready"]
    interval: 10s
    timeout: 5s
    retries: 5
```

### Gitea webhook payload → n8n
```json
{
  "ref": "refs/heads/main",
  "commits": [{"id": "abc1234", "modified": ["CLAUDE.md", ".claude/hooks/bash-lint.js"]}]
}
```
n8n extrait `commits[0].id` (sha court) + `commits[0].modified` (liste fichiers).

</specifics>

<deferred>
## Deferred Ideas

- Arize Phoenix — hors scope Phase 10, reporter en Phase 11 si besoin RAG eval confirmé
- Langfuse self-hosted (Track C) — décision après 4 semaines données réelles
- LiteLLM → Langfuse callback natif — pertinent pour n8n/OpenClaw, pas Claude Code. Phase ultérieure.
- Multi-platform publishing, ElevenLabs voiceover — v2 Content Factory

</deferred>

---

*Phase: 10-ai-ops*
*Context gathered: 2026-04-12 — architecture finale après 3 passes Advisor ULTRATHINK + inventaire stack complète*
*Stack exploitée: Langfuse Cloud + NocoDB + VictoriaMetrics + Tempo + Loki + Qdrant + n8n + LiteLLM + Gitea + OpenClaw*
