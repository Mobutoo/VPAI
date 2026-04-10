# Runbook — AI Memory Operations

Date: 2026-04-10
Statut: v0.5 mapping migration valide
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
- `v0.4` ajoute et valide l'audit read-only des collections Qdrant avant migration legacy
- `v0.5` ajoute le mapping initial de migration legacy
- resultats benchmark:
  - `VPAI`: 7/8 hits top-3, `miss_ratio=0.125`
  - `flash-studio`: 7/8 hits top-3, `miss_ratio=0.125`
  - `story-engine`: 8/8 hits top-3, `miss_ratio=0.0`
- dernier audit Qdrant v0.4:
  - rapport: `/opt/workstation/data/ai-memory-worker/audits/qdrant-inventory-20260410T215942Z.md`
  - collections: 28
  - active: 1 (`memory_v1`)
  - legacy: 23
  - empty: 4
  - total points: 252073
- mapping migration v0.5:
  - fichier: `docs/audits/qdrant-legacy-migration-map-2026-04-11.md`
  - pilote `v0.6`: `app-factory-rex`, `flash-rex`, `rex_lessons`
  - exclusions explicites: `semantic_cache`, collections Jarvis, catalogues applicatifs

## 2. Composants

### Waza

- service: `llamaindex-memory-worker.service`
- timer: `llamaindex-memory-worker.timer`
- wrapper: `/opt/workstation/ai-memory-worker/run-and-report.sh`
- config: `/opt/workstation/configs/ai-memory-worker/config.yml`
- sources: `/opt/workstation/configs/ai-memory-worker/sources.yml`
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

Piege a connaitre sur l'etat du service:

- le service est `Type=oneshot` donc `systemctl is-active llamaindex-memory-worker.service`
  retourne `inactive` apres une execution **reussie**. C'est le comportement
  documente par `systemd.service(5)` pour `Type=oneshot`: l'unite retourne a
  l'etat `inactive` sans jamais transiter par `active`
- seul le **timer** doit rester `active` en permanence
- pour detecter une execution en echec utiliser:

```bash
systemctl is-failed llamaindex-memory-worker.service
systemctl show llamaindex-memory-worker.service --property=ActiveState,SubState,ExecMainStatus
```

- pour lire l'etat du dernier run consulte toujours la DB `memory_runs` en priorite, pas `systemctl`

Verifier aussi:

- log worker: `/opt/workstation/data/ai-memory-worker/logs/memory-worker.log`
- spool local: `/opt/workstation/data/ai-memory-worker/spool/`
- cache HF: `/opt/workstation/data/ai-memory-worker/hf-cache/`

### 4.1.1 Loadavg gate (`memory-wait-calm.sh`)

Le service appelle `memory-wait-calm.sh` en `ExecStartPre=`. Ce script bloque
le demarrage tant que `loadavg(1 min)` depasse le seuil configure. C'est une
protection contre les runs concurrents et contre le vol de CPU pendant que
ComfyUI ou Remotion travaillent.

Source systemd authoritative: d'apres `systemd.service(5)`, si un `ExecStartPre=`
sort avec un code non zero et qu'il n'est **pas** prefixe par `-`, les commandes
suivantes **ne sont pas executees** et l'unite est marquee `failed`. C'est
exactement le comportement voulu ici: si Waza est chaude, on skip proprement
plutot que de lancer un run qui va aggraver la charge.

Script deploye: `/opt/workstation/ai-memory-worker/memory-wait-calm.sh`

Tunables via environnement (lus par le script):

- `MEMORY_WAIT_LOAD_THRESHOLD` (defaut: `memory_worker_loadavg_threshold`, soit `6.0`)
- `MEMORY_WAIT_MAX_CHECKS` (defaut: `60`)
- `MEMORY_WAIT_DELAY_SEC` (defaut: `10`)

Soit une fenetre d'attente maximale de `60 * 10s = 10 min`. Si le Pi reste
au-dessus du seuil pendant 10 minutes, le script rend `exit 1`, le service
est `failed`, et le timer reessaiera au prochain tick.

Test manuel des 3 chemins possibles:

