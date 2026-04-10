# Plan — Memoire IA locale Waza -> Qdrant central

Date: 2026-04-09
Statut: Draft
Portee: conception et plan d'implementation d'une memoire unifiee pour agents IA, prioritairement a partir des repos presents sur Waza.

## 1. Resume

L'objectif est de construire une memoire semantique exploitable par Codex, Claude Code et les autres agents, en partant d'un principe simple:

- les sources principales actuelles sont sur **Waza** ou sur **GitHub**
- l'indexation doit etre **deterministe**
- les embeddings doivent etre **locaux**
- le stockage vectoriel reste **centralise dans Qdrant sur Sese-AI**
- les hooks IA sont un bonus, pas le mecanisme principal

Le lot 1 se concentre sur **Waza**.  
Les documents de travail presents sur Sese-AI seront traites dans un lot ulterieur.

## 2. Objectifs du projet

Construire une memoire qui permette:
- de retrouver du code, des REX, des plans, des specs, des docs et des configs par similarite semantique
- d'avoir une nomenclature uniforme des documents indexes
- de reduire la perte de contexte entre agents et entre sessions
- de donner a n8n un pipeline deterministe pour relancer et superviser l'indexation
- de preparer une migration propre des collections Qdrant existantes vers un schema unique

## 3. Contraintes et hypotheses

## 3.1 Contraintes techniques

- Waza est un **Raspberry Pi 5 16 Go**
- Waza execute deja des services lourds selon les periodes
- Sese-AI heberge deja Qdrant et d'autres services critiques
- il existe deja plusieurs collections dans Qdrant, avec schemas et usages heterogenes
- les hooks IA ne sont pas fiables a 100%

## 3.2 Contraintes d'architecture

- pas d'appel a un provider d'embeddings externe pour cette memoire
- pas de dependance forte a LiteLLM pour les embeddings memoire
- pas de FastAPI en lot 1 si elle n'apporte pas un vrai gain
- pas de destruction immediate des collections legacy

## 3.3 Hypotheses retenues

- Qdrant reste sur Sese-AI
- l'indexation principale est faite sur Waza, localement
- les repos sont disponibles sur Waza ou clonables depuis GitHub
- n8n orchestre les jobs, mais ne fait pas lui-meme la lecture bas niveau des fichiers

## 4. Decisions de conception

## 4.1 Embeddings

Le pipeline memoire n'utilisera pas LiteLLM comme moteur d'embedding principal.

Raison:
- LiteLLM ajoute une couche API/proxy
- il peut reposer sur des modeles distants
- cela ne repond pas au besoin "local"

Le worker d'indexation embarquera donc directement un modele d'embeddings local.

## 4.2 LlamaIndex

LlamaIndex est retenu comme bibliotheque pour:
- loading de documents
- chunking
- enrichissement metadata
- mapping vers Qdrant
- retrieval et recherche structuree

LlamaIndex ne sera pas expose via FastAPI en phase 1.

Raison:
- le besoin premier est batch/deterministe
- une CLI suffit pour l'implementation initiale
- une API HTTP pourra etre ajoutee plus tard si necessaire

## 4.3 Orchestration

L'orchestration sera partagee entre:
- **scripts CLI locaux** pour l'indexation
- **n8n** pour les declenchements, logs, retries et notifications
- **timers systemd** possibles pour les scans locaux simples

Principe:
- n8n pilote
- les scripts indexent

## 4.4 Positionnement du worker

Le worker d'indexation principal sera deploye sur **Waza**.

Raison:
- les repos sources y sont deja presents
- pas besoin de rsync comme chemin principal
- pas besoin de parsing distant via SSH
- moins de couplage et moins de fragilite

## 4.5 Qdrant

Qdrant reste central sur **Sese-AI**.

Raison:
- coherence du stockage memoire
- pas de duplication vectorielle
- continuite avec l'existant
- simplifie la consommation par d'autres services

## 4.6 Collection cible

La phase 1 utilisera une **collection Qdrant unique**:
- `memory_v1`

Le typage du contenu sera gere par les metadonnees payload, notamment:
- `doc_kind`
- `source_kind`
- `tags`

