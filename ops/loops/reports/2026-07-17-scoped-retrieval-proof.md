# REX — Retrieval scopé par métadonnée (repo/wing/topic) vs recherche globale

**Date** : 2026-07-17
**Collection** : `memory_v3` (83 212 points, dense embeddinggemma-300m 768d + sparse BM25, fusion DBSF)
**Harnais** : `scripts/memory/eval/run_eval.py` (étendu — cf §Implémentation) + `scripts/memory/eval/golden.yml` (76 questions)
**Protocole** : DBSF + `exact=True` sur les 4 variantes (élimine le bruit d'approximation HNSW, cf docstring `run_eval.py`)
**Résultats bruts** : `.planning/eval/eval-memory_v3-hybrid-scoped-{global,repo,wing,topic}-20260717T235500Z.json` + `.planning/eval/oracle-scope-derivation-20260717T235500Z.json`

## Question

Le retrieval SCOPÉ par filtre Qdrant (repo/wing/topic) restaure-t-il le recall@1 par
rapport à la recherche globale actuelle, et à quel coût honnête (filtre-miss) ?

## 1. Schéma et cardinalités (confirmé live)

Payload memory_v3 porte bien `repo`, `wing`, `topic` (+ `room`, `doc_kind`, `tags`), tous
indexés keyword (`payload_indexes` de config.yml, vérifié `client.facet()`).

| Champ | Cardinalité distincte | Distribution |
|---|---|---|
| `wing` | 4 (`infra`, `saas`, `refdocs`, `tools`) | infra=8941, saas=47249, refdocs=26602, tools=420 |
| `repo` | 29 | VPAI=8410, n8n-docs=9035, litellm-docs=11310, … |
| `topic` | **2698** (limite sonde 5000, non tronquée) | médiane **12** points/topic, 263 topics à 1 seul point, 453 à ≤3 points |

`topic` est en pratique une granularité **quasi fichier** : sonde sur `VPAI:docs/TROUBLESHOOTING.md`
(156 chunks, ~40 sections distinctes couvertes par le golden set) → **1 seul** topic
(`"TROUBLESHOOTING.md — Pieges Connus et REX"`), homogène sur tout le fichier. Vérifié
sur les 76 questions golden : **0 fichier hétérogène** en interne (topic dérivé du titre,
pas de la section). `wing` est homogène par repo par construction (`sources.yml`).

## 2. Oracle (plafond)

Pour chaque question, dérivation du repo/wing/topic à partir des `expected_paths` (scroll
Qdrant filtré `repo=X AND relative_path=Y`, lecture seule). **76/76 expected_paths résolus
en ≥1 point** (0 gap oracle).

Le filtre-oracle utilisé est l'**union** des valeurs sur tous les `expected_paths` d'une
question (ex. question à 2 fichiers de topics différents → `MatchAny([topic_a, topic_b])`).
C'est le plafond correct : le meilleur filtre qu'un système omniscient pourrait construire.
**Par construction, ce filtre ne peut jamais exclure la bonne réponse** — le filtre-miss
empirique (vérifié via `client.count()` avant toute recherche vectorielle, indépendamment
du classement retourné) est donc structurellement nul pour les 3 granularités, et c'est
bien ce qui est mesuré (§4).

**Biais majeur du golden set** : 75/76 questions ont un `expected_paths` **exclusivement
VPAI** ; 1 seule question touche aussi `n8n-docs` (doc officielle dupliquée). Le scoping
repo/wing n'est donc quasiment jamais mis à l'épreuve du cross-repo par ce golden set —
le coût mesuré ici (0% miss) est probablement **sous-estimé** pour un usage réel où un
agent dans VPAI pose une question dont la vraie réponse vit dans `litellm-docs` ou
`openclaw-docs` (wing `refdocs`).

## 3. Mesure — 4 variantes (76 questions, DBSF, exact=True)

| Variante | recall@1 | recall@5 | mrr@10 | filtre-miss (honnête) |
|---|---|---|---|---|
| **GLOBAL** (contrôle) | **0.6711** | 0.9737 | 0.7939 | n/a |
| SCOPÉ REPO (oracle union) | **0.7500** | 0.9868 | 0.8547 | **0.0000** (0/76) |
| SCOPÉ WING (oracle union) | **0.7500** | 0.9868 | 0.8536 | **0.0000** (0/76) |
| SCOPÉ TOPIC (oracle union) | **1.0000** | 1.0000 | 1.0000 | **0.0000** (0/76) |

Contrôle GLOBAL = **0.6711**, identique au chiffre de référence cité dans le protocole →
le harnais est sain (sibling test byte-identique confirmé, cf §Implémentation).

Le gain repo/wing est **strictement monotone** : sur les 6 questions qui basculent
(rank≠1 en global → rank=1 en scopé), **aucune** ne régresse en sens inverse (0 question
où global=1 devient scopé≠1). Exemples de bascules : *"Which volume mount path does
PostgreSQL 18 use…"*, *"Caddy crash loop unrecognized directive: 200…"*, *"n8n IF node
typeVersion 2 crashes…"* — toutes des questions exact-match où le bruit du corpus à 83k
points (dont 47k `saas`, hors sujet infra) noyait le bon chunk hors du rang 1.

REPO (mrr@10=0.8547) légèrement > WING (0.8536) : cohérent — `wing` agrège plusieurs
`repo` (le pool `refdocs` scopé pour la question mixte VPAI+n8n-docs est ~35k points vs
~17k pour le pool `repo`-scopé), donc `repo` est structurellement plus précis que `wing`.

## 4. Réalisme — le filtre est-il dérivable en pratique ?

**repo/wing — OUI, trivialement.** Le CWD de l'agent (`~/work/infra/VPAI`) donne
`wing=infra` (dossier parent) et `repo=VPAI` (basename) directement, sans inférence —
c'est exactement la règle déjà documentée dans `MEMORY-TAXONOMY-MANIFEST.md` (`wing` =
assigné par source dans `sources.yml`, homogène par repo). Aucune nouvelle brique à
construire.

