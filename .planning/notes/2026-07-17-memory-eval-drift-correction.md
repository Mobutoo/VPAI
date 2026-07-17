# Correction — cause de la dérive éval mémoire 2026-07-17

Complète/corrige le commit `57586e2` (`.planning/eval/eval-memory_v3-hybrid-full-2026-07-17.json`).

## Ce qui était affirmé (à tort)

Le message de commit `57586e2` avançait comme hypothèse principale : `golden.yml`
gelé sur l'arborescence pré-réorg, désormais désaligné avec les `relative_path`
réindexés après réorg/purge (2026-06-29, 95881→75438 pts).

**Cette hypothèse est réfutée par les chiffres eux-mêmes** :

| Métrique | Baseline 06-10 | Rejoué 07-17 | Delta |
|---|---|---|---|
| recall@1 | 0.7237 | 0.5921 | **-13.16 pts** |
| recall@5 | 0.9868 | 0.9737 | -1.31 pts |
| mrr@10 | 0.8432 | 0.7465 | **-9.67 pts** |

Un désalignement de chemins ferait sortir la question du top-5 entière →
`recall@5` chuterait au même rythme que `recall@1`. Or `recall@5` reste
quasi stable (-1.3 pt, cohérent avec les 2 MISS apparus) pendant que
`recall@1`/`mrr@10` s'effondrent. Signature = **régression de ranking**
(les bons documents restent récupérés dans le top-5, mais mal classés),
pas de bookkeeping de chemins.

## Piste retenue (non confirmée)

`encode_s` est passé de **116.97s → 21.06s** (5.5x plus rapide) sur les
mêmes 76 requêtes, sur le même Pi, **sous charge plus lourde** (swap
quasi plein, plusieurs sessions Claude actives) qu'au baseline.
L'encodage ne devrait pas accélérer sous charge — un encodeur de requête
plus rapide suggère un changement de chemin d'encodage/scoring côté
requête depuis le baseline (modèle, version de lib, ou paramètres).

## Vérifs faites cette passe (rapides, pas exhaustives)

- `scripts/memory/eval/run_eval.py` : le mode hybrid n'invoque PAS
  `rerank.py` (pas de cross-encoder ONNX dans le chemin d'éval) — écarte
  une contamination par reranker.
- `config.yml` embedding : `google/embeddinggemma-300m`, dim 768,
  `normalize_embeddings: true`, `query_prompt_name: "Retrieval-query"` —
  identique à la description mémoire du baseline (dense 768 cosine).
- `requirements.txt` worker (diff `eec9547`→`3d3aa2e`) : seul ajout
  `fastembed==0.8.0` (déjà requis pour le mode hybrid, probablement déjà
  installé au baseline qui tournait aussi en hybrid) ; range
  `sentence-transformers>=5.1,<5.2` inchangée.
- Versions installées dans le venv : `sentence-transformers 5.1.2`,
  `transformers 4.57.6`, `torch 2.11.0`, `fastembed 0.8.0`,
  `onnxruntime 1.26.0`. Pas de pip-freeze baseline disponible pour
  comparer — impossible de confirmer/infirmer un bump de patch dans la
  plage `5.1.x` ou une dépendance transitive (`transformers`, `torch`)
  qui aurait subtilement changé les embeddings sans casser le pin.

## Statut

**Root cause non confirmée.** Dérive réelle (pas du bruit), signature
ranking pas bookkeeping. À creuser dans une passe dédiée (hors périmètre
de cette tâche A7) : comparer un pip-freeze figé au 2026-06-10 (si
disponible) au freeze actuel ; ou rejouer le baseline dense-only pour
isoler si la régression vient du canal dense, du canal sparse BM25, ou
de la fusion RRF.
