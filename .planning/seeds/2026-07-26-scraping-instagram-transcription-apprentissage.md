# Plan d'implémentation — Instagram → transcription → extraction d'apprentissages

> **PROMU / SUPERSEDED — 2026-07-27**
> Ce seed reste la trace d'exploration. Les contrats retenus vivent désormais dans :
> - `docs/superpowers/specs/2026-07-27-prisme-knowledge-application-design.md`
> - `.planning/plans/2026-07-27-prisme-knowledge-application-execution.md`
>
> Toute implémentation doit suivre ces deux documents. `trading_v1` est hors périmètre.

> Date : 2026-07-26
> Statut : **v3 — architecture estate + contre-vérification**, exécution réelle bloquée par les gates G1 et G2
> Portée : compte Instagram public autorisé par l'utilisateur, vidéos de posts et Reels uniquement
> Référence d'architecture : `docs/audits/2026-06-10-content-factory-v2-analyse-fonctionnelle-structurelle.md`, § B4 « Scout »

## 1. Résultat attendu

À partir de l'URL d'un profil Instagram :

1. découvrir ses vidéos sans les télécharger ;
2. présenter le volume estimé et permettre un canary limité ;
3. télécharger les vidéos **une par une**, avec délai configurable et reprise après arrêt ;
4. transcrire l'audio et analyser le texte à l'écran ;
5. produire, pour chaque vidéo, un document d'apprentissage structuré, traçable jusqu'aux timestamps ;
6. conserver le bundle JSON/Markdown sur Banga comme source de vérité et indexer une projection
   reconstructible dans Qdrant ;
7. pouvoir relancer le même profil sans doublon ;
8. contre-vérifier les affirmations importantes par des sources externes indépendantes ;
9. proposer des expériences sûres et reproductibles pour les affirmations testables ;
10. consulter la bibliothèque par catalogue, recherche hybride et chat avec citations.

« Apprentissage » signifie ici **extraction de connaissances consultables**, pas entraînement ni
fine-tuning d'un modèle.

## 2. Parcours opérateur concret

### 2.1 Où soumettre un compte

La cible durable est une nouvelle page authentifiée dans **Palais** :

```text
https://palais.<domaine>/knowledge/ingestions/new
```

Formulaire :

| Champ | Exemple | Règle |
|---|---|---|
| URL du profil | `https://instagram.com/example/` | obligatoire |
| Relation au compte | `compte géré` / `public autorisé` | détermine le fetcher |
| Période | tout / depuis une date / entre deux dates | défaut : canary |
| Maximum | `3`, `50`, etc. | jamais illimité au premier run |
| Contenu | posts vidéo, Reels | stories hors MVP |
| Conservation source | supprimer après validation / archiver sur Banga | choix explicite |
| Cadence | prudente / personnalisée | bornée côté serveur |
| Langue attendue | auto / fr / en | aide la transcription |

À la soumission, Palais :

1. crée le job et son audit dans PostgreSQL ;
2. appelle `instagram-scout` sur Waza via une API interne authentifiée ;
3. affiche le manifeste et exige un clic **Approuver** ;
4. présente ensuite la progression par média et les erreurs ;
5. envoie les notifications via n8n/Telegram, sans confier l'état durable à n8n.

Le MVP peut exposer d'abord les mêmes opérations avec `scoutctl`, mais ce CLI est un outil
d'exploitation, **pas l'interface utilisateur finale**.

### 2.2 Deux chemins d'acquisition

| Compte | Fetcher prioritaire | Pourquoi |
|---|---|---|
| Compte professionnel que nous gérons | API Instagram officielle après OAuth | plus stable, autorisée, métadonnées fiables |
| Compte public tiers explicitement autorisé | gallery-dl avec compte dédié | l'API officielle ne donne pas librement tous les médias de comptes tiers |

L'API officielle ne remplace donc pas totalement gallery-dl, mais elle doit toujours passer en
premier lorsqu'elle est applicable. Le champ « relation au compte » interdit de choisir
accidentellement le scraper pour un compte que nous pouvons connecter proprement.

### 2.3 Où retrouver le résultat

Trois vues complémentaires, chacune avec un rôle clair :

1. **Palais `/knowledge`** — catalogue canonique :
   - comptes, vidéos, états, thèmes, concepts, claims, tags ;
   - filtres par compte/date/langue/thème ;
   - transcript synchronisé, enseignements et provenance ;
   - liens vers la vidéo archivée lorsqu'elle existe ;
   - recherche hybride et réponses citées.
2. **Open WebUI — espace “Bibliothèque de connaissances”** :
   - questions en langage naturel ;
   - réponses générées à partir des passages retrouvés ;
   - citations `profil / vidéo / timestamp` ;
   - comparaison et synthèse entre plusieurs vidéos.
3. **Jellyfin** — lecture des sources vidéo archivées sur Banga :
   - utile pour vérifier une citation ou revoir la source ;
   - aucune donnée métier n'est stockée dans Jellyfin.

> État actuel à ne pas masquer : Open WebUI `lxc-chat` est codé mais son déploiement final est encore
> bloqué par le gate réseau Banga documenté le 2026-07-26. Le module `/memory` actuel de Palais
> utilise encore une lignée `palais_memory`/embedding legacy. La bibliothèque vidéo nécessite un
> module `/knowledge` dédié et le contrat hybride actif, pas un simple renommage de page.

## 3. État réel du dépôt et corrections du seed initial

| Sujet | Constat vérifié | Conséquence |
|---|---|---|
| URL vidéo unitaire | MeTube télécharge avec yt-dlp | On conserve MeTube pour les URL unitaires |
| Déclenchement unitaire | `roles/metube/templates/metube.env.j2` appelle directement `POST /api/webhook/metube` | Le workflow n8n `vref-remix-ingest` supposé par le seed n'est pas dans ce chemin |
| Webhook MeTube | `roles/videoref-engine/files/app.py::_background_analyze()` lance `run_analysis()` | Ce webhook exécute l'analyse créative historique, **pas** `/api/intelligence` |
| Transcription | `/api/transcribe` et `_transcribe_audio()` existent avec whisper.cpp `ggml-base` | Réutilisable pour le MVP après durcissement |
| Analyse actuelle | `/api/intelligence` combine transcript, OCR et synthèse LLM | Base de code réutilisable, contrat métier insuffisant |
| Idempotence actuelle | fichiers nommés par filename et point Qdrant basé sur `hash(filename)` | À corriger : le hash Python n'est pas un identifiant persistant stable |
| Concurrence actuelle | le webhook crée une tâche asyncio sans file durable ni verrou | Inadapté à un bulk de longue durée |
| OCR actuel | le paramètre `interval_sec` n'est pas réellement utilisé par `_ocr_frames()` | Bug à corriger avant d'exposer le réglage |
| Collection actuelle | `/api/intelligence` écrit dans `videoref_styles` | Ne pas y mélanger des connaissances ; cette collection est classée métier séparée |
| RAG actif | `memory_v3` combine dense 768d + BM25 + RRF | Réutiliser son moteur et ses tests, pas sa collection opérationnelle |
| Palais | `/memory` existe mais cible une lignée legacy | Créer `/knowledge`, puis mutualiser le client hybride |
| Banga | `tank`, lxc-cloud et Jellyfin sont déployés ; `lxc-chat` reste à finaliser | Banga peut porter archive et batch GPU, pas le catalogue 24/7 |
| Profil yt-dlp | l'extracteur officiel `instagram:user` est marqué `Currently broken` | Ne pas perdre un lot à « tester yt-dlp profil » comme solution principale |

