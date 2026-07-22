---
title: Comparaison — Phase 10 AI Ops (VPAI) vs boucle d'amélioration Claude Code existante (lab + loops)
date: 2026-07-22
context: Demande opérateur — examiner si Phase 10 (planifiée, jamais exécutée) fait doublon avec le travail déjà livré ailleurs
status: DRAFT — à faire réfuter par Opus (reviewer local) et Codex (review-file.sh) avant synthèse
---

## 1. Les deux objets comparés

### Objet A — Phase 10: AI Ops (`.planning/phases/10-ai-ops/`, VPAI)
- Genèse : note `2026-04-12` (`ai-ops-langfuse-arize-decision.md`) — au moment de l'écriture,
  ULTIMATE-CONFIG couches 0-5 (hooks) étaient **"en cours d'implémentation"**, pas encore livrées.
- Spec figée le **2026-04-12** (10-CONTEXT.md, 10-TRACK-B-SPEC.md, 10-STATE.md) : **jamais planifiée**
  (aucun `PLAN.md`, `ROADMAP.md` dit "Plans: TBD"), donc **jamais exécutée**.
- Contenu : cycle d'amélioration continue des sessions Claude Code, deux tracks parallèles :
  - **Track A** : Langfuse Cloud free tier, branché sur hook `SessionStop`.
  - **Track B** : stack maison — `session-analyst.py` (enhanced) pousse en parallèle vers
    **7 destinations** : NocoDB (`claude_sessions`, stockage long terme), VictoriaMetrics+Grafana
    (dashboards tokens/coût), **Tempo** (nouveau service — traces OTLP via Alloy), Loki (logs
    structurés), Qdrant `sessions_v1` (recherche sémantique sur sessions passées), n8n +
    LiteLLM-juge (score qualité 1-10, alerte Telegram si <6), Gitea `claude-config` (corrélation
    sha CLAUDE.md/hooks ↔ session).
  - **Track C** (optionnel) : Langfuse self-hosted si rétention/confidentialité bloquent — décision
    différée à 4 semaines de données réelles (jamais atteintes, Track A/B jamais lancés).
  - Périmètre annoncé : **8 projets Waza**, pas seulement VPAI.
  - Un "coach mode" (génération async de patterns de prompts + `human_rating` Telegram) est
    esquissé en session 2 (10-STATE.md) mais pas détaillé au niveau spec.

### Objet B — Boucle d'amélioration Claude Code déjà LIVE (`~/work/ops/claude-code-improvement-lab/`
  + `~/work/ops/loops/`, hors VPAI, git local)
- Genèse : audit **2026-07-14** sur DEUX sources — l'archive `session-analyst` (2 240 JSONL
  févr→avril, **le même outil que Phase 10 veut "enhancer"**, analysé AVANT les hooks) + le live
  `~/.claude/projects/` (juin→juil, APRÈS hooks).
