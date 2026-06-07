# Handoff — Refonte mémoire (memory-worker + Qdrant) — reprise nouvelle session

**Date** : 2026-06-05
**Pourquoi ce doc** : session de brainstorming devenue trop lourde. Reprendre ici à froid.
**Contrainte dure (verbatim user)** : « Quoiqu'il arrive on ne déploie rien avant la semaine prochaine. » → tout ce qui suit = design only, zéro deploy.

---

## 1. Ce qu'on est en train de faire

Refonte **complète** du système mémoire. Pas un patch — repartir des bases.
Demande user (verbatim) :
> « repartir à 0. De vider Qdrant, d'inspecter tous les repos locaux afin d'extraire tous les REX, Docs, etc. et de bien tout réorganiser pour recommencer une ingestion cohérente. Il faut reposer les bases de ce projet. La gestion de la mémoire doit être faite comme ce que l'on a étudié pour fantrad (le système de RAG avancé). »

Ambition confirmée **en deux temps** : **P1 pragmatique → P2 complet**.

On est en phase **brainstorming** (skill superpowers:brainstorming). Pas encore de spec écrite.
Cible spec : `docs/superpowers/specs/2026-06-05-memory-system-rebuild-design.md` (À CRÉER).

---

## 2. Décisions déjà ACQUISES (ne pas re-débattre)

| # | Décision | Source |
|---|---|---|
| D1 | **Rooms = topics au 1er niveau DANS une seule collection** (payload taxonomy), PAS une collection par room. | Correction explicite user |
| D2 | Modèle = MemPalace fantrad : **Wings (domaines) → Rooms (catégories) → Drawers (unités verbatim)** en champs de payload. | fantrad PRD §10-11 |
| D3 | Phasé **P1 pragmatique / P2 complet**. | user |
| D4 | **Réorganiser les repos sur Waza** pour une logique évolutive (déplacer/ranger). Cohérence validée par user. | user |
| D5 | Ingestion lourde → s'appuyer sur le **harness RunPod serverless de fantrad** pour un rebuild bulk rapide (pod GPU) vs ~8h sur Waza. | user + étude fantrad |
| D6 | **Coupling critique** : modèle d'embedding à l'index DOIT == modèle à la query. La query tourne sur **Waza CPU, offline**. → un seul modèle unifié, assez petit pour le CPU Pi. | analyse |
| D7 | Docs officielles = **facette dans memory_v1** (Path 1), pas une collection par doc. Markdown-only, racine dédiée `/home/mobuone/refdocs/<tech>-docs/` (PAS sous DOCS/.git). | `docs/runbooks/DOCS-OFFICIAL-DOCS-TO-MIRROR-2026-06-05.md` |

---

## 3. Questions OUVERTES (reprendre ici)

Dernière question posée au user, **SANS RÉPONSE** :
> Le **pod GPU d'ingestion**, on le met en **P1** (le rebuild se fait directement sur pod) ou en **P2** (P1 = un rebuild lent accepté une fois sur Waza, on ajoute le pod ensuite) ?

Restent aussi à trancher AVANT d'écrire la spec :
- **(a)** Modèle d'embedding unifié. Reco actuelle = **Option A, modèle 768d** (`e5-base` ou `embeddinggemma-300m`) : assez petit pour query CPU Waza, GPU accélère juste le bulk. À confirmer.
- **(b)** Taxonomie **Wings/Rooms** concrète pour la base code+docs+REX (lister les wings : ex. `infra`, `saas`, `refdocs`, `ops/rex`… et les rooms par wing).
- **(c)** **Périmètre du wipe Qdrant** (cf §4 inventaire) : confirmer ce qu'on supprime vs ce qu'on épargne.
- **(d)** **Layout cible de la réorg repos** (proposé : `/home/mobuone/work/{infra,saas,tools,refdocs}` — à valider).

---

## 4. Inventaire Qdrant (FAIT cette session)

Constat (vérifié sur le live) :
- ~30 collections façon "ailes/rooms" ad-hoc. Docs officielles suivent déjà un pattern **1 collection par outil** (`comfyui-docs`, `zitadel-docs`, `kitsu-docs`, `netbird-docs`) peuplées par scripts ad-hoc (`scripts/index-comfyui-docs.py`).
- **Fragmentation embeddings** : `memory_v1`=768 (embeddinggemma-300m), comfyui/kitsu=1536, zitadel/netbird=384 → **pas de recherche transversale cohérente**.
- **`memory_v1` n'a AUCUN payload index** → filtres `--repo/--topic/--doc-kind` = scan complet (lent). ← créer les indexes (`namespace`, `doc_kind`, `tags`, `topic`) est l'action la plus rentable et indépendante.
- Les REX VPAI sont éclatés sur `memory_v1` / `vpai_rex` / `operational-rex` avec 768/1536/384 → incohérent.

**Périmètre wipe proposé** (à confirmer — point (c)) :
- **Supprimer / refondre** : `memory_v1`, `mop_kb`, `vpai_rex`, `operational-rex`, `rex_lessons`, `dev-knowledge`, `content_index`, + 7 `*-docs` fragmentées.
- **Épargner** : `semantic_cache` (245 563 pts), `jarvis-*`, `flash-*`, `zimboo`, `macgyver`, `app-factory`.

