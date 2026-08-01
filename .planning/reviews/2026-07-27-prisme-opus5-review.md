# Revue Claude Opus 5 — Prisme

> Date : 2026-07-27
> Reviewer : Claude Opus 5 via `claude --model opus`
> Mode : lecture seule, deux passes (design puis exécution)
> Documents :
> - `docs/superpowers/specs/2026-07-27-prisme-knowledge-application-design.md`
> - `.planning/plans/2026-07-27-prisme-knowledge-application-execution.md`

## Verdict courant — passe 29

**READY — 0 P0, 0 P1, 5 P2 non bloquants.**

Le verdict courant est uniquement celui de cette section. Les verdicts suivants sont l'historique
chronologique des passes antérieures.

### Historique v1

Le reviewer jugeait l'architecture saine : séparation PostgreSQL/Banga/Qdrant, Qdrant
reconstructible, migrations sans wipe, gates explicites, séparation extraction/vérification/
expérience et isolement de `trading_v1`.

#### P0 design

1. L'identité d'un point doit inclure modèle, chunker et versions de prompts afin qu'une
   réanalyse ne remplace pas silencieusement l'historique.
2. L'asymétrie d'embedding document/requête doit être explicite, versionnée et testée.
3. ACL et validité doivent être injectées dans chaque prefetch dense et BM25, avant RRF.
4. Le client Qdrant doit être default-deny et autoriser uniquement `knowledge_v1`,
   `knowledge_current` et les collections de test.

#### P0 exécution

1. Les quatre corrections design doivent devenir des tâches/tests nommés dans le plan.
2. L'outbox PostgreSQL nécessite un relais at-least-once avec déduplication, DLQ et métrique lag.
3. Le modèle/tokenizer d'embedding doit être décidé et pinné avant le bootstrap.

#### P1

- ajouter `chunk_index`/`chunk_total` ;
- ajouter `answers`, `answer_citations` et un ledger `index_points` ;
- ajouter takedown/suppression logique ;
- figer les enums de vérification/preuve/risque ;
- interdire explicitement toute connexion de l'experiment-runner à `trading_v1` ou à un courtier ;
- définir un golden transcript avant le benchmark média ;
- propager l'identité/ACL dans MCP ;
- commencer les golden sets et un vertical slice UI plus tôt ;
- ne purger réellement qu'un artefact jetable pendant le canary.

#### P2

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

## Revue v3 — taxonomie, stockage et retrieval

Une nouvelle revue ciblée a été exécutée après clarification de la taxonomie financière et du rôle
de la provenance.

### Première passe

Verdict `NOT READY`. Corrections P0 intégrées :

- identité de point incluant unité, texte exact, modèles dense/sparse et versions
  taxonomie/ontologie ;
- versionnement des alias injectés dans les embeddings ;
- séparation exhaustive payload immuable/projection mutable ;
- cardinalités `entity_kinds[]` et `claim_ids[]` ;
- sécurité obligatoire dans les prefetch Qdrant et le graphe SQL ;
- fusion Qdrant distincte de l'enrichissement graphe.

Corrections P1 intégrées :

- `provenance_class` canonique, `wing` alias compatible dérivé ;
- arborescence Banga par identifiants stables ;
- sentinelle `valid_to`, `is_deleted` et indexes utiles seulement ;
- invariant `room == racine(topic_path)` ;
- `buildValidationFilter()` séparé pour les points staging ;
- matrice `doc_kind/knowledge_kind` ;
- backup Banga 3-2-1-1-0 et golden BM25-only ;
- gate interdisant tout filtre dur implicite de provenance.

### Deuxième passe

Verdict `NOT READY` avec un P0 résiduel et quatre P1. Corrections intégrées :

- `knowledge_item_id`, `artifact_id` et `canonical_id` ajoutés au payload et aux indexes ;
- déduplication des versions par `canonical_id` ;
- partition mutable exhaustive, incluant ACL, claims, risque, tags et projection métier ;
- type SQL `ScopedQuery` et interdiction lint des accès retrieval non scopés ;
- `valid_to` obligatoire et testé avant upsert ;
- test `wing == provenance_class`.