```bash
# happy path (seuil tres haut, passe immediatement)
MEMORY_WAIT_LOAD_THRESHOLD=999 MEMORY_WAIT_MAX_CHECKS=1 MEMORY_WAIT_DELAY_SEC=1 \
  /opt/workstation/ai-memory-worker/memory-wait-calm.sh

# timeout propre (seuil minuscule, fail apres N checks)
MEMORY_WAIT_LOAD_THRESHOLD=0.1 MEMORY_WAIT_MAX_CHECKS=2 MEMORY_WAIT_DELAY_SEC=1 \
  /opt/workstation/ai-memory-worker/memory-wait-calm.sh

# seuil production (sera refuse si la Pi est chaude)
MEMORY_WAIT_MAX_CHECKS=2 MEMORY_WAIT_DELAY_SEC=1 \
  /opt/workstation/ai-memory-worker/memory-wait-calm.sh
```

Si le seuil de production devient trop restrictif (le worker ne tourne plus
jamais) on peut l'ajuster en deploy via `memory_worker_loadavg_threshold` dans
les overrides d'inventaire, puis `make deploy-memory-worker`.

Signal de derive cote `memory-healthcheck`:

- si `ExecStartPre` fail N fois d'affilee, aucun nouveau `memory_runs` n'est
  insere, donc le healthcheck remontera `stale:last_run_Xh_ago` apres
  `MEMORY_HEALTHCHECK_MAX_AGE_HOURS` heures (defaut: 2h)

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

### 5.3.1 Sources indexees

Les sources indexables sont separees de la configuration technique.

Fichier par defaut:

```bash
/opt/workstation/configs/ai-memory-worker/sources.yml
```

Le worker lit ce fichier a chaque run via `config.yml`:

```yaml
paths:
  sources_file: /opt/workstation/configs/ai-memory-worker/sources.yml
```

Ajouter ou ajuster un chemin de source ne demande donc pas de modifier le code
du worker. On peut aussi tester un fichier ponctuel avec:

```bash
/opt/workstation/ai-memory-worker/.venv/bin/python \
  /opt/workstation/ai-memory-worker/index.py \
  --config /opt/workstation/configs/ai-memory-worker/config.yml \
  --sources /tmp/memory-sources-test.yml \
  --preflight-only \
  --repo ops
```

Validation effectuee:

- `--sources /tmp/memory-sources-ops.yml --preflight-only --repo ops`:
  `repo_roots=1`, `repos=['ops']`, `exit_code=0`
- sources par defaut + dry-run `ops`:
  `attempted_files=1`, `indexed_chunks=20`, `errors=[]`, `exit_code=0`

### 5.3.2 Seed scope recommande pour v0.3

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

### 5.6 Audit Qdrant v0.4

L'audit Qdrant est **read-only**. Il inventorie les collections existantes,
leur dimension vectorielle, leur volume, leur forme de payload et leur statut
probable (`active`, `legacy`, `empty`).

Depuis le repo d'ops:

```bash
make memory-qdrant-audit
```

Depuis Waza:

```bash
set -a
. /opt/workstation/configs/ai-memory-worker/memory-worker.env
set +a

ts=$(date -u +%Y%m%dT%H%M%SZ)
/opt/workstation/ai-memory-worker/.venv/bin/python \
  /opt/workstation/ai-memory-worker/inventory_collections.py \
  --config /opt/workstation/configs/ai-memory-worker/config.yml \
  --output-json /opt/workstation/data/ai-memory-worker/audits/qdrant-inventory-${ts}.json \
  --output-md /opt/workstation/data/ai-memory-worker/audits/qdrant-inventory-${ts}.md
```

Rapports:

- JSON: `/opt/workstation/data/ai-memory-worker/audits/qdrant-inventory-*.json`
- Markdown: `/opt/workstation/data/ai-memory-worker/audits/qdrant-inventory-*.md`

Regles:

- ne jamais supprimer une collection legacy depuis ce script
- reindexer depuis les sources originales si la dimension ou le payload differe
- garder les anciennes collections tant que le benchmark retrieval n'est pas valide
- documenter le mapping legacy -> `memory_v1` avant toute purge

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

### 6.3 Exit codes du worker

Codes produits par `index.py` et propages par `run-and-report.sh`:

| Code | Signification | Cause typique |
|---|---|---|
| `0` | Run nominal. Aucune erreur par fichier. | Cas normal. |
| `1` | Le run a demarre mais au moins un fichier a echoue, ou une erreur fatale a stoppe le scan. | `errors` non vide dans le rapport, ou `RuntimeError` attrape en fin de main. |
| `1` | Lock file present (un autre run est deja en cours). | Concurrence detectee. Ne se produit normalement pas grace a `ExecStartPre`. |
| `1` | `loadavg too high` (garde in-code). | Controle residuel si `memory-wait-calm.sh` a ete contourne. |
| `1` | Repo demande introuvable. | `--repo X` ou `sources.yml` reference un chemin qui n'existe pas. |

