# Plan d'exécution — Prisme, application de connaissance vérifiable

> Date : 2026-07-27
> Statut : **v3 post-revue Claude Opus 5 — READY**, prêt pour décisions G0, exécution non autorisée
> Design source : `docs/superpowers/specs/2026-07-27-prisme-knowledge-application-design.md`
> Collection : nouvelle `knowledge_v1`, sans aucune interaction avec `trading_v1`

## 0. Règles d'exécution

1. Chaque lot se termine par ses tests et un artefact de preuve.
2. Aucun lot suivant ne masque un gate rouge.
3. Aucun `drop_collection`, `recreate_collection` ou purge automatique.
4. La source unique des collections Qdrant et politiques de mutation est
   `inventory/group_vars/all/qdrant_collections.yml`; le client Prisme en génère son allowlist et
   ses tests. Aucun duplicata manuel de denylist n'est autorisé.
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
- propriétaire du registre d'ontologie et procédure d'ajout d'entité/topic ;
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
- `.gitignore` et contrôle CI refusant média réel, transcript d'exploitation, frame, OCR, export,
  cache modèle et volume runtime dans le repo ; seules les petites fixtures synthétiques ou
  explicitement redistribuables sont autorisées.

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
knowledge-entity.v1
strategy-spec.v1
search-intent.v1
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

Le registre contient :

- `taxonomy_namespace=prisme.knowledge`, `taxonomy_version=1` et `ontology_version` ;
- `provenance_class` canonique : `social`, `web`, `official`, `academic`, `internal`, `derived`,
  `experimental` ;
- `wing` alias de compatibilité dérivé côté serveur, strictement égal à `provenance_class` ;
- `room` de domaine ;
- `topic_path` hiérarchique et `topic_ancestors[]` ;
- `entity_kind`, entités canoniques et alias ;
- `doc_kind` de représentation ;
- `knowledge_kind` de rôle intellectuel ;
- statuts, niveaux de risque et règles de fallback.

`misc`, null et chaînes libres non enregistrées sont refusés. `provenance_class` n'est jamais un score de
vérité ni un filtre dur implicite. `doc_kind` est unique et ne mélange plus représentation,
contenu intellectuel et rôle probatoire.
La matrice complète `doc_kind/knowledge_kind`, l'invariant racine de `topic_path == room` et les
règles `source_provenance_classes[]` pour `derived/experimental` vivent dans le YAML et ses tests.
Tout changement d'alias ou de reclassification incrémente `ontology_version` et planifie le
réencodage des points affectés.
`repo` est dérivé de `corpus_id`; un test refuse toute divergence.
`wing` est dérivé de `provenance_class`; le client ne peut pas le fournir et un test refuse toute
divergence `wing != provenance_class`.

### T1.4 — Contrat embedding partagé

Créer :

```text
packages/embeddings/src/prompts.ts
packages/embeddings/src/client.ts
packages/embeddings/src/version.ts
packages/embeddings/tests/
```

Contrats :

- `embedDocument()` applique uniquement `build_doc_prompt` avec room/topic, entités/alias,
  `doc_kind/knowledge_kind`, provenance et texte ;
- `embedQuery()` applique uniquement le prompt nommé `Retrieval-query` ;
- `embedSparse()` applique `build_sparse_text` incluant acronymes, noms canoniques et alias ;
- modèle, tokenizer, sparse model et prompts ont des versions pinnées ;
- import direct d'un autre client embedding interdit par lint ;
- aucune retombée silencieuse vers un autre modèle ;
- parité avec `memory_v3` limitée aux modèles, à l'asymétrie requête/document et aux primitives
  sparse ; le prompt documentaire Prisme est volontairement différent et testé comme tel.

### T1.5 — Golden set embryonnaire

Avant tout benchmark :

