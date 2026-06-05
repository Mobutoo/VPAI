# Spec — Auto-découverte des repos pour le memory-worker

**Date** : 2026-06-05
**Statut** : design, à implémenter d'ici ~1 semaine (gate : pas de déploiement avant la semaine prochaine)
**Origine** : sources actuellement déclarées à la main dans `roles/llamaindex-memory-worker/defaults/main.yml` (`memory_worker_sources` → `sources.yml.j2`). Plusieurs repos du workspace ne sont jamais indexés faute de déclaration. Le code déployé (`index.py.j2`) n'a **aucune** logique de découverte (`os.walk` scanne *dans* un repo déclaré, `list_repo_roots`/`find_repo_root` lisent une liste statique).

## Objectif

Indexer automatiquement tout dépôt git d'un (ou plusieurs) dossier(s) racine du workspace, sans édition manuelle de `sources.yml` à chaque nouveau projet — tout en gardant un contrôle explicite (exclusions, overrides de tags, garde-fous coût).

## Non-objectifs

- Pas de découverte hors git (un répertoire sans `.git` n'est pas une source).
- Pas de scan réseau / multi-host (waza uniquement, comme aujourd'hui).
- Ne change pas le modèle push-only des run reports ni le schéma Qdrant.

## Décisions de design

### 1. Source de vérité = bloc `discovery` dans le config

Nouveau bloc dans `config.yml` (généré par Ansible), **en plus** d'une liste manuelle qui garde la priorité :

```yaml
discovery:
  enabled: true
  roots:
    - "/home/mobuone"            # scanné à plat
    - "/home/mobuone/projects/saas"
  max_depth: 2                   # profondeur de recherche de .git sous chaque root
  require_git: true              # seuls les dirs contenant .git deviennent sources
  prune_nested: true            # si un .git est trouvé, ne pas descendre chercher des .git imbriqués
  exclude_names:                 # basenames exclus (exact match)
    - ".claude"
    - ".codex"
  exclude_globs:                 # chemins exclus (fnmatch sur le path absolu)
    - "*/.worktrees/*"
    - "*/node_modules/*"
  max_repos: 30                  # garde-fou : abort si dépassé (évite explosion coût)
  default_tags_template:         # tags auto par repo découvert
    - "scope:{name}"             # {name} = basename du repo

# Sources manuelles : priorité sur la découverte (collision par `name`).
# Sert aux overrides de tags ou aux roots hors `discovery.roots`.
sources_manual:
  - name: "DOCS"
    kind: "git_repo"
    root: "/home/mobuone/DOCS"
    tags: ["kind:official-docs", "scope:wiki"]
```

`memory_worker_sources` (statique) est **conservé** mais renommé conceptuellement `sources_manual` ; il l'emporte sur les découvertes de même `name`.

### 2. Algorithme `discover_sources(config) -> list[Source]`

1. Pour chaque `root` de `discovery.roots` : `os.walk` jusqu'à `max_depth`.
2. Un dossier `D` est une source si `D/.git` existe (`require_git`).
3. Si `prune_nested` : dès qu'un `.git` est trouvé dans `D`, on ne descend pas chercher des `.git` plus profonds (évite d'indexer `flash-infra` à la fois comme partie de `flash-studio` ET comme source autonome ; idem `DOCS/n8n-docs`). **Point clé** : règle le double-comptage actuel.
4. `name = basename(D)`. Collision de `name` entre deux découvertes → garder la première + WARN log (et conseiller un override manuel).
5. Filtres : `exclude_names`, `exclude_globs`.
6. Tags = `default_tags_template` rendu avec `{name}`.
7. Merge : `sources_manual` ajoutés/écrasent par `name` (manual gagne).
8. Garde-fou : si `len(final) > max_repos` → **abort** run avec message clair (pas de troncature silencieuse — cf LOI "no silent caps").

### 3. Stabilité des payloads Qdrant

`repo` (payload) = `name` = basename. Les 5 repos actuels gardent leur nom (VPAI, flash-studio, story-engine, typebot-docs, DOCS) → **aucune ré-indexation forcée**, les filtres `repo:` existants continuent de matcher. `host_origin` inchangé (`waza`).

### 4. Préflight + observabilité

- `run_preflight` logue déjà `repo_roots=… repos=…` : étendre pour logger `discovered=N manual=M total=K` et la **liste nominative** des repos retenus + ceux exclus (et pourquoi).
- Nouveau flag CLI `--list-sources` (ou `--dry-run-discovery`) : imprime le set final SANS indexer. Sert de "auto-découverte manuelle" pour valider avant un vrai run.
- Le run report (push n8n) gagne `repos_target` = liste découverte → visible via `/memory_status` du bot.

### 5. Côté Ansible

- `defaults/main.yml` : nouveau bloc `memory_worker_discovery` (roots, max_depth, excludes, max_repos) + `memory_worker_sources_manual` (overrides). Supprimer/garder `memory_worker_repo_roots` (legacy `config.yml repos:`) — à trancher : le fusionner dans la découverte.
- `config.yml.j2` : rendre le bloc `discovery` + `sources_manual`.
- `sources.yml.j2` : devient soit obsolète (tout passe par config), soit réservé aux `sources_manual`. **Décision** : fusionner dans `config.yml`, retirer `sources.yml` (un seul fichier de vérité).

## Risques & garde-fous

| Risque | Mitigation |
|---|---|
| Explosion du coût (15+ repos d'un coup, gros embeddings) | `max_repos` + abort ; rollout progressif (ajouter `roots` par étapes) |
| Double-indexation repos imbriqués (flash-infra, DOCS/*) | `prune_nested: true` |
| Repo géant non pertinent capté (node_modules vendored avec .git) | `exclude_globs` + extensions déjà filtrées |
| Collision de basename (deux `vps`, deux `docs`) | WARN + override manuel par `name` |
| Redeploy supprime des sources actives | Préflight nominatif + `--list-sources` avant deploy ; diff explicite |

## Plan d'implémentation (≤ 1 semaine)

1. **Code** `index.py.j2` : ajouter `discover_sources()` + `--list-sources`, brancher dans le chargement des sources (remplace `list_repo_roots`/lecture `sources.yml` par `discover_sources(config)`), étendre `run_preflight`. Garder rétro-compat : si `discovery.enabled: false`, lire `sources_manual` seul (comportement actuel).
2. **Tests** : `tests/test_discovery.py` — arbre temp avec repos imbriqués, exclusions, collision, `max_repos` abort, `prune_nested`. (sibling test R4 avant tout deploy.)
3. **Ansible** : nouveaux defaults + templates `config.yml.j2` (+ retrait `sources.yml.j2`).
4. **Validation à blanc** : `index.py --config … --list-sources` sur waza → comparer au set live (5) + nouveaux. **Zéro deploy tant que le diff n'est pas validé.**
5. **Migration** : un `--list-sources` doit ré-émettre exactement les 5 actuels (+ les nouveaux voulus) avant bascule. Reconcilier `defaults` AVANT (cf dérive sources.yml live vs defaults, voir handoff 2026-06-05).

## Dépendances / liens

- Réconciliation manuelle préalable (étape 1, faite séparément) : aligner `defaults/main.yml` sur le live 5 + nouveaux repos choisis, pour qu'un redeploy ne droppe pas VPAI/typebot-docs/DOCS.
- Spec remote-control bot : `docs/superpowers/specs/2026-06-04-memory-worker-remote-control-design.md`.
- Handoff état worker : `.planning/notes/2026-06-05-memory-bot-handoff.md`.