### Passe finale

Claude Opus 5 a rendu le verdict **READY**, sans P0 ni P1.

## Revue v4 — intégration Karakeep

### Passe 1 pré-exécution

Verdict : **NOT READY** — 3 P0 et 10 P1.

P0 :

1. le prompt autonome déclarait encore la v3 autoritaire et ne portait aucun invariant Karakeep ;
2. `external_resources` mélangeait qualification par run et bookmark global, rendant impossible
   la même URL dans plusieurs recherches ;
3. la promotion durable vers Banga était exigée sans route, événement ni tâche.

P1 :

1. statut et sections déploiement/décisions/gates du design restaient v3 ;
2. aucune revue v4 n'était consignée ;
3. clé webhook contradictoire et protections replay/tenant incomplètes ;
4. ordre des webhooks indéductible depuis le payload upstream ;
5. canonicalisation URL sans contrat ni version ;
6. optionalité Karakeep incompatible avec G7/canary et sans feature flag ;
7. G0/G1 n'incluaient pas les nouvelles décisions et le snapshot OpenAPI ;
8. ACL/tenant absents des tables et routes recherche/connecteur ;
9. SSRF non bornée sur base URL, redirects et délégation au crawler Karakeep ;
10. `roles/karakeep/` n'était rattaché à aucune tâche.

Corrections intégrées dans les autorités v4 :

- prompt v4 et invariants non négociables ;
- qualifications `research_candidates` par run, ressource externe globale et table de liaison ;
- route/événement/workflow de promotion Banga avec checksum ;
- snapshot OpenAPI Karakeep v0.32.0 pinné ;
- webhook comme signal d'invalidation, déduplication tenant-aware et relecture API monotone ;
- canonicalisation versionnée et procédure de recalcul ;
- `karakeep_enabled=false` par défaut et gates conditionnels sur fake/instance de test ;
- ACL/tenant et connecteur mono-tenant ;
- allowlist Ansible et SSRF avant outbox sur tous les chemins ;
- tâche de déploiement `roles/karakeep/`, secrets distincts, backup et rollback de rotation.

Sources upstream vérifiées pendant la revue :

- documentation officielle Karakeep des variables d'environnement et de l'API ;
- tag `v0.32.0`, commit `b9b252ecb6d2af379192778ec24f766d4cd60da3` ;
- OpenAPI SHA-256
  `69b85ed2cdbfb0904bd04c83dd3d3d24b44838815ebd2031d0ad89b9cc7f7f24` ;
- licence AGPL-3.0 upstream.

### Passe 2 pré-exécution

Verdict : **NOT READY** — 1 P0 et 7 P1.

Le P0 corrige une hypothèse upstream : le Bearer entrant n'est pas une variable
`WEBHOOK_TOKEN`; il est configuré par webhook dans Karakeep. Les P1 portaient sur l'absence de
`research_runs`, trois formats de tags contradictoires, les uniques incompatibles lors d'un bump
de canonicalisation, un G2 excluant le lecteur nécessaire au fake, la liste exacte des événements,
la provenance des fixtures webhook et l'absence de gate capacité Sese.

Corrections intégrées :

- Bearer généré par Prisme, au coffre puis enregistré/vérifié dans `/settings/webhooks` ;
- `research_runs` et ses FK/ACL ;
- tags `role:<research_run_id>:<role>` et `status:<research_run_id>:<status>` ;
- canonicalisation mise à jour en place avec fusion transactionnelle des collisions ;
- relais outbox/reconciler autorisés contre fake à G2 ;
- événements `created|crawled|edited|deleted`, `ai tagged` désactivé ;
- fixture webhook dérivée des deux fichiers source pinnés et hashés ;
- pré-check Sese bloquant et limites mémoire par conteneur.

### Passe 3 pré-exécution

Verdict : **NOT READY** — 1 P0 et 3 P1.

