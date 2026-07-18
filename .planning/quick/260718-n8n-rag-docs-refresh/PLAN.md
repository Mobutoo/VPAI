# PLAN — Remplacement de la doc n8n dans le RAG (memory_v3)

**Date** : 2026-07-18
**Origine** : follow-up §6 du cutover n8n 2.30.7 (`RUNBOOK-N8N-UPGRADE-SIDECAR.md`, handoff `~/work/ops/loops/plans/2026-07-18-HANDOFF-n8n-fiabilite-et-memoire.md`, item « et-mémoire »).
**Statut** : PLAN — exécution = gate humain (touche l'index RAG prod `memory_v3` sur Qdrant Sese).

---

## 0. Problème

Le RAG (`memory_v3`) indexe les docs n8n depuis le clone git **`/home/mobuone/work/refdocs/n8n-docs`**
(remote `github.com/n8n-io/n8n-docs`), auto-découvert par le worker (wing `refdocs`,
`discovery.enabled: true`). Ce clone est **figé à HEAD `2a3ea68` (2026-04-09)** — il documente n8n
tel qu'il était il y a ~3 mois, alors que la prod tourne désormais en **2.30.7**. Résultat : quand
Claude Code interroge le RAG sur une feature n8n 2.x (nouveaux nodes, MCP natif, task runners
récents), il obtient la doc d'une version antérieure ou rien.

> Note : `n8n-io/n8n-docs` est un dépôt à **branche unique** (docs.n8n.io = doc de la version
> courante, pas de branche par version). « Remplacer » = `git pull` du clone à HEAD puis réindexer.
> Le chemin `/home/mobuone/DOCS/n8n-docs/` cité dans d'anciennes notes est **vide/obsolète** — la
> vraie source est `~/work/refdocs/n8n-docs` (vérifié 2026-07-18).

## 1. État vérifié (2026-07-18)

| Élément | Valeur |
|---|---|
| Source docs | `/home/mobuone/work/refdocs/n8n-docs` (git, remote n8n-io/n8n-docs, HEAD `2a3ea68` 2026-04-09, 2032 fichiers) |
| Collection RAG | `memory_v3` sur `https://qd.ewutelo.cloud` (Qdrant Sese) |
| Worker | `llamaindex-memory-worker.service` + `.timer` (systemd-user, waza) ; wrapper `run-and-report.sh` |
| Config | `/opt/workstation/configs/ai-memory-worker/config.yml` |
| Découverte | `discovery.enabled: true`, `workspace_root: /home/mobuone/work`, wings `[infra, saas, tools, refdocs]` |
| Embedding | `google/embeddinggemma-300m` (768d, local, fp32 sur ARM) |
| Identité fichier | payload `ref_doc_id` (indexé — clé de delete/upsert) ; `repo=n8n-docs`, `wing=refdocs` |
| Filtres | `include_extensions` inclut `.md` ; `exclude_dirs` inclut `.git`, `node_modules`, `eval`… |

## 2. Objectif & critères de succès

- Le RAG répond avec la doc n8n **2.30.x** sur des features postérieures à avril 2026.
- Les points d'anciens fichiers **supprimés/renommés** par le `git pull` sont **purgés** (pas de fantômes).
- Idempotence : un 2e run worker après ingestion = **0 upsert / 0 delete**.
- Éval golden (`memory-eval-golden`) : **zéro régression** sur les requêtes existantes.

## 3. Étapes

### T1 — Rafraîchir le clone source (réversible, hors RAG)
```bash
cd /home/mobuone/work/refdocs/n8n-docs
git fetch origin
git log -1 origin/main --format='%h %ci %s'         # noter la cible
git diff --stat HEAD origin/main | tail -1          # ampleur du delta (fichiers +/-/~)
git checkout main && git pull --ff-only origin main
git log -1 --format='%h %ci %s'                      # confirmer HEAD avancé
```
- **Décision** : si le delta est énorme (refonte arborescence), noter les répertoires
  renommés/supprimés — ce sont eux qui généreront des points orphelins à purger (T4).
- Le clone reste un `git` propre (`require_git: true`) → toujours auto-découvert.

### T2 — Pré-flight worker (éviter les pièges connus)
Réfs mémoire : `project_rag_v3_hybrid`, `project_memory_worker_bm25_cache_reconcile`, `project_waza_ssh_dhcp_oom_2026_06_05`.
- [ ] **Lock/lease** : vérifier qu'aucun run n'est en cours — `index.lock` absent OU `etime` du
      process worker cohérent (un lock zombie bloque ; ne pas lancer par-dessus).
- [ ] **Cache BM25 persistant** : `FASTEMBED_CACHE_PATH` + `HF_HUB_OFFLINE=1` positionnés (le cache
      sur tmpfs `/tmp` est vidé au reboot → re-DL ; cause de l'ingestion HS des 28-29/06).
- [ ] **Mémoire bornée** : lancer le run manuel via `systemd-run --user -p MemoryMax=<N>G` (worker
      non-borné = OOM global → perte DHCP eth0, incident 2026-06-05). NE PAS lancer nu.
- [ ] **Index payload `ref_doc_id`** présent sur `memory_v3` (config `payload_indexes`) — requis
      AVANT toute purge de masse, sinon `delete` par `ref_doc_id` = full-scan → `wait_timeout`.

### T3 — Ingestion incrémentale
Deux voies (choisir selon urgence) :
- **(a) Laisser le timer** `llamaindex-memory-worker.timer` faire son prochain run (calm-wait :
      tourne quand le Pi est calme). Le worker diff par checksum → ré-embed uniquement les fichiers
      changés par le pull, upsert par `ref_doc_id`.
- **(b) Run manuel contrôlé** (si on veut le résultat maintenant) :
```bash
set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
systemd-run --user --scope -p MemoryMax=3G \
  /opt/workstation/ai-memory-worker/.venv/bin/python \
  /opt/workstation/ai-memory-worker/<entrypoint-ingestion> \
  --config /opt/workstation/configs/ai-memory-worker/config.yml
# (confirmer le nom exact de l'entrypoint d'ingestion via run-and-report.sh avant de lancer)
```
- Surveiller `logs/` : progression, pas d'erreur d'embedding, batch OK.

### T4 — Réconciliation / GC des points orphelins
- Les fichiers **supprimés/renommés** par le pull laissent des points `memory_v3` avec un
  `ref_doc_id` qui n'existe plus sur disque. Le GC du worker itère sur son **state**, pas sur
  Qdrant (piège `project_memory_worker_bm25_cache_reconcile`) → vérifier qu'il retire bien ces
  `ref_doc_id`. Sinon purge ciblée par filtre `repo=n8n-docs` + `ref_doc_id` absent du nouveau set.
- Compter avant/après :
```bash
# points n8n-docs dans memory_v3 (filtre repo) — avant T1 et après T4
mcp__qdrant__qdrant-find  query="..." repo=... (ou API count avec filtre repo=n8n-docs)
```

### T5 — Validation
- [ ] **Requête ciblée feature 2.x** : `qdrant-find "n8n MCP server trigger node"` ou une feature
      documentée seulement après avril 2026 → doit renvoyer un chunk `n8n-docs/...` récent.
- [ ] **Non-régression** : lancer `memory-eval-golden.service` (ou attendre le timer 02:02) →
      comparer `recall@1/@5`, `MRR` au dernier rapport `audits/` — zéro régression.
- [ ] **Idempotence** : relancer le worker → 0 upsert / 0 delete sur `n8n-docs`.

## 4. Rollback
- Le clone : `git -C ~/work/refdocs/n8n-docs checkout 2a3ea68` (revenir au HEAD pré-pull), re-run.
- Le RAG : `memory_v3` a un rollback documenté vers `memory_v2` (~2 sem, var `memory_collection_name`,
  `project_rag_v3_hybrid`) — surdimensionné pour ce seul refresh, à ne sortir que si corruption large.

## 5. Points à confirmer à l'exécution (ne pas supposer)
- Nom exact de l'entrypoint d'ingestion appelé par `run-and-report.sh` (T3b).
- Le worker gère-t-il le delete des `ref_doc_id` orphelins automatiquement, ou faut-il la purge
  ciblée T4 ? (tester sur le delta réel du pull).
- Ampleur du delta `git diff HEAD origin/main` (conditionne l'effort T4).

## 6. Liens
- `project_rag_v3_hybrid`, `project_memory_worker_bm25_cache_reconcile`, `project_memory_autodiscovery`
- `docs/runbooks/AI-MEMORY-AGENT-PROTOCOL.md`, `docs/runbooks/MANIFESTE-CREATION-PROJET.md`
- `RUNBOOK-N8N-UPGRADE-SIDECAR.md` §6 (follow-up d'origine)
