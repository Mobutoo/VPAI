# Design — Prisme, application de connaissance vérifiable

> Date : 2026-07-27
> Statut : **v2 post-revue Claude Opus 5**, prêt pour décisions G0, aucune mutation autorisée
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
  aucun read, write, alias, migration, retrieval fédéré ou dépendance.
- `memory_v3` reste la mémoire opérationnelle des agents.
- Prisme crée et utilise exclusivement `knowledge_v1` pour son index métier.

La source de vérité n'est jamais Qdrant :

| Donnée | Autorité |
|---|---|
| médias et artefacts dérivés | Banga, `/tank/knowledge` |
| catalogue, workflows, ACL, graphe de preuves | PostgreSQL Prisme sur Sese |
| recherche dense/sparse | Qdrant `knowledge_v1`, reconstructible |
| encodage dense/sparse | service Embedding Prisme pinné sur Banga |
| état local de téléchargement/reprise | SQLite du worker Waza |

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
     ├── MCP server             agents et clients
     └── Outbox                 commandes/événements
             │
       ┌─────┴────────────────────┐
       ▼                          ▼
Waza acquisition             Banga knowledge plane
official API/gallery-dl      ZFS + GPU + expériences
SQLite + spool HOT           `/tank/knowledge`
```

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

## 4. Arborescence du repo Prisme

```text
prisme/
├── AGENTS.md
├── README.md
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
│   ├── consolidation/
│   └── indexer/
├── packages/
│   ├── contracts/
│   ├── embeddings/
│   ├── qdrant-schema/
│   └── evals/
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
└── docker/
```

Le repo est placé sous le wing `saas`, conformément à
`docs/runbooks/MANIFESTE-CREATION-PROJET.md`. Son auto-ingestion dans `memory_v3` concerne
uniquement sa documentation et son code ; elle est indépendante de `knowledge_v1`.

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
9. `trading_v1`, `memory_v3`, `videoref_styles`, `semantic_cache` et `palais_memory`
   restent dans une denylist de défense en profondeur.
10. Aucun code Prisme n'importe directement le client Qdrant officiel hors du package wrapper.

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
- Documents : fonction `build_doc_prompt` compatible avec le contrat `memory_v3`
  (`title: {wing}/{repo}/{relative_path}{section} | text: {chunk_text}`).
- Requêtes denses : prompt SentenceTransformers nommé `Retrieval-query`.
- Sparse document/requête : fonction partagée `build_sparse_text`, versionnée.
- `embedding_prompt_version` identifie ces transformations.
- Fusion par défaut : RRF.
- `knowledge_current` pointe vers `knowledge_v1` après validation du bootstrap et des evals.
- Une future migration crée `knowledge_v2` côte à côte puis bascule l'alias ; aucun wipe.

### 5.3 Taxonomie — adaptation maximale du Memory Manifest

Les trois axes `wing`, `room`, `doc_kind` sont conservés et restent orthogonaux.

#### `wing` — famille de provenance

```text
social       contenu issu d'une plateforme sociale
web          page/site éditorial hors source officielle
official     régulateur, administration, documentation officielle
academic     publication ou base scientifique
internal     note ou document explicitement fourni par l'utilisateur
experimental résultat produit par un protocole Prisme
```

Fallback : `internal`, uniquement pour un dépôt manuel dont la provenance est connue.
Une provenance inconnue est mise en quarantaine, jamais classée arbitrairement.

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

#### `doc_kind` — nature de l'unité

```text
transcript, visual-observation, concept, claim, evidence,
procedure, example, caveat, summary, lesson,
experiment-protocol, experiment-result, source-document
```

#### Compatibilité `repo` / `relative_path`

- `repo` contient le slug stable du corpus, analogue au dépôt source de `memory_v3` ;
- le même identifiant est exposé avec le nom métier `corpus_id` ;
- `repo` est dérivé côté serveur de `corpus_id` et ne peut pas être fourni séparément par un client ;
- `relative_path` pointe vers l'artefact canonique sous `/tank/knowledge`, sans préfixe absolu ;
- le changement de username ou de titre ne modifie ni `repo` ni `source_id`.

### 5.4 Payload commun obligatoire

| Champ | Type | Rôle |
|---|---|---|
| `wing` | keyword | provenance |
| `room` | keyword | domaine |
| `doc_kind` | keyword | nature |
| `repo` | keyword | compatibilité : corpus stable |
| `relative_path` | keyword | chemin canonique relatif |
| `topic` | keyword | sujet principal |
| `tags` | keyword[] | facettes libres contrôlées |
| `valid_from` | datetime | début de validité |
| `valid_to` | datetime/null | fin de validité |
| `text` | text | unité verbatim/indexée |
| `schema_version` | keyword | `knowledge.v1` |
| `embedding_model` | keyword | modèle dense |
| `embedding_model_version` | keyword | révision exacte modèle/tokenizer |
| `embedding_dim` | integer | 768 |
| `sparse_model` | keyword | modèle sparse et version |
| `chunking_strategy_version` | keyword | stratégie de chunking |
| `prompt_version` | keyword | prompt documentaire |
| `embedding_prompt_version` | keyword | prompts asymétriques document/requête |
| `host_origin` | keyword | producteur technique |
| `source_kind` | keyword | type de source |
| `content_sha256` | keyword | intégrité |
| `chunk_index` | integer | position déterministe |
| `chunk_total` | integer | nombre de chunks |
| `index_state` | keyword | `staging` ou `active` |
| `deleted_at` | datetime/null | retrait logique |

### 5.5 Payload métier

| Champ | Type |
|---|---|
| `tenant_id` | keyword |
| `acl_scope` | keyword[] |
| `corpus_id` | keyword |
| `source_id` | keyword |
| `publisher_id` | keyword |
| `platform` | keyword |
| `canonical_url` | keyword |
| `language` | keyword |
| `published_at` | datetime/null |
| `created_at` | datetime |
| `start_ms` / `end_ms` | integer/null |
| `claim_id` | keyword/null |
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

### 5.6 Payload indexes

Indexes `keyword` :

```text
wing, room, doc_kind, repo, topic, tags,
schema_version, embedding_model, embedding_model_version, sparse_model,
chunking_strategy_version, prompt_version,
embedding_prompt_version, index_state,
host_origin, source_kind, tenant_id, acl_scope, corpus_id, source_id,
publisher_id, platform, language, claim_id, verification_status,
risk_level, evidence_level, experiment_status
```

Indexes `datetime` :

```text
valid_from, valid_to, published_at, created_at, last_verified_at, deleted_at
```

Indexes `integer` :

```text
embedding_dim, start_ms, end_ms, chunk_index
```

Le bootstrap vérifie type et présence de chaque index. Toute divergence produit un échec lisible
et un plan de migration ; elle ne déclenche jamais de correction destructive implicite.
`relative_path` et `content_sha256` restent filtrables dans PostgreSQL et ne reçoivent pas d'index
Qdrant à haute cardinalité sans mesure démontrant son utilité.

### 5.7 Identifiants et versionnement

Identité source :

```text
<platform>:<publisher_stable_id>:<content_stable_id>:<media_index>
```

Identité point :

```text
UUIDv5(PRISME_NAMESPACE,
  artifact_id + ":" + canonical_id + ":" + doc_kind + ":" + chunk_index + ":" +
  content_sha256 + ":" + schema_version + ":" + embedding_model_version + ":" +
  chunking_strategy_version + ":" + prompt_version + ":" + embedding_prompt_version)