Le P0 constatait que P0/P1 v3 existaient déjà alors que la v4 décrivait seulement une création
neuve, permettant de contourner le G1 élargi. Les P1 portaient sur la migration des candidats lors
d'un bump de canonicalisation, l'absence de `research-run.v1` et un validateur `relative_path`
limité à `library/`.

Corrections intégrées :

- sémantique explicite de reprise depuis `3cee720`, G0/G1 rouverts et P2 interdit avant nouveau
  G1 v4 `READY` ;
- contrat `research-run.v1`, portant le total à 19 contrats ;
- migration transactionnelle des candidats avec fusion auditée ou revue bloquante si les
  qualifications divergent ;
- la passe 3 avait temporairement rendu indexables `library`, `research`, `experiments` et
  `exports`; la passe 4 corrige ensuite ce point : seuls les trois premiers le sont, tandis que
  `incoming`, `exports` et `quarantine` ne produisent aucun point.

### Passe 4 pré-exécution

Verdict : **NOT READY** — 0 P0, 4 P1 et 8 P2.

Les P1 portaient sur une Definition of Done exigeant le déploiement Karakeep malgré son flag
désactivé et le gate capacité rouge, une tâche de revue créée dans une transaction ensuite
rollbackée, l'absence de tests nommés pour la migration de canonicalisation et des enums
rôle/décision/statut incomplets.

Corrections intégrées :

- le déploiement réel Karakeep est conditionnel au flag et à son gate de capacité propre ; fake
  et branche désactivée restent exécutables ;
- la détection des collisions est un dry-run, les tâches divergentes sont committées séparément,
  puis la mutation atomique ne s'exécute qu'après résolution ;
- G2 nomme les tests dry-run, fusion identique, divergence persistée et crash/rollback ;
- enums fermés et tags `role`, `status`, `decision` sont explicités ;
- G1 avait d'abord distingué les contrats internes des cinq contrats d'intégration ; la passe 5
  précise ensuite que seules deux projections wire sont comparées aux sources upstream ;
- création repo/remote rendue conditionnelle, `research_sources` retirée et `exports/` déclarée
  physique non indexable ;
- port `BookmarkSink.applyProjection()` ajouté et `canonical_url` externe explicitement hors
  Qdrant ;
- aucun fallback de revue vers un modèle plus faible ; seul un défaut réel d'accès/quota bloque.

### Passe 5 pré-exécution

Verdict : **NOT READY** — 1 P0, 4 P1 et 8 P2.

Le P0 a révélé que le NO-GO offsite global Banga rendait P4 et la DoD inatteignables. Les P1
portaient sur les cinq contrats d'intégration non nommés au gate, le rôle nullable sans règle de
tag, l'absence de génération cross-repo du registre Qdrant et l'absence de gate capacité pour
Prisme lui-même.

Corrections intégrées :

- P4 dépend du pool/provisioning ZFS vert, puis `tank/knowledge` reçoit une politique offsite et
  un restore drill Prisme propres avant G10, sans déclarer le chantier global Banga résolu ;
- les six ajouts v4 sont nommés et seules les projections wire pertinentes sont comparées aux
  sources Karakeep ;
- `role=null` est testé et n'émet aucun tag `role:*` ;
- snapshot du registre Qdrant généré depuis VPAI, vendored/hashé dans Prisme et vérifié par les
  deux CI ;
- gate capacité Prisme distinct ajouté avant son déploiement réel ;
- les P2 ont aussi été fermés : secrets conditionnels, Mean Reversion dans les goldens,
  homonymie `canonical_url`, historique `exports`, type de tâche de collision, endpoint Qdrant,
  revues Opus dans les sessions et verrou d'écriture pendant un bump.

### Passe 6 pré-exécution

Verdict : **NOT READY** — 0 P0, 3 P1 et 6 P2.

Corrections intégrées :

- tâche de remédiation capacité Sese réversible ajoutée ; si elle ne suffit pas, placement,
  dépense ou interruption étrangère redevient une décision G0 explicite ;
