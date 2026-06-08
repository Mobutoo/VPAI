# Manifeste de Création de Projet — placement workspace + ingestion Qdrant

**Statut** : source canonique de la procédure de placement physique d'un nouveau repo dans `~/work/` et de sa déclaration pour l'ingestion `memory_v2` (Qdrant).
**Origine** : gap déclaré dans `MEMORY-TAXONOMY-MANIFEST.md` (« Le layout physique `~/work/` (reorg M1) est documenté à part (Plan B) ») — jamais écrit jusqu'ici. Ce fichier **est** ce Plan B.
**Portée** : OÙ ranger le repo, COMMENT le nommer, COMMENT le déclarer pour qu'il soit ingéré. La taxonomie (wing/room/doc_kind, dérivation) reste dans `MEMORY-TAXONOMY-MANIFEST.md` — ce manifeste la référence, ne la duplique pas.
**Appliqué par Claude** : au moment de la création d'un nouveau projet (`gsd-new-project` Intake, App Factory étape « repo GitHub », ou scaffold manuel). Étape obligatoire AVANT le premier commit du nouveau repo.

> **Règle d'or** : le **placement physique** `~/work/<wing>/<name>/` est l'invariant durable. Quand l'auto-découverte sera shippée (spec `docs/superpowers/specs/2026-06-05-memory-worker-repo-autodiscovery-design.md`, **non déployée à ce jour**), le `wing` se dérivera du dossier parent et la déclaration manuelle disparaîtra. Bien placer le repo aujourd'hui = ingestion correcte aujourd'hui (déclaration manuelle) ET demain (auto-découverte sans effort).

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

L'ingestion ne prend que des **dépôts git** (`kind: git_repo`, `require_git`). Un dossier sans `.git` n'est jamais une source. → `git init` (puis remote `git@github-seko:Mobutoo/<name>.git` si publié) avant déclaration.

## 4. Déclaration pour l'ingestion (auto-découverte NON shippée → manuelle obligatoire)

L'auto-découverte n'est pas déployée (`roles/llamaindex-memory-worker/defaults/main.yml` n'a que `memory_worker_sources` statique, aucun bloc `discovery`). **Tant qu'elle ne l'est pas, déclarer le repo à la main.**

### 4.1 Source de vérité unique = Ansible defaults

Déclarer dans **`roles/llamaindex-memory-worker/defaults/main.yml`** → liste `memory_worker_sources`. Le redeploy rend `sources.yml`. **Champs obligatoires** :

```yaml
  - name: "<name>"          # = basename = payload repo (cf §2)
    wing: "<wing>"          # OBLIGATOIRE — infra|saas|tools|refdocs
    kind: "git_repo"
    root: "{{ workstation_projects_dir }}/<wing>/<name>"
    tags:
      - "scope:<name>"      # + "kind:official-docs" si refdocs
```

> **`wing` n'est jamais facultatif.** Le worker déployé (`index.py.j2` → `memory_core.build_payload`) fait `assert wing, "wing ne peut pas être nul"`. Une source sans `wing` **fait crasher l'ingestion** de tout le repo.

### 4.2 Interdit absolu : hand-edit du live

**NE JAMAIS** éditer à la main `/opt/workstation/configs/ai-memory-worker/sources.yml`. C'est un fichier **rendu** par Ansible. L'éditer à la main crée la dérive defaults↔live (et c'est précisément ainsi que le `wing` a disparu de la live, cassant l'invariant §4.1). Toujours : éditer `defaults/main.yml` → redeploy → la live est régénérée.

### 4.3 Parité rebuild GPU (si remote git-clonable)

Si le repo a un remote git clonable et doit être inclus au prochain rebuild bulk GPU, l'ajouter aussi à **`scripts/memory/gpu_ingest/sources.pod.yml`** avec **`name` + `wing` identiques** (le `root` y est le chemin de staging `/staging/<name>`). Parité stricte name/wing exigée : un décalage fait diverger `relative_path` → `node_id` → doublons dans Qdrant. Repos local-only (pas de remote) → indexés en incrémental par le worker Waza uniquement, **pas** dans `sources.pod.yml`.

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

- [ ] **Wing choisi** selon §1 (ingestion voulue ⇒ infra|saas|tools|refdocs)
- [ ] **Nom validé unique** via le `ls | grep -ix` du §2
- [ ] **Dossier créé** : `mkdir -p /home/mobuone/work/<wing>/<name>` + `git init`
- [ ] **Déclaré** dans `roles/llamaindex-memory-worker/defaults/main.yml` (`name`, `wing`, `kind: git_repo`, `root`, `tags`) — §4.1
- [ ] **`wing` non nul** vérifié — §4.1
- [ ] **`sources.pod.yml`** mis à jour SI remote git-clonable, parité name+wing — §4.3
- [ ] **Live JAMAIS hand-edité** — §4.2
- [ ] **Arbo docs/** conforme §5 pour les premiers fichiers
- [ ] Redeploy worker (gate humain) → la live `sources.yml` régénérée inclut la nouvelle source

## 7. Liens

- `docs/runbooks/MEMORY-TAXONOMY-MANIFEST.md` — modèle wing/room/doc_kind + dérivation (référencé, non dupliqué)
- `docs/superpowers/specs/2026-06-05-memory-worker-repo-autodiscovery-design.md` — auto-découverte (future ; rendra §4 obsolète)
- `docs/standards/AI-PLATFORM-STARTER-KIT.md` — structure INTERNE d'un repo (orthogonal : ce manifeste = placement EXTERNE dans `~/work/`)
- `scripts/memory/memory_core.py` — `resolve_source` / `build_payload` (autorité du contrat repo/wing/relative_path)
- `roles/llamaindex-memory-worker/defaults/main.yml` — `memory_worker_sources` (source de vérité déclaration)
