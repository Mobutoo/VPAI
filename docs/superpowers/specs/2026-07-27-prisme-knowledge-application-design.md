# Design — Prisme, application de connaissance vérifiable

> Date : 2026-07-27
> Statut : **v4 READY — revue Claude Opus 5 passe 29, 0 P0 / 0 P1**
> Nom produit : **Prisme** (nom de travail, renommable avant création du repo)
> Repo cible : `/home/mobuone/work/saas/prisme`
> Collection Qdrant cible : `knowledge_v1`
> Seed d'origine : `.planning/seeds/2026-07-26-scraping-instagram-transcription-apprentissage.md`

## 1. Décision

Prisme est une **application autonome de bout en bout**, et non un module de Palais.

- Prisme possède son interface, son API, son modèle PostgreSQL et ses workers métier.
- Palais fournit un lien de lancement et peut consommer l'API/MCP, mais ne porte aucun état Prisme.
- Open WebUI est une façade conversationnelle optionnelle.
- Jellyfin est un lecteur de sources archivées, pas un catalogue métier.
- `trading_v1` appartient à un autre projet et est **strictement hors périmètre** :
  aucune lecture de points/vecteurs/payloads, write, alias, migration, retrieval fédéré ou
  dépendance. Seul l'inventaire read-only des métadonnées de collection est autorisé pour le
  registre et la preuve d'absence de mutation G3.
- `memory_v3` reste la mémoire opérationnelle des agents.
- Prisme crée et utilise exclusivement `knowledge_v1` pour son index métier.
- Karakeep est une **Inbox documentaire et un journal de consultation optionnel** : il capture les
  URL, pages, PDF, notes et vidéos retenus par l'opérateur ou le research worker. Il ne porte ni
  verdict, ni graphe de preuves, ni vérité métier.
- L'intégration Karakeep se fait exclusivement par API REST et webhooks versionnés. Prisme ne lit
  jamais sa base SQLite et n'importe ni son index Meilisearch ni ses embeddings.

La source de vérité n'est jamais Qdrant :

| Donnée | Autorité |
|---|---|
| médias et artefacts dérivés | Banga, `/tank/knowledge` |
| catalogue, workflows, ACL, graphe de preuves | PostgreSQL Prisme sur Sese |
| recherche dense/sparse | Qdrant `knowledge_v1`, reconstructible |
| encodage dense/sparse | service Embedding Prisme pinné sur Banga |
| état local de téléchargement/reprise | SQLite du worker Waza |
| capture, lecture différée et copie de commodité d'une URL | Karakeep, non canonique |
| requête, sélection, qualification et décision de recherche | PostgreSQL Prisme |
| original pérenne autorisé et artefacts de recherche | Banga, `/tank/knowledge` |

La règle de promotion est explicite : **trouvé dans Karakeep ne signifie ni vrai, ni vérifié, ni
archivé durablement**. Prisme décide ce qui devient une source de recherche, Banga conserve ce qui
doit être canonique, et PostgreSQL porte l'évaluation intellectuelle.

## 2. Produit

### 2.1 Sujet, utilisateur et mission

Sujet concret : transformer des vidéos et documents autorisés en connaissances critiques,
traçables et testables.

Utilisateur initial : un opérateur unique de VPAI qui veut apprendre à partir de contenus
externes sans confondre discours, preuve et vérité.

Job principal de l'interface :

> Partir d'une affirmation et comprendre immédiatement qui l'a formulée, sur quelle preuve elle
> repose, ce qui la contredit, ce qui a été testé et ce que l'on peut raisonnablement retenir.

### 2.2 Vocabulaire produit

| Terme UI | Sens |
|---|---|
| Source | compte, créateur, site, publication ou corpus |
| Contenu | vidéo, audio, page, PDF ou document |
| Affirmation | proposition attribuée à une source, jamais tenue pour vraie par défaut |
| Preuve | élément externe favorable ou défavorable |
| Vérification | conclusion datée et limitée sur une affirmation |
| Expérience | protocole reproductible testant une affirmation |
| Enseignement | synthèse issue d'affirmations et preuves explicitement qualifiées |
| Dossier | regroupement de contenus, affirmations et expériences |

Le code peut utiliser `claim`, `evidence` et `knowledge_item`, mais l'interface reste en français
et emploie les termes ci-dessus de manière stable.

### 2.3 Périmètre MVP

- ingestion Instagram autorisée : posts vidéo et Reels ;
- dépôt manuel d'une vidéo ou d'un document ;
- manifeste avant téléchargement ;
- transcription, OCR et segmentation temporelle ;
- extraction d'affirmations ;
- contre-vérification par sources externes ;
- revue humaine des domaines à risque ;
- recherche hybride ;
- réponse avec citations vidéo et externes ;
- proposition et exécution d'expériences isolées ;
- catalogue, dossiers, annotations et exports Markdown/JSON.

### 2.4 Hors MVP

- conseil financier, médical ou juridique personnalisé ;
- passage automatique d'un backtest à des ordres réels ;
- ingestion de comptes privés sans autorisation explicite ;
- contournement de CAPTCHA, challenge ou rate limit ;
- application mobile native ;
- collaboration multi-organisation ;
- entraînement automatique d'un modèle ;
- fédération avec `trading_v1`.

## 3. Architecture logique

```text
Browser / PWA
     │ HTTPS + SSE
     ▼
Prisme Web + API ─────────────── PostgreSQL Prisme
Sese, VPN-only                  catalogue + workflow + preuve + ACL
     │
     ├── Qdrant `knowledge_v1`  index reconstructible
     ├── LiteLLM                extraction, synthèse, judges
     ├── Research worker        recherche externe bornée
     │       └── Karakeep       Inbox URL/API/webhooks, non autoritaire
     ├── MCP server             agents et clients
     └── Outbox                 commandes/événements
             │
       ┌─────┴────────────────────┐
       ▼                          ▼
Waza acquisition             Banga knowledge plane
official API/gallery-dl      ZFS + GPU + expériences
SQLite + spool HOT           `/tank/knowledge`
```

Prisme utilise une clé virtuelle LiteLLM dédiée, avec allocation quotidienne décidée en G0 à
l'intérieur du hard cap partagé VPAI `$5/day`. Cette clé borne la contribution Prisme mais ne
l'isole pas physiquement des dépenses des autres applications ; G0 documente la répartition et
ne relève le cap global qu'après décision explicite de doctrine/coût. Spend, restant et refus sont
métriqués ; Prisme arrête ses jobs avant d'épuiser son allocation.

### 3.1 Plan de contrôle — Sese

- application SvelteKit ;
- API REST versionnée ;
- PostgreSQL dédié `prisme` ;
- Drizzle ORM et migrations SQL ;
- outbox transactionnelle ;
- worker de recherche externe ;
- client Qdrant unique ;
- client Embedding Prisme avec dégradation BM25-only ;
- serveur MCP ;
- SSE pour la progression ;
- instrumentation OpenTelemetry.

### 3.2 Plan d'acquisition — Waza

- découverte et téléchargement séquentiels ;
- API officielle prioritaire lorsque le compte est géré ;
- gallery-dl pour un profil public explicitement autorisé ;
- cookies read-only hors Git ;
- SQLite WAL pour reprise hors connexion ;
- spool borné ;
- transfert SFTP/SSH restreint vers Banga ;
- aucun index Qdrant direct depuis le fetcher.

### 3.3 Plan de données et calcul — Banga

- dataset ZFS `tank/knowledge` ;
- promotion `incoming → library` après SHA-256 ;
- transcription/OCR/VLM GPU ;
- service d'embedding dense+sparse partagé par indexation et requête ;
- experiment-runner sans accès production ;
- snapshots et janitor auditable ;
- montage Jellyfin read-only des sources archivées ;
- aucune dépendance catalogue indispensable au boot de Banga.

Le rôle `knowledge-store` expose sur le mesh VPN une API interne mTLS/service-token, non publique :
lecture de manifest par IDs stables, transcript/artefact avec HTTP Range, limites taille/temps et
aucun chemin libre. Chaque chemin relatif est reconstruit côté serveur depuis les IDs puis validé
sous les racines canoniques. L'indexer Sese utilise cette API ; les routes utilisateur Prisme
revalident tenant/ACL en PostgreSQL puis proxifient les octets autorisés, sans URL Banga directe.

## 4. Arborescence du repo Prisme