### Décision principale

Utiliser **gallery-dl** comme fetcher Instagram dédié :

- il couvre profils, posts et Reels ;
- il sait enregistrer les IDs téléchargés dans une archive SQLite ;
- il expose des délais distincts entre requêtes, téléchargements et retries ;
- il peut fournir les métadonnées nécessaires à une file durable ;
- il peut déléguer la récupération vidéo à yt-dlp si nécessaire.

Instaloader reste un **fallback de spike**, pas une seconde implémentation au MVP. Il sait parcourir
posts/Reels et reprendre des itérations, mais ajouter deux fetchers dès le départ doublerait les cas
d'authentification, de métadonnées et de reprise.

## 4. Architecture retenue

```text
Palais /knowledge (Sese, catalogue + formulaire + recherche)
    │  submit / approve / status / stop / retry
    ▼
instagram-scout (Waza, 1 worker, SQLite durable)
    ├── API Instagram officielle OU gallery-dl
    ├── cookies.txt monté read-only
    ├── délai + jitter + circuit breaker
    └── spool HOT /opt/workstation/data/instagram-scout/hot/<job_id>/
                              │
             transfert source │ et artefacts atomiques
                              ▼
Banga /tank/knowledge
    ├── source vidéo optionnelle, archive durable
    ├── batch GPU : whisper.cpp + OCR/VLM + consolidation
    ├── experiment-runner isolé + quant-lab sans accès courtier
    ├── JSON/Markdown dérivés = source documentaire
    └── Jellyfin lit seulement les MP4 archivés
                              │
                              │ documents/chunks + métadonnées
                              ▼
Sese
    ├── PostgreSQL Palais = catalogue et état global
    ├── Qdrant `knowledge_v1` = dense + BM25 + RRF
    ├── research-worker = sources externes + dossiers de preuve
    ├── API Knowledge = recherche + réponses citées
    └── Open WebUI appelle l'API Knowledge
```

### Placement par machine

| Nœud | Responsabilité | Ce qu'il ne doit pas devenir |
|---|---|---|
| **Waza** | soumission technique, découverte, téléchargement séquentiel, spool chaud, fallback VideoRef | archive longue durée ou moteur de recherche |
| **Banga** | ZFS, archive des sources, transcription/OCR GPU, expériences isolées, consolidation batch, lecture Jellyfin | source unique sans backup, ni service catalogue indispensable 24/7 |
| **Sese** | Palais/PostgreSQL, Qdrant, recherche externe, API Knowledge, LiteLLM, notifications n8n | stockage de MP4 volumineux |

La première version peut encore analyser un canary avec VideoRef sur Waza. Avant le bulk, un benchmark
de 10 vidéos compare :

- whisper.cpp `ggml-base` CPU Waza ;
- whisper.cpp GPU Banga avec un modèle plus qualitatif ;
- OCR/VLM actuel via LiteLLM ;
- GLM-OCR Banga lorsqu'il est déployé durablement ;
- analyse vidéo native Gemini en challenger, pas en dépendance par défaut.

Le meilleur couple qualité/coût/latence devient le profil de production. L'architecture ne doit pas
figer prématurément Waza comme moteur d'analyse alors que la RTX 3060 Banga est disponible.

### Pourquoi pas n8n pour la boucle

Un lot espacé de 15 minutes à plusieurs heures peut durer des jours. Des nœuds Wait n8n
conserveraient un état d'exécution long, compliqueraient l'arrêt/reprise et coupleraient la sécurité
anti-ban à une interface d'orchestration. Le worker local possède l'état ; n8n pourra plus tard
déclencher un job court ou notifier, sans être la source de vérité.

### Pourquoi ne pas passer le bulk par MeTube

MeTube reste utile pour une URL connue, mais n'apporte ni découverte fiable de profil, ni manifeste
avant exécution, ni état métier détaillé par vidéo. Le bulk écrit dans le même volume partagé, puis
appelle explicitement le nouvel endpoint d'apprentissage. Il ne déclenche donc pas accidentellement
le webhook créatif MeTube.

## 5. Cycle de vie et arborescence des données

### 5.1 Stockage chaud sur Waza

```text
/opt/workstation/data/instagram-scout/
├── state/
│   └── instagram-scout.sqlite3
├── manifests/
│   └── <job_id>.json
├── hot/
│   └── <job_id>/
│       └── <source_id>/
│           ├── source.mp4.part
│           ├── source.mp4
│           └── metadata.json
├── failed/
└── logs/
```

Règles :

- `.part` jusqu'à téléchargement complet, puis rename atomique ;
- un média réussi quitte Waza dès que sa destination finale est vérifiée ;
- un média échoué reste 14 jours par défaut pour diagnostic ;
- aucun TTL ne supprime un média encore lié à un job actif ;
- seuil d'espace disque : pause avant saturation, jamais purge improvisée.

### 5.2 Dataset Banga

Créer un dataset ZFS distinct, proposé initialement à **2 TiB sans réservation**, à confirmer après
mesure :

```text
tank/knowledge
```

Ne pas déposer ces données dans les répertoires internes d'Immich ou Seafile. Ces applications
possèdent leur propre format de stockage et leur propre base. `tank/media` reste une bibliothèque de
lecture ; `tank/knowledge` est la source de vérité de ce pipeline.

Arborescence :

```text
/tank/knowledge/
├── incoming/
│   └── <job_id>/                         # transfert en cours, jamais indexé
├── library/
│   └── instagram/
│       └── <profile_id>--<username>/
│           └── <YYYY>/
│               └── <MM>/
│                   └── <shortcode>--<media_index>/
│                       ├── manifest.json
│                       ├── source/
│                       │   ├── original.mp4       # absent si politique derived-only
│                       │   ├── metadata.json
│                       │   └── poster.jpg
│                       ├── derived/
│                       │   ├── transcript.json
│                       │   ├── transcript.vtt
│                       │   ├── ocr.json
│                       │   ├── learning.v1.json
│                       │   ├── verification.v1.json
│                       │   ├── knowledge.md
│                       │   └── chunks.jsonl
│                       └── integrity/
│                           └── sha256sums.txt
├── corpus/
│   └── instagram/
│       └── <profile_id>--<username>/
│           ├── topics/
│           ├── lessons/
│           ├── contradictions/
│           └── corpus-summary.json
├── research/
│   ├── sources/                            # métadonnées et captures autorisées
│   └── reports/                            # dossiers de vérification versionnés
├── experiments/
│   └── <experiment_id>/                   # protocole, code, données permises, résultats
├── exports/                              # exports utilisateur, temporaires
└── quarantine/                           # bundle invalide/incomplet
```

Principes :

- le chemin humain est stable et lisible ;
- l'identité machine reste `source_id`, pas le chemin ;
- un changement de username n'entraîne pas de déplacement obligatoire ;
- `incoming` → `library` uniquement après checksum et validation du bundle ;
- seuls les fichiers sous `library` sont indexables ;
- `quarantine` n'est jamais indexé ;
- Jellyfin monte uniquement `library/**/source` en lecture seule.

### 5.3 Politiques de conservation

