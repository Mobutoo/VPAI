# Manifeste de Création de Projet — placement workspace + ingestion Qdrant

**Statut** : source canonique de la procédure de placement physique d'un nouveau repo dans `~/work/` et de sa déclaration pour l'ingestion `memory_v2` (Qdrant).
**Origine** : gap déclaré dans `MEMORY-TAXONOMY-MANIFEST.md` (« Le layout physique `~/work/` (reorg M1) est documenté à part (Plan B) ») — jamais écrit jusqu'ici. Ce fichier **est** ce Plan B.
**Portée** : OÙ ranger le repo, COMMENT le nommer, COMMENT le déclarer pour qu'il soit ingéré. La taxonomie (wing/room/doc_kind, dérivation) reste dans `MEMORY-TAXONOMY-MANIFEST.md` — ce manifeste la référence, ne la duplique pas.
**Appliqué par Claude** : au moment de la création d'un nouveau projet (`gsd-new-project` Intake, App Factory étape « repo GitHub », ou scaffold manuel). Étape obligatoire AVANT le premier commit du nouveau repo.

> **Règle d'or** : le **placement physique** `~/work/<wing>/<name>/` est le SEUL geste requis. L'auto-découverte est **LIVE depuis 2026-06-08** (déployée sur waza, `discovery.enabled: true`) : le worker scanne `~/work/{infra,saas,tools,refdocs}/*`, dérive `wing` du dossier parent et `name`=basename, et indexe tout repo git — **sans aucune déclaration manuelle**. Poser le repo au bon endroit + `git init` suffit.

---

## 1. Nomenclature physique

```
/home/mobuone/work/<wing>/<name>/
```

| Wing | Ingéré ? | Sens | Exemples |
|------|----------|------|----------|
| **infra** | ✅ | Ansible, déploiement, ops self-hosted | VPAI |
| **saas** | ✅ | Produits SaaS (room = concern interne) | flash-studio, story-engine, hawkeye, fantrad, riposte, podpilot |
| **tools** | ✅ | Outillage transverse, CLI, scripts isolés | jarvis, macgyver, mission-control-tui |
| **refdocs** | ✅ | Docs officielles tierces (`doc_kind=official-docs`) | DOCS, typebot-docs |
| **ops** | ❌ | REX/runbooks workspace hors repo | ops/rex |
| **writing** | ❌ | Contenu créatif | — |

**Frontière dure** : un projet dont on VEUT l'ingestion mémoire **doit** vivre sous `infra/`, `saas/`, `tools/` ou `refdocs/`. Le placer sous `ops/` ou `writing/` = jamais indexé (par design). Le wing détermine la dérivation `room` (cf `MEMORY-TAXONOMY-MANIFEST.md` §3) — choisir le mauvais wing produit des rooms incohérents.

## 2. Nom du repo (`<name>` = basename)

`<name>` (basename du dossier) devient le payload Qdrant `repo` — **la clé de filtre `--repo` / `repo:`**. Donc :

| Règle | Pourquoi |
|-------|----------|
| **kebab-case**, minuscule | cohérence des filtres (`--repo story-engine`) |
| **unique sur TOUS les wings** | collision de basename → « premier gagne + WARN », le 2ᵉ devient un shadow muet (déjà un `saas/vps` existe — vérifier avant de nommer) |
| **stable** (ne pas renommer) | `repo` est embarqué dans chaque payload + `ref_doc_id`/`node_id` ; renommer = ré-indexation forcée |
| refdocs : **pas** de logique de room dans le nom | le room refdocs se dérive du 1ᵉʳ segment de chemin (`n8n-docs/…`→`n8n`) ; pour `DOCS` multi-techno, garder l'arbo interne `<techno>-docs/` |

**Vérif unicité (obligatoire avant de nommer)** :
```bash
ls -1d /home/mobuone/work/{infra,saas,tools,refdocs}/* | xargs -n1 basename | sort | grep -ix "<name>"
# zéro ligne = OK ; une ligne = collision, choisir un autre nom
```

## 3. git init obligatoire

L'ingestion ne prend que des **dépôts git** (`require_git`). Un dossier sans `.git` n'est **jamais** indexé. → `git init` (puis remote `git@github-seko:Mobutoo/<name>.git` si publié). C'est le seul acte requis en plus du placement : dès que `~/work/<wing>/<name>/.git` existe, l'auto-découverte l'indexe au prochain run du worker.

## 4. Ingestion = AUTOMATIQUE (auto-découverte LIVE depuis 2026-06-08)

**Aucune déclaration manuelle.** Le worker (`discovery.enabled: true` dans `config.yml`) dérive les sources de l'arborescence : `memory_core.discover_sources()` scanne `~/work/{infra,saas,tools,refdocs}/*`, prend tout enfant direct avec `.git`, dérive `wing`=dossier parent + `name`=basename, tags `scope:{name}` (+`kind:official-docs` si refdocs). Vérifier ce que le worker voit :