```

Lorsqu'un contenu change :

1. transaction PostgreSQL : nouvelle version et événements outbox en attente ;
2. nouveau point distinct upserté avec `index_state=staging` ;
3. contrôle de comptage/retrieval par un chemin de validation interne ;
4. nouveau point passe `active`, puis ancien point reçoit `valid_to` ;
5. le retrieval déduplique transitoirement par identité canonique et prend le `valid_from`
   le plus récent ;
6. version PostgreSQL devient active ;
7. un reconciler corrige tout état partiel après crash.

Un test échoue si l'ancien et le nouvel artefact produisent le même point ID après changement de
modèle, chunker ou prompt.

### 5.8 Exemple minimal

```json
{
  "wing": "social",
  "room": "finance",
  "doc_kind": "claim",
  "repo": "instagram-17841400000000000",
  "corpus_id": "instagram-17841400000000000",
  "relative_path": "instagram/17841400000000000/2026/07/ABC/derived/learning.v1.json",
  "topic": "gestion du risque",
  "tags": ["instagram", "trading", "risk-management"],
  "valid_from": "2026-07-27T00:00:00Z",
  "valid_to": null,
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
  "tenant_id": "personal",
  "acl_scope": ["owner"],
  "source_id": "instagram:17841400000000000:ABC:0",
  "publisher_id": "17841400000000000",
  "platform": "instagram",
  "language": "fr",
  "claim_id": "...",
  "verification_status": "pending",
  "risk_level": "high",
  "evidence_level": "source-only"
}
```

## 6. PostgreSQL

Tables minimales :

```text
users
sources
ingestion_jobs
ingestion_items
media_artifacts
knowledge_items
claims
research_sources
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
- ACL présentes dès le premier schéma, même en mono-utilisateur ;
- suppression logique avant purge physique ;
- Qdrant point IDs enregistrés pour audit, sans devenir l'autorité.
- `index_points` relie point, item, artefact, collection, versions et validité ;
- `answers`/`answer_citations` figent les preuves réellement présentées.

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
GET    /research/:id/events
```

Toutes les mutations acceptent `Idempotency-Key`. Les jobs longs retournent `202` avec un lien de
statut. Les erreurs suivent Problem Details JSON et n'exposent jamais de secrets ni de contenu brut
non autorisé.
Chaque route possède rate limit, quota de coût et budget maximum configurables.

## 8. Retrieval

Pipeline par défaut :

1. authentifier et construire un `SecurityContext` non optionnel ;
2. construire le filtre `tenant_id + acl_scope + index_state=active + deleted_at=null +
   valid_from<=as_of + (valid_to=null ou valid_to>as_of)` ;
3. injecter ce filtre dans **chaque** prefetch dense top-30 et BM25 top-30 ;
4. fusion RRF ;
5. rerank top-5 uniquement après benchmark ;
6. regrouper par `claim_id`/`source_id` pour éviter la domination d'une source ;
7. dédupliquer toute coexistence transitoire de versions ;
8. exclure les claims réfutés des recommandations ;
9. générer avec citations ;
10. vérifier que chaque affirmation de réponse possède une citation qui la supporte.

Le runtime lit l'alias `knowledge_current`, jamais le nom physique en dur. Le wrapper refuse de
construire une requête sans `SecurityContext`; les appels directs Qdrant sont interdits par lint.

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
- priorité aux sources primaires ;
- URL canonique, date, éditeur, hash et date de consultation conservés ;
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
/experiments/:id
/review
/topics/:id
/ask
/settings
```

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
- `retrieval`: requêtes réelles, cibles réparties ;
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
| retrieval recall@5 | baseline puis seuil fixé sur golden réel |
| restauration bundle → Qdrant | 100 % sur canary |
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
- DB/user PostgreSQL dédiés ;
- route Caddy VPN-only ;
- réseau Docker interne ;
- secrets avec `no_log` ;
- healthchecks et limites ;
- backup PostgreSQL ;
- dashboards/alertes.

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

Un LXC dédié n'est créé que si `lxc-chat` ne satisfait pas les exigences d'isolation et de capacité.

## 15. Décisions différées

| Décision | Gate |
|---|---|
| nom définitif et domaine | avant scaffold du repo |
| auth session locale ou SSO | avant première route privée |
| fournisseur de recherche web | benchmark qualité/coût/conditions |
| moteur OCR/transcription | benchmark 10 vidéos |
| LXC Banga dédié | mesure isolation/capacité |
| reranker | gain mesuré sur golden réel |
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