| Politique | Waza | Banga | Usage |
|---|---|---|---|
| `derived-only` — défaut tiers | suppression MP4 après validation | JSON/Markdown + poster, sans MP4 | connaissances consultables, stockage minimal |
| `archive-source` | suppression après checksum Banga | MP4 + dérivés | source importante ou fragile |
| `temporary-review` | suppression après 7 jours post-validation | MP4 30 jours puis purge, dérivés conservés | canary/contrôle qualité |
| `legal-hold` | aucune suppression auto avant copie | MP4 + dérivés, purge manuelle seulement | exception explicitement approuvée |

La suppression d'une source est autorisée seulement quand :

1. le bundle dérivé valide existe ;
2. le catalogue PostgreSQL pointe vers ce bundle ;
3. les chunks Qdrant sont présents ;
4. si `archive-source`, le SHA-256 du MP4 Banga correspond ;
5. l'événement de rétention est audité.

### 5.4 Backup

RAIDZ2 et snapshots ZFS ne constituent pas un backup.

- **dérivés + catalogue + manifests** : haute valeur, faible volume → backup Banga + offsite
  Object-Lock dès intégration dans le design 3-2-1-1-0 ;
- **MP4 tiers re-téléchargeables** : Banga seul accepté si la politique le dit explicitement ;
- **MP4 irremplaçables** : offsite sélectif ou conservation de la source externe, sinon le système
  ne doit pas promettre une archive durable ;
- snapshot Qdrant utile pour DR, mais la réindexation depuis `knowledge.md`/`chunks.jsonl` doit rester
  possible : Qdrant est un index dérivé, jamais la seule copie.

## 6. Contrats durables

### 6.1 Identité d'un média

Clé stable :

```text
instagram:<profile_id>:<shortcode>:<media_index>
```

- `profile_id` plutôt que le seul username, car un compte peut être renommé ;
- `shortcode` identifie le post/Reel ;
- `media_index` distingue plusieurs vidéos dans un carrousel.

Le nom de fichier humain n'est jamais utilisé comme clé d'idempotence.

### 6.2 État SQLite du worker

Fichier : `/state/instagram-scout.sqlite3`, mode WAL.

Table `jobs` :

```text
id, profile_url, profile_id, username, mode, status,
request_delay_min_s, request_delay_max_s,
media_delay_min_s, media_delay_max_s,
max_items, discovered_count, created_at, updated_at, last_error
```

Table `items` :

```text
source_id UNIQUE, job_id, shortcode, media_index, canonical_url,
published_at, caption, duration_s, local_path, sha256,
status, attempts, next_attempt_at, banga_bundle_path, analysis_path, qdrant_point_id,
error_code, error_detail, updated_at
```

États autorisés :

```text
discovered → approved → downloading → downloaded → transferring → stored
                                                               → analyzing → analyzed → indexed
           └──────────────────────────────────────────────────────────────→ skipped
           └──────────────────────────────→ failed_retryable → approved
           └──────────────────────────────→ failed_terminal
```

`stored` signifie « bundle promu sous `library/` et checksum validé », même si la politique prévoit
de supprimer ultérieurement le MP4. Chaque transition est transactionnelle. Au démarrage, un item
resté `downloading`, `transferring` ou `analyzing` est remis dans l'état reprenable correspondant.

### 6.3 Document d'apprentissage v1

Le endpoint retourne et persiste :

```json
{
  "schema_version": "learning.v1",
  "source": {
    "platform": "instagram",
    "source_id": "instagram:123:ABC:0",
    "profile_id": "123",
    "username": "example",
    "shortcode": "ABC",
    "canonical_url": "https://www.instagram.com/reel/ABC/",
    "published_at": "ISO-8601",
    "sha256": "..."
  },
  "media": {
    "duration_s": 42.1,
    "language": "fr"
  },
  "transcript": {
    "segments": [
      {"start_s": 0.0, "end_s": 3.2, "text": "..."}
    ],
    "full_text": "..."
  },
  "learning": {
    "title": "...",
    "summary": "...",
    "concepts": ["..."],
    "claims": [
      {
        "claim_id": "uuid-v5",
        "claim": "...",
        "claim_type": "factual|causal|forecast|opinion|anecdote|procedure|recommendation",
        "speaker_evidence": [{"start_s": 12.0, "end_s": 18.0, "quote": "..."}],
        "extraction_confidence": 0.8,
        "verification_status": "pending"
      }
    ],
    "steps": [{"order": 1, "action": "...", "evidence_start_s": 20.0}],
    "examples": ["..."],
    "tools_mentioned": ["..."],
    "prerequisites": ["..."],
    "caveats": ["..."],
    "unknowns": ["..."],
    "actionable_takeaways": ["..."],
    "tags": ["..."]
  },
  "provenance": {
    "transcriber": "whisper.cpp/ggml-base",
    "analysis_model": "...",
    "prompt_version": "learning-v1",
    "created_at": "ISO-8601"
  }
}
```

Règles :

- une affirmation sans preuve temporelle va dans `unknowns` ou reçoit une confiance basse ;
- `extraction_confidence` mesure la fidélité de l'extraction, jamais la véracité de l'affirmation ;
- aucun prompt ne présente le contenu comme factuellement vrai par défaut ;
- le transcript complet reste dans le bundle canonique Banga, pas tronqué silencieusement ;
- l'index Qdrant contient résumé, concepts, étapes, tags et provenance, pas la vidéo brute ;
- l'ID Qdrant est un UUIDv5 déterministe dérivé de `source_id + schema_version`.

### 6.4 Synchronisation Palais ↔ worker

PostgreSQL porte la vue opérateur et SQLite la reprise locale du worker. Pour éviter deux vérités
concurrentes :

- la commande Palais contient une `idempotency_key` et retourne immédiatement un `job_id` ;
- chaque transition SQLite produit un événement numéroté dans une table outbox ;
- le worker pousse ces événements vers Palais avec retry ; Palais ignore un numéro déjà appliqué ;
- Palais ne déduit jamais un succès d'un simple timeout HTTP ;
- un endpoint de réconciliation retourne le snapshot signé du job ;
- après 15 minutes sans heartbeat, Palais affiche `stalled`, pas `failed` ;
- le worker reste capable de finir un item si Palais redémarre.

### 6.5 Document de contre-vérification v1

La vérification est un artefact distinct de `learning.v1`. Elle ne réécrit jamais rétroactivement
ce que l'auteur a dit :

```json
{
  "schema_version": "verification.v1",
  "claim_id": "uuid-v5",
  "claim_snapshot": "...",
  "domain": "finance",
  "risk_level": "high",
  "status": "contested",
  "conclusion": "...",
  "supporting_evidence": [
    {
      "title": "...",
      "publisher": "...",
      "url": "https://...",
      "published_at": "ISO-8601",
      "retrieved_at": "ISO-8601",
      "source_class": "regulator|official_data|primary_research|systematic_review",
      "excerpt_or_fact": "...",
      "content_sha256": "..."
    }
  ],
  "counter_evidence": [],
  "conflicts_of_interest": [],
  "limitations": [],
  "experiment_candidate": true,
  "verification_model": "...",
  "reviewed_by_human": false
}
```

Statuts autorisés :

```text
pending | supported | partially_supported | contested | refuted
insufficient_evidence | not_verifiable | time_sensitive
```

Règles :

- le LLM formule une conclusion argumentée, mais les URLs, dates, extraits et données constituent
  la preuve ;
