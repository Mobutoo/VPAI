# REX Session 22 — StoryEngine v1.7.0 IDE Shell + Intelligence Layer (2026-04-07)

## Objectif

Livrer le milestone **v1.7.0** — fusion de deux milestones parallèles :
- **v1.7 IDE Shell + Modes** (5 phases, frontend Next.js/TipTap)
- **v1.7b Intelligence Layer** (5 phases, backend FastAPI)

Exécuté en autonomie totale (overnight, GO explicite) via le framework GSD.

## Ce qui a été fait

### v1.7 IDE Shell + Modes (main)

| Phase | Livrable | Statut |
|-------|----------|--------|
| v1.7-01 IDE Chrome | Activity bar + status bar (SHELL-05, SHELL-06) | ✅ |
| v1.7-02 Multi-Document | Tabs + split editor (SHELL-01, SHELL-02) | ✅ |
| v1.7-03 Navigation Panels | Scene tree + outline (SHELL-03, SHELL-04) | ✅ |
| v1.7-04 BD Mode | Panel nodes + dialogue balloons (MODE-01, MODE-02) | ✅ |
| v1.7-05 Script Mode | Fountain extensions + ModeSwitcher (MODE-03..06) | ✅ |

### v1.7b Intelligence Layer (feat/v1.7b-intelligence → merged)

| Phase | Livrable | Tests | Statut |
|-------|----------|-------|--------|
| v1.7b-01 Perceptual Scopes | DIRECT/PERCEIVED/CONDITIONAL facts + migration 009 | — | ✅ |
| v1.7b-02 Constraint Rules | DSL evaluation (simpleeval) + CRUD API + migration 010 | — | ✅ |
| v1.7b-03 Heuristics H1-H6 | Fréquence, densité, asymétrie, drift, couplage, arc | 26 | ✅ |
| v1.7b-04 Judges L1-L4 | Scene/arc/global/aesthetic judges + 4 endpoints | 55 | ✅ |
| v1.7b-05 Rules R6-R10 | Contradiction, stale, constraint, narrator, twist | 34 | ✅ |

**Total tests v1.7b :** 89 tests

### Déploiement

- Merge feat/v1.7b-intelligence → main (9 conflits résolus)
- Migration 012 créée pour merger les heads 008 et 011 (Alembic merge point)
- Tag v1.7.0 pushé
- Deploy Ansible : `ok=12 changed=5 failed=0`
- Migrations en prod : 012 (head) ✅

## Bugs rencontrés et corrigés en prod

| Bug | Cause | Fix |
|-----|-------|-----|
| `Multiple head revisions` au premier deploy | v1.7b branché depuis 007, v1.7 avait 008 | Migration merge 012 |
| `DuplicateObjectError: constraintscope already exists` | Migration 010 créait l'enum explicitement + via `create_table` | Supprimé l'appel `.create()` redondant |
| `InvalidRequestError: bind parameter '1'` | `sa.text()` interprétait les `:` dans les JSON strings comme bind params | Remplacé par `op.bulk_insert()` avec dicts Python |

## Architecture insights

- **Alembic merge migrations** : quand deux branches modifient la DB en parallèle, créer une migration merge vide (`down_revision = (head1, head2)`) avant le déploiement. Pattern réutilisable pour tout projet parallèle.
- **sa.text() + JSON** : ne jamais mettre de JSON avec des `:` dans `sa.text()` — utiliser `op.bulk_insert()` ou `sa.insert()` avec des dicts Python.
- **Enum création en migration** : ne pas appeler `enum.create()` explicitement si l'enum est déjà dans un `create_table` — SQLAlchemy le fait automatiquement.
- **Branches parallèles** : v1.7 (frontend) et v1.7b (backend) ont pu tourner en parallèle sans conflit de code car la séparation des domaines était stricte (`apps/web/` vs `apps/api/`). Un seul fichier partagé (layout.tsx) avec un conflit trivial.

## Lessons transversales

- **Planning docs en conflit** : les fichiers `.planning/` en merge conflict peuvent se résoudre proprement avec `--ours` sur les docs de la branche la plus à jour (main avait le milestone v1.7 complet).
- **OAuth token expiry** en session longue (>2h) : le planner agent peut rencontrer des 401. Solution : `/login` dans le terminal pour refresh, puis relancer.
- **GSD gsd-tools bug** : `init phase-op` retourne `phase_found: false` pour les phases v1.7b-XX. Workaround : détecter le PHASE_DIR manuellement via `ls .planning/phases/`.

## Prochaines étapes

1. Tester v1.7.0 sur https://story.ewutelo.cloud
2. Démarrer v1.8 — Frontend Intelligence Inspector (affichage H1-H6, judges UI)