**topic — NON, pas avec l'outillage existant.** Comparaison directe des deux taxonomies :

- `topic-extract.js` (hook R0, `~/.claude/hooks/lib/topic-extract.js`, lu en lecture
  seule, fonction pure `extract()` appelée sans écrire son cache) produit, sur VPAI, des
  tokens **mono-mot dérivés de la structure du repo** (noms de `roles/*/`, dépendances,
  services docker-compose, noms de fichiers `REX-*`) : `["caddy", "docker", "disk-guard",
  "diun", "firefly", "ansible-lint", "molecule", …]`.
- Le `topic` du payload Qdrant est une **phrase-titre par document**, dérivée à
  l'ingestion : `"TROUBLESHOOTING.md — Pieges Connus et REX"`,
  `"Guide — Mise sous VPN d'un Caddy en Docker (Headscale/Tailscale)"`,
  `"n8n nodes base.code"`.

Ce sont deux taxonomies **structurellement disjointes** (granularité repo vs document,
vocabulaire mono-token vs phrase). Un `FieldCondition(topic=MatchValue("caddy"))` construit
depuis la sortie de `topic-extract.js` ne matchera **jamais** le payload réel, même quand
le token est sémantiquement pertinent (`"caddy"` ⊂ `"Guide — Mise sous VPN d'un Caddy…"`
mais pas égal). Le plafond topic (recall@1=1.0000) est donc **réel mais inatteignable
en l'état** sans un nouveau composant d'alignement (dérivation du topic-titre depuis la
requête, ou matching flou/substring au lieu d'exact-match) — c'est un chantier à part,
pas une bascule de config.

## 5. Verdict chiffré

| Granularité | Gain recall@1 | Coût mesuré | Dérivable aujourd'hui ? | Verdict |
|---|---|---|---|---|
| REPO | +8.9 pts (0.6711→0.7500) | 0% miss (mais sous-mesuré, cf biais golden §2) | Oui (CWD) | **PROBANT, actionnable immédiatement** |
| WING | +8.9 pts (identique ici) | 0% miss (idem) | Oui (CWD) | Probant, mais strictement ≤ REPO (agrège plus large) — préférer REPO |
| TOPIC | +32.9 pts (0.6711→1.0000) | 0% miss (oracle) | **Non** — taxonomie incompatible avec `topic-extract.js` | Plafond réel, **non actionnable** sans nouveau chantier d'alignement |

**Verdict global : PROBANT pour le scoping REPO** (avec WING en repli si le CWD ne
mappe pas franc à un seul repo). Seuil du protocole (≥0.72) largement dépassé (0.75).
Le scoping TOPIC prouve qu'il existe encore ~25 points de recall@1 sur la table
(0.75→1.00) mais ce gain reste **hors de portée sans construire l'alignement de
taxonomie** — à traiter comme piste future, pas comme partie de ce chantier.

**Recommandation de granularité** : construire le scoping **repo** (dérivé du CWD),
avec repli sur **wing** si l'agent n'est pas dans un repo précis (session multi-repo,
recherche transverse). Avant d'industrialiser, étoffer `golden.yml` avec des questions
**volontairement cross-repo** (le set actuel est VPAI-only à 75/76 — le 0% de
filtre-miss mesuré ici est optimiste, pas une garantie de production).

## Pièges rencontrés

1. **`filtre-oracle union` = filtre-miss structurellement nul.** Une première approche
   envisagée (oracle "primaire seul", 1er `expected_path`) aurait semblé produire un
   signal de coût, mais reste tout aussi structurellement nulle (le doc primaire est
   toujours dans son propre scope) — vérifié par raisonnement avant de lancer les runs
   (relecture avant exécution, cf `advisor()`). Le vrai coût n'apparaît qu'à la dérivation
   **réaliste** (query-derived), pas à l'oracle — d'où le §4 qualitatif plutôt qu'un
   5ème run chiffré.
2. **`filter_miss_rate` a été vérifié empiriquement** (pas seulement déduit par
   construction) via `client.count()` sur chaque `expected_path` sous le filtre AVANT
   la recherche vectorielle — les 3 variantes scopées confirment `0/76` en pratique, pas
   seulement en théorie.
3. **HNSW filtré** : non observé dans cette mesure (protocole `exact=True` partout,
   contrat explicite). Note pour un futur run en production (approximatif) : les pools
   topic-filtrés sont très petits (médiane 12 points) — Qdrant bascule probablement déjà
   en scan exact sous son `full_scan_threshold` interne à cette taille, donc le risque de
   sous-performance HNSW-filtré est plus pertinent pour le scoping repo/wing (pools de
   milliers de points) que pour topic. À vérifier si le scoping repo passe en prod
   interactif (non-exact).
4. **Latence `search_s`** : scoping repo/wing quasi triple la latence de recherche
   (5.4s→16-17s pour 76 requêtes globales, encore ~0.2s/requête — négligeable côté
   agent interactif) — coût du filtre Qdrant côté serveur, pas un problème en pratique.

## Implémentation (extension additive, sibling test passé)

`scripts/memory/eval/run_eval.py` étendu avec `--scope-file`/`--scope-field`
(filtre Qdrant **par question**, appliqué aux deux canaux du prefetch hybrid comme
`search_memory.py`) + vérification empirique `in_scope` via `client.count()`. Comportement
par défaut (sans ces flags) **byte-identique** à avant — sibling test rejoué : rejeu du
script original vs script patché, mêmes flags `--fusion dbsf --exact`, mêmes 76 questions
→ `recall@1=0.6711 / recall@5=0.9737 / mrr@10=0.7939` identiques au chiffre près
(cf `.planning/eval/eval-memory_v3-hybrid-scoped-global-20260717T235500Z.json`).
