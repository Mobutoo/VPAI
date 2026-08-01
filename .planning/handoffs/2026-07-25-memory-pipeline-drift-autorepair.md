# Handoff — memory pipeline drift : fix racine + auto-repair 1h

## Objectif

Débloquer durablement le pipeline memory-worker (les notifications "memory
pipeline drift detected" reçues en boucle ne sont pas un faux positif — le
pipeline est réellement cassé depuis >21h) et livrer une brique d'auto-repair :
après 1h de drift continu, si aucune trace de demande d'arrêt manuel n'est
trouvée dans les logs, déclencher automatiquement l'investigation/réparation.

## Décisions prises

- **Root cause confirmée par logs live** (pas une hypothèse) :
  `RuntimeError: discover_sources: 31 repos > max_repos=30`
  (`memory_core.py:363`), sur CHAQUE run incrémental depuis au moins
  2026-07-24 19:38:43 (dernier run réussi, `memctl.sh status` →
  `last_run_ts` à ~21.7h au moment du handoff). Chaque run échoue en ~4s
  AVANT de POSTer un rapport (`run-and-report: no report produced or
  webhook not configured — skipping POST`) → la table Postgres `memory_runs`
  ne reçoit plus de ligne fraîche → le workflow n8n `memory-healthcheck`
  (Cron 1h) recalcule l'âge du dernier run incrémental et alerte
  indéfiniment (`stale_incremental:last_run_Xh_ago`) tant que la cause
  n'est pas traitée — **il ne se résorbe jamais tout seul**.
- `max_repos: 30` est un garde-fou **volontaire** ("abort, no silent cap"),
  posé au ship de l'auto-découverte le 2026-06-08 (REX
  `project_memory_autodiscovery`, alors 20 repos). Ne PAS le bumper à
  l'aveugle sans compter les sources réelles post-excludes : au moins un
  repo très récent (`usine-saas`, cette semaine, cf REX
  `project_usine_saas_ia_factory`) explique une partie de la dérive, mais
  `~/work/saas` contient déjà 22 dossiers à lui seul — vérifier via
  `index.py --list-sources` (dry-run, pas de coût modèle/Qdrant) avant de
  choisir la nouvelle valeur.
- `memctl.sh fix` (déjà en place, `cmd_fix` ligne 51-56) ne traite QUE le
  cas "lock zombie" (PID mort qui bloque le prochain run). Un futur watcher
  qui appellerait `memctl fix` en boucle sur CE symptôme relancerait
  indéfiniment le même crash sans jamais le résoudre. **Ne pas construire
  l'auto-repair sur `memctl fix` seul** — il doit distinguer les classes de
  panne (lock zombie / garde-fou discovery / qdrant injoignable / autre
  exit_code) et n'agir automatiquement que sur les classes sûres et
  réversibles.
- Précédent directement réutilisable pour la mécanique "sonde indépendante
  + anti-spam + Telegram" : rôle `roles/memory-worker-watchdog/` (timer
  systemd --user 15min, seuil stagnation 90min, anti-spam 3h, notif
  rétablissement) — mais il ALERTE seulement, jamais n'agit. La nouvelle
  brique "auto-repair après 1h" est un rôle frère (ou une extension), pas
  une réécriture de celui-ci.
- Canal Telegram existant (`memory-telegram-bot.json`, actions
  `/memory_status|_last|_health|_help|_start|_stop|_run|_fix` via SSH
  forced-command `memctl-remote.sh`, cf REX
  `project_memory_worker_control.md`) = voie naturelle pour (a) notifier
  avant/après une auto-réparation (feedback mémoire "Gate humain →
  Telegram" : toute notif doit passer par un canal qui atteint le
  téléphone, pas les notifs natives CC) et (b) fournir le point d'ancrage
  d'un arrêt manuel explicite (`/memory_stop`) que l'auto-repair peut
  chercher dans les logs avant d'agir. Ce canal a un historique de gate
  humain non soldé (Task 5 du plan v2, credential SSH n8n→waza) — vérifier
  qu'il est bien opérationnel de bout en bout avant de s'appuyer dessus.
