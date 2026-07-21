# Rôle `cc-improvement-loop`

Versionne le **planificateur systemd-user** de la boucle d'amélioration continue
Claude Code (backlog **P4-1** du lab `~/work/ops/claude-code-improvement-lab`).

## Périmètre

- Déploie `cc-improvement-loop.service` (oneshot) + `cc-improvement-loop.timer`
  (mensuel, `Persistent=true`) dans `~/.config/systemd/user/`.
- Active le timer (idempotent, désactivable via `cc_improvement_enabled: false`).
- Le service exécute **3 étapes séquentielles** (`ExecStart=` multiples,
  ordre garanti) :
  1. `continuous-improvement.sh observe` (pipeline d'audit sessions, inchangé).
  2. `token_audit_notify.sh` (**T1.2**) : audit tokens/coût 30 derniers jours
     via `token_audit.py`, écrit `metrics/token-audit-YYYYMM.json`, calcule
     la part Opus+Fable du coût NOTIONNEL (tarif liste `PRICING` interne au
     script, pas la facturation réelle ccusage — cf `cost_split.py`) et
     alerte Telegram si elle dépasse `cc_improvement_token_audit_threshold_pct`
     (défaut 50 %). Silence si sous le seuil (anti-spam).
  3. `plugin_drift_check.sh` (**T1.3**, seed 2026-07-21) : compare chaque
     plugin installé (`~/.claude/plugins/installed_plugins.json`) à son
     marketplace amont GitHub (`.claude-plugin/marketplace.json`, via
     `gh api` puis fallback `curl raw.githubusercontent.com`), plus la
     fraîcheur de `known_marketplaces.json` (seuil
     `cc_improvement_plugin_drift_stale_days`, défaut 60 j). Écrit un
     fichier `inbox/YYYY-MM-DD-plugin-drift.md` dans le lab UNIQUEMENT s'il
     y a ≥1 finding (DRIFT/STALE/UNKNOWN) — silence sinon (anti-bruit).
     **Détection-only, jamais d'auto-update** (pin discipline). Origine :
     superpowers 5.0.4 a stagné 4 mois derrière l'amont (6.1.1) sans que la
     boucle ne le détecte — elle n'auditait que sessions/tokens, jamais les
     versions plugins.
- **Ne versionne PAS** les scripts `continuous-improvement.sh`,
  `token_audit.py`, `token_audit_notify.sh`, `plugin_drift_check.sh` : ils
  vivent dans le lab git-local (jamais poussé, cf CSV metrics = risque
  scrubbing résiduel). Ce rôle suppose le lab déjà présent en
  `{{ cc_improvement_lab_dir }}` et crée seulement
  `{{ cc_improvement_lab_dir }}/metrics/` s'il est absent.
- **Aucun secret Telegram dans ce rôle/repo** : `token_audit_notify.sh`
  source en lecture seule le fichier 0600
  `/opt/workstation/configs/ai-memory-worker/memory-eval-golden.env`
  (canal Telegram canonique, déployé par le rôle `llamaindex-memory-worker`,
  réutilisé tel quel — T1.1).

## Propriétés

- **Read-only** : le service rejoue le pipeline d'audit en mode observation
  (collecte rsync locale → sanitize → normalize → métriques → compare baseline
  figée → rapport), puis l'audit tokens (lecture seule `~/.claude/projects`),
  puis le drift plugins (lecture seule `~/.claude/plugins/*.json`). Il ne
  modifie jamais `~/.claude/` ni n'exécute de mise à jour de plugin. Appels
  réseau sortants possibles : Telegram (uniquement si seuil Opus+Fable
  dépassé) et GET read-only vers `api.github.com`/`raw.githubusercontent.com`
  (lecture des `marketplace.json` amont, T1.3).
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
