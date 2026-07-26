# Plan d'exécution — Prisme, application de connaissance vérifiable

> Date : 2026-07-27
> Statut : **v2 post-revue Claude Opus 5 — prêt pour décisions G0, exécution non autorisée**
> Design source : `docs/superpowers/specs/2026-07-27-prisme-knowledge-application-design.md`
> Collection : nouvelle `knowledge_v1`, sans aucune interaction avec `trading_v1`

## 0. Règles d'exécution

1. Chaque lot se termine par ses tests et un artefact de preuve.
2. Aucun lot suivant ne masque un gate rouge.
3. Aucun `drop_collection`, `recreate_collection` ou purge automatique.
4. La liste de collections Qdrant protégées est testée :
   `memory_v3`, `trading_v1`, `videoref_styles`, `semantic_cache`,
   `model-registry`, `palais_memory`, `content_index`.
5. Les migrations PostgreSQL et Qdrant sont forward-only avec rollback applicatif documenté.
6. Les images, modèles, packages et actions sont pinnés.
7. Les services sont VPN-only et least privilege.
8. Les contenus récupérés sont non fiables et ne deviennent jamais des instructions.
9. Le canary utilise trois médias autorisés au maximum.
10. L'activation Instagram réelle reste bloquée par confirmation d'autorisation et acceptation
    du risque de compte.

## 1. Résultat final

Depuis `https://prisme.<domaine>` :

1. l'opérateur soumet une source ;
2. Prisme produit un manifeste sans téléchargement ;
3. l'opérateur approuve ;
4. Waza acquiert séquentiellement ;
5. Banga vérifie, stocke et analyse ;
6. Prisme extrait les affirmations ;
7. Sese recherche les preuves favorables et contradictoires ;
8. les domaines sensibles passent en revue ;
9. les éléments testables peuvent produire une expérience isolée ;
10. la bibliothèque répond avec citations, statuts et provenance.

La reconstruction de `knowledge_v1` depuis PostgreSQL + Banga est démontrée.

## 2. Graphe de dépendances

```text
P0 décisions + repo
 ├── P1 contrats partagés
 │    ├── P2 PostgreSQL/API skeleton
 │    ├── P3 Qdrant knowledge_v1
 │    ├── P4 Banga knowledge plane
 │    └── P5 Waza acquisition
 │           └── P6 media analysis
 ├───────────────┴───────┐
 ▼                       ▼
P7 verification       P8 interface
 └───────────────┬───────┘
                 ▼
        P9 retrieval/MCP
                 ▼
        P10 security/evals/ops
                 ▼
        P11 canary + production
```

P2, P3 et P4 peuvent avancer en parallèle après P1. Un vertical slice P8 commence sur fixtures
dès G2 afin de valider tôt le vocabulaire et la ligne de preuve.

## 3. P0 — Décisions et création du projet

### T0.1 — Décisions humaines

À valider :

- nom produit `Prisme` ou remplaçant ;
- slug repo `prisme` ;
- FQDN ;
- politique d'auth ;
- politiques de conservation par défaut ;
- domaines sensibles ;
- budget maximal de recherche/LLM ;
- révision exacte `google/embeddinggemma-300m` et tokenizer ;
- version `Qdrant/bm25`/FastEmbed ;
- emplacement Banga du service d'embedding et mode dégradé BM25-only ;
- route interne de composants retenue, sans Storybook au MVP ;
- source Instagram du canary et autorisation.

Artefact :

```text
prisme/docs/adr/0001-product-boundary-and-name.md
```

Gate G0 : aucune ambiguïté sur nom, domaine, auth et propriétaire des données.

### T0.2 — Vérifier le placement

Commandes read-only :

```bash
ls -1d /home/mobuone/work/{infra,saas,tools,refdocs}/* \
  | xargs -n1 basename | sort | grep -ix prisme
```

Attendu : zéro collision.