- une absence de contre-preuve ne vaut jamais validation ;
- deux pages qui recopient la même dépêche ne sont pas deux sources indépendantes ;
- les sources primaires priment : régulateur, texte légal, documentation officielle, données
  publiées, article scientifique primaire ; une revue systématique prime pour l'état de l'art ;
- forum, réseau social, contenu affilié et autre vidéo servent au mieux de piste, jamais de preuve
  suffisante pour un claim à risque élevé ;
- toute conclusion porte une date de validité et peut repasser à `time_sensitive` ;
- finance, santé, droit et sécurité exigent une revue humaine avant le statut `supported`.

## 7. Construction de la bibliothèque de connaissances

### 7.1 Les cinq passes de connaissance

Il ne faut ni croire automatiquement la vidéo, ni la réanalyser à chaque question. Le système
sépare cinq moments :

#### Passe A — analyse par vidéo, une seule fois

Entrées :

- source vidéo ;
- métadonnées Instagram ;
- transcription temporelle ;
- OCR/VLM sur frames sélectionnées.

Sorties :

- concepts ;
- claims avec preuves temporelles ;
- procédures et étapes ;
- exemples, outils, prérequis et limites ;
- `knowledge.md` lisible ;
- chunks citables.

La source brute n'est relue que si :

- le premier résultat est incomplet ou sous le seuil de confiance ;
- le modèle/prompt change et une migration est approuvée ;
- un opérateur demande explicitement une analyse plus profonde.

#### Passe B — contre-vérification des claims

Le `research-worker` sur Sese traite en priorité les affirmations :

- factuelles, causales ou chiffrées ;
- présentant une recommandation, un rendement ou un risque ;
- nouvelles, contestées ou incompatibles avec le corpus ;
- classées à risque élevé.

Pour chaque claim, il :

1. le reformule en question falsifiable sans changer son sens ;
2. cherche d'abord les sources primaires adaptées au domaine ;
3. recherche explicitement des preuves favorables **et** défavorables ;
4. vérifie identité, date, périmètre, méthode et conflits d'intérêts ;
5. compare populations, période, marché et hypothèses ;
6. produit `verification.v1` avec statut et limites ;
7. envoie les cas sensibles ou ambigus en revue humaine.

La recherche web doit passer par un fournisseur/API déclaré, journalisé et soumis à une allowlist
de domaines pour les catégories à risque. Le modèle n'invente jamais une citation et un lien
inaccessible n'est pas compté comme preuve.

#### Passe C — validation pratique lorsque c'est testable

Un claim `experiment_candidate=true` peut produire un `experiment.v1` :

```text
hypothèse, variables, données, protocole gelé, baseline,
métriques et seuil de succès, risques, coût maximal,
environnement isolé, résultats bruts, conclusion, reproductibilité
```

L'expérience progresse par gates :

```text
proposed → reviewed → sandbox → reproduced → accepted|rejected|inconclusive
```

Les tests sont isolés, plafonnés en ressources et réversibles. Ils ne modifient jamais la
production, ne contactent pas de tiers et ne dépensent pas d'argent sans nouvelle approbation.

Pour une stratégie de trading :

1. traduire le discours en règles calculables, sans paramètre implicite ;
2. geler le protocole avant de regarder le résultat ;
3. séparer apprentissage, validation et test hors échantillon ;
4. éliminer autant que possible biais d'anticipation et de survivance ;
5. inclure spread, commissions, slippage, financement et liquidité ;
6. comparer à une baseline simple et cohérente avec le risque ;
7. mesurer rendement net, volatilité, drawdown maximal, exposition et stabilité par régime ;
8. tester sensibilité des paramètres et périodes, pas seulement le meilleur backtest ;
9. passer ensuite en **paper trading/shadow mode** avec données arrivant réellement ;
10. conclure `inconclusive` si la puissance ou la durée sont insuffisantes.

Le passage à de l'argent réel, même faible, est hors pipeline : il exige une décision humaine
séparée, un budget de risque, des limites de perte, un kill switch et une vérification réglementaire.

#### Passe D — consolidation du corpus

Après un canary puis par lot, cette analyse travaille sur les **documents dérivés**, pas sur les
MP4 :

- regrouper les vidéos par sujet ;
- fusionner les enseignements redondants ;
- relever les contradictions ;
- distinguer opinion, expérience et fait vérifiable ;
- construire des « leçons » transverses avec plusieurs citations ;
- séparer clairement `affirmé dans la vidéo`, `confirmé extérieurement` et `observé en expérience` ;
- mettre à jour les dossiers sous `corpus/<profil>/`.

Cette passe est idéale pour un batch nocturne sur Banga : elle consomme du texte, peut utiliser le
LLM local via LiteLLM, et basculer vers un modèle cloud seulement pour les cas difficiles.

#### Passe E — réponse à une question

À chaque question :

1. recherche hybride dense + BM25 dans Qdrant ;
2. filtres éventuels (profil, période, langue, thème) ;
3. récupération des passages et claims les plus pertinents ;
4. reranking optionnel des candidats ;
5. génération distinguant affirmation source, état de vérification et résultat expérimental ;
6. citations cliquables `@profil — shortcode — MM:SS` ;
7. réponse « sources insuffisantes » si le corpus ne permet pas de conclure.

La Passe E ne réanalyse donc ni audio ni image. Elle synthétise des preuves déjà calculées. Par
défaut, les réponses excluent les claims `pending`, `refuted` ou `insufficient_evidence` des
recommandations et les montrent seulement dans une section critique.

### 7.2 Modèle documentaire

Chaque vidéo produit plusieurs unités indexables :

| Type | Exemple | Granularité |
|---|---|---|
| `concept` | « coût d'opportunité » | définition + contexte |
| `claim` | « telle méthode réduit le délai » | assertion + preuve vidéo + confiance d'extraction |
| `verified_claim` | état critique d'une affirmation | sources externes + statut + limites |
| `procedure` | suite d'étapes actionnables | étape ou petit groupe d'étapes |
| `experiment` | test reproductible d'une proposition | protocole + résultats + conclusion |
| `example` | cas concret donné dans la vidéo | exemple autonome |
| `caveat` | limite, exception, contre-indication | passage cité |
| `summary` | synthèse de la vidéo | un document par média |
| `corpus_lesson` | enseignement consolidé multi-vidéos | plusieurs sources |

Le chunking suit les segments sémantiques et les timestamps, pas seulement une taille arbitraire en
tokens. Un chunk conserve toujours :

```text
source_id, profile_id, shortcode, start_s, end_s,
knowledge_type, confidence, language, published_at,
verification_status, risk_level, bundle_path, source_url, prompt_version
```

### 7.3 Stockage logique

Trois couches, aucune ne remplace les autres :

| Couche | Technologie | Rôle |
|---|---|---|
| Fichiers canoniques | Banga ZFS | reconstruction, audit, lecture humaine |
| Catalogue | PostgreSQL de Palais sur Sese | comptes, jobs, médias, claims, thèmes, rétention, permissions |
| Index de recherche | Qdrant sur Sese | recherche hybride rapide, index reconstructible |

Collection cible : **`knowledge_v1`**.

Elle reprend le contrat éprouvé de `memory_v3` :