```text
prisme/
├── AGENTS.md
├── README.md
├── .planning/
│   └── EXECUTION.md
├── package.json
├── pnpm-lock.yaml
├── svelte.config.js
├── vite.config.ts
├── drizzle.config.ts
├── src/
│   ├── app.css
│   ├── lib/
│   │   ├── components/
│   │   ├── contracts/
│   │   ├── server/
│   │   │   ├── auth/
│   │   │   ├── db/
│   │   │   ├── events/
│   │   │   ├── qdrant/
│   │   │   ├── retrieval/
│   │   │   ├── research/
│   │   │   ├── connectors/
│   │   │   │   └── karakeep/
│   │   │   └── telemetry/
│   │   └── stores/
│   └── routes/
│       ├── (app)/
│       │   ├── dashboard/
│       │   ├── ingestions/
│       │   ├── library/
│       │   ├── sources/
│       │   ├── items/
│       │   ├── claims/
│       │   ├── research/
│       │   ├── experiments/
│       │   ├── review/
│       │   ├── topics/
│       │   └── ask/
│       └── api/v1/
├── workers/
│   ├── research/
│   ├── connectors/
│   │   └── karakeep/
│   ├── consolidation/
│   └── indexer/
├── packages/
│   ├── contracts/
│   ├── embeddings/
│   ├── qdrant-schema/
│   └── evals/
├── config/
│   ├── qdrant-collections.snapshot.yml
│   └── qdrant-collections.snapshot.sha256
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── security/
│   └── evals/
├── docs/
│   ├── architecture/
│   ├── runbooks/
│   ├── adr/
│   └── rex/
├── scripts/
│   ├── verify-qdrant-registry
│   └── qdrant-registry-canonicalize.mjs
└── docker/
```

Le repo est placé sous le wing `saas`, conformément à
`docs/runbooks/MANIFESTE-CREATION-PROJET.md`. Son auto-ingestion dans `memory_v3` concerne
uniquement sa documentation et son code ; elle est indépendante de `knowledge_v1`.

### 4.1 Séparation immuable code/contenu

`/home/mobuone/work/saas/prisme` ne contient que code, migrations, contrats, tests, petites
fixtures synthétiques ou transcripts de benchmark explicitement redistribuables, documentation
et configuration sans secret. Aucun média binaire réel, transcript d'exploitation, frame, OCR,
export utilisateur, cache modèle ou volume de base n'y est écrit. Les manifests de golden
référencent licence, URL et hash ; les binaires sont réhydratés hors Git.

Les contenus sont adressés par identifiants stables, jamais par taxonomie métier :

```text
/tank/knowledge/
├── incoming/<ingestion_id>/
├── library/<tenant_id>/<corpus_id>/<item_id>/<version_id>/
│   ├── manifest.json
│   ├── source/
│   ├── derived/
│   └── knowledge/
├── research/<claim_id>/<research_run_id>/
├── experiments/<experiment_id>/<run_id>/
├── exports/<export_id>/
└── quarantine/<ingestion_id>/
```

Une arborescence telle que `/tank/knowledge/finance/VPIN` est interdite : une taxonomie évolue et
un contenu peut couvrir plusieurs sujets. PostgreSQL porte le catalogue et l'ontologie, les
manifestes Banga portent la traçabilité, Qdrant porte un index reconstructible. Le spool Waza est
transitoire, borné et placé hors de tout repo Git.

`tank/knowledge` possède une politique backup 3-2-1-1-0 Prisme avec copie offsite et restore
drill via le hub unique zerobyte v3 PULL SSH (phases P6/P6b), livrée avant G10 sans déclarer
résolu le NO-GO offsite global Banga. Prisme ne crée aucun bucket/credential parallèle ; les
gates Object-Lock/billing/escrow/prune restent ceux de zerobyte v3. P4 peut créer le
dataset lorsque le pool et son provisioning ZFS sont verts, puis active immédiatement ses
snapshots locaux ; l'offsite Prisme reste un gate terminal propre au dataset. Toute perte acceptée
ou exception de rétention est une décision explicite de l'ADR 0001.

## 5. Contrat Qdrant `knowledge_v1`

### 5.1 Invariants

1. Une seule collection pour le bounded context Prisme.
2. Les catégories vivent dans les payloads, jamais dans une collection par thème.
3. Dense, sparse et requête utilisent les mêmes fonctions partagées et versions pinées.
4. Le texte canonique reste dans le payload et dans le bundle Banga.
5. Toute version antérieure est invalidée avec `valid_to`, jamais effacée silencieusement.
6. Qdrant est reconstructible depuis PostgreSQL + Banga.
7. Aucun bootstrap ne supprime/recrée automatiquement une collection incompatible.
8. Le client est **default-deny** : seules `knowledge_v1`, `knowledge_current` et des collections
   de test au préfixe imposé sont acceptées.
   Les cibles de test exigent simultanément un mode test et un endpoint local/éphémère ; elles sont
   refusées sur le Qdrant production avant tout appel réseau.
9. `inventory/group_vars/all/qdrant_collections.yml` est l'unique registre des propriétaires et
   politiques de mutation ; l'allowlist/denylist Prisme et ses tests en sont générés.
10. Aucun code Prisme n'importe directement le client Qdrant officiel hors du package wrapper.

Avant création sur le Qdrant partagé Sese, un préflight mesure son plafond conteneur, son usage
réel et l'empreinte projetée de `knowledge_v1` avec 30 % de marge ; aucune réserve de
`memory_v3` ou `trading_v1` n'est consommée implicitement. Les drills de reconstruction tournent
sur une instance Qdrant éphémère dédiée et localement isolée, jamais sur cette production.

### 5.2 Configuration

```yaml
collection: knowledge_v1
alias: knowledge_current
on_disk_payload: true
vectors:
  dense:
    size: 768
    distance: Cosine
    hnsw_config:
      m: 16
      ef_construct: 100
sparse_vectors:
  bm25:
    modifier: idf
```

- Dense : `google/embeddinggemma-300m`, 768d, normalisé.
- Sparse : `Qdrant/bm25`, modifier IDF.
- Documents : fonction `build_doc_prompt` compatible avec l'asymétrie du contrat `memory_v3`,
  mais contextualisée pour Prisme :
  `title: {room}/{topic_path} | entities: {entity_aliases} | kind:
  {doc_kind}/{knowledge_kind} | source: {provenance_class}/{publisher_id} | text: {chunk_text}`.
- Requêtes denses : prompt SentenceTransformers nommé `Retrieval-query`.
- Sparse document/requête : fonction partagée `build_sparse_text`, versionnée, qui inclut texte,
  acronymes, noms canoniques et alias d'entités.
- `embedding_prompt_version` identifie ces transformations.
- RRF et DBSF sont implémentés ; la stratégie active est choisie sur le golden Prisme réel et
  versionnée. Aucun résultat de `memory_v3` n'est transposé sans mesure.
- `knowledge_current` pointe vers `knowledge_v1` après validation du bootstrap vide et du smoke
  de schéma G3. Les evals P10 conditionnent le passage production et toute future bascule vers
  `knowledge_v2`, pas la création initiale de l'alias.
- Une future migration crée `knowledge_v2` côte à côte puis bascule l'alias ; aucun wipe.

### 5.3 Taxonomie — adaptation maximale du Memory Manifest

Le patron du Memory Manifest est conservé, mais ses enums ne sont pas copiés : `memory_v3` classe
des fichiers de repos, Prisme classe des sources et unités de connaissance. Pour éviter qu'un
`wing=saas` de `memory_v3` soit confondu avec une provenance Prisme, le champ canonique est
`provenance_class`. `wing` reste un alias local Prisme de transition API en lecture, dérivé côté serveur et
strictement égal à `provenance_class`.

La taxonomie porte `taxonomy_namespace=prisme.knowledge`, `taxonomy_version=1` et
`ontology_version`. `taxonomy_version` versionne schémas, enums et hiérarchie ; `ontology_version`
versionne le snapshot des entités, alias et affectations de topics injecté dans les embeddings.

#### `provenance_class` — famille de provenance (`wing` alias local transitoire)

```text
social       contenu issu d'une plateforme sociale
web          page/site éditorial hors source officielle
official     régulateur, administration, documentation officielle
academic     publication ou base scientifique
internal     note ou document explicitement fourni par l'utilisateur
derived      synthèse Prisme issue d'une ou plusieurs provenances
experimental résultat produit par un protocole Prisme
```

Fallback : `internal`, uniquement pour un dépôt manuel dont la provenance est connue.
Une provenance inconnue est mise en quarantaine, jamais classée arbitrairement.

`provenance_class` n'est jamais un score de vérité. Il sert à expliquer la provenance, diversifier les
résultats, appliquer un boost dépendant de l'intention et filtrer lorsque l'utilisateur le demande
explicitement. Il ne devient jamais un filtre dur implicite. Une extraction mono-source hérite du
champ de sa source. Toute synthèse `derived` et tout résultat `experimental` conserve un
`source_provenance_classes[]` non vide décrivant ses entrées.

