# Runbook — AI Memory Operations

Date: 2026-04-10
Statut: v0.3 validee
Portee: exploitation du pipeline memoire Waza -> Qdrant -> n8n

## 1. Objectif

Ce runbook couvre l'exploitation du lot memoire actuellement deploye:

- worker local sur **Waza**
- embeddings locaux via `google/embeddinggemma-300m`
- stockage dans `memory_v1` sur Qdrant
- rapports JSON pushes vers `n8n`
- supervision par `memory-run-report-ingest` et `memory-healthcheck`

Etat reel:

- `v0.2` est deployee et operable
- `v0.3` a elargi la couverture retrieval aux 3 repos prioritaires
- les seeds cibles sont valides avant indexation plus large
- resultats benchmark:
  - `VPAI`: 7/8 hits top-3, `miss_ratio=0.125`
  - `flash-studio`: 7/8 hits top-3, `miss_ratio=0.125`
  - `story-engine`: 8/8 hits top-3, `miss_ratio=0.0`

## 2. Composants

### Waza

- service: `llamaindex-memory-worker.service`
- timer: `llamaindex-memory-worker.timer`
- wrapper: `/opt/workstation/ai-memory-worker/run-and-report.sh`
- config: `/opt/workstation/configs/ai-memory-worker/config.yml`
- env: `/opt/workstation/configs/ai-memory-worker/memory-worker.env`
- secret webhook: `/opt/workstation/configs/ai-memory-worker/memory-webhook-secret`

### Sese-AI

- Qdrant collection: `memory_v1`
- n8n workflow: `memory-run-report-ingest`
- n8n workflow: `memory-healthcheck`
- table Postgres: `memory_runs`

## 3. Deploiement

### 3.1 Stack prod / n8n

```bash
ansible-playbook playbooks/site.yml -e "target_env=prod" --tags "docker-stack,n8n" --diff
```

Puis reimporter/activer dans l'UI n8n:

- `scripts/n8n-workflows/memory-run-report-ingest.json`
- `scripts/n8n-workflows/memory-healthcheck.json`

### 3.2 Worker Waza

```bash
make deploy-memory-worker
```

Ou:

```bash
ansible-playbook playbooks/workstation.yml --tags llamaindex-memory-worker --diff
```

## 4. Verification post-deploiement

### 4.1 Waza

```bash
systemctl is-enabled llamaindex-memory-worker.timer
systemctl is-active llamaindex-memory-worker.timer
systemctl status llamaindex-memory-worker.service --no-pager
```

Verifier aussi:

- log worker: `/opt/workstation/data/ai-memory-worker/logs/memory-worker.log`
- spool local: `/opt/workstation/data/ai-memory-worker/spool/`
- cache HF: `/opt/workstation/data/ai-memory-worker/hf-cache/`

### 4.2 n8n

Verifier:

- `memory-run-report-ingest` actif
- `memory-healthcheck` actif
- variable `MEMORY_WEBHOOK_SECRET` chargee
- variables `MEMORY_HEALTHCHECK_MAX_AGE_HOURS` et `MEMORY_HEALTHCHECK_MAX_SPOOL` chargees

### 4.3 Postgres / n8n

Verifier qu'un rapport remonte dans `memory_runs`.

Exemple:

```sql
SELECT run_id, host_origin, mode, attempted_files, indexed_files, exit_code, received_at
FROM memory_runs
ORDER BY received_at DESC
LIMIT 10;
```

## 5. Commandes d'exploitation

### 5.1 Preflight

Depuis Waza:

```bash
/opt/workstation/ai-memory-worker/run-and-report.sh --preflight-only
```

### 5.2 Dry-run incremental

```bash
/opt/workstation/ai-memory-worker/run-and-report.sh --mode incremental --dry-run
```

### 5.3 Backfill manuel d'un repo

```bash
scripts/memory-backfill.sh --repo VPAI
scripts/memory-backfill.sh --repo flash-studio --max-files 100
scripts/memory-backfill.sh --repo story-engine --path /home/mobuone/projects/saas/story-engine/docs --dry-run
```

Important:

- `--path` doit etre un **vrai chemin filesystem**
- le chemin doit etre sous un des `memory_worker_repo_roots` configures
- sur un backfill cible avec `--path`, le worker **n'applique pas le GC**
  global; cela evite de supprimer des documents hors scope pendant un seed

### 5.3.1 Seed scope recommande pour v0.3

Pour accelerer la valeur utile sur le Pi avant un backfill large, utiliser en priorite:

#### VPAI

```bash
scripts/memory-backfill.sh --repo VPAI \
  --path /home/mobuone/VPAI/playbooks/site.yml \
  --path /home/mobuone/VPAI/playbooks/workstation.yml \
  --path /home/mobuone/VPAI/inventory/hosts.yml \
  --path /home/mobuone/VPAI/roles/llamaindex-memory-worker/defaults/main.yml \
  --path /home/mobuone/VPAI/roles/llamaindex-memory-worker/tasks/main.yml \
  --path /home/mobuone/VPAI/scripts/n8n-workflows/memory-run-report-ingest.json \
  --path /home/mobuone/VPAI/scripts/n8n-workflows/memory-healthcheck.json \
  --path /home/mobuone/VPAI/docs/runbooks/AI-MEMORY-OPERATIONS.md \
  --path /home/mobuone/VPAI/Makefile
```