Créer ensuite `/home/mobuone/work/saas/prisme`, `git init`, arborescence de la spec et remote
approuvé. Ne pas ajouter le repo au rebuild bulk `memory_v3` tant qu'un remote clonable et le
besoin ne sont pas confirmés ; l'auto-découverte Waza suffit.

### T0.3 — Toolchain

- Node.js/pnpm selon standard VPAI actuel ;
- SvelteKit 5 ;
- TypeScript strict ;
- Drizzle ;
- Vitest ;
- Playwright ;
- ESLint/Prettier ;
- axe-core ;
- Dockerfile multi-stage non-root ;
- CI : lint, typecheck, unit, integration, e2e smoke, secret scan.

Gate G0b :

```text
pnpm lint
pnpm check
pnpm test
pnpm test:e2e
```

verts sur le squelette.

## 4. P1 — Contrats partagés

### T1.1 — Schémas

Créer dans `packages/contracts` :

```text
source.v1
ingestion-job.v1
ingestion-item.v1
artifact.v1
learning.v1
verification.v1
experiment.v1
knowledge-point.v1
outbox-event.v1
problem-details.v1
```

Autorité choisie : **Zod** dans `packages/contracts`. Générer JSON Schema/OpenAPI et des fixtures
consommables par les workers Python ; aucune seconde définition manuelle.
Interdire la duplication manuelle TypeScript/Python.

Tests :

- fixtures valides ;
- champs inconnus rejetés sur mutations ;
- compatibilité backward sur lecture ;
- dates UTC ;
- bornes taille/durée ;
- enums taxonomiques ;
- aucun secret/URL CDN signé dans les artefacts.

### T1.2 — Automates

Automate ingestion :

```text
requested → discovering → awaiting_approval → approved
→ fetching → transferred → stored → analyzing → analyzed
→ extracting → indexed → completed
```

Branches :

```text
paused, stalled, skipped, failed_retryable, failed_terminal, cancelled
```

Automates séparés :

- vérification ;
- revue ;
- expérience ;
- rétention.

Tests exhaustifs de transitions autorisées et interdites.

### T1.3 — Taxonomie partagée

Créer :

```text
packages/contracts/src/taxonomy.ts
packages/contracts/taxonomy/knowledge-v1.yaml
packages/contracts/tests/taxonomy.test.ts
```

Le registre contient `wing`, `room`, `doc_kind`, statuts, niveaux de risque et règles de fallback.
`misc`, null et chaînes libres non enregistrées sont refusés.
`repo` est dérivé de `corpus_id`; un test refuse toute divergence.

### T1.4 — Contrat embedding partagé

Créer :

```text
packages/embeddings/src/prompts.ts
packages/embeddings/src/client.ts
packages/embeddings/src/version.ts
packages/embeddings/tests/
```

Contrats :

- `embedDocument()` applique uniquement `build_doc_prompt` ;
- `embedQuery()` applique uniquement le prompt nommé `Retrieval-query` ;
- `embedSparse()` applique `build_sparse_text` ;
- modèle, tokenizer, sparse model et prompts ont des versions pinnées ;
- import direct d'un autre client embedding interdit par lint ;
- aucune retombée silencieuse vers un autre modèle ;
- parité fixtures avec le contrat `memory_v3`.

### T1.5 — Golden set embryonnaire

Avant tout benchmark :

- 10 médias autorisés gelés ;
- transcript humain de référence sur passages représentatifs ;
- claims/timestamps attendus ;
- 20 paires query/document ;
- cas contradictoires et injections indirectes ;
- données sensibles exclues.

Ce jeu démarre petit mais précède P4/P6/P7 ; P10 l'étend en golden de production.

Gate G1 : contrats utilisables par web, workers Python et bootstrap Qdrant.

## 5. P2 — PostgreSQL et squelette API

### T2.1 — Base dédiée

Dans VPAI :

- créer DB/user `prisme` via le rôle PostgreSQL existant ;
- secret coffre, `no_log`;
- connexion uniquement depuis le réseau Prisme ;
- backup intégré ;
- métriques connexion/espace.

### T2.2 — Migrations

Créer les tables de la spec avec :