```bash
cd /opt/workstation/ai-memory-worker
.venv/bin/python index.py --config /opt/workstation/configs/ai-memory-worker/config.yml --list-sources
# imprime le set effectif (mode discovery, count, wings) SANS indexer — ni modèle ni Qdrant
```

### 4.1 Exclure ou surcharger (rare)

- **Ne PAS indexer un repo** présent sous un wing : ajouter son basename à `memory_worker_discovery.exclude_names` (ou un glob dans `exclude_globs`) dans `roles/llamaindex-memory-worker/defaults/main.yml`, puis redeploy (`make deploy-memory-worker`).
- **Tags non-standards / root hors arborescence** : `memory_worker_sources_manual` (prioritaire sur la découverte par `name`).
- **Garde-fou coût** : `max_repos: 30` (abort si dépassé, pas de troncature silencieuse). 20 repos au 2026-06-08.

### 4.2 Interdit absolu : hand-edit du live

**NE JAMAIS** éditer à la main `/opt/workstation/configs/ai-memory-worker/{config.yml,sources.yml}` — fichiers **rendus** par Ansible. Tout passe par `defaults/main.yml` → `make deploy-memory-worker`. Le hand-edit = la dérive defaults↔live (cause historique de la disparition du champ `wing`).

### 4.3 Parité rebuild GPU (si remote git-clonable)

L'auto-découverte concerne le worker incrémental waza. Pour inclure un repo au prochain **rebuild bulk GPU**, l'ajouter à **`scripts/memory/gpu_ingest/sources.pod.yml`** avec `name` + `wing` identiques (root = `/staging/<name>`). Décalage name/wing → `relative_path`→`node_id` divergent → doublons Qdrant. Repos local-only (sans remote) : worker waza uniquement, **pas** dans `sources.pod.yml`.

## 5. Conventions intra-repo (pour une dérivation `room`/`doc_kind` correcte)

Le `room` et le `doc_kind` se **dérivent du chemin** (`classify_room` / `classify_doc_kind`, cf `MEMORY-TAXONOMY-MANIFEST.md` §3-4). Pour que la dérivation soit propre, respecter l'arbo :

| Type de fichier | Chemin | Dérive vers |
|---|---|---|
| REX | `docs/rex/REX-*.md` | `doc_kind: rex` |
| Spec | `docs/superpowers/specs/*.md` ou `docs/specs/*.md` | `doc_kind: spec` |
| Audit | `docs/audits/*.md` | `doc_kind: audit` |
| Runbook | `docs/runbooks/*.md` | `doc_kind: runbook` |
| Planning | `.planning/**` | `doc_kind: doc` |
| Rôle Ansible (infra) | `roles/<x>/**` | `room` dérivé du rôle (caddy→`caddy-vpn`, postgres→`postgres`…) |

**Anti-patterns** :
- **`.git` imbriqué** : ne pas nicher un sous-projet avec son propre `.git` dans un repo déclaré (ex. `flash-infra` dans `flash-studio`). Soit il est couvert comme **sous-dossier** (pas de `.git`), soit c'est une source autonome déclarée — jamais les deux (double-comptage).
- Artefacts lourds/captures à la racine : exclus de toute façon (`node_modules`, `dist`, `.venv`, `.playwright-mcp`, `coverage` filtrés), mais à ne pas committer.
- Extensions hors `include_extensions` (cf `config.yml`) : non indexées (binaires, images).

## 6. Checklist exécutable (Claude, à la création)

- [ ] **Wing choisi** selon §1 (ingestion voulue ⇒ infra|saas|tools|refdocs ; jamais ops/writing)
- [ ] **Nom validé unique** via le `ls | grep -ix` du §2 (collision cross-wing = shadow muet)
- [ ] **Dossier créé** : `mkdir -p /home/mobuone/work/<wing>/<name>` + **`git init`** (sans `.git`, jamais indexé)
- [ ] **Arbo docs/** conforme §5 pour les premiers fichiers (dérivation room/doc_kind)
- [ ] (rien à déclarer) — l'auto-découverte indexe au prochain run du worker. Vérifier via `index.py --list-sources` (§4)
- [ ] **`sources.pod.yml`** mis à jour SEULEMENT si remote git-clonable + inclusion rebuild GPU voulue — §4.3
- [ ] **Live JAMAIS hand-edité** — §4.2

## 7. Liens

- `docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md` — modèle wing/room/doc_kind + dérivation (référencé, non dupliqué)
- `docs/superpowers/specs/2026-06-05-memory-worker-repo-autodiscovery-design.md` — spec auto-découverte (implémentée + LIVE 2026-06-08, raffinée wing-keyée)
- `docs/standards/AI-PLATFORM-STARTER-KIT.md` — structure INTERNE d'un repo (orthogonal : ce manifeste = placement EXTERNE dans `~/work/`)
- `scripts/memory/memory_core.py` — `discover_sources` / `resolve_effective_sources` / `resolve_source` / `build_payload` (autorité du contrat repo/wing/relative_path)
- `roles/llamaindex-memory-worker/defaults/main.yml` — `memory_worker_discovery` (workspace_root, wings, exclude_names, max_repos) + `memory_worker_sources_manual`