Raison:
- recherches cross-type plus simples
- moins de complexite d'orchestration
- meilleur point de depart pour les agents

## 5. Modele d'embedding recommande

## 5.1 Choix lot 1

Modele recommande:
- `EmbeddingGemma-300M`

Raisons:
- tres bon niveau de qualite retrieval pour sa taille
- multilingue FR/EN, mieux adapte au corpus reel
- meilleur candidat pour une memoire commune code + docs + REX + plans
- evite de sacrifier trop tot la qualite semantique

## 5.2 Alternatives

### `Snowflake/snowflake-arctic-embed-xs`

Points forts:
- meilleure qualite retrieval attendue
- 384 dimensions
- bon compromis qualite/taille

Limite:
- moins bon choix sur corpus FR/EN que le modele principal
- plutot fallback si `EmbeddingGemma-300M` s'avere trop couteux sur Waza

### `intfloat/multilingual-e5-small`

Points forts:
- tres pertinent en FR/EN
- 384 dimensions

Limite:
- plus lourd encore
- moins confortable pour Waza

## 5.3 Decision pratique

Phase 1:
- deployer avec `EmbeddingGemma-300M`

Phase benchmark ulterieure:
- comparer avec `snowflake-arctic-embed-xs` si la charge Waza est trop forte

## 5.4 Contraintes d'usage du modele

La mise en oeuvre devra respecter le format de prompt recommande par la doc officielle `EmbeddingGemma`.

Pour les requetes:
- `task: search result | query: {content}`

Pour les documents:
- `title: {title | "none"} | text: {content}`

Implications:
- il faut conserver un `title` exploitable par chunk si possible
- les chunks documents ne doivent pas etre embeddes comme des requetes
- la logique d'embedding doit etre explicite dans le code et testee en retrieval

## 5.5 Critere de bascule du modele

Le pilote doit inclure un benchmark retrieval avec seuil de decision explicite.

Corpus de validation:
- 20 requetes reelles
- evaluation manuelle des resultats

Critere:
- si le bon fichier n'apparait pas dans le top 3 pour plus de 30% des requetes,
  `EmbeddingGemma-300M` est considere insuffisant pour ce lot
- dans ce cas, bascule vers `snowflake-arctic-embed-xs`

Les mesures CPU, RAM et temps d'indexation restent importantes, mais la qualite retrieval est le critere principal de decision.

## 6. Architecture cible

## 6.1 Architecture generale

```text
Repos locaux sur Waza
    ->
Worker LlamaIndex local sur Waza
    ->
Embeddings locaux sur Waza
    ->
Upsert vers Qdrant sur Sese-AI via VPN
    ->
Recherche et consommation par agents / outils
```

## 6.2 Composants

### Waza

- role Ansible `llamaindex-memory-worker`
- environnement Python dedie
- modele d'embedding local
- scripts d'indexation
- cache d'etat d'indexation
- file locale persistante pour retry en cas d'echec reseau
- timer local ou execution distante pilotee par n8n

### Sese-AI

- Qdrant existant
- nouvelles collections memoire
- workflows n8n de declenchement et supervision
- scripts de maintenance/audit Qdrant

## 6.3 Flux d'indexation principal

1. Le worker determine la liste des repos a traiter
2. Il detecte les fichiers eligibles
3. Il filtre selon extensions, taille et dossiers exclus
4. Il determine ce qui a change depuis le dernier run
5. Il chunk les fichiers
6. Il genere les embeddings localement
7. Il tente l'upsert des chunks dans Qdrant
8. En cas d'echec reseau, il stocke les lots dans une file locale persistante
9. Il met a jour l'etat local d'indexation
10. n8n journalise et notifie le resultat

## 6.4 Connectivite Waza -> Qdrant

Le worker sur Waza ne doit pas utiliser un endpoint backend Docker interne.

Il doit utiliser:
- l'IP Tailscale de Sese-AI ou un endpoint equivalent accessible via VPN
- la cle API Qdrant stockee dans le Vault

La variable `memory_worker_qdrant_url` doit donc pointer vers l'endpoint reel accessible depuis Waza.

## 7. Taxonomie des contenus

## 7.1 Familles de contenu

Chaque chunk doit etre classe dans une categorie metier stable.

