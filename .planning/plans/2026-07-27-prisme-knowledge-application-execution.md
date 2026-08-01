# Plan d'exécution — Prisme, application de connaissance vérifiable

> Date : 2026-07-27
> Statut : **v4 READY — revue Claude Opus 5 passe 29, 0 P0 / 0 P1**
> Design source : `docs/superpowers/specs/2026-07-27-prisme-knowledge-application-design.md`
> Collection : nouvelle `knowledge_v1`, sans aucune interaction avec `trading_v1`

## 0. Règles d'exécution

1. Chaque lot se termine par ses tests et un artefact de preuve.
2. Aucun lot suivant ne masque un gate rouge.
3. Aucun `drop_collection`, `recreate_collection` ou purge automatique.
4. À partir de T3.1, la source unique des collections Qdrant et politiques de mutation est
   `inventory/group_vars/all/qdrant_collections.yml`; le client Prisme en génère son allowlist et
   ses tests. T3.1 crée ce fichier ; avant T3.1 aucune allowlist Qdrant ni client mutable n'est
   autorisé. Aucun duplicata manuel de denylist n'est autorisé.
5. Les migrations PostgreSQL et Qdrant sont forward-only avec rollback applicatif documenté.
6. Les images, modèles, packages et actions sont pinnés.
7. Les services sont VPN-only et least privilege.
8. Les contenus récupérés sont non fiables et ne deviennent jamais des instructions.
9. Le canary utilise trois médias autorisés au maximum.
10. L'activation Instagram réelle reste bloquée par confirmation d'autorisation et acceptation
    du risque de compte.
11. Le NO-GO global de la phase offsite Banga n'est pas déclaré résolu par Prisme. P4 dépend
    seulement du pool `tank` sain et du provisioning ZFS vert ; Prisme livre pour
    `tank/knowledge` sa politique backup dédiée, son offsite et son restore drill avant G10.
    L'offsite passe exclusivement par l'orchestrateur zerobyte v3 approuvé. Une destination ou un
    secret absent déclenche son gate humain billing/décision et le blocage prévu par le prompt ;
    Prisme ne crée aucun bucket/credential parallèle.
12. Les revues `claude -p --model opus` sont des tâches de gate : pré-exécution v4, après
    G1/G2/G3/G7/G9/G10 et avant G11. Chaque session correspondante inclut correction puis relance
    jusqu'à `READY`; aucun modèle de substitution.
    Avant chaque smoke/revue, exécuter
    `~/work/ops/loops/scripts/claude-usage-guard.sh`; à jauge `>= 80 %`, différer/séquencer le
    gate sans jamais le sauter. Puis un smoke minimal `claude -p --model opus` vérifie accès/quota ; son échec
    donne `AWAITING_OPUS_QUOTA`, journalisé dans `.planning/EXECUTION.md` et le rapport de revue
    avec sortie caviardée ; jamais un verdict technique. La reprise relance le même gate.
13. Tout gate humain portant sur un artefact texte substantiel exécute d'abord
    `~/work/ops/loops/scripts/review-file.sh --sol <artefact>`, intègre les findings HIGH, puis
    appelle `~/work/ops/loops/scripts/notify-gate.sh --artifact <artefact> "<titre>"`
    `["<contexte>"]`. Une confirmation triviale utilise consciemment
    `--no-artifact "<titre>" ["<contexte>"]`. Exit non nul : gate non posé, aucune attente
    implicite dans un terminal headless.

### 0.1 Reprise depuis l'état v3 existant

Le repo `/home/mobuone/work/saas/prisme` existe au commit initial `3cee720` et contient un lot P1
v3 non commité. La v4 impose la reprise suivante :

1. ne pas relancer `git init`, ne pas recréer le remote et ne pas exiger zéro collision de nom ;
2. auditer le worktree et préserver le scaffold/ADR/diff P1 existants ;
3. rouvrir G0 pour consigner toutes les décisions T0.1 manquantes, dont Karakeep, OCI, fixtures
   canary et propriétaire nommé du registre d'ontologie, dans l'ADR 0001 ;
4. déclarer les anciens résultats G1 insuffisants pour la v4 ;
5. compléter P1 de 13 à 19 contrats, snapshot/canonicalisation compris ;
6. relancer toute la matrice G1 et la revue Opus jusqu'à `READY` ;
7. interdire P2 et tout gate aval avant ce nouveau G1 vert.

Le journal `.planning/EXECUTION.md` de Prisme porte explicitement cette reprise et ne présente
jamais le G1 v3 comme validant le delta v4.
Première mutation de reprise : vérifier le lot stagé v3 tel quel, puis le committer comme
checkpoint d'audit ne revendiquant pas G1. Dans le commit suivant, avant tout delta contractuel,
remplacer l'état P1 du journal par `G1 v3 SUPERSEDED — sans valeur pour les contrats v4`. Aucun
stash n'est utilisé.

Avant toute modification VPAI, auditer aussi son worktree. Préserver les changements étrangers,
ne jamais utiliser `git add -A`, `git add .` ou `git commit -a`. Stage par chemins/hunks Prisme
seulement. Pour un fichier partagé déjà modifié, sauvegarder le patch préexistant
et son hash, appliquer des hunks Prisme minimaux, puis construire un patch d'index contenant
uniquement ces hunks (`git apply --cached --check` puis `git apply --cached`). Vérifier que
`git diff --cached` ne contient que Prisme et que le patch/hash étranger reste présent dans
`git diff`; ne jamais stasher ni committer le travail étranger. Refuser seulement si les mêmes
lignes se chevauchent réellement. Sur ces fichiers partagés sales, committer **sans pathspec**
(`git commit`, index seul) ; `git commit <chemin>` est interdit. Après commit, re-vérifier que le
patch étranger et son hash restent dans `git diff`. Les secrets Prisme utilisent un nouveau
`inventory/group_vars/all/prisme-secrets.yml` chiffré, sans réécrire `secrets.yml`.
Avant le premier hunk VPAI, générer depuis `git status --porcelain=v1 -z` le manifeste exhaustif
de tous les chemins déjà sales, puis capturer/hash chaque patch préexistant sans en afficher le
contenu. Cela inclut actuellement `inventory/group_vars/{all,prod}/main.yml`,
`inventory/group_vars/all/secrets.yml`, `roles/caddy/{defaults,tasks,templates}/*` et
`roles/monitoring/*`, sans s'y limiter. Sur un chemin ensuite modifié par Prisme, extraire le
patch préexistant et prouver après commit qu'il reste applicable/présent comme sous-patch ;
`secrets.yml` reste hors périmètre Prisme et son contenu ne va dans aucun artefact/log.

## 1. Résultat final

Depuis `https://prisme.<domaine>` :

1. l'opérateur soumet une source ;
2. Prisme produit un manifeste sans téléchargement ;
3. l'opérateur approuve ;
4. Waza acquiert séquentiellement ;
5. Banga vérifie, stocke et analyse ;
6. Prisme extrait les affirmations ;
7. Sese recherche les preuves favorables et contradictoires ;
8. chaque URL ouverte, analysée, citée ou rejetée est journalisée dans Prisme puis, lorsque
   `karakeep_enabled=true`, projetée automatiquement dans l'Inbox Karakeep ; sinon le fake
   contractuel prouve la projection sans dépendance runtime ;
9. les originaux à conserver sont promus sur Banga, seul stockage canonique ;
10. les domaines sensibles passent en revue ;
11. les éléments testables peuvent produire une expérience isolée ;
12. la bibliothèque répond avec citations, statuts et provenance.

La reconstruction de `knowledge_v1` depuis PostgreSQL + Banga est démontrée.
Karakeep reste optionnel et reconstructible : son indisponibilité ne bloque ni recherche, ni
vérification, ni retrieval.

## 2. Graphe de dépendances

```text
P0 décisions + repo
 ├── P1 contrats partagés
 │    ├── P2 PostgreSQL/API skeleton
 │    ├── P3 Qdrant knowledge_v1
 │    └── P4 Banga knowledge plane
 │           └── P5 Waza acquisition
 │                  └── P6 media analysis
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
Dépendances dures : P5 attend P4 vert pour son transfert Banga ; P6 attend P4 et P5 verts pour
bundles, stockage et embedding. P8 peut être codé en parallèle de P7, mais G8 attend G7.

## 3. P0 — Décisions et création du projet

### T0.1 — Décisions humaines

À consigner dans l'ADR 0001 :

- nom produit `Prisme` ou remplaçant ;
- slug repo `prisme` ;
- FQDN ;
- politique d'auth ;
- politiques de conservation par défaut ;
- domaines sensibles ;
- propriétaire du registre d'ontologie et procédure d'ajout d'entité/topic ;
- budget maximal de recherche/LLM ;
- acceptation explicite de l'overcommit mémoire Docker : ratio somme des hard limits de tous les
  conteneurs actifs / `MemTotal` borné à `1,5`, avec protection du RSS p95 des services étrangers ;
- allocation quotidienne de la clé virtuelle LiteLLM Prisme à l'intérieur du cap partagé VPAI
  `$5/day`, répartition laissée aux autres applications et politique d'arrêt avant épuisement ;
  tout relèvement du cap global exige une décision G0 explicite de doctrine/coût ;
- révision exacte `google/embeddinggemma-300m` et tokenizer ;
- version `Qdrant/bm25`/FastEmbed ;
- emplacement Banga du service d'embedding et mode dégradé BM25-only ;
- route interne de composants retenue, sans Storybook au MVP ;
- registre OCI `ghcr.io/Mobutoo/prisme`, politique de publication `linux/amd64` et pin par digest ;
- format des fixtures synthétiques du canary ; la source Instagram réelle et son autorisation
  restent volontairement hors G0 et ne sont demandées qu'en P11 ;
- outil/version/voix/seed du TTS déterministe utilisé uniquement pour les fixtures golden CC0,
  pinnés et disponibilité vérifiée avant T1.5 ;
- implémentation `prisme-db-proxy` : HAProxy L4 en passthrough protocolaire avec SNAT conservé
  (PostgreSQL voit l'IP du proxy), image pinnée par digest, ACL source réseau/IP sans terminaison
  d'auth ; PostgreSQL conserve l'auth MD5 et Drizzle/prepared statements passent sans pooling de
  transaction ;
- rôle de Karakeep : Inbox documentaire non autoritaire, jamais interface métier ni source de
  vérité ;
- instance Karakeep VPAI sur Sese, `karakeep.ewutelo.cloud`, VPN-only, compte opérateur local
  mono-tenant, backup/restore smoke et capacité mesurée ;
- Karakeep `v0.32.0` au commit `b9b252ecb6d2af379192778ec24f766d4cd60da3`,
  image par digest et snapshot OpenAPI SHA-256
  `69b85ed2cdbfb0904bd04c83dd3d3d24b44838815ebd2031d0ad89b9cc7f7f24` ;
- politique `auto_save`: `opened_or_evaluated` par défaut, jamais tous les résultats SERP ;
- liste racine, convention de tags et règle de conservation de la copie Karakeep ;
- droits autorisant la capture et l'archivage des contenus externes ;
- politique de promotion Karakeep → Banga et comportement explicite aux suppressions externes ;
- acceptation du déploiement AGPL-3.0 isolé et règle : aucune copie/modification de code Karakeep
  dans Prisme sans nouvel ADR et revue de licence.

Artefact :

```text
prisme/docs/adr/0001-product-boundary-and-name.md
```

Gate G0 : aucune ambiguïté sur nom, domaine, auth, propriétaire des données et les décisions
Karakeep de T0.1 : rôle non autoritaire, instance, version/snapshot, désactivation par défaut,
capture, tags/listes, droits, promotion, suppression externe et AGPL.
Le budget quotidien et la clé virtuelle LiteLLM Prisme, le registre OCI amd64/digest, le format
des fixtures canary et le propriétaire nommé du registre d'ontologie sont également décidés ; le
budget reste sous le cap global VPAI.
G0 mesure aussi Sese en lecture seule avant investissement P1→P10 : `MemAvailable`, RSS actuel,
PSI/swap sur 15 minutes, espace disque, hard limits Prisme (`5 888 MiB`) et réservations
(`2 944 MiB`), ainsi que le ratio hard limits/MemTotal de base sans Prisme puis projeté avec
Prisme. Si le ratio de base est déjà au seuil `1,5` ou si l'ajout Prisme le dépasse, consigner
immédiatement la décision capacité G0 avant P1. Si la formule
T11.2 prédit déjà un rouge après remédiations réversibles, consigner immédiatement
`AWAITING_G0_CAPACITY_DECISION`; les artefacts non-production peuvent progresser, mais aucun
déploiement réel n'est promis.
Le même préflight G0 inventorie Banga en lecture seule (LXC, Docker, GPU/passthrough, capacité) et
vérifie seulement la présence effective, jamais la valeur, de `vault_ghcr_pull_token` dans son
vault. À défaut de cible Docker+GPU déjà approuvée ou de credential, consigner
`AWAITING_G0_BANGA_PLACEMENT` et la liste exacte des manques. Sous cet état, seuls P0–P3 et P8 sur
fixtures restent livrables, mais G8 n'est pas évalué faute de G7 vert ; P4–P11 et la DoD restent
rouges.

### T0.2 — Vérifier le placement

Commandes read-only :

```bash
ls -1d /home/mobuone/work/{infra,saas,tools,refdocs}/* \
  | sort | grep -Eix '.*/prisme$'