- FK et uniques ;
- timestamps UTC ;
- colonnes de version ;
- soft delete ;
- outbox ;
- audit append-only ;
- ACL ;
- index SQL sur états, source IDs, claim IDs et dates ;
- GIN uniquement sur besoins démontrés.

Tests :

- migration depuis base vide ;
- migration répétée ;
- rollback applicatif ;
- contraintes d'idempotence ;
- suppression logique ;
- outbox dans la même transaction que le changement métier.

### T2.3 — API skeleton

Implémenter :

- auth middleware ;
- request ID ;
- `Idempotency-Key` ;
- Problem Details ;
- pagination par curseur ;
- OpenAPI ;
- `/health/live`, `/health/ready`;
- SSE avec reprise `Last-Event-ID`.

Le buffer SSE a une taille et une TTL configurables ; au-delà, le client recharge un snapshot
plutôt que de supposer que tous les événements sont encore disponibles.

### T2.4 — Relais outbox

- livraison at-least-once ;
- claim par `FOR UPDATE SKIP LOCKED` ;
- déduplication consommateur par `event_id` ;
- retry borné et dead-letter queue ;
- heartbeat ;
- métriques lag/échec/âge ;
- reconciler des états PostgreSQL/worker/Qdrant après crash ;
- tests arrêt entre claim, effet et ack.

Gate G2 : API démarre avec PostgreSQL, sans Qdrant ni worker, et expose des états dégradés exacts.

## 6. P3 — Qdrant `knowledge_v1`

### T3.1 — Registre global des collections

Ajouter dans VPAI :

```text
docs/runbooks/QDRANT-COLLECTION-MANIFEST.md
inventory/group_vars/all/qdrant_collections.yml
```

Pour chaque collection :

```text
name, owner, purpose, source_of_truth, producer, consumers,
vector_schema, payload_schema, retention, backup, mutation_policy
```

`trading_v1` y apparaît comme `owner: hawktrade`, `mutation_policy: deny-from-prisme`.

### T3.2 — Package schéma

Créer dans Prisme :

```text
packages/qdrant-schema/src/schema.ts
packages/qdrant-schema/src/bootstrap.ts
packages/qdrant-schema/src/validate.ts
packages/qdrant-schema/src/ids.ts
packages/qdrant-schema/src/client.ts
packages/qdrant-schema/src/filters.ts
packages/qdrant-schema/tests/
```

Le bootstrap :

1. liste les collections ;
2. refuse si la cible ne vaut pas exactement `knowledge_v1` ou une cible de test allowlistée ;
3. crée si absente ;
4. vérifie dense, sparse, distance, HNSW, on-disk payload ;
5. crée les indexes absents ;
6. échoue sur un index de type incompatible ;
7. ne supprime rien ;
8. écrit un rapport JSON sans secret ;
9. crée l'alias seulement après validation.

Le client runtime :

- allowlist exacte `knowledge_v1`, `knowledge_current`, `prisme_test_*` ;
- default-deny avant tout appel réseau ;
- aucune méthode `deleteCollection`, `recreateCollection` ou `snapshotRestore` exportée ;
- `buildSecurityFilter(SecurityContext, asOf)` obligatoire ;
- filtre ACL/validité/index actif injecté dans chaque prefetch dense et BM25 ;
- import direct du SDK Qdrant interdit hors du package.

`ids.ts` inclut artefact, contenu, modèle/révision, chunker, prompt d'extraction et prompt embedding.

### T3.3 — Tests sans production

Qdrant éphémère local :

- création depuis zéro ;
- second run sans changement ;
- collection compatible déjà présente ;
- dimension incompatible ;
- dense unnamed ;
- BM25 absent ;
- index manquant ;
- index mauvais type ;
- cible protégée ;
- cible inconnue refusée avant réseau ;
- `trading_v1` refusée avant réseau ;
- stabilité UUIDv5 inter-processus ;
- non-collision après changement modèle/chunker/prompt ;
- ACL étrangère, point expiré, staging et deleted exclus dans dense **et** BM25 ;
- timeout ;
- alias atomique.