Categories cibles:
- `code`
- `doc`
- `rex`
- `plan`
- `spec`
- `config`
- `workflow`
- `official-docs`

## 7.2 Regles de classification initiales

Exemples:
- `docs/REX-*` ou `docs/rex/` -> `rex`
- `docs/plans/` -> `plan`
- `docs/specs/` -> `spec`
- `scripts/n8n-workflows/*.json` -> `workflow`
- `*.py`, `*.ts`, `*.go`, `*.sh` -> `code`
- `*.yml`, `*.yaml`, `*.j2`, `*.env` -> `config`
- `README*`, `*.md`, `*.rst`, `*.txt` hors chemins specifiques -> `doc`

## 7.3 Tags normalises

Chaque point Qdrant doit avoir des tags standardises.

Exemples:
- `kind:code`
- `kind:doc`
- `kind:rex`
- `kind:plan`
- `kind:spec`
- `host:waza`
- `repo:vpai`
- `scope:infra`
- `lang:python`
- `lang:yaml`

## 7.4 Champ `topic`

Le lot 1 peut ajouter un champ `topic` au payload, mais uniquement avec une extraction prudente.

Ordre de priorite recommande:
- `H1` markdown si le contenu est de type `doc`, `rex`, `plan`, `spec`
- nom du role Ansible si le fichier est sous `roles/<role>/...`
- nom du repo si aucun meilleur signal n'est disponible
- dossier parent en dernier fallback

Regle:
- si le signal est ambigu ou trop faible, laisser `topic` vide
- un `topic` vide vaut mieux qu'un `topic` bruité qui degrade les filtres retrieval

## 7.5 Chunking strategy

Le chunking doit etre defini explicitement avant implementation.

### Code

Strategie:
- chunk par symbole logique quand c'est faisable
- sinon fallback sliding window avec overlap

Approche initiale:
- Python: fonctions / classes si detectables
- JS/TS/TSX/JSX/Go: heuristiques simples ou fallback texte
- fallback universel si parsing impossible

### Markdown / documentation

Strategie:
- chunk par sections `#`, `##`, `###`
- sous-chunk si une section depasse la taille cible

### YAML / Jinja2 / env / config

Strategie:
- par bloc logique
- ou fichier entier si petit et coherent

### SQL

Strategie:
- par statement ou bloc logique commente

### Fallback universel

Pour tout contenu non reconnu:
- chunk de taille fixe
- overlap stable

Chaque point doit inclure:
- `chunking_strategy_version`
- `chunking_kind`

## 8. Schema metadata Qdrant cible

Chaque point doit embarquer un payload standard.

Champs minimaux proposes:
- `schema_version`
- `embedding_model`
- `embedding_dim`
- `chunking_strategy_version`
- `ref_doc_id`
- `repo`
- `namespace`
- `host_origin`
- `source_kind`
- `doc_kind`
- `topic`
- `relative_path`
- `filename`
- `language`
- `tags`
- `git_commit_sha`
- `content_hash`
- `chunk_index`
- `chunk_count`
- `indexed_at`
- `title`
- `text`

Champs optionnels possibles:
- `git_branch`
- `section`
- `source_url`
- `legacy_collection`
- `legacy_payload_shape`

## 8.1 Compatibilite avec les payloads REX existants

Les collections REX existantes montrent deja plusieurs formes utiles a conserver au niveau du mapping:

- style `operational-rex` / `vpai_rex`:
  - `source_project`
  - `source_file`
  - `section_title`
  - `category`
  - `type`
  - `severity`
  - `date`
  - `text`
- style `app-factory-rex`:
  - `source`
  - `project_name`
  - `phase_number`
  - `phase_name`
  - `metadata`
  - `indexed_at`
  - `text`
- style `rex_lessons`:
  - `issue_title`
  - `phase`
  - `severity`
  - `outcome`
  - `lesson_text`
  - `date`
  - `tags`
- style `flash-rex`:
  - `project`
  - `type`
  - `sprint`
  - `status`
  - `severity`
  - `file`
  - `fix_commit`
  - `document`

