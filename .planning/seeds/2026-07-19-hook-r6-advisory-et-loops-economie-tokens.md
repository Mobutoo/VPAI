# Seed — Hook R6 advisory + loops économie tokens (pour lundi 2026-07-21)

## ⛔ DISCIPLINE DE SESSION (validée user + Fable 19/07) — LIRE EN PREMIER

Ce seed = **2-3 sessions**, PAS une. Vouloir tout faire lundi = le seul moyen de rater.

**Session 1 (lundi)** — ordre strict, s'arrêter là où on arrive :
1. Lire l'inbox `lab/inbox/cc-releases/` (rituel veille).
2. Mining : `mine_tool_sequences.py` + efficacité prompts (corrections audit : sanitized only,
   stratifié par work_nature, pondérer le récent) → top-10 documenté.
3. POC top-1 en Workflow script — **verdict GO/NO-GO chiffré** (tokens JSONL locaux, tâches
   jumelles, qualité reviewer identique sur les 2 bras).
4. SI temps restant : hook R6 (avec cooldown + exemptions debug/GSD).

**Session 2+** (à planifier selon verdict POC) : gabarit prompts standard, test contrôlé
`/goal`, inventaire commandes de boucle (6 fiches max), bibliothèque Gitea + smoke-tests +
make verify, migration du mécanique GSD.

**Règle d'arrêt** : chaque session livre un verdict écrit (GO/NO-GO ou fait/reporté) dans ce
seed avant de s'étendre. Pas de nouveau chantier tant que le précédent n'a pas son verdict.

Contexte : clôture chantier routage P1-P3 (nuit 18→19/07). Quota hebdo à 98 % → reporté
post-reset (dimanche 10:00 CEST). Politique : lab `recommendations/2026-07-18-model-routing-policy.md`.

## 1. Hook R6 advisory (décidé, à construire)