#### flash-studio

```bash
scripts/memory-backfill.sh --repo flash-studio \
  --path /home/mobuone/flash-studio/docs/QUICK_REFERENCE.md \
  --path /home/mobuone/flash-studio/docs/GUIDE_INITIALISATION.md \
  --path /home/mobuone/flash-studio/flash-infra/README.md \
  --path /home/mobuone/flash-studio/flash-infra/ARCHITECTURE.md \
  --path /home/mobuone/flash-studio/flash-infra/ansible/playbooks/site.yml \
  --path /home/mobuone/flash-studio/flash-infra/ansible/playbooks/rebuild-work.yml \
  --path /home/mobuone/flash-studio/flash-infra/scripts/flash-daemon.sh \
  --path /home/mobuone/flash-studio/flash-infra/scripts/flash-ctl.sh
```

#### story-engine

```bash
scripts/memory-backfill.sh --repo story-engine \
  --path /home/mobuone/projects/saas/story-engine/CLAUDE.md \
  --path /home/mobuone/projects/saas/story-engine/apps/api/src/story_engine/main.py \
  --path /home/mobuone/projects/saas/story-engine/apps/collab/src/server.ts \
  --path /home/mobuone/projects/saas/story-engine/apps/collab/src/health.ts \
  --path /home/mobuone/projects/saas/story-engine/apps/collab/src/extensions/database.ts \
  --path /home/mobuone/projects/saas/story-engine/packages/editor/src/extensions.ts \
  --path /home/mobuone/projects/saas/story-engine/infra/docker-compose.yml \
  --path /home/mobuone/projects/saas/story-engine/docs/specs/2026-04-01-gaps-resolution.md
```

Ce seed v0.3 couvre les zones les plus utiles pour:

- architecture
- playbooks / infra
- workflows
- points d'entree applicatifs
- documentation structurante

### 5.4 Recherche manuelle

```bash
/opt/workstation/ai-memory-worker/.venv/bin/python \
  /opt/workstation/ai-memory-worker/search_memory.py \
  --config /opt/workstation/configs/ai-memory-worker/config.yml \
  --query "qdrant healthcheck"
```

### 5.5 Benchmark retrieval

```bash
/opt/workstation/ai-memory-worker/.venv/bin/python \
  /opt/workstation/ai-memory-worker/benchmark_memory.py \
  --config /opt/workstation/configs/ai-memory-worker/config.yml \
  --repo VPAI
```

Critere actuel:

- si `miss_ratio > 0.30`, le modele n'est plus considere acceptable

## 6. Lecture des signaux

### 6.1 Etat nominal

- `memory_runs.exit_code = 0`
- `errors = []`
- `spool_size = 0`
- `memory-healthcheck` retourne `healthy`
- dernier run `incremental` recent depuis `host_origin = waza`

### 6.2 Signaux de derive

- plus aucun `incremental` recent dans `memory_runs`
- `spool_size` qui monte
- `qdrant_reachable = false`
- `exit_code != 0`
- `memory-healthcheck` envoie une alerte Telegram

## 7. Incidents frequents

### 7.1 Qdrant inaccessible

Symptomes:

- `Connection refused`
- `qdrant_reachable = false`
- lots dans le spool

Checks:

- VPN/Tailscale
- endpoint `https://qd.<domain>:443`
- cle API Qdrant

### 7.2 Charge Waza trop haute

Symptome:

- `loadavg too high`

Action:

- attendre une fenetre plus calme
- eviter les runs memoire pendant les grosses charges ComfyUI / render / jobs rails

### 7.3 Hugging Face / modele

Symptomes:

- echec au bootstrap du modele
- probleme d'acces au repo gated

Checks:

- `HF_TOKEN`
- licence Gemma acceptee
- cache local present

Voir aussi:

- `docs/runbooks/HUGGINGFACE-TOKEN-BOOTSTRAP.md`

## 8. Scope lot 1

Repos cibles actuels:

- `VPAI`
- `flash-studio`
- `story-engine`

Le lot 1 ne couvre pas encore:

- docs de travail locaux sur Sese-AI
- ecriture directe multi-agents
- migration legacy Qdrant
- memoire conversationnelle

## 9. Definition de Done v0.2

Le lot `v0.2` est considere operable si:

- les workflows n8n sont importes et actifs
- le timer Waza tourne sans intervention manuelle
- un rapport est bien pousse dans `memory_runs`
- `memory-healthcheck` peut detecter l'absence de run `incremental`
- le runbook est a jour

## 10. Definition de Done v0.3

Le lot `v0.3` sera considere valide si:

- les 3 repos prioritaires (`VPAI`, `flash-studio`, `story-engine`) ont au moins un seed indexe
- le benchmark retrieval versionne couvre ces 3 repos
- chaque repo passe un benchmark top-3 acceptable ou produit un ecart actionnable
- la qualite retrieval n'est plus validee uniquement sur le repo pilote historique
