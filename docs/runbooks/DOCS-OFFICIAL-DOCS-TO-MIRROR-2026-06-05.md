# Docs officiels à miroiter dans `/home/mobuone/DOCS/`

**Date** : 2026-06-05
**Méthode** : scan des manifests (package.json, requirements/pyproject, go.mod, docker-compose, versions.yml) des 7 repos indexés : VPAI, flash-studio, story-engine, podpilot, hawkeye, fantrad, riposte.
**But** : alimenter la mémoire sémantique (memory-worker → Qdrant → R0) en docs officielles des technos réellement utilisées.

## Déjà dans DOCS (ne pas re-cloner)

`litellm-docs`, `n8n-docs`, `openclaw-docs`, `wiki`. (typebot-docs = source séparée, déjà indexée.)

> Note context7 : React, Next.js, FastAPI, Tailwind, Prisma, etc. sont aussi accessibles **live** via le MCP `context7`. Miroiter dans DOCS n'a de sens que pour la **recherche mémoire R0** (Qdrant), pas pour la consultation ponctuelle (context7 suffit). Priorise donc ce qui sert de socle récurrent.

## Matrice cross-repos (technos doc-worthy)

| Techno | VPAI | flash | story | podpilot | hawkeye | fantrad | riposte |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| PostgreSQL | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| Qdrant | ✓ | ✓ | ✓ | | | ✓ | |
| Redis | ✓ | ✓ | ✓ | | ✓ | | |
| FastAPI | | | ✓ | ✓ | ✓ | ✓ | |
| SQLAlchemy + Alembic | | | ✓ | ✓ | | ✓ | |
| Caddy | ✓ | ✓ | | | ✓ | ✓ | |
| Grafana/Loki/Prometheus | ✓ | ✓ | | | | ✓ | |
| React | | ✓ | ✓ | | | | ✓ |
| Next.js | | ✓ | ✓ | | | | |
| Tailwind CSS | | ✓ | ✓ | ✓ | | ✓ | |
| TanStack Query/Table | | ✓ | ✓ | | | | |
| Zod | | ✓ | ✓ | | | | ✓ |
| Stripe | | ✓ | ✓ | | | | |
| Ansible | ✓ | ✓ | | | | | |
| NocoDB / Plane | ✓ | ✓ | | | | | |
| RunPod | | | | ✓ | | ✓ | |
| Anthropic SDK | (claude) | | | | | ✓ | |
| llama.cpp / CUDA | | | | | | ✓ | |
| LlamaIndex | ✓ | | | | | | |

## Recommandations — à cloner dans DOCS

### Tier 1 — socle récurrent (à faire en priorité)

| Doc | Pourquoi | Source officielle (à confirmer) |
|---|---|---|
| **PostgreSQL** | 7/7 repos | postgresql.org/docs (ou repo `postgres/postgres` doc/) |
| **Qdrant** | 4 repos + memory-worker lui-même | github.com/qdrant/qdrant — dossier `docs/`, ou qdrant.tech/documentation |
| **FastAPI** | 4 repos (backend Python standard) | github.com/fastapi/fastapi (`docs/`) |
| **Caddy** | 4 repos + 4 pièges critiques VPAI | github.com/caddyserver/website (`src/docs`) |
| **SQLAlchemy + Alembic** | ORM/migrations de 3 backends | github.com/sqlalchemy/{sqlalchemy,alembic} |
| **Redis** | cache/queue 4 repos | github.com/redis/redis-doc |

### Tier 2 — fort intérêt (1-2 repos clés)

| Doc | Pourquoi |
|---|---|
| **LlamaIndex** | cœur du memory-worker (VPAI) — actuellement non documenté localement |
| **RunPod** | pipeline GPU serverless (fantrad + podpilot), API peu connue |
| **llama.cpp** | inference GGUF fantrad (CUDA, quantization) |
| **Stripe** | paiement flash-studio + story-engine |
| **Zitadel** | auth/OIDC flash-studio (déjà eu des galères SSO) |
| **Budibase** | hawkeye repose dessus |
| **Yjs / Tiptap / Hocuspocus** | éditeur collaboratif story-engine (CRDT, peu trivial) |
| **Grafana/Loki/Prometheus** | stack observabilité (VPAI, flash, fantrad) |

### Tier 3 — optionnel (bien couverts par context7 ou trop volumineux)

React, Next.js, Tailwind, TypeScript, Vite, TanStack, Zod, Fastify, Pydantic, DaisyUI, Radix, Zustand — **context7 les sert live**. Ne miroiter que si on veut absolument la recherche R0 dessus. Presidio (PII), Spacy, WeasyPrint, Chainlit, Flyway, Gotenberg : niche, à la demande.

## Décision d'architecture (2026-06-05) — recherche efficace

### Constat (vérifié sur le Qdrant live)
- Le Qdrant est un "MemPalace" : ~30 collections = les ailes/rooms. Les docs officielles suivent déjà un pattern **1 collection par outil** (`comfyui-docs`, `zitadel-docs`, `kitsu-docs`, `netbird-docs`), peuplées par des scripts ad-hoc (`scripts/index-comfyui-docs.py`).
- **Fragmentation embeddings** : memory_v1=768 (embeddinggemma-300m), comfyui/kitsu=1536, zitadel/netbird=384 → pas de recherche transversale cohérente entre rooms.
- **memory_v1 = AUCUN payload index** → filtres `--repo/--topic/--doc-kind` = scan complet (lent).

### Décision : Path 1 — facette dans memory_v1 (PAS une collection par doc)
1. Chaque doc-set officielle = **une source distincte** dans `memory_worker_sources` → `namespace`/`repo` propre + tags `scope:<tech>` + `kind:official-docs`. C'est la "room", en facette, dans l'espace 768 unifié.
2. **Ne PAS nicher sous `/home/mobuone/DOCS`** (repo git → worker fait `if (path/.git): continue` → tout retombe `namespace=DOCS`). Racine-source dédiée par doc-set (ex. `/home/mobuone/refdocs/<tech>-docs/`).
3. Clone **markdown-only** (sparse-checkout dossier docs + `.md/.mdx`) → ~250M total Tier1+2 (budget OK validé).
4. **Créer les payload indexes** sur `memory_v1` : `namespace`, `doc_kind`, `tags`, `topic` (Qdrant `create_field_index`) → filtrage room-scopé en O(rapide). ← action la plus rentable, indépendante.

### Pourquoi pas Path 2 (collection par doc)
Reproduirait la fragmentation (modèles d'embedding ≠) sauf à d'abord standardiser le modèle partout + généraliser `index-comfyui-docs.py` en indexeur paramétrique. Plus d'effort, recherche transversale impossible tant que les modèles divergent. À envisager seulement après unification du modèle (chantier cleanup séparé).

## Périmètre à confirmer (semaine prochaine, avant clonage)

- Tier 1 + Tier 2 = ~14 doc-sets, markdown-only, ~250M, espace 768.
- PostgreSQL : SGML (pas markdown) → soit version HTML, soit s'appuyer sur context7. À trancher.
- Convention de nommage source : `scope:<tech>` + `kind:official-docs` + racine `/home/mobuone/refdocs/<tech>-docs/`.
