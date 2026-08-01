# Audit — Prisme, état fonctionnel réel (2026-08-01)

> Contexte : audit demandé juste après le déploiement du plan de contrôle sur Sese.
> Méthode : sondes runtime sur la prod + lecture du code de l'image déployée
> (`prisme@sha256:5f11f097…`) et du repo `~/work/saas/prisme`.

## 1. Verdict

L'**infrastructure** est complète et saine. Le **produit** ne l'est pas : le chemin de lecture
(recherche / Ask), qui est la promesse centrale, est cassé en prod et, même réparé, ne fait pas
de recherche réelle. Prisme est un squelette de production correct autour d'un moteur qui n'est
pas branché.

## 2. Ce qui fonctionne (vérifié)

| Élément | Preuve |
|---|---|
| 9 conteneurs + migrate | `docker compose ps`, 0 restart |
| `/health/live`, `/health/ready` | 200, `databaseReady:true` |
| `/metrics` + Bearer | 200 |
| Vhost VPN-only + TLS LE | `https://prisme.ewutelo.cloud` 200 |
| Auth opérateur | `POST /api/v1/auth/session` → 200 + cookie |
| `GET /api/v1/library`, `/connectors` | 200, `{"items":[]}` |
| Pages UI | `/`, `/ask`, `/library`, `/review`, `/settings/connectors`, `/ingestions/new` → 200 |
| Clé LiteLLM isolée | `prisme-production`, cap 0,50 USD/j |
| Schéma PostgreSQL + migrations | migrate exited 0 |

## 3. Défauts bloquants (preuves)

### D1 — `GET /api/v1/search` et `POST /api/v1/ask` → HTTP 500, systématiquement

```
ZodError: subjectId — Invalid UUID
  at planRetrieval (…/_server.ts.js:420)
```

`src/routes/api/v1/auth/session/+server.ts` signe toute session avec
`userId: '00000000-0000-0000-0000-000000000001'`. `dispatcher.ts:116` ne remplace par l'UUID nil
que si l'`userId` **ne** ressemble pas à un UUID ; or celui-ci matche `/^[a-f0-9-]{36}$/i`, donc il
passe tel quel. Le validateur de `planRetrieval` exige la version `[1-8]` et le variant
`[89abAB]` (ou nil / max exactement). `…0001` échoue les deux.

Conséquence : **le seul chemin de connexion existant produit une identité que le retrieval refuse.**
Aucune recherche, aucune réponse citée n'est possible en prod. Non détecté par les tests : les
goldens injectent un store de fixtures avec un `subjectId` valide.

### D2 — La recherche « hybride » ne calcule aucun score

`src/lib/server/api/production.ts:229` (store de **production**) :

```ts
denseScore: 0.5,
sparseScore: 0.5
```

Constantes. Le classement RRF/DBSF s'applique donc à des scores identiques pour tous les records ;
seuls subsistent les bonus heuristiques (`+0.08` entité exacte, `+0.04` topic_path). Il n'y a ni
embedding, ni BM25, ni requête Qdrant **au moment de la lecture** : le seul appel Qdrant du code
est un `PUT /collections/knowledge_current/points` dans `workers/worker.ts:120` (écriture). Le
sidecar sparse et la collection `knowledge_v1` sont alimentés mais jamais interrogés.

Corollaire : `knowledgeRecords()` charge **toute** la table (`index_points ⋈ knowledge_items ⋈ …`,
sans `LIMIT`) en mémoire Node à chaque requête, puis trie en JS. Tient à 0 document, pas à 10 000.

### D4 — L'index Qdrant n'est ni alimenté ni authentifiable

