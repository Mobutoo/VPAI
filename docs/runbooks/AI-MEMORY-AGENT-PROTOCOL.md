> ⚠️ **RÉFÉRENCES PÉRIMÉES (memory_v1)** — La doctrine active est **memory_v3** (BM25+RRF hybride, hook R0-Continu, floor de score v3). Ce protocole d'usage v1 est **superseded par la LOI OPÉRATIONNELLE R0** (`docs/runbooks/LOI-OPERATIONNELLE-MCP-FIRST.md`) et la mémoire projet `project_rag_v3_hybrid`. Collection, scores et protocole décrits ci-dessous peuvent être caducs — vérifier avant de s'y fier. _(bandeau audit RAG 2026-07-15, P1-5)_

# Runbook — Protocole d'usage de la memoire IA par les agents

Date: 2026-04-11
Statut: v0.7 — protocole initial
Portee: comment Claude Code, Codex, et les autres agents doivent interroger
et alimenter la memoire `memory_v1` sur Waza.

Ce runbook est la **reference de comportement agent**. CLAUDE.md pointe ici.
Il suppose que le lot memoire est deja deploye et operable (voir
`docs/runbooks/AI-MEMORY-OPERATIONS.md`).

## 1. Principes

Trois regles absolues:

1. **Seul le worker ecrit dans `memory_v1`.** Les agents ne poussent jamais
   directement dans Qdrant. Si un agent produit du contenu digne d'etre
   memorise, il l'ecrit comme **fichier indexable** (REX, plan, spec, doc)
   dans un repo deja couvert par `sources.yml`, et laisse le timer Waza
   l'indexer au prochain tick.
2. **Interroger avant de conclure.** Quand une question touche l'historique
   du projet, une decision passee, un pattern deja implemente ou un incident
   precedent, lancer `search_memory.py` **avant** de repondre. La memoire
   a ete construite pour eviter les regressions et les reinventions.
3. **Pas de reponse fabulee sur un sujet passe.** Si la memoire ne sait
   pas, dire "je ne trouve pas" est meilleur qu'inventer. L'agent doit
   explicitement indiquer quand il cite la memoire vs quand il raisonne
   sur le code courant.

## 2. Quand interroger la memoire

Sujets qui justifient une recherche memoire avant de repondre:

- **Decisions passees**: "pourquoi on a choisi X plutot que Y ?"
- **Incidents connus**: "est-ce qu'on a deja vu cette erreur ?"
- **Patterns etablis**: "comment on fait une `Caddy VPN ACL` dans ce projet ?"
- **REX de session**: "qu'est-ce qui s'est passe pendant la session du
  2026-02-18 ?"
- **Workflows existants**: "est-ce qu'il y a deja un n8n workflow pour X ?"
- **Architecture deja definie**: "la stack de story-engine, elle utilise quoi ?"

Sujets qui **n'ont pas besoin** de memoire:

- Questions triviales sur le code courant (lire le fichier directement)
- Questions sur l'etat live d'un service (utiliser `systemctl`, `docker`, etc.)
- Questions sur la date, l'heure, l'environnement (pas dans Qdrant)
- Questions dont la reponse tient dans la prochaine commande shell a lancer

Heuristique: **"si un collegue senior avec 6 mois d'historique projet
pourrait repondre de memoire, interroger la memoire."**

## 3. Comment interroger

### 3.1 Commande de base

La CLI actuelle expose `search_memory.py`. Elle doit etre lancee sur Waza
avec l'environnement du worker (sinon HuggingFace echoue a charger le modele
local):

```bash
set -a
. /opt/workstation/configs/ai-memory-worker/memory-worker.env
set +a

/opt/workstation/ai-memory-worker/.venv/bin/python \
  /opt/workstation/ai-memory-worker/search_memory.py \
  --config /opt/workstation/configs/ai-memory-worker/config.yml \
  --query "ma question en langage naturel" \
  --limit 5
```

### 3.2 Parametres utiles

| Flag | Effet |
|---|---|
| `--query` | Texte de la requete. Obligatoire. Utiliser des mots-cles metier, pas du jargon. |
| `--limit` | Nombre de resultats (defaut 5). Augmenter si la reponse semble fragmentee. |
| `--repo` | Filtre par repo: `VPAI`, `flash-studio`, `story-engine`, `ops`. |
| `--doc-kind` | Filtre par type: `code`, `doc`, `rex`, `plan`, `spec`, `config`, `workflow`. |
| `--topic` | Filtre par topic (roles Ansible, H1 markdown, etc.). |