- vecteur nommé `dense`, EmbeddingGemma 300M, 768 dimensions, cosine ;
- vecteur sparse `bm25`, modifier IDF ;
- fusion RRF par défaut ;
- payload indexé sur `platform`, `profile_id`, `username`, `knowledge_type`, `language`,
  `published_at`, `tags`, `verification_status`, `risk_level`, `schema_version`,
  `prompt_version`.

`memory_v3` reste la mémoire opérationnelle des agents. `knowledge_v1` contient la bibliothèque de
contenus. `trend-dna` pourra être créé plus tard pour les métriques créatives ContentDNA
(hook, pacing, cuts/s, CTA), sans mélanger ce besoin avec les enseignements généraux.

### 7.4 Présentation

#### Palais — autorité

Ajouter un module `/knowledge` :

```text
/knowledge
├── /ingestions               jobs et erreurs
├── /sources                  profils/comptes
├── /videos                   catalogue filtrable
├── /topics                   concepts et leçons consolidées
├── /search                   recherche hybride
└── /ask                      réponse IA avec citations
```

Une fiche vidéo affiche :

- poster et lien de lecture Jellyfin si le MP4 est archivé ;
- métadonnées source ;
- transcript/VTT synchronisé ;
- enseignements et claims ;
- état de contre-vérification, sources favorables/défavorables et limites ;
- protocoles expérimentaux et résultats reproductibles ;
- confiance d'extraction, statut de vérification et modèles ayant produit chaque objet ;
- citations temporelles ;
- versions d'analyse et bouton de réanalyse explicite ;
- politique de conservation et preuve de suppression/archivage.

#### Open WebUI — conversation

Créer un modèle/espace « Bibliothèque » qui appelle l'API Knowledge avant le LLM et injecte les
passages cités. Cette intégration doit être déterministe et ne pas dépendre du tool-calling parfois
fragile des petits modèles locaux.

Open WebUI sait aussi gérer ses propres Knowledge Bases et du RAG hybride, mais recopier tous les
documents dans son index créerait une seconde source de vérité. Son connecteur Qdrant externe est
encore expérimental. Pour le MVP, l'API Knowledge de Sese reste le retriever unique ; Open WebUI est
une façade.

#### Agents

Exposer ensuite les mêmes opérations en MCP :

```text
knowledge.search(query, filters)
knowledge.get(source_id)
knowledge.ask(question, filters)
knowledge.citations(answer_id)
knowledge.verify(claim_id)
knowledge.get_verification(claim_id)
knowledge.propose_experiment(claim_id)
knowledge.get_experiment(experiment_id)
```

Codex/OpenClaw/Palais/Open WebUI consomment ainsi le même moteur et les mêmes citations.

## 8. Limitation de charge et sécurité de compte

### Valeurs de configuration

Deux temporisations distinctes :

- `request_delay` : délai court entre requêtes d'énumération ; conserver au minimum le défaut
  Instagram de gallery-dl (actuellement 6–12 s) ;
- `media_delay` : délai métier entre deux vidéos ; plage configurable, défaut initial proposé
  **15–20 min avec jitter**.

Le délai ne garantit pas l'absence de blocage. Il réduit seulement la cadence.

### Circuit breaker obligatoire

Arrêt immédiat du job sur :

- HTTP 401/403/429 répétés ;
- checkpoint/challenge/login required ;
- cookies invalides ;
- changement de structure empêchant d'obtenir un `source_id` fiable.

Pas de retry agressif. L'opérateur doit voir la cause, renouveler explicitement l'autorisation puis
reprendre.

### Cookies

- compte Instagram dédié et sacrifiable, jamais le compte principal ;
- export Netscape fourni hors Git ;
- fichier déployé en `0400`, répertoire `0700`, volume Docker read-only ;
- aucune valeur de cookie dans env, argv, logs, manifests ou sorties Ansible ;
- test CI qui échoue si `sessionid`, `csrftoken` ou une ligne Netscape apparaît dans un artefact suivi.

## 9. Gates avant exécution réelle

| Gate | Condition | Bloquant |
|---|---|---|
| G0 — tests locaux | tests unitaires + Molecule + `ansible-playbook --syntax-check` verts | oui |
| G1 — autorisation | l'utilisateur confirme le compte cible et qu'il est autorisé à archiver/analyser son contenu | oui |
| G2 — risque compte | l'utilisateur accepte le risque de checkpoint/ban et fournit un compte dédié | oui |
| G3 — dry-run | manifeste sans téléchargement : volume, types, dates et taille estimée disponibles | oui |
| G4 — canary | 3 vidéos max, une à la fois, résultat `learning.v1` validé manuellement | oui |
| G5 — bulk | lancement explicite avec `max_items` ou plage temporelle | oui |
| G6 — stockage | promotion atomique et restauration Banga testées avec un bundle factice | oui avant canary |
| G7 — bibliothèque | recherche et réponse citée testées depuis un bundle réindexé | oui avant bulk |
| G8 — risque élevé | revue humaine du dossier de preuve et du protocole expérimental | oui avant statut `supported` ou test |

Le déploiement peut être terminé avant G1/G2, mais aucune requête Instagram réelle ne doit partir.

## 10. Lots d'implémentation

### Lot 0 — Spike reproductible, sans mutation de production

Objectif : verrouiller les hypothèses instables avant de coder le worker.

1. Pinner une version gallery-dl compatible ARM64.
2. Sur un profil public de test autorisé, exécuter uniquement les commandes de métadonnées :
   - vérifier distinction posts/Reels ;
   - lister les clés avec `gallery-dl -K` ;
   - confirmer la clé vidéo et les carrousels ;
   - confirmer que le manifeste conserve une URL canonique, pas seulement une URL CDN expirante.
3. Tester un seul Reel avec et sans cookies.
4. Mesurer les erreurs produites pour 401, 403, 429 et challenge.
5. Comparer Instaloader uniquement si gallery-dl échoue sur l'un des critères bloquants.

Artefact : `docs/rex/REX-INSTAGRAM-SCOUT-SPIKE-2026-XX-XX.md`, sans données personnelles ni cookies.

Sortie de lot : décision `gallery-dl`, `instaloader` ou `fallback managé`; pas de worker construit
tant que le fetcher ne produit pas l'identité stable attendue.

### Lot 1 — Figer le contrat d'analyse et choisir son placement

Le contrat `learning.v1` est indépendant de la machine et du moteur. Avant de déplacer la charge,
constituer un jeu de 10 vidéos autorisées, variées en durée, langue, présence de texte et qualité
audio, puis comparer :

| Étape | Baseline | Challenger |
|---|---|---|
| audio | whisper.cpp `base` sur Waza | whisper.cpp GPU sur Banga |
| OCR | extraction actuelle via LiteLLM | GLM-OCR sur Banga |
| synthèse | alias LiteLLM actuel | modèle multimodal Gemini autorisé |

Mesurer WER sur un échantillon corrigé, rappel OCR, conformité JSON, qualité des preuves,
latence et coût. La décision par défaut est :

- Banga pour `ffmpeg`, transcription et OCR batch ;
- LiteLLM sur Sese pour la synthèse structurée ;
- Waza comme fallback temporaire, pas comme cible de calcul lourd.

Travaux communs :

1. Extraire de VideoRef la logique transcription/OCR commune sans changer ses endpoints existants.
2. Corriger l'utilisation de `interval_sec`.
3. Ajouter un endpoint interne `POST /api/learning` au moteur retenu avec validation :
   - chemin résolu strictement sous `WATCH_DIR` ;
   - extension vidéo allowlistée ;
   - taille/durée maximales configurables ;
   - métadonnées source obligatoires ;
   - réponse idempotente si `source_id + sha256 + prompt_version` existe déjà.