- **P0 à P4 déployés directement dans `~/.claude`** (git local, hooks vivants, pas une spec) :
  - bash-lint (fix message stderr), error-escalator **v2** (redesign PreToolUse+lecture transcript
    — découverte que PostToolUse ne se déclenche jamais sur un échec, CLI 2.1.209),
    workflow-guard désactivé (pure friction, 0/1651 suivi), gate R0 à 2 tiers, resume-gate,
    loop-detector v2 + signal `same_error`, boucle continue = timer systemd mensuel.
  - **Backup offsite Gitea LIVE depuis 2026-07-21** : `~/.claude` → `mobuone/claude-config`
    (privé) — **c'est exactement le repo Gitea que Phase 10 prévoyait de créer** pour la
    corrélation git sha. Il existe déjà, mais pour du backup, pas encore câblé à une corrélation
    session-par-session.
  - **Entonnoir de gate A+B+C (2026-07-22, jour même)** : hook `Stop` qui vérifie qu'un artefact
    texte substantiel présenté à un gate a bien été relu par Codex avant présentation
    (`notify-gate.sh` + `gate-funnel-stop.sh`) — un mécanisme de **contrôle qualité en temps réel**,
    différent dans sa forme du "score LLM après coup" de Phase 10 mais visant un objectif voisin
    (ne pas laisser passer du travail dégradé).
  - Programme **"Fable amiral"** (2026-07-21) : `/factor` (handoff session→téléphone),
    `graph-runner` (DAG d'agents, GO −57,6% tokens mesuré), doctrine essaims, `convergence.js`
    (boucle artefact→revue Codex→correction, générique).
- **`~/work/ops/loops/`** (projet frère, tracké Plane OPS-LOOPS) : `review-pr.sh` + timer
  `pr-watch` 15 min, `claude-usage-guard.sh` (jauges), pipeline consulting Codex
  (`review-file.sh`, `codex-verify.sh`) — **hors quota Claude**, routage modèle automatisé
  (`gsd-model-audit` hebdo, `token_audit` mensuel).
- **`project_loops_economie_tokens.md`** (sessions 1-9, 2026-07-20/21) : outillage de MESURE
  direct sur les JSONL — `measure_headless_session.py`, `mine_tool_sequences.py`,
  `mine_prompt_efficacy.py` — **calcule déjà tokens/coût/outils par session sans passer par
  NocoDB/VictoriaMetrics/Tempo**. Migration GSD→Workflows mesurée (2 GO, 1 NO-GO, règle d'arrêt
  appliquée).

## 2. Chevauchements identifiés (à charge, pour Opus/Codex : confirmer ou réfuter)

| # | Chevauchement | Phase 10 (avril, jamais exécuté) | Objet B (juillet, LIVE) | Verdict provisoire |
|---|---|---|---|---|
| 1 | Repo Gitea corrélation session↔config | `claude-config` à créer, token à générer, wiring `git_sha_hooks` | `mobuone/claude-config` **existe déjà** (backup offsite 21/07) | Infra dupliquée à l'identique si Phase 10 recrée le repo — seul le wiring applicatif (session→sha) manque encore des deux côtés |
| 2 | Mesure tokens/coût/outils par session | 7 destinations (NocoDB/VM/Loki/Tempo/Qdrant/n8n) à écrire | `measure_headless_session.py` + mining scripts déjà opérationnels, lisent le JSONL directement | Objet B résout la même question avec 0 nouveau service ; Phase 10 réinvente potentiellement la même extraction avant de la pousser vers 7 destinations |
| 3 | Détection de dégradation de session | Score LLM juge (n8n+LiteLLM, post-hoc, seuil <6 → Telegram) | Hooks déterministes temps réel (bash-lint, error-escalator, loop-detector, gate-funnel) — corrige/bloque PENDANT la session, pas après | Complémentaires en principe (rétrospectif vs temps réel) — mais Phase 10 (avril) ignore l'existence de ces hooks (postérieurs), donc son score LLM pourrait dupliquer un signal que loop-detector/error-escalator captent déjà différemment |
| 4 | session-analyst.py comme pivot | Doit être "enhanced" avec parser+7 destinations | Objet B l'a déjà utilisé comme SOURCE d'audit (archive févr-avril) mais a depuis construit ses PROPRES scripts de mesure séparés (measure_headless_session.py etc.), sans jamais toucher/enrichir session-analyst.py lui-même | Deux lignées d'outillage sur la même donnée source (JSONL), non réconciliées |
| 5 | Gouvernance / boucle "amélioration continue" | Objectif déclaré de la Phase 10 | `continuous-improvement.sh` (mode observe/propose, timer mensuel) DÉJÀ live et exécuté | Le nom même de la Phase 10 ("cycle d'amélioration continue") est déjà incarné par un mécanisme distinct et actif |
| 6 | Observabilité Grafana | Dashboards tokens/coût/qualité 30j (VictoriaMetrics) | Pas d'équivalent identifié dans le lab/loops — analyses = rapports markdown ponctuels, pas de dashboard vivant | **Pas de chevauchement** — reste une valeur ajoutée potentielle de Phase 10 |
| 7 | Recherche sémantique sur sessions passées | Qdrant `sessions_v1`, activé "après 50 paires" | R0-Continu / `memory_v1` (Qdrant) indexe déjà repos+REX ; pas de collection sessions dédiée trouvée | Pas de chevauchement direct, mais risque de fragmentation (encore une collection Qdrant séparée) si non arbitré avec R0-Continu |

## 3. Ce qui ne fait PAS doublon (a priori)

- **Track A Langfuse Cloud** : jamais mentionné dans le lab/loops, jamais commencé. Neutre.
- **Dashboards Grafana tokens/coût/qualité** : le lab produit des rapports ponctuels (markdown,
  `EXECUTIVE_SUMMARY.md`, `recommendations/*.md`), pas de dashboard vivant. Valeur ajoutée réelle
  si le besoin de suivi visuel continu est confirmé.
- **Alertes Telegram sur score qualité** : le lab alerte déjà sur d'autres signaux (gate-events,
  backup offsite) via `notify-gate.sh`, mais pas sur un score de qualité de session — angle neuf.

## 4. Question ouverte pour Opus / Codex

