# Prompt — développement autonome complet de Prisme

Implémente Prisme intégralement, de bout en bout, en suivant strictement :

- `/home/mobuone/work/infra/VPAI/docs/superpowers/specs/2026-07-27-prisme-knowledge-application-design.md`
- `/home/mobuone/work/infra/VPAI/.planning/plans/2026-07-27-prisme-knowledge-application-execution.md`
- `/home/mobuone/work/infra/VPAI/.planning/reviews/2026-07-27-prisme-opus5-review.md`
- les `AGENTS.md` et `CLAUDE.md` applicables dans chaque repo.

Les documents v4 et leur revue Claude Opus 5 sont les autorités du produit et de l'exécution. En
cas de divergence avec un ancien seed, design, plan v3 ou handoff, la v4 gagne. Aucune exécution
de la v4 ne commence tant que sa revue pré-exécution ne porte pas le verdict `READY`.

Le repo Prisme et son lot P0/P1 v3 existent déjà. La reprise v4 ne recrée pas le repo : elle
audite et conserve le commit `3cee720`, rouvre G0/G1, ajoute le delta v4 puis exige un nouveau
verdict G1 `READY` avant P2. Aucun ancien résultat G1 ne vaut pour les contrats v4.

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

- seulement pour une création neuve, créer `/home/mobuone/work/saas/prisme` et son remote si les
  accès le permettent ; dans la reprise actuelle, conserver le repo et son remote existants ;
- modifier VPAI et Banga uniquement pour les intégrations Prisme prévues ;
- créer PostgreSQL Prisme et, après le gate prévu, Qdrant `knowledge_v1` avec alias
  `knowledge_current` ;
- déployer progressivement sur Sese, Waza et Banga après validation des gates, et mettre à jour
  le split-DNS Headscale sur Seko-VPN pour les FQDN VPN-only ;
- committer et pousser chaque lot cohérent vert ;
- préserver tout changement local étranger au périmètre ;
- ne jamais lire de points, vecteurs ou payloads, écrire, migrer, aliaser ou fédérer
  `trading_v1`. Seul l'inventaire read-only de métadonnées
  `GET /collections`/`GET /collections/:name` est autorisé pour le registre et G3, sans
  scroll/search/retrieve.

Le NO-GO offsite global Banga n'est pas réputé levé. Prisme peut créer `tank/knowledge` lorsque le
pool/provisioning ZFS est vert, mais doit livrer avant G10 une politique offsite et un restore
drill propres à ce dataset. L'absence vérifiée du secret ou de l'accès à la destination offsite
relève du blocage d'accès autorisé ci-dessous.

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
5. revalider chaque candidat Qdrant via PostgreSQL avec `ScopedQuery` et
   `applySecurityScope()` ; écarter toute ligne absente/révoquée/expirée/supprimée/inactive avant
   rescoring, citation ou retour, puis enrichir uniquement les survivants ; sur-récupérer au plus
   `min(3*k, 200)` ;
6. appliquer des boosts bornés entity/topic/type/qualité/temps/provenance selon intention ;
7. pour chaque `knowledge_item_id`, garder d'abord l'`index_generation` active maximale du
   ledger, puis dédupliquer par `canonical_id`, diversifier sources/provenances et conserver
   contradictions ;
8. répondre avec citations vérifiées ou s'abstenir.

Une requête sans `provenance_constraint` doit tracer zéro filtre dur de provenance.

### Vérification

- une affirmation extraite n'est jamais tenue pour vraie ;
- rechercher preuves favorables et contradictoires ;
- conserver indépendance, date, hash, provenance et limites ;
- aucun verdict sensible `supported` sans revue humaine ;
- finance : backtest puis paper/shadow uniquement, jamais d'ordre réel ;
- aucun broker, connecteur marché ou accès à `trading_v1`.

### Karakeep

- Karakeep est une Inbox optionnelle et reconstructible, jamais une source de vérité métier ;
- PostgreSQL conserve requêtes, décisions et qualifications ; Banga seul conserve les originaux
  canoniques autorisés ;
- aucune lecture de SQLite, Meilisearch, filesystem ou embeddings Karakeep ;
- intégration uniquement par API REST/webhooks du snapshot pinné ;
- `karakeep_enabled=false` par défaut ; une panne ou désactivation ne bloque jamais recherche,
  vérification ou retrieval ;
- URL seulement présente dans une SERP jamais sauvegardée automatiquement ;
- URL ouverte, analysée, citée ou rejetée journalisée avant projection asynchrone ;
- suppression ou modification Karakeep sans cascade vers Prisme, Banga ou Qdrant ;
- base URL allowlistée par configuration, contrôle SSRF avant outbox sur chaque chemin d'entrée ;
- un connecteur est mono-tenant et lié à un compte Karakeep ;
- promotion Karakeep/research vers Banga séparée, autorisée, manifestée et hashée ;
- code Karakeep jamais copié dans Prisme sans ADR et revue de licence AGPL.

## Mode opératoire

