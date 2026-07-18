# Rôle `cc-improvement-loop`

Versionne le **planificateur systemd-user** de la boucle d'amélioration continue
Claude Code (backlog **P4-1** du lab `~/work/ops/claude-code-improvement-lab`).

## Périmètre

- Déploie `cc-improvement-loop.service` (oneshot) + `cc-improvement-loop.timer`
  (mensuel, `Persistent=true`) dans `~/.config/systemd/user/`.
- Active le timer (idempotent, désactivable via `cc_improvement_enabled: false`).
- Le service exécute **2 étapes séquentielles** (`ExecStart=` multiples,
  ordre garanti) :
  1. `continuous-improvement.sh observe` (pipeline d'audit sessions, inchangé).
  2. `token_audit_notify.sh` (**T1.2**) : audit tokens/coût 30 derniers jours
     via `token_audit.py`, écrit `metrics/token-audit-YYYYMM.json`, calcule
     la part Opus+Fable du coût NOTIONNEL (tarif liste `PRICING` interne au
     script, pas la facturation réelle ccusage — cf `cost_split.py`) et
     alerte Telegram si elle dépasse `cc_improvement_token_audit_threshold_pct`
     (défaut 50 %). Silence si sous le seuil (anti-spam).
- **Ne versionne PAS** les scripts `continuous-improvement.sh`,
  `token_audit.py`, `token_audit_notify.sh` : ils vivent dans le lab
  git-local (jamais poussé, cf CSV metrics = risque scrubbing résiduel). Ce
  rôle suppose le lab déjà présent en `{{ cc_improvement_lab_dir }}` et crée
  seulement `{{ cc_improvement_lab_dir }}/metrics/` s'il est absent.
- **Aucun secret Telegram dans ce rôle/repo** : `token_audit_notify.sh`
  source en lecture seule le fichier 0600
  `/opt/workstation/configs/ai-memory-worker/memory-eval-golden.env`
  (canal Telegram canonique, déployé par le rôle `llamaindex-memory-worker`,
  réutilisé tel quel — T1.1).

## Propriétés

- **Read-only** : le service rejoue le pipeline d'audit en mode observation
  (collecte rsync locale → sanitize → normalize → métriques → compare baseline
  figée → rapport), puis l'audit tokens (lecture seule `~/.claude/projects`).
  Il ne modifie jamais `~/.claude/`. Seul appel réseau sortant possible :
  Telegram, et uniquement si le seuil de part Opus+Fable est dépassé.
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