`knowledge_v1` existe et est `green`, mais **`points_count = 0`** (vérifié via l'API Qdrant).
Et aucun service runtime ne reçoit de clé : `QDRANT_API_KEY` n'apparaît que dans
`qdrant-bootstrap.mjs` (script Ansible), ni dans `prisme.env`, ni dans le `docker-compose.yml`,
alors que l'instance rejette tout appel non authentifié
(`Must provide an API key or an Authorization bearer token`).

Donc la boucle d'indexation est cassée aux deux bouts : le worker écrirait en 401 s'il tournait,
et la lecture ne l'interroge pas (D2). Ce n'est pas « un index maintenu sans usage » — c'est un
index jamais écrit et jamais lu.

### D3 — Les métriques métier sont des constantes

`src/lib/server/observability.ts` fixe à l'import :
`prisme_retrieval_ndcg=1`, `prisme_backup_last_success_timestamp_seconds=0`,
`prisme_queue_depth=0`, `prisme_budget_remaining_usd=0.5`, `qdrant_projection_lag_seconds=0`,
`prisme_projection_drift_total=0`. Aucun code ne les met à jour ensuite.

Le dashboard `Prisme — Operations` et `alerting-prisme.yaml` sont donc **verts par construction** :
une alerte sur nDCG, sur le lag de projection ou sur le budget ne peut structurellement jamais
partir. C'est pire qu'une absence de métrique.

## 4. Périmètre non livré (par conception, à ce stade)

| Fonction MVP annoncée | État réel |
|---|---|
| Acquisition Instagram / Reels | absente — le worker Waza (`prisme-fetcher.service`, actif) est un **fixture worker** : copie de fichiers `incoming/`→`outgoing/` avec sha256, aucun réseau |
| Transcription, OCR, segmentation | benchmarks G4 seuls ; aucun média traité en prod |
| Extraction d'affirmations, preuves, expériences | pages de détail `/claims/<uuid>`, `/research/<uuid>`, `/items/<uuid>` répondent 200 ; il n'existe pas de page d'index (`/claims` → 404, comportement SvelteKit normal). Aucune donnée derrière |
| Karakeep (inbox documentaire) | `PRISME_KARAKEEP_ENABLED=false` |
| Offsite `/tank/knowledge` | `AWAITING_OFFSITE_DESTINATION`, backup jamais exécuté |
| API design §7 (preuves, expériences) | dispatcher n'expose que `search`, `ask`, `library`, `ingestions`, `connectors`, `events` |

Base vide : `library` retourne `items: []`, aucun contenu n'a jamais transité.

## 5. Écarts au design annoncé, et pistes

Le design (`docs/superpowers/specs/2026-07-27-…`) promet une recherche hybride dense+sparse sur
Qdrant. Écart mesuré, puis pistes qui relèvent de ma recommandation et non d'un standard cité :

| Capacité | Prisme (grep sur `src`, `packages`, `services`) | Nature |
|---|---|---|
| Recherche vectorielle réelle à la requête | absente (D2/D4) | **écart au design** |
| Evals branchées sur des métriques vivantes | absentes (D3) — goldens hors ligne seulement | **écart au design** (§12 observabilité) |
| Reranker cross-encoder sur le top-k | aucune occurrence `rerank` | piste |
| Enrichissement contextuel du chunk avant embedding | aucune | piste |
| Multi-hop / décomposition de requête | une passe, un `q` | piste |
| Exploitation du graphe de preuves au retrieval (GraphRAG) | aucune | piste — et à mon sens la plus payante : le modèle affirmation/preuve/contradiction est déjà le graphe, c'est l'avantage produit le plus distinctif de Prisme |

À l'inverse, ce que le projet fait mieux que la moyenne et qu'il faut garder : séparation stricte
autorité/index (Qdrant reconstructible, PostgreSQL autorité), versionnement de génération d'index,
ACL + fenêtre temporelle appliquées **avant** fusion, citations revalidées à la lecture, images
pinnées par digest, clé LiteLLM budgétée par service.

## 6. Recommandations, par ordre de valeur

1. **D1** — corriger l'`userId` de session (UUID v4 réel) *et* durcir : `planRetrieval` doit
   renvoyer un 400 explicite, jamais un 500. Un test doit passer par le vrai chemin de session,
   pas par le store de fixtures. C'est un correctif d'une ligne pour un blocage total.
2. **D2 + D4** — refermer la boucle d'index : câbler `QDRANT_API_KEY` dans les services runtime
   (sinon l'indexeur 401), puis brancher la lecture sur `query_points` dense+sparse avec préfiltre
   tenant/ACL/génération côté Qdrant, `LIMIT` côté SQL, fusion sur de vrais scores.
3. **D3** — rendre les métriques vivantes ou les **supprimer**. Une jauge constante à 1 sur nDCG
   est un piège opérationnel.
4. Reranker cross-encoder sur le top-50 (le gain qualité le plus élevé par unité d'effort une fois
   D2 fait ; tient sur le GPU Banga).
5. Décider du plan d'acquisition : soit on implémente l'acquisition réelle, soit on assume le mode
   dépôt manuel et on retire la promesse Instagram du périmètre affiché.
6. Offsite `/tank/knowledge` (zerobyte v3) avant toute ingestion de volume — aujourd'hui le
   contenu canonique n'a aucune copie hors site.

## 7. Point sécurité annexe

`PRISME_EMBEDDING_TOKEN` est rendu **en clair dans `docker-compose.yml`** (bloc `environment:` du
service `sparse-query`) et non via `env_file`. Il apparaît donc dans tout `docker inspect`, tout
`--diff` Ansible et tout `cat` du fichier. Il a été exposé pendant cet audit → rotation
recommandée, et bascule vers `env_file` comme le reste de la stack.

## 8. Limites de cet audit

Sondes runtime + lecture de code, sans exécution de la suite de tests du repo ni ingestion réelle.
Les défauts D1–D3 sont reproduits en prod, pas déduits.