4. Ajouter un sémaphore d'analyse configurable, défaut `1` sur le Pi.
5. Remplacer les troncatures fixes par un traitement par segments/chunks puis consolidation.
6. Valider strictement `learning.v1`; conserver la réponse LLM brute en diagnostic si invalide,
   sans l'indexer.
7. Utiliser un alias de modèle configuré dans l'env, jamais un nom de modèle hardcodé.
8. Persister atomiquement (`.tmp` puis rename).
9. Indexer seulement après écriture locale réussie.
10. Ne pas modifier le comportement de `/api/webhook/metube`, `/api/transcribe` ou
    `/api/intelligence` dans ce lot, sauf correction de bug couverte par test.

Fichiers VPAI si Waza reste la baseline :

- `roles/videoref-engine/files/app.py`
- `roles/videoref-engine/defaults/main.yml`
- `roles/videoref-engine/templates/videoref.env.j2`
- `roles/videoref-engine/files/Dockerfile`
- `roles/videoref-engine/molecule/default/verify.yml`
- nouveau `roles/videoref-engine/files/tests/test_learning.py`

Tests :

- rejet traversal `../../...` ;
- même requête deux fois → même résultat, un seul point ;
- changement de SHA → nouvelle analyse contrôlée ;
- LLM JSON invalide → `failed`, aucun point Qdrant ;
- vidéo sans piste audio → résultat partiel explicite ;
- OCR vide → extraction transcript-only ;
- timeout LiteLLM → erreur retryable ;
- UUID stable entre deux processus Python.

### Lot 2 — Provisionner `knowledge_v1`

La collection métier reste séparée de `memory_v3` et de `videoref_styles`. Elle reprend les briques
dense+BM25+RRF et le harness de `memory_v3`, sans dupliquer sa collection opérationnelle.

Avant création :

1. résoudre l'alias d'embedding réellement utilisé ;
2. mesurer et figer sa dimension ;
3. documenter `embedding_model`, `embedding_dimension` et `schema_version` dans chaque payload.

Ajouter un provisionnement Ansible idempotent :

- création si absente ;
- validation dimension/distance si présente ;
- échec dur si le schéma existant est incompatible ;
- aucun delete/recreate automatique.

Tests de retrieval :

- une requête sur un concept retrouve la bonne vidéo ;
- les filtres `username`, `published_at`, `language`, `schema_version` fonctionnent ;
- réindexer le même document ne change pas le nombre de points.

### Lot 3 — Worker durable `instagram-scout`

Nouveaux fichiers :

```text
roles/instagram-scout/
├── defaults/main.yml
├── tasks/main.yml
├── templates/instagram-scout.env.j2
├── templates/gallery-dl.conf.json.j2
├── files/Dockerfile
├── files/scout.py
├── files/scoutctl
└── molecule/default/{converge,molecule,verify}.yml
```

Intégrations :

- `inventory/group_vars/all/versions.yml` : versions pinées du worker et de gallery-dl ;
- `roles/comfyui/templates/docker-compose-creative.yml.j2` : service sur le réseau `creative` ;
- `playbooks/hosts/workstation.yml` : rôle et tag `instagram-scout` ;
- volumes :
  - état RW dédié ;
  - downloads RW partagé ;
  - cookies RO ;
  - aucun montage du socket Docker.

Commandes opérateur :

```text
scoutctl discover <profile-url> [--max-items N] [--since YYYY-MM-DD]
scoutctl approve <job-id>
scoutctl run <job-id>
scoutctl status <job-id>
scoutctl stop <job-id>
scoutctl retry <job-id> [--item SOURCE_ID]
scoutctl export <job-id>
```

Contraintes du worker :

- une seule vidéo `downloading|analyzing` à la fois ;
- `discover` ne télécharge rien ;
- `run` refuse un job non approuvé ;
- les délais sont calculés côté worker, pas confiés à un appelant ;
- arrêt SIGTERM propre après l'item courant ;
- reprise automatique depuis SQLite ;
- stdout JSON structuré sans headers/cookies/URLs CDN signées ;
- téléchargement vers `.part`, hash puis rename atomique ;
- espace disque vérifié avant chaque média ;
- rétention configurable des MP4, jamais supprimés avant JSON + index validés.

Tests unitaires avec faux fetcher et faux VideoRef :

- découverte de carrousel contenant deux vidéos ;
- doublons entre `posts` et `reels` fusionnés par `source_id` ;
- arrêt/reprise au milieu d'un lot ;
- délai/jitter bornés (horloge injectée, aucun vrai sleep en test) ;
- 429 ouvre le circuit et bloque l'item suivant ;
- crash après download mais avant analyse reprend à `downloaded` ;
- crash pendant transfert reprend sans bundle partiel indexable ;
- analyse déjà existante passe de `stored` à `analyzed`, puis vérifie l'index ;
- disque sous le seuil bloque proprement le job.

### Lot 4 — Provisionner Banga comme archive canonique

Travaux dans le dépôt `banga` :

1. Ajouter le dataset `tank/knowledge` au provisionnement ZFS idempotent.
2. Déployer la racine `/tank/knowledge` avec l'arborescence de la section 5.2, permissions
   séparées `incoming`, `library`, `quarantine` et `exports`.
3. Exposer uniquement un compte de service SFTP/SSH restreint à Waza ; aucun partage
   NFS/SMB généraliste.
4. Transférer chaque média vers `incoming/<job_id>/<source_id>/`, vérifier SHA-256 côté Banga,
   puis faire un rename atomique vers `library/`.
5. Installer un janitor en mode rapport seul par défaut. L'activation de la suppression exige
   les quatre conditions de la section 5.3.
6. Ajouter snapshots ZFS et quotas/alertes ; ne pas considérer RAIDZ2 comme une sauvegarde.
7. Tester la restauration du catalogue et des dérivés. Le backup distant des sources brutes reste
   sélectif selon la politique de rétention.
8. Brancher le moteur d'analyse retenu au GPU Banga. Réutiliser `lxc-chat` seulement si son
   isolation, ses montages et sa concurrence sont adaptés ; sinon créer un LXC dédié
   `knowledge-worker`. Ce choix est arrêté par le benchmark du lot 1.

Fichiers cibles dans le dépôt frère `../banga` :

- `../banga/inventory/group_vars/all/main.yml`
- rôle ZFS existant de `../banga`
- nouveau rôle `../banga/roles/knowledge-store/`
- `../banga/roles/lxc-chat/` ou nouveau `../banga/roles/knowledge-worker/`
- `../banga/docs/runbooks/KNOWLEDGE-STORE.md`

Sortie de lot : un média factice peut être transféré, vérifié, promu, relu puis restauré sans
accès à Instagram.

### Lot 5 — Catalogue, API et soumission dans Palais

Créer une migration PostgreSQL pour :

- `knowledge_sources` : compte, plateforme, relation d'autorisation, politique ;
- `knowledge_ingestion_jobs` : demande, statut, limites, approbation, progression ;
- `knowledge_media` : identité stable, archive, analyse, rétention ;
- `knowledge_artifacts` : type, version, SHA, chemin Banga ;
- `knowledge_claims` : claim, preuve vidéo, timestamp, type et confiance d'extraction ;
- `knowledge_research_sources` : URL, éditeur, dates, classe, SHA et indépendance ;
- `knowledge_claim_verifications` : statut, conclusion, limites, version et revue ;
- `knowledge_experiments` : hypothèse, protocole, gates, résultats et décision ;
- `knowledge_corpus_versions` : périmètre, prompt, sources et état.

