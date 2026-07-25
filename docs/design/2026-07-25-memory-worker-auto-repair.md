# Design — memory-worker-auto-repair (réparation bornée après 1h de drift)

Date : 2026-07-25
Statut : PROPOSITION — à valider au gate humain AVANT toute implémentation
Convergence Codex (gpt-5.6-sol, `review-file.sh`) : 4 rounds, tous les HIGH
confirmés par escalade intégrés (R1 1, R2 6, R3 2, R4 1 — trajectoire
convergente, dernier HIGH = raffinement du thème redaction), MED/LOW
pertinents intégrés. Rapports :
`~/work/ops/loops/reviews/REVIEW-FILE-2026-07-25-memory-worker-auto-repair-20260725-{1736,1740,1748,1753}.md`
Origine : handoff `.planning/handoffs/2026-07-25-memory-pipeline-drift-autorepair.md`
(incident `discover_sources: 31 repos > max_repos=30`, pipeline cassé >21h,
notifications "memory pipeline drift detected" en boucle sans action).

## 1. Problème

Le pipeline memory-worker dispose de trois briques d'observation qui **alertent
mais n'agissent jamais** :

| Brique | Voit | Aveugle à | Anti-spam |
|---|---|---|---|
| `memory-worker-watchdog` (waza, timer 15 min) | run EN COURS bloqué (systemd `activating` > 90 min) | run qui ne démarre plus, crash rapide | oui (3h) |
| `memory-healthcheck` (n8n, cron 1h) | staleness `memory_runs` (`stale_incremental` > 2h), spool, exit_code | run crashé AVANT rapport (aucun POST → invisible) | non (notif chaque heure) |
| `memory-run-report-ingest` (n8n, par run) | exit_code ≠ 0 / erreurs D'UN run rapporté | crash avant rapport | non |

