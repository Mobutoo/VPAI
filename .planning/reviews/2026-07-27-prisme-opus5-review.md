# Revue Claude Opus 5 — Prisme

> Date : 2026-07-27
> Reviewer : Claude Opus 5 via `claude --model opus`
> Mode : lecture seule, deux passes (design puis exécution)
> Documents :
> - `docs/superpowers/specs/2026-07-27-prisme-knowledge-application-design.md`
> - `.planning/plans/2026-07-27-prisme-knowledge-application-execution.md`

## Verdict

**GO conditionnel après corrections P0.**

Le reviewer juge l'architecture saine : séparation PostgreSQL/Banga/Qdrant, Qdrant
reconstructible, migrations sans wipe, gates explicites, séparation extraction/vérification/
expérience et isolement de `trading_v1`.

## P0 design

1. L'identité d'un point doit inclure modèle, chunker et versions de prompts afin qu'une
   réanalyse ne remplace pas silencieusement l'historique.
2. L'asymétrie d'embedding document/requête doit être explicite, versionnée et testée.
3. ACL et validité doivent être injectées dans chaque prefetch dense et BM25, avant RRF.
4. Le client Qdrant doit être default-deny et autoriser uniquement `knowledge_v1`,
   `knowledge_current` et les collections de test.

## P0 exécution

1. Les quatre corrections design doivent devenir des tâches/tests nommés dans le plan.
2. L'outbox PostgreSQL nécessite un relais at-least-once avec déduplication, DLQ et métrique lag.
3. Le modèle/tokenizer d'embedding doit être décidé et pinné avant le bootstrap.

## P1

- ajouter `chunk_index`/`chunk_total` ;
- ajouter `answers`, `answer_citations` et un ledger `index_points` ;
- ajouter takedown/suppression logique ;
- figer les enums de vérification/preuve/risque ;
- interdire explicitement toute connexion de l'experiment-runner à `trading_v1` ou à un courtier ;
- définir un golden transcript avant le benchmark média ;
- propager l'identité/ACL dans MCP ;
- commencer les golden sets et un vertical slice UI plus tôt ;
- ne purger réellement qu'un artefact jetable pendant le canary.

## P2

- éviter les indexes inutiles à très haute cardinalité ;
- lire via l'alias `knowledge_current` ;
- ajouter SSE recherche/expériences ;
- définir quotas et rate limits ;
- tester les citations longues et les grands écrans ;
- imposer une non-régression explicite aux rôles partagés.

## Forces à préserver

- autorité des données clairement séparée ;
- aucune suppression/recréation automatique ;
- taxonomie orthogonale avec fallbacks ;
- quarantaine des provenances inconnues ;
- gates sécurité chiffrées ;
- SLO établis après baseline ;
- interface centrée sur la preuve ;
- sandbox sans secrets ni ordres réels ;
- canary limité et autorisé humainement.

## Décision de l'auteur

Toutes les corrections P0 et P1 sont intégrées. Les P2 sont intégrées lorsqu'elles n'imposent pas
un seuil arbitraire avant baseline. Les chaînes exactes de prompts EmbeddingGemma suivent le
contrat déjà éprouvé de `memory_v3`, plutôt qu'une chaîne nouvelle suggérée sans vérification.

## Passe finale

Opus 5 a rendu le verdict **READY**, sans reliquat P0. Deux corrections mineures finales ont été
appliquées :

- le fallback BM25 utilise la même image immuable en mode `sparse-query-only` sur Sese, avec test
  de parité Banga/Sese ;
- `repo` est dérivé de `corpus_id` et leur divergence est refusée.

Le service d'embedding reçoit également un jeton de service rotatable en plus de l'isolation mesh.