Ajouter :

- `POST /api/v1/knowledge/ingestions` ;
- `GET /api/v1/knowledge/ingestions/:id` ;
- `POST /api/v1/knowledge/ingestions/:id/approve` ;
- `POST /api/v1/knowledge/search` ;
- `GET /api/v1/knowledge/videos/:source_id` ;
- `POST /api/v1/knowledge/claims/:claim_id/verify` ;
- `GET /api/v1/knowledge/claims/:claim_id/verification` ;
- `POST /api/v1/knowledge/claims/:claim_id/experiments` ;
- `POST /api/v1/knowledge/experiments/:id/approve` ;
- `GET /api/v1/knowledge/experiments/:id` ;
- page `/knowledge/ingestions/new` ;
- pages `/knowledge`, `/knowledge/sources/[id]` et `/knowledge/videos/[id]`.

L'API crée le job puis appelle le worker Waza avec un jeton de service. Elle n'exécute ni
gallery-dl ni ffmpeg dans le processus web. Toutes les pages indiquent l'état réel :
`discovered`, `approved`, `downloading`, `transferring`, `stored`, `analyzing`, `analyzed`,
`indexed`, `failed`.

Implémenter aussi le callback d'événements et la réconciliation définis en 6.4. Les écritures de
statut utilisent un numéro de séquence monotone ; une livraison en double ou hors ordre ne régresse
jamais l'état affiché.

Le bouton de suppression ne supprime jamais directement le MP4 : il crée une demande auditable
appliquée par le janitor Banga après vérification des gates.

Tests :

- validation URL et limites ;
- job créé une seule fois avec la même clé d'idempotence ;
- approbation nécessaire avant téléchargement ;
- utilisateur non autorisé refusé ;
- recherche hybride et filtres ;
- résultat avec lien vers vidéo, timestamp et preuve ;
- disparition de Qdrant simulée : le catalogue reste consultable et réindexable.

### Lot 6 — Contre-vérification, expérimentation, consolidation et accès conversationnel

Déployer sur Sese un `research-worker` asynchrone, distinct du processus Palais :

1. file PostgreSQL/outbox avec budget, timeout et nombre maximal de sources ;
2. connecteur de recherche web déclaré et remplaçable ;
3. extracteur de pages qui conserve URL canonique, éditeur, dates et hash ;
4. allowlists par domaine sensible et priorité aux sources primaires ;
5. recherche contradictoire explicite ;
6. validation stricte de `verification.v1` ;
7. revue humaine obligatoire selon G8 ;
8. cache par requête et URL afin de maîtriser coût et répétitions.

Créer un `experiment-runner` sans accès à la production :

- manifestes `experiment.v1` versionnés ;
- image/versions/données et seed enregistrées ;
- CPU/RAM/GPU/temps et réseau bornés ;
- aucun secret de courtage ni capacité d'envoyer un ordre réel ;
- résultats bruts et rapport stockés sur Banga ;
- pour le trading, adaptateur de backtest puis paper trading en lecture seule côté décision.

Le profil trading recommandé est un conteneur **NautilusTrader** versionné sur Banga : moteur
événementiel déterministe, modèles de frais/fills/latence et même sémantique entre simulation et
sandbox. Pour ce projet, les adaptateurs live ne sont pas installés, aucun secret courtier n'est
monté et l'egress réseau est refusé. `vectorbt` peut servir au prototypage exploratoire rapide, mais
ne valide pas seul une stratégie ; le résultat final doit être reproduit dans le moteur
événementiel.

Créer un job versionné de consolidation qui lit uniquement les artefacts dérivés :

1. regrouper par source, période et thème ;
2. dédupliquer les enseignements sémantiquement proches ;
3. conserver accords, contradictions et incertitudes ;
4. intégrer statut de vérification et résultats d'expérience sans les confondre ;
5. produire `lesson.v1`, `topic-summary.v1` et `corpus-summary.v1` ;
6. écrire les fichiers sur Banga, le catalogue dans PostgreSQL et les chunks dans
   `knowledge_v1`.

Ajouter à Palais les outils MCP :

- `knowledge_search`
- `knowledge_get_source`
- `knowledge_get_evidence`
- `knowledge_compare_claims`
- `knowledge_verify_claim`
- `knowledge_get_verification`
- `knowledge_propose_experiment`
- `knowledge_get_experiment`

Brancher ensuite Open WebUI sur ces outils/API comme façade conversationnelle, sans lui confier
une seconde copie canonique des documents. Toute réponse doit citer `source_id`, vidéo et
timestamp, sources externes et statut de vérification ; une réponse sans preuve est présentée comme
synthèse non vérifiée.

### Lot 7 — Canary de bout en bout puis bulk

1. Déployer avec cookies absents et worker désactivé par défaut.
2. Vérifier healthchecks et réseau interne.
3. Après G1/G2, installer le fichier cookie sans l'afficher dans Ansible.
4. `discover --max-items 3`.
5. Faire valider le manifeste.
6. Lancer 3 vidéos avec le délai configuré.
7. Contrôler manuellement :
   - correspondance vidéo/transcript ;
   - timestamps ;
   - claims réellement appuyés par la source ;
   - au moins un claim vérifié avec source favorable et recherche contradictoire ;
   - aucun claim à risque élevé marqué `supported` sans revue humaine ;
   - un protocole expérimental exécutable sans effet réel ;
   - absence de doublon local/Qdrant ;
   - charge CPU/RAM/température et espace disque.
8. Attendre au moins un cycle normal sans 429/challenge.
9. Lancer le bulk avec limite explicite, jamais « illimité » au premier run.

Le canary valide le trajet complet : formulaire Palais → manifeste Waza → approbation → archive
Banga → extraction → contre-vérification → catalogue PostgreSQL → index Qdrant → réponse
Palais/Open WebUI distinguant clairement affirmation, preuve externe et expérience.

### Lot 8 — Exploitation

Ajouter :

- runbook `docs/runbooks/INSTAGRAM-SCOUT.md` ;
- runbook `docs/runbooks/KNOWLEDGE-LIBRARY.md` ;
- métriques ou, au minimum, état JSON consommable :
  `discovered`, `downloaded`, `stored`, `analyzed`, `indexed`, `failed`, `circuit_open`,
  `last_success`;
- alerte si circuit ouvert, cookies invalides, spool Waza haut, quota Banga haut, index en retard
  ou aucun progrès pendant 24 h ;
- procédure de rotation des cookies ;
- procédure de réindexation depuis les bundles Banga sans re-télécharger Instagram ;
- procédure de changement de prompt avec nouvelle `prompt_version`.
- procédure de revalidation des claims `time_sensitive` ;
- procédure d'arrêt et d'audit d'une expérience ;
- workflow n8n limité aux notifications d'échec, demande d'approbation et rapport de fin.

## 11. Critères d'acceptation

### Fonctionnel

