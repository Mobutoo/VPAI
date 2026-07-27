# Prompt — développement autonome complet de Prisme

Implémente Prisme intégralement, de bout en bout, en suivant strictement :

- `/home/mobuone/work/infra/VPAI/docs/superpowers/specs/2026-07-27-prisme-knowledge-application-design.md`
- `/home/mobuone/work/infra/VPAI/.planning/plans/2026-07-27-prisme-knowledge-application-execution.md`
- `/home/mobuone/work/infra/VPAI/.planning/reviews/2026-07-27-prisme-opus5-review.md`
- les `AGENTS.md` et `CLAUDE.md` applicables dans chaque repo.

Les documents v3 ont reçu le verdict Claude Opus 5 `READY`. Ils sont les autorités du produit et
de l'exécution. En cas de divergence avec un ancien seed, design ou handoff, la v3 gagne.

## Objectif

Livrer une application Prisme autonome, testée, documentée, déployable et opérable :

```text
soumission d'une source autorisée
→ acquisition et stockage Banga
→ transcription/OCR/analyse
→ entités, affirmations et enseignements
→ recherche et contre-vérification
→ expériences isolées
→ bibliothèque de connaissances avec citations
```

Ne t'arrête pas à un scaffold ou à un MVP superficiel. Poursuis jusqu'à la Definition of Done de
P0 à P11, au restore drill et au canary prêt. Si le canary réel manque uniquement d'une source
autorisée, livre tout le reste et fournis l'unique action humaine restante.

## Autorisation et périmètre

- créer `/home/mobuone/work/saas/prisme` et son remote si les accès le permettent ;
- modifier VPAI et Banga uniquement pour les intégrations Prisme prévues ;
- créer PostgreSQL Prisme et, après le gate prévu, Qdrant `knowledge_v1` avec alias
  `knowledge_current` ;
- déployer progressivement sur Sese, Waza et Banga après validation des gates ;
- committer et pousser chaque lot cohérent vert ;
- préserver tout changement local étranger au périmètre ;
- ne jamais lire, écrire, migrer, aliaser ou fédérer `trading_v1`.

## Contrats non négociables

### Données

- code, tests et documentation : `/home/mobuone/work/saas/prisme` ;
- contenus runtime : Banga `/tank/knowledge` uniquement ;
- spool Waza : transitoire, borné, hors Git ;
- catalogue, ACL, ontologie et graphe : PostgreSQL Prisme ;
- Qdrant : index reconstructible, jamais source de vérité ;
- aucune arborescence Banga basée sur `room`, `topic_path` ou un nom d'entité.

### Qdrant

- collection physique `knowledge_v1`, alias runtime `knowledge_current` ;
- dense 768, EmbeddingGemma révision exacte pinnée ;
- sparse BM25/FastEmbed révision exacte pinnée ;
- RRF et DBSF implémentés, stratégie choisie seulement sur golden Prisme réel ;
- client default-deny généré depuis le registre global des collections ;
- aucune suppression/recréation automatique ;
- ACL, tenant, validité, `index_state=active` et `is_deleted=false` dans chaque prefetch ;
- aucun accès direct au SDK hors wrapper ;
- aucune mutation d'une collection étrangère.

### Taxonomie et ontologie

- `taxonomy_namespace=prisme.knowledge` ;
- `taxonomy_version` pour schémas/enums/hiérarchie ;
- `ontology_version` pour entités, alias et affectations de topics ;
- `provenance_class` est canonique ; `wing` est un alias dérivé et égal ;
- `provenance_class` n'est jamais un score de vérité ou un filtre dur implicite ;
- `room` est le domaine large ;
- `topic_path` et `topic_ancestors[]` portent le routage fin ;
- `entity_ids[]` et alias portent l'identité sémantique ;
- `doc_kind` représente le format logique indexé ;
- `knowledge_kind` représente le rôle intellectuel ;
- le rôle `supports/contradicts/contextualizes` appartient à l'arête de preuve PostgreSQL.

Les fixtures obligatoires incluent VPIN, VWAP, HMM, OBI et Mean Reversion, retrouvables par
acronyme, nom développé, alias, topic et formulation sémantique.