Le schema `memory_v1` ne doit pas recopier ces formes heterogenes telles quelles, mais il doit:
- les mapper vers un schema canonique unique
- conserver la provenance d'origine via `legacy_collection` et `legacy_payload_shape`
- garder les champs analytiques utiles sous une forme normalisee (`severity`, `category`, `phase`, `source_file`, `project_name`)

## 9. Collection Qdrant cible

Il existe deja des collections heterogenes.  
Le projet doit creer une nouvelle generation de stockage normalise.

Collection proposee:
- `memory_v1`

Le filtrage se fera par payload:
- `doc_kind`
- `repo`
- `host_origin`
- `tags`
- `topic`
- `severity`
- `category`
- `phase`

Raison:
- recherches transverses plus simples
- meilleure experience de recherche pour les agents
- moins de complexite au lot 1

Des `payload_indexes` devront etre poses des la creation de la collection pour les champs filtres frequents.

Dimension initiale recommandee:
- `768`

Raison:
- meilleure qualite retrieval au lot 1
- evite une troncature prematuree
- la compression Matryoshka pourra etre evaluee plus tard si necessaire

## 10. Gestion des collections existantes

## 10.1 Probleme

Les collections actuelles ont ete creees progressivement pour des usages differents:
- docs officielles
- REX
- recherche applicative
- indexations one-shot

Leur payload et leur nomenclature ne sont pas uniformes.

## 10.2 Objectif

Produire une base memoire coherente et uniforme sans casser l'existant.

## 10.3 Strategie retenue

### Etape 1 - Inventaire

Produire un rapport listant:
- nom de collection
- dimension
- nombre de points
- source
- type de contenu
- payload actuel
- statut: active / legacy / obsolete

### Etape 2 - Cartographie legacy -> cible

Pour chaque collection:
- definir si elle doit etre migree
- definir dans quelle collection cible elle doit finir
- definir si la source originale est disponible pour reindexation

### Etape 3 - Reindexation

Si on change de modele:
- on ne migre pas les vecteurs
- on reindexe depuis la source si possible
- on utilise `embedding_model` et `embedding_dim` pour detecter proprement l'incompatibilite

### Etape 4 - Validation

Valider:
- recherche semantique
- filtres metadata
- couverture des sources importantes

### Etape 5 - Declassement

Une fois valide:
- marquer les anciennes collections comme legacy
- suppression ulterieure uniquement apres validation complete

## 10.4 Politique d'ecriture lot 1

Pour le lot 1:
- seul le worker d'indexation ecrit dans `memory_v1`
- les agents IA consultent la memoire mais n'ecrivent pas directement
- les hooks eventuels passent par des artefacts fichiers ou des reruns de pipeline, pas par un upsert direct

Objectif:
- limiter les conflits d'ecriture
- garder une source de verite unique pendant la phase de validation

## 11. Worker d'indexation sur Waza

## 11.1 Role Ansible a creer

Nouveau role:
- `roles/llamaindex-memory-worker`

Responsabilites:
- installer l'environnement
- installer le modele local
- deployer les scripts
- deployer la configuration
- deployer les services/timers

Le role devra rester coherent avec les conventions Ansible du repo:
- taches explicites et idempotentes
- `changed_when: false` sur les commandes d'etat/reconciliation qui ne representent pas une modification de configuration
- secrets via Vault / templates en `0600`
- restart via handlers uniquement quand les fichiers de config changent

Le role doit aussi respecter le protocole de travail valide pour ce projet:
- verifier les sources de verite avant de modifier le design
- implementer de facon non destructive
- controler les ecarts avant commit

## 11.2 Variables a prevoir

Exemples:
- `memory_worker_install_dir`
- `memory_worker_venv_dir`
- `memory_worker_model_name`
- `memory_worker_qdrant_url`
- `memory_worker_qdrant_api_key`
- `memory_worker_repo_roots`
- `memory_worker_include_extensions`
- `memory_worker_exclude_dirs`
- `memory_worker_schedule`

## 11.3 Cible d'inventaire

Deploiement initial:
- groupe `workstation`

## 12. Scripts CLI a produire

## 12.1 `index.py`

Fonction:
- script unique de pilotage de l'indexation