```

Attendu sur création neuve : zéro collision. En reprise v4, la collision exacte `prisme` est le
repo attendu et T0.2 devient un audit read-only du remote, du commit et du worktree ; toute
seconde collision sur un autre wing reste bloquante.

Sur création neuve seulement, créer ensuite `/home/mobuone/work/saas/prisme`, `git init`,
arborescence de la spec et remote approuvé. En reprise v4, conserver le repo/remote existants et
suivre §0.1. Ne pas ajouter le repo au rebuild bulk `memory_v3` tant qu'un remote clonable et le
besoin ne sont pas confirmés ; l'auto-découverte Waza suffit.

### T0.3 — Toolchain

- Node.js/pnpm selon standard VPAI actuel ;
- SvelteKit 2 avec Svelte 5 ;
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

### T1.0 — Snapshot Karakeep

Figer depuis le tag upstream `v0.32.0` :

- vérifier d'abord via `git ls-remote --tags` que `refs/tags/v0.32.0` existe et résout, après
  peel éventuel, exactement vers `b9b252ecb6d2af379192778ec24f766d4cd60da3`; mismatch = gate
  rouge avant tout fetch/snapshot ;

```text
packages/contracts/karakeep/openapi-v0.32.0.json
packages/contracts/karakeep/webhook-v0.32.0.fixture.json
packages/contracts/karakeep/SOURCE.md
```

Le snapshot provient du chemin upstream
`packages/open-api/karakeep-openapi-spec.json`. Le fichier porte le commit et le SHA-256 décidés
en G0. La CI compare le hash et valide les
fixtures contractuelles utilisées par l'adaptateur. Le webhook, absent du snapshot OpenAPI, est
dérivé des fichiers upstream du même commit :

```text
packages/shared/types/webhooks.ts
  sha256 a57e66b68ebc4dc577b20697eb28f0672d0f38ec1db35a72461be8dc41296913
apps/workers/workers/webhookWorker.ts
  sha256 9e5243204a6834f564eebf17d5bedc6091a7b109ad8cf8052797f11e4cc89eb5
```

Tout upgrade modifie explicitement version, snapshot, fixture webhook, hashes source et rapport
de compatibilité.

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
research-run.v1
external-connector.v1
external-resource.v1
research-query.v1
research-candidate.v1
external-sync-event.v1
outbox-event.v1
problem-details.v1
```

Autorité choisie : **Zod** dans `packages/contracts`. Générer JSON Schema/OpenAPI et des fixtures
consommables par les workers Python ; aucune seconde définition manuelle.
Interdire la duplication manuelle TypeScript/Python.
Les consommateurs Python nommés sont le fetcher Waza et les rôles Banga
`knowledge-worker`, `knowledge-embedding` et `experiment-runner`; les workers recherche,
connecteur Karakeep et indexeur du repo Prisme restent TypeScript.

Tests :

- fixtures valides ;
- champs inconnus rejetés sur mutations ;
- compatibilité backward sur lecture ;
- dates UTC ;
- bornes taille/durée ;
- enums taxonomiques ;
- aucun secret/URL CDN signé dans les artefacts ;
- `external_id` n'est jamais un identifiant métier Prisme ;
- URL originale, URL canonique et hash canonique distingués ;
- `canonicalizeUrl()` et `url_canonicalization_version` partagés ; le hash inclut la version et
  possède une procédure de recalcul/réconciliation ;
- états `pending|synced|failed_retryable|failed_terminal|disabled|deleted_external` ;
- rôle nullable ; son enum fermé contient uniquement
  `supporting|contradicting|context|primary_source|rejected`. `null` signifie absence de rôle,
  n'appartient pas à l'enum et n'émet aucun tag `role:*`; les cinq valeurs en émettent exactement
  un par run ;
- décisions `pending|selected|rejected|promotion_requested|promoted` ;
- statuts d'interaction `opened|analyzed|cited|archived_banga` ;
- règles de projection tags/listes Karakeep versionnées ;
- fixtures contractuelles conformes au snapshot OpenAPI Karakeep pinné pour les seules projections
  wire concernées.

Le delta v4 de cinq contrats est nommé exactement :
`external-connector.v1`, `external-resource.v1`, `research-query.v1`,
`research-candidate.v1`, `external-sync-event.v1`; `research-run.v1` est le sixième ajout.
Ces cinq contrats restent le domaine d'intégration Prisme, pas des copies de schémas Karakeep.
Seules les projections HTTP de `external-resource.v1` et `external-sync-event.v1`, ainsi que les
fixtures privées d'upsert/lecture bookmark et webhook qui en dérivent, sont validées contre les
opérations/sources upstream pinnées. `external-connector.v1`, `research-query.v1` et
`research-candidate.v1` passent uniquement les fixtures internes cross-runtime.

`research-run.v1` porte `claim_id` nullable, tenant/ACL, état, budget et horodatages. Les ports
`BookmarkSink` et leurs types sont définis dès G1 ; le fake G2 les implémente avant l'adaptateur
HTTP réel de T7.2.

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
- `wing` alias local Prisme de transition API, dérivé côté serveur et strictement égal à
  `provenance_class`; il ne prétend aucune compatibilité de valeurs avec `memory_v3` ;
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
- transcripts humains publiés avec des clips de benchmark librement licenciés, dont licence,
  URL et hash sont gelés ; aucune pseudo-référence générée par un modèle. Les médias Instagram
  réels ne sont ajoutés au golden qu'après autorisation et validation humaine P10 ;
