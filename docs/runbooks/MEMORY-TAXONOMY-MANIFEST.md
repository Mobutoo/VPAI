# Manifeste Taxonomie Mémoire — memory_v2

**Statut** : source canonique de la taxonomie wing/room/doc_kind pour `memory_v2`.
**Origine** : spec `docs/superpowers/specs/2026-06-05-memory-system-rebuild-design.md` §4 + MemPalace fantrad (PRD §10-11).
**Consommé par** : `sources.yml` (wing par source), `index.py.j2` (`classify_room`, payload), le batch d'ingestion GPU/CPU, `search_memory.py` (filtres).
**Portée** : taxonomie mémoire uniquement. Le layout physique `~/work/` (reorg M1) est documenté à part (Plan B).

> Règle d'or : un nouveau repo/doc DOIT recevoir un `wing` (config sources.yml) ; le `room` est dérivé du chemin ; le `doc_kind` est dérivé du chemin/contenu. Ne jamais laisser `wing`/`room` nuls.

## 1. Modèle (3 axes orthogonaux)

| Axe | Niveau | Assigné | Cardinalité |
|-----|--------|---------|-------------|
| **wing** | domaine/origine | **config** (`sources.yml` par source) | 1 par repo |
| **room** | catégorie | **dérivé** du chemin relatif (`classify_room`) | N par repo |
| **doc_kind** | nature | **dérivé** (`classify_doc_kind`, existant) | N par repo |
| drawer | unité verbatim | chunk (append-only `valid_from`/`valid_to`) | — |

### Payload du drawer (unité verbatim, append-only) — schéma complet

| Champ | Type | Rôle |
|-------|------|------|
| `wing` | keyword | infra / saas / tools / refdocs |
| `room` | keyword | catégorie dans le wing (cf §3) |
| `doc_kind` | keyword | rex / doc / config / code / audit / runbook / spec / official-docs |
| `repo` | keyword | nom du repo source (ex. fantrad, story-engine, VPAI) |
| `relative_path` | keyword | chemin relatif dans le repo |
| `topic` | keyword | sujet dérivé (titre section) |
| `tags` | keyword[] | tags libres |
| `valid_from` | datetime | début de validité |
| `valid_to` | datetime \| null | null = drawer vivant ; daté = supplanté (append-only) |
| `text` | text | contenu verbatim du chunk |
| (vecteur) | 768d | embedding embeddinggemma-300m |

Champs hérités du worker actuel conservés tels quels : `schema_version`, `embedding_model`, `embedding_dim`, `chunking_strategy_version`, `ref_doc_id`, `namespace` (=`repo`), `host_origin`, `source_kind`, `filename` (+ `severity`/`category`/`phase` legacy, vides).

### Indexes Qdrant (action la plus rentable, cf handoff §4)
Payload indexes sur : `wing`, `room`, `doc_kind`, `repo`, `topic`, `tags`. Sans eux, les filtres = scan complet. (Créés par `qdrant_rebuild.py --create`, déjà en place sur `memory_v2`.)

## 2. Wings (assignés par source dans sources.yml)

| Wing | Sources (repo) | Sens |
|------|----------------|------|
| **infra** | VPAI | Ansible, déploiement, ops self-hosted |
| **saas** | flash-studio, story-engine, podpilot, hawkeye, fantrad, riposte | produits SaaS (room = concern) |
| **refdocs** | DOCS, typebot-docs | docs officielles tierces (`doc_kind=official-docs`) |
| **tools** | (futurs repos outils/scripts isolés) | outillage transverse |

## 3. Rooms — règles de dérivation (`classify_room(wing, relative_path)`)

Ordre = première règle qui matche. Fallback explicite par wing (jamais nul).

### wing `infra` (VPAI)
| Si le chemin… | room |
|---|---|
| `roles/caddy*` ou contient `caddy` | `caddy-vpn` |
| `roles/postgres*` | `postgres` |
| `roles/{grafana,loki,prometheus,alloy,victoriametrics,cadvisor,monitoring}*` | `monitoring` |
| `roles/docker*` ou `docker-stack` | `docker` |
| contient `n8n` (roles/scripts) | `n8n` |
| `roles/*` (autres) | `ansible-roles` |
| `playbooks/*` | `deploy` |
| `docs/TROUBLESHOOTING*` ou `troubleshooting` | `troubleshooting` |
| `docs/*`, `.planning/*` (autres) | `deploy` |
| défaut | `ansible-roles` |

### wing `saas` (room = concern, projet déjà dans `repo`)
| Si le chemin contient… | room |
|---|---|
| `rag`, `memory`, `qdrant`, `embed`, `mind_state` | `rag` |
| `api`, `server`, `routes`, `handler`, `endpoint` | `api` |
| `web`, `frontend`, `ui`, `components`, `app/` (front) | `frontend` |
| `pipeline`, `worker`, `scheduler`, `ingest`, `llama-worker` | `pipeline` |
| `PRD`, `ARCHITECTURE`, `.planning`, `README`, `docs` | `prd-arch` |
| défaut | `api` |

### wing `refdocs` (room = techno)
| Règle | room |
|---|---|
| **Repo-direct** (réorg 2026-06-10, doc-sets au premier niveau `~/work/refdocs/<name>`) : nom du repo sans suffixe `-docs` (`n8n-docs`→`n8n`, `litellm-docs`→`litellm`, `openclaw-docs`→`openclaw`, `wiki`→`wiki`, `typebot-docs`→`typebot`) | `<techno>` |
| `DOCS` legacy (parapluie imbriqué, supprimé 2026-06-10) : 1er segment de chemin sans suffixe `-docs` | `<techno>` |
| défaut | `misc` |

> Signature : `classify_room(wing, relative_path, repo=None)` — `repo` requis pour la
> règle repo-direct ; sans `repo` (ou `repo="DOCS"`), retombe sur la règle par segment.

### wing `tools`
| Règle | room |
|---|---|
| chemin contient `n8n` | `n8n-workflows` |
| `*.sh`, `scripts/` | `scripts` |
| `mcp` | `mcp` |
| défaut | `cli` |

## 4. doc_kind (inchangé — `classify_doc_kind` existant)
`rex` / `audit` / `runbook` / `spec` / `doc` / `config` / `code` / `official-docs`.
Facette orthogonale : un REX de déploiement VPAI = `wing:infra` + `room:deploy` + `doc_kind:rex`.

## 5. Invariants
- `wing` ∈ {infra, saas, refdocs, tools}. `room` non nul (fallback par wing).
- `embedding_model = google/embeddinggemma-300m`, `dim = 768`, `normalize = true`.
- Append-only : nouvelle version d'un chunk → `valid_to` sur l'ancien, nouveau drawer `valid_to=null`.
- Index ⇒ même stack que la query (sentence-transformers 5.1.2 / torch 2.11.0 / fp32). Voir spec §M3.
