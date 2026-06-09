# Contrats — RAG memory_v3 (hybrid + harness + feedback) — 2026-06-10

Statut : EXÉCUTION AUTONOME (GO utilisateur). Source audit : session 2026-06-09/10.
Référence architecture existante : `docs/superpowers/specs/2026-06-05-memory-system-rebuild-design.md`,
`docs/rex/REX-SESSION-2026-06-06-memory-bulk-gpu-bf16.md`, `scripts/memory/gpu_ingest/README.md`.

## Objectif

Migration `memory_v2` → `memory_v3` côte à côte (zéro wipe de v2, rollback = flip config) avec :
hybrid dense+sparse BM25+RRF, contextual prefix au niveau prompt d'embedding, harness d'éval
golden-set, hygiène d'injection hooks, feedback loop use_count, decay/boost, consolidation REX.

## Invariants NON NÉGOCIABLES (parité worker ↔ pod)

1. **node_id INCHANGÉ** : `UUID(sha256(f"{ref_doc_id}:{chunk_index}:{chunk_text}")[:32])`.
   `chunk_text` reste BRUT — le prefix contextuel va dans le PROMPT d'embedding, jamais dans le texte.
2. **Chunking INCHANGÉ** : CHUNK_SIZE=1600, OVERLAP=200, MAX_CHUNKS_PER_FILE=200, mêmes parsers.
3. **Modèle dense INCHANGÉ** : `google/embeddinggemma-300m`, 768d, normalize=True,
   fp32 worker (ARM) / bf16 autocast pod (flag `--bf16`), query prompt `"Retrieval-query"`.
4. **Toute logique partagée vit dans `scripts/memory/memory_core.py`** (parité worker/pod).
   Tests parité dans `scripts/memory/test_memory_core.py` doivent passer.
5. **memory_v2 INTOUCHÉE** (collection, config live). La bascule = changer `collection_name`
   dans `config.yml` (+ template `config.yml.j2`) APRÈS validation éval.

## Collection `memory_v3` (nouveau)

- Vecteurs nommés :
  - `dense` : 768d, Cosine (params HNSW identiques v2 : m=16, ef_construct=100).
  - `bm25` : sparse, `modifier: idf`.
- `on_disk_payload: true`.
- Index payload : keyword sur wing, room, doc_kind, repo, topic, tags, host_origin, source_kind
  (DROP legacy severity/category/phase) ; integer sur `use_count` ; datetime sur `valid_from`, `last_used_at`.
- Script bootstrap idempotent : `scripts/memory/qdrant_bootstrap_v3.py` (create si absent, vérifie schéma sinon).

## Nouveaux contrats d'encodage

- **Prompt document v2** (dense) : `title: {wing}/{repo}/{relative_path}{ > header_path si section} | text: {chunk_text}`
  → fonction `build_doc_prompt(meta, chunk)` dans memory_core.py. Constante `PROMPT_VERSION = "v2-2026-06-10"`,
  écrite en payload `prompt_version`.
- **Sparse BM25** : FastEmbed modèle `Qdrant/bm25`, texte = `f"{relative_path} {section} {chunk_text}"`
  → fonction `build_sparse_text(meta, chunk)` + wrapper encodeur lazy (`fastembed`) dans memory_core.py.
  MÊME fonction côté worker, pod, et requête (search).
- **Payload ajouts** : `prompt_version` (str), `use_count` (int, défaut 0), `last_used_at` (null).
  Le reste du payload v2 est conservé à l'identique (sauf severity/category/phase, supprimés).

## Recherche (search_memory.py + mcp_search.py)

- **Hybrid par défaut sur v3** : Query API `query_points` avec `prefetch` dense (limit 30, using="dense")
  + sparse (limit 30, using="bm25") → fusion RRF. Flag `--mode dense|hybrid`.
- **Score floor** : `--min-score` (défaut 0.50 sur le score dense cosine ; sous le floor → sortie
  explicite `not found`). mcp_search applique le même floor.
- **Format compact** : `score | repo/relative_path | section | snippet 1 ligne` (plus de JSON brut verbeux).
- **Boost usage/récence** (flag `--boost-usage`) : formula query Qdrant
  (score × (1 + ln(1+use_count)) avec composante récence sur valid_from). Désactivé par défaut,
  activable après accumulation de données.
- **Rerank optionnel** (`--rerank`, flag OFF par défaut) : module `scripts/memory/rerank.py`,
  bge-reranker-v2-m3 ONNX int8 sur top-30 → top-k. Lazy : si modèle absent du cache HF → skip avec warning.
  NE PAS télécharger le modèle pendant le build (HF_HUB_OFFLINE=1 sur Waza).
- **Rétro-compat** : sur une collection à vecteur unnamed (v2), mode dense legacy doit continuer à marcher
  (détection auto du schéma de collection).

## Harness d'éval (`scripts/memory/eval/`)