---

## 5. Étude RAG — ce qu'on réutilise

### fantrad (le « RAG avancé » cité par le user) — `/home/mobuone/projects/saas/fantrad`
- Taxonomie **wing/room/drawer**, **VERBATIM**, **APPEND-ONLY** (`valid_to`), **ENTITY-FIRST**, **RETRIEVAL SCOPÉ**, boosts (humain ×1.5, temporel ×1.2). → c'est le modèle conceptuel cible (D2).
- Mais **sous-implémenté** : rerank/backcheck/hybrid désactivés. Embedding = `fastembed e5-base` 768 **CPU** (`services/scheduler/main.py`). RunPod GPU = **uniquement pour le LLM 70B**, pas l'embedding.
- Harness serverless réutilisable : `services/llama-worker/handler.py` (`runpod.serverless.start`), `README-DEPLOY.md` (network volume `/runpod-volume`, création endpoint GraphQL, `RUNPOD_API_KEY`/`VOLUME_ID`/`ENDPOINT_ID`). PRD §10-11 = MemPalace. Voir aussi `AMELIORATIONS-FANTRAD-2026.md`.

### story-engine (version RAG la plus évoluée côté ingénierie) — `saas/story-engine`
- `mind_states` : 8 dimensions mentales, `te3-small` **1536 via LiteLLM**, **payload lean** (UUIDs seuls, texte en Postgres).
- **Retrieval progressif L0→L3** avec dégradation gracieuse. **Dirty-bit debounce** (anti-cascade). **Staleness flag**. Graphe **blast-radius / god-nodes**.
- Fichiers : `apps/api/src/story_engine/services/{mind_state_builder,qdrant,embeddings,scene_context_v2}.py`, `.planning/research/ARCHITECTURE.md`.
- À reprendre : les **patterns d'ingénierie** (lean payload + texte hors-vecteur, retrieval étagé, debounce, staleness), pas le domaine (esprits de perso).

**Synthèse cible** : taxonomie conceptuelle fantrad (wing/room/drawer, verbatim, append-only, scoped) + patterns d'ingénierie story-engine (lean payload, L0-L3, debounce/staleness) + un seul modèle d'embedding unifié.

---

## 6. État du worker actuel (ce qui tourne)

- Rôle : `roles/llamaindex-memory-worker/`. Déployé : `/opt/workstation/ai-memory-worker/index.py` (source `templates/index.py.j2`).
- Embedding : `google/embeddinggemma-300m` 768d. Chunking markdown-section/llama-sentence, chunk 1600 / overlap 200 / max 200.
- Collection : `memory_v1`. Config : `/opt/workstation/configs/ai-memory-worker/config.yml` + `sources.yml` (live).
- **Sources réconciliées 2→9** cette session (`defaults/main.yml` `memory_worker_sources`) : VPAI, flash-studio, story-engine, typebot-docs, DOCS, podpilot, hawkeye, fantrad, riposte. Commit `7f3b9c2`.
- **Auto-découverte des repos** : design écrit `docs/superpowers/specs/2026-06-05-memory-worker-repo-autodiscovery-design.md` (bloc `discovery` + `prune_nested` + `--list-sources` + `max_repos`). Commit `2a2d970`. **Pas implémenté.**
- Recherche : protocole `docs/runbooks/AI-MEMORY-AGENT-PROTOCOL.md` (`search_memory.py`). Seul le worker écrit dans `memory_v1`.

> ⚠️ La refonte (§1) **supplante** potentiellement le schéma actuel. L'auto-découverte et la réorg repos sont des briques de P1.

---

## 7. Prochaines étapes (ordre)

1. **Reprendre le brainstorming** : faire répondre le user aux 4 questions ouvertes §3 (a/b/c/d) + la question P1/P2 du pod GPU.
2. Présenter le **design phasé complet** (P1 pragmatique / P2 complet) pour validation.
3. Écrire la spec → `docs/superpowers/specs/2026-06-05-memory-system-rebuild-design.md`.
4. Boucle `spec-document-reviewer`, review user.
5. `superpowers:writing-plans` → plan exécutable. **Zéro deploy avant semaine prochaine.**

## 8. Fichiers de référence

- `docs/runbooks/DOCS-OFFICIAL-DOCS-TO-MIRROR-2026-06-05.md` — Tier1/2 docs + décision Path 1 (facette memory_v1). **Non commité.**
- `docs/superpowers/specs/2026-06-05-memory-worker-repo-autodiscovery-design.md` — auto-découverte (commité).
- `.planning/notes/2026-06-05-memory-bot-handoff.md` — handoff précédent (bot Telegram @EkengeBot, désormais armé/E2E OK).
- Mémoires liées : `project_memory_worker_control.md`, `project_r0_continu.md`, `project_loi_system_bricks.md` (index `MEMORY.md`).
- Transcript complet de la session lourde : `/home/mobuone/.claude/projects/-home-mobuone-VPAI/0a3fadbd-88bb-412f-b8da-91c0767d3e46.jsonl`
