# Seed — SIRA (facebookresearch/sira) vs notre RAG memory_v3 — 2026-07-22

Question opérateur : « ce repo serait-il un plus pour notre RAG actuel ? »
Analyse menée par 2 scouts (repo+papier / stack locale). Verdict ci-dessous.

## 1. Ce qu'est SIRA (faits établis)

SuperIntelligent Retrieval Agent (Meta/FAIR, arXiv 2605.06647, MIT + Apache2 pour `bm25x`).
Pipeline 5 étapes, **inference-time compute uniquement** (zéro entraînement), SOTA BEIR.
Code de recherche Python+Rust servi par sglang sur **8×H100** — pas une lib installable.

| Étape | Appels LLM | Source |
|---|---|---|
| Corpus enrichment (≤10 phrases de 1-4 mots par doc) | **1 / doc** | `scripts/add_doc_index_adapter.py:229-248`, `enrich/prompts/doc_v07.txt` |
| Query expansion | **1 / requête** | `scripts/enrich_query_and_retrieve.py:216-233` |
| Reranking pointwise | **200 / requête** (`top_n: 200`, 1 appel par candidat) | `scripts/llm_reranking.py:194-219`, `rerank/default.yaml:4` |

Modèle unique pour les 3 : `Qwen/Qwen3.6-35B-A3B-FP8` (MoE, 3B actifs).
Répartition du temps sur leur run d'exemple (`scripts/README.md:38-47`) :
enrich_corpus 131,2 s / enrich_query 20,5 s / **rerank 469,1 s** = 76 % du total.
Ni le papier ni le repo ne publient de coût $ ni de latence par requête.

## 2. Confrontation à nos contraintes

| Contrainte | Effet |
|---|---|
| Cap IA **$5/jour** (LiteLLM `max_budget`) | tue tout coût **par requête** |
| Recherche interactive Pi5 (~3-5 s budget) | tue le rerank : notre bge-reranker ONNX int8 est déjà OFF pour **+9,8 s médiane** (`search_memory.py:14-19`) — SIRA propose 200 appels LLM à la place |
| GPU = pod RunPod éphémère uniquement | un coût **à l'ingestion** est amortissable (pattern déjà prouvé : 24 403 chunks embarqués en 17 min sur RTX 4090) |

→ Ligne de partage : **ingestion (amortissable) vs requête (récurrent)**.
Sur les 3 briques SIRA, **seul le corpus enrichment tombe du bon côté**.

## 3. Séparabilité — la brique est-elle détachable ?

**Oui, techniquement.**
- Les 3 étapes sont 3 CLI indépendants avec leur propre éval (`stages='[enrich_corpus]'`, `scripts/README.md:20`).
- Sortie de l'enrichment = **texte pur** : `{doc_id: [phrase, ...]}`.
- `bm25x.enrich_batch()` (Rust, `src/sira/bm25x/src/index.rs:2148-2240`) = fonctionnellement « concaténer le texte au doc et ré-indexer ». **Aucune dépendance dure au BM25 Rust** : réinjectable dans n'importe quel index sparse, Qdrant idf inclus.
- Prompts en clair (25-28 lignes), appel LLM = `POST /v1/chat/completions` OpenAI-compatible (`src/sira/llm.py:13-30`) → **pointable sur notre LiteLLM ou un pod local**. Client réimplémentable en ~50 lignes.

**Mais** : le papier ne publie **aucune ablation isolant le corpus enrichment** sur les 10 BEIR (Table 2 = pipeline complet, une seule ligne). La seule ablation proche (§4.4) *retire* l'enrichissement et ne concerne que BrowseComp-Wikipedia. **Le gain de la brique seule n'est chiffré nulle part** — ni par eux, ni a fortiori sur notre corpus.

## 4. Point d'injection dans memory_v3 (identifié)

- Vecteur sparse calculé sur `f"{relative_path} {section} {chunk_text}"` — `memory_core.py:651-658` (`build_sparse_text`). **Une fonction à modifier**, c'est tout.
- Le payload stocké garde `text` = chunk brut (invariant `node_id`) ; **aucun champ libre existant** → ajouter un champ dédié aux phrases générées, ne jamais toucher `chunk_text`.
- Aucune expansion de requête n'existe côté recherche (requête brute vers dense et sparse) — vérifié par grep exhaustif.

## 5. Ordre de grandeur du coût d'enrichissement (estimation, à valider)

Hypothèses : `chunk_size: 1600` car ≈ 400 tok, prompt doc_v07 ≈ 300 tok, sortie ≤10 phrases courtes ≈ 80 tok.
≈ **700 tok in / 80 tok out par chunk**.