### T3.4 — Smoke prod read-only puis création

Avant mutation :

- inventorier noms/schémas ;
- sauvegarder le rapport ;
- confirmer absence de `knowledge_v1` ;
- vérifier health/snapshot policy.

Mutation autorisée uniquement après revue du rapport et gate humain.
Elle reste bloquée tant que les tests client/ACL/identités de T3.2/T3.3 ne sont pas verts.

Après création :

- `knowledge_v1` green ;
- 0 point ;
- schéma exact ;
- tous les indexes présents ;
- autres collections : nombre de points et schéma inchangés.

Gate G3 : diff avant/après prouve que seule `knowledge_v1` et son alias ont changé.

## 7. P4 — Banga knowledge plane

Travaux dans `../banga`.

### T4.1 — ZFS

- dataset `tank/knowledge`, quota initial validé ;
- sous-arborescence `incoming`, `library`, `research`, `experiments`, `exports`, `quarantine`;
- permissions distinctes ;
- snapshots ;
- métriques quota ;
- aucune réservation avant mesure.

### T4.2 — Knowledge store

Rôle `knowledge-store` :

- compte de transfert dédié ;
- SFTP/SSH restreint ;
- promotion atomique ;
- SHA-256 source/destination ;
- manifeste de bundle ;
- API interne de statuts ou callback signé ;
- janitor report-only par défaut.

### T4.3 — Worker

Le jeu T1.5 fournit les 10 vidéos et transcripts de référence avant le benchmark :

- Waza whisper base ;
- Banga whisper GPU ;
- OCR actuel ;
- GLM-OCR ;
- challenger multimodal cloud autorisé.

Choisir sur WER/CER, rappel OCR, conformité JSON, latence et coût.

### T4.4 — Service Embedding Prisme

Rôle `knowledge-embedding` :

- image unique pour indexation et requête ;
- modèle/tokenizer EmbeddingGemma et FastEmbed pinnés ;
- endpoints document/query/sparse distincts ;
- prompts partagés T1.4 ;
- batching, cache par SHA et limites ;
- accès mesh + jeton de service rotatable ;
- test parité CPU/GPU ;
- healthcheck exposant toutes les versions ;
- aucun fallback de modèle implicite.

La même image immuable est déployée sur Sese en mode `sparse-query-only`. Sur indisponibilité
Banga/dense, Prisme annonce le mode dégradé et utilise ce sidecar BM25-only. La release est bloquée
si les vecteurs sparse Banga/Sese divergent. La recherche dense n'est jamais simulée avec un autre
modèle.

### T4.5 — Experiment runner

- conteneur non privilégié ;
- réseau refusé par défaut ;
- CPU/RAM/GPU/temps bornés ;
- filesystem éphémère ;
- datasets read-only ;
- aucune credential production/courtier ;
- aucun connecteur marché et aucune lecture de `trading_v1` ;
- manifeste et résultats persistés.

Gate G4 :

- bundle factice transféré/promu/relu ;
- snapshot et restauration testés ;
- embeddings document/query produits avec versions attendues ;
- purge impossible sans gates ;
- test d'évasion/egress négatif.

## 8. P5 — Waza acquisition

Dans VPAI :

```text
roles/prisme-fetcher/
```

### T5.1 — Fetcher abstrait

Interface :

```text
discover(request) -> manifest
fetch(item) -> source bundle
health() -> capability
```

Implémentations :

- Instagram official API ;
- gallery-dl ;
- local upload fixture.

### T5.2 — État durable

SQLite WAL :

- jobs ;
- items ;
- transitions ;
- outbox ;
- leases ;
- retries ;
- circuit breaker ;
- heartbeat.

### T5.3 — Limites

- acquisition Instagram concurrence 1 ;
- `.part` puis rename ;
- délai/jitter côté worker ;
- espace disque avant chaque média ;
- aucun retry agressif ;
- 401/403/429/challenge ouvrent le circuit ;
- transfert vers Banga avant suppression ;
- logs JSON caviardés.