- 10 médias autorisés gelés ;
- transcript humain de référence sur passages représentatifs ;
- claims/timestamps attendus ;
- 20 paires query/document ;
- requêtes exactes VPIN/VWAP/HMM/OBI, synonymes, noms développés et formulations sémantiques ;
- intentions `explore`, `learn`, `verify`, `source`, `compare` ;
- cas contradictoires et injections indirectes ;
- données sensibles exclues.

Ce jeu démarre petit mais précède P4/P6/P7 ; P10 l'étend en golden de production.

### T1.6 — Contrat de retrieval

Créer un contrat pur et testable :

```text
query → SearchIntent + resolved entities/aliases + room/topic +
        temporal constraints + explicit provenance constraints
```

Règles :

- ACL, tenant, validité, suppression et version active sont toujours des filtres durs ;
- une contrainte de provenance n'est dure que si l'utilisateur l'a explicitement demandée ;
- `entity_ids`/alias et `topic_path` portent le routage principal ;
- `room`, `doc_kind` et `knowledge_kind` sont des boosts ou filtres dépendant de l'intention ;
- `provenance_class` sert à la provenance, à la diversité et à un boost borné dépendant de
  l'intention ;
- `verify` doit conserver les preuves favorables et contradictoires de plusieurs provenances ;
- le contrat de score et chaque feature sont versionnés et désactivables pour ablation.

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

Inclure explicitement :

```text
knowledge_entities
entity_aliases
entity_relations
knowledge_item_entities
strategy_specs
```

`strategy_specs` versionne hypothèses, paramètres, univers, horizon, coûts, risques, métriques et
liens vers expériences. Les alias sont normalisés, uniques dans leur namespace et testés contre les
collisions d'acronymes.

Définir la projection Qdrant mutable :

```text
topic, tags, acl_scope, claim_ids, verification_status, risk_level,
evidence_level, experiment_status, last_verified_at, index_state,
valid_to, is_deleted, deleted_at
```

PostgreSQL en reste l'autorité ; seuls ces champs utilisent `set_payload`. L'outbox, le reconciler,
la métrique `qdrant_projection_lag_seconds` et les tests de crash garantissent la convergence.

Tests :

- migration depuis base vide ;
- migration répétée ;
- `valid_to NOT NULL DEFAULT '9999-12-31T00:00:00Z'` dans la projection/index ledger ;
- rollback applicatif ;
- contraintes d'idempotence ;
- suppression logique ;
- outbox dans la même transaction que le changement métier.

### T2.3 — API skeleton

Implémenter :

- auth middleware ;
- repositories SQL de retrieval retournant uniquement un type `ScopedQuery` après
  `applySecurityScope()` ;
- import/accès `db.` brut interdit par lint hors migrations et couche repository allowlistée ;
- request ID ;
- `Idempotency-Key` ;
- Problem Details ;
- pagination par curseur ;
- OpenAPI ;
- `/health/live`, `/health/ready`;
- SSE avec reprise `Last-Event-ID`.

Le buffer SSE a une taille et une TTL configurables ; au-delà, le client recharge un snapshot
plutôt que de supposer que tous les événements sont encore disponibles.

Tests : une requête retrieval SQL non scopée échoue au typecheck/lint ; une identité étrangère ne
retourne aucune ligne par les repositories d'entités, claims, preuves et graphe.

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

`ids.ts` inclut `knowledge_item_id`, artefact, identité canonique, `doc_kind`, `knowledge_kind`,
index de chunk, SHA-256 du texte exact de l'unité, schéma, `taxonomy_version`, `ontology_version`,
modèles dense et sparse, chunker, prompt d'extraction et prompt embedding. Deux unités issues du
même chunk restent distinctes et tout changement vectoriel produit une nouvelle identité.