### 3.3 Exemples reels

Trouver le guide operationnel d'un sous-systeme:

```bash
search_memory.py ... --query "caddy vpn only acl split dns" --limit 3
```

Chercher un REX sur un incident:

```bash
search_memory.py ... --query "openclaw crash loop v2026" --doc-kind rex
```

Trouver un workflow n8n existant:

```bash
search_memory.py ... --query "af rex indexer webhook" --doc-kind workflow
```

Verifier si un pattern a deja ete implemente ailleurs:

```bash
search_memory.py ... --query "systemd ExecStartPre loadavg gate"
```

### 3.4 Lecture d'un resultat

Chaque ligne de sortie est un JSON avec les champs:

- `score` — similarite cosine (0 a 1). Au-dessus de ~0.40 le resultat est
  pertinent. En dessous de 0.25 c'est probablement du bruit.
- `repo` — source d'origine (`VPAI`, `flash-studio`, etc.)
- `doc_kind` — classification du chunk (`code`, `doc`, `rex`, ...)
- `relative_path` — chemin du fichier dans son repo
- `title` — titre extrait automatiquement du chunk
- `topic` — theme (nom du role Ansible, H1 markdown, etc.)
- `section` — section markdown si applicable

Quand un score est eleve (>0.5), l'agent **doit** ouvrir le fichier cite
pour verifier le contenu reel avant d'en tirer une conclusion. La memoire
donne la **localisation**, pas la verite. Les chunks peuvent etre obsoletes
si le fichier a change entre l'indexation et la requete.

### 3.5 Bench qualite

Si la memoire semble donner des resultats incoherents, lancer le benchmark:

```bash
set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a

/opt/workstation/ai-memory-worker/.venv/bin/python \
  /opt/workstation/ai-memory-worker/benchmark_memory.py \
  --config /opt/workstation/configs/ai-memory-worker/config.yml \
  --repo VPAI
```

Critere de maintien: `miss_ratio <= 0.30` sur les 20 requetes de
`benchmark-queries.yml`. Au-dessus, le modele d'embedding est degrade et
une escalade est necessaire (voir plan section 5.5).

### 3.6 Rerank (cable, OFF par defaut — ne pas activer sur le chemin R0 interactif)

`rerank.py` (bge-reranker-v2-m3 ONNX) est cable derriere `search_memory.py`
(`--rerank` / env `RERANK_ENABLED`) et `mcp_search.py` (le vrai backend de
`mcp__qdrant__qdrant-find`, env `RERANK_ENABLED`). **Les deux entrypoints sont
OFF par defaut** — l'agent qui appelle `mcp__qdrant__qdrant-find` normalement
ne passe jamais par le reranker.

Benchmark reel (audit 2026-07-17, FIX B, RPi5 waza, `nice -19`, modele charge
une fois — 27 requetes `benchmark-queries.yml`, 20 candidats re-scores) :

| | Sans rerank (RRF seul) | Avec rerank |
|---|---|---|
| Mediane | 0.6s | **10.4s** (+9.8s) |
| Max | 1.1s | **13.6s** (+13.6s) |

Trop lent pour un usage interactif R0 (budget ~3-5s/requete) — **reste OFF
par defaut**. Cause: cross-encoder 568M params en inference CPU pure sur
ARM64, pas de GPU. Le repo HF par defaut de `rerank.py`
(`BAAI/bge-reranker-v2-m3`) n'a d'ailleurs AUCUN artefact ONNX — l'override
`MEMORY_RERANK_MODEL_ID=onnx-community/bge-reranker-v2-m3-ONNX` est
obligatoire pour que le flag fonctionne (sinon fail-open silencieux, warning
stderr `rerank indisponible`).

Si un jour necessaire (ex. eval hors-ligne, pas R0 interactif): activer via
`RERANK_ENABLED=true` dans `memory-worker.env` (ou `memory_worker_rerank_enabled:
true` cote Ansible) — jamais comme defaut du chemin agent tant qu'un modele
plus leger (ex. cross-encoder MiniLM fastembed, ~90MB) n'a pas ete valide sur
Pi avec une latence sous budget.