### T5.4 — Tests

- discover ne télécharge rien ;
- carrousel ;
- doublons posts/Reels ;
- restart chaque état ;
- crash transfert ;
- cookies absents/invalides ;
- 429 ;
- disque bas ;
- idempotence ;
- SIGTERM ;
- aucune fuite cookie/header/URL signée.

Gate G5 : pipeline fixture local complet vers Banga, sans appel Instagram.

## 9. P6 — Analyse média et extraction

### T6.1 — Segmentation

- métadonnées ffprobe ;
- scènes ;
- pistes audio ;
- langue par segment ;
- timestamps en millisecondes ;
- posters ;
- sélection de frames déterministe.

### T6.2 — Transcription/OCR

- sortie segmentée ;
- VTT ;
- diarisation seulement si benchmark utile ;
- OCR avec bounding boxes et timestamp ;
- erreurs partielles explicites ;
- provenance modèle/version.

### T6.3 — Extraction

Produire `learning.v1` :

- concepts ;
- claims typés ;
- citation source ;
- procédures ;
- exemples ;
- limites ;
- inconnues ;
- confiance d'extraction, jamais score de vérité.

### T6.4 — Indexation

- écrire bundle Banga ;
- enregistrer PostgreSQL ;
- encoder via `embedDocument()`/`embedSparse()` du contrat T1.4 ;
- produire des IDs déterministes incluant toutes les versions ;
- écrire le ledger `index_points` ;
- upserter d'abord avec `index_state=staging` ;
- upsert batch ;
- vérifier count/source IDs/retrieval ;
- activer la nouvelle version puis invalider l'ancienne ;
- dédupliquer la coexistence transitoire au retrieval ;
- réconcilier tout état partiel après crash ;
- marquer `indexed` seulement après lecture de contrôle.

Gate G6 : trois fixtures produisent bundles valides et points retrouvables sans doublon ; changer
modèle/chunker/prompt crée de nouveaux IDs et conserve l'historique.

## 10. P7 — Contre-vérification et expériences

### T7.1 — Research worker

- queue PostgreSQL ;
- provider de recherche interchangeable ;
- recherche favorable/contradictoire ;
- canonicalisation URL ;
- qualification source ;
- hash/date ;
- budget ;
- timeout ;
- cache ;
- allowlist sensible ;
- protection SSRF ;
- contenu externe marqué non fiable.

### T7.2 — Vérification

Produire `verification.v1` :

- snapshot claim ;
- statut ;
- preuves favorables ;
- contre-preuves ;
- dépendance des sources ;
- conflits d'intérêts ;
- limites ;
- date d'expiration ;
- revue humaine.

### T7.3 — Revue

Workflow :

```text
pending → in_review → approved|rejected|needs_more_evidence
```

Finance/santé/droit/sécurité : aucun `supported` sans reviewer humain.

### T7.4 — Expériences

- proposition ;
- protocole gelé ;
- métriques/seuil ;
- approbation ;
- sandbox ;
- résultats bruts ;
- reproduction ;
- conclusion.

Pour le trading : backtest puis paper/shadow uniquement, jamais ordre réel.

Gate G7 :

- un claim supporté ;
- un claim contesté ;
- un claim insuffisant ;
- une injection indirecte neutralisée ;
- une expérience reproductible ;
- aucun verdict sensible sans humain.

## 11. P8 — Interface Prisme

### T8.1 — Design system

Implémenter les tokens et composants :

- typographie ;
- couleurs ;
- grille ;
- ligne de preuve ;
- badges avec texte/icône ;
- lecteur temporel ;
- panneau de citations ;
- tables denses ;
- skeletons ;
- erreurs et empty states ;
- focus/reduced motion.

Le MVP utilise une route interne de composants. Storybook n'est pas ajouté sans ADR ultérieur.

### T8.2 — Vertical slice UI

Ordre :