Les indexes couvrent au minimum `taxonomy_namespace`, `taxonomy_version`, `ontology_version`,
`provenance_class`, `wing`, `room`, `topic_path`, `topic_ancestors`, `entity_ids`, `entity_kinds`,
`doc_kind`, `knowledge_kind`, `source_provenance_classes`, `knowledge_item_id`, `artifact_id`,
`canonical_id` et tous les champs sécurité/validité de la spec. `topic`, `embedding_dim`,
`relative_path` et `content_sha256` restent hors index.

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
- non-collision après changement de taxonomie ;
- non-collision après changement de modèle sparse ou d'ontologie/alias ;
- deux unités issues du même chunk donnent deux points distincts ;
- deux versions d'une même unité partagent `canonical_id` et sont dédupliquées au retrieval ;
- enums `doc_kind` mutuellement exclusifs et combinaisons `doc_kind/knowledge_kind` valides ;
- alias exact VPIN/VWAP/HMM/OBI routés vers les bonnes entités ;
- ACL étrangère, point expiré, staging et deleted exclus dans dense, BM25 **et graphe SQL** ;
- `buildValidationFilter()` conserve tenant/ACL mais retrouve le staging pour l'indexeur seulement ;
- un point sans `valid_to` ou avec `valid_to=null` est refusé avant upsert ;
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

Dépendance dure : le pool ZFS `tank` et son chantier de provisioning/backup sont verts avant toute
création de dataset Prisme. Sinon P4 s'arrête sans créer de stockage alternatif.

### T4.1 — ZFS

- dataset `tank/knowledge`, quota initial validé ;
- sous-arborescence `incoming`, `library`, `research`, `experiments`, `exports`, `quarantine`;
- permissions distinctes ;
- snapshots ;
- rattachement au backup 3-2-1-1-0 Banga, copie offsite et restore drill ;
- métriques quota ;
- aucune réservation avant mesure.

Arborescence obligatoire par identifiants stables :

```text
/tank/knowledge/
├── incoming/<ingestion_id>/
├── library/<tenant_id>/<corpus_id>/<item_id>/<version_id>/{source,derived,knowledge}/
├── research/<claim_id>/<research_run_id>/
├── experiments/<experiment_id>/<run_id>/
├── exports/<export_id>/
└── quarantine/<ingestion_id>/
```

Interdire toute arborescence physique dérivée de `room`, `topic_path` ou d'un nom d'entité.
Le rôle vérifie que chaque `relative_path` est relatif à `/tank/knowledge` et conforme au patron
`library/<tenant>/<corpus>/<item>/<version>/...`.

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

- entités canoniques candidates avec `entity_kind`, alias et score de résolution ;
- `room`, `topic_path` et `topic_ancestors` issus du registre versionné ;
- claims typés ;
- citation source ;
- définitions, explications, formules, procédures et stratégies via `knowledge_kind` ;
- exemples ;
- limites ;
- inconnues ;
- confiance d'extraction, jamais score de vérité.

La résolution d'entité est déterministe lorsqu'un alias unique existe. Une collision ou une entité
nouvelle crée une tâche de revue ; elle n'invente pas silencieusement un nouvel identifiant. Les
stratégies produisent un `strategy_spec` distinct avec hypothèses, paramètres, univers, horizon,
coûts, risques et métriques testables.

### T6.4 — Indexation

- écrire bundle Banga ;
- enregistrer PostgreSQL ;
- encoder via `embedDocument()`/`embedSparse()` du contrat T1.4 ;
- produire des IDs déterministes incluant toutes les versions ;
- écrire le ledger `index_points` ;
- upserter d'abord avec `index_state=staging` ;
- upsert batch ;
- vérifier count/source IDs/retrieval via `buildValidationFilter()` réservé à l'indexeur ;
- activer la nouvelle version puis invalider l'ancienne ;
- vérifier côté PostgreSQL que toute connaissance servie est active ;
- dédupliquer la coexistence transitoire au retrieval ;
- réconcilier tout état partiel après crash ;
- tester un crash entre chaque étape, notamment activation Qdrant et activation PostgreSQL ;
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
- parser versionné des intentions `explore`, `learn`, `verify`, `source`, `compare` ;
- résolution préalable des entités, acronymes, alias, `room`, `topic_path`, temporalité et
  `provenance_constraint` explicite ;