- un compte est soumis depuis Palais et son état est visible sans accès SSH ;
- un profil produit un manifeste avant téléchargement ;
- seuls les médias vidéo approuvés sont traités ;
- 3 vidéos de canary donnent 3 JSON `learning.v1` validables ;
- les claims vérifiables produisent des `verification.v1` distincts ;
- les sources et dérivés sont rangés sous l'identité stable prévue sur Banga ;
- la suppression du spool Waza n'arrive qu'après promotion vérifiée sur Banga ;
- une relance n'effectue aucun téléchargement ni indexation en double ;
- arrêt/restart du conteneur reprend sans perdre l'état ;
- un carrousel multi-vidéo est représenté sans collision.
- une consolidation produit une vue par thème sans relire les MP4 ;
- Palais et Open WebUI retrouvent un enseignement et sa preuve horodatée.
- un claim testable peut produire un protocole, un résultat brut et une conclusion reproductible ;
- aucune fonctionnalité ne permet d'envoyer un ordre de marché réel.

### Qualité

- chaque claim important a une preuve temporelle ou une incertitude explicite ;
- extraction, vérification externe et validation expérimentale sont affichées séparément ;
- la recherche contradictoire est tracée, même lorsqu'elle ne trouve rien ;
- les sources dupliquées ou dépendantes ne gonflent pas le niveau de preuve ;
- transcript complet et fichiers canoniques disponibles sur Banga ;
- recherche Qdrant retrouve au moins 4/5 concepts d'un mini jeu de test ;
- aucun résultat invalide n'est indexé.
- la reconstruction de `knowledge_v1` depuis Banga + PostgreSQL est testée ;
- une contradiction entre deux vidéos reste visible après consolidation.
- un claim réfuté n'est jamais présenté comme recommandation dans `/ask`.

### Sécurité et exploitation

- zéro secret dans Git, logs, argv et résultats Ansible ;
- aucun port public ajouté ;
- un 429/challenge stoppe le lot ;
- concurrence effective égale à 1 ;
- aucune suppression automatique d'une collection Qdrant ;
- un export JSON/CSV permet d'auditer l'état complet du job.
- restauration d'un artefact dérivé testée ;
- quota, snapshot, rétention et propriétaire sont documentés pour `tank/knowledge`.
- toute expérience possède limites de ressources, arrêt, journal et approbation ;
- finance/santé/droit/sécurité restent bloqués en revue humaine avant validation forte.

## 12. Non-objectifs MVP

- stories, highlights, lives, commentaires et messages privés ;
- profils privés non explicitement autorisés ;
- contournement de checkpoint, CAPTCHA, challenge ou restriction Meta ;
- rotation de proxies ou multi-comptes pour contourner un rate limit ;
- entraînement/fine-tuning automatique ;
- analyse frame par frame de toute la vidéo ;
- remplacement immédiat de whisper.cpp par Gemini ;
- ingestion automatique de nouveaux posts récurrents.
- duplication des documents dans la base Knowledge interne d'Open WebUI ;
- backup distant systématique de tous les MP4 bruts.
- conseil financier personnalisé ou exécution d'ordres ;
- optimisation automatique d'une stratégie sur le jeu de test ;
- promotion automatique d'un résultat de backtest vers le réel.

## 13. Décisions reportées, avec déclencheur

| Décision | Déclencheur |
|---|---|
| Instaloader comme fallback | gallery-dl ne produit pas un manifeste fiable sur le canary |
| Fallback managé type Apify | les deux fetchers locaux échouent durablement et le coût est accepté |
| Modèle Gemini audio+vidéo | benchmark canary montrant un gain net qualité/coût/latence |
| `faster-whisper large-v3-turbo` | `ggml-base` échoue au seuil qualité défini sur le jeu canary |
| Scheduler récurrent | le premier backfill complet est stable et l'autorisation couvre la veille |
| LXC Banga dédié | `lxc-chat` ne satisfait pas isolation, montage ou capacité |
| backup distant des MP4 | valeur patrimoniale et budget de stockage le justifient |

## 14. Ordre de livraison recommandé

```text
Lot 0 spike fetcher
  → Lot 1 contrat + benchmark Waza/Banga
  → Lot 2 stockage Qdrant
  → Lot 3 worker durable
  → Lot 4 archive Banga
  → Lot 5 catalogue + interface Palais
  → Lot 6 consolidation + MCP/Open WebUI
  → G1/G2
  → Lot 7 canary de bout en bout
  → validation humaine
  → bulk limité
  → Lot 8 exploitation
```

Les lots 2 et 4 peuvent avancer en parallèle après le contrat du lot 1. Le chemin critique est la
fiabilité du fetcher, l'identité stable, l'idempotence, la promotion Waza→Banga et la reprise.
Aucun bulk ne commence tant que ces propriétés ne sont pas démontrées sur le canary complet.

## 15. Sources vérifiées

### Mémoire et dépôt VPAI

- `docs/audits/2026-06-10-content-factory-v2-analyse-fonctionnelle-structurelle.md`
- `docs/plans/2026-04-09-llamaindex-memory-waza-plan.md`
- `docs/superpowers/specs/2026-06-10-rag-v3-contracts.md`
- `docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md`
- `docs/design/2026-07-23-refonte-backup-zerobyte-orchestrateur-seko.md`
- `docs/2026-07-16-feuille-de-route-infra-sota.md`
- `docs/audits/qdrant-legacy-migration-map-2026-04-11.md`
- `roles/metube/defaults/main.yml`
- `roles/metube/templates/metube.env.j2`
- `roles/videoref-engine/files/app.py`
- `roles/videoref-engine/defaults/main.yml`
- `roles/comfyui/templates/docker-compose-creative.yml.j2`
- `roles/palais/files/app/src/routes/api/v1/memory/search/+server.ts`
- `roles/palais/files/app/src/routes/memory/+page.svelte`

### Mémoire et dépôt Banga

- `../banga/.planning/STATE.md`
- `../banga/docs/audits/2026-07-23-quotas-diskguard-gate.md`
- `../banga/docs/superpowers/specs/2026-07-23-lxc-cloud-design.md`
- `../banga/docs/superpowers/specs/2026-07-24-lxc-chat-design.md`

### Documentation upstream consultée le 2026-07-27

- yt-dlp, `supportedsites.md` et `yt_dlp/extractor/instagram.py` :
  `instagram:user` déclaré non fonctionnel ;
- gallery-dl, documentation de configuration :
  profils/posts/Reels, archive SQLite, cookies, délais et stratégie Instagram ;
- Instaloader, documentation CLI/module :
  parcours posts/Reels, reprise et contrôleur de cadence.
- Meta Instagram API : accès officiel aux médias des comptes professionnels gérés ;
- Qdrant : recherche hybride dense+sparse et fusion RRF ;
- Open WebUI : Knowledge, API et citations RAG ; backend Qdrant externe encore expérimental.
- ESMA, recommandations d'investissement sur les réseaux sociaux : distinguer faits,
  interprétations/opinions, vérifier les sources et déclarer les conflits d'intérêts ;
- AMF, finfluenceurs et vérification des acteurs : exactitude, risques, rémunérations, REGAFI,
  ORIAS et listes noires ;
- SEC, Investment Adviser Marketing : limites des performances hypothétiques, hypothèses,
  risques, performance nette et présentation équilibrée ;
- NautilusTrader : simulation événementielle déterministe et modèles de fills, frais et latence ;
- vectorbt : prototypage vectorisé rapide, utilisé seulement comme outil exploratoire.