1. Le spec Phase 10 (figé avril, jamais mis à jour depuis) est-il encore une base saine pour
   planifier maintenant (juillet), ou son architecture (Langfuse+Tempo+Qdrant+n8n-juge) est-elle
   invalidée par ce qui a été construit entre-temps (hooks déterministes, gate-funnel, mesure
   directe JSONL) ?
2. Y a-t-il un chevauchement que la liste ci-dessus **rate** — notamment sur le repo Gitea
   `claude-config` (usage backup vs usage corrélation qualité), et sur la collection Qdrant
   `sessions_v1` vs `memory_v1` ?
3. Recommandation : (a) exécuter Phase 10 telle quelle, (b) la réduire au sous-ensemble non
   redondant (dashboards Grafana + NocoDB stockage long terme, sans Tempo/Qdrant/n8n-juge qui
   dupliquent l'existant), ou (c) la geler/archiver et documenter que son objectif est déjà
   substantiellement couvert par le lab+loops ?

---

## 5. Verdict final — après revue Opus (reviewer local) + Codex (`review-file.sh --sol`)

**Statut : brouillon corrigé. Ne pas se fier aux options (a)/(b) ci-dessus — voir réfutations.**

### Codex (4 MED, 0 HIGH)
- L'affirmation « jamais exécuté » manquait de preuve citée (elle tient : `ls` phase 10 = pas de
  `PLAN.md`, `ROADMAP.md` = "0/TBD").
- Le chiffre « graph-runner −57,6 % » cité hors contexte (protocole non lié).
- Item 4 (session-analyst) et Option (b) se contredisaient avec les rows 6-7 du tableau
  ("pas de doublon" puis "à retirer car doublon" pour Tempo/Qdrant).

### Opus (reviewer, lecture indépendante des sources) — verdict structurant
**Raté CRITICAL non vu par le brouillon ni par Codex** : `~/work/ops/loops/PLAN.md` **Phase 2**
(T2.1-T2.4, lignes 109-127) planifie **déjà** le récepteur OTLP→Alloy→VictoriaMetrics et un
dashboard Grafana "Claude Windows" (tokens/coût/par modèle/par loop) — **le même livrable que
Track B de Phase 10**, dans un backlog différent (tracké Plane OPS-LOOPS), non exécuté (bloqué sur
le NAS Banga en burn-in). Mon item 6 ("pas de chevauchement, valeur ajoutée") était **faux**.

Ratés HIGH :
- `10-QUALITY-FRAMEWORK.md:598-643` spécifie entièrement des "Règles 8-11" pour
  `prompt-preprocessor.js` (coach mode) — **collision directe** avec la "Règle 8" déjà déployée
  dans ce même hook par le lab (P2-1 resume-gate, 2026-07-16). Forkerait un hook activement
  maintenu ailleurs.
- `ROADMAP.md` (goal révisé, critères succès) a **déjà retiré Tempo et Qdrant `sessions_v1`** du
  périmètre — mais `10-TRACK-B-SPEC.md` (spec gelée) les garde. Phase 10 n'a **plus de référent
  unique** : "exécuter telle quelle" ne veut rien dire tant que ces deux documents divergent.

**Verdict global : NO-GO sur l'exécution de Phase 10 comme phase VPAI.**
Découpe par composant (remplace les options a/b) :

| Composant | Verdict |
|---|---|
| Track A Langfuse Cloud | Drop (jamais commencé, cloud externe = fuite P0-1 non résolu) |
| VictoriaMetrics+Loki+Alloy-OTLP+Grafana | Drop — relocaliser vers `ops/loops` Phase 2 (doublon direct) |
| Tempo | Drop (déjà hors goal ROADMAP, RAM Sese contrainte) |
| Qdrant `sessions_v1` | Drop (déjà hors goal, contredit la consolidation Qdrant `ops` non indexé) |
| NocoDB `claude_sessions` | Drop (VM+Plane OPS-LOOPS+rapports lab couvrent déjà le besoin) |
| Coach / Règles 8-11 preprocessor | Drop / proposer au lab (collision hook actif) |
| Juge qualité longitudinal (score 1-10 tendance 30j) | **Seul résidu non couvert** → à verser dans le backlog `ops/loops` (post-NAS), pas dans VPAI |

**Action recommandée** : marquer Phase 10 GELÉE/ARCHIVÉE dans `10-STATE.md`/`ROADMAP.md` (objectif
substantiellement couvert par lab P0-P4 + `continuous-improvement.sh` + `ops/loops` Phase 2-4),
verser le résidu "juge qualité longitudinal" au backlog `ops/loops`. Gate humain requis avant
d'écrire ce changement dans le planning (touche 2 repos).