> ⚠️ **Correction 2026-07-22** : le corpus n'est pas de ~30 k chunks mais de **88 720 points**
> (`GET /collections/memory_v3`, vérifié en direct). Le backfill est donc **≈ 62 M tok in /
> 7 M tok out**, soit ~3× l'estimation initiale. Restreint au code seul (cible corrigée §8),
> le volume reste à établir.
Deux voies : (a) LiteLLM sur modèle éco — impacte le cap $5/j, à étaler ; (b) **pod GPU éphémère** avec modèle local — hors cap, coût = heures de pod (pattern déjà prouvé pour l'embedding).
Coût récurrent ensuite = 1 appel par nouveau chunk du delta (worker incrémental) → **fail-open obligatoire** dans le chemin d'ingestion.

## 6. Verdict

| | |
|---|---|
| **Adopter SIRA en bloc** | **NON.** Rerank 200 appels/requête + expansion 1/requête = coût récurrent contre un cap de $5/jour, sur un Pi où +9,8 s de rerank local est déjà jugé rédhibitoire. Code de recherche H100, pas une dépendance. |
| **Emprunter le corpus enrichment** | **Piste plausible mais à espérance réduite, et non prouvée.** Séparable, réinjectable, ~50 lignes + un prompt MIT à copier — mais voir la décote ci-dessous. |

### Décote hybride — la raison principale d'être sceptique

Le SOTA de SIRA est mesuré sur du **BM25 seul**. Le travail du corpus enrichment est de corriger
le décalage lexical question/document — c'est-à-dire **précisément ce que notre branche dense
(embeddinggemma) fait déjà**. Dans un système dense+sparse fusionné, un enrichissement purement
lexical a beaucoup moins à apporter que dans le monde-benchmark de SIRA : la branche sémantique
récupère déjà les documents à vocabulaire décalé. C'est vraisemblablement pourquoi notre
`recall@5` plafonne déjà à **0,9775**. Le gain publié par SIRA **ne se transfère pas tel quel**.

### Ce que l'enrichissement peut / ne peut pas viser chez nous

- `recall@5 = 0,9775` → il ne reste que **2,25 % de marge de rappel**. L'enrichissement est
  d'abord un **levier de rappel** (faire entrer le doc dans l'ensemble candidat) : sa cible
  naturelle est presque épuisée.
- `recall@1 = 0,6629` → l'écart « dans le top-5 mais pas premier » est un problème de
  **classement**, dont l'outil canonique est le reranking, pas l'enrichissement.

**Côté rerank et expansion de requête, rien à emprunter à SIRA** — mais notre propre reranker
n'est pas catégoriquement mort : le benchmark +9,8 s médiane portait sur **20 candidats**
(`search_memory.py:14-15`), soit ≈ 0,49 s/paire. Reranker seulement le top-5 (suffisant quand
`recall@5 = 0,98`) ramènerait à ≈ 2,5 s — toujours au-dessus du budget mais d'un facteur ~1,7,
pas ~6,5. Le site d'appel passe aujourd'hui **tous** les candidats retenus au reranker
(`search_memory.py:340`), pas un top-k réduit. Piste distincte, à ne pas confondre avec SIRA.

## 7. Spike proposé (bornable, mesurable)

Le harness golden-89 rend la question décidable au lieu d'arbitrable :

1. Enrichir un **sous-ensemble à forte valeur** (docs/runbooks/REX, pas le code) → collection `memory_v3_enriched`.
2. A/B avec la commande existante :
   ```
   run_eval.py --collection memory_v3          --mode hybrid --fusion dbsf --exact --out A.json
   run_eval.py --collection memory_v3_enriched --mode hybrid --fusion dbsf --exact --out B.json --baseline A.json
   ```
3. Critères, sur les questions dont la cible est dans le sous-ensemble enrichi :
   - **Signal GO primaire = `mrr@10`** (métrique sensible au classement, seule capable de
     capter un effet là où le rappel est déjà saturé).
   - **Signal de rappel = le miss-set de `recall@5`** (les ~2,25 % actuellement hors top-5) :
     est-ce que l'enrichissement en récupère ?
   - **Garde-fous** : aucune régression `recall@1` ni `recall@5`.
   Piloter la décision sur `recall@1` seul mesurerait le mauvais effet.

Sans ce chiffre, personne (pas même le papier) ne peut dire si ça vaut le coût.

## 8. Décision opérateur — 2026-07-22

**Concept gardé, implémentation NON lancée.** Raisons : plafond de rappel à 2,25 pts, décote
hybride (§6), et trois leviers de classement déjà codés au backlog avec un meilleur ratio
(rerank top-5, `--boost-usage`, scope boost).