Parametres:
- `--path`
- `--repo`
- `--namespace`
- `--host-origin`
- `--mode full|incremental`
- `--gc`
- `--dry-run`

Raison:
- plus simple a maintenir
- une seule logique pour full, incremental et garbage collection
- permet d'adosser les suppressions a un `ref_doc_id` stable

## 12.2 `search_memory.py`

Fonction:
- faire une recherche simple dans Qdrant
- filtrable par repo, kind, tags

## 12.3 `inventory_collections.py`

Fonction:
- auditer les collections existantes
- preparer le plan de migration

## 12.4 `reindex_legacy.py`

Fonction:
- reindexer proprement une source legacy vers la nouvelle taxonomie

## 12.5 Protocole agent

Un protocole d'usage doit etre documente pour les agents qui consomment cette memoire.

Regles cibles:
- avant de repondre sur une decision passee, interroger la memoire
- avant de modifier un repo existant sur un sujet recurrent, rechercher le contexte associe
- apres une session importante, produire un artefact indexable (`REX`, plan, spec, doc) plutot qu'un ecrit direct agent -> Qdrant
- ne pas contourner le pipeline d'indexation valide

## 13. Detection des changements

## 13.1 Principe

Le worker garde un etat local par fichier:
- taille
- mtime
- hash de contenu
- git commit sha si disponible
- modele utilise
- version du schema
- date du dernier index

## 13.2 Pourquoi ne pas se limiter a Git

Parce que:
- certains fichiers utiles ne sont pas commits
- certaines modifications locales doivent etre capturables
- le flux memoire doit couvrir le travail vivant

## 13.3 Strategie retenue

- comparer l'etat courant a l'etat local persiste
- recalculer le `content_hash` uniquement si le couple taille/mtime a bouge
- produire un `ref_doc_id` stable par source documentaire
- supprimer via `ref_doc_id` les anciens chunks d'une source remplacee
- supprimer les chunks orphelins lors du mode `--gc`

## 13.4 `ref_doc_id` canonique

Le pipeline doit definir un identifiant documentaire stable pour profiter de la suppression native de LlamaIndex / Qdrant.

Format recommande:
- `{host_origin}:{repo}:{relative_path}`

Exemples:
- `waza:vpai:docs/REX-SESSION-2026-03-04.md`
- `waza:story-engine:apps/api/src/story_engine/services/search.py`

Ce `ref_doc_id`:
- reste stable tant que la source logique est la meme
- permet de supprimer/remplacer tous les chunks d'un document
- sert de pivot pour le garbage collection

## 13.5 Robustesse reseau

Si l'upsert Qdrant echoue:
- le lot est ecrit dans une file persistante locale
- le run est marque comme incomplet
- le prochain cycle retente d'abord la file avant de rescanner

Objectif:
- aucune perte silencieuse de chunks si le VPN ou Qdrant sont indisponibles

## 13.6 Controle de charge Waza

Avant de lancer l'embedding:
- verifier la charge systeme
- verifier l'absence d'un lock actif
- sauter proprement le cycle si la machine est trop chargee

Exemples de garde-fous:
- seuil de `loadavg`
- lockfile de job actif
- fenetres horaires evitant les periodes de rendu ou d'usage lourd

Par defaut:
- scan du filesystem
- filtrage par patterns
- calcul d'un hash sur les fichiers a traiter
- comparaison a l'etat local

Git peut etre utilise en optimisation plus tard, mais pas comme unique source de verite.

## 13.7 Provenance multi-agents

Le besoin multi-agents est reconnu, mais il n'est pas implemente en lot 1.

Decision:
- ne pas ajouter des champs de provenance toujours vides ou constants des maintenant
- documenter seulement le schema cible futur
- implementer la provenance reelle quand un second writer apparaitra (ex: n8n ou hooks valides)

Schema cible futur possible:
- `writer_kind`
- `writer_id`
- `ingest_source`
- `ingested_by`
- `ingest_run_id`

## 13.4 Garbage collection

Le pipeline doit supprimer les chunks fantomes.

Cas a couvrir:
- fichier supprime
- fichier renomme
- chunking strategy modifiee
- modele change

Strategie:
- identifier les `source_uid` attendus apres le scan
- comparer avec l'etat precedent
- supprimer de Qdrant les points associes a des sources absentes
- supporter un mode `--gc`