1. `/ingestions/new`;
2. `/ingestions/:id`;
3. `/items/:id`;
4. `/claims/:id`;
5. `/review`;
6. `/ask`;
7. `/library`;
8. dashboard/admin.

Sur fixtures, livrer `/ingestions/:id` et `/claims/:id` dès G2, avant les workers réels. Les autres
pages suivent dans P8.

### T8.3 — Tests UX

- 360, 768, 1280, 1600 et 1920 px ;
- clavier ;
- axe ;
- contrastes ;
- reduced motion ;
- états vide/erreur/partiel ;
- lien timestamp ;
- citations très longues et textes sans espaces ;
- aucune couleur seule ;
- tests visuels sur pages critiques.

Gate G8 : un utilisateur peut soumettre, approuver, lire, vérifier et retrouver une preuve sans
CLI ni accès direct aux machines.

## 12. P9 — Retrieval, réponses et MCP

### T9.1 — Search API

- client Embedding : dense+BM25 avec dégradation BM25-only explicite ;
- filtre `SecurityContext` injecté dans chaque prefetch ;
- hybrid dense+BM25+RRF via l'alias `knowledge_current` ;
- filtres taxonomiques ajoutés au filtre sécurité, jamais à sa place ;
- ACL, validité, `index_state=active` et `deleted_at=null` obligatoires ;
- versions actives ;
- regroupement source/claim ;
- rerank flaggé OFF ;
- citations structurées.

### T9.2 — Ask

- décomposition en claims ;
- retrieval borné ;
- preuves contradictoires ;
- génération abstention-aware ;
- vérification citation-support ;
- sauvegarde answer/citations ;
- claims pending/refuted exclus des recommandations.

### T9.3 — MCP

```text
knowledge_search
knowledge_get
knowledge_get_claim
knowledge_get_evidence
knowledge_compare_claims
knowledge_verify_claim
knowledge_propose_experiment
knowledge_get_experiment
```

Les outils MCP appellent l'API, jamais Qdrant directement.
Chaque appel MCP propage une identité authentifiée et ses ACL ; une identité absente est refusée.

Gate G9 : UI, API et MCP retournent les mêmes résultats/citations pour les mêmes filtres.

## 13. P10 — Sécurité, evals et exploitation

### T10.1 — Threat model

Menaces :

- prompt injection directe/indirecte ;
- RAG poisoning ;
- SSRF ;
- archive bomb/media malformé ;
- traversal ;
- fuite de cookies/secrets ;
- confusion ACL ;
- replay callback ;
- job dupliqué ;
- expérience échappant au sandbox ;
- verdict IA non revu.

Créer tests et mitigations explicites.

### T10.2 — Observabilité

- spans OpenTelemetry ;
- métriques files/latence/coût/qualité ;
- dashboards Grafana ;
- alertes stalled, circuit open, quota, index lag, backup, qualité ;
- sampling sans contenu sensible ;
- corrélation `job_id/source_id/claim_id`.

### T10.3 — Evals

Étendre les fixtures T1.5 en golden sets humains versionnés. Mesurer :

- extraction ;
- retrieval ;
- citations ;
- vérification ;
- sécurité ;
- reproductibilité.

Ne pas fixer les seuils retrieval avant baseline sur requêtes réelles.

### T10.4 — Runbooks

Dans Prisme :

```text
docs/runbooks/INGESTION.md
docs/runbooks/RESEARCH.md
docs/runbooks/REINDEX.md
docs/runbooks/RESTORE.md
docs/runbooks/RETENTION.md
docs/runbooks/INCIDENT.md
docs/runbooks/MODEL-MIGRATION.md
```

Dans VPAI/Banga : déploiement, stockage et DR.

Gate G10 :

- threat model couvert ;
- dashboards actifs ;
- restore drill réussi ;
- golden baseline archivée ;
- aucune alerte critique ;
- secrets scan vert.

## 14. P11 — Canary et production

### T11.1 — Préproduction

- environnement/stacks séparés ;
- DB propre ;
- collection de test ;
- trois fixtures ;
- tests E2E ;
- restauration.