#### `room` — domaine de connaissance

Registre initial :

```text
general, finance, technology, operations, business,
science, health, law, creative, personal-development
```

- une room est attribuée par règles déterministes puis confirmée par classifieur ;
- `general` est le fallback explicite ;
- tout ajout de room modifie un registre versionné et ses tests ;
- `misc` est interdit.

#### `topic_path` — routage hiérarchique

`room` reste un domaine large. Le routage fin utilise un chemin contrôlé et ses ancêtres :

```text
finance/market-microstructure/order-flow/toxicity/vpin
finance/execution/benchmarks/vwap
finance/quantitative-finance/regime-models/hmm
finance/market-microstructure/order-book/imbalance
finance/systematic-trading/strategy-families/mean-reversion
```

`topic_path` désigne la feuille canonique ; `topic_ancestors[]` contient les parents filtrables.
Les changements de libellé passent par alias et migration versionnée, jamais par réécriture
silencieuse.
Invariant : le premier segment de `topic_path` est strictement égal à `room`.

#### Entités canoniques

Une entité représente l'objet étudié indépendamment des documents qui en parlent :

```text
entity_kind =
  concept | metric | indicator | benchmark | feature | model |
  hypothesis | market-mechanism | strategy-family | strategy |
  procedure | risk-rule
```

VPIN est par exemple une entité `indicator`, VWAP un `benchmark`, HMM un `model`, OBI une `feature`
et Mean Reversion une `strategy-family`. Une unité peut référencer plusieurs `entity_ids[]`.
Les acronymes, noms développés, synonymes et variantes linguistiques vivent dans
`entity_aliases`, puis sont injectés dans le texte sparse.

Tout ajout/retrait d'alias ou toute reclassification incrémente `ontology_version` et déclenche un
réencodage tracé des points affectés. Un corpus ne mélange pas silencieusement plusieurs snapshots
d'ontologie actifs.

#### `doc_kind` — représentation indexée

```text
source-document, transcript, visual-observation, knowledge-unit,
synthesis, experiment-protocol, experiment-result
```

`doc_kind` est unique et mutuellement exclusif. Le rôle intellectuel est séparé :

```text
knowledge_kind =
  definition | claim | explanation | formula | procedure |
  strategy | example | comparison | caveat | lesson
```

| `doc_kind` | `knowledge_kind` |
|---|---|
| `source-document`, `transcript`, `visual-observation` | null |
| `knowledge-unit` | une valeur non nulle |
| `synthesis` | `explanation`, `comparison`, `caveat` ou `lesson` |
| `experiment-protocol`, `experiment-result` | null |

La fonction probatoire n'est pas intrinsèque au document : `supports`, `contradicts`,
`contextualizes` ou `neutral` appartient d'abord à l'arête PostgreSQL `claim_evidence`. Elle peut
être dénormalisée dans Qdrant pour un besoin mesuré, sans devenir l'autorité.

#### Compatibilité `repo` / `relative_path`

- `repo` contient le slug stable du corpus, analogue au dépôt source de `memory_v3` ;
- le même identifiant est exposé avec le nom métier `corpus_id` ;
- `repo` est dérivé côté serveur de `corpus_id` et ne peut pas être fourni séparément par un client ;
- `relative_path` pointe vers l'artefact canonique sous `/tank/knowledge`, sans préfixe absolu ;
- pour un point indexable, `relative_path` commence par l'une des racines canoniques :
  `library/<tenant>/<corpus>/<item>/<version>/{source|derived|knowledge}/...`,
  `research/<claim>/<run>/...` ou `experiments/<experiment>/<run>/...` ;
- `incoming/`, `exports/` et `quarantine/` sont physiques et validées par le store mais ne
  produisent jamais de point Qdrant ni de `relative_path` indexable ;
- le changement de username ou de titre ne modifie ni `repo` ni `source_id`.

### 5.4 Payload commun obligatoire

| Champ | Type | Rôle |
|---|---|---|
| `provenance_class` | keyword | provenance canonique |
| `wing` | keyword | alias local transitoire dérivé de `provenance_class` |
| `room` | keyword | domaine |
| `doc_kind` | keyword | représentation indexée |
| `repo` | keyword | compatibilité : corpus stable |
| `relative_path` | keyword | chemin canonique relatif |
| `topic` | keyword | libellé principal compatible Memory Manifest |
| `tags` | keyword[] | facettes libres contrôlées |
| `taxonomy_namespace` | keyword | `prisme.knowledge` |
| `taxonomy_version` | integer | version du registre |
| `ontology_version` | integer | snapshot entités/alias/topics |
| `valid_from` | datetime | début de validité |
| `valid_to` | datetime | fin de validité, sentinelle `9999-12-31T00:00:00Z` si active |
| `text` | text | unité verbatim/indexée |
| `schema_version` | keyword | `knowledge.v1` |
| `embedding_model` | keyword | modèle dense |
| `embedding_model_version` | keyword | révision exacte modèle/tokenizer |
| `embedding_dim` | integer | 768 |
| `sparse_model` | keyword | modèle sparse et version |
| `chunking_strategy_version` | keyword | stratégie de chunking |
| `prompt_version` | keyword | extraction/construction du texte canonique |
| `embedding_prompt_version` | keyword | seul formatage asymétrique document/requête envoyé au modèle |
| `host_origin` | keyword | producteur technique |
| `source_kind` | keyword | type de source |
| `content_sha256` | keyword | intégrité |
| `chunk_index` | integer | position déterministe |
| `chunk_total` | integer | nombre de chunks |
| `index_generation` | integer | génération d'encodage, croissante par `knowledge_item_id` |
| `index_state` | keyword | `staging` ou `active` |
| `deleted_at` | datetime/null | retrait logique |
| `is_deleted` | bool | filtre runtime, PostgreSQL conserve le null métier |

### 5.5 Payload métier

| Champ | Type |
|---|---|
| `tenant_id` | keyword |
| `acl_scope` | keyword[] |
| `corpus_id` | keyword |
| `source_id` | keyword |
| `knowledge_item_id` | keyword |
| `artifact_id` | keyword |
| `canonical_id` | keyword |
| `publisher_id` | keyword |
| `platform` | keyword |
| `canonical_url` | keyword |
| `language` | keyword |
| `topic_path` | keyword |
| `topic_ancestors` | keyword[] |
| `entity_ids` | keyword[] |
| `entity_kinds` | keyword[] |
| `knowledge_kind` | keyword/null |
| `source_provenance_classes` | keyword[] |
| `published_at` | datetime/null |
| `created_at` | datetime |
| `start_ms` / `end_ms` | integer/null |
| `claim_ids` | keyword[] |
| `verification_status` | keyword |
| `risk_level` | keyword |
| `evidence_level` | keyword |
| `experiment_status` | keyword/null |
| `last_verified_at` | datetime/null |

Enums versionnés :

```text
verification_status = pending | supported | partially_supported |
                      contested | refuted | insufficient_evidence |
                      not_verifiable | time_sensitive
risk_level          = low | medium | high
evidence_level      = source-only | secondary | primary | replicated
experiment_status   = proposed | reviewed | sandbox | reproduced |
                      accepted | rejected | inconclusive
index_state         = staging | active
```

Deux classes exhaustives de payload sont explicites.

Immuables par point :

```text
provenance_class, wing, room, doc_kind, repo, relative_path,
taxonomy_namespace, taxonomy_version, ontology_version, valid_from, text,
schema_version, embedding_model, embedding_model_version, embedding_dim,
sparse_model, chunking_strategy_version, prompt_version,
embedding_prompt_version, host_origin, source_kind, content_sha256,
chunk_index, chunk_total, index_generation, tenant_id, corpus_id, source_id,
knowledge_item_id, artifact_id, canonical_id, publisher_id, platform,
canonical_url, language, published_at, created_at, start_ms, end_ms,
topic_path, topic_ancestors, entity_ids, entity_kinds, knowledge_kind,
source_provenance_classes
```

`index_generation` appartient à cette partition immuable ; une mutation exige un nouveau point
ID. Un test rend la partition immuable/mutable exhaustive et refuse tout champ obligatoire non
classé.

Mutables par `set_payload` uniquement :

```text
topic, tags, acl_scope, claim_ids, verification_status, risk_level,
evidence_level, experiment_status, last_verified_at, index_state,
valid_to, is_deleted, deleted_at
```

PostgreSQL reste l'autorité des champs mutables. L'outbox et un reconciler idempotent propagent les
changements ; `qdrant_projection_lag_seconds` et les écarts de projection sont mesurés. Une
mutation de projection ne modifie jamais les vecteurs ni l'identité du point.

### 5.6 Payload indexes

Indexes `keyword` :