- périmètre étendu à Seko-VPN et split-DNS Headscale requis pour Prisme/Karakeep, sans A public ;
- golden T1.5 amorcé depuis des clips librement licenciés avec transcripts humains publiés,
  licences et hashes, jamais depuis une pseudo-référence modèle ;
- emplacements du snapshot/générateur Qdrant ajoutés aux arbres et listes de fichiers ;
- contraintes de collision différées, sentinelle UUID nullable, exception `role=null`, quota
  mesuré avec `disk-guard`, et revalidation du quota Opus avant chaque gate maintenus.

### Passe 7 pré-exécution

Verdict : **NOT READY** — 0 P0, 6 P1 et 7 P2.

Corrections intégrées :

- identité UUIDv5 normalisée avec séparateur unique `\x1f` et sentinelle nullable ;
- manifests golden seuls dans Git ; médias licenciés réhydratés par hash dans le spool Waza puis
  dans Banga après P4 ;
- uniques immédiats compatibles `ON CONFLICT`; bump via table temporaire, lock, fusion/suppression
  des perdants puis mise à jour des survivants ;
- drill et commande de rebuild Qdrant depuis PostgreSQL+Banga ajoutés à G10 ;
- préflight quota Prisme read-only et scoppé remplace toute dépendance au `disk-guard` global ;
- gate capacité fondé sur réserve RAM, PSI et swap I/O, jamais sur l'ajout de swap ;
- P2 fermés : split-DNS dans le design, sémantique alias G3, script de vérification registre,
  smoke accès/quota Opus, webhook récepteur auth, baseline lag en P9 et canary retiré de G0.

### Passe 8 pré-exécution

Verdict : **NOT READY** — 1 P0, 3 P1 et 7 P2.

Corrections intégrées :

- préflight capacité du Qdrant partagé ajouté avant G3 ; le rebuild G10 utilise une instance
  Qdrant éphémère isolée avec teardown strictement labellisé test-only ;
- G3 compare schémas/config/alias et le journal des mutations Prisme, pas le compteur vivant des
  collections étrangères ;
- gate Karakeep aligné sur réserve RAM, PSI et swap I/O, non contournable par ajout de swap ;
- bump de canonicalisation en double passe via hashes sentinelles uniques, avec test de
  permutation injective ;
- P2-1 golden réhydraté sous un vrai `incoming/<ingestion_id>` ;
- P2-2 aucun spool Waza pré-P4 ;
- P2-3 test UUID/sentinelle cross-runtime nommé ;
- P2-4 contrat PostgreSQL VPAI respecté ;
- P2-5 politique `prisme_test_*` générée ;
- P2-6 branche canary non autorisé explicite ;
- P2-7 endpoint Karakeep qualifié et périmètre des workers Python explicité.

### Passe 9 pré-exécution

Verdict : **NOT READY** — 0 P0, 3 P1 et 7 P2.

Corrections intégrées :

- double passe sentinelle étendue explicitement à `research_candidates` et
  `external_resources`, tests de permutation sur les deux tables ;
- sidecar `sparse-query-only` rattaché au compose `roles/prisme/`, limité à `1 GiB` et inclus au
  pré-check avec web/API et outbox ;
- tâche T2.5 propriétaire du rôle principal ajoutée, avec build, pin, Caddy, backup, dashboards,
  tests locaux/fake et déploiement Sese différé ;
- P2 fermés : hôte Banga du rebuild, sémantique des deux prompts, invariant Qdrant remis en forme,
  slug topic dérivé du registre, G8 ordonné après G7, et création G3 autorisée par le prompt sans
  gate humain supplémentaire.

### Passe 10 pré-exécution

Verdict : **NOT READY** — 0 P0, 2 P1 et 8 P2.

Corrections intégrées :

- double passe sentinelle alignée dans le design pour `external_resources` ;
- top-k final obligatoirement revalidé dans PostgreSQL par `applySecurityScope()` avant
  rescoring, citation ou retour ; G9 teste révocation ACL/takedown pendant lag Qdrant ;