## 14. Orchestration n8n

## 14.1 Role de n8n

n8n ne lit pas directement les fichiers.

n8n sert a:
- lancer les jobs
- journaliser
- notifier
- relancer
- exposer des triggers manuels

## 14.2 Contrat de sortie du worker

Avant de definir les workflows n8n, le worker doit exposer une sortie stable
que n8n peut consommer sans parser des logs texte.

C'est le prerequis numero un: tant que le worker ne sort pas un rapport
machine-readable, tout workflow n8n restera fragile.

Le script `index.py` doit ecrire en fin de run un resume JSON, soit sur
stdout (derniere ligne, prefixee pour filtrage facile), soit dans un
fichier `--report-path`. Le format est versionne via
`report_schema_version`.

Champs obligatoires:

- `report_schema_version`
- `run_id`
- `worker_version`
- `host_origin`
- `repo` (string, liste de strings, ou `null` si un run couvre plusieurs repos)
- `mode` (`full` | `incremental` | `gc`)
- `collection_name`
- `embedding_model`
- `started_at`
- `duration_sec`
- `attempted_files`
- `indexed_files`
- `indexed_chunks`
- `indexed_points`
- `skipped_files`
- `errors` (liste courte de resumes, **pas** de tracebacks complets)
- `spool_size` (lots en attente dans la file locale)
- `qdrant_reachable` (bool, reflet de l'etat **reel du run**, pas juste du preflight)
- `exit_code`

Regles:

- le JSON est **toujours** produit, meme en echec partiel
- un run degrade doit renvoyer `exit_code != 0` mais un JSON valide
- `n8n` ne doit jamais dependre de la forme des logs texte
- `indexed_files` et `indexed_chunks` sont distincts pour eviter de confondre
  volume documentaire et nombre de fichiers traites
- les tracebacks detaillees restent dans les logs locaux, pas dans le rapport

## 14.3 Workflows cibles - lot 1

### 14.3.1 Modele d'integration: push-only

Decision: le worker sur Waza est l'acteur actif du pipeline.
n8n n'ouvre **jamais** de connexion sortante vers Waza.

Raisons:
- le container n8n est sur le reseau Docker `backend` interne
- il n'a pas d'acces Tailscale direct sans modification du compose
- ouvrir un chemin n8n -> Waza ajoute une credential SSH a gerer
- pour le lot 1 on minimise la surface

Flux:

```text
systemd timer sur Waza
    -> worker LlamaIndex indexe et upsert vers Qdrant (Tailscale)
    -> worker POST le rapport JSON a https://mayi.ewutelo.cloud/webhook/memory-run-report
    -> n8n ingest, persiste, alerte si anomalie
    -> n8n healthcheck cron lit la derniere entree et l'etat Qdrant
```

### 14.3.2 Ordre d'implementation

1. contrat JSON du worker (section 14.2)
2. systemd timer + script d'appel webhook sur Waza
3. workflow `memory-run-report-ingest`
4. workflow `memory-healthcheck`
5. script CLI `memory-backfill.sh` (hors n8n)

Raison: sans rapport JSON les workflows sont bancals. Une fois le rapport
en place, l'ingest est trivial et le healthcheck devient une simple requete
SQL + ping Qdrant.

### `memory-run-report-ingest` (n8n)

Type: webhook POST `/webhook/memory-run-report`

But:
- recevoir le rapport JSON du worker
- le persister dans Postgres (`memory_runs`)
- alerter Telegram seulement si `exit_code != 0` ou `errors` non vide

Securite:
- header `X-Memory-Secret` valide contre `MEMORY_WEBHOOK_SECRET` (env n8n)
- 403 sur mismatch

Comportement:
- `CREATE TABLE IF NOT EXISTS` idempotent sur premier appel
- insert du rapport complet
- silence sur run nominal (pas de Telegram)

### `memory-healthcheck` (n8n)

Type: Schedule trigger, 1 heure

But:
- detecter une derive silencieuse du pipeline memoire

Verifications:
- Qdrant accessible (`GET http://javisi_qdrant:6333/collections/memory_v1`)
- dernier run dans `memory_runs` plus recent que `memory_healthcheck_max_age_hours`
- dernier run avec `spool_size` sous `memory_healthcheck_max_spool`
- dernier run avec `qdrant_reachable = true`

Alerte:
- Telegram si un critere devie

Seuils (a affiner apres premier run reel, valeurs de depart proposees):
- `memory_healthcheck_max_age_hours`: 2
- `memory_healthcheck_max_spool`: 50

Raison d'etre:
- filet de securite face au risque
  "decouvrir trop tard qu'on n'indexe plus rien"

### `memory-backfill.sh` (CLI, hors n8n)

Type: script shell versionne dans `scripts/memory-backfill.sh`

But:
- declencher un reindex complet controle d'un repo donne depuis Waza

Parametres:
- `--repo`
- `--path`
- `--max-files`
- `--dry-run`

Comportement:
- wrapper autour du worker en mode `--mode full`
- execution manuelle depuis Waza uniquement au depart
- le worker POST quand meme son rapport JSON au webhook n8n
- donc backfill visible dans `memory_runs` avec `mode = full`

Raison de la sortie du scope n8n:
- backfill est rare (changement schema ou modele)
- un script shell local est suffisant
- evite d'ouvrir un chemin de declenchement reseau n8n -> Waza
- une future integration GitHub Actions reste possible sans changer
  le workflow cible

Usage attendu:
- changement de schema (par exemple ajout du champ `topic`)
- changement de modele d'embedding
- backfill propre d'une source

## 14.4 Workflows differes

Les workflows suivants sont utiles mais pas requis pour le lot 1.
Ils seront ajoutes apres validation du pilote.

### `memory-benchmark-retrieval`

- execute `benchmark_memory.py` apres changement modele/chunking
- alerte si `miss_ratio > 0.30`
- manuel ou planifie

### `memory-qdrant-audit`

- inventorie les collections
- exporte un rapport
- pre-requis de la phase E (migration legacy)

### `memory-maintenance`

- purge / verification / metriques
- a activer une fois le pipeline stabilise

## 14.5 Pourquoi n8n est retenu

Parce qu'il apporte:
- execution deterministe
- visualisation des runs
- retries
- notifications
- pilotage central

## 14.6 Resilience reseau

Si le VPN Waza -> Sese-AI est indisponible:
- les lots non pousses sont ecrits dans une file locale persistante
- le prochain run tente d'abord de vider cette file
- aucune perte silencieuse ne doit etre acceptee

## 15. Budget ressources sur Waza

## 15.1 Objectif

Ne pas degrader Waza quand il execute deja d'autres charges.

## 15.2 Cible lot 1

Avec `EmbeddingGemma-300M`, on vise:
- 2 a 4 coeurs CPU selon la fenetre de run
- environ 400 a 500 Mo de budget RAM pour le worker
- batchs petits
- un seul job d'indexation a la fois

Mode fallback si charge trop forte:
- basculer vers `snowflake-arctic-embed-xs`

## 15.3 Regles d'exploitation

- limiter le parallellisme
- indexation incrementale par defaut
- full reindex manuel ou planifie hors periodes sensibles
- verifier la charge avant lancement
- skip propre du cycle si la machine est trop chargee
- si besoin, `nice` / `ionice`

## 15.4 Concurrence avec les autres workloads

Le worker doit eviter de concurrencer brutalement:
- ComfyUI
- Remotion
- autres traitements lourds

Mesures a prevoir:
- lock pour eviter plusieurs runs simultanes
- verification de charge avant lancement
- skip si loadavg ou pression memoire depasse un seuil

## 16. Sources a traiter en phase 1

## 16.1 Priorite 1

Repos locaux sur Waza.

Exemples probables:
- `VPAI`
- autres repos d'applications presents localement

## 16.2 Priorite 2

Repos GitHub non presents localement, mais juges critiques.

Mode prevu:
- clone/pull local puis indexation

## 16.3 Hors phase 1

Documents de travail sur Sese-AI.

Ils feront l'objet d'un workflow d'indexation separe plus tard.

## 16.4 Tests de retrieval

Le benchmark retrieval doit etre present des la phase pilote.

Le pilote ne sera valide que si:
- le pipeline tourne
- et la qualite retrieval est acceptable sur de vraies requetes

Jeu minimal attendu:
- 10 a 20 requetes reelles
- resultats attendus documentes
- evaluation qualitative
- mesure du temps de recherche
- decision explicite de maintien ou de bascule du modele selon le seuil defini en section 5.5

## 17. Plan d'execution

## Phase A - Validation du design

- valider le modele d'embedding
- valider la taxonomie
- valider la nomenclature Qdrant
- valider la chunking strategy
- valider le role d'Ansible
- valider l'usage de n8n

## Phase B - Prototype technique minimal

- deployer le worker sur Waza
- indexer 1 repo pilote
- pousser vers `memory_v1`
- mesurer CPU, RAM, temps
- mesurer la qualite retrieval avec un jeu de requetes documente
- benchmarker `EmbeddingGemma-300M` contre `snowflake-arctic-embed-xs` si necessaire
- maintenir ou basculer le modele selon le seuil defini en section 5.5

## Phase C - Normalisation du schema

- creer les collections cibles
- stabiliser le payload standard
- stabiliser les tags
- stabiliser la strategie de chunking

## Phase D - Orchestration deterministe

- ajouter timer(s) ou workflows n8n
- logs et notifications
- run incremental fiable

## Phase E - Audit et migration legacy

- inventaire complet Qdrant
- mapping legacy -> cible
- reindexation progressive
- validation

## Phase F - Extensions futures

- repos GitHub non locaux
- docs officielles
- documents de travail Sese-AI
- provenance multi-agents
- WAL / audit trail d'ecriture
- graphe temporel de faits
- pipeline conversations dedie

## 18. Livrables attendus

## Livrables techniques

- role Ansible `llamaindex-memory-worker`
- scripts CLI d'indexation
- scripts de recherche
- scripts d'audit Qdrant
- workflow(s) n8n d'orchestration

## Livrables documentaires

- spec de taxonomie memoire
- runbook d'exploitation
- rapport d'inventaire des collections existantes
- procedure de migration legacy

## 19. Risques et parades

## Risque 1

Le modele principal reste trop lourd sur Waza.

Parade:
- benchmark reel sur Waza
- fallback possible vers `snowflake-arctic-embed-xs`
- benchmark reel avant generalisation

## Risque 2

La qualite retrieval n'est pas suffisante.

Parade:
- benchmark retrieval des la phase pilote
- ajuster chunking et modele avant extension

## Risque 3

Les collections existantes restent heterogenes trop longtemps.

Parade:
- creer une nouvelle generation de collections propres
- ne pas melanger legacy et v1

## Risque 4

Le pipeline depend trop de n8n.

Parade:
- scripts CLI idempotents
- n8n uniquement comme orchestrateur

## 20. Decision proposee pour validation

Je propose de valider les points suivants:

1. Worker d'indexation principal sur **Waza**
2. Embeddings **locaux**
3. Modele lot 1: **`EmbeddingGemma-300M`**
4. Qdrant central sur **Sese-AI**
5. Pas de **FastAPI** en phase 1
6. **n8n** comme orchestrateur deterministe
7. Collection cible unique: **`memory_v1`**
8. Migration legacy uniquement apres prototype fonctionnel valide
9. Champ `topic` avec extraction prudente uniquement
10. Provenance multi-agents documentee, pas codee en lot 1
11. **Rapport JSON stable** du worker (section 14.2) comme prerequis
    des workflows n8n — implemente avant les workflows eux-memes
12. Lot 1 n8n limite a 2 workflows **push-only**:
    `memory-run-report-ingest` (webhook) et `memory-healthcheck` (cron).
    Le backfill est un script CLI `scripts/memory-backfill.sh`, hors n8n.
13. Worker sur Waza = **seul acteur actif**. n8n n'ouvre jamais de
    connexion sortante vers Waza (pas de SSH depuis n8n).

## 21. Prochaine etape

Une fois ce plan valide:
- produire la spec technique d'implementation
- lister les repos Waza a surveiller en priorite
- ecrire l'inventaire des collections Qdrant existantes
- puis seulement lancer l'implementation Ansible