```text
provenance_class, room, doc_kind, repo, tags, taxonomy_namespace,
topic_path, topic_ancestors, entity_ids, entity_kinds, knowledge_kind,
source_provenance_classes,
schema_version, embedding_model, embedding_model_version, sparse_model,
chunking_strategy_version, prompt_version,
embedding_prompt_version, index_state,
host_origin, source_kind, tenant_id, acl_scope, corpus_id, source_id,
knowledge_item_id, artifact_id, canonical_id, canonical_url,
publisher_id, platform, language, claim_ids, verification_status,
risk_level, evidence_level, experiment_status
```

Indexes `datetime` :

```text
valid_from, valid_to, published_at, created_at, last_verified_at
```

Indexes `integer` :

```text
taxonomy_version, ontology_version, start_ms, end_ms, chunk_index, index_generation
```

Index booléen : `is_deleted`.

Le bootstrap vérifie type et présence de chaque index. Toute divergence produit un échec lisible
et un plan de migration ; elle ne déclenche jamais de correction destructive implicite.
`relative_path` et `content_sha256` restent filtrables dans PostgreSQL et ne reçoivent pas d'index
Qdrant à haute cardinalité sans mesure démontrant son utilité.
`wing` reste un payload local transitoire égal à `provenance_class`; les filtres legacy `wing` sont
réécrits vers ce dernier et aucun index Qdrant redondant n'est créé.

### 5.7 Identifiants et versionnement

Identité source :

```text
<platform>:<publisher_stable_id>:<content_stable_id>:<media_index>
```

`source_id` porte cette identité du contenu original. `canonical_id` est l'UUID PostgreSQL stable
de la lignée logique d'une unité de connaissance à travers ses versions. `knowledge_item_id`
identifie une version précise de cette unité ; `artifact_id` identifie l'artefact Banga exact dont
elle dérive. Plusieurs versions partagent donc `canonical_id`, mais jamais `knowledge_item_id`.

Identité point :

```text
UUIDv5(PRISME_NAMESPACE,
  join(SEP, knowledge_item_id, artifact_id, canonical_id, doc_kind, knowledge_kind,
       chunk_index, content_sha256, schema_version, taxonomy_version, ontology_version,
       embedding_model_version, sparse_model, chunking_strategy_version, prompt_version,
       embedding_prompt_version, index_generation))
```

`SEP` est exclusivement l'octet `\x1f`; le séparateur littéral `:` est interdit. La concaténation
inter-runtime utilise UTF-8 et la sentinelle ASCII `-`
pour toute valeur nullable, notamment `knowledge_kind`; une valeur métier réelle égale à `-` est
interdite.

`content_sha256` est toujours le SHA-256 du `text` exact de l'unité indexée, pas celui du média ni
du bundle. Deux unités issues du même chunk ont des `knowledge_item_id` distincts.

Lorsqu'un contenu change :

1. transaction PostgreSQL : nouvelle version et événements outbox en attente ;
2. nouveau point distinct upserté avec `index_state=staging` ;
3. contrôle de comptage/retrieval avec `buildValidationFilter()`, réservé à l'indexeur : ACL et
   tenant obligatoires, `staging` explicitement autorisé ;
4. nouveau point Qdrant passe `active`, sans invalider l'ancien ;
5. nouvelle version PostgreSQL devient active ; jusqu'ici la revalidation SQL continue de servir
   l'ancienne, puis autorise la nouvelle sans fenêtre vide ;
6. pendant la coexistence Qdrant, le retrieval déduplique par identité canonique et prend le
   `valid_from` actif le plus récent confirmé en PostgreSQL ;
7. l'ancienne version PostgreSQL devient superseded, puis l'ancien point reçoit `valid_to` ;
8. un reconciler corrige tout état partiel après crash.

La fenêtre entre activation Qdrant et activation PostgreSQL est tracée. Le runtime ne présente
jamais une connaissance dont l'enregistrement PostgreSQL n'est pas actif ; un test de crash entre
chaque étape prouve la convergence.

Un test échoue si l'ancien et le nouvel artefact produisent le même point ID après changement de
modèle, chunker ou prompt.

Un réencodage sans nouvelle version métier utilise `index_generation` dans `index_points` :
nouvelle génération Qdrant en staging puis active, même `knowledge_item_id` PostgreSQL déjà actif,
coexistence dédupliquée vers la génération la plus récente validée, puis expiration de l'ancienne.
Le point ID inclut la génération ; le retrieval déduplique par `knowledge_item_id` et garde la
génération active maximale validée dans le ledger. Le crash entre chaque étape conserve au moins
une génération servable ; aucune fausse nouvelle version PostgreSQL n'est créée.

### 5.8 Exemple minimal

```json
{
  "provenance_class": "social",
  "wing": "social",
  "room": "finance",
  "doc_kind": "knowledge-unit",
  "knowledge_kind": "claim",
  "entity_kinds": ["indicator"],
  "entity_ids": ["entity:vpin"],
  "topic_path": "finance/market-microstructure/order-flow/toxicity/vpin",
  "topic_ancestors": [
    "finance",
    "finance/market-microstructure",
    "finance/market-microstructure/order-flow"
  ],
  "taxonomy_namespace": "prisme.knowledge",
  "taxonomy_version": 1,
  "ontology_version": 1,
  "repo": "instagram-17841400000000000",
  "corpus_id": "instagram-17841400000000000",
  "relative_path": "library/personal/instagram-17841400000000000/item-ABC/v1/knowledge/learning.v1.json",
  "topic": "VPIN et toxicité du flux d'ordres",
  "tags": ["instagram", "trading", "market-microstructure", "vpin"],
  "valid_from": "2026-07-27T00:00:00Z",
  "valid_to": "9999-12-31T00:00:00Z",
  "text": "L'auteur affirme que ...",
  "schema_version": "knowledge.v1",
  "embedding_model": "google/embeddinggemma-300m",
  "embedding_model_version": "<revision-pinned>",
  "embedding_dim": 768,
  "sparse_model": "Qdrant/bm25@<version-pinned>",
  "chunking_strategy_version": "semantic-timestamp-v1",
  "prompt_version": "knowledge-doc-v1",
  "embedding_prompt_version": "embeddinggemma-asymmetric-v1",
  "host_origin": "banga",
  "source_kind": "instagram-video",
  "content_sha256": "...",
  "chunk_index": 0,
  "chunk_total": 1,
  "index_state": "active",
  "deleted_at": null,
  "is_deleted": false,
  "tenant_id": "personal",
  "acl_scope": ["owner"],
  "source_id": "instagram:17841400000000000:ABC:0",
  "knowledge_item_id": "ki-vpin-claim-v1",
  "artifact_id": "artifact-learning-v1",
  "canonical_id": "canonical-vpin-claim",
  "publisher_id": "17841400000000000",
  "platform": "instagram",
  "language": "fr",
  "claim_ids": ["..."],
  "verification_status": "pending",
  "risk_level": "high",
  "evidence_level": "source-only"
}
```

## 6. PostgreSQL

Tables minimales :

```text
users
idempotency_records
webhook_delivery_receipts
sources
ingestion_jobs
ingestion_items
media_artifacts
knowledge_items
knowledge_entities
entity_aliases
entity_relations
knowledge_item_entities
strategy_specs
claims
research_runs
research_queries
research_candidates
research_candidate_merges
external_connectors
external_resources
external_resource_merges
research_candidate_resources
external_sync_attempts
claim_evidence
claim_verifications
experiments
experiment_runs
topics
knowledge_item_topics
annotations
collections
collection_items
review_tasks
corpus_versions
answers
answer_citations
index_points
outbox_events
audit_events
```

Contraintes :

- UUID applicatifs stables ;
- `source_id` unique par plateforme ;
- transitions d'état contrôlées en base ;
- clés d'idempotence uniques ;
- aucune URL signée/CDN comme identité ;
- provenance et audit append-only ;
- unicité des noms canoniques dans un namespace, alias normalisés et relations typées ;
- `strategy_specs` versionne hypothèses, paramètres, univers, horizon, coûts, risques et métriques ;
- ACL présentes dès le premier schéma, même en mono-utilisateur ;
- suppression logique avant purge physique ;
- Qdrant point IDs enregistrés pour audit, sans devenir l'autorité ;
- `index_points` relie point, item, artefact, collection, versions et validité ;
- `answers`/`answer_citations` figent les preuves réellement présentées ;
- leur relecture reste dynamique côté sécurité : chaque citation repasse par
  `applySecurityScope(ctx, securityAsOf=now())`, indépendamment de l'`asOf` historique de la
  question ; une citation révoquée/takedown est masquée et
  la réponse GET calcule `effective_visibility_status=stale_redacted` sans écrire. L'événement
  transactionnel de révocation/takedown persiste ensuite idempotemment
  `answers.visibility_status=stale_redacted`; aucune fuite du texte ou de l'URL retirés. Enum
  versionné : `active|stale_redacted` ;
