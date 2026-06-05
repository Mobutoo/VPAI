# Spec — Refonte mémoire (memory-worker + Qdrant)

**Date** : 2026-06-05
**Statut** : design validé (brainstorming), prêt pour writing-plans
**Origine** : `.planning/notes/2026-06-05-memory-system-rebuild-handoff.md`
**Demande user (verbatim)** : « repartir à 0. De vider Qdrant, d'inspecter tous les repos locaux afin d'extraire tous les REX, Docs, etc. et de bien tout réorganiser pour recommencer une ingestion cohérente. La gestion de la mémoire doit être faite comme ce que l'on a étudié pour fantrad (le système de RAG avancé). »
**Timing** : contrainte « rien avant semaine prochaine » **levée 2026-06-05** → exécution autorisée dès ce soir.

---

## 1. Objectif

Reconstruire le système mémoire de zéro : Qdrant cohérent (un modèle d'embedding, une collection, indexes de payload), repos Waza réorganisés en layout évolutif, ingestion bulk rapide via pod GPU, retrieval scopé offline sur Waza CPU. Modèle conceptuel = MemPalace fantrad (wing/room/drawer, verbatim, append-only) + patterns d'ingénierie story-engine (lean payload, retrieval étagé L0-L3, debounce/staleness). Un manifeste garantit que les sessions futures respectent l'organisation.

Phasage : **P1 pragmatique** (mémoire utilisable, ingestion GPU, retrieval scopé) → **P2 complet** (reranker, hybrid, backcheck, boosts).

## 2. Décisions actées (ne pas rejouer)

| # | Décision | Source |
|---|----------|--------|
| D1 | Rooms = topics 1er niveau **dans une seule collection** (payload taxonomy), pas 1 collection/room. | user |
| D2 | Modèle MemPalace fantrad : **Wings → Rooms → Drawers** en champs de payload, verbatim, append-only. | fantrad PRD §10-11 |
| D3 | Phasé **P1 pragmatique / P2 complet**. | user |
| D4 | **Réorg physique des repos** sur Waza en layout évolutif (hard-move, symlinks rejetés). | user |
| D5 | Ingestion bulk **GPU dès P1** : **pod RunPod on-demand fixe** (pas serverless — batch one-shot), embed sur GPU, **upsert direct** dans Qdrant via **clé Headscale éphémère**, puis terminate + révoque. | user 2026-06-05 |
| D6 | **Coupling critique** : modèle d'embedding à l'index == à la query. Query tourne **Waza CPU offline**. | analyse |
| D7 | Docs officielles = **facette dans la collection** (wing `refdocs`), markdown-only, racine `~/work/refdocs/<tech>-docs/`. | `docs/runbooks/DOCS-OFFICIAL-DOCS-TO-MIRROR-2026-06-05.md` |
| D8 | Embedding unifié = **`google/embeddinggemma-300m` 768d** (continuité, CPU-viable, zéro migration dim). | session 2026-06-05 |
| D9 | Wipe = **périmètre mémoire/RAG only** (apps épargnées). | session 2026-06-05 |
| D10 | Layout cible = **`~/work/{infra,saas,tools,refdocs}`**. | session 2026-06-05 |
| D11 | saas rooms **par concern** (projet dans champ `repo`). | session 2026-06-05 |
| D12 | REX/audit/incident/runbook = **facette `doc_kind`** (pas un wing). | session 2026-06-05 |
| D13 | Reranker = **P2, contraint CPU-offline** Waza. | session 2026-06-05 |
| D14 | **Cap mémoire obligatoire** sur tout process Waza (worker, embed, retrieval). Le worker non-borné a OOM le Pi → networkd affamé → bail DHCP perdu → SSH/Tailscale down. | `project_waza_ssh_dhcp_oom_2026_06_05.md` |

## 3. Modèle de données

### Collection & hébergement
`memory_v2` (nouvelle, 768d, distance cosine). Remplace `memory_v1`.
**Hôte** : instance Qdrant **prod sur Sese-AI**, exposée `qd.ewutelo.cloud:443` derrière Caddy **VPN-only (Tailscale) + API key** (`roles/caddy/templates/Caddyfile.j2` route `import vpn_only`, `roles/llamaindex-memory-worker/defaults/main.yml` `memory_worker_qdrant_url`). Le worker Waza y écrit déjà par-dessus le VPN. Précision D6 : « offline » = embedding **calculé en local CPU Waza** ; le lookup Qdrant est un appel **VPN vers Sese**, pas un air-gap.

### Payload du drawer (unité verbatim, append-only)

| Champ | Type | Rôle |
|-------|------|------|
| `wing` | keyword | infra / saas / tools / refdocs |
| `room` | keyword | catégorie dans le wing (cf §4) |
| `doc_kind` | keyword | rex / doc / config / code / audit / runbook / spec / official-docs |
| `repo` | keyword | nom du repo source (ex. fantrad, story-engine, VPAI) |
| `relative_path` | keyword | chemin relatif dans le repo |
| `topic` | keyword | sujet dérivé (titre section) |
| `tags` | keyword[] | tags libres |
| `valid_from` | datetime | début de validité |
| `valid_to` | datetime\|null | null = drawer vivant ; daté = supplanté (append-only) |
| `text` | text | contenu verbatim du chunk |
| (vecteur) | 768d | embedding embeddinggemma-300m |

### Indexes Qdrant (action la plus rentable, cf handoff §4)
Payload indexes sur : `wing`, `room`, `doc_kind`, `repo`, `topic`, `tags`. Sans eux, les filtres = scan complet.

## 4. Taxonomie Wings → Rooms

Principe : **Wing = origine physique/domaine**, **Room = catégorie**, **`doc_kind` = facette orthogonale** filtrable dans tout wing (résout la fragmentation REX `memory_v1`/`vpai_rex`/`operational-rex` du handoff §4).

| Wing | Source physique | Rooms |
|------|-----------------|-------|
| **infra** | `~/work/infra/VPAI` | `ansible-roles`, `deploy`, `troubleshooting`, `caddy-vpn`, `docker`, `postgres`, `monitoring`, `n8n` |
| **saas** | `~/work/saas/*` | `rag`, `api`, `frontend`, `pipeline`, `prd-arch` (room = concern ; projet dans `repo`) |
| **tools** | `~/work/tools/*` | `n8n-workflows`, `scripts`, `mcp`, `cli` |
| **refdocs** | `~/work/refdocs/<tech>-docs` | 1 room/tech : `n8n`, `litellm`, `typebot`, `comfyui`, `kitsu`, `zitadel`, `netbird`, … (`doc_kind=official-docs`) |

## 4b. Contrainte transversale — cap mémoire Waza (D14)

Le memory-worker actuel **tourne sans cap** : il a saturé la RAM du Pi → `systemd-networkd` affamé → bail DHCP `eth0` perdu → `tailscale ENETUNREACH` → SSH down (réf `project_waza_ssh_dhcp_oom_2026_06_05.md`). Le worker est **stoppé** suite à cet incident. Conséquences pour la refonte :

- **Tout process Waza** (worker re-ingestion incrémentale, retrieval `search_memory.py`, embed CPU) DOIT avoir un cap mémoire (`MemoryMax`/`MemoryHigh` systemd ou `mem_limit` Docker). Sibling de la mémoire incident : fix B (caps + OOM-shield + watchdog réseau) est en Ansible **mais pas déployé** → à intégrer/réutiliser, pas réinventer.
- **Renforce le choix GPU pod (M3)** : l'embed bulk de tout le corpus sur Waza CPU est précisément la charge qui a OOM le Pi. Le pod GPU sort cette charge de Waza → le fallback « embed CPU Waza » (M3) reste un dernier recours **borné** (cap + batch petit), pas le défaut.

## 5. P1 — modules indépendamment testables

### M1 — Réorg repos (orthogonal au modèle mémoire, blast radius le plus large)
Hard-move vers `~/work/{infra,saas,tools,refdocs}`. Auto-découverte (spec existante `docs/superpowers/specs/2026-06-05-memory-worker-repo-autodiscovery-design.md`) scanne `~/work/*`.

**Checklist de migration — dépendances de chemin à mettre à jour** (toute omission casse un outil) :

| Dépendance | Chemin actuel | Action |
|------------|---------------|--------|
| Ansible venv | `/home/mobuone/VPAI/.venv` | **Recréer** au nouvel emplacement (paths absolus hardcodés ⇒ ne pas `mv`) : `python -m venv` + `pip install -r requirements.txt` |
| Worker sources | `sources.yml` (paths absolus) | Réécrire vers `~/work/*` |
| MCP filesystem root | `/home/mobuone/projects` | Mettre à jour `.mcp.json` |
| search_memory.py | paths sources | Aligner sur `~/work/*` |
| CLAUDE.md (global + projet) | venv, SSH, workspace | Mettre à jour les chemins |
| Pointeurs worker | `/opt/workstation/configs/ai-memory-worker/*`, `/opt/workstation/ai-memory-worker/*` | Mettre à jour |
| settings Claude Code | `.claude/settings*` | Vérifier paths |

**Séquençage self-refactor (la session tourne dans `/home/mobuone/VPAI`)** :
Le harness re-`cd` dans le CWD à chaque appel Bash → déplacer VPAI **en cours de session brique la session**.
1. Déplacer d'abord **saas/tools/refdocs** (pas le CWD) + créer `~/work`, update toutes les refs.
2. **Étape terminale** : `mv ~/VPAI ~/work/infra/VPAI`, recréer `.venv`, finaliser updates, puis **redémarrer Claude Code depuis `~/work/infra/VPAI`**.

### M2 — Schéma + taxonomie + indexes Qdrant (cœur, indépendant)
- Créer `memory_v2` (768d cosine) + les 6 payload indexes (§3).
- **Wipe (D9)** : périmètre mémoire/RAG only — `memory_v1`, `mop_kb`, `vpai_rex`, `operational-rex`, `rex_lessons`, `dev-knowledge`, `content_index`, les `*-docs` fragmentées, et `semantic_cache` (régénéré seul par LiteLLM). **Épargner** : `jarvis-*`, `flash-*`, `zimboo`, `macgyver`, `app-factory` (données runtime d'apps, non ré-ingérables depuis local).
- **Pré-check** : vérifier qu'un drop de `semantic_cache` ne crashe pas LiteLLM avant qu'il recrée la collection.
- **Snapshot pré-wipe** (assurance) : snapshot Qdrant des collections supprimées avant drop (rollback possible). Défendable de skip vu la logique « mémoire ré-ingérable depuis local », mais one-shot peu coûteux pour un « repartir à 0 » irréversible.

### M3 — Ingestion GPU (P1)
**Topologie (verrouillée 2026-06-05)** : **pod RunPod on-demand fixe**, pas serverless.
Raison : la mission est un **batch one-shot** (rebuild complet, puis ré-ingestions ponctuelles), pas du per-request continu. Le serverless fantrad est taillé pour le LLM 70B bursty (cold-start recharge le modèle, limites de durée) → inadapté à un embed de corpus complet.

**Flux** :
1. **Staging corpus** : Waza synchronise le corpus source (markdown/code de `~/work/*`) vers le **network-volume `/runpod-volume`** avant le run. Le volume sert au **staging du corpus en entrée + cache des poids du modèle** — **PAS** au chemin de sortie (la sortie = upsert direct, step 4).
2. Louer un pod GPU on-demand, monter `/runpod-volume`.
3. Pod **rejoint Headscale** via **clé pre-auth éphémère** (auto-remove à la mort du pod + révocation manuelle après).
4. Embed les chunks sur GPU avec `embeddinggemma-300m`.
5. **Upsert direct** dans `qd.ewutelo.cloud` (`memory_v2`) **par-dessus le VPN** (un seul saut, pas d'artefact vecteurs à transférer en retour).
6. **Terminate** le pod → clé révoquée. Surface VPN temporaire et contrôlée.

⚠️ **Embedding net-new, pas une réutilisation** : le RunPod de fantrad sert le **LLM 70B uniquement** ; son embedding est `fastembed e5-base` **CPU** (`services/scheduler/main.py`). On écrit un **batch GPU `embeddinggemma-300m`** (pas un handler serverless). Réutilisable de fantrad : mécanique network-volume `/runpod-volume`, création/gestion endpoint, `RUNPOD_API_KEY`/`VOLUME_ID` (`README-DEPLOY.md`) — **pas** le payload d'embedding.
- Chunking : reprendre celui du worker actuel (markdown-section / llama-sentence, chunk 1600 / overlap 200).
- **Recherche à l'implémentation (R0/R8)** : valider côté doc officielle (a) clé pre-auth éphémère Headscale + ACL pour le nœud pod, (b) pod RunPod on-demand + accès réseau sortant VPN, avant codage.
- **Gate d'acceptation P1 — parité GPU↔CPU (R4 protège D6)** : même modèle, devices différents (GPU index vs CPU query). fp16/kernels peuvent décaler les vecteurs → dégradation silencieuse du retrieval. Test : embed un texte identique sur pod GPU et Waza CPU → **cosine ≈ 1.0** requis avant de valider l'ingestion bulk. **Fallback si échec** : forcer **fp32** sur le pod (élimine la dérive fp16/kernel) ; en dernier recours, repli embed CPU sur Waza (le P2-fallback de D5).

### M4 — Retrieval (Waza CPU offline)
- `search_memory.py` v2, embedding `embeddinggemma-300m` CPU (D6/D8).
- **Scoping par défaut sur `wing`/`doc_kind`** : les refdocs (100k+ chunks, même collection D1/D7) noieraient REX/mémoire en requête non scopée. Les indexes M2 sont l'enforcement.
- Patterns story-engine : retrieval étagé **L0→L3** avec dégradation gracieuse, lean payload, debounce/staleness.
- Filtres exposés : `--wing`, `--room`, `--doc-kind`, `--repo`, `--topic`, `--tags`.

### M5 — Manifeste futurs projets
Garantit que les sessions Claude futures respectent l'organisation.
- `~/work/MANIFEST.md` canonique : wings/rooms, règle « où ranger un nouveau repo / doc / REX », convention de nommage, modèle de payload mémoire.
- Section « Workspace layout » dans `~/.claude/CLAUDE.md` (global, chargé chaque session) qui pointe vers le manifeste.

## 6. P2 — RAG avancé

- **Reranker (D13)** : cross-encoder léger (ex. `bge-reranker-base` / MiniLM) **CPU-offline** Waza, sur le top-k vectoriel de M4. C'est ce qui manquait à fantrad (désactivé ⇒ « sous-implémenté »).
- **Hybrid search** (dense + sparse/BM25), **backcheck**, **boosts** (humain ×1.5, temporel ×1.2).
- **Graphe** blast-radius / god-nodes (story-engine) si justifié.

## 7. Gates d'acceptation P1

1. `memory_v2` créée + 6 indexes présents (vérifiable via Qdrant API).
2. Wipe effectué, apps épargnées intactes, LiteLLM sain après drop `semantic_cache`.
3. Parité embedding GPU↔CPU : cosine ≈ 1.0.
4. Ingestion bulk complète depuis `~/work/*` (auto-découverte).
5. `search_memory.py` v2 : requête scopée renvoie des résultats pertinents sans noyade refdocs.
6. Repos réorganisés sous `~/work/`, venv recréé, tous les outils (ansible, MCP, worker) fonctionnels post-move.
7. `~/work/MANIFEST.md` + section CLAUDE.md en place.

## 8. Risques

| Risque | Mitigation |
|--------|-----------|
| Move VPAI brique la session | VPAI en étape terminale + restart (cf M1) |
| venv déplacé = paths cassés | Recréation, pas `mv` |
| Drift vecteurs GPU vs CPU | Gate parité cosine (M3) |
| Refdocs noient la mémoire | Scoping wing/doc_kind par défaut (M4) |
| Wipe `semantic_cache` casse LiteLLM | Pré-check avant drop + snapshot (M2) |
| Perte données apps | Périmètre wipe mémoire-only strict (D9) |
| Clé Headscale fuite via pod cloud | Clé éphémère + révocation post-batch + ACL nœud restreinte (M3) |
| Qdrant VPN-only injoignable depuis pod | Pod rejoint le mesh (clé éphémère) → upsert sur VPN (M3 verrouillé) |

## 9. Fichiers de référence

- `.planning/notes/2026-06-05-memory-system-rebuild-handoff.md` — handoff source
- `docs/superpowers/specs/2026-06-05-memory-worker-repo-autodiscovery-design.md` — auto-découverte
- `docs/runbooks/DOCS-OFFICIAL-DOCS-TO-MIRROR-2026-06-05.md` — refdocs Tier1/2 + Path 1
- `docs/runbooks/AI-MEMORY-AGENT-PROTOCOL.md` — protocole recherche actuel
- fantrad `services/llama-worker/`, `README-DEPLOY.md`, PRD §10-11 — harness RunPod + MemPalace
- story-engine `apps/api/src/story_engine/services/` — patterns retrieval étagé / lean payload