- P2 fermés : sémantique prompts alignée, dépendances P4→P5/P6, bootstrap T11 idempotent, Bearer
  lié au connecteur, `.planning/EXECUTION.md` dans l'arbre, checklist rôle Ansible, index
  `canonical_url` documentaire et historique passe 4 clarifié.

### Passe 11 pré-exécution

Verdict : **NOT READY** — 0 P0, 4 P1 et 6 P2.

Corrections intégrées :

- revalidation top-k portée dans le prompt, le design et T9.1, sur-récupération bornée
  `min(3*k, 200)` ;
- relecture des answers/citations re-scoppée ; citations retirées masquées et answer
  `stale_redacted`, avec test G9 ;
- fusion canonicalisation repointe les liaisons candidates, conserve les sync attempts append-only
  via merge-map/tombstone et interdit la suppression physique, avec test ;
- clé virtuelle LiteLLM Prisme et budget quotidien sous le cap global `$5/day`, métriques et
  arrêt préventif ajoutés à G0/T2.5/G10/G11 ;
- P2 fermés : advisory lock design, sentinelles protégées par CHECK, gate qualité lag,
  `idempotency_records` avec TTL, et fail-closed `503` si PostgreSQL est indisponible.

### Passe 12 pré-exécution

Verdict : **NOT READY** — 0 P0, 5 P1 et 8 P2.

Corrections intégrées :

- fusion externe sans DELETE, uniques partielles sur ressources actives, liaisons candidates
  uniques, merge-map/tombstone et reconciler anti-résurrection ;
- G2 exige explicitement CHECK sentinelle, repointage, merge-map, immutabilité/résolution des sync
  attempts et anti-résurrection ;
- clé virtuelle provisionnée par `roles/prisme/tasks/litellm-key.yml` via API admin, secret
  chiffré contrôlé REX-62, sans modifier le rôle LiteLLM partagé ;
- table `webhook_delivery_receipts` tenant/ACL dédiée à la fenêtre 30 jours ;
- split-DNS protégé par rendu/diff complet, smoke de tous les anciens noms et rollback Headscale ;
- P2 fermés : prompt top-k strict, G0 LiteLLM, `securityAsOf=now()`, enum answer visibility,
  unicité/qualité merge et routes test/reconcile scoppées par connecteur.

### Passe 13 pré-exécution

Verdict : **NOT READY** — 0 P0, 4 P1 et 9 P2.

Corrections intégrées :

- ordre versionné sans fenêtre vide : nouveau Qdrant actif, nouvelle version PostgreSQL active,
  coexistence dédupliquée, puis ancienne version superseded/expirée ;
- uniques `external_id`/URL partielles sur ressources actives alignées ; liaisons déjà
  dupliquées tombstonées par `merged_into_link_id` sans perte ;
- T7.0 interdit l'apply vpn-dns direct et dépend du protocole sécurisé T10.5 ;
- P2 fermés : endpoints LiteLLM generate/info/delete et rollback, deux CIDR Caddy + webhook
  Docker interne, chaînes de merge bornées/anti-cycle, tests Qdrant interdits en prod, build OCI
  amd64 borné, colonne answer visibility, receipts testés G2 et index `wing` supprimé.

### Passe 14 pré-exécution

Verdict : **NOT READY** — 0 P0, 3 P1 et 7 P2.

Corrections intégrées :

- bootstrap clé LiteLLM one-shot sur contrôleur persistant puis secret vaulté commité ; CI
  fail-loud et vérification `/key/info`, jamais de génération en checkout éphémère ;
- budget Prisme reformulé comme allocation du cap partagé `$5/day`, avec répartition G0 et
  relèvement global seulement sur décision explicite ;
- T6.4 suit l'ordre sans fenêtre vide et teste le crash Qdrant-actif/PG-inactif ;
- P2 fermés : contrôle croisé registre VPAI/Prisme, GHCR/amd64 en G0, topic_path du run,
  événements outbox Qdrant, prédicat `ON CONFLICT`, ordre UI G2 et re-smoke split-DNS G10.

### Passe 15 pré-exécution

Verdict : **NOT READY** — 0 P0, 3 P1 et 6 P2.