Conséquence observée (incident 2026-07-24→25) : un crash systématique en ~4s
avant rapport rend le healthcheck aveugle à la cause (il ne voit que l'âge),
les notifications se répètent indéfiniment, et rien ne tente les réparations
pourtant sûres (ni ne distingue les pannes réparables des pannes à décision).

## 2. Objectif

Un rôle Ansible **frère** de `memory-worker-watchdog` (pas une réécriture) :
`roles/memory-worker-auto-repair/`. Après **1h de drift continu**, si aucune
trace d'arrêt volontaire n'est trouvée, exécuter une réparation **bornée aux
classes de panne sûres et réversibles**, notifier Telegram avant/après (jamais
silencieux), et escalader en alerte enrichie (cause classifiée) pour tout le
reste.

Non-objectifs explicites :
- Ne JAMAIS modifier une config de production (ex. `max_repos`) — les pannes
  "décision de coût/portée" restent des alertes (gate humain ou gate technique
  tracé, hors de cette brique).
- Ne pas remplacer le healthcheck n8n ni le watchdog — ils restent tels quels.
- Pas de dépendance nouvelle waza→Postgres Sese : la sonde est 100 % locale
  (systemd + `memctl.sh status` + journal). Le healthcheck n8n reste
  l'observateur côté Sese.

## 3. Détection du drift (locale)

Condition de drift, évaluée à chaque tick (timer 15 min, même cadence que le
watchdog). Le signal de santé vient de systemd ; `memctl.sh status` (sonde
réparée le 2026-07-25 : collection lue depuis `config.yml`, env auto-sourcé)
alimente le classifieur §5 (lock, timer, qdrant).

**Signal de santé = dernier run TERMINÉ AVEC SUCCÈS, pas la fraîcheur du
log.** L'âge de la dernière ligne du log (`age_seconds` de `memctl status`)
se rafraîchit dès qu'un run démarre, même s'il crashe 4 s plus tard — sur
l'incident fondateur (crash systématique en ~4 s toutes les 30 min), ce proxy
serait resté « frais » en permanence et n'aurait JAMAIS détecté le drift.
Source fiable et locale : systemd.

À chaque tick, la sonde lit `systemctl --user show <service>
-p ExecMainStatus -p ExecMainExitTimestamp -p ActiveState -p Result`
(**wall-clock**, converti en epoch via `date -d` — PAS la variante
`…TimestampMonotonic`, qui compte depuis le boot et rendrait le calcul de
drift silencieusement faux après un reboot) et maintient dans son state :

- `LAST_SUCCESS_EPOCH` : mis à jour quand le dernier run terminé a
  `ExecMainStatus == 0` **ET `Result == success`** (un `Result` en
  timeout/échec ne compte jamais comme succès, quel que soit l'exit code) ;
  valeur = epoch de fin de ce run. Initialisation au premier tick : si
  l'état courant est sain, `now` ; sinon 0 (inconnu = suspect).
- `drift := now - LAST_SUCCESS_EPOCH > AUTOREPAIR_DRIFT_SEC (déf. 5400)
  ET ActiveState != activating` (jamais d'action pendant un run en cours).

Latence d'action réelle, documentée : le run attendu survient au plus tard
`LAST_SUCCESS + 30 min` (timer worker) ; le seuil 5400 s = 30 min d'intervalle
nominal + 1h de drift effectif, PLUS l'exigence `DRIFT_TICKS >= 2` (§ suivant)
⇒ action effective **≈ 75-90 min après le premier run manqué** (granularité
des ticks de 15 min incluse). Pas de condition sur `spool_depth`
(exigerait un historique sans améliorer la détection — le spool reste un
signal du healthcheck n8n).

Persistance : state file `KEY=VALUE` (pattern watchdog) :
`LAST_SUCCESS_EPOCH`, `DRIFT_TICKS`, `HEALTHY_TICKS` (incrémenté à chaque
tick sain consécutif, remis à zéro dès un tick en drift — alimente le dégel
automatique §5), `LAST_REPAIR_EPOCH`, `REPAIR_ATTEMPTS`, `REPAIR_LOCKED`,
`ALERTED`, `LAST_ALERT`. L'action exige en plus
`DRIFT_TICKS >= 2` (deux ticks consécutifs en drift — un tick isolé ne
déclenche jamais). **Le retour à la santé ne remet à zéro QUE
`DRIFT_TICKS`, `ALERTED`, `LAST_ALERT`** : `LAST_REPAIR_EPOCH` et
`REPAIR_ATTEMPTS` survivent (le cooldown §5 doit tenir même si un run
réussit transitoirement entre deux pannes), et `REPAIR_LOCKED` a sa propre
règle de dégel (§5).

## 4. Garde "arrêt volontaire" (obligatoire avant toute action)

Ordre de vérification, le premier signal trouvé ⇒ NE PAS réparer. Politique
de notification par garde : timer désactivé (n°1) ⇒ notif UNE fois par
épisode de drift (reset au rétablissement) ; sentinelle (n°2) ⇒ notif au
premier tick gelé puis rappels anti-spam 3h (elle peut durer des jours) :

1. `timer_enabled == "disabled"` dans `memctl status` — c'est LA trace durable
   d'un `/memory_stop` Telegram ou `memctl stop` manuel (tous deux font
   `systemctl --user disable --now` le timer). Signal fiable, machine-readable,
   survit au reboot.
2. Marqueur opérateur explicite : fichier sentinelle
   `${state_dir}/maintenance` (touch manuel par l'opérateur, documenté
   runbook). **Reprise** : suppression du fichier (`rm`) ; à la détection de
   la reprise, `DRIFT_TICKS` est remis à zéro et une fenêtre complète de
   drift recommence (le drift "vieilli" pendant la maintenance ne doit
   jamais déclencher une action immédiate à la seconde où la sentinelle
   tombe). Tant qu'elle est présente, l'auto-repair notifie "gelé par
   sentinelle" au premier tick concerné puis se tait (rappel anti-spam 3h),
   et notifie la reprise à la suppression. Une commande Telegram
   `/memory_hold` + `/memory_resume` est une extension possible — à trancher
   au gate (§8.4), PAS un prérequis de cette itération.
3. Journal systemd de la fenêtre de drift : signal d'ENRICHISSEMENT seulement
   (contexte dans la notif), jamais un garde bloquant — un motif
   `Stopped`/`stop` apparaît aussi sur des fins de run normales, il est
   inexploitable seul pour distinguer un arrêt opérateur.

Le cas 1 est le contrat principal ; 2 est un ajout minime (check `-e` + doc) ;
seuls 1 et 2 peuvent bloquer une réparation.

## 5. Classification des pannes et actions

Classifieur exécuté au moment où le drift dépasse 1h (source : `memctl status`
+ `systemctl --user show` + dernier traceback du journal).

**Ordre d'évaluation strict : D → E → A → B → C → F, premier match gagne.**
Les SIGNATURES peuvent se chevaucher (un même incident peut en présenter
plusieurs) ; c'est la priorité qui rend la CLASSE finale unique. Les classes
« alerte seule » sont évaluées
AVANT les classes « action » : si un crash discovery (D) a aussi laissé un
lock zombie (A), c'est D qui gagne — réparer A relancerait indéfiniment le
même crash en masquant la cause. L'alerte mentionne les signatures
secondaires détectées (ex. « + lock zombie présent »). Le harnais de tests
DOIT couvrir les collisions (D+A, E+B, …).

| Classe | Signature | Action auto | Notif |
|---|---|---|---|
| A. Lock zombie | `lock_pid` non vide ET `lock_alive:false` | `memctl fix` (supprime lock mort + relance run) | avant + résultat |
| B. Timer/service arrêté par accident | `timer_active != "active"` MAIS `timer_enabled == "enabled"` (ex. crash user-manager, OOM) | `memctl start` (= `enable --now` le timer) ; puis `memctl run` SEULEMENT si aucun run n'a démarré entre-temps — détection par comparaison de `InactiveExitTimestamp` avant/après le start (un simple re-check `ActiveState` raterait un run démarré ET terminé dans l'intervalle ; un timer `Persistent=true` peut rattraper la fenêtre manquée dès le start) | avant + résultat |
| C. Run jamais relancé, service `failed`, cause inconnue | `Result=exec-condition` (calm-wait timeout) ou `ExecMainStatus!=0`, SANS signature D/E (dernier résultat observé — pas de critère « répété », le cooldown §5 et la relance unique bornent déjà le risque) | 1 seul `memctl run` de relance (le run suivant peut réussir : Pi chaud transitoire) | avant + résultat |
| D. Garde-fou discovery | traceback `discover_sources.*max_repos` dans le journal de la fenêtre | AUCUNE — alerte enrichie "décision requise : max_repos/exclude_names" | alerte seule |
| E. Qdrant injoignable | `qdrant_reachable:false` (sonde réparée = signal fiable) | AUCUNE — dépendance externe, le spool absorbe ; alerte enrichie | alerte seule |
| F. Inclassable | tout le reste | AUCUNE — alerte enrichie avec extrait du dernier traceback | alerte seule |

Règles transverses :
- **Budget de réparation** : au plus 1 action auto par fenêtre de
  `AUTOREPAIR_COOLDOWN_SEC` (déf. 4h, > 2× le seuil de drift), calculée sur
  `LAST_REPAIR_EPOCH` — qui SURVIT aux retours transitoires à la santé (§3) :
  un run qui réussit une fois puis recasse ne réarme pas le budget.
- **Gel après échec** : si le drift persiste au tick suivant une réparation
  (vérif : un run doit s'être terminé avec le prédicat de succès du §3 —
  `ExecMainStatus == 0` ET `Result == success` ET fin POSTÉRIEURE à
  l'action), escalade "🔴 auto-repair a agi mais le drift persiste —
  intervention requise" et pose de `REPAIR_LOCKED=1` — état DISTINCT de
  l'anti-spam `ALERTED` (qui, lui, se réinitialise au rétablissement §3).
  Dégel de `REPAIR_LOCKED` — deux voies exactement, la sentinelle
  `maintenance` n'en fait PAS partie (elle gèle, elle ne dégèle rien) :
  (a) opérateur — suppression du marqueur DÉDIÉ `${state_dir}/repair-locked`
  (fichier séparé du state file, précisément pour que le dégel manuel ne
  puisse pas effacer `LAST_REPAIR_EPOCH` et contourner le cooldown) ;
  (b) automatique quand `HEALTHY_TICKS >= AUTOREPAIR_UNLOCK_TICKS`
  (déf. 8 = 2h de santé soutenue), avec notif de dégel. Tant que `REPAIR_LOCKED=1` : alertes seulement (rappels
  anti-spam 3h), aucune action.
- Les actions A/B/C sont toutes **réversibles et déjà exposées par `memctl`**
  (surface d'action existante, allow-list du forced-command SSH inchangée).
  Aucune commande nouvelle n'entre dans la surface d'action.
- La classe D est le cas de l'incident fondateur : l'auto-repair l'aurait
  classifié à sa première fenêtre d'action — 75-90 min après le premier run
  manqué (latence §3) — avec la cause exacte (`max_repos`) dans la notif, au lieu
  de 21h de `stale_incremental` opaque côté healthcheck.

## 6. Notifications

Canal : même bot que watchdog/healthcheck/disk-guard
(`telegram_monitoring_bot_token/chat_id`, env file 0600, `no_log: true`).
Format (préfixe commun `🔧 memory-auto-repair @waza`) :

- Avant action : classe, signature, action prévue.
- Immédiatement après action : "action lancée" (le résultat n'est PAS encore
  vérifiable — un run dure plusieurs minutes).
- Au tick suivant : notification de résultat vérifié (un run s'est terminé
  `ExecMainStatus == 0` depuis l'action, ou non → escalade §5).
- Alerte-seule (D/E/F) : cause classifiée + extrait traceback (≤ 400 chars)
  + rappel de la commande de diagnostic (`§6.4 AI-MEMORY-OPERATIONS.md`).
  **Redaction obligatoire avant envoi** — un traceback brut peut contenir
  bien plus que du contenu indexé (tokens, URLs avec identifiants, valeurs
  d'env). **L'exigence est comportementale, pas un regex normatif** (un
  motif figé dans un design finit toujours par avoir un trou) : le filtre
  `redact()` DOIT masquer intégralement toute valeur de credential sous
  chacune des formes suivantes, et le harnais de tests DOIT injecter un
  credential factice de CHAQUE forme et prouver qu'aucun fragment ne
  survit :
  `KEY=v` (env shell) ; `key: v` (YAML) ; `"api_key": "v a l"` (JSON,
  valeur quotée AVEC espaces — la valeur entière est masquée jusqu'au
  guillemet fermant, pas jusqu'au premier espace) ; `'token':'v'` ;
  `Authorization: Bearer <token>` ET `Authorization: Basic <base64>`
  (schémas séparés par ESPACE, pas par `=`/`:`) ; userinfo d'URL
  (`scheme://user:pass@` → `scheme://***@`) ; chaînes `sk-\S+`.
  Mots-clés sensibles minimum : `api[-_]?key, token, secret, password,
  authorization, bearer, basic` (insensible à la casse).
- Anti-spam : état `ALERTED/LAST_ALERT`, rappel ≥ 3h, notif de rétablissement
  quand la santé revient (run terminé `ExecMainStatus == 0` récent, §3 —
  pattern watchdog repris tel quel).

## 7. Livrables & discipline

1. `roles/memory-worker-auto-repair/` : defaults (seuils nommés
   `memory_worker_auto_repair_*`, fallbacks sur `memory_worker_service_name`
   etc., pattern watchdog), templates (script + env + service/timer user),
   tasks (linger, `bash -n`, daemon_reload user, flush_handlers), handlers,
   meta. Tags `[memory_worker_auto_repair, phase3]` (même phase que le worker).
2. Tests miroir `roles/llamaindex-memory-worker/tests/` : harnais bash avec
   injections (`FAKE_*` env, systemctl/curl mockés dans PATH) couvrant : garde
   arrêt-volontaire (timer disabled ⇒ no-op), sentinelle maintenance (gel +
   reprise avec fenêtre recommencée), classification des SIX classes
   A/B/C/D/E/F, priorité et collisions (D+A, E+B), cooldown survivant à un
   retour transitoire à la santé, drift persistant post-réparation ⇒
   escalade + `REPAIR_LOCKED`, dégel (santé soutenue), anti-course classe B
   (run démarré entre start et run ⇒ pas de 2e déclenchement), redaction
   (toutes les formes du §6).
3. LOI : FQCN, `changed_when`/`failed_when` explicites, `set -euo pipefail`,
   pas de `:latest`, idempotence 0 changed au 2e run.
4. MAJ `docs/runbooks/AI-MEMORY-OPERATIONS.md` : nouveau §4.1.3 (auto-repair),
   tableau des classes, procédure sentinelle `maintenance` (pose + reprise
   manuelles ; les commandes Telegram `/memory_hold`/`/memory_resume` ne
   deviennent un livrable QUE si retenues au gate §8.4), et note que le
   healthcheck n8n reste inchangé.
5. Revue `reviewer` (Opus) avant tout déploiement ; déploiement ciblé
   `--tags memory_worker_auto_repair` (jamais `make deploy-workstation` full —
   landmine `settings.json.j2`).

## 8. Points à trancher au gate

1. **Valider la frontière classes A/B/C (agir) vs D/E/F (alerter)** — le point
   le plus sensible du chantier : un auto-repair trop large masque les vrais
   problèmes.
2. Seuils proposés : `AUTOREPAIR_DRIFT_SEC` 5400 (= 30 min d'intervalle
   nominal + 1h de drift), cooldown 4h, cadence 15 min, dégel 8 ticks — OK ?
3. La classe C (relance unique sur cause inconnue) est la plus discutable :
   option de repli = la déclasser en alerte-seule si jugée trop agressive.
4. Commandes Telegram `/memory_hold`/`/memory_resume` : inclure dans cette
   itération ou différer ? (La sentinelle FICHIER `maintenance`, elle, est
   un livrable acquis de l'itération — §4.2 et §7.4 ; seule l'exposition
   Telegram est à trancher. NB : ce canal a un gate non soldé — credential
   SSH n8n→waza, Task 5 du plan de contrôle v2.)
5. Rotation de la clé API Qdrant (hors périmètre de la brique mais liée à la
   session). Preuves : (a) fuite `--diff` du 2026-07-23 — REX
   `project_coffre_agents_secrets` (mémoire projet), fix `no_log: true`
   commit VPAI `21d9c01`, rotation recommandée jamais faite ; (b) fuite
   transcript session Claude du 2026-07-25 (session `448d…478`, masquage
   raté lors de la lecture de `memory-worker.env` — transcript local waza,
   accès restreint). État rotation : NON FAITE au 2026-07-25. Après
   rotation : consigner date + empreinte partielle (4 derniers caractères)
   de la nouvelle clé dans le REX coffre, jamais la valeur.
