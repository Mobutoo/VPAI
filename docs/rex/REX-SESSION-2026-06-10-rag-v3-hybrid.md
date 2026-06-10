# REX Session — RAG memory_v3 hybrid (BM25+RRF + prompt contextuel + harness + feedback) — 2026-06-10

## Objectif

Implémenter en autonomie toutes les recommandations de l'audit RAG 2026-06-09 : migration
`memory_v2` → `memory_v3` côte à côte (hybrid dense+sparse, contextual prompt, harness d'éval,
hygiène hooks, feedback use_count, consolidation REX) + bulk GPU. Contrat normatif :
`docs/superpowers/specs/2026-06-10-rag-v3-contracts.md`.

## Résultat mesuré (golden 76 questions, .planning/eval/)

| Métrique | v2 dense (baseline) | v3 hybrid | Δ |
|---|---|---|---|
| recall@1 | 0.6711 | **0.7237** | +5.3 pts |
| recall@5 | 0.9474 | **0.9868** | +3.9 pts (1 miss/76) |
| MRR@10 | 0.7887 | **0.8432** | +5.5 pts |

Zéro régression (rex : r@5=1.0 maintenu). Gain obtenu AVANT l'ingestion du delta DOCS.
Flip fait : `memory_collection_name: memory_v3` (inventory), rollback = re-flip v2 + redeploy.

## Architecture livrée

- **memory_v3** : vecteurs nommés `dense` (768 cosine, HNSW m=16/ef=100) + `bm25` (sparse,
  modifier=idf), 24 403 pts (7 sources pod) + delta 14 repos en cours. Payload v3 :
  `prompt_version`, `use_count`, `last_used_at` ; legacy severity/category/phase supprimés.
- **Prompt doc v2** : `title: {wing}/{repo}/{relative_path} > {section} | text:` — contextual
  retrieval au niveau prompt, `chunk_text` brut → **node_id inchangés** (parité 13/13 vs live).
- **Recherche** : RRF prefetch dense+bm25 (limit 30), auto-dégradé dense sur collection unnamed,
  floor 0.50 → "not found", format compact, `--boost-usage` (FormulaQuery usage×récence, OFF),
  `--rerank` lazy (bge-reranker-v2-m3 ONNX cache-only, no-op si absent).
- **Harness** : `scripts/memory/eval/` (golden 76 q, recall@k/MRR, --baseline diff). Toute
  modif chunking/modèle/config se mesure désormais avant/après.
- **Feedback loop** : hook Stop `r0-usage-tracker.js` (use_count++/last_used_at sur les hits
  cités), golden candidates jsonl via r0-marker — en avance sur l'état de l'art 2026.
- **Consolidation REX** : `consolidate_rex.py` + timer hebdo (LiteLLM, dim 04:30).
- **Pod bulk** : RTX 4090, bf16 autocast batch 64, **175.7 ch/s** (bench), 24 403 pts en
  ~17 min d'encode, dérive bf16 min=0.99990 (gate >0.999 OK), gates G4c sparse + G5 bootstrap v3.

## Erreurs rencontrées et leçons

### 1. Watcher pod : `diag_gpu` traité comme échec ❌ → pod sain tué
**Symptôme** : watcher v1 stoppe le pod 1 (`bcrrl718k3vy1v`) sur détection `diag_*`.
**Cause** : `diag_gpu` est INFORMATIF (log nvidia-smi du choix torch cuXY, REX bf16 #4) — pas
une balise d'échec. **Fix** : watcher v2 = fatal seulement si pod EXITED **sans** sentinelle,
ou timeout. Coût : ~$0.05 + 25 min.
**Leçon** : la sémantique de chaque balise d'observabilité doit être vérifiée dans le code
producteur avant d'en faire un critère de kill. Un nom de collection ne porte pas sa sévérité.

### 2. Lock tenu par un run worker de 30 h ❌ → delta mort-né
**Symptôme** : delta `--repos` échoue : `lock held by live pid 3666222`.
**Cause** : run incrémental démarré le 08/06 20:00 (ingestion des 13 nouveaux repos
auto-découverts vers v2 à ~0.5 ch/s) toujours vivant 30 h plus tard — il chargeait load>10 en
permanence et ciblait v2 avec l'ancien code (config/code chargés au démarrage, le deploy ne
change pas un process vivant). **Fix** : `systemctl --user stop` (travail obsolète post-flip).
**Leçon** : avant tout run manuel, `cat index.lock` + `ps -p <pid> -o etime` — un timer 30 min
peut cacher un run multi-jours. Le rapport webhook ne signale pas les runs interminables :
ajouter une alerte durée (cf. amélioration future).

### 3. Garde-fou loadavg 6.0 incompatible multi-sessions Claude ❌ → contourné proprement
**Symptôme** : delta relancé échoue : `loadavg too high: 15.00 > 6.00`.
**Cause** : 5 sessions Claude simultanées sur waza ≈ load 13+ structurel ; le seuil 6.0 de
`config limits.loadavg_threshold` (pensé pour les runs non-surveillés du timer) ne descendra
jamais. **Fix** : config dédiée `/tmp/config-v3-delta.yml` (seuil 24) + exécution sous
`systemd-run --user` avec caps D14 (MemoryMax=4G, Nice=19, IOSchedulingClass=idle).
**Leçon** : un run manuel sous nohup N'A PAS les caps mémoire du service systemd (précédent
OOM 2026-06-05). `systemd-run -p MemoryMax=...` donne la parité de protection en one-shot.

### 4. `head -3` mange le résultat derrière les warnings stderr ⚠️
Le smoke "floor" semblait vide : les 2 warnings onnxruntime + 1 warning qdrant-client
consommaient le budget `head`. Re-test avec `2>/dev/null` → `not found` correct.
**Leçon** : toujours séparer stderr avant de tronquer une sortie de vérification.

## Chiffres de référence

| Mesure | Valeur |
|---|---|
| Pod 4090 bench | 74 ch/s fp32 per-batch / 175.7 ch/s bf16, drift 0.99990 |
| Bulk 7 sources | 24 403 chunks, ~17 min encode+upsert |
| Éval Pi (76 q) | encode 117 s (hybrid, 2 encoders), search 5.8 s |
| Coût pods | ~$0.30 (pod 1 tué 25 min + pod 2 22 min, 4090 $0.69/h) |
| fastembed ARM64 | 0.8.0 + onnxruntime 1.26.0 (sibling test OK, pinné worker+pod) |

## Reste / suivis

1. Delta 14 repos (`memory-delta-v3.service`) en cours — watcher ré-arme le timer worker à la fin.
2. Ré-éval post-delta optionnelle (les 2 expected_paths DOCS sont des alternates).
3. `--boost-usage` à activer quand use_count aura accumulé (tracker live).
4. Rerank : déposer l'export ONNX int8 de bge-reranker-v2-m3 dans le cache HF.
5. Rotation secrets (gate humain, inchangé depuis M3/M4).
6. memory_v2 conservée en rollback — supprimer après période d'observation (~2 semaines).
7. Couche graphe (design 2026-06-07) : le harness fournit désormais le banc de mesure du gate P4.

## Commits

VPAI `14d7bf7..031cb98` (contrats, harness, core+pod, search, ansible) + flip inventory +
ce REX. Hooks `~/.claude` : `e224b4f`.