Corrections intégrées :

- aucun secret dans URL : lookup LiteLLM par alias sous master header ; vault Prisme séparé,
  bootstrap one-shot et staging/commit par chemin ;
- compose/pré-check exhaustif : web+MCP, outbox, research, navigateur isolé, connecteur, indexer,
  consolidation et sparse, tous bornés avec rollback individuel ;
- P2 fermés : unique external_id simple, réseau Docker externe interne partagé, consolidation
  rattachée, playbook Waza scoppé par tag, checklist/Molecule fetcher+Karakeep, SvelteKit 2/Svelte
  5 et build GitHub Actions x86_64.

### Passe 16 pré-exécution

Verdict : **NOT READY** — 1 P0, 3 P1 et 6 P2.

Corrections intégrées :

- fichiers VPAI partagés sales gérés par patch d'index/hunks Prisme uniquement, avec preuve que le
  diff étranger reste intact ; seul un chevauchement de lignes réel bloque ;
- merge/tombstone symétrique ajouté pour `research_candidates`, avec repointage et links
  redondants tombstonés ;
- Karakeep réel reporté après T11.2 ; G7 reste sur fake, réseau/service Prisme garantis avant
  activation ;
- production/DoD conditionnée au gate capacité Prisme ; statut explicite
  `AWAITING_G0_CAPACITY_DECISION` si les remédiations réversibles ne suffisent pas ;
- P2 fermés : ref registre inverse, GHCR pull, service/port normatifs, prédicat partiel des links,
  digest embedding cross-repo et chemin Banga absolu.

### Passe 17 pré-exécution

Verdict : **NOT READY** — 1 P0, 1 P1 et 6 P2.

Corrections intégrées :

- commit des fichiers partagés sales strictement depuis l'index sans pathspec, avec preuve
  post-commit que le patch étranger reste intact ;
- registre cross-repo fondé sur hash YAML normalisé hors refs, danse deux commits sans
  auto-référence ;
- P2 fermés : merge candidates récursif/anti-cycle et CHECK symétrique, activation Karakeep
  ordonnée en T11.2, setup webhook Playwright autonome, GET answers sans écriture et contrat
  `index_generation` pour réencodage sans version métier.

### Passe 18 pré-exécution

Verdict : **NOT READY** — 0 P0, 4 P1 et 7 P2.

Corrections intégrées :

- API de lecture Banga mesh-only mTLS/service-token, IDs stables, Range et proxy Prisme scoppé ;
- rebuild alimenté par export ledger signé/chiffré/TTL de Sese vers Banga, sans ouvrir PostgreSQL ;
- `index_generation` ajouté au payload, index, point ID et dédup génération active maximale ;
- registre normalisé par RFC 8785/JCS via le même script et fixtures dans les deux CI ;
- P2 fermés : DNS reporté T11.2, rollback Playwright, bookmark doublon non recréé, formule capacité
  déterministe, URL webhook absolue, ansible-lint et tag `prisme-fetcher` conforme.

### Passe 19 pré-exécution

Verdict : **NOT READY** — 0 P0, 3 P1 et 6 P2.

Corrections intégrées :

- accès DB Prisme isolé via proxy IP fixe et règles HBA allow/reject user/db, reload sans restart,
  rollback et smokes partagés ;
- `index_generation` classé immuable, index minimal, point ID et dédup normative T9/G9 ;
- P2 fermés : statuts index explicites, export ledger SFTP restreint et chiffré, DNS sans clause
  morte, canonicalizer partagé byte-for-byte, rollback alias ops-only, réseau connector créé et
  indexer déclaré unique écrivain Qdrant.

### Passe 20 pré-exécution

Verdict : **NOT READY** — 1 P0, 3 P1 et 6 P2.

Corrections intégrées :

- split-DNS Prisme appliqué inconditionnellement en T11.2 ; Karakeep reste conditionnel ;
- HBA partagé utilise un handler reload dédié sans restart, proxy DB intégré au compose/limites,
  tests locaux G2 et smokes production T11 ;