1. Appliquer MEMORY FIRST avant toute action sur un sujet documenté.
2. Auditer l'état réel des repos, machines et services avant mutation.
3. Résoudre P0 et produire l'ADR 0001.
4. Exécuter P0 à P11 selon le graphe de dépendances.
5. Ne franchir aucun gate rouge applicable à la branche exécutée. Le gate capacité du déploiement
   Karakeep réel ne bloque pas les branches fake ou `karakeep_enabled=false`.
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
11. Pour un gate capacité rouge, tenter seulement les remédiations réversibles prévues et
    remesurer. Toute relocalisation, extension payante ou interruption d'un service étranger
    devient une décision G0 de placement/capacité si elle n'est pas déductible.

Ne demander une intervention humaine que pour :

- secret ou accès réellement absent après vérification ;
- destination/credential offsite zerobyte v3 pour `tank/knowledge` réellement absent, avec gate
  humain billing/décision, statut `AWAITING_OFFSITE_DESTINATION` et liste exacte des éléments
  manquants ; Prisme ne crée jamais de bucket/credential parallèle ;
- credential de lecture cross-repo privé réellement absent ;
- décision de placement Docker+GPU Banga impossible à déduire, statut
  `AWAITING_G0_BANGA_PLACEMENT` ; sous ce statut seuls P0–P3 et P8 sur fixtures peuvent être
  livrés, mais G8 n'est pas évalué faute de G7 vert ; jamais P4–P11 ni la DoD ;
- choix G0 impossible à déduire des conventions existantes ;
- autorisation légale ou source Instagram du canary ;
- mutation irréversible ou risque production non couvert par un gate.

Avant tout gate humain portant sur un artefact texte substantiel, exécuter
`~/work/ops/loops/scripts/review-file.sh --sol <artefact>`, intégrer tous les findings HIGH, puis
présenter le gate avec
`~/work/ops/loops/scripts/notify-gate.sh --artifact <artefact> "<titre>" ["<contexte>"]`. Pour une
confirmation sans artefact substantiel, utiliser explicitement
`notify-gate.sh --no-artifact "<titre>" ["<contexte>"]`.
Un exit non nul signifie que le gate n'a pas été posé.

## Revues Claude Opus 5

Utiliser `claude -p --model opus` en lecture seule :

- après G1 : contrats, taxonomie, identité et ontologie ;
- après G2 : PostgreSQL, outbox, fake Karakeep, webhook et isolation ACL ;
- après G3 : schéma Qdrant, indexes, allowlist et ACL ;
- après G7 : vérification, preuves et expériences ;
- après G9 : retrieval, ranking, citations et isolation SQL/Qdrant ;
- après G10 et avant G11 : sécurité, sauvegarde, exploitation et canary.

Ces revues sont obligatoires et n'ont aucun fallback vers un modèle plus faible. Une absence
réellement vérifiée d'accès ou de quota Opus est un blocage d'accès autorisé par ce prompt ; la
reprise relance Opus, elle ne substitue pas un autre reviewer. Le statut est
`AWAITING_OPUS_QUOTA`, journalisé dans `.planning/EXECUTION.md` et le rapport de revue avec sortie
du usage guard/smoke sans secret ; à restauration du quota, reprendre exactement le même gate.

À chaque revue :

1. fournir design, plan, diff, tests, golden et artefacts de preuve ;
2. enregistrer le rapport dans `.planning/reviews/` ;
3. corriger tous les P0/P1 factuels ;
4. relancer jusqu'au verdict `READY` sans P0/P1 ;
5. documenter tout refus de suggestion contredisant un contrat ou une mesure.

## Critère terminal

Marquer le projet terminé uniquement lorsque :

- P0 à P11 et tous les gates applicables sont verts ;
- si le gate capacité Prisme est vert, production VPN-only et canary sont exigés ; s'il reste
  rouge après les seules remédiations réversibles autorisées, livrer tout le reste, marquer
  `AWAITING_G0_CAPACITY_DECISION` et demander uniquement la décision G0 placement/capacité sans
  prétendre la Definition of Done complète ;
- si le gate Banga placement/credential est rouge, livrer P0–P3 et P8 sur fixtures sans évaluer
  G8, marquer
  `AWAITING_G0_BANGA_PLACEMENT` avec la cible GPU et/ou le secret exact manquant, sans prétendre
  P4–P11 ni la Definition of Done complète ;
- UI, API et MCP ont une parité de résultats/citations ;
- `knowledge_v1` est reconstructible depuis PostgreSQL + Banga ;
- dense, BM25-only, RRF/DBSF et boosts ont été évalués sur requêtes réalistes ;
- aucune fuite ACL n'existe dans dense, BM25, résolution d'entités ou graphe SQL ;
- aucune donnée runtime n'est présente dans le repo ;
- backup offsite et restore drill sont démontrés ; si leur destination ou credential est
  réellement absent, tout le reste est livré et l'état terminal reste
  `AWAITING_OFFSITE_DESTINATION`, sans revendiquer la Definition of Done complète ;
- observabilité, coûts, runbooks et rollback sont disponibles ;
- contrats Karakeep conformes au snapshot OpenAPI pinné ;
- capture/déduplication Karakeep, désactivation, retry, réconciliation et absence de cascade sont
  démontrés sur fake ou instance de test ;
- tous les gates techniques antérieurs au canary sont verts ; le canary peut alors être accepté
  ou rester bloqué uniquement par l'autorisation humaine explicitement identifiée.
