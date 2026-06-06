# Vision — Extraction du système mémoire en tool autonome, agnostique & dockerisé

> **Statut** : document de cadrage. À traiter dans une **nouvelle session** (projet dédié, nouveau repo).
> **Origine** : le pipeline d'ingestion mémoire construit dans VPAI (cf `docs/rex/REX-SESSION-2026-06-06-memory-bulk-gpu-bf16.md` + `.planning/notes/2026-06-06-memory-bulk-rapport.md`).

## 1. Objectif

Sortir le système d'ingestion mémoire de VPAI pour en faire un **outil indépendant et réutilisable** sur n'importe quel projet, avec :

- **Worker incrémental local** (CPU, léger) : indexe en continu les fichiers modifiés.
- **Pod bulk** (GPU, jetable) : ingestion massive initiale ou ré-indexation complète, accélérée.
- **Base Qdrant architecturée** : schéma + index payload + dtype définis, portables.
- **Agnostique** : zéro dépendance aux concepts VPAI ; tout pilotable par config.
- **Dockerisé** : worker et bulk-runner packagés en images.

Principe directeur conservé : **parité worker ↔ pod** via `node_id` texte-seul → ré-ingestion idempotente, indépendante du matériel et du dtype.

## 2. Ce qui existe déjà (réutilisable tel quel ou presque)

| Composant | Fichier (VPAI) | Réutilisabilité |
|---|---|---|
| Chunking déterministe (tiktoken cl100k) | `scripts/memory/memory_core.py` `build_chunks` | ✅ générique |
| `node_id` texte-seul (parité/idempotence) | `memory_core.make_node_id` | ✅ **invariant à garder** |
| Encodeur (fp32 + flag bf16 autocast) | `memory_core.EmbeddingGemmaEncoder` | ✅ rendre le modèle configurable |
| git SHA par-repo (×180) | `memory_core.build_repo_git_shas` | ✅ générique |
| Bulk ingest (git pré-calc + encode batché + bf16) | `gpu_ingest/pod_ingest.py` | ✅ découpler des sources VPAI |
| Bootstrap pod (gates G1→G10, fail-fast cuda/fp32, détection driver, bench honnête) | `gpu_ingest/bootstrap.sh` | ⚠️ découpler de Headscale/socat |
| Provisioning RunPod (REST, gpuTypeIds repli) | `gpu_ingest/provision_pod.sh` | ⚠️ abstraire le « bulk runner » |
| Observabilité sans logs API (beacons/diag Qdrant) | `bootstrap.sh` | ✅ pattern générique |
| Watcher kill-actif (anti pod orphelin) | `/tmp/watch_pod3.sh` | ✅ à intégrer proprement |

## 3. Ce qui est VPAI-spécifique → à abstraire

1. **Taxonomie `wing`/`room`/`doc_kind`** : concepts VPAI. → rendre optionnelle / pluggable (schéma de payload défini par config, classifieurs injectables).
2. **Sources git en dur** (`sources.pod.yml` : VPAI, flash-studio…). → fichier de config générique : liste de sources (git URL ou chemin local) + métadonnées arbitraires.
3. **Réseau Headscale/Tailscale + pont socat** : infra VPAI (Qdrant derrière Caddy vpn_only). → le tool doit supporter un **Qdrant joignable directement** (URL + API key), le mesh devenant une *option* de déploiement, pas un prérequis.
4. **Provisioning RunPod** : un fournisseur parmi d'autres. → interface « bulk runner » : RunPod, GPU local, autre cloud.
5. **Modèle `embeddinggemma-300m`** : défaut, mais configurable (dim, prompt format, normalize, dtype).
6. **Rôle Ansible worker** (`llamaindex-memory-worker`) : déploiement VPAI. → remplacer par image Docker + compose/systemd générique.

## 4. Architecture cible

```
┌─────────────────────────────────────────────────────────────┐
│ memory-tool/  (repo autonome)                                │
│                                                              │
│  core/            lib pure (chunk, node_id, payload, encoder)│
│   ├─ chunking.py     tiktoken déterministe                   │
│   ├─ node_id.py      sha(ref:idx:text) — INVARIANT parité    │
│   ├─ encoder.py      modèle configurable, fp32 / bf16 gaté   │
│   ├─ payload.py      schéma payload défini par config        │
│   └─ sources.py      abstraction source (git/local/…)        │
│                                                              │
│  worker/          incrémental local (CPU)                    │
│   ├─ scan changed files → chunk → encode (fp32) → upsert     │
│   ├─ état: dernier scan / hashes (pour le diff)              │
│   └─ Dockerfile (CPU), monte les dossiers sources            │
│                                                              │
│  bulk/            ingestion massive (GPU)                    │
│   ├─ runner interface: runpod | local-gpu | …                │
│   ├─ bootstrap: gates, fail-fast cuda/fp32, détection driver │
│   ├─ git pré-calc + encode batché + bf16 autocast            │
│   ├─ observabilité beacons/diag (si pas de logs)             │
│   └─ Dockerfile (GPU/CUDA)                                   │
│                                                              │
│  qdrant/          schéma de la base                          │
│   ├─ create_collection (dim, distance, payload indexes)      │
│   └─ migration / vérif schéma                                │
│                                                              │
│  config.yml       LE point d'entrée agnostique :            │
│   ├─ qdrant: url, api_key, collection, dim, distance         │
│   ├─ model: name, prompt_format, normalize, dtype_bulk       │
│   ├─ sources: [ {name, type:git|local, uri, meta:{…}} ]      │
│   ├─ payload_schema + payload_indexes                        │
│   └─ bulk_runner: {provider, gpu_types, …}                   │
└─────────────────────────────────────────────────────────────┘
```