**Correction de cible** (invalide la reco initiale du §7) : viser **le code** (`.py/.js/.yml`),
pas les docs. Les docs sont déjà en prose et couvertes par le dense ; un chunk de code n'a
aucune prose et le sparse n'y matche que des identifiants — c'est le seul endroit où notre
index lexical est structurellement aveugle.

**Forme d'activation retenue : par cycle, pas en ligne dans l'ingestion.** L'enrichissement
n'est PAS à greffer dans le chemin du worker incrémental (1 appel LLM par chunk à perpétuité,
fail-open à écrire, latence d'ingestion). Il se greffe sur un **passage de retraitement
périodique déjà existant** — batch, hors ligne, rejouable, sans impact sur la recherche
interactive. Cadence et point d'accroche exact : §9.

## 9. Point d'accroche par cycle — le précédent existe déjà

Inventaire des cycles `memory_v3` sur waza (re-vérifié `systemctl --user list-timers`, 2026-07-22) :

| Unité | Cadence réelle | Rôle |
|---|---|---|
| `llamaindex-memory-worker.timer` | 30 min (`OnUnitActiveSec`) | ingestion incrémentale + `--gc` |
| `memory-worker-watchdog.timer` | 15 min | sonde stagnation, alerte 27 h |
| `memory-eval-golden.timer` | `Sun 02:00` +15 m → **dim 02:05** | éval golden-89, gate `--assert-thresholds` |
| `memory-consolidate-rex.timer` | `Sun 04:30` +15 m → **dim 04:41** | consolidation REX **via LiteLLM** |

**Aucun script de reclassement / retag / repatch de points n'existe** (confirmé absent).

### Le précédent à cloner : `consolidate_rex.py`

`/opt/workstation/ai-memory-worker/consolidate_rex.py` fait **déjà exactement** ce dont
l'enrichissement SIRA a besoin — vérifié dans sa docstring (`:1-18`) :

- hebdo, batch, hors ligne, `MemoryMax=1G` (aucun embed) ;
- appelle **LiteLLM** (`LITELLM_BASE_URL` = `https://llm.ewutelo.cloud/v1`, `LITELLM_MODEL` =
  `claude-haiku`, modèle économique explicitement choisi pour le cap budget) ;
- **idempotent par mtime** — un topic est sauté si sa synthèse est plus récente que toutes ses
  sources ; `--force` regénère, `--dry-run` existe ;
- écrit des **fichiers markdown** dans `docs/memory-consolidated/` que **le worker indexe
  ensuite comme n'importe quel doc**, avec frontmatter `consolidated: true` + `sources: [...]`.

### Ce que ce patron résout gratuitement

| Objection soulevée en §8 | Levée par le patron consolidate_rex |
|---|---|
| « 1 appel LLM par chunk à perpétuité » | **faux si cycle** : l'idempotence mtime ne retraite que les fichiers **modifiés**. Après backfill initial, le coût hebdo est marginal |
| « fail-open à écrire dans l'ingestion » | inutile : le job est **hors** du chemin worker. S'il échoue, le worker indexe ce qui existe |
| « modifier `build_sparse_text`, risque de casser la parité worker/pod/requête » | inutile : les phrases deviennent des **fichiers indexés normalement**, zéro chirurgie sur le worker |
| rollback | `rm -rf` du dossier + le `--gc` du worker purge les points orphelins au tick suivant |

**Contrepartie assumée** : un hit tombe sur le fichier de phrases, pas sur le chunk de code
lui-même — il faut que `relative_path` de la source soit porté en tête (comme `sources:` des REX
consolidés) pour que le résultat pointe vers le bon fichier. C'est le compromis déjà accepté
pour les REX consolidés, pas une nouveauté.

### Cadence recommandée : **hebdomadaire, pas mensuelle**

- Le code change tous les jours ; en mensuel l'index lexical retarderait de 4 semaines.
- Créneau : dimanche, **après** `memory-consolidate-rex` (04:41) — p. ex. `Sun 05:30`.
- Rythme d'A/B naturel : ce qui est écrit dimanche 05:30 est indexé par le worker dans les
  30 min, et **mesuré par l'éval golden du dimanche suivant 02:05**. Une semaine baseline,
  une semaine enrichie, même harnais, même gate.
- Backfill initial (le vrai coût, ~21 M tok) : one-shot, hors cycle — pod GPU ou étalement
  LiteLLM sur plusieurs nuits, jamais dans le tick hebdo.

## Inconnues assumées

- Gain du corpus enrichment isolé : non publié, non mesuré chez nous.
- Coût $/temps GPU réel d'un enrichissement à notre échelle : estimation seule (§5).
- Le stage `rerank` figure dans le pipeline du repo mais **n'apparaît dans aucune des deux versions du papier** — non élucidé.