Compteur PostToolUse en session principale : ≥5 Read / ≥10 Bash consécutifs **sans dispatch
d'agent** → nudge « délègue à scout/mech, passe des chemins pas du contenu » (advisory, exit 0).
- Pattern : identique aux hooks existants (`model-routing-advisor.js` pour la structure,
  compteur d'état type ledger comme `loi-op-enforcer.js`).
- Vérifié le 19/07 : AUCUN hook n'enforce R6 aujourd'hui (loi-op-enforcer = R0/R1/R3/R8-R11 ;
  le « R6 » de mcp-intent-guard = simple label d'une redirection docker→MCP).
- Reset du compteur : à chaque dispatch Agent/Workflow, et par topic/phase.
- Verify : simulation stdin (série de Read → nudge au 6e ; dispatch agent → reset ; subagent
  session → exempt). Sync copie lab + commit.

## 2. Loops / suites de prompts automatiques (réflexion user 19/07 matin)

Question : enchaîner automatiquement des prompts selon les résultats pour réduire les
allers-retours (= le levier « session principale ~53 % du notionnel »).
Réponse courte consignée : le gain vient du **contrôle déterministe** (zéro token pour la
logique d'enchaînement) — 3 mécanismes déjà disponibles, par ordre de pertinence :
1. **Workflow tool** (opt-in « use a workflow ») : script JS déterministe qui orchestre des
   `agent()` sonnet avec boucles/conditions — la logique ne coûte RIEN en tokens, seuls les
   agents consomment ; la session principale n'ingère plus les sorties intermédiaires.
2. **Chaînes bash `claude -p`** (pattern autofix/pr-watch existant) : le script décide de la
   suite sur exit codes — rappel T3-bis : débite quand même le quota du plan → toujours
   `--model sonnet --max-budget-usd`.
3. **/loop, /schedule, hooks** : récurrence/réaction, pas économie par tour.
### POC lundi — mining des patterns AVANT de choisir le POC (validé avec user 19/07)

Les candidats Workflow sont identifiables dans les logs de sessions EXISTANTS, et le lab a
déjà le pipeline (zéro token modèle, tout est déterministe local) :
- `data/normalized/sessions.jsonl` (215 sessions principales) + `events-{archive,live}.jsonl.gz`
  (événements compacts par session) — produits par `normalize_sessions.py`
- `metrics/taxonomy.json` + `classify_sessions.py` (work_nature/outcome)
- `loop_error_scan.py` (signatures d'erreurs/boucles de retry) + `cost_split.py` (axe $)

**À écrire lundi : `mine_tool_sequences.py`** sur events normalisés :
1. n-grams de séquences d'outils par session (ex. Read→Edit→Bash(lint)→Bash(git commit) ×N)
   → chaînes mécaniques répétées = candidates Workflow ;
2. croiser fréquence × coût (cost_split) → prioriser par ROI ;
3. repérer les allers-retours orchestrateur↔subagents (dispatch puis relecture de résultats)
   → candidats pipeline() ;
4. sortie : top-10 séquences (fréquence, coût cumulé, exemple de session) → choisir LE POC.
Puis : convertir le top-1 en Workflow script, mesurer delta tokens main-session vs
orchestration classique (jauge `api/oauth/usage` avant/après, méthode T3-bis).

### Axe prompts — « workflows au top de l'ingénierie » (demande user 19/07)

Le mining de lundi doit AUSSI comparer les prompts, pas seulement les séquences d'outils :
1. **Efficacité empirique depuis les logs** : les JSONL contiennent tous les prompts de dispatch
   d'agents + leur issue (succès/retry/erreur/tokens consommés). `mine_tool_sequences.py` (ou un
   `mine_prompt_efficacy.py` dédié) : extraire les prompts de dispatch, les regrouper par forme
   (longueur, présence objectif/contraintes/format-de-sortie/critères-verify), croiser avec
   outcome + nb de retries + tokens → identifier les formes de prompts qui MARCHENT chez nous.
2. **Canon Anthropic** (rapport claude-code-guide 19/07, sourcé) :
   **Boucle fondamentale** : contexte → action → vérification (how-claude-code-works.md) ;
   contexte = ressource partagée (persistant → CLAUDE.md) ; checkpoints avant édits.
   **Features orchestration** (code.claude.com/docs/en/{goal,workflows,agent-teams}.md) :
   - **`/goal`** ✅ EXISTE : exécution autonome jusqu'à CONDITION, évaluateur Haiku par tour,
     marche en headless `claude -p "/goal …"` → LA primitive « boucle jusqu'au résultat » ;
   - `/loop` (récurrence), `/effort ultracode` (workflows auto sur tâches substantielles),
     Workflow scripts (1-1000 subagents, resumable, `/workflows` = progress live),
     agent-teams (exp., leads+peers, task list partagée), checkpointing/rewind,
     channels (messages entrants agents long-running), routines (cron cloud).
   **6 règles prompts agents** (platform…/agent-skills/best-practices.md) :
   concision (chaque token doit se justifier) ; degrees of freedom (fragile→instructions
   exactes, heuristique→liberté) ; tester sur Haiku/Sonnet/Opus (Haiku veut plus de détail) ;
   progressive disclosure (1 niveau de profondeur max) ; étapes + checklist + validations
   intermédiaires ; exemples concrets + format de sortie exact si critique.
   **Anti-patterns** : trop d'options, nesting profond, nombres magiques.

### Veille + inventaire complet des commandes (demande user 19/07)

- **Veille LIVE** : `cc-release-watch.{sh,service,timer}` (ops 25773c7 puis refactor) — diff du
  changelog local entre versions vues → **digest markdown déposé dans
  `lab/inbox/cc-releases/`** (décision user : la veille nourrit le PROCESSUS, pas Telegram —
  zéro notification humaine). Consommation : les sessions d'amélioration lisent l'inbox en
  début de session (l'ajouter au rituel lundi) ; indexable mémoire. Testé : digest 20 Ko
  2.1.213→2.1.215 déposé, re-run silencieux. Pièges rencontrés : SIGPIPE `head -c` sous
  pipefail (→ substring bash), awk sans section LAST → tout le changelog (→ borne 20k).
- **Inventaire complet à faire lundi** : liste brute des slash-commands extraite du binaire
  2.1.214 (bruitée, à trier) — commandes remarquables non utilisées : `/goal`, `/tasks`,
  `/routines`, `/rewind`, `/memories`, `/powerup`, `/babysit-prs`, `/teleport`,
  `/remote-control`, `/channel`, `/bridge`, `/btw`. Croiser avec la doc live
  (sitemap code.claude.com/docs) + fiche 1-ligne par commande « quand l'utiliser dans une
  boucle ». NB binaire 2.1.214 vs CLI 2.1.215 : les updates tombent plusieurs fois/semaine.
3. **Synthèse lundi** : gabarit de prompt standard pour la bibliothèque de workflows
   (objectif mesurable + contraintes + format de sortie + critère de verify), validé par les
   deux sources (empirique §1 + canon §2).

### Conception cible (validée avec user 19/07 matin)

- **Bibliothèque de workflows versionnée Gitea** → sync `.claude/workflows/` (résolution par nom,
  paramétrage par `args` : repo/scope/question). Même modèle que les rôles Ansible.
- **Granularité = 1 workflow par PHASE** (étude, revue, migration…), jamais un projet entier :
  le jugement entre phases reste à la session principale. Contrainte qui l'impose : `workflow()`
  imbriqué = 1 seul niveau.
- **GSD = la bibliothèque existante en prompt-space** (90 workflows, contrôle payé en tokens) ;
  cible = migrer les parties MÉCANIQUES vers des Workflow scripts (contrôle gratuit), garder le
  jugement en prompt. Pas un remplacement, une extraction.
- Philosophie Cherny : objectif + boucle de feedback vérifiable, l'humain cadre et revoit.
  Toujours un verdict vérifiable par boucle (pattern verify/reviewer).

## AUDIT FABLE (19/07 matin) — corrections À APPLIQUER lundi, prioritaires sur le plan ci-dessus

**Méthode (sinon conclusions fausses)** :
- Mining prompts : stratifier par `work_nature` (taxonomy existante) — les retries corrèlent avec
  la difficulté de la tâche, pas la forme du prompt (biais de confusion).
- Mesure POC : tokens depuis les JSONL locaux (précis), PAS la jauge oauth (% entiers) ;
  bras A/B = tâches jumelles indépendantes (re-exécuter la même tâche avantage le 2e bras).
- Corpus 215 sessions = pré-routage : séquences valides, coûts périmés — pondérer le récent.
- **Hygiène** : mining sur `data/sanitized/` UNIQUEMENT (P0-1 : 46 876 secrets dans les bruts).

**Bibliothèque workflows** :
- Chaque workflow a un smoke-test (args démo) + entre dans `make verify` + périmètre backup.
- Mutateurs → `isolation: worktree` ; JAMAIS de secret en `args` (transcripts = fuite).
- Défaut : bibliothèque globale + généricité par args (leçon P6 topics), pas de chemins en dur.
- Ops Pi : 1 workflow lourd à la fois sur waza.

**Gouvernance POC** :
- GO/NO-GO explicite : ex. −30 % tokens main-session ET verdict qualité identique (reviewer/tests
  sur les DEUX bras). Tokens sans qualité = régression.
- `/goal` : test contrôlé empirique AVANT toute doctrine (pattern A9 — le test tue ou valide).

**Hook R6** : cooldown anti-spam (1 nudge/topic/période) + exemption mode debug R5 + exemption
sessions GSD orchestrées (double-nudge). Leçon fatigue d'alerte ×2 (D1-1, veille).

**Périmètre inventaire commandes** : fiches SEULEMENT pour les commandes de boucle
(goal, tasks, routines, workflows, agent-teams, rewind) — pas les ~100 du binaire.

## Incident worker mémoire 19/07 midi (RÉSOLU — vérif résiduelle lundi)

Run incrémental de 15 h sur `banga/.ansible` (40 Mo, ~5 000 modules tiers vendorés — banga créé
la veille, ramassé par l'auto-découverte). Traité : stop timer+service (ordre timer d'abord,
sinon respawn), lock zombie supprimé (PID mort), **exclude `.ansible` ajouté au rôle
`llamaindex-memory-worker` (VPAI 079f8c5, déployé, vérifié live : skipped 258/260, contenu sain
ré-indexé)**. Unités memory-consolidate-rex + memory-eval-golden failed pendant la contention →
reset-failed, auto-heal au prochain timer hebdo.
**✅ PURGE FAITE 20/07 13h30** : 5 206 points `relative_path` préfixe `.ansible/` supprimés,
**244 légitimes conservés** (recount exact), recherche banga saine vérifiée (design/CLAUDE.md/
README remontent, zéro bruit). Méthode SANS index supplémentaire (contourne le piège
wait_timeout du REX juin) : scroll par filtre `repo` (indexé) → classification côté client sur
`relative_path` → delete par batches d'IDs. Incident worker mémoire : **100 % clos**.
**Divers résolus 20/07** : veille cc-release-watch durcie (ops 22ec285 — à 00:08 un update CC
en cours a fait lire « 2.1.75 » + changelog vide → digest bidon supprimé, state reseedé
2.1.215, gardes abstention ajoutées) ; timers nuit OK (gsd-model-audit 9 PASS silencieux,
00:12). Piège watcher à retenir : `pgrep -f` peut matcher SON PROPRE cmdline (watcher zombie
b822wjsy9) — ancrer le pattern sur un chemin réel (ex. `/opt/.*/index.py`).

## ✅ VERDICT SESSION 1 (2026-07-20, exécutée dimanche — jauge seven_day 6 %, reset déjà passé)

1. **Veille inbox lue** : digest 2.1.213→215 — caps runaway (200 subagents/200 WebSearch),
   SendMessage dédupliqué (économie inter-agents), piège pgrep self-match fixé upstream.
2. **Mining FAIT** (lab e8e3580) : `mine_tool_sequences.py` + `mine_prompt_efficacy.py`
   (tests 10/10, corrections audit appliquées). Top-10 documenté :
   `lab/analysis/2026-07-20-mining-tool-sequences-prompts.md`. Motif n°1 dispatch =
   boucle subagent-driven implement→review (~100 % main). Quick win hors Workflow :
   ToolSearch→qdrant-find (410 sessions) → précharger au SessionStart.
3. **POC exécuté** (lab 138cca1 + 4bb4256, protocole+résultats :
   `lab/evaluations/2026-07-20-poc-workflow-vs-classic.md`) —
   **verdict : NO-GO au seuil −30 % (out −23 %, ingestion −13 %), À REJOUER amendé** :
   schéma retour compact (détails sur disque) + tâche multi-rounds. Gain inattendu
   PROUVÉ : **subagents −31 %** (sortie structurée contraint la verbosité reviewer).
   Pas d'industrialisation bibliothèque tant que le re-POC n'a pas donné GO.
4. **Hook R6 LIVRÉ** (~/.claude 868aa8d, copie lab 4393b07) : `r6-delegation-advisor.js`
   PostToolUse advisory — nudge scout/mech au 6e Read / 11e Bash cumulés sans dispatch,
   reset au dispatch Agent/Workflow, 1 nudge/type/cycle + plancher 10 min, exemptions
   subagents + debug R5 + sessions GSD. Tests 31/31 (simulation stdin). Piège corrigé :
   `ts | 0` tronque Date.now() à 32 bits. NB : run-all.sh a 14 échecs PRÉEXISTANTS
   (topics/escalator/gate-log, prouvés par stash/re-run) → à trier séparément.

Session 2 = re-POC amendé + follow-ups code --since/--nature (listés au doc d'éval),
PUIS seulement gabarit prompts + inventaire commandes de boucle + bibliothèque Gitea.

## ✅ VERDICT SESSION 2 (2026-07-20 après-midi) — re-POC : **GO −77 %/−77 %**

Re-POC amendé exécuté (lab 9258c10, protocole+résultats :
`lab/evaluations/2026-07-20-re-poc-workflow-vs-classic.md`) sur les follow-ups
--since/--nature comme tâches jumelles (dette soldée en même temps, f0516a9 + 90506d4) :
- **GO net** : output −77 % (4 983→1 128 tok), ingestion −77 % (13 734→3 194 chars),
  seuil −30 % largement franchi. Gate qualité OK (0 CRITICAL des 2 côtés, pytest
  10/10 et 12/12). Verdict conservateur : le bras B a fait PLUS de rounds (3 reviews/
  2 fixes vs 2/1) pour un coût main 4,4× moindre.
- **Les 2 amendements prouvés** : retour compact (ingestion B 8 845→3 194 vs v1) ;
  multi-rounds (coût main A croît avec les rounds, B reste plat).
- **Contreparties chiffrées** : +44 % tokens subagents (rounds opus en plus),
  +119 % durée mur. Le pattern échange temps+volume subagent contre contexte main.
- Script v2 archivé `lab/workflows/implement-review-verify-v2.js` (1er élément de la
  bibliothèque). Journal du run : session e0526fff, wf_6942103a-327.

**Session 3 = industrialisation** : généraliser v2 par `args` (cible/pytest/périmètre
en dur), smoke-test + make verify + périmètre backup (audit Fable), bibliothèque
Gitea → sync `.claude/workflows/` ; + follow-up LOW résiduel (assertion
test_main_nature_filter inerte contre l'inversion du filtre) ; PUIS gabarit prompts
+ inventaire commandes de boucle (6 fiches max).

**Graphes/parallélisme (question user 20/07, statué)** : NON mesuré à ce jour — POC
v1/v2 = chaîne séquentielle seule (des workflows parallèles ont été utilisés ailleurs,
jamais A/B). Le mining ne classe aucun motif parallèle en tête (motif payé = boucle
séquentielle ; candidat n°2 = « stage de pipeline, pas un Workflow entier »). Le GO se
transfère a fortiori aux graphes (un fan-out classique coûte PLUS cher en main : N
rapports) et le parallélisme est le remède direct au +119 % de durée mesuré.
Contrainte : cap concurrence par workflow = min(16, cœurs−2) = **2 sur waza (Pi5
4 cœurs)** → fan-out large par vagues de 2, `pipeline()` (recouvrement) pleinement
utile. Décision : PAS de session dédiée — session 3 livre un **2e template parallèle**
(review multi-lentilles en `parallel()` 3 reviewers correctness/tests/périmètre +
fusion, ou pipeline de fix par fichier), mesuré au même `measure_arm_windows_v2.py`
→ verdict graphes obtenu pendant l'industrialisation.

## ✅ VERDICT SESSION 3 (2026-07-20 soir) — industrialisation LIVRÉE + GO graphes −44 % durée

1. **Bibliothèque v1** (lab c5ada5d→dc18a54) : `workflows/implement-review-verify.js`
   généralisé par args (repo/objective/scope/verify_cmd/constraints/hunt/max_review_rounds/
   implement, v2 POC → archive/) + `workflows/review-multilens.js` (2e template PARALLÈLE :
   3 lentilles opus correctness/tests/scope + fusion dédup script-space, revue seule — la
   session principale arbitre). Demo-args + fixtures + smoke-tests statiques + **harness node
   validate/simulate** (`scripts/wf_harness.mjs` — exécute la vraie validation d'args et la
   logique post-agents avec stubs) ; `make verify` lab = 41 tests verts.
2. **Verdict graphes : GO** (éval `evaluations/2026-07-20-parallel-multilens-verdict-graphes.md`,
   run wf_fd85b7e7 = revue réelle du diff session 3, pattern tâches jumelles) : mur 903 s vs
   1 615 s de séquentialisation des mêmes reviews = **−44 % durée** (slots 89 %, cap waza 2 ;
   extrapolé −56 % à cap ≥3). Main 1 686 tok out / 9 534 chars ingérés ; subagents 198 680 tok.
   Boucle bouclée : 9 findings (0C/0H/3M/6L, 2 recoupés par 2 lentilles) TOUS appliqués+testés.
3. **Gitea** : repo privé `mobuone/claude-code-improvement-lab` créé (API localhost:3030, token
   éphémère CLI admin, les 3 tokens de session révoqués). **Push du lab complet REFUSÉ** :
   l'historique contient des transcripts `data/sanitized/*.jsonl` committés pré-gitignore
   (risque scrubbing résiduel = périmètre P0-1) → backup = **snapshot orphelin du tree tracké**
   (`make backup-gitea`, 91fc948) ; bibliothèque → `make sync-claude` → `~/.claude/workflows/`
   (commit ~/.claude ee51c3c). Mirror complet différé post-P0-1.
4. **Gabarit prompts VALIDÉ** (`workflows/PROMPT-TEMPLATE.md` : objectif→contexte→contraintes→
   étapes numérotées→format exact→critère verify, sourcé mining+canon+2 runs) + **6 fiches
   commandes de boucle** (`recommendations/2026-07-20-fiches-commandes-boucle.md` : Workflow
   MESURÉ GO, /goal NON TESTÉ (A9, backlog), /tasks, /routines vs timers systemd, agent-teams
   non prioritaire, /rewind). Follow-up LOW soldé (assertion test_main_nature_filter
   discriminante : --min-bucket 1 + assert nature/sid du bucket).

**Pièges session 3** : args Workflow livré en CHAÎNE JSON via scriptPath (templates tolèrent
objet|string) ; la notification de résultat ÉCHOE les args (bloc recovery) → scope/hunt denses ;
le compteur measure v2 ignorait le contenu user de type string (la notification en est un) ;
prose « agent() » dans un message d'erreur = faux positif smoke (regex ancrée await|=>) ;
Gitea : POST /user/repos exige write:user, push-to-create OFF, HTTP sur 127.0.0.1:3030.

**Reste (session 4+)** : test contrôlé `/goal` (A9), migration du mécanique GSD vers Workflows,
mirror lab complet post-P0-1, trier les 14 échecs préexistants run-all.sh hooks.

## ✅ VERDICT SESSION 4 (2026-07-20 soir) — `/goal` : **GO headless** (A9 validé)

Test contrôlé A/B exécuté (lab `evaluations/2026-07-20-test-controle-goal.md`,
prompts jumeaux `evaluations/scenarios/goal-ab-arm-{A,B}.prompt.md`) :
1. **Tâches jumelles = 11 échecs MÉCANIQUES de run-all.sh** (triage scout 14/14 :
   4 clusters ; partition contrainte par le grain fichier 5v6) — dette soldée en même
   temps : bras A = fixture `tool_response` + isolation R0 du bloc R1 (commit ~/.claude
   `0ae8fb9`), bras B = 6 topics DOC_TOPICS via `docTopicsIn()` (`1328a64`).
   Suite hooks : 14 → 3 échecs.
2. **Verdict `/goal` : GO** — bras B (headless `claude -p "/goal …"` sonnet) : condition
   atteinte + **arrêt autonome propre** + aucun surcoût vs one-shot A (out −54 %,
   coût API −24 %, durée −13 % ; clause artefact : tâche B plus simple → conclusion
   « pas plus cher », pas « moins cher »). Critère ≤ 1,2× A largement franchi.
3. **Mécanique élucidée** : `/goal` = `Goal set` + **Stop hook session-scoped portant
   la condition** (3 blocs user injectés). L'« évaluateur Haiku par tour » de la doc
   n'apparaît PAS dans le JSONL (100 % sonnet). Fiche 2 mise à jour.
4. **Outillage** : `scripts/measure_headless_session.py` (v3 : session entière +
   ventilation par modèle, règles v2 conservées, pytest lab 47 verts, commit `621b9e0`).

**Restent (session 5+)** : cluster D `sources.yml` (3 échecs JUGEMENT : fixture
`R0_SOURCES_YML` hermétique et/ou régénération worker — dérive live RÉELLE : racines
`flash-studio` et `VPAI` mortes dans sources.yml, à statuer) ; migration du mécanique
GSD → Workflows (cadrage non entamé s4) ; mirror lab post-P0-1 ; `/goal` interactif
non testé.

## Rappels d'état

- Hebdo 98 % (**reset LUNDI 10:00**, corrigé par user), Opus scopé 83 %. Ne rien lancer de lourd avant.
- Restes programme : P0-1 scrubbing (réservé), backup offsite ~/.claude+lab (décision),
  spike @opengsd/gsd-core sandboxé, re-mesure 2026-08-17.