**Modele leger teste et DISQUALIFIE (2026-07-17, restauration recall@1)** :
`Xenova/ms-marco-MiniLM-L-6-v2` (fastembed `TextCrossEncoder`, ~23M params,
~90MB ONNX — 25x plus petit que bge-reranker-v2-m3) rerank les meilleurs hits
fusionnes sur le TEXTE COMPLET du chunk (le snippet 160 car. est aveugle pour
un cross-encoder). Resultat, sous-echantillon 15 questions, `nice -19`, modele
charge une fois :

| Texte fourni | Mediane/requete | recall@1 (15 q) |
|---|---|---|
| Complet (jusqu'a 1600 car.) | **9.7s** | 0.33 (baseline ~0.60 sur ce sous-ensemble) |
| Tronque a 400 car. | **2.9s** | 0.27 |

Double disqualification : (1) latence quasi identique au modele lourd malgre
23M vs 568M params — le cout domine par la longueur de sequence (texte complet
necessaire), pas le nombre de parametres, et meme tronque reste ~2x le budget
interactif ; (2) **qualite degradee**, pas seulement neutre — le modele
(anglais, entraine MS MARCO) sur-note des blobs JSON de workflows n8n sur pur
chevauchement lexical de noms de champs (`webhook`, `responseNode`), poussant
un resultat non pertinent au rang 13. Piste rerank leger fermee tant qu'aucun
autre modele n'est teste (candidat multilingue restant : `jinaai/jina-reranker-
v2-base-multilingual`, 1.1GB — jamais teste, taille suggere une latence encore
pire).

### 3.7 Fusion RRF vs DBSF (restauration recall@1, 2026-07-17)

Qdrant RRF utilise **k=2 par defaut** (PAS 60, la valeur "standard" de la
litterature IR generaliste) — verifie doc officielle
https://qdrant.tech/documentation/concepts/hybrid-queries/. Fusion rank-only
tres sensible au bruit de classement introduit par la croissance du corpus
(24k -> 82k+ pts, 9 -> 27 repos auto-decouverts depuis le ship 2026-06-10,
cf `docs/audits/2026-07-17-audit-memoire.md` §3).

**DBSF (Distribution-Based Score Fusion, natif Qdrant, ZERO cout de latence
additionnel)** mesure sur golden 76 questions (memory_v3, collection gelee) :

| Fusion | recall@1 | recall@5 | mrr@10 | Reproductibilite |
|---|---|---|---|---|
| RRF (k=2, ancien defaut) | 0.6316 (exact) / 0.6447 (approx) | 0.9737 | ~0.78 | Bruit HNSW +-2 a 4 pts entre runs identiques |
| **DBSF (nouveau defaut)** | **0.6711** | 0.9737 | 0.7939 | **Identique 2/2 exact ET 2/2 approximatif** |

+3 a +4 pts recall@1 vs RRF, recall@5 inchange, ET plus stable que RRF lui-meme
(0 variance observee sur 4 runs vs jusqu'a 5,3 pts d'ecart RRF run-a-run —
approximation HNSW, pas un bug). Inspection individuelle : DBSF corrige les cas
de **decalage de score pur** entre deux documents deja indexes (ex. n8n
workflow DELETE : rang 2->1) mais ne corrige PAS les cas de **croissance de
corpus reelle** ou un document nouvellement indexe (`wiki:*.md`,
`hawktrade:*`) est un concurrent legitimement pertinent qui n'existait pas au
golden.yml d'origine (ex. PostgreSQL 18 mount path, Caddy heredoc, checklist
OpenClaw — `wiki:caddy.md`/`wiki:openclaw.md` gagnent legitimement). Ces cas
ne sont pas un bug de ranking : ils signalent un **golden-set a rafraichir**
(gate humain — ne jamais editer golden.yml sans validation qu'un nouveau
document est reellement la meilleure reponse).

**Defaut depuis 2026-07-17** : `MEMORY_FUSION_MODE=dbsf` (env, `mcp_search.py`
+ `search_memory.py` + `run_eval.py --fusion`). Rollback instantane :
`MEMORY_FUSION_MODE=rrf` (ou `memory_worker_fusion_mode: rrf` cote Ansible).

## 4. Comment alimenter la memoire

### 4.1 Le canal legitime

Le seul moyen propre d'ajouter du contenu memorise est d'ecrire un fichier
**versionne** dans un repo couvert par `sources.yml`. Le timer Waza va
l'indexer au prochain tick (30 min par defaut, ou immediatement via
`scripts/memory-backfill.sh --path <fichier>`).

Types de contenu a produire en priorite:

| Type | Format | Emplacement typique |
|---|---|---|
| REX de session | markdown avec titre horodate | `docs/REX-SESSION-YYYY-MM-DD.md` |
| Plan d'implementation | markdown structure | `docs/plans/YYYY-MM-DD-<slug>.md` |
| Spec technique | markdown structure | `docs/specs/YYYY-MM-DD-<slug>.md` |
| Runbook | markdown operationnel | `docs/runbooks/<slug>.md` |
| Decision majeure | inclure dans le REX de session | — |

Regles de redaction:

- **Titres explicites** — les H1/H2 deviennent du `topic` dans la metadata
- **Horodatage dans le chemin** — rend la chronologie lisible dans les resultats
- **Faits verifiables** — le worker n'a pas de notion de "source fiable",
  tout ce qui est indexe est tenu pour vrai au moment du run
- **Pas de secrets** — contenu indexable = contenu potentiellement cite

### 4.2 Ce que l'agent ne doit PAS faire

- Ecrire directement dans Qdrant via `qdrant-client` ou HTTP
- Envoyer du contenu dans la memoire via les hooks Claude Code
- Ajouter une nouvelle collection Qdrant sans passer par la phase E (migration legacy)
- Supprimer ou modifier des points existants dans `memory_v1`
- Ajouter un repo source sans editer `sources.yml` en code et redeployer
  le role Ansible

Tout contournement de ce protocole casse la garantie "un seul writer" sur
laquelle repose la resilience du pipeline (plan section 10.4).

## 5. Cas particulier: detection de regression sur un REX ancien

Si un agent decouvre qu'un REX indexe est **obsolete** (ex: un bug a ete
corrige apres la redaction du REX), le bon comportement est:

1. Ecrire un nouveau REX qui reference l'ancien et decrit le fix
2. Laisser l'ancien REX dans le repo et dans l'index
3. **Ne pas** supprimer l'ancien contenu

Le worker utilise `ref_doc_id` stable par chemin: si l'ancien REX n'est pas
modifie, ses chunks restent. Si un nouveau REX le remplace, l'indexation
incrementale upsert correctement le nouveau contenu au prochain tick.

## 6. Cas particulier: session multi-agent

Si plusieurs agents travaillent sur un meme sujet (ex: Claude Code +
Codex), ils peuvent se partager le contexte **via la memoire** plutot que
de se copier des extraits de conversation:

- Agent A termine une etape → ecrit un REX intermediaire → commit
- Agent B demarre sa session → interroge la memoire sur le sujet → recoit
  le REX de A dans les resultats → lit le fichier complet avant d'avancer

Cela evite les regressions "Codex ne sait pas ce que Claude a fait" et
reciproquement.

## 7. Protocole de citation

Quand un agent cite un fait appris de la memoire, il doit indiquer
explicitement la source:

> "D'apres le REX du 2026-02-18 (`docs/REX-SESSION-2026-02-18.md`), on avait
> deja resolu ce probleme en..."

Pas:

> "De memoire, je crois qu'on avait fait X..."

La premiere formulation permet au lecteur de verifier. La seconde dilue la
confiance dans tout ce que dit l'agent.

## 8. Signaux de derive a remonter

Si un agent constate un des signaux suivants, il doit le mentionner dans
la reponse utilisateur plutot que de l'ignorer:

- Les resultats de search_memory sont **tous** en dessous de score 0.25
- Les resultats citent des fichiers qui n'existent plus
- Le repo `sources.yml` ne contient pas un repo que l'agent aurait du
  pouvoir interroger
- Le dernier run visible dans `memory_runs` est plus vieux que 24h

Ces signaux indiquent un probleme pipeline qui depasse la session en cours
et meritent une action dediee.

## 9. Resume pour l'agent presse

- **Sujet historique** → `search_memory.py` avant de repondre
- **Produit quelque chose d'important** → REX markdown dans `docs/`
- **Cite un fait** → donner le chemin du fichier source
- **Ne pas** ecrire dans Qdrant directement
- **Ne pas** inventer si la memoire ne sait pas
- **Ne pas** modifier ou supprimer des points existants

Pour tout probleme pipeline, voir `docs/runbooks/AI-MEMORY-OPERATIONS.md`.