### T11.2 — Création production

- créer `knowledge_v1` via bootstrap revu ;
- appliquer migrations ;
- déployer services désactivés ;
- healthchecks ;
- sauvegardes ;
- aucun cookie Instagram.

### T11.3 — Canary autorisé

1. discover 3 médias ;
2. revue du manifeste ;
3. approbation ;
4. acquisition séquentielle ;
5. transfert Banga ;
6. analyse ;
7. extraction/indexation ;
8. vérification d'au moins un claim ;
9. revue humaine ;
10. question `/ask` avec citations ;
11. purge simulée sur le canary ; purge réelle uniquement sur un artefact jetable créé pour ce test.

### T11.4 — Go/no-go bulk

GO si :

- zéro doublon ;
- zéro perte ;
- zéro secret ;
- checksums corrects ;
- citations ouvrables ;
- statuts cohérents ;
- restauration prouvée ;
- qualité canary validée humainement ;
- Instagram sans challenge/429 ;
- coûts/capacité acceptés.

Sinon NO-GO et REX.

## 15. Fichiers VPAI prévus

```text
inventory/group_vars/all/versions.yml
inventory/group_vars/all/qdrant_collections.yml
playbooks/hosts/sese-ai.yml
playbooks/hosts/workstation.yml
roles/prisme/
roles/prisme-fetcher/
roles/caddy/templates/Caddyfile.j2
roles/postgresql/
roles/monitoring/
docs/runbooks/QDRANT-COLLECTION-MANIFEST.md
docs/runbooks/PRISME-DEPLOYMENT.md
```

Toute modification d'un rôle partagé doit être minimisée et couverte par non-régression.
Les checks nommés Caddy/PostgreSQL/monitoring existants doivent rester verts avant merge.

## 16. Fichiers Banga prévus

```text
inventory/group_vars/all/main.yml
roles/knowledge-store/
roles/knowledge-worker/
roles/knowledge-embedding/
roles/experiment-runner/
docs/runbooks/KNOWLEDGE-STORE.md
```

## 17. Stratégie de rollback

| Incident | Rollback |
|---|---|
| UI/API défectueuse | image précédente |
| migration DB | compatibilité applicative précédente, pas de down destructive |
| index incomplet | désactiver `knowledge_current`, reconstruire depuis Banga |
| modèle embedding changé | nouvelle collection versionnée, ancien alias intact |
| chunker/prompt changé | nouveaux point IDs, ancienne version conservée jusqu'à validation |
| worker Waza | stop après item courant, reprise SQLite |
| worker Banga | bundle conservé, retry depuis état PostgreSQL |
| research provider | circuit open, claims restent pending |
| purge erronée | snapshot/backup selon politique ; jamais promettre récupération non sauvegardée |

## 18. Definition of Done produit

- application autonome accessible VPN-only ;
- aucune dépendance métier à Palais/Open WebUI ;
- `knowledge_v1` dense 768 + BM25 + RRF ;
- taxonomie et tous indexes vérifiés ;
- aucune mutation de `trading_v1` ni autre collection protégée ;
- ingestion autorisée de bout en bout ;
- bundle canonique Banga ;
- extraction, vérification et expérience séparées ;
- revue humaine des risques élevés ;
- recherche/UI/MCP avec citations ;
- sécurité adversariale testée ;
- observabilité et coûts visibles ;
- restore drill réussi ;
- canary accepté ;
- runbooks disponibles.

## 19. Ordre des premières sessions

```text
Session 1 : décisions P0 + scaffold + contrats P1
Session 2 : PostgreSQL/API P2
Session 3 : Qdrant P3
Session 4 : Banga store P4
Session 5 : Waza fetcher P5
Session 6 : analyse/indexation P6
Session 7 : recherche/vérification P7
Session 8 : UI vertical slice P8
Session 9 : retrieval/MCP P9
Session 10 : sécurité/evals/ops P10
Session 11 : canary P11
```

Chaque session produit tests, rapport et handoff ; elle ne présume pas le GO de la suivante.