---

## 6. Fusion "meilleur des deux" — après lecture directe `ops/loops/PLAN.md` Phase 2 +
   vérification factuelle OTEL native (doc officielle `code.claude.com/docs`)

**Question opérateur** : ne pas juste jeter Phase 10 — garder ce qu'elle fait de mieux, fusionné
dans `ops/loops` Phase 2 (T2.1-T2.4, lignes 109-127).

### Fait vérifié qui tranche le point technique central (télémétrie natives vs parsing maison)

| | OTEL natif (`CLAUDE_CODE_ENABLE_TELEMETRY=1`) | Parser maison Phase 10 (`session-analyst.py`) |
|---|---|---|
| Tokens + **coût USD** | ✅ natif, calculé auto par le CLI | Table `PRICING` codée à la main — **déjà périmée** (ne liste que `claude-sonnet-4-6`/`claude-opus-4-6`, absents : sonnet-5, opus-4.8, haiku-4.5, fable-5) |
| `session_id`, corrélation | ✅ natif (`session.id` sur tout span) | Recalculé depuis le nom de fichier JSONL |
| Décomposition par outil | Possible via `OTEL_LOG_TOOL_DETAILS=1` (attribut span), pas agrégé nativement | ✅ `tool_distribution` dict |
| **bash évitable / signaux sémantiques** | ❌ **hors scope OTEL** — confirmé, aucune sémantique | ✅ seule façon d'obtenir ce signal (regex sur `tool_use.input`) |
| **Signaux de correction utilisateur** | ❌ hors scope OTEL | ✅ seule façon (grep texte user) |

**Conclusion technique** : sur la partie où les deux se chevauchent (tokens/coût/dashboard), OTEL
natif est strictement supérieur — zéro table de pricing à maintenir, zéro parseur JSONL à écrire.
La partie sémantique de Phase 10 (bash évitable, corrections, compaction) est en revanche **la
seule à produire un signal qu'OTEL ne peut structurellement pas donner**.

### Design fusionné — greffer, pas dupliquer

| Brique | Origine | Action |
|---|---|---|
| Pipe OTLP→Alloy→VictoriaMetrics, dashboard Grafana "Claude Windows", alerte 80% fenêtre | `loops` Phase 2 (T2.1-T2.3) | **Backbone unique**, ne pas reconstruire côté VPAI |
| Coût USD, tokens, session_id | OTEL natif (T2.2) | Remplace intégralement le calcul manuel de Phase 10 — la table `PRICING` de `10-TRACK-B-SPEC.md` est jetée |
| `bash_avoidable` (regex), `correction_signals`, `compact_count` | Design Phase 10 (`10-TRACK-B-SPEC.md:213-232`) — **la seule partie à garder telle quelle** | Greffer en 2-3 métriques VM supplémentaires poussées par un parser JSONL léger, **réutilisant `lab/scripts/measure_headless_session.py` existant** (pas `session-analyst.py`, lignée abandonnée — cf §3 M4) plutôt qu'en écrire un 3e. Panels ajoutés au dashboard "Claude Windows" existant (T2.3), pas un nouveau dashboard. |
| Juge qualité LLM (score 1-10, tendance 30j) | Design Phase 10, seul résidu net-new (§4) | Garder — mais écrire le score comme **métrique VM** (gauge par session, même pipe), pas une table NocoDB séparée |
| Corrélation git sha CLAUDE.md/hooks | Design Phase 10 | Garder — via `OTEL_RESOURCE_ATTRIBUTES`, même mécanisme que `loop.name` (T2.2), pas de nouveau repo Gitea (celui de backup suffit) |
| Langfuse Cloud, Tempo, Qdrant `sessions_v1`, NocoDB `claude_sessions`, Coach/Règles 8-11 | Phase 10 | **Drop confirmé** — aucune de ces briques n'apporte un signal que le pipe fusionné ci-dessus ne couvre pas déjà, une fois la partie sémantique greffée |

**Amendement à proposer sur `ops/loops/PLAN.md` T2.2/T2.3** : ajouter la tâche "métriques
sémantiques (bash_avoidable/correction_signals/compact_count) via extension de
`measure_headless_session.py`" + 2-3 panels Grafana, comme sous-tâche de Phase 2 — pas une
nouvelle phase.

Gate humain requis avant d'écrire (2 repos : archiver Phase 10 côté VPAI + amender `loops/PLAN.md`
côté ops).