- backup/restore drill PostgreSQL Prisme ajouté à G10 ;
- P2 fermés : `index_generation` dans le bloc immuable + test/prompt, transport Karakeep sortant
  interne, non-régression HBA, et traçabilité revue complétée.

### Passe 21 pré-exécution

Verdict : **NOT READY** — 2 P0, 3 P1 et 6 P2.

Corrections intégrées :

- HBA durci par destination DB pour tous les rôles : allow proxy `/32`, reject subnet backend,
  y compris superuser `postgres`, puis reload vérifié sans restart ;
- gate T4.0 ajouté : inventaire LXC/Docker/GPU/passthrough/capacité et décision G0 obligatoire
  avant toute création de LXC ou extension GPU ;
- `tank/knowledge` rejoint le `zfs_datasets` autoritaire Banga et donc `disk-guard`; le rôle
  knowledge-store vérifie/fail-fast sans création parallèle, avec seuils numériques quota ;
- provisioning DB/user live idempotent, service Prisme joint au réseau Caddy
  `javisi_frontend` ;
- P2 fermés : credential GHCR Banga, capacité du restore PostgreSQL, Node 22 en CI VPAI,
  handler REX-59, et smoke exhaustif des records split-DNS Waza.

### Passe 22 pré-exécution

Verdict : **NOT READY** — 1 P0, 7 P1 et 8 P2.

Corrections intégrées :

- ACL proxy DB rendue normative et testée depuis un conteneur `javisi_backend`, localement puis
  sur Sese ; le proxy n'accepte que `prisme_internal` ;
- orchestration Sese corrigée vers `playbooks/stacks/site.yml`; handler reload tolérant une
  installation fraîche, assert déplacé au contrôle Prisme ;
- statuts `AWAITING_OFFSITE_DESTINATION` et blocker credential cross-repo définis ;
- CI cross-repo privée fondée sur PAT read-only nommé, Qdrant/LiteLLM joints par réseau backend
  interne et smokes depuis le conteneur ;
- verdict courant unique en tête du journal et protocole `review-file.sh`/`notify-gate.sh` ajouté
  pour tout gate humain ;
- P2 fermés : collision multi-wing, graphe P4→P5→P6, tags de phase, nom vault GHCR,
  bibliothèque/fixtures YAML, fallback golden manuel CC0, workflows CI listés et mesure capacité
  Sese déplacée en G0.

### Passe 23 pré-exécution

Verdict : **NOT READY** — 0 P0, 3 P1 et 8 P2.

Corrections intégrées :

- egress explicitement limité à research/browser et aux crawlers Karakeep ; tous les autres
  services en sont exclus et le web Karakeep rejoint `javisi_frontend` ;
- réconciliation préalable live/template split-DNS, incluant `chat`, `wizy` et `hook`, avant les
  ajouts Prisme/Karakeep ;
- préflight Banga déplacé en G0 et statut distinct `AWAITING_G0_BANGA_PLACEMENT`, avec périmètre
  atteignable P0–P3/P8 fixtures explicite ;
- P2 fermés : remplacement du handler restart, test API LiteLLM réel avec pagination fallback,
  naissance du registre à T3.1, position du rôle dans `site.yml`, journal v3 superseded et commit
  checkpoint, sidecar sparse local P9 et enum rôle réellement nullable.

### Passe 24 pré-exécution

Verdict : **NOT READY** — 0 P0, 4 P1 et 10 P2.

Corrections intégrées :

- `prisme_enabled=false` garde le rôle entier dans `site.yml`; le précheck n'est bloquant que sous
  activation explicite après capacité verte ;
- interdiction `trading_v1` précisée : métadonnées de collection seulement, jamais
  points/vecteurs/payloads/retrieval ni mutation ;
- Molecule limité à configuration/idempotence ; health, HBA et ACL proxy passent dans un harnais
  compose x86_64 réel ;
- golden synthétique sans dépendance humaine : script source autoritaire, génération audio
  déterministe et hashes ;
