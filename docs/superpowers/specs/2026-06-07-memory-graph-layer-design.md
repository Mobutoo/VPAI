# Design — Couche graphe de connaissances sur memory_v2

> Date : 2026-06-07
> Statut : design approuvé (gate brainstorming) — pré-spec-review
> Origine : analyse de `safishamsi/graphify` vs notre mémoire Qdrant `memory_v2`

## 1. Problème

Notre mémoire R0 repose sur Qdrant `memory_v2` : recherche **vectorielle** (kNN sémantique)
sur ~23 692 points (`embeddinggemma-300m`, 768-dim). Excellente pour le rappel flou
("comment on a fixé X"), mais **incapable** de :

- répondre aux questions **relationnelles / multi-hop** (`var → role → service`,
  `A appelle B appelle C`) ;
- distinguer un fait **certain** d'un fait **deviné** (cosinus seul, pas de provenance) ;
- faire de l'**analyse d'impact** ("je change `{{ postgresql_password }}`, quels
  conteneurs crash-loop ?") — pourtant une règle dure de `CLAUDE.md`.

`graphify` résout ça avec un **graphe typé** (arêtes `calls/imports/...`,
labels de confiance, `shortest_path`). On **n'adopte pas graphify** : on **bâtit ces
capacités dans notre système**, en couche **au-dessus** de `memory_v2`.

## 2. Principe directeur

Le graphe **complète** la recherche vectorielle, ne la remplace pas. Chaque nœud
porte `qdrant_point_ids[]` → pont de retour vers les vecteurs. Deux mémoires
complémentaires :

| Mémoire | Rôle | Reste maître de |
|---|---|---|
| `memory_v2` (Qdrant) | sémantique / rappel flou | REX, runbooks, "ce qu'on a appris" |
| Graphe (nouveau) | structurel / relationnel | topologie, var-flow, provenance, multi-hop |

## 3. Architecture — module `scripts/memory/graph/`

| Fichier | Rôle |
|---|---|
| `graph_build.py` | scroll `memory_v2` → nœuds + arêtes méta ; + extracteurs ; + `similar_to` (recommend-by-id) → `graph.json` (+ shards/repo) |
| `varflow_extract.py` | extracteur **Ansible/Jinja** : `group_vars → role tasks → docker service → container`, refs `{{ var }}` (P2 prioritaire) |
| `ast_extract.py` | extracteur tree-sitter maison (py/ts/js/go/sh/sql) → `calls/imports/inherits` (P2 secondaire) |
| `rationale_extract.py` | extraction du "pourquoi" : `# NOTE/WHY/HACK`, `# REX-xx`, docstrings → nœuds 1ʳᵉ classe liés au code |
| `graph_query.py` | charge NetworkX → `get_node / get_neighbors / shortest_path / query_subgraph` |
| `graph_mcp.py` | serveur MCP **stdio** (waza) exposant `graph_query` |
| `querylog.py` | log JSONL des requêtes graphe (question / nœuds / durée) |
| (réutilise `memory_core.py`) | client Qdrant + helpers existants |

## 4. Modèle de nœuds (collapse — PAS 1 nœud/chunk)

Les vecteurs vivent au niveau **chunk** (`chunk_size: 1600`). Les nœuds sont collapsés :

| Type | id | porte |
|---|---|---|
| Fichier | `repo:relative_path` | `doc_kind`, `qdrant_point_ids[]` |
| Symbole | `repo:path:Symbol` | `source_location` (AST) |
| Topic | `topic:<name>` | — |
| Doc/REX | `repo:path#section` | — |
| Rationale | `repo:path#why@Lxx` | texte de la raison, lien vers le code |
| Var (Ansible) | `var:<name>` | scope (group_vars/role) |

**IDs Qdrant stables** : `memory_core.py:728` →
`str(uuid.UUID(sha256_text(f"{ref_id}:{chunk_index}:{chunk_text}")[:32]))`.
Hash de contenu → même texte = même ID après ré-ingest → **back-pointers survivent**
→ **rebuild incrémental viable** (pas de full re-link).

## 5. Modèle d'arêtes — typées + confidence

| relation | source | confidence |
|---|---|---|
| `contains` (repo→file→symbol/section) | métadonnées payload | EXTRACTED |
| `tagged` (node→topic) | payload `topic` | EXTRACTED |
| `defines_var` / `uses_var` (Ansible) | `varflow_extract` | EXTRACTED |
| `calls` / `imports` / `inherits` | `ast_extract` (tree-sitter) | EXTRACTED |
| `explains` (rationale→code) | `rationale_extract` | EXTRACTED |
| `references` (`[[wikilink]]`, cross-ref exact) | regex exact | EXTRACTED |
| `references` (mention chemin floue) | regex flou | INFERRED |
| `similar_to` | Qdrant recommend-by-id, score≥τ_high | INFERRED ; τ_low<s<τ_high = AMBIGUOUS ; <τ_low jeté |

La confidence est **exposée dans la sortie MCP** → l'agent sait certain-vs-deviné
(le gain de provenance).

### Génération de `similar_to` (contrainte critique)

`embeddinggemma` est **asymétrique** (`query_prompt_name: "Retrieval-query"` ≠ prompt
document utilisé à l'ingest). Re-embedder le texte d'un nœud via le chemin *query*
corromprait toutes les arêtes doc-à-doc.

→ `similar_to` se génère **exclusivement** via **Qdrant recommend / query-by-point-id**
sur les **vecteurs document stockés** :

1. kNN au niveau **point/chunk** (recommend-by-id, k=5–8, server-side sur sese).
2. **Agréger** les voisins-chunks en arêtes **fichier↔fichier** (poids = agrégat des
   similarités de paires de chunks). **Jamais** de mean-pool des vecteurs fichier (lossy).

**Seuils `τ_high` / `τ_low`** : valeur de départ P1 `τ_high=0.78`, `τ_low=0.62`
(cosinus sur vecteurs normalisés), à calibrer sur le benchmark P4. Exposés en config
(pas en dur) pour ajustement sans rebuild de code.

Conséquence : l'ANN reste **server-side Qdrant** → 0 vecteur tiré sur le Pi,
0 cosine local ARM → tue le coût "23k recherches" et la crainte ARM.

## 6. Flux

```
WAZA (extract, offline + idle-gated comme le worker — loadavg_threshold)
  scroll memory_v2 ─────────┐
  varflow_extract (Ansible) ┤
  ast_extract (code) ───────┼─> graph_build.py ─> graph.json (+ shards/repo, committé)
  rationale_extract ────────┤
  recommend-by-id (sese) ───┘   (similar_to agrégé chunk→file)

WAZA (serve, local)
  graph_mcp.py stdio ──> Claude Code / R0

R0 hook (waza)
  qdrant-find (vecteur) ─> top hits ─> get_neighbors 1-2 hops typés ─> append contexte
  save-result : Q&A réinjecté comme nœud ─> prochain rebuild l'extrait (boucle fermée)
```

**HTTP sese différé** : R0 tourne sur waza → stdio local suffit. Le serveur MCP HTTP
sur sese (+Caddy ACL 2 CIDRs +api-key) est **hors scope** tant qu'aucun consommateur
sese concret (OpenClaw/n8n/équipe) n'est prouvé.

## 7. Corpus

Multi-repo : **tout ce qui est dans `memory_v2`** (repos déclarés dans
`sources.yml` / `config.yml`), pas un repo isolé.

## 8. Placement des fichiers + déploiement (LOI / manifeste)

**Décision : extension du rôle existant `roles/llamaindex-memory-worker/`** — pas de
nouveau rôle. Le graphe partage venv, config Qdrant, timer et `memory_core.py` du worker.

### Source de vérité (committée, repo VPAI)

Même emplacement que `memory_core.py` (cf `scripts/memory/`) :

```
scripts/memory/graph/
  graph_build.py        graph_query.py      querylog.py
  varflow_extract.py    ast_extract.py      rationale_extract.py
  graph_mcp.py          test_*.py           (fixtures/)
```

### Déploiement via le rôle worker (mirror du pattern `memory_core.py`)

| Fichier rôle | Action |
|---|---|
| `roles/llamaindex-memory-worker/tasks/main.yml` | + tâches `ansible.builtin.copy` de `{{ role_path }}/../../scripts/memory/graph/*.py` → `{{ memory_worker_install_dir }}/graph/` (idempotent, comme la tâche `memory_core.py` existante L82-90) |
| `templates/graph-build.service.user.j2` + `.timer.user.j2` | systemd-user waza, **déclenché après** le cycle d'ingest worker (chaîné via `run-and-report.sh.j2` ou `OnUnitInactiveSec`) |
| `defaults/main.yml` | + `memory_worker_graph_dir`, seuils `τ`, k kNN |
| `templates/requirements.txt.j2` | + deps tree-sitter (versions **pinnées**) |
| `roles/claude-code/templates/mcp.json.j2` | + entrée MCP **stdio** `graph` → `graph_mcp.py` (consommée par R0/Claude Code sur waza) |

### Conventions imposées (manifeste)

- **Tags** : `[llamaindex-memory-worker, memory_remote]` sur chaque tâche (parité avec
  l'existant — pas de tag inventé).
- **FQCN** (`ansible.builtin.*`) + `changed_when`/`failed_when` explicites + `copy`
  idempotent (0 changed au 2ᵉ run).
- `set -euo pipefail` + `executable: /bin/bash` sur tout bloc `shell`.
- Deps tree-sitter **pinnées** dans `inventory/group_vars/all/versions.yml` (jamais flottant).
- **R7** : Tailscale only — accès Qdrant `qd.ewutelo.cloud` via VPN.
- Idle-gate : réutilise `memory-wait-calm.sh` / `loadavg_threshold` du worker.

## 9. Tests (R4 sibling-first)

- **P0 bloquant** : valider les wheels **tree-sitter ARM64** sur waza. Échec →
  bascule extracteur (ou AST repoussé).
- Unit : `varflow_extract` (fixtures Ansible), `ast_extract` par langage, typage
  d'arêtes, banding confidence, `shortest_path`. `scripts/memory/graph/test_*.py`.
- Intégration : graphe depuis repo fixture + scroll Qdrant mocké + recommend mocké →
  asserts counts nœuds/arêtes + requêtes path.

## 10. Phasage

| Phase | Livre | Gate |
|---|---|---|
| **P0** | pré-requis P2 : valider wheels tree-sitter ARM64 sur waza (§9). Échec → bascule extracteur | bloque P2 |
| **P1** | modèle nœuds/arêtes + graphe Qdrant-derived (méta + `similar_to` recommend-by-id) + `graph_query` + **query log** + tests | — |
| **P2** | **`varflow_extract` Ansible/Jinja D'ABORD** (`defines_var`/`uses_var`), puis `ast_extract` code (`calls`/`imports`) | — |
| **P3** | `graph_mcp` stdio waza + hook R0 (`get_neighbors`) + `save-result` + `rationale_extract` | — |
| **P4** | **GATE DUR** : benchmark (méthode `benchmark.py` de graphify : tokens lecture corpus brut **vs** subgraph servi) sur un jeu de questions relationnelles. **Cible** : **−70 % de tokens** (référence annoncée graphify), **plancher d'acceptation ≥−50 %**, **ET** ≥+15 % de rappel multi-hop, **sans** régression du rappel flou. Sous le plancher → P5-P6 ré-évalués | **bloque P5-P6** |
| **P5** | god-nodes/centralité + communautés (Leiden) → affine `topic` ; **affected** (`var→role→service`) ; benchmark token | conditionné P4 |
| **P6** (option) | `pg_introspect` (schéma DB n8n, douleur R10) ; `mcp_ingest` (MCP orphelins) ; wiki/callflow Mermaid ; merge-driver union `graph.json` | conditionné P4 |

## 11. Features volées à graphify (récap)

**Retenues** : arêtes typées · confidence labels · shortest-path · extraction "pourquoi" ·
affected/impact (retargeté Ansible) · save-result loop · query log · god-nodes/communautés ·
benchmark token · (P6) pg_introspect · mcp_ingest · wiki/callflow · merge-driver.

**Laissées (YAGNI VPAI)** : transcribe (déjà content-factory) · PR triage dashboard
(équipe solo) · exports Neo4j/Gephi/SVG/Obsidian · 28 langages (limité aux nôtres) ·
watch.py (timer worker suffit) · HTTP serve sese (pas de consommateur).

## 12. Risques

| Risque | Mitigation |
|---|---|
| Wheels tree-sitter ARM64 | validation P0 bloquante avant P2 |
| Explosion arêtes `similar_to` | cap k=5–8 + seuil τ_low, recommend-by-id server-side |
| Coût scroll/kNN sur 23k points | batch, gate loadavg (comme worker), ANN server-side sese |
| Fraîcheur graphe vs drift `memory_v2` | rebuild incrémental (IDs hash-contenu) sur cycle worker |
| Hypothèse non prouvée (graphe > vecteur seul) | **P4 gate dur** avant tout effort P5-P6 |
| `affected` n'émerge pas de l'AST code | extracteur var-flow Ansible dédié (C4) |