- `research_runs` porte `claim_id` nullable, tenant/ACL, `topic_path` autoritaire/versionné, état,
  budget et horodatages ; les
  requêtes et candidats lui sont rattachés par FK ;
- `research_candidates` est unique par `(research_run_id, canonical_url_hash)` sur les lignes
  `merged_into_candidate_id IS NULL` et porte la
  qualification propre au run : rôle, décision et motif de rejet. Un bump de canonicalisation
  exécute d'abord un dry-run sans mutation. Une collision aux qualifications identiques est
  fusionnable avec audit ; une collision aux rôles/décisions divergents fait créer et committer
  une tâche de revue dans une transaction séparée, puis bloque la mutation. Après résolution
  seulement, le recalcul et les fusions s'exécutent dans une nouvelle transaction atomique.
  L'unique reste immédiat et compatible `ON CONFLICT`; sous lock, une double passe par hashes
  sentinelles `migration:<migration_id>:<row_id>` couvre aussi les permutations avant les hashes
  finaux. Une CHECK n'autorise ce préfixe que si `canonicalization_migration_id` concorde et est
  ensuite remis à null. Une fusion identique repointe les liaisons, ajoute la ligne append-only
  `research_candidate_merges(loser_id, survivor_id)`, tombstone le perdant via
  `merged_into_candidate_id` et interdit tout DELETE. L'upsert répète le prédicat partiel ; une
  liaison ressource déjà présente côté survivant conserve l'ancienne et tombstone la redondante
  via `merged_into_link_id`. Un rollback conserve donc la tâche de revue. Aucune nouvelle version
  n'est activée avant résolution ;
- les chaînes candidates se résolvent récursivement vers la racine, profondeur max 8, compression
  sous lock et rejet de tout cycle/dépassement ;
- `external_resources` représente une projection externe dédupliquée, unique par
  `(connector_id, canonical_url_hash)` sur les seules lignes actives
  `merged_into_resource_id IS NULL`; `(connector_id, external_id)` reste unique sur toutes les
  lignes, y compris tombstonées, afin d'interdire sa réutilisation. La
  version de canonicalisation est une colonne non-clé. Sous advisory lock et gel des écritures,
  un bump exécute dry-run, fusionne/repointe les perdants, place les survivants sur les mêmes
  sentinelles protégées par CHECK, puis écrit les hashes finaux avant commit ; il couvre ainsi
  les permutations sous unique immédiat. Elle ne
  porte ni rôle ni décision de recherche et n'a pas de FK directe vers un run ;
- `research_candidate_resources` relie plusieurs qualifications par run à une unique ressource
  externe, unique `(research_candidate_id, external_resource_id)` pour les lignes
  `merged_into_link_id IS NULL`, et conserve l'historique sans écrasement ;
- une fusion repointe transactionnellement `research_candidate_resources` vers le survivant,
  ajoute une ligne append-only `external_resource_merges(loser_id, survivor_id)` et conserve le
  perdant tombstoné avec `merged_into_resource_id`. Les `external_sync_attempts` restent
  immuables et se résolvent par cette chaîne ; aucune suppression physique du perdant ;
- si une liaison active identique existe déjà après repointage, la plus ancienne reste active et
  la redondante est tombstonée via `merged_into_link_id`, sans DELETE ni perte d'historique ;
- le reconciler suit la merge-map vers le survivant, ignore les perdants tombstonés et ne les
  ressuscite jamais par `external_id`. Il résout récursivement jusqu'à la racine avec profondeur
  maximale 8 ; la transaction de merge verrouille la chaîne, compresse les chemins et refuse tout
  cycle ou dépassement ;
- chaque ressource conserve URL originale, URL résolue, URL canonique,
  `url_canonicalization_version`, hash versionné et identifiants Prisme séparés ;
- `canonical_url` des ressources externes reste hors index Qdrant : la déduplication et la
  canonicalisation sont exclusivement autoritaires dans PostgreSQL. Ce champ externe est
  distinct du `canonical_url` documentaire du payload `knowledge-point.v1`, qui peut être indexé
  pour retrouver la source canonique d'un item ;
- une collision divergente crée un `review_tasks.kind=canonicalization_collision` avec les IDs,
  versions, hashes et qualifications conflictuels ; elle est distincte des revues de claim et
  d'entité ;
- `research_queries` conserve requête, provider, budget et session. Les résultats bruts non
  examinés restent éphémères ; `research_candidates` conserve toute URL effectivement ouverte,
  analysée, citée ou explicitement rejetée ;
- `tenant_id` et `acl_scope` sont obligatoires sur `research_queries`, `research_candidates`,
  `external_connectors`, `external_resources`, `research_candidate_resources` et
  `external_sync_attempts`. Un connecteur lie exactement un tenant à un compte Karakeep ;
- aucun secret Karakeep, corps HTML complet ou asset binaire dans PostgreSQL.
- `idempotency_records` conserve tenant, route, clé, hash de requête, statut/réponse minimale et
  expiration 24 h, unique par `(tenant_id, route, key)` avec purge bornée auditée.
- `webhook_delivery_receipts` conserve tenant/ACL, connecteur, job, bookmark, opération et
  expiration 30 jours, unique par
  `(tenant_id, connector_id, job_id, bookmark_id, operation)` avec purge auditée.

## 7. API

Préfixe : `/api/v1`.

### Ingestion

```text
POST   /ingestions
GET    /ingestions/:id
POST   /ingestions/:id/discover
POST   /ingestions/:id/approve
POST   /ingestions/:id/stop
POST   /ingestions/:id/retry
GET    /ingestions/:id/events
```

### Bibliothèque

```text
GET    /sources
GET    /sources/:id
GET    /items
GET    /items/:id
GET    /items/:id/transcript
GET    /items/:id/artifacts
POST   /items/:id/reanalyze
POST   /items/:id/takedown
DELETE /sources/:id
GET    /entities
GET    /entities/:id
GET    /topics/:id
```

### Preuves

```text
GET    /claims
GET    /claims/:id
POST   /claims/:id/verify
GET    /claims/:id/verification
POST   /claims/:id/review
GET    /review-tasks
POST   /review-tasks/:id/resolve
```

### Expériences

```text
POST   /claims/:id/experiments
GET    /experiments/:id
POST   /experiments/:id/approve
POST   /experiments/:id/run
POST   /experiments/:id/stop
GET    /experiments/:id/runs
GET    /experiments/:id/events
```

### Recherche

```text
POST   /search
POST   /ask
GET    /answers/:id/citations
GET    /research/:id
GET    /research/:id/events
GET    /research/:id/resources
POST   /research/:id/resources/:resource_id/save
POST   /research/:id/resources/:resource_id/retry-sync
POST   /research/:id/resources/:resource_id/promote
```

### Connecteurs

```text
GET    /connectors
POST   /connectors/karakeep/:connector_id/test
POST   /connectors/karakeep/:connector_id/webhooks
POST   /connectors/karakeep/:connector_id/reconcile
```

Le webhook Karakeep est authentifié par Bearer token comparé en temps constant, rate-limité,
borné en taille et dédupliqué par `(connector_id, jobId, bookmarkId, operation)` pendant 30 jours,
au-delà des trois tentatives totales/deux retries upstream pinnés. `payload.userId` doit égaler
`connector.external_owner_id`. Le
webhook reste un signal d'invalidation non fiable : Prisme relit l'état via l'API officielle et
applique seulement une observation dont `external_state_read_at` est plus récente. Les appels
sortants utilisent un jeton API provenant du coffre. Les réponses API enregistrent
`connector_id`, `external_id` et l'URL profonde, jamais les jetons.

La route POST `/connectors/karakeep/:connector_id/webhooks` est un récepteur d'événements, pas une
route de création de webhook. Elle est exemptée de la session utilisateur mais refuse toute
requête sans Bearer valide pour ce `connector_id` exact. Le hash du token est stocké/résolu par
connecteur et un token d'un autre connecteur est rejeté avant lecture du payload ; toutes les
autres routes connecteur exigent la session et les ACL habituelles.

Toutes les mutations acceptent `Idempotency-Key`. Les jobs longs retournent `202` avec un lien de
statut. Les erreurs suivent Problem Details JSON et n'exposent jamais de secrets ni de contenu brut
non autorisé.
Chaque route possède rate limit, quota de coût et budget maximum configurables.

## 8. Retrieval

Le retrieval distingue cinq intentions : `explore`, `learn`, `verify`, `source` et `compare`.
L'intention détermine les types de connaissance, la diversification et la pondération de
provenance ; elle ne relâche jamais la sécurité.