### Retrieval

Implémenter les intentions :

```text
explore, learn, verify, source, compare
```

Pipeline :

1. construire un `SecurityContext` obligatoire ;
2. résoudre intention, entités, alias, room/topic, temps et contrainte explicite de provenance ;
3. récupérer dense et BM25 avec filtres de sécurité identiques ;
4. fusionner RRF/DBSF selon configuration évaluée ;
5. enrichir via PostgreSQL uniquement avec `ScopedQuery` et `applySecurityScope()` ;
6. appliquer des boosts bornés entity/topic/type/qualité/temps/provenance selon intention ;
7. dédupliquer par `canonical_id`, diversifier sources/provenances et conserver contradictions ;
8. répondre avec citations vérifiées ou s'abstenir.

Une requête sans `provenance_constraint` doit tracer zéro filtre dur de provenance.

### Vérification

- une affirmation extraite n'est jamais tenue pour vraie ;
- rechercher preuves favorables et contradictoires ;
- conserver indépendance, date, hash, provenance et limites ;
- aucun verdict sensible `supported` sans revue humaine ;
- finance : backtest puis paper/shadow uniquement, jamais d'ordre réel ;
- aucun broker, connecteur marché ou accès à `trading_v1`.

## Mode opératoire

1. Appliquer MEMORY FIRST avant toute action sur un sujet documenté.
2. Auditer l'état réel des repos, machines et services avant mutation.
3. Résoudre P0 et produire l'ADR 0001.
4. Exécuter P0 à P11 selon le graphe de dépendances.
5. Ne franchir aucun gate rouge.
6. Pour chaque lot :
   - implémenter ;
   - tester ;
   - lancer lint, format, typecheck, unit, intégration, sécurité et E2E pertinents ;
   - produire les preuves et métriques prévues ;
   - mettre à jour le journal d'exécution et le handoff ;
   - committer puis pousser seulement si le lot est vert.
7. Utiliser fixtures et mocks avant toute source Instagram réelle.
8. Ne lancer le canary Instagram qu'avec une source explicitement autorisée.
9. Ne jamais exposer de secret dans Git, logs, traces, prompts ou artefacts.
10. Diagnostiquer et corriger de manière autonome les échecs reproductibles.

Ne demander une intervention humaine que pour :

- secret ou accès réellement absent après vérification ;
- choix G0 impossible à déduire des conventions existantes ;
- autorisation légale ou source Instagram du canary ;
- mutation irréversible ou risque production non couvert par un gate.

## Revues Claude Opus 5

Utiliser `claude -p --model opus` en lecture seule :

- après G1 : contrats, taxonomie, identité et ontologie ;
- après G3 : schéma Qdrant, indexes, allowlist et ACL ;
- après G7 : vérification, preuves et expériences ;
- après G9 : retrieval, ranking, citations et isolation SQL/Qdrant ;
- après G10 et avant G11 : sécurité, sauvegarde, exploitation et canary.

À chaque revue :

1. fournir design, plan, diff, tests, golden et artefacts de preuve ;
2. enregistrer le rapport dans `.planning/reviews/` ;
3. corriger tous les P0/P1 factuels ;
4. relancer jusqu'au verdict `READY` sans P0/P1 ;
5. documenter tout refus de suggestion contredisant un contrat ou une mesure.

## Critère terminal

Marquer le projet terminé uniquement lorsque :

- P0 à P11 et tous les gates applicables sont verts ;
- UI, API et MCP ont une parité de résultats/citations ;
- `knowledge_v1` est reconstructible depuis PostgreSQL + Banga ;
- dense, BM25-only, RRF/DBSF et boosts ont été évalués sur requêtes réalistes ;
- aucune fuite ACL n'existe dans dense, BM25, résolution d'entités ou graphe SQL ;
- aucune donnée runtime n'est présente dans le repo ;
- backup offsite et restore drill sont démontrés ;
- observabilité, coûts, runbooks et rollback sont disponibles ;
- le canary est accepté ou bloqué uniquement par l'autorisation humaine explicitement identifiée.
