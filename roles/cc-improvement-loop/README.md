# Rôle `cc-improvement-loop`

Versionne le **planificateur systemd-user** de la boucle d'amélioration continue
Claude Code (backlog **P4-1** du lab `~/work/ops/claude-code-improvement-lab`).

## Périmètre

- Déploie `cc-improvement-loop.service` (oneshot) + `cc-improvement-loop.timer`
  (mensuel, `Persistent=true`) dans `~/.config/systemd/user/`.
- Active le timer (idempotent, désactivable via `cc_improvement_enabled: false`).
- **Ne versionne PAS** le script `continuous-improvement.sh` : il vit dans le lab
  git-local (jamais poussé, cf CSV metrics = risque scrubbing résiduel). Ce rôle
  suppose le lab déjà présent en `{{ cc_improvement_lab_dir }}`.

## Propriétés

- **Read-only** : le service rejoue le pipeline d'audit en mode observation
  (collecte rsync locale → sanitize → normalize → métriques → compare baseline
  figée → rapport). Il ne modifie jamais `~/.claude/`.
- **Batch borné** (doctrine REX 2026-06-05) : `MemoryMax=2G`, `OOMScoreAdjust=1000`,
  `Nice=19`, `IOSchedulingClass=idle`.
- **Cadence mensuelle** : cohérente avec la purge quotidienne de
  `~/.claude/projects/*.jsonl` (governance.md §2 du lab).

## Prérequis

- Linger utilisateur (assuré par le rôle `llamaindex-memory-worker`, exécuté avant).

## Déploiement

```bash
ansible-playbook playbooks/hosts/workstation.yml --tags cc-improvement-loop
```

Rollback : `cc_improvement_enabled: false` (redeploy) ou
`systemctl --user disable --now cc-improvement-loop.timer`.