Pipeline :

1. authentifier et construire un `SecurityContext` non optionnel ;
2. analyser la requête en intention, entités, alias, `room`, `topic_path`, temporalité et
   `provenance_constraint` explicite ;
3. construire le filtre `tenant_id + acl_scope + index_state=active + is_deleted=false +
   valid_from<=as_of + valid_to>as_of` ;
4. appliquer le `SecurityContext` à **chaque** accès : `buildSecurityFilter()` dans chaque
   prefetch Qdrant et `applySecurityScope(queryBuilder, ctx, asOf)` dans chaque requête SQL ;
5. résoudre entity/alias/topic avant retrieval, puis récupérer les candidats dense et BM25 ;
6. fusionner les deux distributions Qdrant avec RRF ou DBSF, stratégie choisie par évaluation ;
7. revalider chaque candidat top-k dans PostgreSQL via `applySecurityScope(ctx, asOf)` et écarter
   toute ligne absente, révoquée, expirée, supprimée ou non active avant rescoring/citation/retour,
   même si la projection Qdrant est en retard ; sur-récupérer au plus `min(3*k, 200)` et mesurer
   l'épuisement avant de compléter k.
   Enrichir ensuite ces seuls candidats autorisés via le graphe PostgreSQL ; la branche SQL
   n'entre pas comme distribution non scorée dans DBSF, elle fournit des features et voisins
   explicitement tracés ;
8. appliquer un rescoring applicatif borné : entité exacte, topic, adéquation
   `doc_kind/knowledge_kind`,
   qualité de vérification, temporalité et provenance conditionnée par l'intention ;
9. pour chaque `knowledge_item_id`, garder d'abord l'`index_generation` active maximale confirmée
   par `index_points`, puis regrouper par entité/claim/source et dédupliquer les versions par
   `canonical_id` en gardant le `knowledge_item_id` actif le plus récent ; pénaliser les
   quasi-doublons ;
10. en mode `verify`, préserver preuves favorables et contradictoires et diversifier les
   provenances ;
11. reranker un petit top-k uniquement après benchmark ;
12. exclure les claims réfutés des recommandations, sans les cacher des vues d'audit ;
13. générer avec citations puis vérifier que chaque affirmation matérielle est supportée.

Politique des métadonnées :

| Champ | Effet par défaut |
|---|---|
| ACL, tenant, validité, suppression, index actif | filtre dur |
| contrainte utilisateur explicite | filtre dur |
| `entity_ids`, alias exacts, `topic_path` | boost fort/routage |
| `room`, `doc_kind`, `knowledge_kind` | boost ou filtre selon intention |
| `provenance_class` | boost conditionnel, facette et diversification |
| vérification, niveau de preuve, fraîcheur | qualité conditionnelle |

`provenance_class` n'est filtré durement que pour une demande explicite telle que « sources académiques
uniquement ». Une recherche de vérification ne filtre jamais implicitement la provenance, car elle
doit pouvoir retrouver la source sociale originale, l'autorité officielle, la littérature et les
contre-preuves.

Le runtime lit l'alias `knowledge_current`, jamais le nom physique en dur. Le wrapper refuse de
construire une requête sans `SecurityContext`; les appels directs Qdrant sont interdits par lint.
`buildValidationFilter()` est une API séparée, non exportée au web/MCP, qui conserve tenant et ACL
mais autorise `index_state=staging` uniquement pour les validations de promotion.

Le late interaction/multivecteur n'est pas activé au MVP. Il possède un spike séparé et n'est
adopté que si le golden set réel démontre un gain supérieur au coût.

### 8.1 Service d'embedding

Un service interne unique sur Banga sert :

```text
POST /v1/embed/documents
POST /v1/embed/query
POST /v1/embed/sparse
GET  /health/ready
```

- image, modèle, tokenizer, FastEmbed et prompt versions pinnés ;
- même image pour backfill, ingestion incrémentale et requête ;
- API accessible uniquement depuis Prisme/les workers sur le mesh et authentifiée par jeton
  de service rotatable ;
- batching et cache par SHA ;
- aucune donnée persistante autre que le cache de modèles ;
- parité CPU/GPU testée sur fixtures ;
- la même image immuable tourne sur Sese en mode `sparse-query-only`, sans modèle dense ;
- si Banga/dense est indisponible, Prisme annonce le mode dégradé et utilise ce sidecar pour une
  recherche BM25-only ;
- un test de parité Banga/Sese vérifie le vecteur sparse sur chaque release ;
- aucune retombée silencieuse vers un autre modèle.

## 9. Recherche et vérification

La recherche externe est une boucle bornée :

```text
claim → question falsifiable → recherche favorable → recherche contradictoire
→ qualification des sources → couverture → conclusion ou preuves insuffisantes
```

Règles :

- fournisseurs de recherche interchangeables ;
- allowlists pour domaines sensibles ;
- base URL Karakeep issue exclusivement de l'allowlist Ansible, jamais d'une valeur libre fournie
  par l'API ;
- canonicalisation, résolution DNS publique et filtre SSRF avant toute insertion outbox, sur les
  chemins worker, sauvegarde manuelle et reconciler ; chaque redirection est bornée et revalidée ;
- une URL refusée par Prisme n'est jamais déléguée au crawler Karakeep ;
- priorité aux sources primaires ;
- URL canonique, date, éditeur, hash et date de consultation conservés ;
- chaque URL effectivement ouverte, analysée, citée ou explicitement rejetée est journalisée dans
  PostgreSQL puis, si `karakeep_enabled=true`, envoyée de manière asynchrone vers Karakeep par
  l'outbox ; le fake prouve ce contrat lorsque le connecteur est désactivé ;
- une URL seulement apparue dans une page de résultats n'est pas sauvegardée par défaut ;
- la requête et la stratégie restent dans Prisme ; une note récapitulative Karakeep par
  `research_run_id` est optionnelle et ne remplace jamais le journal PostgreSQL ;
- les listes et tags Karakeep sont une projection reconstructible, par exemple
  `Prisme / Recherches`, `prisme`, `research:<research_run_id>`, `topic:<slug>`,
  `role:<research_run_id>:<role>`, `status:<research_run_id>:<status>` et
  `decision:<research_run_id>:<decision>`. Les enums fermés sont :
  `role=supporting|contradicting|context|primary_source|rejected` avec champ nullable (`null`
  signifie absence de rôle et n'appartient pas à l'enum),
  `status=opened|analyzed|cited|archived_banga` et
  `decision=pending|selected|rejected|promotion_requested|promoted`. Un rôle `null` n'émet aucun
  tag `role:*` ; il n'émet jamais la chaîne littérale `role:<run>:null` ;
- le tag `topic:<slug>` dérive exclusivement du dernier segment normalisé du `topic_path`
  autoritaire et versionné, jamais d'un texte produit par LLM ;
- la déduplication repose sur URL canonique et identifiant externe ; les paramètres de tracking,
  fragments non sémantiques et redirections sont normalisés avant création ;
- `canonicalizeUrl()` est un contrat partagé versionné. Son hash inclut
  `url_canonicalization_version`; tout changement produit un recalcul tracé et une
  réconciliation de `research_candidates` et `external_resources`, jamais une dérive silencieuse ;
- un échec Karakeep ne bloque ni la vérification ni l'enregistrement Prisme : état
  `pending|synced|failed_retryable|failed_terminal|disabled|deleted_external`, retry borné et
  réconciliation ;
- Karakeep peut capturer une copie de commodité ; seul un bundle promu, hashé et manifesté sur
  Banga constitue l'archive canonique ;
- la promotion utilise une commande séparée et écrit sous
  `research/<claim_id>/<research_run_id>/`. Sans claim attaché, la commande reste
  `awaiting_claim` et n'invente aucun chemin canonique ;
- toute suppression ou modification dans Karakeep est un événement externe à réconcilier, jamais
  une instruction implicite de purge Banga ou PostgreSQL ;
- copie locale uniquement lorsque les droits le permettent ;
- une citation inaccessible n'est pas une preuve ;
- un LLM ne peut pas attribuer seul `supported` à un claim à risque élevé ;
- revue humaine obligatoire pour finance, santé, droit et sécurité.

## 10. Interface

### 10.1 Direction visuelle

Métaphore : **table de travail d'un enquêteur de connaissances**. La preuve est visible et
manipulable ; l'IA reste en arrière-plan.

Signature : une **ligne de preuve** continue relie verticalement Source → Affirmation → Source
externe → Expérience → Enseignement. Chaque nœud indique son état et ouvre le passage exact.

Palette :