- `golden.yml` : ≥60 questions FR/EN générées depuis docs/rex/, docs/runbooks/, docs/TROUBLESHOOTING.md,
  docs/guides/ — chaque entrée : `{query, expected_paths: [repo:relative_path...], doc_kind, note}`.
  Inclure cas exact-match (noms de variables, commandes, tags d'images) ET cas sémantiques.
- `run_eval.py` : `--collection`, `--mode dense|hybrid`, `--limit`, `--golden`, `--out`.
  Métriques : recall@1, recall@5, MRR@10, breakdown par doc_kind. Match = expected_path ∈ top-k
  (match sur payload `repo`+`relative_path`). Sortie JSON dans `.planning/eval/`.
  Doit tourner sur le venv worker Waza (`/opt/workstation/ai-memory-worker/.venv`).
- Comparaison : `run_eval.py --baseline <json>` affiche le diff par métrique.

## Hooks (~/.claude — repo git séparé, NE PAS COMMIT, état dirty préexistant)

- `r0-usage-tracker.js` (event **Stop**) : lit le transcript (chemin fourni par le hook input),
  repère les `relative_path` retournés par les recherches mémoire du turn ET cités dans la réponse
  finale → `POST /collections/<coll>/points/payload` Qdrant (set `last_used_at`, incrément `use_count`
  via lecture-modification simple sur les points filtrés repo+relative_path). Fail-open, timeout 5s,
  env chargé depuis `/opt/workstation/configs/ai-memory-worker/memory-worker.env`.
- Hygiène injection : `memory-search-start.sh` + `mcp_search.py` consommé par hooks → appliquer floor
  0.50 et rendu compact ; sous floor, afficher `not found` (jamais de hit hors-sujet).
- Golden candidates : dans `r0-marker.js`, append `{ts, query, top_hit_path, score}` à
  `~/.claude/r0-golden-candidates.jsonl` (fail-open) — vivier pour enrichir golden.yml.
- Enregistrer le hook Stop dans `~/.claude/settings.json` (suivre le pattern des hooks Stop existants).
- Vérif : `node -c` sur chaque JS modifié + suites de test existantes dans ~/.claude si présentes.

## Ansible (roles/llamaindex-memory-worker)

- Source of truth = repo VPAI. Vérifier dans `tasks/main.yml` COMMENT memory_core.py et mcp_search.py
  arrivent dans /opt (template/copy depuis scripts/memory ?) et garantir que le deploy reproduit
  TOUS les fichiers modifiés (memory_core.py, index.py, search_memory.py, mcp_search.py, eval/, rerank.py,
  qdrant_bootstrap_v3.py).
- `requirements.txt.j2` += `fastembed` (vérifier wheel ARM64/onnxruntime dispo — sibling test pip
  dans un venv /tmp AVANT de figer).
- Caps mémoire D14 : vérifier que les templates service portent MemoryHigh=3G/MemoryMax=4G/
  MemorySwapMax=512M/OOMScoreAdjust=1000 (le live /opt les a ; le rôle doit les porter aussi).
- `config.yml.j2` : `collection_name` pilotée par variable `memory_collection_name`
  (défaut **memory_v2** — flip vers v3 = changement de variable, pas de code).
- index.py(.j2) : flag `--repos <name,name>` (filtre sources), rotation backup `memory_state.json.bak`,
  compteur de troncatures MAX_CHUNKS_PER_FILE loggé + remonté dans le report webhook.
- Consolidation REX : `scripts/memory/consolidate_rex.py` (lit docs/rex/ récents → synthèse 5-10 lignes
  par topic via LiteLLM `https://llm.ewutelo.cloud/v1` modèle économique, écrit
  `docs/memory-consolidated/<topic>.md` doc_kind auto `doc`) + timer systemd-user hebdo (template rôle).
  Budget : 1 run/semaine, gardé par le cap LiteLLM existant.

## Pod bulk (gpu_ingest/)

- `pod_ingest.py` + `bootstrap.sh` : cible collection via env `MEMORY_COLLECTION` (défaut memory_v2),
  upsert bi-vecteur (dense nommé + bm25), prompt v2, fastembed dans `requirements.lock.txt`
  (version pinnée), bootstrap collection v3 au démarrage (G-gate dédié), balises stage_* conservées.
- `provision_pod.sh` : corriger ENV_RUNPOD défaut → `/home/mobuone/work/saas/fantrad/.env` ;
  passer `MEMORY_COLLECTION` au pod.
- RAPPEL REX #3 : le pod clone depuis GitHub → push origin main obligatoire avant launch.

## Couverture corpus v3

- Pod : les 7 sources git de `sources.pod.yml` (~23.7k chunks, prouvé).
- Delta (13 repos auto-découverts restants) : worker Waza `--mode full --repos <delta>`
  (run one-shot nohup, nice/capé, plusieurs heures acceptées).

## Interdits pour les agents de build

- AUCUN `git commit` / `git push` (l'orchestrateur committe à la fin, streams séquencés).
- AUCUNE mutation Qdrant live (pas de création de collection, pas d'upsert) pendant le build.
- AUCUN déploiement (make deploy-*) pendant le build.
- Ne pas toucher au venv live `/opt/workstation/ai-memory-worker/.venv` (sibling tests dans /tmp).
