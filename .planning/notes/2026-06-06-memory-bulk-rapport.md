# Rapport — Bulk mémoire M3 sur pod GPU + optimisation matérielle (2026-06-06)

## 1. Contexte & objectif

Le rebuild du système mémoire (Plan A) en est à l'étape **M3** : peupler la collection Qdrant `memory_v2` (768d cosine, modèle `google/embeddinggemma-300m`) avec l'intégralité du corpus — **7 sources git** (VPAI, flash-studio, story-engine, typebot-docs, hawkeye, fantrad, riposte) — via un **pod RunPod jetable et non-supervisé**.

Contrainte fondatrice : **parité stricte** entre le worker d'ingestion Waza (incrémental, ARM CPU) et le pod bulk (GPU), pour que la ré-ingestion soit **idempotente** (mêmes `node_id`, mêmes payloads).

Demande utilisateur en cours de route : reposer l'architecture à plat pour une solution **pérenne, efficiente, qui utilise pleinement le matériel** — sans jamais sacrifier la qualité d'embedding.

## 2. Ce qui a été livré

### Pipeline d'ingestion GPU non-supervisé (`scripts/memory/gpu_ingest/`)
- `provision_pod.sh` : création pod RunPod (REST API), modes `--check[-gpu]`, `--probe`, `--create[-gpu]`, `--stop`, `--terminate`. Mode GPU : `computeType GPU` + `gpuTypeIds` (liste de repli Ada-d'abord, 6 IDs validés via GraphQL) + `EXPECT_CUDA=1`.
- `bootstrap.sh` : gates durs G1→G10 (Tailscale userspace + pont socat → Qdrant → clone PAT → venv → **détection driver + torch aligné** → warm-up assert cuda/fp32 → parité node_id → bench → bulk → sentinelle → self-stop). Observabilité par collections Qdrant (`stage_*`, `diag_*`) car RunPod n'expose pas de logs via API.
- `pod_ingest.py` / `memory_core.py` (partagé worker/pod) : chunking, payload, encodeur. Optimisations : `build_repo_git_shas` (git 1 traversée/repo), encode **batché cross-fichier**, flag `--bf16` (autocast cuda côté pod), bench instrumenté (split CPU/GPU + dérive bf16).

### Décisions d'architecture (toutes adossées à une mesure)
1. **Modèle conservé** : `embeddinggemma-300m`. Aucun modèle rapide n'est équivalent en qualité (candidats tous 384d, MTEB-multilingue inférieur). Archi réutilisable sur d'autres projets.
2. **Schéma dtype hybride** : pod = **bf16** (tensor cores L4), worker Waza = **fp32** (ARM sans bf16 HW). Mixage prouvé sûr (dérive 0.00008).
3. **Encodeur partagé fp32-pur** : bf16 reste un flag pod-side → worker intact, zéro risque de parité.
4. **`node_id` texte-seul** : parité indépendante du dtype/matériel → idempotence garantie.

## 3. Résultats mesurés

| Indicateur | Avant | Après optimisation |
|---|---|---|
| Débit embedding | 0.5 ch/s (CPU) / 22.8 (GPU per-fichier) | **53.2 ch/s** (GPU bf16) |
| git_sha | 38.5 ms/fichier (subprocess) | **0.35s/repo** (×180, parité 300/300) |
| Goulot identifié | — | **encode = 87%** du temps (mesuré, pas supposé) |
| Dérive fp32↔bf16 | — | **min 0.99992 / mean 0.99997** (retrieval-équivalent) |
| Corpus | estimé 78 500 (faux) | **23 672 chunks** (réel) |
| GPU | 0% (fallback CPU) | **100% util, bf16 tensor cores** |

Coût : ~$0.39/h (L4), bulk ≈ 10-15 min → quelques centimes par run.

## 4. État actuel

- Pipeline **prouvé bout-en-bout** : un run fp32 batch-64 a complété (sentinelle `ingest_done`, `memory_v2`=23 672, self-stop propre).
- **Run bf16 en cours** (pod `tkf07peh1913di`) → écrase idempotemment les points fp32 en bf16. Vérification attendue : compte final ≈ 23 672.
- 6 commits poussés sur `origin/main` (`988b219`→`4aabd1f`).
- REX détaillé : `docs/rex/REX-SESSION-2026-06-06-memory-bulk-gpu-bf16.md`.

## 5. Reste à faire

1. **Vérifier** le run bf16 (compte ≈ 23 672 + parité node_id).
2. **Teardown** : terminer le pod, révoquer la clé Headscale éphémère + le PAT read-only, `rm pod-ingest.env`, supprimer les collections transitoires `stage_*`/`diag_*`/`probe_ok`/`ingest_done`.
3. **Rotation des secrets exposés** durant l'opération : `HF_TOKEN`, `QDRANT_API_KEY`, `RUNPOD_API_KEY`.
4. **M4** : repointer `search_memory.py` + `mcp__qdrant__qdrant-find` sur `memory_v2`, retirer le flag `r0-rebuild.flag` + le bloc hook `r0Rebuild`, purger les `.bak`. Rétablit le canal froid de recherche mémoire.

## 6. Réutilisabilité

Le pipeline (`provision_pod.sh` + `bootstrap.sh` + `pod_ingest.py` + `memory_core.py`) est paramétré par `sources.pod.yml` et `requirements.lock.txt`. Pour un autre projet/corpus : changer les sources + le lock, garder la mécanique (détection driver, fail-fast cuda/fp32, git per-repo, encode batché, bf16 gaté, observabilité Qdrant, watcher kill actif). Le schéma hybride dtype (GPU bf16 / CPU fp32) est transposable à tout couple worker-léger / bulk-accéléré.