- Portée scindée en deux livrables séquencés : (1) débloquer le pipeline
  MAINTENANT — fix ponctuel, réversible, faible risque ; (2) concevoir puis
  livrer la brique d'auto-repair générique, avec discipline LOI (FQCN,
  `changed_when`/`failed_when` explicites, `set -euo pipefail`, jamais
  `:latest`, tags `[role_name, phaseN]`).

## Chemins / artefacts

- Logs bruts confirmant la cause :
  `journalctl --user -u llamaindex-memory-worker.service -n 100 --no-pager`
  (traceback complet `discover_sources`, répété à chaque déclenchement du
  timer ~30min)
- Garde-fou : `/opt/workstation/configs/ai-memory-worker/config.yml:48`
  (`max_repos: 30`) ; source Ansible
  `/home/mobuone/work/infra/VPAI/roles/llamaindex-memory-worker/defaults/main.yml:161` ;
  template
  `/home/mobuone/work/infra/VPAI/roles/llamaindex-memory-worker/templates/config.yml.j2:53`
- Logique de discovery :
  `/opt/workstation/ai-memory-worker/memory_core.py:363`
  (`discover_sources`, scan `~/work/{infra,saas,tools,refdocs}/*`)
- Outil d'exploitation local : `/opt/workstation/ai-memory-worker/memctl.sh`
  (`status|start|stop|run|fix`)
- Healthcheck n8n (source de la notif "drift") :
  `/home/mobuone/work/infra/VPAI/scripts/n8n-workflows/memory-healthcheck.json`,
  nœud `Evaluate Memory Health` (jsCode) ; seuils
  `MEMORY_HEALTHCHECK_MAX_AGE_HOURS` (def 2h) /
  `MEMORY_HEALTHCHECK_MAX_SPOOL` (def 50) ; table Postgres `memory_runs`
  (host `postgresql`, db `n8n`)
- Rôle de référence pour bâtir la sonde d'auto-repair :
  `/home/mobuone/work/infra/VPAI/roles/memory-worker-watchdog/` + doc
  `/home/mobuone/work/infra/VPAI/docs/runbooks/AI-MEMORY-OPERATIONS.md` §4.1.2
- Bot Telegram + wrapper distant :
  `/home/mobuone/work/infra/VPAI/scripts/n8n-workflows/memory-telegram-bot.json`,
  `memctl-remote.sh` (chemin exact à relocaliser sur waza, cf REX)
- Runbook d'exploitation à tenir à jour après le fix :
  `/home/mobuone/work/infra/VPAI/docs/runbooks/AI-MEMORY-OPERATIONS.md`
- REX à relire avant de coder (déjà lus pendant l'investigation, mais à
  reconfirmer dans la session reprise) :
  `/home/mobuone/.claude/projects/-home-mobuone-work-infra-VPAI/memory/project_memory_autodiscovery.md`,
  `/home/mobuone/.claude/projects/-home-mobuone-work-infra-VPAI/memory/project_memory_worker_bm25_cache_reconcile.md`
  (piège cache tmpfs + GC state≠Qdrant, pertinent si l'auto-repair touche au
  state/Qdrant),
  `/home/mobuone/.claude/projects/-home-mobuone-work-infra-VPAI/memory/project_memory_worker_control.md`
  (pièges Switch v3 `is_action:false`+`fallbackOutput`, `DBUS_SESSION_BUS_ADDRESS`
  requis pour tout `systemctl --user` déclenché à distance)
- État live au moment du handoff (`memctl.sh status`) :
  `{"last_run_ts":"2026-07-24 19:38:43","age_seconds":77693,"spool_depth":0,
  "lock_alive":false,"qdrant_reachable":false,"timer_enabled":"enabled",
  "timer_active":"active"}` — `qdrant_reachable:false` de cette sonde
  ponctuelle est probablement un faux négatif transitoire (le service
  Qdrant `javisi_qdrant` est `healthy` depuis 2 semaines côté Sese, URL
  configurée = `https://qd.ewutelo.cloud:443`, pas `localhost`) : à
  revérifier avec `memctl.sh status` en direct avant de conclure quoi que
  ce soit dessus, ne pas supposer un 2e incident sans le reconfirmer.