| Token | Couleur | Usage |
|---|---|---|
| `--paper-cool` | `#F2F5F6` | fond principal |
| `--ink` | `#182229` | texte et structure |
| `--petrol` | `#176073` | actions et liens |
| `--oxide` | `#B85C38` | contradiction/refutation |
| `--proof` | `#28785B` | preuve supportée |
| `--amber` | `#B8871B` | incertitude/revue |

Typographie :

- titres : `Sora`, géométrique mais contenue ;
- corps : `Atkinson Hyperlegible`, lecture longue et accessibilité ;
- preuves/données : `IBM Plex Mono`, timestamps, hashes et statuts.

Pas de glow, pas de cartes uniformes partout, pas de score circulaire décoratif. Les séparateurs
expriment la provenance ou la chronologie.

### 10.2 Workspace principal

```text
┌──────────────┬───────────────────────────────┬────────────────────┐
│ Source       │ Affirmation sélectionnée      │ Ligne de preuve    │
│ vidéo/texte  │ formulation + contexte        │ externe/test       │
│ timeline     │ limites + enseignement        │ verdict daté       │
└──────────────┴───────────────────────────────┴────────────────────┘
```

- desktop : trois panneaux redimensionnables ;
- tablette : source repliable, preuve persistante ;
- mobile : source → affirmation → preuve en pile, navigation par ancres ;
- `MM:SS` ouvre exactement la séquence vidéo ;
- un statut n'est jamais indiqué uniquement par une couleur ;
- clavier complet, focus visible, réduction des animations respectée.

### 10.3 Pages

```text
/dashboard
/ingestions/new
/ingestions/:id
/library
/sources/:id
/items/:id
/claims/:id
/research/:id
/research/:id/resources
/experiments/:id
/review
/topics/:id
/ask
/settings
/settings/connectors
```

La vue recherche affiche séparément : requêtes, résultats non retenus, sources examinées, état de
synchronisation Karakeep, qualification, motifs de rejet et état d'archivage Banga. Elle expose
les actions `Enregistrer dans Karakeep`, `Réessayer`, `Ouvrir dans Karakeep` et
`Promouvoir vers Banga` selon les droits. Une indisponibilité Karakeep est visible mais n'empêche
pas de poursuivre la vérification.

### 10.4 États produit

Les écrans doivent être conçus pour :

- vide : action claire pour ajouter une première source ;
- découverte : manifeste en construction ;
- attente d'approbation ;
- traitement partiel ;
- preuve insuffisante ;
- contradiction ;
- révision requise ;
- service externe indisponible ;
- reconstruction d'index ;
- contenu supprimé mais connaissance conservée.

## 11. Sécurité

- VPN-only derrière Caddy ;
- session signée ou SSO partagé, décision avant implémentation ;
- RBAC minimal `owner`, `reviewer`, `reader`, `service`;
- ACL ajoutée à toute requête Qdrant ;
- secrets via le coffre VPAI, jamais dans le repo ;
- cookies Instagram read-only ;
- jeton Karakeep via le coffre, jamais exposé au navigateur, aux logs ou aux artefacts ;
- webhook Karakeep authentifié par Bearer token, dédupliqué sur
  `(connector_id, jobId, bookmarkId, operation)` et convergent par relecture API ;
- une suppression Karakeep ne déclenche jamais implicitement une purge Prisme/Banga ;
- contenu récupéré toujours traité comme donnée non fiable ;
- aucune instruction d'un média/page ne déclenche un outil ;
- research browser isolé, egress borné, protection SSRF ;
- ffmpeg/OCR non privilégiés, filesystem read-only hors workspace ;
- experiment-runner sans secrets production ;
- aucun adaptateur de courtage live ;
- une expérience financière utilise uniquement des données fournies/validées dans son sandbox,
  sans connecteur marché et sans lecture de `trading_v1` ;
- audit append-only des approbations, suppressions et verdicts ;
- scan de fuite de secrets dans logs, traces et artefacts.

## 12. Observabilité et évaluation

### 12.1 Traces

OpenTelemetry de bout en bout :

```text
submit, discover, fetch, transfer, transcribe, ocr, extract,
research, verify, review, experiment, index, retrieve, rerank, answer
```

Attributs : job/source/claim IDs, modèle, prompt, durée, coût, tokens, cache hit, statut.
Le contenu complet n'est pas exporté par défaut.

### 12.2 Golden sets

Jeux séparés :

- `extraction`: claims attendus et timestamps ;
- `retrieval`: requêtes réelles, acronymes/alias, exact-match, questions sémantiques, cibles
  réparties, routage entity/topic et recherche cross-provenance ;
- `retrieval-degraded`: le même jeu en BM25-only, avec mode explicitement visible dans l'API ;
- `citation`: support, pertinence et indépendance ;
- `verification`: verdict humain et limites ;
- `security`: prompt injection, poisoning, SSRF ;
- `experiments`: reproductibilité et respect des gates.

### 12.3 Gates qualité initiales

| Mesure | Gate MVP |
|---|---|
| schéma JSON valide | 100 % |
| citation ouvre une source existante | 100 % |
| claims matériels avec citation dans `/ask` | 100 % |
| claim à risque élevé `supported` sans humain | 0 |
| doublon après retry | 0 |
| résultat ou citation servi après révocation ACL/takedown pendant lag | 0 |
| citation figée relue après retrait | masquée, answer `stale_redacted` |
| fusion ressource | 0 liaison dupliquée, 0 sync attempt perdu, perdant résolu vers survivant |
| retrieval recall@5 | baseline puis seuil fixé sur golden réel |
| entity routing recall@k | baseline puis seuil par type de requête |
| diversité de provenance en mode verify | couverture attendue sur cas vérifiables |
| filtre provenance implicite sans contrainte | 0, vérifié par trace de plan de requête |
| projection PostgreSQL → Qdrant | lag baseline puis seuil/alerte fixé |
| restauration bundle → Qdrant | 100 % sur canary |
| URL ouvertes/analysées/citées/rejetées capturées | 100 % sur fake ou instance de test activée |
| SERP non examinés sauvegardés | 0 |
| doublon canonicalisation multi-runs | 0 bookmark, qualification par run conservée |
| suppression Karakeep causant une cascade canonique | 0 |
| ordre réel possible depuis experiment-runner | 0 |

## 13. SLO et capacité

SLO à mesurer avant de figer :

- disponibilité API/UI ;
- p95 recherche hors génération ;
- p95 affichage fiche depuis PostgreSQL ;
- âge maximal de la file ;
- délai source → connaissance indexée ;
- coût IA par minute de média ;
- espace Banga par heure de source ;
- taux de succès par étape ;
- couverture de vérification ;
- dérive du golden set.

Les premiers canaries établissent les baselines. Aucun objectif arbitraire de latence ou de qualité
n'est déclaré avant mesure.

## 14. Déploiement

### Sese

Nouveau rôle VPAI :

```text
roles/prisme/
├── defaults/main.yml
├── tasks/main.yml
├── handlers/main.yml
├── templates/prisme.env.j2
├── templates/docker-compose-prisme.yml.j2
└── molecule/default/
```

Intégrations :

- image pinnée dans `inventory/group_vars/all/versions.yml` ;
- `prisme_enabled=false` par défaut garde le rôle entier dans `site.yml`; il ne passe à true
  qu'après gate capacité vert, afin de ne jamais bloquer les rôles étrangers ;
- compose propriétaire de web/API+MCP `1 GiB`, outbox `384 MiB`, research worker `512 MiB`,
  navigateur isolé `1536 MiB`, connecteur Karakeep `384 MiB`, indexer `512 MiB`, consolidation
  `384 MiB`, sidecar `sparse-query-only` `1 GiB` et proxy DB `128 MiB`; les hard limits totalisent
  `5 888 MiB` et les réservations explicites `2 944 MiB`. Le proxy joint `prisme_internal` au backend à IP
  fixe ; le service `prisme` rejoint aussi explicitement les réseaux externes
  `javisi_frontend` de Caddy et `javisi_backend` pour joindre Qdrant/LiteLLM par leurs noms Docker
  internes. Le proxy DB n'accepte que le CIDR source `prisme_internal`; un test depuis
  `javisi_backend` vers le proxy doit échouer. HBA autorise ce `/32` pour tous les rôles puis refuse toute connexion à la DB Prisme
  depuis le reste du backend, superuser `postgres` inclus. L'IP backend fixe du service `prisme`
  est ensuite rejetée vers toutes les DB avant le broad allow backend ; Prisme accède à sa DB
  uniquement via proxy. Après l'allow DB Prisme/proxy, le HBA rejette aussi l'IP proxy vers toute
  autre DB. Les IP `.240`/`.241` sont vérifiées libres par inspect avant déploiement, sans mutation
  de l'IPAM existant ; toutes les règles HBA Prisme sont conditionnées à `prisme_enabled`, dont le
  rendu false reste byte-identique. Reload sans restart ;