### Flux
1. **Init** : `qdrant/` crée la collection (dim/distance/index) depuis `config.yml`.
2. **Bulk** (1×, ou ré-index) : pod GPU clone/lit les sources → chunk → encode **bf16** → upsert. Idempotent.
3. **Incrémental** (continu) : worker local CPU détecte les fichiers changés → chunk → encode **fp32** → upsert (mêmes `node_id` → écrase).
4. **Recherche** : encode requête (fp32) → Qdrant search. Mixage fp32/bf16 sûr (dérive mesurée 0.00008).

## 5. Invariants NON-NÉGOCIABLES (sinon on casse l'idempotence/parité)

- **`node_id` = sha(ref_doc_id : chunk_index : chunk_text)** — texte seul, jamais le vecteur ni le dtype ni le matériel.
- **Chunking déterministe** : même tokenizer (tiktoken cl100k baké offline), mêmes `CHUNK_SIZE`/`OVERLAP`/`MAX_CHUNKS` worker == bulk.
- **Encodeur partagé** entre worker et bulk (même prompt format, même normalize). dtype = seule divergence autorisée (fp32 vs bf16, dérive bornée mesurée).
- **Self-check parité** au démarrage du bulk (échantillon → `node_id` attendus).
- **Fail-fast** : sur GPU, assert `cuda.is_available()` + dtype attendu, sinon self-stop (pas de fallback CPU silencieux à 45×).
- **Observabilité** quand pas de logs (beacons/diag dans la base).
- **Kill garanti** du runner bulk (ne pas dépendre du self-stop).

## 6. Packaging Docker

- **`memory-worker`** (image CPU) : entrypoint = boucle incrémentale (scan → diff → upsert). Volumes = dossiers sources. Env = config Qdrant. `restart: unless-stopped`. Léger (Pi/ARM OK, fp32).
- **`memory-bulk`** (image GPU/CUDA) : entrypoint = bootstrap (clone/lit sources → bulk bf16 → sentinelle → exit). Lançable sur RunPod **ou** tout hôte GPU (`docker run --gpus all`). Le provisioning RunPod devient un wrapper optionnel autour de cette image.
- **`compose`** d'exemple : Qdrant + worker, pour un démarrage local complet.

## 7. Décisions ouvertes (pour la nouvelle session)

1. **Nom + licence** du tool (open-source ?).
2. **Taxonomie** : garder `wing`/`room` en plugin optionnel, ou payload 100 % libre piloté par config ?
3. **Worker incrémental** : état du diff (DB sqlite locale ? hashes en payload Qdrant ? mtime ?). Watch (inotify) vs scan périodique (cron/systemd timer).
4. **Bulk runner** : interface formelle (abstraite RunPod) ou rester RunPod-only au début ?
5. **Réseau** : Qdrant direct (API key) par défaut ; mesh/proxy en option documentée.
6. **GC des orphelins** : éditer un fichier change ses `node_id` → anciens chunks orphelins. Stratégie ? (re-bulk périodique, ou tag `content_hash` + purge des node_id absents du dernier scan d'un fichier).
7. **Modèle par défaut** : embeddinggemma-300m (gated, HF token) vs alternative non-gated pour l'open-source.
8. **Multi-collection / multi-projet** : un Qdrant pour N projets (filtre par `project`) ou 1 collection/projet ?

## 8. Roadmap d'extraction proposée

1. **P0 — Squelette repo** : `core/` extrait de `memory_core.py` (sans wing/room en dur), `config.yml`, tests `node_id`/chunking (parité = golden tests).
2. **P1 — Qdrant init** : création collection depuis config (dim/distance/index).
3. **P2 — Worker incrémental dockerisé** : diff + upsert fp32, image CPU, compose avec Qdrant.
4. **P3 — Bulk dockerisé** : image GPU (bootstrap généralisé, fail-fast, bf16, observabilité), `docker run --gpus all`.
5. **P4 — Bulk runner RunPod** : wrapper provisioning autour de l'image P3 + watcher kill-actif intégré.
6. **P5 — Doc + exemple** : README, quickstart compose, doc des invariants.

## 9. Sources à reprendre (dans VPAI)

- `scripts/memory/memory_core.py` (cœur)
- `scripts/memory/gpu_ingest/{pod_ingest.py,bootstrap.sh,provision_pod.sh,sources.pod.yml,requirements.lock.txt,reference_nodeids.json,tiktoken_cache/}`
- Rôle worker : `roles/llamaindex-memory-worker/` (à transposer en Docker)
- REX + rapport : `docs/rex/REX-SESSION-2026-06-06-memory-bulk-gpu-bf16.md`, `.planning/notes/2026-06-06-memory-bulk-rapport.md`
