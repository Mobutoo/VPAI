# Point — Couche graphe memory_v2 : design figé, placement EN ATTENTE

> Statut : design approuvé + spec écrite/committée. **2 décisions ouvertes** avant writing-plans.
> Spec : `docs/superpowers/specs/2026-06-07-memory-graph-layer-design.md` (commit `fe95b42`)
> Origine : analyse `safishamsi/graphify` vs notre mémoire Qdrant `memory_v2`.

## Ce qui est DÉCIDÉ (verrouillé en spec)

- **Quoi** : couche graphe de connaissances AU-DESSUS de `memory_v2` (complète, ne remplace pas).
  3 features cœur + extras volés à graphify : arêtes typées · confidence labels (EXTRACTED/
  INFERRED/AMBIGUOUS) · shortest-path · extraction "pourquoi" · affected/impact · save-result
  loop · query log · god-nodes/communautés · benchmark token.
- **Arêtes** : `contains/tagged/defines_var/uses_var/calls/imports/explains/references/similar_to`.
- **`similar_to`** : via Qdrant **recommend-by-id** sur vecteurs doc stockés (embeddinggemma
  asymétrique → jamais re-embedder le texte du nœud). kNN chunk-level → agrégé en arêtes fichier.
  Seuils départ `τ_high=0.78 / τ_low=0.62`.
- **Nœuds** : collapse file/symbol/topic/section/rationale/var, back-pointer `qdrant_point_ids[]`.
  IDs Qdrant = hash-contenu (`memory_core.py:728`) → rebuild incrémental viable.
- **Extracteur** : tree-sitter maison (py/ts/js/go/sh/sql) ; **var-flow Ansible/Jinja prioritaire**
  sur l'AST code (l'« affected » `var→role→service` n'émerge PAS de l'AST code — correction advisor).
- **Hôte** : extract waza, serve **stdio waza** (HTTP sese différé, pas de consommateur).
- **Phasage** : P0 (wheels ARM) · P1 graphe Qdrant-derived + query log · P2 var-flow puis AST ·
  P3 MCP stdio + hook R0 + save-result + rationale · **P4 GATE DUR** (cible **−70 % tokens**,
  plancher −50 %, +15 % rappel multi-hop) · P5-P6 conditionnés P4.

## Décisions OUVERTES (à discuter plus tard)

### D1 — Placement source (lié à la vision d'extraction)

`.planning/notes/2026-06-06-memory-tool-extraction-vision.md` planifie de sortir TOUT le système
mémoire de VPAI vers un **repo dédié agnostique dockerisé** `memory-tool/` (`core/worker/bulk/
qdrant/`), en session/projet séparé. La vision liste à abstraire : **taxonomie wing/room** ET
**rôle Ansible**. → mettre `graph/` dans VPAI ajoute du couplage juste avant l'extraction.

| Option | Résumé | Tradeoff |
|---|---|---|
| **A (reco)** | `scripts/memory/graph/` **agnostique** (config-driven, 0 wing/room en dur), ajouté aux « sources à reprendre » de la vision | livre maintenant, 0 friction, migre tel quel vers `memory-tool/graph/` le jour J |
| B | Bootstrap `~/work/tools/memory-tool/` maintenant ; graph/ = 1er module (graine extraction) ; VPAI le consomme | propre long-terme, mais tire l'extraction en avant + intégration worker actuel |
| C | Différer : extraction d'abord, graph/ ensuite comme module natif | 0 double travail, mais bloque le graphe derrière un plus gros chantier |

Topologie confirmée : `/opt/workstation/ai-memory-worker` = repo git **local sans remote** =
**cible de déploiement** (fichiers générés par le rôle, `search_memory.py` ≡ `.j2`). Source de
vérité = monorepo VPAI (`scripts/memory/` + `roles/llamaindex-memory-worker/templates/`).

### D2 — Taxonomie (CORRECTION, pas une option)

Ma spec ne modélisait que `topic`. Le worker écrit en réalité `wing` / `room` / `doc_kind` /
`topic` (payload `memory_core.py:494-499`, indexes `config.yml.j2:45-77`). → le modèle de nœuds
doit porter ces 4 dimensions + arêtes `tagged`, **filtrable par wing/room**, lecture **config-driven**
(depuis `payload_indexes`) — ce qui sert aussi l'agnosticité (option A/D1). À plier en spec quoi
qu'il arrive, avant writing-plans.

## Reprise (prochaine session)

1. Trancher D1 (placement) — dépend du timing extraction memory-tool.
2. Plier D2 (taxonomie wing/room/doc_kind/topic config-driven) dans la spec §2/§4/§5.
3. Re-spec-review si D1 change §8 (déploiement), sinon → **writing-plans** (plans GSD P0→P6).