- seuls le research worker et le navigateur isolé rejoignent `javisi_egress`, avec egress
  allowlisté et tests SSRF ; web/API, outbox, indexer, consolidation, sidecar sparse et proxy DB
  en sont exclus ;
- DB/user PostgreSQL dédiés ;
- route Caddy VPN-only ;
- route Caddy Prisme limitée aux deux CIDR du registre. Karakeep, sur le même hôte, envoie ses
  webhooks via le réseau Docker externe partagé `prisme_connector_internal`, marqué
  `internal: true` et joint explicitement par les deux composes, vers `http://prisme:3000`, pas
  via la route VPN Caddy ;
- réseau Docker interne ;
- secrets avec `no_log` ;
- healthchecks et limites ;
- backup PostgreSQL ;
- dashboards/alertes.

### Karakeep

Le rôle VPAI `roles/karakeep/` rend l'instance optionnelle déployable et testée sur fake avant G7.
Il ne la déploie réellement qu'après présence du service/réseau Prisme en T11.2, si
`karakeep_enabled=true` et si le gate de capacité propre à cette branche est vert :

Le web Karakeep rejoint `javisi_frontend` pour Caddy. Seuls ses composants de crawl sortant
rejoignent `javisi_egress` sous allowlist et contrôles SSRF ; le réseau interne
`prisme_connector_internal` reste le seul transport Karakeep↔Prisme.

Les FQDN Prisme et Karakeep sont publiés par le split-DNS Headscale de Seko-VPN
(`roles/vpn-dns`), résolvent l'IP Tailscale Sese et n'exigent aucun A public grâce à ACME DNS-01.
Les appels sortants Prisme→Karakeep utilisent `http://karakeep:3000` sur
`prisme_connector_internal`, jamais le FQDN Caddy.

- FQDN `karakeep.ewutelo.cloud`, VPN-only sur les deux CIDR du registre Caddy ;
- Karakeep `v0.32.0`, commit upstream
  `b9b252ecb6d2af379192778ec24f766d4cd60da3`, image pinnée par digest ;
- snapshot OpenAPI
  `packages/contracts/karakeep/openapi-v0.32.0.json`, SHA-256
  `69b85ed2cdbfb0904bd04c83dd3d3d24b44838815ebd2031d0ad89b9cc7f7f24` ;
- compte opérateur local mono-tenant, sans dépendance SSO au MVP ;
- API key sortante et Bearer entrant distincts au coffre. Le Bearer entrant, généré par Prisme,
  est configuré idempotemment par setup Playwright dans `/settings/webhooks` pour le connecteur
  et les événements `created`, `crawled`, `edited`, `deleted`; credentials et captures sont
  caviardés. L'URL est
  `http://prisme:3000/api/v1/connectors/karakeep/:connector_id/webhooks` sur le réseau interne. Il
  fait au plus 100 caractères et n'est pas une variable d'environnement Karakeep ;
- backup des données Karakeep et restore smoke ; Meilisearch reste un index reconstructible ;
- healthchecks et ressources mesurées avant ajustement de capacité ;
- `karakeep_enabled=false` par défaut dans Prisme.

Avant déploiement réel, le rôle réserve les limites web `2 GiB`, Chrome `2 GiB`, Meilisearch
`1536 MiB`, puis exige
`MemAvailable + RSS_Karakeep_déjà_running - somme(limites Karakeep) >= 1 GiB`, PSI mémoire
`avg10 < 10 %`, aucune activité swap-in/swap-out soutenue sur 15 minutes, espace libre
`/ >= 25 GiB` et utilisation `/ <= 75 %`. Ajouter du swap ne peut pas rendre ce gate vert. La
baseline Sese interdit actuellement ce déploiement réel par réserve RAM/disque, sans bloquer les
branches fake et `karakeep_enabled=false`.

Le rôle `roles/prisme/` possède un pré-check distinct avant son propre déploiement sur Sese. Les
hard limits totalisent `5 888 MiB`, les réservations Docker explicites `2 944 MiB`; le gate exige
`MemAvailable + RSS_Prisme_déjà_running -
max(somme(réservations), RSS_p95_mesuré×1,3) >= 1 GiB`, un ratio hard limits actifs / `MemTotal`
`<= 1,5`, et
`RSS_étrangers_p95×1,3 + réservations_Prisme + 1 GiB <= MemTotal`. L'overcommit borné est accepté
dans l'ADR 0001. Puis PSI mémoire
`avg10 < 10 %`, absence de swap-in/swap-out soutenu sur 15 minutes, espace libre `/ >= 15 GiB`
et utilisation `/ <= 80 %`. Ajouter du swap ne peut pas rendre ce gate vert. La branche de
déploiement Prisme reste rouge jusqu'à mesure/remédiation conforme ; elle ne bloque pas les
builds, tests et déploiements isolés précédents.
Si ce gate reste rouge après remédiations réversibles, le projet livre tous les artefacts et
preuves non-production mais reste `AWAITING_G0_CAPACITY_DECISION`; il ne revendique ni production
accessible ni DoD complète avant décision de placement/capacité.

L'usage et le déploiement de l'image AGPL-3.0 sont acceptés pour ce composant isolé. Aucun code
Karakeep n'est copié, lié ou modifié dans Prisme sans nouvel ADR et revue de licence.

### Waza

```text
roles/prisme-fetcher/
```

### Banga

Dans le dépôt frère :

```text
roles/knowledge-store/
roles/knowledge-worker/
roles/knowledge-embedding/
roles/experiment-runner/
```

Un gate de placement en lecture seule inventorie LXC, Docker, GPU/passthrough, RAM, disque et
charges avant tout worker, embedding ou experiment runner. La cible doit être un LXC existant
déjà approuvé, Docker-capable et GPU-capable, ou un futur `lxc-prisme-knowledge`; `lxc-chat` et
`lxc-infer` ne sont jamais présumés conformes. Créer un LXC ou étendre un passthrough GPU exige
une décision G0 placement/capacité avant mutation.
Si aucune cible n'est déjà approuvée ou si le credential GHCR Banga manque, l'état est
`AWAITING_G0_BANGA_PLACEMENT`; seuls P0–P3 et P8 sur fixtures sont alors atteignables.

`tank/knowledge` est déclaré dans le `zfs_datasets` autoritaire de Banga sous le nom pool-relatif
`knowledge` (`recordsize: 1M`, `compression: lz4`, quota mesuré, `reservation: none`) afin que le provisioning
ZFS et `disk-guard` le couvrent. Le rôle `knowledge-store` vérifie dataset, mountpoint, owner et
quota mais ne crée pas un dataset invisible au guard. Le quota n'est applicable que si
l'utilisation projetée, réserve snapshots comprise, reste au plus à 80 % et laisse au moins
5 TiB libres.

Les images Prisme consommées sur Banga sont tirées uniquement par digest avec le
`vault_ghcr_pull_token` du coffre Banga sous `no_log`, sans valeur par défaut ; une absence de
credential bloque le déploiement.

## 15. Décisions différées

| Décision | Gate |
|---|---|
| nom définitif et domaine | avant scaffold du repo |
| auth session locale ou SSO | avant première route privée |
| upgrade Karakeep/OpenAPI | nouvelle revue de snapshot avant bump depuis v0.32.0 |
| activer Karakeep en production | après fake contractuel, backup et gate G7 |
| SSO Karakeep | différé ; compte local mono-tenant VPN-only au MVP |
| fournisseur de recherche web | benchmark qualité/coût/conditions |
| moteur OCR/transcription | benchmark 10 vidéos |
| LXC Banga dédié | mesure isolation/capacité |
| reranker | gain mesuré sur golden réel |
| fusion RRF ou DBSF | benchmark Prisme sur requêtes réelles |
| multivecteur visuel | gain mesuré sur requêtes visuelles |
| Langfuse | OpenTelemetry/Grafana insuffisant pour les evals |

## 16. Sources internes

- `docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md`
- `docs/superpowers/specs/2026-06-10-rag-v3-contracts.md`
- `docs/superpowers/specs/2026-06-05-memory-system-rebuild-design.md`
- `docs/superpowers/specs/2026-06-07-memory-graph-layer-design.md`
- `docs/runbooks/MANIFESTE-CREATION-PROJET.md`
- `.planning/notes/2026-07-22-rag-etat-des-lieux-angles-morts.md`
- `docs/design/2026-07-23-refonte-backup-zerobyte-orchestrateur-seko.md`
- `../banga/.planning/STATE.md`
- `../banga/docs/superpowers/specs/2026-07-24-lxc-chat-design.md`
