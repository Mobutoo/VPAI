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

## Rappels d'état

- Hebdo 98 % (**reset LUNDI 10:00**, corrigé par user), Opus scopé 83 %. Ne rien lancer de lourd avant.
- Restes programme : P0-1 scrubbing (réservé), backup offsite ~/.claude+lab (décision),
  spike @opengsd/gsd-core sandboxé, re-mesure 2026-08-17.