- filtre `SecurityContext` injecté dans chaque prefetch dense/BM25 et
  `applySecurityScope(queryBuilder, ctx, asOf)` obligatoire pour chaque requête SQL ;
- candidats dense/BM25 fusionnés via RRF ou DBSF sur l'alias `knowledge_current` ;
- graphe PostgreSQL utilisé après fusion pour features/voisins autorisés, jamais injecté comme
  distribution non scorée dans DBSF ;
- filtres taxonomiques ajoutés au filtre sécurité, jamais à sa place ;
- ACL, `valid_from<=as_of`, `valid_to>as_of`, `index_state=active` et `is_deleted=false`
  obligatoires ;
- `provenance_class` utilisé comme facette, diversification et boost dépendant de l'intention,
  jamais comme filtre dur implicite ni score de vérité ;
- boost borné pour entité exacte, topic, adéquation `doc_kind/knowledge_kind`, vérification et
  temporalité ;
- versions actives ;
- regroupement entité/claim/source et pénalité des quasi-doublons ;
- mode `verify` conservant supports, contradictions et plusieurs provenances ;
- rerank petit top-k flaggé OFF jusqu'au benchmark ;
- citations structurées.

Le score est composable, versionné et chaque feature est ablatable. Tester au minimum :

```text
dense
BM25
RRF
DBSF
fusion + entity/topic
fusion + entity/topic + qualité/vérification
```

Un filtre dur de provenance n'est autorisé que pour une contrainte utilisateur explicite.
Le plan de requête trace si une contrainte de provenance a été appliquée. Une requête sans
`provenance_constraint` doit prouver qu'aucun filtre dur de provenance n'a été injecté.

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

Gate G9 :

- UI, API et MCP retournent les mêmes résultats/citations pour les mêmes filtres ;
- aucun résultat étranger ne fuit par dense, BM25, résolution d'entité ou graphe SQL ;
- une requête sans `provenance_constraint` trace zéro filtre dur de provenance ;
- le mode BM25-only est visible et passe son golden dégradé ;
- le lag de projection PostgreSQL/Qdrant reste sous le seuil établi après baseline.

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
- métriques `qdrant_projection_lag_seconds`, écarts de projection et mode retrieval actif ;
- dashboards Grafana ;
- alertes stalled, circuit open, quota, index lag, backup, qualité ;
- sampling sans contenu sensible ;
- corrélation `job_id/source_id/claim_id`.

### T10.3 — Evals

Étendre les fixtures T1.5 en golden sets humains versionnés. Mesurer :

- extraction ;
- retrieval sur requêtes réellement observées ;
- exact-match, acronymes, noms développés, alias multilingues et requêtes sémantiques ;
- entity routing et topic routing ;
- recall@k, MRR/nDCG, diversité des sources et couverture des contradictions ;
- ablations dense/BM25/RRF/DBSF/boosts ;
- golden complet en mode dégradé BM25-only, mode exposé dans chaque réponse API/MCP ;
- citations ;
- vérification ;
- sécurité ;
- reproductibilité.

Ne pas fixer les seuils retrieval avant baseline sur requêtes réelles. Le golden interdit qu'un
fichier, une source ou une forme interrogative domine artificiellement la distribution. RRF/DBSF,
boosts et rerank ne passent en production que sur gain supérieur au bruit de mesure et sans
régression des requêtes exactes ou cross-provenance.

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
- `knowledge_v1` dense 768 + BM25, fusion RRF/DBSF sélectionnée sur golden réel ;
- taxonomie versionnée, ontologie entités/topics et tous indexes vérifiés ;
- `provenance_class` canonique, `wing` simple alias compatible, jamais vérité ou filtre implicite ;
- VPIN, VWAP, HMM, OBI et Mean Reversion retrouvables par acronyme, nom, alias et sujet ;
- code Prisme séparé de tout contenu runtime, bundle canonique uniquement sur Banga ;
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