## Prochaine étape

1. **Débloquer immédiatement** : lancer
   `index.py --list-sources` (ou équivalent dry-run) pour compter les
   sources réellement découvertes post-excludes, décider soit d'un nouveau
   `max_repos` avec marge (ex. +10 au-delà du compte réel) soit d'exclure
   explicitement un repo qui ne doit pas être indexé (`exclude_names`) —
   patcher `roles/llamaindex-memory-worker/defaults/main.yml` (+ override
   inventory si besoin), déployer le rôle ciblé, vérifier un run
   incrémental réussi (`memctl.sh run` puis `memctl.sh status`), confirmer
   qu'une ligne fraîche apparaît dans `memory_runs` pour que la prochaine
   passe du healthcheck n8n repasse `healthy`.
2. **Concevoir puis implémenter la brique d'auto-repair** : nouveau rôle
   (ou extension de `memory-worker-watchdog`) qui (a) détecte la même
   condition de drift que le healthcheck n8n (ou lit directement
   `memctl.sh status` / `memory_runs`), (b) attend 1h de drift CONTINU,
   (c) avant d'agir, grep les logs pertinents (journal systemd du service +
   éventuelle trace `/memory_stop` Telegram ou `memctl stop` manuel) pour
   une preuve de "stop volontaire" dans la fenêtre — si trouvée, NE PAS
   réparer ; (d) sinon déclenche une réparation bornée aux classes de panne
   sûres (lock zombie via `memctl fix`, simple restart) et notifie
   Telegram avant/après (jamais silencieux, cf feedback "Gate humain →
   Telegram") ; (e) pour les classes de panne qui impliquent une décision
   de coût/portée (ex. garde-fou `max_repos`) — alerter seulement, ne
   jamais auto-modifier une config de production sans repasser par un gate
   explicite ou une règle d'arbitrage tracée (cf feedback "Gate technique →
   Fable/Codex, pas l'humain" si le critère est vérifiable et rien ne sort
   du périmètre).
3. Écrire des tests (miroir
   `roles/llamaindex-memory-worker/tests/test_memctl.sh`) + mettre à jour
   `docs/runbooks/AI-MEMORY-OPERATIONS.md` avec la nouvelle brique.
4. Revue avant merge/déploiement prod : dispatcher `reviewer` (Opus) local
   avant tout `make deploy-workstation` (LOI règle 3 —
   `finishing-a-development-branch`).

## Gates humains

- Choix du nouveau `max_repos` (ou exclusion d'un repo précis) : décision
  de coût/portée volontairement gardée hors auto-repair par le design
  2026-06-08 — trancher explicitement (ou dispatcher un gate technique
  arbitrable si le critère est vérifiable et sans enjeu humain).
- Tout déploiement Ansible non-`--check` sur un service qui tourne en
  continu (`make deploy-workstation` / rôle ciblé) — confirmer avant
  d'exécuter.
- Portée exacte de l'auto-repair (quelles classes de panne sont "sûres à
  corriger seule" vs "notifier seulement") : à faire valider AVANT
  l'implémentation, pas après — le risque d'un "auto-repair" qui masque un
  vrai problème, ou pire, qui patche une config de garde-fou sans
  traçabilité, est le point le plus sensible de ce chantier.
- Si le nouveau rôle réutilise le canal Telegram/SSH existant
  (`memory-telegram-bot.json` / `memctl-remote.sh`) : vérifier d'abord que
  la credential SSH n8n→waza (Task 5 du plan v2 de contrôle, jamais confirmée
  soldée dans le REX) est bien posée — sinon ce canal n'est peut-être pas
  encore opérationnel de bout en bout.