- si dix couples publiés redistribuables ne sont pas disponibles, utiliser dix fixtures
  vidéo synthétiques CC0 créées pour Prisme à partir de scripts/storyboards écrits et versionnés
  avant rendu déterministe de plans, texte incrusté et audio TTS. Scripts, outil/versions,
  seed/voix et hashes sont pinnés ; aucun modèle ni transcription humaine ne produit/corrige la
  référence. Le producteur est le runner GitHub Actions x86_64 ; le manifeste porte
  `render_recipe` (pas d'URL source) et enregistre le hash issu du premier rendu reproductible.
  Chaque vidéo possède un
  `packages/evals/golden/manifests/ocr-<id>.json` avec chaînes attendues, bboxes et timestamps par
  segment ;
- claims/timestamps attendus ;
- 20 paires query/document ;
- requêtes exactes VPIN/VWAP/HMM/OBI/Mean Reversion, synonymes, noms développés et formulations
  sémantiques ;
- intentions `explore`, `learn`, `verify`, `source`, `compare` ;
- cas contradictoires et injections indirectes ;
- données sensibles exclues.

Ce jeu démarre petit mais précède P4/P6/P7 ; P10 l'étend en golden de production.
Le repo ne contient que `packages/evals/golden/manifests/*.json` avec licence, URL, hash et
segments attendus redistribuables. Les binaires ne sont ni committés ni téléchargés en P1. À
partir de P4 ils sont réhydratés dans
`tank/knowledge/incoming/<golden_ingestion_id>/` et promus selon le workflow normal.

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

Gate G1 : contrats utilisables par web, workers Python et bootstrap Qdrant. Les 19 contrats,
dont les six ajouts nommés T1.1, passent les fixtures cross-runtime générées. Seules les
projections wire d'`external-resource.v1` et `external-sync-event.v1` sont comparées aux
opérations/sources Karakeep pinnées ; les trois autres contrats du domaine d'intégration ne le
sont pas. La canonicalisation passe ses propres fixtures versionnées. Ce gate est rouvert et
remplace intégralement le résultat G1 v3.

## 5. P2 — PostgreSQL et squelette API

### T2.1 — Base dédiée

Dans VPAI :

- créer DB/user `prisme` via une tâche live du rôle PostgreSQL existant ;
- mot de passe issu de `postgresql_password` partagé conformément au contrat du rôle VPAI,
  injecté avec `no_log`; ne pas créer de variable `vault_prisme_db_password` incompatible ;
- `prisme-db-proxy` à IP backend fixe joint les réseaux Prisme/backend ; il n'accepte en entrée que
  le CIDR Prisme. `pg_hba` ajoute avant la règle backend
  `host prisme all <proxy_ip>/32 md5`, puis
  `host all all <proxy_ip>/32 reject`, puis
  `host prisme all <backend_subnet> reject`, couvrant tous les rôles dont `postgres`. Appliquer par
  `SELECT pg_reload_conf()` sans restart du PostgreSQL partagé, avec snapshot/rollback du HBA et
  smoke Prisme+n8n+Plane+LiteLLM ; aucune autre application ne peut ouvrir la DB Prisme depuis le
  réseau Docker backend. Les accès administratifs locaux Unix/loopback restent réservés aux
  tâches de provisioning `docker exec` sous `no_log` ;
- attribuer au service `prisme` une IP fixe `javisi_backend` et insérer, avant le broad allow
  backend, `host all all <prisme_service_ip>/32 reject`. Prisme atteint PostgreSQL exclusivement
  via le proxy, jamais directement ni vers une DB étrangère ;
- fixer proxy `172.20.2.240` et service `172.20.2.241` via variables de
  `inventory/group_vars/all/docker.yml`, sans modifier l'IPAM du réseau existant. Avant toute
  mutation, `docker network inspect javisi_backend` vérifie que ces IP ne sont attribuées à aucun
  conteneur ; collision = gate rouge et nouvelle décision G0 d'IP, jamais recréation du réseau.
  Tout changement IPAM ultérieur exige décision G0, fenêtre de maintenance et redémarrage ordonné.
  Tous les hunks HBA
  Prisme sont sous `{% if prisme_enabled | default(false) | bool %}` ; flag false rend
  `pg_hba.conf` byte-identique à HEAD et ne réserve/rejette aucun `/32` ;
- modifier le rôle PostgreSQL partagé pour que la tâche `Deploy pg_hba.conf` **remplace** son
  notify `Restart postgresql stack` par deux handlers partageant
  `listen: "Reload PostgreSQL config"` : le premier probe `docker exec ... pg_isready` avec
  `failed_when: false` et `register: pg_probe`; le second reload s'exécute avec
  `when: pg_probe.rc == 0`. Un conteneur absent au premier déploiement relira le fichier à son
  démarrage. L'`assert rc == 0` appartient au contrôle Prisme T11.2, jamais au handler partagé,
  et ce handler ne restart pas PostgreSQL ;
  un test inspecte la tâche et les deux listeners, et prouve qu'elle ne notifie plus aucun
  handler de restart ;
  Prisme ne modifie jamais `postgresql.conf`, sa tâche ni son template, qui conservent leur
  comportement existant ;
  test de non-régression prouvant ordre allow DB Prisme proxy/reject toutes autres DB proxy/reject
  DB Prisme backend/reject IP service avant `all all` backend, avec tentative `postgres` directe
  et proxy→DB `n8n` refusées ;
- backup Prisme par `pg_dump --format=custom`, chiffré, hashé, rétention/offsite ; restore drill
  avec le compte administrateur PostgreSQL injecté `no_log` vers une DB temporaire, après
  préflight exigeant au minimum `2 × taille_dump + 20 %` d'espace libre, puis migrations,
  comptes/FK et smoke API avant suppression de la seule DB de test ;
- provisionner le conteneur déjà vivant par `docker exec` idempotent : DB via
  `SELECT ... \\gexec`, rôle via bloc `DO $$ ... duplicate_object`, grants explicites et `no_log`;
  ne jamais compter sur `init.sql.j2`. Garde REX-59 : probe `failed_when: false`, puis assert
  `rc == 0` avant toute commande ;
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
idempotency_records
webhook_delivery_receipts
research_queries
research_runs
research_candidates
research_candidate_merges
external_connectors
external_resources
external_resource_merges
research_candidate_resources
external_sync_attempts
```

`strategy_specs` versionne hypothèses, paramètres, univers, horizon, coûts, risques, métriques et
liens vers expériences. Les alias sont normalisés, uniques dans leur namespace et testés contre les
collisions d'acronymes.

Contraintes connecteurs :

- toutes les tables recherche/connecteur portent `tenant_id` et `acl_scope`; `research_runs`
  porte `claim_id` nullable, `topic_path` autoritaire/versionné, état, budget et horodatages, avec
  FK depuis requêtes/candidats. Un
  connecteur lie un
  tenant à un unique compte Karakeep via `external_owner_id` ;
- `external_connectors`: type, base URL sélectionnée dans l'allowlist Ansible, état, capabilities
  et configuration non secrète ;
- secret référencé par `secret_ref`, jamais stocké en base ;
- `research_candidates`: unique `(research_run_id, canonical_url_hash)` pour les lignes
  `merged_into_candidate_id IS NULL`, URL, rôle, décision et
  motif de rejet autoritaires pour ce run. Un bump commence par un dry-run sans mutation :
  qualifications identiques sont fusionnables avec audit ; les divergences rôle/décision créent
  et committent une tâche de revue dans une transaction séparée, puis bloquent la mutation.
  Après résolution seulement, une nouvelle transaction atomique conserve l'unique immédiat
  compatible `ON CONFLICT`, renseigne `canonicalization_migration_id`, place tous les survivants
  sur les mêmes sentinelles `migration:<migration_id>:<row_id>` protégées par CHECK, puis
  écrit les hashes finaux et active la version. Une fusion identique repointe les liaisons,
  ajoute `research_candidate_merges(loser_id, survivor_id)`, tombstone le perdant via
  `merged_into_candidate_id` et interdit tout DELETE. L'upsert candidat répète
  `WHERE merged_into_candidate_id IS NULL`; si le survivant possède déjà la même liaison
  ressource, la liaison redondante est tombstonée via `merged_into_link_id`; son rollback conserve
  la tâche de revue ;
- les chaînes `merged_into_candidate_id` se résolvent vers la racine avec profondeur max 8,
  compression sous lock et rejet de cycle/dépassement, comme les ressources ;
- `external_resources`: ressource projetée sans rôle/décision ni FK directe vers un run, URL
  originale/résolue/canonique, version de canonicalisation, hash versionné, `external_id`, deep
  link, état de synchronisation et `external_state_read_at` ;
- `research_candidate_resources`: liaison plusieurs-à-un entre qualifications par run et
  ressource externe dédupliquée, unique `(research_candidate_id, external_resource_id)` pour les
  lignes `merged_into_link_id IS NULL` ;
- unique `(connector_id, external_id)` lorsque non null sur toutes les lignes, y compris
  tombstonées, implémentée comme contrainte UNIQUE simple (NULL distincts, sans prédicat), afin
  d'interdire sa réutilisation ; unique `(connector_id, canonical_url_hash)`
  uniquement pour les ressources actives `WHERE merged_into_resource_id IS NULL` ;
  `url_canonicalization_version` reste non-clé. Un bump
  utilise des contraintes uniques immédiates, donc compatibles avec `INSERT ... ON CONFLICT` au
  runtime ; l'upsert par URL répète explicitement le prédicat
  `WHERE merged_into_resource_id IS NULL`, tandis que l'upsert par `external_id` utilise l'unique
  globale. Sous advisory lock, il calcule la nouvelle correspondance dans une table temporaire,
  bloque les écritures, repointe les liaisons et tombstone les perdants sans DELETE, puis
  affecte à tous les survivants `canonicalization_migration_id=migration_id` et un hash sentinelle
  texte `migration:<migration_id>:<row_id>`, avant d'écrire les hashes finaux et remettre l'ID à
  null. Une CHECK autorise le préfixe réservé uniquement lorsque l'ID migration non nul concorde ;
  le runtime ne peut donc jamais l'insérer. Cette double passe couvre aussi les permutations
  injectives et réconcilie ensuite Karakeep ;
- `external_sync_attempts` append-only avec code d'erreur caviardé, dates, tentative et prochain
  retry ;
- les résultats SERP bruts expirent ; une URL ouverte, analysée, citée ou rejetée devient un
  `research_candidate` durable ;
- aucune cascade de suppression Karakeep vers source, preuve, bundle ou point Qdrant.
- une fusion repointe transactionnellement `research_candidate_resources` vers le survivant et
  ajoute `external_resource_merges(loser_id, survivor_id)` ; le perdant reste tombstoné
  `merged_into_resource_id` pour que les `external_sync_attempts` append-only restent immuables et
  résolubles. Auditer les IDs et interdire toute suppression physique ;
- si le candidat possède déjà une liaison vers le survivant, conserver la plus ancienne liaison
  active et tombstoner l'autre avec `merged_into_link_id`; ne jamais écraser ni supprimer
  l'historique ;
- le reconciler résout toujours `merged_into_resource_id`, ignore le perdant tombstoné et ne peut
  jamais le ressusciter par `external_id`; résolution récursive vers la racine limitée à 8,
  compression de chemin sous lock et rejet de tout cycle/dépassement ;
- `idempotency_records` stocke tenant, route, clé, hash requête, statut/réponse minimale et
  expiration 24 h ; unicité `(tenant_id, route, key)` et purge bornée auditée ;
- `webhook_delivery_receipts` porte tenant/ACL, connector, job/bookmark/operation, reçu le et
  expiration 30 jours ; unicité
  `(tenant_id, connector_id, job_id, bookmark_id, operation)` et purge auditée ;
- `answers.visibility_status` est non null, enum versionné `active|stale_redacted`, défaut
  `active`; toute relecture applique `securityAsOf=now()`.
- `canonical_url` externe reste hors Qdrant ; canonicalisation et déduplication sont réalisées
  dans PostgreSQL. Pendant un bump, un advisory lock bloque les écritures URL concernées ; le
  dry-run, la résolution des divergences puis l'UPDATE atomique terminent avant réouverture, ce
  qui interdit un doublon inter-version malgré le hash incluant la version.

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
- canonicalisation, pour `research_candidates` et `external_resources` : dry-run sans écriture,
  fusion d'une collision identique, collision divergente avec tâche de revue persistante après
  blocage, permutation injective de deux hashes via sentinelles de migration, et crash/rollback
  de la transaction de mutation sans activation partielle, repointage des liaisons candidates,
  merge-map/tombstone conservant les sync attempts append-only, et CHECK refusant une sentinelle
  hors migration.

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

Routes connecteur livrées dès P2 avec un adaptateur fake :

```text
GET    /api/v1/connectors
POST   /api/v1/connectors/karakeep/:connector_id/test
POST   /api/v1/connectors/karakeep/:connector_id/webhooks
POST   /api/v1/connectors/karakeep/:connector_id/reconcile
GET    /api/v1/research/:id/resources
POST   /api/v1/research/:id/resources/:resource_id/save
POST   /api/v1/research/:id/resources/:resource_id/retry-sync
POST   /api/v1/research/:id/resources/:resource_id/promote
GET    /api/v1/ingestions/:id
GET    /api/v1/claims/:id
```

Les deux lectures ingestion/claim passent par repositories `ScopedQuery`, servent les fixtures du
vertical slice et leurs cas ACL/404 sont nommés dans G2.

Le webhook compare le Bearer token en temps constant, applique taille/rate limit/schéma, valide
`payload.userId == connector.external_owner_id`, puis déduplique
`(connector_id, jobId, bookmarkId, operation)` avec une rétention de 30 jours, supérieure aux
trois tentatives totales/deux retries upstream pinnés. Il est seulement un signal d'invalidation :
le worker relit
`GET ${karakeep_base_url}/api/v1/bookmarks/:id` sur l'API Karakeep et applique l'observation si
`external_state_read_at` est monotone.
Un 404 authentifié devient `deleted_external`; réseau/5xx produit un retry sans changement. Le
webhook ne modifie jamais directement une preuve ou un bundle. Cette route POST réceptrice est
seule exemptée de session utilisateur et exige le Bearer hashé lié au `connector_id` exact du
chemin ; le token d'un autre connecteur est rejeté avant parsing du payload. Toutes les autres
routes exigent session et ACL.

Tests : une requête retrieval SQL non scopée échoue au typecheck/lint ; une identité étrangère ne
retourne aucune ligne par les repositories d'entités, claims, preuves, graphe, recherches,
ressources ou connecteurs.

### T2.4 — Relais outbox

- livraison at-least-once ;
- claim par `FOR UPDATE SKIP LOCKED` ;
- déduplication consommateur par `event_id` ;
- retry borné et dead-letter queue ;
- heartbeat ;
- métriques lag/échec/âge ;
- reconciler des états PostgreSQL/worker/Qdrant après crash ;
- tests arrêt entre claim, effet et ack ;
- événements `external_resource.save_requested`, `external_resource.tags_requested`,
  `external_resource.synced`, `external_resource.sync_failed` et
  `external_resource.deleted_external` ;
- événement `external_resource.promotion_requested` séparé de la synchronisation Karakeep ;
- événements Qdrant `knowledge_point.projection_requested`,
  `knowledge_point.projection_applied` et `knowledge_point.projection_failed` pour les
  `set_payload` mutables, avec idempotence par point/version ;
- projection de tags multivaluée par run (`research:<research_run_id>`,
  `role:<research_run_id>:<role>`, `status:<research_run_id>:<status>`,
  `decision:<research_run_id>:<decision>`) sans écraser les qualifications historiques ;
  lorsque `role=null`, aucun tag `role:*` n'est projeté.

### T2.5 — Rôle principal Prisme

Créer et tester `roles/prisme/` dès P2 : build/pin de l'image, réseau interne, PostgreSQL, Caddy
VPN-only, secrets `no_log`, healthchecks, dashboards, backup et runbook. Le compose possède et
borne : web/API+MCP `1 GiB`, outbox `384 MiB`, research worker `512 MiB`, navigateur de recherche
isolé `1536 MiB`, connecteur Karakeep `384 MiB`, indexer `512 MiB`, consolidation `384 MiB` et
sidecar `sparse-query-only` `1 GiB` et `prisme-db-proxy` `128 MiB`. Le rôle crée
`prisme_internal`, joint le proxy à `javisi_backend` avec IP fixe et joint explicitement le
service `prisme` aux réseaux Docker externes `javisi_frontend` utilisé par Caddy et
`javisi_backend` pour les seuls endpoints internes
`http://{{ project_name }}_qdrant:6333` et `http://{{ project_name }}_litellm:4000`, ainsi qu'au réseau externe interne
`prisme_connector_internal` pour les webhooks Karakeep. Le proxy écoute/autorise exclusivement le CIDR source de
`prisme_internal` : son listener bind uniquement son IP fixe `prisme_internal`, jamais
`0.0.0.0` ni son interface `javisi_backend`; cette dernière sert seulement à la sortie vers
PostgreSQL. Il refuse ainsi tout client de `javisi_backend`. Tous portent aussi une réservation,
respectivement `512/192/256/768/192/256/192/512/64 MiB` (somme `2 944 MiB`), en plus des hard
limits ; chaque worker a
un rollback stop/reprise indépendant. Le même digest embedding sert sur Banga et Sese, avec mode
différent et test de parité. P2 ne déploie que l'environnement local/fake ; T11.2 applique le rôle
sur Sese après gates.
Ces neuf couples sont les variables autoritaires `prisme_*_memory_limit` et
`prisme_*_memory_reservation` de `inventory/group_vars/all/docker.yml`; le compose ne contient
aucune seconde valeur littérale et la formule capacité lit ces mêmes variables.
Seuls `research-worker` et le navigateur isolé rejoignent aussi `javisi_egress`, avec politique
de sortie allowlistée, DNS contrôlé, proxy/timeout et tests SSRF. Web/API, outbox, indexer,
consolidation, sidecar sparse et `prisme-db-proxy` ne rejoignent jamais ce réseau d'egress.
Le rôle crée idempotemment le réseau Docker externe `prisme_connector_internal` avec
`internal: true` avant tout compose.
Le service compose normatif s'appelle `prisme`, écoute `3000` sur le réseau interne et sert
web/API/MCP. Sese tire le digest GHCR avec `vault_ghcr_pull_token` existant au coffre, sans
`default()`, sous `no_log`, smoke
de pull avant bascule et rotation documentée.
Construire l'OCI `linux/amd64` sur GitHub Actions x86_64 isolé (jamais Waza ARM64 ni Sese prod), publier au registre
approuvé puis pinner le digest dans `versions.yml`; Waza ne consomme pas cette image. Le préflight
inclut l'espace temporaire du build et nettoie uniquement le cache labellisé de ce build.
`roles/prisme/tasks/litellm-key-bootstrap.yml`, tag one-shot
`prisme_litellm_key_bootstrap`, ne tourne que depuis le contrôleur persistant : lookup préalable
par `GET /key/list?key_alias=prisme` authentifié avec la master key en header (alias non secret,
jamais de clé virtuelle en URL), puis `POST /key/generate` si absent, persistance sous `no_log`
dans `inventory/group_vars/all/prisme-secrets.yml` avec `ansible-vault`, vérification de
déchiffrement et commit par ce chemin seul avant tout
déploiement. `roles/prisme/tasks/litellm-key.yml` ne génère jamais : en CI/checkout éphémère il
exige `prisme_litellm_virtual_key`, retrouve son token ID par alias via l'API admin et valide
allocation/modèles sans placer la clé dans query string ou logs. Il échoue bruyamment si le
secret manque ou dérive (REX-62). Exposer spend/restant/refus, couper
les nouveaux jobs avant épuisement et prouver qu'aucun appel ne retombe sur une clé globale ni ne
change les budgets/keys existants.
Avant d'écrire ce bootstrap, un sibling test R4 interroge l'instance LiteLLM pinnée
`v1.83.3-stable` et vérifie le filtrage `key_alias`; s'il n'est pas supporté, le client pagine
`/key/list` puis filtre l'alias côté contrôleur, toujours sous master header/no-log et avec une
borne de pages. Aucun lookup silencieusement vide ne génère une seconde clé.
Le rôle suit `docs/standards/ANSIBLE-ROLE-CHECKLIST.md` et ansible-lint : tags
`[prisme, phase3, apps]`, logging
`json-file` `10m/3`, `state: present` avec `recreate: always` pour tout changement `env_file`, et
Molecule couvrant idempotence et configuration, sans prétendre exécuter Docker/health.
Un harnais `docker compose` d'intégration sur runner GitHub Actions x86_64 exécute health, HBA,
ACL proxy et tests réseau réels.
`inventory/group_vars/all/main.yml` déclare `prisme_enabled: false` et
`karakeep_enabled: false`; les guards de `site.yml` utilisent toujours
`| default(false) | bool`. Toutes les tâches/mutations Prisme sont gardées ; le précheck capacité
n'est fail-loud que lorsque `prisme_enabled=true`.
Le bloc route Prisme de `Caddyfile.j2` est sous
`{% if prisme_enabled | default(false) | bool %}` ; flags Prisme/Karakeep false, le rendu partagé
reste byte-identique à HEAD.

Gate G2 : API démarre avec PostgreSQL, sans Qdrant, sans instance Karakeep réelle et sans workers
d'acquisition/analyse. Le relais outbox et le lecteur de réconciliation tournent contre le fake
Karakeep pour prouver idempotence, déduplication multi-runs, convergence de webhooks inversés, ACL
et absence de cascade destructive. Le gate exécute aussi les quatre scénarios de migration de
canonicalisation sur les deux tables plus la permutation : dry-run, fusion identique, divergence
avec tâche persistée, permutation injective, crash atomique, CHECK sentinelle, repointage sans
doublon des liaisons candidates, merge-map/tombstone, sync attempts immuables/résolubles et
reconciler incapable de ressusciter un perdant.
G2 teste aussi doublon webhook, isolation inter-connecteur et expiration/purge auditée de
`webhook_delivery_receipts` à 30 jours.
Le harnais d'intégration x86_64 de G2 prouve : connexion Prisme via proxy autorisée, connexion directe depuis un
autre conteneur backend refusée, **et** connexion depuis un conteneur `javisi_backend` vers
`prisme-db-proxy:5432` refusée par l'ACL d'ingress du proxy, puis reload HBA sans restart.
Il prouve aussi que l'IP fixe du service `prisme` est refusée vers toutes les DB PostgreSQL en
direct et que proxy→DB `n8n` est refusé, tandis que proxy→DB Prisme reste vert.
Le test de rôle prouve aussi qu'avec `prisme_enabled=false`, le rendu HBA est byte-identique à
HEAD ; le préflight inspect prouve les deux IP libres sans mutation IPAM.
T11.2 répète ces preuves sur Sese puis
exécute les smokes n8n/Plane/LiteLLM avant de poursuivre.

## 6. P3 — Qdrant `knowledge_v1`

### T3.1 — Registre global des collections

Ajouter dans VPAI :

```text
docs/runbooks/QDRANT-COLLECTION-MANIFEST.md
inventory/group_vars/all/qdrant_collections.yml
```

Instance cible : Qdrant production sur Sese. Le bootstrap contrôleur utilise l'endpoint VPN-only
`https://qd.ewutelo.cloud:443`; le runtime Prisme utilise
`http://{{ project_name }}_qdrant:6333` sur `javisi_backend`, dans les deux cas avec API key au coffre.
Un smoke partant du conteneur `prisme` vérifie ce chemin interne avant G3. G3 inventorie cette instance exacte et
prouve que `trading_v1`, `memory_v3` et toute collection étrangère restent inchangées.

Le registre VPAI génère, via `scripts/generate-prisme-qdrant-registry`, le snapshot sans secret
`config/qdrant-collections.snapshot.yml` commité dans Prisme et son SHA-256 dans
`config/qdrant-collections.snapshot.sha256`. La CI VPAI régénère et diff le snapshot depuis la
source ; la CI Prisme vérifie le hash commité puis génère son client uniquement depuis ce
snapshot. Toute modification du registre impose le même commit d'intégration côté Prisme avant
déploiement ; aucune liste de collections codée à la main n'est autorisée.
T3.1 crée aussi `scripts/verify-qdrant-registry` dans Prisme ; la CI l'exécute pour vérifier le
hash avant toute génération du client.
Le snapshot porte `source_commit` VPAI et `qdrant_collections.yml` un `prisme_registry_ref`, mais
ces deux champs de traçabilité sont exclus du contenu canonique. L'intégrité repose uniquement sur
le SHA-256 RFC 8785/JCS : parser YAML, retirer les deux clés top-level, convertir vers JSON,
trier/canonicaliser selon RFC 8785, encoder UTF-8 sans BOM puis SHA-256. Les deux CI appellent le
même `scripts/qdrant-registry-canonicalize.mjs`, source VPAI copiée byte-for-byte dans Prisme avec
son propre SHA-256 vérifié, et les mêmes fixtures de conformité, pas deux implémentations. La
bibliothèque YAML est pinnée par lockfile et exécutée avec installation gelée ; les fixtures
couvrent `yes/no/on/off`, nombres et dates pour empêcher une coercition divergente. La CI VPAI
installe explicitement Node.js 22 pinné avant d'exécuter ce `.mjs`. Les CI privées font un
checkout read-only croisé avec le PAT dédié `PRISME_CROSS_REPO_READ_TOKEN` (`contents:read`
strictement sur VPAI/Prisme/Banga), sous masquage/no-log ; son absence vérifiée est un blocker
d'accès. Mise à jour en deux commits : Prisme régénère depuis
VPAI et publie son commit, puis VPAI met à jour `prisme_registry_ref`; les deux CI régénèrent et
comparent le hash normalisé, tandis que les refs servent seulement à l'audit. Toute dérive métier
fait échouer les deux côtés sans auto-référence de commit.
Le registre porte aussi la politique de cibles de test `prisme_test_*`; elle est générée avec
les collections/alias, jamais ajoutée localement à la main.

Pour chaque collection :

```text
name, owner, purpose, source_of_truth, producer, consumers,
vector_schema, payload_schema, retention, backup, mutation_policy
```

`trading_v1` y apparaît comme `owner: hawktrade`, `mutation_policy: deny-from-prisme`.
Pour toute collection étrangère, `vector_schema`/`payload_schema` peuvent être
`owner-declared` : Prisme ne lit alors que les métadonnées de collection nécessaires au diff G3,
jamais points, vecteurs ou payloads.

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

- allowlist obtenue du snapshot généré : `knowledge_v1`, `knowledge_current`, `prisme_test_*` ;
- `prisme_test_*` n'est activé que si `PRISME_TEST_MODE=true` **et** endpoint Qdrant
  loopback/éphémère attesté ; sur `qd.ewutelo.cloud` toute cible de test est refusée avant réseau ;
- default-deny avant tout appel réseau ;
- aucune méthode `deleteCollection`, `recreateCollection` ou `snapshotRestore` exportée ;
- `buildSecurityFilter(SecurityContext, asOf)` obligatoire ;
- filtre ACL/validité/index actif injecté dans chaque prefetch dense et BM25 ;
- import direct du SDK Qdrant interdit hors du package.

Un outil ops séparé `scripts/qdrant-alias-rollback` est le seul à pouvoir retirer/rebasculer
`knowledge_current` : cible exacte issue du registre, état avant/après, double confirmation gate,
journal JSON et aucune méthode collection destructive. Il n'est ni importable ni exécutable par
le runtime.

`ids.ts` inclut `knowledge_item_id`, artefact, identité canonique, `doc_kind`, `knowledge_kind`,
index de chunk, SHA-256 du texte exact de l'unité, schéma, `taxonomy_version`, `ontology_version`,
modèles dense et sparse, chunker, prompt de construction du texte canonique, prompt embedding et
`index_generation`. Deux unités issues du
même chunk restent distinctes et tout changement vectoriel produit une nouvelle identité.
Ici `prompt_version` versionne l'extraction/construction du texte canonique et
`embedding_prompt_version` versionne uniquement le formatage documentaire/requête envoyé au
modèle ; aucun troisième prompt embedding implicite.
Il sérialise explicitement `SEP=0x1f` et `null="-"`; le test cross-runtime compare TypeScript et
Python sur valeurs nulles et refuse séparateur/valeur sentinelle métier.

Les indexes couvrent au minimum `taxonomy_namespace`, `taxonomy_version`, `ontology_version`,
`provenance_class`, `room`, `topic_path`, `topic_ancestors`, `entity_ids`, `entity_kinds`,
`doc_kind`, `knowledge_kind`, `source_provenance_classes`, `knowledge_item_id`, `artifact_id`,
`canonical_id`, `canonical_url` documentaire et tous les champs sécurité/validité de la spec.
`topic`, `embedding_dim`, `relative_path` et `content_sha256` restent hors index.
`wing` reste dans le payload comme alias local transitoire mais tout filtre `wing` est réécrit côté serveur vers
`provenance_class`; aucun index redondant n'est créé.
`index_generation` fait partie des indexes integer minimaux ; `chunk_total` et `deleted_at`
restent explicitement hors index Qdrant.

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
- incrémenter `index_generation` produit un point ID distinct et la génération inférieure n'est
  plus servie après activation ;
- deux unités issues du même chunk donnent deux points distincts ;
- deux versions d'une même unité partagent `canonical_id` et sont dédupliquées au retrieval ;
- enums `doc_kind` mutuellement exclusifs et combinaisons `doc_kind/knowledge_kind` valides ;
- alias exact VPIN/VWAP/HMM/OBI et Mean Reversion routés vers les bonnes entités/strategy-family ;
- ACL étrangère, point expiré, staging et deleted exclus dans dense, BM25 **et graphe SQL** ;
- `buildValidationFilter()` conserve tenant/ACL mais retrouve le staging pour l'indexeur seulement ;
- un point sans `valid_to` ou avec `valid_to=null` est refusé avant upsert ;
- timeout ;
- alias atomique.
- identité UUIDv5 TypeScript/Python identique avec `knowledge_kind=null`, séparateur `0x1f` et
  sentinelle `-`.

### T3.4 — Smoke prod read-only puis création

Avant mutation :

- inventorier noms/schémas ;
- sauvegarder le rapport ;
- confirmer absence de `knowledge_v1` ;
- vérifier health/snapshot policy.
- mesurer mémoire/stockage actuels du Qdrant partagé, estimer l'empreinte du golden puis du volume
  cible avec marge de 30 %, et vérifier que limite conteneur + capacité Sese les absorbent sans
  réduire la réserve de `memory_v3`/`trading_v1`. Toute hausse de limite ou relocalisation est une
  décision G0 capacité avant mutation.

La création vide de `knowledge_v1` est déjà autorisée par le prompt : après revue enregistrée du
rapport, le gate automatique autorise cette mutation bornée sans nouvelle intervention humaine.
Elle reste bloquée tant que les tests client/ACL/identités de T3.2/T3.3 ne sont pas verts.

Après création :

- `knowledge_v1` green ;
- 0 point ;
- schéma exact ;
- tous les indexes présents ;
- schéma, configuration et alias des autres collections inchangés ; leur nombre de points peut
  évoluer sous leurs producteurs normaux, mais le journal default-deny prouve que Prisme n'a émis
  aucune mutation vers elles.

Gate G3 : diff avant/après et journal client prouvent que seule `knowledge_v1` et son alias ont
reçu une mutation Prisme ; toute variation de points étrangère est attribuée à son producteur.

## 7. P4 — Banga knowledge plane

Travaux dans `/home/mobuone/work/infra/banga`.

### T4.0 — Gate de placement et capacité

Avant T4.2, T4.4 et T4.5, inventorier en lecture seule les LXC Banga existants, Docker, GPU,
passthrough NVIDIA, RAM/disque et charges. Choisir uniquement un LXC existant déjà approuvé,
Docker-capable et doté du GPU requis, ou documenter le besoin d'un LXC dédié
`lxc-prisme-knowledge`. Ne jamais supposer que `lxc-chat` ou `lxc-infer` satisfait ces propriétés.
Toute création de LXC, extension de passthrough GPU ou relocalisation de charge constitue une
décision G0 placement/capacité : si elle n'est pas déjà approuvée et déductible, statut
`AWAITING_G0_BANGA_PLACEMENT` et aucune mutation d'infrastructure. Gate G4.0 : cible, capacité,
isolation, runtime Docker et accès T4 GPU prouvés avant tout service de calcul.

Dépendance dure : le pool ZFS `tank` et son provisioning ZFS sont verts avant toute création de
dataset Prisme. Le NO-GO offsite global Banga reste déclaré et n'est pas contourné ; il ne bloque
pas la création idempotente de `tank/knowledge`. La couverture 3-2-1-1-0 propre à ce dataset est
une tâche Prisme obligatoire avant G10. Si le pool/provisioning est rouge, P4 s'arrête sans créer
de stockage alternatif.

### T4.1 — ZFS

- entrée pool-relative dans `zfs_datasets` :
  `{name: knowledge, recordsize: "1M", compression: lz4, quota: "<mesuré T4.1>",
  reservation: "none"}` ; dataset résultant `{{ zfs_pool_name }}/knowledge`
  (`tank/knowledge` aujourd'hui), quota initial validé ;
- sous-arborescence `incoming`, `library`, `research`, `experiments`, `exports`, `quarantine`;
- permissions distinctes ;
- snapshots ;
- snapshots locaux dès P4 ; définition versionnée de la politique backup Prisme, dont la copie
  offsite via zerobyte v3 et le restore drill deviennent effectifs et verts avant G10 ;
- métriques quota ;
- aucune réservation avant mesure.

Avant de fixer le quota, T4.1 exécute un préflight read-only Prisme qui mesure
l'espace/allocation ZFS réel, les quotas effectivement appliqués et l'overcommit documenté. Le
quota projeté n'est autorisé que si l'utilisation projetée du pool, réserve snapshots comprise,
reste `<= 80 %` et si l'espace libre projeté reste `>= 5 TiB`; sinon le gate est rouge. Ajouter
l'entrée `name: knowledge` ci-dessus à `zfs_datasets` dans
`inventory/group_vars/all/main.yml` Banga, jamais `name: tank/knowledge`, puis appliquer
la phase de provisioning ZFS existante et ciblée : le `disk-guard` dérive ainsi ses métriques et
seuils de la même source autoritaire. `roles/knowledge-store` ne crée jamais le dataset
indépendamment : son préflight vérifie et échoue rapidement si dataset, mountpoint, owner ou quota
diffèrent. Il ne modifie aucun dataset étranger et aucun quota théorique n'est forcé.

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
Le rôle vérifie chaque chemin physique contre les six racines déclarées. Un `relative_path`
indexable est relatif à `/tank/knowledge` et conforme à l'un des patrons :

```text
library/<tenant>/<corpus>/<item>/<version>/{source|derived|knowledge}/...
research/<claim>/<run>/...
experiments/<experiment>/<run>/...
```

`incoming/`, `exports/` et `quarantine/` ne produisent jamais de point Qdrant. Les tests refusent
traversal, racine inconnue et mélange entre identifiants et taxonomie métier.

### T4.2 — Knowledge store

Rôle `knowledge-store` :

- tirer chaque image GHCR pinnée par digest avec le `vault_ghcr_pull_token` référencé au coffre Banga,
  tâches `no_log`, smoke de pull avant bascule et procédure de rotation ; l'absence réelle du
  secret est un blocker d'accès, jamais un fallback vers un tag public ;
- compte de transfert dédié ;
- SFTP/SSH restreint ;
- promotion atomique ;
- SHA-256 source/destination ;
- manifeste de bundle ;
- API interne de statuts ou callback signé ;
- API de lecture mesh-only authentifiée mTLS/service-token : manifests par IDs, transcript et
  artefacts avec Range, quotas taille/temps, chemin reconstruit/validé côté serveur sans paramètre
  de chemin libre. L'indexer Sese la consomme ; Prisme proxifie les lectures utilisateur après
  revalidation tenant/ACL PostgreSQL ;
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
Le digest produit par `roles/knowledge-embedding` est écrit dans
`/home/mobuone/work/infra/banga/inventory/group_vars/all/versions.yml`, puis propagé exactement
dans VPAI `inventory/group_vars/all/versions.yml`; les CI cross-repo refusent toute divergence via
le checkout read-only et `PRISME_CROSS_REPO_READ_TOKEN` définis en T3.1.

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

Déployer uniquement avec `playbooks/hosts/workstation.yml --tags prisme-fetcher`; interdire
l'exécution non taggée de ce playbook partagé. Le rôle suit la checklist Ansible, ansible-lint,
tag exclusif `[prisme-fetcher]` afin qu'un run générique `workstation`/`services` ne l'active
jamais, `prisme_fetcher_enabled: false` dans les defaults et
`when: prisme_fetcher_enabled | default(false) | bool` au niveau rôle dans
`playbooks/hosts/workstation.yml`, Molecule et un second run idempotent avant G5.

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

- l'indexer est l'unique écrivain Qdrant : il consomme les événements outbox de projection ; API
  et relais ne font jamais de `set_payload` directement. Il gère staging/activation/expiration et
  acquitte l'événement après lecture de contrôle ;
- écrire bundle Banga ;
- enregistrer PostgreSQL ;
- encoder via `embedDocument()`/`embedSparse()` du contrat T1.4 ;
- produire des IDs déterministes incluant toutes les versions ;
- écrire le ledger `index_points` ;
- upserter d'abord avec `index_state=staging` ;
- upsert batch ;
- vérifier count/source IDs/retrieval via `buildValidationFilter()` réservé à l'indexeur ;
- passer le nouveau point Qdrant `active` sans invalider l'ancien ;
- activer ensuite la nouvelle version PostgreSQL ; tester un crash entre ces deux étapes et
  prouver que l'ancienne reste servie ;
- dédupliquer la coexistence transitoire au retrieval, puis marquer l'ancienne version PostgreSQL
  `superseded` et enfin poser `valid_to` sur l'ancien point ;
- vérifier côté PostgreSQL que toute connaissance servie est active ;
- réconcilier tout état partiel après crash ;
- tester un crash entre chaque étape, notamment activation Qdrant et activation PostgreSQL ;
- marquer `indexed` seulement après lecture de contrôle.
- le worker consolidation consomme les événements de supersession, vérifie la coexistence bornée
  et déclenche le reconciler sans supprimer l'historique.
- pour un changement modèle/chunker/prompt/ontologie sans version métier, utiliser
  `index_generation` : staging/validation/activation de la nouvelle génération sur le même
  `knowledge_item_id` actif, point ID distinct, déduplication par génération active maximale
  validée dans `index_points`, puis expiration de l'ancienne, avec crash tests garantissant
  toujours une génération servable.

Gate G6 : trois fixtures produisent bundles valides et points retrouvables sans doublon ; changer
modèle/chunker/prompt crée de nouveaux IDs et conserve l'historique.

## 10. P7 — Contre-vérification et expériences

### T7.0 — Instance Karakeep optionnelle

Créer et tester `roles/karakeep/` après le fake contractuel G2. G7 reste sur fake ; aucun
Karakeep réel n'est déployé avant que T11.2 ait créé le réseau et le service Prisme sur Sese.
Après T11.2 seulement, la branche `karakeep_enabled=true` peut appliquer ce rôle si ses gates
capacité/DNS sont verts :

- image `v0.32.0` pinnée par digest dans `versions.yml` ;
- `karakeep_subdomain` déclaré dans l'inventaire ; ne jamais exécuter directement
  `playbooks/utils/vpn-dns.yml` ici. T7 prépare seulement rôle/config ; T11.2 exécute le protocole
  sécurisé T10.5 complet juste avant tout déploiement réel, puis crée la route VPN-only via les
  deux CIDR du registre Caddy. Aucun A public n'est requis par l'ACME DNS-01 ;
- compte local mono-tenant et API key sortante au coffre ;
- Bearer entrant généré par Prisme et stocké au coffre. Faute d'API webhook upstream, un setup
  Playwright idempotent sous compte opérateur du coffre configure `/settings/webhooks` sans
  exposer credentials/screenshots, puis relit l'écran pour vérifier l'URL
  `http://prisme:3000/api/v1/connectors/karakeep/:connector_id/webhooks` sur le réseau interne et
  les événements `created`, `crawled`, `edited`, `deleted`. Le jeton fait au plus 100 caractères
  conformément au schéma upstream.
  L'enregistrement et sa vérification précèdent toute activation ;
- tâches secrètes `no_log`, healthchecks, ressources bornées ;
- joindre le réseau Docker externe partagé `prisme_connector_internal` (`internal: true`), créé
  par `roles/prisme`, pour les webhooks `http://prisme:3000`; ce transport n'utilise pas Caddy ;
- joindre le web Karakeep à `javisi_frontend` pour sa route Caddy VPN-only ; seuls ses composants
  de crawl sortant rejoignent `javisi_egress` sous allowlist et contrôles SSRF. Aucun autre
  composant Karakeep ne rejoint l'egress ;
- backup des données et restore smoke ; Meilisearch reste reconstructible ;
- `karakeep_enabled=false` par défaut dans `inventory/group_vars/all/main.yml`.
- `roles/karakeep` suit la checklist Ansible, tags `[karakeep, phase3, apps]`, ansible-lint,
  Molecule et un second run idempotent
  avant toute activation.

Le déploiement accepte l'usage AGPL-3.0 du composant isolé. Aucun code Karakeep n'est copié ou
modifié dans Prisme sans nouvel ADR et revue de licence.

Pré-check bloquant avant création de conteneur :

- après réservation des limites Karakeep,
  `MemAvailable + RSS_Karakeep_déjà_running - somme(limites Karakeep) >= 1 GiB` ; au premier
  déploiement RSS vaut zéro, évitant tout double comptage lors d'un redeploy ;
- PSI mémoire `avg10 < 10 %` et aucun swap-in/swap-out soutenu sur 15 minutes ;
- espace libre `/ >= 25 GiB` et utilisation `<= 75 %` ;
- limites : web `2 GiB`, Chrome `2 GiB`, Meilisearch `1536 MiB`.

Une mesure hors seuil met uniquement la branche de déploiement Karakeep réel au rouge : aucune
installation n'est tentée. La baseline actuelle de Sese et la réserve RAM requise imposent donc
remédiation/capacité avant ce déploiement, mais les branches fake et `karakeep_enabled=false`
continuent vers les gates aval.

### T7.1 — Research worker

- queue PostgreSQL ;
- provider de recherche interchangeable ;
- recherche favorable/contradictoire ;
- persistance de la requête, stratégie, provider, budget, timestamps et résultats sélectionnés ;
- canonicalisation URL avant toute sauvegarde : redirections, tracking et fragments non
  sémantiques ;
- `canonicalizeUrl()` partagé et versionné ; recalcul/réconciliation transactionnel des
  candidats et ressources obligatoire à chaque bump, avec collision divergente bloquante ;
- base URL Karakeep issue de l'allowlist Ansible ; résolution DNS, redirect et filtre SSRF
  appliqués avant l'outbox sur research worker, sauvegarde manuelle et reconciler ;
- une URL refusée par Prisme n'est jamais déléguée au crawler Karakeep ;
- qualification source ;
- hash/date ;
- budget ;
- timeout ;
- cache ;
- allowlist sensible ;
- protection SSRF ;
- contenu externe marqué non fiable.

Politique par défaut :

```text
SERP seulement                  → éphémère, non envoyé à Karakeep
ouvert|analysé|cité|rejeté     → durable Prisme + save_requested
capture Karakeep réussie       → synced, copie de commodité
conservation durable autorisée → promotion séparée et hashée sur Banga
```

### T7.2 — Connecteur Karakeep

Implémenter `workers/connectors/karakeep` derrière les ports :

```text
BookmarkSink.health()
BookmarkSink.upsertLink(canonicalUrl, metadata)
BookmarkSink.upsertText(researchSummary)
BookmarkSink.ensureList(path)
BookmarkSink.applyProjection(resource, tags, list)
BookmarkSink.reconcile(resource)
```

Le port n'expose volontairement aucun delete. Après fusion, le bookmark perdant est marqué
`duplicate_external`/lié au survivant et n'est plus projeté ni recréé ; le reconciler garantit
zéro nouveau doublon créé par Prisme, sans promettre la suppression destructive d'un ancien
bookmark Karakeep.

Les ports/types vivent dans `src/lib/server/connectors/`; l'unique implémentation HTTP est le
worker TypeScript `workers/connectors/karakeep`. Aucun second client Karakeep n'est implémenté en
Python ou dans les routes web.

L'adaptateur Karakeep :

- utilise uniquement l'API REST officielle avec Bearer token du coffre ;
- utilise `http://karakeep:3000` sur `prisme_connector_internal` comme base URL interne normative,
  jamais le FQDN Caddy pour le trafic inter-conteneurs ;
- ne lit ni SQLite, ni Meilisearch, ni filesystem Karakeep ;
- crée ou retrouve le bookmark URL, puis applique liste et tags dans des appels idempotents ;
- conserve `external_id`, deep link, version de projection et réponse minimale caviardée ;
- projette `Prisme / Recherches`, `prisme`, `research:<research_run_id>`, `topic:<slug>`,
  `role:<research_run_id>:<role>`, `status:<research_run_id>:<status>` et
  `decision:<research_run_id>:<decision>` depuis les enums fermés
  `role=supporting|contradicting|context|primary_source|rejected` avec champ nullable,
  `status=opened|analyzed|cited|archived_banga` et
  `decision=pending|selected|rejected|promotion_requested|promoted`, jamais depuis du texte LLM
  libre ;
- dérive `<slug>` exclusivement du dernier segment normalisé de `topic_path` autoritaire
  (registre taxonomie/version), jamais d'un libellé LLM ;
- borne concurrence, timeout, retry exponentiel avec jitter et circuit breaker ;
- classe 401/403 comme terminal jusqu'à rotation du secret, 429/5xx comme retryable ;
- traite `200 existing` et `201 created` comme succès équivalents ;
- n'empêche jamais le research worker de conclure lorsque Karakeep est indisponible ;
- souscrit et ingère `created`, `crawled`, `edited` et `deleted` comme signaux idempotents ;
  `ai tagged` reste désactivé au MVP ;
- marque `deleted_external` sans supprimer Prisme/Banga/Qdrant ;
- propose un reconciler paginé par curseur et un mode report-only avant réparation ;
- expose métriques, traces et dead letters sans URL sensible ni token.

Après rotation, le runbook teste d'abord le nouveau jeton, puis réarme explicitement et de manière
auditée les ressources `failed_terminal` concernées ; aucune reprise globale implicite.

Tests contractuels sur fake server :

- create, duplicate, update tags/list, timeout, 401, 429, 500 et réponse malformée ;
- URL avec redirect/tracking, SSRF et hostname interdit ;
- crash après effet Karakeep avant ack outbox ;
- webhook dupliqué, Bearer invalide et deux signaux inversés convergeant vers l'état relu via API ;
- `userId` étranger, rate limit et expiration de la fenêtre de déduplication ;
- Karakeep désactivé ou absent ;
- réconciliation drift `missing|changed|deleted_external` ;
- zéro modification du verdict, du bundle Banga et de `knowledge_v1`.

### T7.3 — Promotion research vers Banga

La commande `promote` :

- exige droit de capture/archivage et autorisation explicite ;
- émet `external_resource.promotion_requested`, distinct de `save_requested` ;
- télécharge dans le navigateur de recherche isolé avec les mêmes règles SSRF ;
- écrit manifeste et SHA-256 source/destination sous
  `research/<claim_id>/<research_run_id>/` ;
- reste `awaiting_claim` lorsqu'aucun claim n'est attaché, sans inventer de chemin ;
- n'utilise jamais la copie Karakeep comme autorité implicite.

Tests : idempotence, checksum, droits absents, crash avant/après promotion et aucune mutation
Karakeep/Qdrant.

### T7.4 — Vérification

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

### T7.5 — Revue

Workflow :

```text
pending → in_review → approved|rejected|needs_more_evidence
```

Finance/santé/droit/sécurité : aucun `supported` sans reviewer humain.

### T7.6 — Expériences

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

- une recherche conserve sa requête et les seules URL réellement évaluées ;
- chaque URL ouverte, citée et rejetée est dédupliquée puis visible dans l'instance de test ou le
  fake contractuel lorsque `karakeep_enabled=true` ;
- un résultat SERP non ouvert n'est pas sauvegardé ;
- une panne Karakeep laisse la vérification fonctionnelle et produit un retry observable ;
- une suppression Karakeep ne supprime aucun contenu canonique ;
- une source autorisée est promue séparément vers Banga avec checksum ;
- un claim supporté ;
- un claim contesté ;
- un claim insuffisant ;
- une injection indirecte neutralisée ;
- une expérience reproductible ;
- aucun verdict sensible sans humain.

Avec `karakeep_enabled=false`, les critères de visibilité/suppression externe sont non
applicables ; journal PostgreSQL, fake contractuel, désactivation et non-blocage restent
obligatoirement verts.

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
3. `/claims/:id` sur fixtures G2 ;
4. `/items/:id` après disponibilité du worker ;
5. `/research/:id` et `/research/:id/resources`;
6. `/settings/connectors`;
7. `/review`;
8. `/ask`;
9. `/library`;
10. dashboard/admin.

Sur fixtures, livrer `/ingestions/:id` et `/claims/:id` dès G2, avant les workers réels. Les autres
pages suivent dans P8.

La vue recherche distingue requêtes, résultats non retenus, URL examinées, rôle probatoire, motif
de rejet, état Karakeep et état canonique Banga. Elle propose sauvegarde manuelle, retry, ouverture
Karakeep et promotion Banga. Aucun badge `Dans Karakeep` ne signifie `Vérifié` ou `Archivé`.

### T8.3 — Tests UX

- 360, 768, 1280, 1600 et 1920 px ;
- clavier ;
- axe ;
- contrastes ;
- reduced motion ;
- états vide/erreur/partiel ;
- lien timestamp ;
- citations très longues et textes sans espaces ;
- Karakeep absent, lent, désynchronisé ou ayant supprimé un bookmark ;
- déduplication visuelle d'une URL rencontrée dans plusieurs recherches ;
- aucune couleur seule ;
- tests visuels sur pages critiques.

Gate G8 : un utilisateur peut soumettre, approuver, lire, vérifier et retrouver une preuve sans
CLI ni accès direct aux machines. P8 peut être implémenté en parallèle de P7, mais G8 n'est évalué
qu'après G7 vert afin que l'action « vérifier » soit réelle.

## 12. P9 — Retrieval, réponses et MCP

### T9.1 — Search API

- client Embedding : dense+BM25 avec dégradation BM25-only explicite ;
- parser versionné des intentions `explore`, `learn`, `verify`, `source`, `compare` ;
- résolution préalable des entités, acronymes, alias, `room`, `topic_path`, temporalité et
  `provenance_constraint` explicite ;
- filtre `SecurityContext` injecté dans chaque prefetch dense/BM25 et
  `applySecurityScope(queryBuilder, ctx, asOf)` obligatoire pour chaque requête SQL ;
- candidats dense/BM25 fusionnés via RRF ou DBSF sur l'alias `knowledge_current` ;
- revalidation obligatoire du top-k fusionné par `applySecurityScope(ctx, asOf)` : écarter toute
  ligne absente, révoquée, expirée, supprimée ou inactive avant rescoring/citation/retour ;
  sur-récupération bornée à `min(3*k, 200)` avec métrique d'épuisement ;
- graphe PostgreSQL utilisé seulement pour les survivants, comme features/voisins autorisés,
  jamais injecté comme distribution non scorée dans DBSF ;
- ACL, `valid_from<=as_of`, `valid_to>as_of`, `index_state=active` et `is_deleted=false`
  obligatoires ;
- `provenance_class` utilisé comme facette, diversification et boost dépendant de l'intention,
  jamais comme filtre dur implicite ni score de vérité ;
- boost borné pour entité exacte, topic, adéquation `doc_kind/knowledge_kind`, vérification et
  temporalité ;
- versions actives ;
- pour un même `knowledge_item_id`, garder uniquement l'`index_generation` active maximale
  confirmée dans `index_points` avant la déduplication par `canonical_id` ;
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
- lecture de `GET /answers/:id/citations` via repositories scoppés : revalider chaque citation au
  moment du read avec `securityAsOf=now()` même pour une answer historique, masquer les citations
  révoquées/takedown et retourner `effective_visibility_status=stale_redacted` sans écriture.
  L'événement outbox de révocation/takedown persiste idempotemment
  `answers.visibility_status=stale_redacted` (enum `active|stale_redacted`); aucune preuve retirée
  n'est renvoyée ;
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
- aucun tenant étranger ne fuit via recherches, ressources externes, connecteurs ou leurs routes ;
- une révocation ACL et un takedown PostgreSQL restent absents du résultat/citation pendant un lag
  Qdrant artificiellement maintenu, grâce à la revalidation finale `applySecurityScope()` ;
- une answer sauvegardée avant révocation ne restitue ensuite aucune citation retirée et devient
  `stale_redacted` à la lecture ;
- pendant la coexistence de réencodage, aucun résultat d'une génération inférieure à la génération
  active maximale du ledger n'est servi ;
- une requête sans `provenance_constraint` trace zéro filtre dur de provenance ;
- le mode BM25-only est visible et passe son golden dégradé ;
- le sidecar `sparse-query-only` tourne dans le harnais compose GitHub Actions x86_64 pendant P9,
  jamais sur Waza ARM64 ; le golden BM25-only de G9 est donc mesuré hors Sese avant son
  déploiement production T11.2 ;
- une baseline de lag PostgreSQL/Qdrant est mesurée en P9 et son seuil provisoire documenté avant
  G9 ; T10.2 le transforme ensuite en alerte opérable sans réécrire rétroactivement G9.

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
- mouvement latéral depuis un conteneur Prisme compromis vers PostgreSQL ou une DB étrangère ;
- replay callback ;
- vol du Bearer token Karakeep ;
- webhook Karakeep sans Bearer valide, rejoué ou signaux inversés ne convergeant pas après
  relecture API ;
- SSRF via URL, redirect ou base URL de connecteur ;
- confusion `deleted_external` avec purge Prisme/Banga ;
- tag/list forgé par contenu ou LLM ;
- job dupliqué ;
- expérience échappant au sandbox ;
- verdict IA non revu.

Créer tests et mitigations explicites.

### T10.2 — Observabilité

- spans OpenTelemetry ;
- métriques files/latence/coût/qualité ;
- métriques `qdrant_projection_lag_seconds`, écarts de projection et mode retrieval actif ;
- métriques `karakeep_sync_total`, lag, retry, dead letters, circuit et drift de réconciliation ;
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
- couverture de capture : URL ouvertes/analysées/citées/rejetées sauvegardées, SERP non examinés
  exclus ;
- précision de déduplication/canonicalisation URL ;
- invariants d'indépendance Karakeep/Prisme/Banga ;
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
docs/runbooks/KARAKEEP-CONNECTOR.md
docs/runbooks/INCIDENT.md
docs/runbooks/MODEL-MIGRATION.md
```

Dans VPAI/Banga : déploiement, stockage et DR.
Créer nommément dans VPAI `docs/runbooks/PRISME-DEPLOYMENT.md` et dans Banga
`docs/runbooks/KNOWLEDGE-STORE.md`.

La politique backup Prisme de `tank/knowledge` déclare ce dataset comme source du hub unique
zerobyte v3 en PULL SSH, phases P6/P6b et leurs gates. Prisme ne crée/configure ni bucket, ni
credential, ni chaîne offsite parallèle. Ses livrables sont sélection des sous-chemins, rétention,
snapshots locaux, preuve qu'un flux vide/tronqué échoue, fixture non vide et restore drill depuis
la copie NAS vers dataset temporaire avec comparaison SHA-256. L'Object-Lock COMPLIANCE,
facturation, escrow et compatibilité prune↔lock restent sous les gates humains zerobyte v3 via
`review-file.sh`/`notify-gate.sh`; destination absente donne `AWAITING_OFFSITE_DESTINATION`.
Cette intégration ne marque jamais la phase2 Banga globale comme verte.

### T10.5 — Capacité et split-DNS

- remesurer Sese et appliquer uniquement des remédiations réversibles sans arrêter de service
  étranger : nettoyage de caches/artefacts Prisme jetables, arrêt des stacks de test Prisme,
  et ajustement des limites Prisme mesurées. Ajouter du swap ne satisfait jamais le gate ;
- si les seuils restent rouges, ouvrir la décision G0 placement/capacité avant toute dépense,
  relocalisation ou interruption de service ;
- déclarer `prisme_subdomain` et `karakeep_subdomain` dans
  `inventory/group_vars/all/main.yml`, les inclure dans `roles/vpn-dns/defaults/main.yml`, puis
  rendre le template complet et sauvegarder config/compose Headscale avant exécution de
  `playbooks/utils/vpn-dns.yml` sur Seko-VPN ;
- avant ces deux ajouts, lire les `extra_records` live Headscale et les différer contre le rendu
  actuel du template. Réconcilier dans un commit/test séparé chaque record vivant absent du
  template — au minimum `lxc_chat_subdomain` (`chat`), `grapesjs_subdomain` (`wizy`) et
  `webhook_subdomain` (`hook`) s'ils sont live — puis prouver un rendu sans suppression. Ce gate
  de conservation doit être vert avant le commit Prisme/Karakeep ;
- le protocole `playbooks/utils/vpn-dns.yml` assert avant toute écriture que
  `_vpn_dns_workstation_ts_ip | length > 0` et qu'aucun record live n'est absent du rendu.
  L'assert est implémenté dans `roles/vpn-dns/tasks/main.yml`, exactement entre
  `VPN-DNS | Parse current config` et `VPN-DNS | Write updated Headscale config`, en comparant
  `_hs_config.dns.extra_records | map(attribute='name')` comme sous-ensemble de
  `vpn_dns_records | map(attribute='name')` ;
- dans `playbooks/stacks/site.yml`, garder le rôle `vpn-dns` par
  `when: _vpn_dns_workstation_ts_ip | default('') | length > 0`; un site complet sans facts Waza
  saute ce rôle au lieu d'échouer/écrire, et un test de non-régression prouve le run vert. Seul
  `playbooks/utils/vpn-dns.yml` est autorisé à effectuer l'apply complet ;
- avant apply, vérifier que tous les `extra_records` existants (`mayi`, `llm`, `tala`, `qd`, etc.)
  sont inchangés et que seuls les deux nouveaux noms apparaissent ; le smoke inclut explicitement
  les records Waza `oc`, `studio`, `re`, `cut`, `pencil`, `tube` et `cine`, plus chaque record
  existant découvert dynamiquement ; après restart, smoke de tous
  les anciens et nouveaux FQDN depuis un client VPN et refus hors CIDR ;
- au premier échec, restaurer les fichiers sauvegardés, redémarrer Headscale et re-smoker tous les
  anciens noms avant de laisser le gate rouge.
- G10 vérifie le hash/rendu, la conservation de tous les anciens records et smoke les FQDN déjà
  publiés sans apply. T11.2 applique ensuite inconditionnellement `prisme_subdomain`; il n'ajoute
  `karakeep_subdomain` que si Karakeep réel est activé.

### T10.6 — Rebuild Qdrant

Livrer `scripts/rebuild-knowledge-index` : Sese exporte d'abord un snapshot ledger tenant/ACL
scoppé, signé, chiffré age, hashé et à TTL court. Le compte SFTP restreint
`prisme-ledger-export`, clé/signature/chiffrement référencées au coffre, ne peut écrire que
`/tank/knowledge/exports/<export_id>/ledger/`; l'outbox transfère puis confirme le hash, et le TTL
purge source/destination. Aucune ACL PostgreSQL réseau n'est élargie. Le script lance sur Banga une instance
Qdrant éphémère dédiée, sur réseau et volume Docker temporaires sans route vers le Qdrant
production, lit ce snapshot et les manifests/artefacts Banga hashés, puis reconstruit une
collection de test. Il vérifie
comptes, hashes, payload/indexes, ACL et golden retrieval. Le teardown test-only accepte
explicitement de supprimer uniquement le conteneur et le volume dont le label UUID émis par ce
run correspond au rapport ; il n'utilise pas le wrapper runtime et refuse tout endpoint non local
ou volume non labellisé. Le drill ne touche ni `knowledge_v1` ni son alias. Un rapport prouve
qu'une instance vide retrouve l'état attendu depuis PostgreSQL + Banga, détruit le snapshot
temporaire selon TTL et prouve que tous les éphémères ont été nettoyés.

Gate G10 :

- threat model couvert ;
- dashboards actifs ;
- budget/clé virtuelle LiteLLM Prisme actifs, spend/restant/refus visibles, refus au-delà de
  l'allocation propre prouvé et répartition du cap global partagé documentée ;
- métriques Karakeep sync/lag/retry/dead-letter/circuit/drift actives ou explicitement
  `disabled` lorsque le connecteur l'est ;
- backup offsite `tank/knowledge` et restore drill Prisme réussis avec hashes ; si la destination
  ou son credential est réellement absent, G10 reste rouge et l'état terminal devient
  `AWAITING_OFFSITE_DESTINATION` avec la liste exacte des accès manquants ;
- backup PostgreSQL Prisme restauré dans une DB temporaire, intégrité/migrations/FK et smoke API
  verts, puis cleanup prouvé ;
- rebuild complet Qdrant vers une collection de test réussi depuis PostgreSQL + Banga ;
- golden baseline archivée ;
- aucune alerte critique ;
- secrets scan vert ; si Karakeep est activé, il couvre l'API key et le Bearer entrant réellement
  enregistré, sinon il couvre les noms/fixtures synthétiques sans exiger de secret réel.

## 14. P11 — Canary et production

### T11.1 — Préproduction

- environnement/stacks séparés sur runner GitHub Actions x86_64 éphémère dédié, jamais Waza
  ARM64 ni Sese production ;
- DB propre ;
- collection de test ;
- Karakeep de test ou fake server contractuel, jamais bibliothèque personnelle de production ;
- trois fixtures ;
- tests E2E ;
- restauration.

### T11.2 — Création production

- insérer `roles/prisme` puis, conditionnellement, `roles/karakeep` dans l'orchestration
  autoritaire `playbooks/stacks/site.yml`, immédiatement après `content-factory` dans la phase
  3/apps, avec `when: prisme_enabled | default(false) | bool` et
  `when: karakeep_enabled | default(false) | bool` ; ne pas créer de
  playbook Sese parallèle. `prisme_enabled` reste false jusqu'au gate capacité vert, afin qu'un
  `make deploy-prod` ordinaire ne bloque aucun rôle étranger. Le rollout Prisme par `site.yml`
  utilise obligatoirement `--skip-tags vpn-dns`; split-DNS est appliqué ensuite uniquement via le
  protocole T10.5 qui collecte les facts Waza. Sous flag true, le conteneur PostgreSQL indisponible
  fait échouer bruyamment ; si le rôle PostgreSQL n'a pas été joué mais que le conteneur est sain,
  le déploiement ciblé est autorisé ;
- mesurer sur Sese avant déploiement :
  `MemAvailable + RSS_Prisme_déjà_running - max(somme(réservations=2 944 MiB), RSS_p95_mesuré×1,3)
  >= 1 GiB`, **et** `somme(hard limits de tous les conteneurs actifs)/MemTotal <= 1,5`, **et**
  `RSS_étrangers_p95×1,3 + réservations_Prisme + 1 GiB <= MemTotal`; cette politique d'overcommit
  est consignée/acceptée dans l'ADR 0001. Puis pression mémoire PSI
  `avg10 < 10 %` et aucun
  swap-in/swap-out soutenu sur 15 minutes, espace libre `/ >= 15 GiB` et utilisation `/ <= 80 %`.
  La taille ou le pourcentage de swap n'est pas un critère substituable ; un seuil rouge bloque
  le déploiement et déclenche remédiation/capacité, sans abaisser le seuil ;
- re-exécuter idempotemment le bootstrap revu de `knowledge_v1` déjà créée en G3 et vérifier
  zéro diff inattendu ;
- vérifier clé virtuelle et budget LiteLLM Prisme avant tout job canary ;
- appliquer HBA via handler reload, démarrer le proxy, prouver accès proxy/refus backend direct et
  refus explicite backend→proxy, assert de disponibilité PostgreSQL, et smokes
  n8n/Plane/LiteLLM verts sans restart PostgreSQL ;
- appliquer migrations ;
- déployer d'abord Prisme et son réseau, services métier désactivés ;
- appliquer le protocole split-DNS sécurisé pour `prisme_subdomain`, puis smoke tous les anciens
  FQDN et Prisme avant route/healthchecks ;
- si `karakeep_enabled=true` et gates Karakeep capacité/DNS verts, appliquer ensuite
  le protocole T10.5 pour ajouter Karakeep, appliquer ensuite `roles/karakeep`, puis exécuter le setup Playwright
  idempotent de T7.0 ; sinon rester sur fake ;
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
8. recherche externe avec une URL ouverte, une citée, une rejetée et un résultat SERP non ouvert ;
9. si `karakeep_enabled=true`, synchronisation Karakeep et contrôle de
   déduplication/tags/liste ; sinon fake contractuel équivalent ;
10. simulation de panne puis retry et réconciliation sur instance de test ou fake ;
11. promotion autorisée d'une source vers Banga ;
12. vérification d'au moins un claim ;
13. revue humaine ;
14. question `/ask` avec citations ;
15. suppression du bookmark jetable sur instance de test ou fake et preuve qu'aucune purge
    Prisme/Banga/Qdrant ne se produit ;
16. purge simulée sur le canary ; purge réelle uniquement sur un artefact jetable créé pour ce test.

### T11.4 — Go/no-go bulk

Si l'autorisation Instagram manque, ne lancer aucune requête réelle : conserver P11 en
`AWAITING_LEGAL_AUTHORIZATION`, publier toutes les preuves pré-canary et l'unique action humaine
requise, sans marquer le bulk GO.

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
- Karakeep activé : déduplication, panne/retry, réconciliation et suppression sans cascade verts ;
- Karakeep désactivé : fake contractuel vert et aucun impact sur recherche/vérification ;
- coûts/capacité acceptés.

Sinon NO-GO et REX.
Gate G11 est le verdict GO de T11.4 après canary autorisé ; sans autorisation il reste
`AWAITING_LEGAL_AUTHORIZATION`, jamais vert implicitement.

## 15. Fichiers VPAI prévus

```text
inventory/group_vars/all/versions.yml
inventory/group_vars/all/docker.yml
inventory/group_vars/all/qdrant_collections.yml
inventory/group_vars/all/main.yml
inventory/group_vars/prod/main.yml
inventory/group_vars/all/prisme-secrets.yml  # nouveau, chiffré, jamais affiché dans diff/log
playbooks/stacks/site.yml
playbooks/hosts/workstation.yml
playbooks/utils/vpn-dns.yml
roles/prisme/
roles/prisme/tasks/litellm-key-bootstrap.yml
roles/prisme/tasks/litellm-key.yml
roles/prisme-fetcher/
roles/karakeep/
roles/caddy/templates/Caddyfile.j2
roles/vpn-dns/defaults/main.yml
roles/vpn-dns/tasks/main.yml
roles/postgresql/
roles/monitoring/
docs/runbooks/QDRANT-COLLECTION-MANIFEST.md
docs/runbooks/PRISME-DEPLOYMENT.md
scripts/generate-prisme-qdrant-registry
scripts/qdrant-registry-canonicalize.mjs
.github/workflows/prisme-contracts.yml
.github/workflows/prisme-registry.yml
```

Toute modification d'un rôle partagé doit être minimisée et couverte par non-régression.
Les checks nommés Caddy/PostgreSQL/monitoring/vpn-dns et les clés/budgets LiteLLM existants
doivent rester verts avant merge.
Pour PostgreSQL, le test vérifie l'ordre HBA allow proxy/reject base Prisme tous rôles avant
`host all all` backend, le rejet direct du superuser `postgres`, le handler reload sans restart et
les connexions n8n/Plane/LiteLLM inchangées.

## 16. Fichiers Banga prévus

```text
inventory/group_vars/all/main.yml
inventory/group_vars/all/versions.yml
inventory/group_vars/all/vault.example.yml  # déclare seulement le nom vault_ghcr_pull_token
roles/knowledge-store/
roles/knowledge-worker/
roles/knowledge-embedding/
roles/experiment-runner/
docs/runbooks/KNOWLEDGE-STORE.md
.github/workflows/prisme-knowledge.yml
```

## 17. Stratégie de rollback

| Incident | Rollback |
|---|---|
| UI/API défectueuse | image précédente |
| worker Prisme (outbox/research/connector/indexer/consolidation/browser/sparse) | stop du seul service fautif, files/ledger conservés, reprise idempotente après correction |
| migration DB | compatibilité applicative précédente, pas de down destructive |
| PostgreSQL indisponible | fail closed, API retrieval/answers en `503`; aucun bypass Qdrant ou BM25-only sans revalidation SQL |
| index incomplet | désactiver `knowledge_current`, reconstruire depuis Banga |
| modèle embedding changé | nouvelle collection versionnée, ancien alias intact |
| chunker/prompt changé | nouveaux point IDs, ancienne version conservée jusqu'à validation |
| worker Waza | stop après item courant, reprise SQLite |
| worker Banga | bundle conservé, retry depuis état PostgreSQL |
| research provider | circuit open, claims restent pending |
| Karakeep indisponible | circuit open, outbox conservée, recherche continue, retry/reconcile |
| projection Karakeep erronée | désactiver sink, corriger mapping versionné, réconcilier |
| bookmark supprimé | marquer `deleted_external`, aucune cascade, recréer seulement sur action |
| API key sortante tournée | tester la nouvelle clé, réarmer explicitement les échecs 401/403, réconcilier |
| Bearer webhook tourné | générer au coffre, appliquer/vérifier par setup Playwright idempotent, puis révoquer l'ancien |
| clé virtuelle LiteLLM Prisme compromise/tournée | générer nouvelle clé/budget, tester Prisme, basculer secret chiffré, puis `POST /key/delete` sur l'ancienne sans toucher aux autres clés |
| split-DNS/Headscale défectueux | restaurer snapshot config/compose pré-apply, redémarrer Headscale, vérifier tous les anciens FQDN |
| purge erronée | snapshot/backup selon politique ; jamais promettre récupération non sauvegardée |

## 18. Definition of Done produit

- application autonome accessible VPN-only si le gate capacité Prisme est vert ; sinon tous les
  artefacts/tests/déploiements isolés sont livrés et le statut reste
  `AWAITING_G0_CAPACITY_DECISION`, jamais DoD complète ;
- si Banga n'a aucune cible Docker+GPU approuvée ou son credential GHCR, seuls P0–P3 et P8 sur
  fixtures sont livrables, G8 non évalué ; statut `AWAITING_G0_BANGA_PLACEMENT`, jamais P4–P11 ni
  DoD complète ;
- aucune dépendance métier à Palais/Open WebUI ;
- `knowledge_v1` dense 768 + BM25, fusion RRF/DBSF sélectionnée sur golden réel ;
- taxonomie versionnée, ontologie entités/topics et tous indexes vérifiés ;
- `provenance_class` canonique, `wing` simple alias local transitoire, jamais vérité ou filtre implicite ;
- VPIN, VWAP, HMM, OBI et Mean Reversion retrouvables par acronyme, nom, alias et sujet ;
- code Prisme séparé de tout contenu runtime, bundle canonique uniquement sur Banga ;
- Karakeep livré comme Inbox optionnelle déployable, sans copie de son code dans Prisme ; lorsque
  `karakeep_enabled=true`, son déploiement réel n'est exigé que si le gate de capacité est vert,
  sinon le fake contractuel et la branche désactivée doivent rester verts et opérables ;
- API/webhook Karakeep idempotents, API key et Bearer par-webhook au coffre, et aucune lecture
  SQLite/Meilisearch ;
- avec `karakeep_enabled=true`, URL ouvertes, analysées, citées ou rejetées sauvegardées
  automatiquement et dédupliquées ; sinon fake contractuel équivalent vert ;
- résultats SERP non examinés exclus par défaut ;
- requêtes et décisions de recherche autoritaires dans PostgreSQL ;
- synchronisation Karakeep non bloquante, observable, réconciliable et testée en panne ;
- suppression Karakeep sans cascade vers Prisme, Banga ou Qdrant ;
- promotion Banga distincte et explicitement autorisée ;
- aucune mutation de `trading_v1` ni autre collection protégée ;
- ingestion autorisée de bout en bout ;
- bundle canonique Banga ;
- extraction, vérification et expérience séparées ;
- revue humaine des risques élevés ;
- recherche/UI/MCP avec citations ;
- sécurité adversariale testée ;
- observabilité et coûts visibles ;
- restore drill réussi ; si l'offsite est réellement inaccessible, état
  `AWAITING_OFFSITE_DESTINATION` sans revendication de DoD complète ;
- canary accepté ;
- runbooks disponibles.

## 19. Ordre des premières sessions

```text
Session 1 : reprise v4 — audit/checkpoint v3 + G0 rouvert + delta P1 13→19 + G1 v4
Session 2 : PostgreSQL/API P2
Session 3 : Qdrant P3
Session 4 : Banga store P4
Session 5 : Waza fetcher P5
Session 6 : analyse/indexation P6
Session 7 : recherche + connecteur Karakeep + vérification P7
Session 8 : UI recherche/Inbox + vertical slice P8
Session 9 : retrieval/MCP P9
Session 10 : sécurité/evals/ops P10
Session 11 : canary P11
```

Chaque session produit tests, rapport et handoff ; elle ne présume pas le GO de la suivante.