Codes additionnels visibles uniquement via systemd (pas dans `memory_runs`
parce que le worker n'a jamais pu produire un rapport):

| Etat systemd | Signification |
|---|---|
| `ExecMainStatus=0` + `SubState=dead` | Oneshot termine normalement. `is-active=inactive`, `is-failed=no`. |
| `ExecMainStatus!=0` + `SubState=failed` | `ExecStart` a echoue. `is-failed=yes`. Un rapport avec `exit_code != 0` a pu etre POST ou non. |
| `ExecMainStatus=0` + `Result=exec-condition` | `ExecStartPre=` (donc `memory-wait-calm.sh`) a echoue. Aucun rapport n'a ete genere. |

### 6.4 Diagnostic pas-a-pas

Ordre de lecture recommande quand l'healthcheck alerte:

1. **Derniere ligne de `memory_runs`**: la DB est la source de verite
   ```sql
   SELECT id, run_id, host_origin, mode, exit_code, qdrant_reachable,
          spool_size, errors::text, received_at
   FROM memory_runs ORDER BY id DESC LIMIT 5;
   ```
2. Si la derniere ligne est **stale** (plus vieille que `MEMORY_HEALTHCHECK_MAX_AGE_HOURS`):
   le worker n'a pas pousse de rapport. Deux sous-cas:
   - `ExecStartPre` refuse les runs (Pi chaud): voir `journalctl -u llamaindex-memory-worker.service` pour les lignes `memory-wait-calm: timeout`
   - le worker ne demarre plus du tout: verifier le timer et les logs systemd
3. Si la derniere ligne est recente mais **`exit_code != 0`**:
   lire `errors::text` pour comprendre. Regarder aussi le log worker aux timestamps concernes.
4. Si **`qdrant_reachable=false`**: voir 7.1 (Qdrant inaccessible).
5. Si **`spool_size > 0`** et remonte: Qdrant a ete KO et le worker a
   reporte les lots. Ils seront retentes au prochain run.

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

- `loadavg too high` dans le log worker
- lignes `memory-wait-calm: timeout waiting for loadavg <= 6.0` dans `journalctl`
- le service part en `failed` avec `Result=exec-condition`

Action:

- attendre une fenetre plus calme (le prochain tick du timer reessaiera)
- eviter les runs memoire pendant les grosses charges ComfyUI / render / jobs rails
- si vraiment bloquant: ajuster `memory_worker_loadavg_threshold` dans l'inventaire et redeployer
- voir **section 4.1.1 Loadavg gate** pour les tunables `MEMORY_WAIT_*`

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

## 11. Definition de Done v0.4

Le lot `v0.4` est considere valide si:

- le script `inventory_collections.py` est deploye sur Waza
- `make memory-qdrant-audit` produit un rapport JSON et Markdown
- la collection cible `memory_v1` est identifiee comme `active`
- les collections non cible sont classees `legacy` ou `empty`
- aucun delete/drop Qdrant n'est execute pendant l'audit
- un mapping de migration legacy peut etre redige a partir du rapport

Validation du 2026-04-10:

- rapport: `/opt/workstation/data/ai-memory-worker/audits/qdrant-inventory-20260410T215942Z.md`
- `memory_v1`: `active`, 1105 points, dimension 768
- collections legacy: 23
- collections vides: 4
- point d'attention: `semantic_cache` contient 245555 points en dimension 1536;
  a traiter comme une collection applicative/cache a part, pas comme une source a
  migrer aveuglement vers `memory_v1`

## 12. Definition de Done v0.5

Le lot `v0.5` est considere valide si:

- chaque collection auditee en v0.4 a une decision initiale
- les collections candidates a migration pilote sont identifiees
- les collections hors scope sont explicitement exclues de `memory_v1`
- aucune suppression Qdrant n'est executee
- le fichier de mapping est versionne dans `docs/audits`

Validation du 2026-04-11:

- mapping: `docs/audits/qdrant-legacy-migration-map-2026-04-11.md`
- pilote `v0.6`: `app-factory-rex`, `flash-rex`, `rex_lessons`
- `semantic_cache` reste hors migration documentaire
- collections vides marquees `drop_candidate_empty`, sans suppression immediate