- P2 fermés : réseau connector, G0/ADR exhaustif, ordre checkpoint v3, portée réseau HBA,
  préprod x86_64, réservations mémoire, existence tag Karakeep, `wing` local, hashes du worktree
  sale et tag fetcher exclusif.

### Passe 25 pré-exécution

Verdict : **NOT READY** — 0 P0, 4 P1 et 8 P2.

Corrections intégrées :

- signature complète `notify-gate.sh` avec titre/contexte ;
- rollout `site.yml --skip-tags vpn-dns`, puis protocole dédié avec facts Waza et assert
  live⊆rendu avant toute écriture ;
- fetcher gardé par `prisme_fetcher_enabled=false` et tag exclusif ;
- IP backend Prisme fixe rejetée par HBA vers toutes les DB ; seul le proxy atteint DB Prisme,
  avec tests et menace de mouvement latéral ;
- P2 fermés : manifeste exhaustif du worktree sale, prérequis PostgreSQL ciblé, overcommit borné
  accepté en ADR, pin TTS, flags globaux default-false, noms Docker Jinja, runbooks nommés et
  Session 1 v4 corrigée.

### Passe 26 pré-exécution

Verdict : **NOT READY** — 0 P0, 4 P1 et 9 P2.

Corrections intégrées :

- dataset Banga déclaré pool-relatif `name: knowledge` avec les cinq clés attendues, jamais
  `tank/knowledge` dans `zfs_datasets` ;
- IP proxy/service `.240/.241` sorties de l'iprange dynamique, HBA entièrement conditionnel à
  `prisme_enabled` et rendu false byte-identique ;
- assert DNS placé précisément dans `roles/vpn-dns/tasks/main.yml` avant write, fichier ajouté au
  périmètre ;
- fallback golden devenu vidéo déterministe avec plans/texte/audio et manifests OCR
  chaînes+bboxes+timestamps ;
- P2 fermés : HAProxy L4 pinné, vault example Banga, variables mémoire docker.yml, usage guard,
  G11 défini, G9 x86_64, routes ingestion/claim P2, G8 non évalué sous blocage Banga et deux
  handlers Ansible avec listener partagé.

### Passe 27 pré-exécution

Verdict : **NOT READY** — 1 P0, 3 P1 et 7 P2.

Corrections intégrées :

- toute mutation IPAM supprimée ; IP `.240/.241` soumises à inspect collision read-only, tout
  changement de réseau devient G0/fenêtre maintenance ;
- HBA refuse proxy→toute DB après l'allow DB Prisme, avec test proxy→n8n refusé ;
- `site.yml` ne joue vpn-dns que si facts Waza disponibles ; l'utility playbook reste seul chemin
  d'apply ;
- offsite intégré exclusivement au hub zerobyte v3 PULL SSH et à ses gates humains, sans bucket
  ni credential parallèle ;
- P2 fermés : historique v1 imbriqué, HAProxy SNAT explicite, ratio Sese baseline G0, runner/recipe
  golden, guard Caddy byte-identique, aucun changement postgresql.conf et statut
  `AWAITING_OPUS_QUOTA`.

### Passe 28 pré-exécution

Interrompue avant restitution du verdict lors de la reprise de conversation ; aucun verdict
technique enregistré.

### Passe 29 pré-exécution — finale bornée

Verdict : **READY** — 0 P0, 0 P1 et 5 P2 non bloquants.

Les fermetures des passes 21–27, les invariants payload (58 champs), les 19 contrats, l'identité
UUIDv5 et les contraintes PostgreSQL/Qdrant ont été revérifiés. P2 conservés pour exécution :

- noter dans le runbook le risque résiduel d'allocation dynamique `.240/.241` et garder le
  préflight collision obligatoire ;
- `vault_ghcr_pull_token` Banga absent attendu au préflight G0 ;
- documenter comme précondition qu'aucune modification étrangère de `postgresql.conf` ne partage
  le run HBA sans-restart ;
- matérialiser le quota ZFS mesuré en expression d'octets conforme aux entrées Banga ;
- verdict courant mis à jour ici avant toute reprise d'implémentation.
